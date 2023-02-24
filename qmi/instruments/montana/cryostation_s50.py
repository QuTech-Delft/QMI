"""Instrument driver for the Montana Cryostation S50."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import json
import logging
from typing import Dict, Optional, Union, cast
import http
import urllib.error
import urllib.parse
import urllib.request

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.exceptions import QMI_InstrumentException, QMI_RuntimeException
from qmi.core.rpc import rpc_method

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class Montana_CryostationS50_Thermometer_Properties:
    """
    Dataclass for the Montana S50 thermometer properties of the sample.
    """
    resistance_ok: bool
    resistance: float
    temperature_ok: bool
    temperature: float
    temperature_stability: float
    temperature_stability_ok: bool
    temperature_stable: bool


class Montana_CryostationS50(QMI_Instrument):
    """
    Instrument driver for the Montana Cryostation S50.
    The S50 uses a RESTful API for communication.
    """

    # the cryostation should respond within 5 seconds
    RESPONSE_TIMEOUT = 5.0

    # subsystem strings
    CONTROLLER_SUBSYSTEM_STR = "controller"
    CRYOCOOLER_SUBSYSTEM_STR = "cooler/cryocooler"
    SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR = "sampleChamber/temperatureControllers/platform"

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 ipv4_address: str
                 ) -> None:
        """
        Initializes a Montana_Cryostation_s50 instance.

        Note:
            This method should not be called directly by a QMI user.
            Always instantiate an instrument via a QMI_Context `make_instrument()` call.

        Arguments:
            context:        the QMI context
            name:           the name of the instrument instance
            ipv4_address:   the IP address of the cryostation
        """

        super().__init__(context, name)
        self._host = IPv4Address(ipv4_address)  # raises ValueError for improper address
        self._base_url = f"http://{self._host}:47101/v1"
        self._timeout = Montana_CryostationS50.RESPONSE_TIMEOUT
        self._is_open = False

    def _send_request(self, url: str, request_type: str, data: Optional[bytes] = None) -> Optional[Dict[str, str]]:
        valid_request_types = ["GET", "PUT", "POST"]
        if not self._is_open:
            raise QMI_RuntimeException("Open device first")
        _logger.debug("Request: %s", url)

        if request_type not in valid_request_types:
            raise QMI_RuntimeException(f"Valid request types are {valid_request_types}")

        # send request and check for response
        req = urllib.request.Request(url, method=request_type, data=data)
        try:
            with urllib.request.urlopen(req) as response:
                status = response.status
                res = response.read() if request_type == 'GET' else None
            if status != http.HTTPStatus.OK:
                raise QMI_InstrumentException(f"HTTP error code: {status}")
        except urllib.error.HTTPError as exc:
            raise QMI_InstrumentException("Error in communication with device") from exc

        return json.loads(res) if request_type == 'GET' else None

    def _set_property(self, subsystem: str, key: str, value: Union[str, float, bool]) -> None:
        # create json dictionary and encode for PUT
        data = {
            key: value
        }
        json_data = json.dumps(data, indent=4)
        encoded_data = bytes(json_data, 'utf-8')

        url = f"{self._base_url}/{subsystem}/properties/{key}"
        self._send_request(url, 'PUT', encoded_data)

    def _get_property(self, subsystem: str, key: str) -> str:
        url = f"{self._base_url}/{subsystem}/properties/{key}"
        response = self._send_request(url, 'GET')
        if response is None:
            raise QMI_InstrumentException("Did not receive any response from a GET request")
        return response[key]

    def _run_method(self, subsystem: str, key: str) -> None:
        url = f"{self._base_url}/{subsystem}/methods/{key}()"
        self._send_request(url, 'POST')

    def _set_platform_bakeout(self, enable: bool) -> None:
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutEnabled", enable)

    @rpc_method
    def open(self) -> None:
        """Opens a connection to the Cryostation instrument."""
        _logger.info("Opening connection to %s", self._name)
        super().open()

    @rpc_method
    def close(self) -> None:
        """Closes a connection to the Cryostation instrument."""
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)
        super().close()

    @rpc_method
    def get_system_goal(self) -> str:
        """
        Gets the current goal of the system.
        """
        _logger.info("Getting system goal of %s", self._name)
        return self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "systemGoal")

    @rpc_method
    def get_system_state(self) -> str:
        """
        Gets the current state of the system.
        """
        _logger.info("Gettng system state of %s", self._name)
        return self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "systemState")

    @rpc_method
    def cooldown_allowed(self) -> bool:
        """
        Checks if the system is in a state where a cooldown can be started.

        Returns:
            true if the system can be cooled down.
        """
        _logger.info("Checking if cooldown is allowed for %s", self._name)
        return bool(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "canCooldown"))

    @rpc_method
    def warmup_allowed(self) -> bool:
        """
        Checks if the system is in a state where a warmup can be started.

        Returns:
            true if the system can be warmed up down.
        """
        _logger.info("Checking if warmup is allowed for %s", self._name)
        return bool(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "canWarmup"))

    @rpc_method
    def set_platform_target_temperature(self, temp: float) -> None:
        """
        Sets the platform target temperature for cooldown.

        Parameters:
            temp: temperature to set in Kelvin.
        """
        _logger.info("Setting platform target temperature of %s", self._name)
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformTargetTemperature", temp)

    @rpc_method
    def get_platform_target_temperature(self) -> float:
        """
        Gets the temperature that the platform is to be cooled down to.

        Returns:
            temperature in Kelvin
        """
        _logger.info("Getting platform target temperature of %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformTargetTemperature"))

    @rpc_method
    def get_platform_target_temperature_limit(self) -> float:
        """
        Gets the temperature limit that the platform can be cooled down to.

        Returns:
            temperature in Kelvin
        """
        _logger.info("Getting max platform temperature for %s", self._name)
        return float(self._get_property(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR, "temperatureLimit"))

    @rpc_method
    def start_cooldown(self) -> None:
        """
        Cools down the sample chamber to the target temperature.
        """
        _logger.info("Starting cooldown of %s", self._name)
        self._run_method(self.CONTROLLER_SUBSYSTEM_STR, "cooldown")

    @rpc_method
    def start_warmup(self) -> None:
        """
        Warms up the sample chamber.
        """
        _logger.info("Starting warmup of %s", self._name)
        self._run_method(self.CONTROLLER_SUBSYSTEM_STR, "warmup")

    @rpc_method
    def enable_platform_bakeout(self) -> None:
        """
        Enables bakeout of platform when cooling down or pulling vacuum.
        """
        _logger.info("Enabling platform bakeout of %s", self._name)
        self._set_platform_bakeout(True)

    @rpc_method
    def disable_platform_bakeout(self) -> None:
        """
        Disables bakeout of platform when cooling down or pulling vacuum.
        """
        _logger.info("Disabling platform bakeout of %s", self._name)
        self._set_platform_bakeout(False)

    @rpc_method
    def is_platform_bakeout_enabled(self) -> bool:
        """
        Checks if the platform bakeout procedure is enabled.

        Returns:
            true if bakeout is enabled else false
        """
        _logger.info("Checking is platform bakeout is enable for %s", self._name)
        return bool(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutEnabled"))

    @rpc_method
    def get_platform_bakeout_temperature_limit(self) -> float:
        """
        Gets the temperature limit that the platform can be baked to.

        Returns:
            temperature in Kelvin
        """
        _logger.info("Getting max platform bakeout temperature for %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTemperatureLimit"))

    @rpc_method
    def set_platform_bakeout_temperature(self, temp: float) -> None:
        """
        Sets the platform bakeout temperature.

        Parameters:
            temp: temperature to set in Kelvin.
        """
        _logger.info("Setting platform bakeout temperature for %s", self._name)
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTemperature", temp)

    @rpc_method
    def get_platform_bakeout_temperature(self) -> float:
        """
        Gets the platform bakeout temperature.

        Returns:
            temperature in Kelvin
        """
        _logger.info("Getting platform bakeout temperature for %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTemperature"))

    @rpc_method
    def set_platform_bakeout_time(self, time: float) -> None:
        """
        Sets the platform bakeout time.

        Parameters:
            time: time to set in seconds.
        """
        _logger.info("Setting platform bakeout time for %s", self._name)
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTime", time)

    @rpc_method
    def get_platform_bakeout_time(self) -> float:
        """
        Gets the platform bakeout time.

        Returns:
            time in seconds
        """
        _logger.info("Getting platform bakeout time for %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTime"))

    @rpc_method
    def is_cryocooler_running(self) -> bool:
        """
        Checks if the cryocooler is running.

        Returns:
            true if the cryocooler is running else false
        """
        _logger.info("Checking if cryocooler is running for %s", self._name)
        return bool(self._get_property(self.CRYOCOOLER_SUBSYSTEM_STR, "cryocoolerRunning"))

    @rpc_method
    def is_cryocooler_connected(self) -> bool:
        """
        Checks if the cryocooler is connected and communicating properly.

        Returns:
            true if the cryocooler is connected and communicating properly else false
        """
        _logger.info("Checking if cryocooler is connected for %s", self._name)
        return bool(self._get_property(self.CRYOCOOLER_SUBSYSTEM_STR, "deviceConnected"))

    @rpc_method
    def get_sample_thermometer_properties(self) -> Montana_CryostationS50_Thermometer_Properties:
        """
        Gets the thermometer properties of the sample.

        Returns:
            Dataclass with the properties
        """
        _logger.info("Getting thermometer properties for sample for %s", self._name)
        dict_data: Dict[str, str] = cast(Dict[str, str], self._get_property(
            self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR + "/thermometer", "sample"))
        return Montana_CryostationS50_Thermometer_Properties(
            bool(dict_data["resistanceOK"]),
            float(dict_data["resistance"]),
            bool(dict_data["temperatureOK"]),
            float(dict_data["temperature"]),
            float(dict_data["temperatureStability"]),
            bool(dict_data["temperatureStabilityOK"]),
            bool(dict_data["temperatureStable"]))
