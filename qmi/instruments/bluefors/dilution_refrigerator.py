"""
Instrument driver for Bluefors dilution refrigerator, based on HTTP API.
"""

import json
import logging
import math
import urllib.parse
import urllib.request
from enum import Enum
from ipaddress import IPv4Address
from typing import Any
from xml.etree import ElementTree

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

# Logger for this module
_logger = logging.getLogger(__name__)

# Conversion constants
CONVERSION_BAR_MBAR = 1e3
CONVERSION_PSI_BAR = 0.0689475729
# Valid valve number range.
VALVE_MIN = 1
VALVE_MAX = 23
# Statuses of a posted value that indicate the request was not successful.
FAILED_STATUSES = ("INVALID", "DISCONNECTED")


class Commands(Enum):
    """Commands."""

    POST_COMMAND = "/values/?fields=name;value;status"
    GET_NAME_AND_VERSION = "/system/?"
    GET_LAYOUT = "/resources/layout.xml"
    GET_FLOWMETER = "/values/mapper/bf/flow?"
    GET_VALVE = "/values/mapper/bf/valves/{valve}?"
    GET_4K_HEATER_VOLTAGE = "/values/mapper/bflegacy/double/el302p_v?"
    GET_4K_HEATER_CURRENT = "/values/mapper/bflegacy/double/el302p_i?"
    GET_4K_HEATER_STATE = "/values/mapper/bf/heaters/heater?"
    GET_4K_FLANGE_TEMPERATURE = "/values/mapper/bf/temperatures/t4k?"
    GET_50K_FLANGE_TEMPERATURE = "/values/mapper/bf/temperatures/t50k?"
    GET_MAGNET_TEMPERATURE = "/values/mapper/bf/temperatures/tmagnet?"
    GET_STILL_FLANGE_TEMPERATURE = "/values/mapper/bf/temperatures/tstill?"
    GET_MXC_FLANGE_TEMPERATURE = "/values/mapper/bf/temperatures/tmixing?"
    GET_FSE_TEMPERATURE = "/values/mapper/bf/temperatures/tfse?"
    GET_STILL_HEATER_POWER = "/values/mapper/temperature_control/heaters/still/power?"
    GET_MXC_HEATER_STATE = "/values/mapper/temperature_control/heaters/sample/enabled?"
    GET_STILL_HEATER_STATE = "/values/mapper/temperature_control/heaters/still/enabled?"
    GET_MXC_HEATER_POWER = "/values/mapper/temperature_control/heaters/sample/power?"
    GET_P1_PRESSURE = "/values/mapper/bf/pressures/p1?"
    GET_P1_STATUS = "/values/mapper/bf/pressures/p1_on?"
    GET_P2_PRESSURE = "/values/mapper/bf/pressures/p2?"
    GET_P2_STATUS = "/values/mapper/bf/pressures/p2_on?"
    GET_P3_PRESSURE = "/values/mapper/bf/pressures/p3?"
    GET_P3_STATUS = "/values/mapper/bf/pressures/p3_on?"
    GET_P4_PRESSURE = "/values/mapper/bf/pressures/p4?"
    GET_P4_STATUS = "/values/mapper/bf/pressures/p4_on?"
    GET_P5_PRESSURE = "/values/mapper/bf/pressures/p5?"
    GET_P5_STATUS = "/values/mapper/bf/pressures/p5_on?"
    GET_P6_PRESSURE = "/values/mapper/bf/pressures/p6?"
    GET_P6_STATUS = "/values/mapper/bf/pressures/p6_on?"
    GET_CPA_TEMPERATURE_WATER_OUT = "/values/mapper/bflegacy/double/cpatempwo?"
    GET_CPA_TEMPERATURE_WATER_IN = "/values/mapper/bflegacy/double/cpatempwi?"
    GET_CPA_TEMPERATURE_OIL = "/values/mapper/bflegacy/double/cpatempo?"
    GET_CPA_TEMPERATURE_HELIUM = "/values/mapper/bflegacy/double/cpatemph?"
    GET_CPA_PRESSURE_LOW_SIDE = "/values/mapper/bflegacy/double/cpalpa?"
    GET_CPA_PRESSURE_HIGH_SIDE = "/values/mapper/bflegacy/double/cpahpa?"


class State(Enum):
    """Valve state (on/off) for valves."""

    OFF = 0
    ON = 1


def _value_name(path: str) -> str:
    """Derive the value name from a '/values/...' query path, e.g. '/values/mapper/bf/flow?' -> 'mapper.bf.flow'."""
    return path.split("?", maxsplit=1)[0].removeprefix("/values/").strip("/").replace("/", ".")


def _get_latest_value(data: dict[str, Any]) -> str:
    """Get the latest value out of a value entry. In case the device is not present or reachable, i.e. the
    device 'type' is 'null' in the original JSON dictionary, we just return "NaN".

    Parameters:
        data: The value entry dictionary obtained from a query response.

    Returns:
        The latest value as a string.

    Raises:
        QMI_InstrumentException: If the device reported an exception or the entry is malformed.
    """
    if data.get("type") is None:
        return "NaN"

    try:
        latest_value = data["content"]["latest_value"]
        value: str = latest_value["value"]
        exception: str = latest_value["exception"]
    except (KeyError, TypeError) as exc:
        raise QMI_InstrumentException(f"Unexpected value entry format: {data}") from exc

    if exception:
        owner = data["content"].get("owner")
        _logger.error("latest_value: %s", latest_value)
        raise QMI_InstrumentException(f"{owner} raised exception {exception}")

    return value


def _to_float(value: str) -> float:
    """Convert a value string into a float."""
    try:
        return float(value)
    except ValueError as exc:
        raise QMI_InstrumentException(f"Unexpected non-numeric value {value!r}") from exc


def _to_optional_float(value: str) -> float | None:
    """Convert a value string into a float, or None if the value is empty."""
    if value == "":
        return None

    return _to_float(value)


def _to_state(value: str) -> State:
    """Convert a value string into an on/off state."""
    number = _to_float(value)
    if math.isnan(number):
        raise QMI_InstrumentException("State value is not available")

    return State.ON if number else State.OFF


def _to_target_state(target_state: State | str) -> State:
    """Convert a target state given as a State or an 'ON'/'OFF' string (any case) into a State."""
    if isinstance(target_state, State):
        return target_state

    try:
        return State[target_state.upper()]
    except KeyError as exc:
        raise QMI_UsageException(f"{target_state} not an option for setting target state. Use 'ON' or 'OFF'") from exc


def _check_valve(valve: int) -> None:
    """Check that the valve number is in the valid range."""
    if not VALVE_MIN <= valve <= VALVE_MAX:
        raise QMI_UsageException(f"Valve number {valve} not in valid range [{VALVE_MIN}-{VALVE_MAX}]")


class Bluefors_DilutionRefrigerator(QMI_Instrument):
    """QMI driver for the Bluefors dilution refrigerator.

    Attributes:
        TIMEOUT:  Urllib request timeout. Default is 5 seconds.
        DISABLED: Setting valve states and 4k heater are disbaled by default.
    """

    _rpc_properties = {"TIMEOUT", "DISABLED"}
    # Default timeout for HTTP requests (seconds)
    TIMEOUT = 5
    DISABLED = True  # Flag to disable some potentially system-damaging commands

    def __init__(
        self, context: QMI_Context, name: str, ipv4_address: str, secure_port: bool = False, access_key: str = ""
    ) -> None:
        """Initialize the instrument driver.

        Parameters:
            context:        QMI Context.
            name:           Identifier for the instrument in the QMI context.
            ipv4_address:   IPv4 address of the device on the network.
            secure_port:    Boolean to select if to use secure port 49098. The default is False with port nr. 49099.
            access_key:     Access key to the data stream. Default empty string.
        """
        super().__init__(context, name)

        self._host = IPv4Address(ipv4_address)  # raises ValueError for improper address
        self._secure_port = secure_port
        if secure_port:
            if not access_key:
                raise QMI_InstrumentException("Need specific access keys for secure connections!")

            self._baseurl = f"https://{self._host}:49098"

        else:
            self._baseurl = f"http://{self._host}:49099"

        self._access_key = access_key

    def _build_url(self, path: str) -> str:
        """Build the full URL for a path, adding the access key as a query parameter if one is set."""
        url = f"{self._baseurl}{path}"
        if self._access_key:
            if "?" not in url:
                url += "?"
            elif not url.endswith("?"):
                url += "&"

            url += "key=" + urllib.parse.quote(self._access_key, safe="")

        return url

    def _request(self, path: str, data: dict[str, Any] | None = None) -> bytes:
        """Send a GET request, or a POST request with a JSON body if `data` is given, and return the response.

        Parameters:
            path: The path (and query) to be requested. Should be one of the 'Commands' enum class commands.
            data: Optional dictionary to post as JSON.

        Returns:
            The raw response body.

        Raises:
            QMI_InstrumentException: At a communication problem (HTTP or network error, timeout).
        """
        self._check_is_open()
        url = self._build_url(path)
        _logger.debug("[%s] Request: %s %s", self._name, "GET" if data is None else "POST", path)
        if data is None:
            req = urllib.request.Request(url, method="GET")
        else:
            req = urllib.request.Request(
                url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}, method="POST"
            )

        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as response:
                answer: bytes = response.read()
        except OSError as exc:
            # URLError, HTTPError and TimeoutError are all subclasses of OSError.
            raise QMI_InstrumentException(f"Error in communication with device: {exc}") from exc

        _logger.debug("[%s] Response: %s", self._name, answer)
        return answer

    def _request_json(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a request and parse the response as a JSON dictionary."""
        answer = self._request(path, data)
        try:
            parsed = json.loads(answer)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unable to parse response as JSON: {answer!r}") from exc

        if not isinstance(parsed, dict):
            raise QMI_InstrumentException(f"Unexpected response: {answer!r}")

        return parsed

    def _query_value(self, path: str) -> str:
        """Query a single value and return its latest value string.

        Parameters:
            path: A '/values/...' query path, the value name is derived from it.

        Returns:
            The latest value string; "" when the value is empty, "NaN" when the device is not available.
        """
        name = _value_name(path)
        response = self._request_json(path)
        try:
            entry = response["data"][name]
        except (KeyError, TypeError) as exc:
            raise QMI_InstrumentException(f"Value {name} not found in response") from exc

        return _get_latest_value(entry)

    def _send_command(self, name: str, value: Any) -> None:
        """Post a new value for a named setting and check the response status.

        Parameters:
            name:  The value name, e.g. 'mapper.temperature_control.heaters.still.power'.
            value: The new value.

        Raises:
            QMI_InstrumentException: If the command response was not successful or at a communication error.
        """
        content = {"data": {name: {"content": {"value": value}}}}
        answer = self._request_json(Commands.POST_COMMAND.value, content)
        try:
            status = answer["data"][name]["content"]["latest_value"]["status"]
        except (KeyError, TypeError) as exc:
            raise QMI_InstrumentException(f"Unexpected response to posting {name}={value}: {answer}") from exc

        if status in FAILED_STATUSES:
            raise QMI_InstrumentException(f"Posting {name}={value} not successful, status {status}.")

    def _get_pressure(self, gauge: int) -> float | None:
        """Get the pressure of a gauge in mbar, or None if the gauge is off or the value is empty."""
        status = self._query_value(Commands[f"GET_P{gauge}_STATUS"].value)
        if status == "" or _to_state(status) == State.OFF:
            return None

        pressure = _to_optional_float(self._query_value(Commands[f"GET_P{gauge}_PRESSURE"].value))
        if pressure is None:
            return None

        return pressure * CONVERSION_BAR_MBAR

    def _get_cpa_pressure(self, path: str) -> float | None:
        """Get a CPA pressure in bar, or None if the value is empty."""
        pressure = _to_optional_float(self._query_value(path))
        if pressure is None:
            return None

        return pressure * CONVERSION_PSI_BAR

    def set_valve(self, valve: int, target_state: State) -> None:
        """Set a valve state for a single specified valve.

        Parameters:
            valve:          Valve number.
            target_state:   target state (State.ON, State.OFF).
        """
        if self.DISABLED:
            raise QMI_UsageException(
                "Setting valve states through software is disabled by default."
                + " Enable only if you really know what you are doing."
            )

        _check_valve(valve)
        self._send_command(f"mapper.bf.v{valve}", target_state.value)

    def set_4k_heater_state(self, target_state: State) -> None:
        """Set the 4k heater ON or OFF.

        Parameters:
            target_state: 4K heater to be set State.ON or State.OFF.
        """
        if self.DISABLED:
            raise QMI_UsageException(
                "Setting 4k heater state through software is disabled by default."
                + " Enable only if you really know what you are doing."
            )

        self._send_command("mapper.bf.heaters.heater", target_state.value)

    @rpc_method
    def open(self) -> None:
        """Open the device interface. No connection is made; each call performs its own HTTP request."""
        self._check_is_closed()
        _logger.info("Opening connection to Bluefors_DilutionRefrigerator at %s", self._host)
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the device interface."""
        self._check_is_open()
        _logger.info("Closing connection to Bluefors_DilutionRefrigerator at %s", self._host)
        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Retrieve the device identification."""
        # Fixed vendor and model, no way to query it
        vendor = "Bluefors"
        model = "Dilution Refrigerator"

        info_dict = self._request_json(Commands.GET_NAME_AND_VERSION.value)
        try:
            version: str = info_dict["data"]["system_version"]
        except (KeyError, TypeError) as exc:
            raise QMI_InstrumentException(f"Unexpected system info response: {info_dict}") from exc

        return QMI_InstrumentIdentification(vendor=vendor, model=model, serial="?", version=version)

    @rpc_method
    def get_layout(self) -> ElementTree.Element:
        """Get the main layout file for the user interface.

        Returns:
            layout.xml file object.
        """
        response = self._request(Commands.GET_LAYOUT.value)
        try:
            return ElementTree.fromstring(response)
        except ElementTree.ParseError as exc:
            raise QMI_InstrumentException("Unable to parse layout XML") from exc

    @rpc_method
    def get_flowmeter_value(self) -> float:
        """Retrieve the latest flowmeter value.

        Returns:
            flow in mmol/s.
        """
        return _to_float(self._query_value(Commands.GET_FLOWMETER.value))

    @rpc_method
    def get_valve(self, valve: int) -> State:
        """Get a valve state for a single specified valve.

        Parameters:
            valve:          Valve number.

        Returns:
            Current state (State.ON, State.OFF).
        """
        _check_valve(valve)
        return _to_state(self._query_value(Commands.GET_VALVE.value.format(valve=f"v{valve}")))

    @rpc_method
    def get_4k_heater_state(self) -> State:
        """Get 4k heater state.

        Returns:
            Current state (State.ON, State.OFF).
        """
        return _to_state(self._query_value(Commands.GET_4K_HEATER_STATE.value))

    @rpc_method
    def get_4k_flange_temperature(self) -> float | None:
        """Get 4k flange temperature.

        Returns:
            flange temperature in Kelvins.
        """
        return _to_optional_float(self._query_value(Commands.GET_4K_FLANGE_TEMPERATURE.value))

    @rpc_method
    def get_50k_flange_temperature(self) -> float | None:
        """Get 50k flange temperature.

        Returns:
            flange temperature in Kelvins.
        """
        return _to_optional_float(self._query_value(Commands.GET_50K_FLANGE_TEMPERATURE.value))

    @rpc_method
    def get_magnet_temperature(self) -> float | None:
        """Get magnet temperature.

        Returns:
            magnet temperature in Kelvins.
        """
        return _to_optional_float(self._query_value(Commands.GET_MAGNET_TEMPERATURE.value))

    @rpc_method
    def get_still_flange_temperature(self) -> float | None:
        """Get still flange temperature.

        Returns:
            flange temperature in Kelvins.
        """
        return _to_optional_float(self._query_value(Commands.GET_STILL_FLANGE_TEMPERATURE.value))

    @rpc_method
    def get_mxc_flange_temperature(self) -> float | None:
        """Get MXC flange temperature.

        Returns:
            flange temperature in Kelvins.
        """
        return _to_optional_float(self._query_value(Commands.GET_MXC_FLANGE_TEMPERATURE.value))

    @rpc_method
    def get_fse_temperature(self) -> float | None:
        """Get FSE temperature.

        Returns:
            FSE temperature in Kelvins.
        """
        return _to_optional_float(self._query_value(Commands.GET_FSE_TEMPERATURE.value))

    @rpc_method
    def get_mxc_heater_state(self) -> State:
        """Get MXC heater (sample) enabled state.

        Returns:
            Current enabled state (State.ON, State.OFF)
        """
        return _to_state(self._query_value(Commands.GET_MXC_HEATER_STATE.value))

    @rpc_method
    def set_mxc_heater_state(self, target_state: State | str) -> None:
        """Set MXC heater (sample) enabled state.

        Parameters:
            target_state: Target enabled state, State.ON/State.OFF or a string "ON"/"OFF" (case-insensitive).
        """
        state = _to_target_state(target_state)
        self._send_command("mapper.temperature_control.heaters.sample.enabled", state.value)

    @rpc_method
    def get_mxc_heater_power(self) -> float:
        """Get sample power from the sample.

        Returns:
            Sample power in Watts
        """
        return _to_float(self._query_value(Commands.GET_MXC_HEATER_POWER.value))

    @rpc_method
    def set_mxc_heater_power(self, power: float) -> None:
        """Set the sample power.

        Parameters:
            power: The target power in Watts. Must be non-negative.
        """
        if power < 0:
            raise QMI_UsageException(f"Heater power {power} W must be non-negative")

        self._send_command("mapper.temperature_control.heaters.sample.power", power)

    @rpc_method
    def get_still_heater_state(self) -> State:
        """Get still heater enabled state.

        Returns:
            Current enabled state (State.ON, State.OFF)
        """
        return _to_state(self._query_value(Commands.GET_STILL_HEATER_STATE.value))

    @rpc_method
    def set_still_heater_state(self, target_state: State | str) -> None:
        """Set still heater enabled state.

        Parameters:
            target_state: Target enabled state, State.ON/State.OFF or a string "ON"/"OFF" (case-insensitive).
        """
        state = _to_target_state(target_state)
        self._send_command("mapper.temperature_control.heaters.still.enabled", state.value)

    @rpc_method
    def get_still_heater_power(self) -> float:
        """Get still heater power.

        Returns:
            Still heater power in Watts
        """
        return _to_float(self._query_value(Commands.GET_STILL_HEATER_POWER.value))

    @rpc_method
    def set_still_heater_power(self, power: float) -> None:
        """Set the still heater power.

        Parameters:
            power: The target power in Watts. Must be non-negative.
        """
        if power < 0:
            raise QMI_UsageException(f"Heater power {power} W must be non-negative")

        self._send_command("mapper.temperature_control.heaters.still.power", power)

    @rpc_method
    def get_p1_pressure(self) -> float | None:
        """Get pressure of P1.

        Returns:
            pressure in mbar, or None if the gauge is off or no value is available.
        """
        return self._get_pressure(1)

    @rpc_method
    def get_p2_pressure(self) -> float | None:
        """Get pressure of P2.

        Returns:
            pressure in mbar, or None if the gauge is off or no value is available.
        """
        return self._get_pressure(2)

    @rpc_method
    def get_p3_pressure(self) -> float | None:
        """Get pressure of P3.

        Returns:
            pressure in mbar, or None if the gauge is off or no value is available.
        """
        return self._get_pressure(3)

    @rpc_method
    def get_p4_pressure(self) -> float | None:
        """Get pressure of P4.

        Returns:
            pressure in mbar, or None if the gauge is off or no value is available.
        """
        return self._get_pressure(4)

    @rpc_method
    def get_p5_pressure(self) -> float | None:
        """Get pressure of P5.

        Returns:
            pressure in mbar, or None if the gauge is off or no value is available.
        """
        return self._get_pressure(5)

    @rpc_method
    def get_p6_pressure(self) -> float | None:
        """Get pressure of P6.

        Returns:
            pressure in mbar, or None if the gauge is off or no value is available.
        """
        return self._get_pressure(6)

    @rpc_method
    def get_cpa_temperature_water_out(self) -> float | None:
        """Get cooling water output temperature of CPA.

        Returns:
            temperature in deg C.
        """
        return _to_optional_float(self._query_value(Commands.GET_CPA_TEMPERATURE_WATER_OUT.value))

    @rpc_method
    def get_cpa_temperature_water_in(self) -> float | None:
        """Get cooling water input temperature of CPA.

        Returns:
            temperature in deg C.
        """
        return _to_optional_float(self._query_value(Commands.GET_CPA_TEMPERATURE_WATER_IN.value))

    @rpc_method
    def get_cpa_temperature_oil(self) -> float | None:
        """Get oil temperature of CPA.

        Returns:
            temperature in deg C.
        """
        return _to_optional_float(self._query_value(Commands.GET_CPA_TEMPERATURE_OIL.value))

    @rpc_method
    def get_cpa_temperature_helium(self) -> float | None:
        """Get helium temperature of CPA.

        Returns:
            temperature in deg C.
        """
        return _to_optional_float(self._query_value(Commands.GET_CPA_TEMPERATURE_HELIUM.value))

    @rpc_method
    def get_cpa_average_high_side_pressure(self) -> float | None:
        """Get avg high side pressure of CPA.

        Returns:
            pressure in bar.
        """
        return self._get_cpa_pressure(Commands.GET_CPA_PRESSURE_HIGH_SIDE.value)

    @rpc_method
    def get_cpa_average_low_side_pressure(self) -> float | None:
        """Get avg low side pressure of CPA.

        Returns:
            pressure in bar.
        """
        return self._get_cpa_pressure(Commands.GET_CPA_PRESSURE_LOW_SIDE.value)
