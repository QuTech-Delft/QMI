"""
Instrument driver for Thorlabs TC200 temperature controller.
"""

from enum import Enum
import logging
from typing import Any, NamedTuple, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport


# Logger for this module
_logger = logging.getLogger(__name__)


# Default timeout for command responses
TIMEOUT = 1


# Various limits
TMIN = 20.0
TMAX = 200.0
TLIMIT_MIN = 20.0
TLIMIT_MAX = 205.0
PLIMIT_MIN = 0.1
PLIMIT_MAX = 18.0
PGAIN_MIN = 1
PGAIN_MAX = 250
IGAIN_MIN = 0
IGAIN_MAX = 250
DGAIN_MIN = 0
DGAIN_MAX = 250


# Error responses
CMD_ERROR = "CMD_NOT_DEFINED"
ARG_RANGE_ERROR = "CMD_ARG_RANGE_ERR"


# Bitmasks for sensor bits
MASK_OUTPUT_STATE   = 0x01
MASK_MODE           = 0x02
MASK_SENSOR_TYPE    = 0x0C
MASK_DISPLAY_UNIT   = 0x30
MASK_ALARM          = 0x40
MASK_CYCLE_STATE    = 0x80


class _Command(Enum):
    """Commands."""
    TOGGLE_ENABLE = "ens"
    SET_TEMPERATURE = "tset"
    PGAIN = "pgain"
    IGAIN = "igain"
    DGAIN = "dgain"
    MAX_POWER = "pmax"  # user manual incorrectly uses PMAX
    MAX_TEMPERATURE = "tmax"  # user manual incorrectly uses TMAX
    TUNE_OFFSET = "tune"


class _Query(Enum):
    """Queries."""
    SETPOINT_TEMPERATURE = "tset?"
    ACTUAL_TEMPERATURE = "tact?"
    STATUS = "stat?"
    PID_GAINS = "pid?"
    MAX_POWER = "pmax?"  # user manual incorrectly uses PMAX?
    MAX_TEMPERATURE = "tmax?"  # user manual incorrectly uses TMAX?
    TUNED = "tune?"
    IDENT = "id?"


class OutputState(Enum):
    """Output state (enabled/disabled)."""
    DISABLED = 0x00
    ENABLED = 0x01


class Mode(Enum):
    """Control mode (constant temperature/cycling)."""
    NORMAL = 0x00
    CYCLE = 0x02


class SensorType(Enum):
    """Sensor type enumeration."""
    TH10K = 0x00
    PTC100 = 0x04
    PTC1000 = 0x08


class DisplayUnit(Enum):
    """Front panel display units."""
    KELVIN = 0x00
    CELSIUS = 0x10
    FAHRENHEIT = 0x20


class SensorAlarmState(Enum):
    """Sensor alarm state."""
    NO_ALARM = 0x00
    ALARM = 0x40


class CycleState(Enum):
    """Cycle state."""
    NOT_PAUSED = 0x00
    PAUSED = 0x80


class Tc200Status(NamedTuple):
    """TC 200 status.

    Attributes:
        output_state:   Output state (enabled/disabled).
        mode:           Output mode (normal/cycle).
        sensor_type:    Sensor type.
        unit:           Display unit (C/F/K).
        alarm:          Sensor alarm state (alarm/no alarm).
        cycle_state:    Cycle state (paused/not paused).
    """
    output_state: OutputState
    mode: Mode
    sensor_type: SensorType
    unit: DisplayUnit
    alarm: SensorAlarmState
    cycle_state: CycleState


class Thorlabs_TC200(QMI_Instrument):
    """Instrument driver for the Thorlabs TC200 temperature controller."""

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        A subset of the commands and queries of the TC200 is implmented. Specifically, configuring the temperature
        (typically done only once) and cycling is not implemented.

        The device uses an FTDI USB-to-serial interface at 115200 baud (8 data bits, no parity, 1 stop bit, no flow
        control). When connected directly to the device, use `serial:<device>:baudrate=115200` as transport
        specification.

        Parameters:
            context:    QMI Context.
            name:       Identifier for the instrument in the QMI context.
            transport:  Transport specification string.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200})

    def _send_command(self, command: _Command, argument: Any = None) -> str:
        self._check_is_open()

        if argument is None:
            command_string = f"{command.value}\r"
        else:
            command_string = f"{command.value}={argument}\r"

        _logger.debug("TC200 command: %s", command_string.strip())
        self._transport.write(command_string.encode("utf-8"))
        response = self._receive_response()
        if CMD_ERROR in response:
            raise QMI_InstrumentException("Command not accepted {}".format(command_string))

        return response

    def _send_query(self, query: _Query) -> str:
        self._check_is_open()

        query_string = f"{query.value}\r"

        _logger.debug("TC200 query: %s", query_string.strip())
        self._transport.write(query_string.encode("utf-8"))
        response = self._receive_response()
        if CMD_ERROR in response:
            raise QMI_InstrumentException("Query not accepted {}".format(query_string))

        return response

    def _receive_response(self) -> str:
        # The device echoes the command, followed by carriage return ('\r'), the actual response, another carriage
        # return and then a "prompt" ("> "). All responses are a single line of text, except the "config?" query, which
        # spans multiple lines separated by carriage returns. (Due to the use of carriage returns, miniterms on a Unix
        # environment do not work well).
        try:
            response = self._transport.read_until(b"\r> ", timeout=TIMEOUT)
            parts = response.decode('ascii').split('\r')
        except UnicodeDecodeError as exc:
            raise QMI_InstrumentException("Invalid instrument response") from exc

        # parts[0] is the echoed command, parts[-1] is the new "prompt"; multiline responses are joined by '\n' (single
        # line responses become a normal string).
        response_string = '\n'.join(parts[1:-1])
        _logger.debug('TC200 response: %s', response_string.strip())
        return response_string

    def _get_status(self) -> Tc200Status:
        self._check_is_open()
        self._transport.write(b"stat?\r")

        # The status query returns a slightly different response than other queries: it returns the hexadecimal
        # representation of the status byte, without the '\r' that terminates other response strings. The hexadecimal
        # is printed without leading zero, so it can be either one or two characters.
        try:
            response = self._transport.read_until(b" > ", timeout=TIMEOUT)
            status_string = response.decode('ascii')[len("stat?\r"):-len(" > ")]  # expected: "stat?\r.. > "
            status_byte = int(status_string, base=16)
            status = Tc200Status(
                output_state=OutputState(status_byte & MASK_OUTPUT_STATE),
                mode=Mode(status_byte & MASK_MODE),
                sensor_type=SensorType(status_byte & MASK_SENSOR_TYPE),
                unit=DisplayUnit(status_byte & MASK_DISPLAY_UNIT),
                alarm=SensorAlarmState(status_byte & MASK_ALARM),
                cycle_state=CycleState(status_byte & MASK_CYCLE_STATE)
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise QMI_InstrumentException("Invalid status response") from exc

        return status

    def _set_gain(self, cmd: _Command, gain: int, min_limit: int, max_limit: int) -> None:
        gain = int(gain)
        if min_limit <= gain <= max_limit:
            gain_string = f"{gain:d}"
        else:
            raise QMI_UsageException(
                "Gain must be between {} and {} inclusive, got {}".format(min_limit, max_limit, gain)
            )

        response = self._send_command(cmd, gain_string)
        if ARG_RANGE_ERROR in response:
            raise QMI_InstrumentException("Gain value not accepted: {}".format(gain_string))

    @rpc_method
    def open(self) -> None:
        """Open the device interface."""
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the device interface."""
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Retrieve the device identification."""
        ident = self._send_query(_Query.IDENT)
        vendor, model, _, version = ident.split(' ')
        return QMI_InstrumentIdentification(vendor=vendor, model=model, serial="", version=version)

    @rpc_method
    def get_status(self) -> Tc200Status:
        """Retrieve and parse device status."""
        return self._get_status()

    @rpc_method
    def is_enabled(self) -> bool:
        """Determine if the heater output is enabled."""
        return self._get_status().output_state == OutputState.ENABLED

    @rpc_method
    def has_alarm(self) -> bool:
        """Determine if sensor alarm is set."""
        return self._get_status().alarm == SensorAlarmState.ALARM

    @rpc_method
    def is_tuned(self) -> bool:
        """Determine if the offset calibration has been performed."""
        response = self._send_query(_Query.TUNED)

        # When response = "0", it means no offset tuning has been performed. A nonzero response should give the offset
        # value (according to the user manual), but it is unclear what the units are.
        return int(response) > 0

    @rpc_method
    def enable(self) -> None:
        """Enable the heater output."""
        if self.has_alarm():
            raise QMI_InstrumentException("Heater cannot be enabled due to sensor alarm")

        if not self.is_enabled():
            self._send_command(_Command.TOGGLE_ENABLE)
        else:
            _logger.info("Ignored enable command: heater already enabled")

    @rpc_method
    def disable(self) -> None:
        """Disable the heater output."""
        if self.is_enabled():
            self._send_command(_Command.TOGGLE_ENABLE)
        else:
            _logger.info("Ignored disable command: heater already disabled")

    @rpc_method
    def set_temperature(self, setpoint: float) -> None:
        """Set the temperature.

        If `setpoint` exceeds the TMAX limit or 200.0 deg Celsius, whichever is lower, the setpoint will be refused by
        the device. Minimum temperature setting is 20.0 deg Celsius. Resolution is 0.1 deg.

        Parameters:
            setpoint:   temperature setpoint in degrees Celsius.
        """
        if TMIN <= setpoint <= TMAX:
            setpoint_string = f"{setpoint:.1f}"
        else:
            raise QMI_UsageException(
                "Temperature setpoint must be between {} and {} inclusive, got {}".format(TMIN, TMAX, setpoint)
            )

        response = self._send_command(_Command.SET_TEMPERATURE, setpoint_string)
        if ARG_RANGE_ERROR in response:
            raise QMI_InstrumentException("Setpoint not accepted: {}".format(setpoint_string))

    @rpc_method
    def get_temperature_setpoint(self) -> float:
        """Get the current temperature setpoint in degrees Celsius."""
        response = self._send_query(_Query.SETPOINT_TEMPERATURE)
        value = response.split()[0]  # response is "XX.X Celsius"
        return float(value)

    @rpc_method
    def get_temperature_actual(self) -> float:
        """Get the actual temperature in degrees Celsius."""
        response = self._send_query(_Query.ACTUAL_TEMPERATURE)
        value = response.split()[0]  # response is "XX.X C"
        return float(value)

    @rpc_method
    def set_temperature_limit(self, limit: float) -> None:
        """Set the upper temperature setpoint limit.

        Parameters:
            limit:  upper temperature limit in degrees Celsius.
        """
        if TLIMIT_MIN <= limit <= TLIMIT_MAX:
            limit_string = f"{limit:.1f}"
        else:
            raise QMI_UsageException(
                "Temperature limit must be between {} and {} inclusive, got {}".format(TLIMIT_MIN, TLIMIT_MAX, limit)
            )

        response = self._send_command(_Command.MAX_TEMPERATURE, limit_string)
        if ARG_RANGE_ERROR in response:
            raise QMI_InstrumentException("Limit value not accepted: {}".format(limit_string))

    @rpc_method
    def get_temperature_limit(self) -> float:
        """Get the upper temperature setpoint limit in degrees Celsius."""
        response = self._send_query(_Query.MAX_TEMPERATURE)
        return float(response)  # response is "XX.X"

    @rpc_method
    def set_power_limit(self, limit: float) -> None:
        """Set the upper power limit.

        Parameters:
            limit:  upper power limit in Watt.
        """
        if PLIMIT_MIN <= limit <= PLIMIT_MAX:
            limit_string = f"{limit:.1f}"
        else:
            raise QMI_UsageException(
                "Power limit must be between {} and {} inclusive, got {}".format(PLIMIT_MIN, PLIMIT_MAX, limit)
            )

        response = self._send_command(_Command.MAX_POWER, limit_string)
        if ARG_RANGE_ERROR in response:
            raise QMI_InstrumentException("Limit value not accepted: {}".format(limit_string))

    @rpc_method
    def get_power_limit(self) -> float:
        """Get the upper power limit in Watt."""
        response = self._send_query(_Query.MAX_POWER)
        return float(response)  # response is "XX.X"

    @rpc_method
    def set_pid_gains(self,
                      p_gain: Optional[int] = None,
                      i_gain: Optional[int] = None,
                      d_gain: Optional[int] = None
                     ) -> None:
        """Set P, I, D gains for the control loop.

        Parameters:
            p_gain:  proportional gain between 1 and 250 inclusive.
            i_gain:  integral gain between 0 and 250 inclusive.
            d_gain:  differential gain between 0 and 250 inclusive.
        """
        if p_gain is not None:
            self._set_gain(_Command.PGAIN, p_gain, PGAIN_MIN, PGAIN_MAX)

        if i_gain is not None:
            self._set_gain(_Command.IGAIN, i_gain, IGAIN_MIN, IGAIN_MAX)

        if d_gain is not None:
            self._set_gain(_Command.DGAIN, d_gain, DGAIN_MIN, DGAIN_MAX)

    @rpc_method
    def get_pid_gains(self) -> Tuple[int, int, int]:
        """Get P, I, D gains for the control loop."""
        response = self._send_query(_Query.PID_GAINS)
        p_gain, i_gain, d_gain = [int(x) for x in response.split()]  # response is X Y Z
        return p_gain, i_gain, d_gain

    @rpc_method
    def tune(self) -> None:
        """Tune the temperature offset.

        The device can automatically tune the temperature offset. This works best if the P-gain is set to a moderate
        value (around 100-125) and the I-gain and D-gain are both zero. Tuning should *only* be performed when the
        temperature has reached a steady state, otherwise the results are unpredictable (note that as a result you
        cannot just `detune()` immediately followed by `tune()`, you need to wait for stead state after the detune).

        The heater output must be enabled and the device must not be already tuned.

        Tuning takes some time and the temperature may overshoot the setpoint a bit, depending on he P-gain. Typical
        time scale is about a minute or more. The final temperature should be within 0.1 degree Celsius.

        The offset is stored in persistent memory and loaded automatically on device startup.
        """
        if not self.is_enabled():
            raise QMI_UsageException("Heater output must be enabled for tuning")

        if self.is_tuned():
            raise QMI_UsageException("Device is already tuned")

        self._send_command(_Command.TUNE_OFFSET)

    @rpc_method
    def detune(self) -> None:
        """Detune (remove) the temperature offset.

        Allow the temperature to settle before re-tuning!
        """
        if self.is_tuned():
            # Issuing a tune command when the device is already tuned results in a detune.
            self._send_command(_Command.TUNE_OFFSET)
        else:
            _logger.debug("Device offset is not tuned, ignoring request for detune")
