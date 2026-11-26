"""Common base for Montana Cryostation drivers that use the RESTful API (S50, S100).

This module is private. Use the model-specific drivers in `qmi.instruments.montana.cryostation_s50` and
`qmi.instruments.montana.cryostation_s100` instead.
"""

import http
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from ipaddress import IPv4Address
from typing import Any, cast

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_RuntimeException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class Montana_CryostationRest_Thermometer_Properties:
    """Dataclass for the thermometer properties of a Montana cryostation temperature controller.

    Attributes:
        resistance_ok:            True if the thermometer resistance reading is valid.
        resistance:               thermometer resistance in Ohm.
        temperature_ok:           True if the temperature reading is valid.
        temperature:              temperature in Kelvin.
        temperature_stability:    temperature stability in Kelvin.
        temperature_stability_ok: True if the temperature stability reading is valid.
        temperature_stable:       True if the temperature is stable.
    """

    resistance_ok: bool
    resistance: float
    temperature_ok: bool
    temperature: float
    temperature_stability: float
    temperature_stability_ok: bool
    temperature_stable: bool


@dataclass
class Montana_CryostationRest_Heater_Properties:
    """Dataclass for the heater properties of a Montana cryostation temperature controller.

    Attributes:
        current:     heater current in Ampere.
        power:       heater power in Watt.
        restriction: heater restriction flag, as reported by the controller.
    """

    current: float
    power: float
    restriction: bool


class Montana_CryostationRest_System_State(Enum):
    """Possible states that the system can be in."""

    INVALID = "Invalid"
    IDLE = "Idle"
    CONFIGURING = "Configuring"
    READY = "Ready"
    WAITING_FOR_VACUUM_SYSTEM = "WaitingForVacuumSystem"
    CLEANING_VACUUM_LINES = "CleaningVacuumLines"
    CHECKING_FOR_LEAKS = "CheckingForLeaks"
    BAKEOUT_PREHEATING = "BakeoutPreheating"
    BAKING_OUT = "BakingOut"
    PURGING = "Purging"
    PULLING_VACUUM = "Pulling Vacuum"
    COOLING_DOWN = "CoolingDown"
    ACQUIRING_TARGET = "AcquiringTarget"
    STABLE_AT_TARGET = "StableAtTarget"
    WARMING_UP = "WarmingUp"
    VENTING = "Venting"


class Montana_CryostationRest_System_Goal(Enum):
    """Possible goals of the system."""

    NONE = "None"
    PULL_VACUUM = "PullVacuum"
    VENT = "Vent"
    COOLDOWN = "Cooldown"
    WARMUP = "Warmup"


def _parse_thermometer_properties(dict_data: dict[str, Any]) -> Montana_CryostationRest_Thermometer_Properties:
    """Convert a "sample" thermometer response into a dataclass."""
    return Montana_CryostationRest_Thermometer_Properties(
        bool(dict_data["resistanceOK"]),
        float(dict_data["resistance"]),
        bool(dict_data["temperatureOK"]),
        float(dict_data["temperature"]),
        float(dict_data["temperatureStability"]),
        bool(dict_data["temperatureStabilityOK"]),
        bool(dict_data["temperatureStable"]),
    )


def _parse_heater_properties(dict_data: dict[str, Any]) -> Montana_CryostationRest_Heater_Properties:
    """Convert a "sample" heater response into a dataclass."""
    return Montana_CryostationRest_Heater_Properties(
        float(dict_data["current"]), float(dict_data["power"]), bool(dict_data["restriction"])
    )


class Montana_CryostationRest_Base(QMI_Instrument):
    """Base class for Montana cryostations controlled through the RESTful API (port 47101).

    All RPC methods that communicate with the instrument raise a `QMI_RuntimeException` if the instrument
    is not open, and a `QMI_InstrumentException` if the HTTP request fails.
    """

    _rpc_properties = {"RESPONSE_TIMEOUT"}

    # Response Timeout.
    RESPONSE_TIMEOUT = 5.0

    # Subsystem strings.
    CONTROLLER_SUBSYSTEM_STR = "controller"
    CRYOCOOLER_SUBSYSTEM_STR = "cooler/cryocooler"
    COOLER_TEMP_CONTROLLER_SUBSYSTEM_STR = "cooler/temperatureControllers"
    SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR = "sampleChamber/temperatureControllers/platform"
    CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR = "sampleChamber/temperatureControllers/cryoOptic"

    # System states.
    SYSTEM_STATES = {value.value: value for value in Montana_CryostationRest_System_State}

    # System goals.
    SYSTEM_GOALS = {value.value: value for value in Montana_CryostationRest_System_Goal}

    def __init__(self, context: QMI_Context, name: str, ipv4_address: str) -> None:
        """Initializes a Montana cryostation instance.

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
        self._timeout = self.RESPONSE_TIMEOUT
        self._is_open = False

    def _send_request(self, url: str, request_type: str, data: bytes | None = None) -> dict[str, Any] | None:
        """Send a GET, PUT or POST request to the instrument.

        Parameters:
            url:            the url to send the request to.
            request_type:   the type of the request.
            data:           optional data for PUT and POST requests.

        Returns:
            the decoded JSON response for a GET request, else None.

        Raises:
            QMI_RuntimeException:    if the instrument is not open or the request type is invalid.
            QMI_InstrumentException: if the HTTP request fails.
        """
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
                if status != http.HTTPStatus.OK:
                    raise QMI_InstrumentException(f"HTTP error code: {status}")

                if request_type == "GET":
                    return json.loads(response.read())

        except urllib.error.HTTPError as exc:
            raise QMI_InstrumentException("Error in communication with device") from exc

        return None

    def _set_property(self, subsystem: str, key: str, value: str | float | bool) -> None:
        """Send a PUT request to set the property.

        Parameters:
            subsystem:  the subsystem to set the property for.
            key:        the name of the property to set.
            value:      the value to set.
        """
        # create json dictionary and encode for PUT
        json_data = json.dumps({key: value}, indent=4)
        url = f"{self._base_url}/{subsystem}/properties/{key}"
        self._send_request(url, "PUT", bytes(json_data, "utf-8"))

    def _get_property(self, subsystem: str, key: str) -> Any:
        """Send a GET request to get the property.

        Parameters:
            subsystem:  the subsystem to get the property for.
            key:        the name of the property to get.

        Returns:
            the value of the property, decoded from JSON.

        Raises:
            QMI_InstrumentException: if no response was received.
        """
        url = f"{self._base_url}/{subsystem}/properties/{key}"
        response = self._send_request(url, "GET")
        if response is None:
            raise QMI_InstrumentException("Did not receive any response from a GET request")
        return response[key]

    def _run_method(self, subsystem: str, key: str) -> None:
        """Send a POST request to run a method of a subsystem.

        Parameters:
            subsystem:  the subsystem to run the method on.
            key:        the name of the method to run.
        """
        url = f"{self._base_url}/{subsystem}/methods/{key}()"
        self._send_request(url, "POST")

    def _set_platform_bakeout(self, enable: bool) -> None:
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutEnabled", enable)

    def _get_thermometer_properties(self, subsystem: str) -> Montana_CryostationRest_Thermometer_Properties:
        """Get the "sample" thermometer properties of a temperature controller subsystem."""
        dict_data = cast(dict[str, Any], self._get_property(subsystem + "/thermometer", "sample"))
        return _parse_thermometer_properties(dict_data)

    def _get_heater_properties(self, subsystem: str) -> Montana_CryostationRest_Heater_Properties:
        """Get the "sample" heater properties of a temperature controller subsystem."""
        dict_data = cast(dict[str, Any], self._get_property(subsystem + "/heater", "sample"))
        return _parse_heater_properties(dict_data)

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
    def get_system_goal(self) -> Montana_CryostationRest_System_Goal:
        """Get the current goal of the system.

        Returns:
            the goal of the system as an enum.
        """
        _logger.info("Getting system goal of %s", self._name)
        goal = self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "systemGoal")
        return self.SYSTEM_GOALS[goal]

    @rpc_method
    def get_system_state(self) -> Montana_CryostationRest_System_State:
        """Get the current state of the system.

        Returns:
            the state of the system as an enum.
        """
        _logger.info("Getting system state of %s", self._name)
        state = self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "systemState")
        return self.SYSTEM_STATES[state]

    @rpc_method
    def cooldown_allowed(self) -> bool:
        """Check if the system is in a state where a cooldown can be started.

        Returns:
            True if the system can be cooled down, else False.
        """
        _logger.info("Checking if cooldown is allowed for %s", self._name)
        return bool(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "canCooldown"))

    @rpc_method
    def warmup_allowed(self) -> bool:
        """Check if the system is in a state where a warmup can be started.

        Returns:
            True if the system can be warmed up, else False.
        """
        _logger.info("Checking if warmup is allowed for %s", self._name)
        return bool(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "canWarmup"))

    @rpc_method
    def set_platform_target_temperature(self, temp: float) -> None:
        """Set the platform target temperature for cooldown.

        Parameters:
            temp: temperature to set in Kelvin.
        """
        _logger.info("Setting platform target temperature of %s", self._name)
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformTargetTemperature", temp)

    @rpc_method
    def get_platform_target_temperature(self) -> float:
        """Get the temperature that the platform is to be cooled down to.

        Returns:
            temperature in Kelvin.
        """
        _logger.info("Getting platform target temperature of %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformTargetTemperature"))

    @rpc_method
    def get_platform_target_temperature_limit(self) -> float:
        """Get the temperature limit that the platform can be cooled down to.

        Returns:
            temperature in Kelvin.
        """
        _logger.info("Getting max platform temperature for %s", self._name)
        return float(self._get_property(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR, "temperatureLimit"))

    @rpc_method
    def start_cooldown(self) -> None:
        """Cool down the sample chamber to the target temperature."""
        _logger.info("Starting cooldown of %s", self._name)
        self._run_method(self.CONTROLLER_SUBSYSTEM_STR, "cooldown")

    @rpc_method
    def start_warmup(self) -> None:
        """Warm up the sample chamber."""
        _logger.info("Starting warmup of %s", self._name)
        self._run_method(self.CONTROLLER_SUBSYSTEM_STR, "warmup")

    @rpc_method
    def enable_platform_bakeout(self) -> None:
        """Enable bakeout of platform when cooling down or pulling vacuum."""
        _logger.info("Enabling platform bakeout of %s", self._name)
        self._set_platform_bakeout(True)

    @rpc_method
    def disable_platform_bakeout(self) -> None:
        """Disable bakeout of platform when cooling down or pulling vacuum."""
        _logger.info("Disabling platform bakeout of %s", self._name)
        self._set_platform_bakeout(False)

    @rpc_method
    def is_platform_bakeout_enabled(self) -> bool:
        """Check if the platform bakeout procedure is enabled.

        Returns:
            True if bakeout is enabled, else False.
        """
        _logger.info("Checking if platform bakeout is enabled for %s", self._name)
        return bool(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutEnabled"))

    @rpc_method
    def get_platform_bakeout_temperature_limit(self) -> float:
        """Get the temperature limit that the platform can be baked to.

        Returns:
            temperature in Kelvin.
        """
        _logger.info("Getting max platform bakeout temperature for %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTemperatureLimit"))

    @rpc_method
    def set_platform_bakeout_temperature(self, temp: float) -> None:
        """Set the platform bakeout temperature.

        Parameters:
            temp: temperature to set in Kelvin.
        """
        _logger.info("Setting platform bakeout temperature for %s", self._name)
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTemperature", temp)

    @rpc_method
    def get_platform_bakeout_temperature(self) -> float:
        """Get the platform bakeout temperature.

        Returns:
            temperature in Kelvin.
        """
        _logger.info("Getting platform bakeout temperature for %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTemperature"))

    @rpc_method
    def set_platform_bakeout_time(self, time: float) -> None:
        """Set the platform bakeout time.

        Parameters:
            time: time to set in seconds.
        """
        _logger.info("Setting platform bakeout time for %s", self._name)
        self._set_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTime", time)

    @rpc_method
    def get_platform_bakeout_time(self) -> float:
        """Get the platform bakeout time.

        Returns:
            time in seconds.
        """
        _logger.info("Getting platform bakeout time for %s", self._name)
        return float(self._get_property(self.CONTROLLER_SUBSYSTEM_STR, "platformBakeoutTime"))

    @rpc_method
    def is_cryocooler_running(self) -> bool:
        """Check if the cryocooler is running.

        Returns:
            True if the cryocooler is running, else False.
        """
        _logger.info("Checking if cryocooler is running for %s", self._name)
        return bool(self._get_property(self.CRYOCOOLER_SUBSYSTEM_STR, "cryocoolerRunning"))

    @rpc_method
    def is_cryocooler_connected(self) -> bool:
        """Check if the cryocooler is connected and communicating properly.

        Returns:
            True if the cryocooler is connected and communicating properly, else False.
        """
        _logger.info("Checking if cryocooler is connected for %s", self._name)
        return bool(self._get_property(self.CRYOCOOLER_SUBSYSTEM_STR, "deviceConnected"))

    @rpc_method
    def get_sample_thermometer_properties(self) -> Montana_CryostationRest_Thermometer_Properties:
        """Get the properties of the platform thermometer, on which the sample is mounted.

        Returns:
            Dataclass with the properties.
        """
        _logger.info("Getting thermometer properties for sample for %s", self._name)
        return self._get_thermometer_properties(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR)

    @rpc_method
    def get_cryooptic_thermometer_properties(self) -> Montana_CryostationRest_Thermometer_Properties:
        """Get the cryo-optic thermometer properties.

        Returns:
            Dataclass with the properties.
        """
        _logger.debug("Getting cryo-optic thermometer properties for %s", self._name)
        return self._get_thermometer_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR)

    @rpc_method
    def get_stage1_thermometer_properties(self) -> Montana_CryostationRest_Thermometer_Properties:
        """Get the stage 1 thermometer properties.

        Returns:
            Dataclass with the properties.
        """
        _logger.debug("Getting stage 1 thermometer properties for %s", self._name)
        return self._get_thermometer_properties(self.COOLER_TEMP_CONTROLLER_SUBSYSTEM_STR + "/stage1")

    @rpc_method
    def get_stage2_thermometer_properties(self) -> Montana_CryostationRest_Thermometer_Properties:
        """Get the stage 2 thermometer properties.

        Returns:
            Dataclass with the properties.
        """
        _logger.debug("Getting stage 2 thermometer properties for %s", self._name)
        return self._get_thermometer_properties(self.COOLER_TEMP_CONTROLLER_SUBSYSTEM_STR + "/stage2")

    @rpc_method
    def get_platform_heater_properties(self) -> Montana_CryostationRest_Heater_Properties:
        """Get the platform heater properties.

        Returns:
            Dataclass with the properties.
        """
        _logger.debug("Getting platform heater properties for %s", self._name)
        return self._get_heater_properties(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR)

    @rpc_method
    def get_cryooptic_heater_properties(self) -> Montana_CryostationRest_Heater_Properties:
        """Get the cryo-optic heater properties.

        Returns:
            Dataclass with the properties.
        """
        _logger.debug("Getting cryo-optic heater properties for %s", self._name)
        return self._get_heater_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR)
