"""Instrument driver for the PhysikInstrumente E-873 Servo Controller."""

import enum
import logging
import re
import time
from typing import List, Mapping, NamedTuple, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

from .gcs_error_codes import GCS_CONTROLLER_ERROR_CODES


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class ReferenceTarget(enum.Enum):
    """Target position of reference move."""
    REFERENCE_POINT = 0
    POSITIVE_LIMIT = 1
    NEGATIVE_LIMIT = -1


class ReferenceSignalMode(enum.Enum):
    """Type of reference signal/approach."""
    DIRECTION_SENSING = 0
    PULSE_SIGNAL = 1
    INDEX_PULSE_VIA_NEGATIVE_LIMIT = 2
    INDEX_PULSE_VIA_POSITIVE_LIMIT = 3


# Named tuple returned by get_stage_info() command.
StageInfo = NamedTuple('StageInfo', [
    ('type', str),
    ('serial_number', str),
    ('assembly_date', str),
    ('hw_version', str)
])

# Named tuple returned by get_system_status() command.
SystemStatus = NamedTuple('SystemStatus', [
    ('negative_limit_switch', bool),
    ('reference_point_switch', bool),
    ('positive_limit_switch', bool),
    ('digital_input', Tuple[bool, bool, bool, bool]),
    ('error_flag', bool),
    ('servo_mode', bool),
    ('in_motion', bool),
    ('on_target', bool)
])


class PI_E873(QMI_Instrument):
    """Instrument driver for the PhysikInstrumente E-873 Servo Controller."""

    _rpc_constants = ["ERROR_CODES"]

    # Error codes returned by instrument via ERR? query.
    ERROR_CODES = GCS_CONTROLLER_ERROR_CODES

    # Instrument should respond within 2 seconds.
    RESPONSE_TIMEOUT = 2.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver.

        :argument name: Name for this instrument instance.
        :argument transport: QMI transport descriptor for command interface.
        """
        super().__init__(context, name)
        self.axis_id = "1"
        self._transport = create_transport(transport)

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()
        # Clear the error register.
        self._ask("ERR?")
        # Check axis identifiers. There should be a single axis, and the axis ID should be "1".
        resp = self._ask("SAI?")
        axis_ids = [t.strip() for t in resp.split("\n")]
        if axis_ids != [self.axis_id]:
            raise QMI_InstrumentException("Unexpected axis identifiers {!r}".format(axis_ids))

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    def _write(self, cmd: str) -> None:
        """Send command to instrument and check instrument responds with "OK"."""
        self._check_is_open()

        # There are a few special one-character commands which must not
        # be terminated. Other commands are terminated with \n.
        rawcmd = cmd.encode('ascii')
        if len(rawcmd) != 1:
            rawcmd += b"\n"

        # Send command.
        self._transport.write(rawcmd)

    def _ask(self, cmd: str) -> str:
        """Send command to instrument and return response from instrument."""
        self._check_is_open()

        # Discard pending data received from the controller.
        # Normally there should not be any pending data. However if a
        # previous query timed out, the belated response to the previous
        # query may now be sitting in the receive buffer. In that case we
        # have to discard it, otherwise we will be forever out of sync
        # with the controller.
        self._transport.discard_read()

        # There are a few special one-character commands which must not
        # be terminated. Other commands are terminated with \n.
        rawcmd = cmd.encode('ascii')
        if len(rawcmd) != 1:
            rawcmd += b"\n"

        # Send command.
        self._transport.write(rawcmd)

        # Read response.
        # NOTE: The instrument can send a multi-line responses. In that case
        # every line except the last line ends with a space character.
        resp = bytearray()
        lines = []  # type: List[bytes]
        while True:
            line = self._transport.read_until(message_terminator=b"\n",
                                              timeout=self.RESPONSE_TIMEOUT)
            if not line and not resp:
                raise QMI_TimeoutException("No response to command {!r}".format(cmd))
            if not line.endswith(b"\n"):
                raise QMI_InstrumentException("Got partial response to command {!r}: {!r}".format(cmd, line))
            line = line.rstrip(b"\r\n")
            if line.endswith(b" "):
                # Multi-line response, to be continued.
                resp.extend(line[:-1])
                resp.extend(b"\n")
            else:
                # This was the last line of the response.
                resp.extend(line)
                break

        return resp.decode('ascii', errors='replace')

    @staticmethod
    def _parse_response_item(resp: str, cmd: str, key: str) -> str:
        """Extract value part from a single-line "key=value" response from the instrument."""
        lines = resp.splitlines()
        if len(lines) != 1:
            raise QMI_InstrumentException(
                "Expecting single line response to command {!r} but got {!r}".format(cmd, resp))
        if not resp.startswith(key + "="):
            raise QMI_InstrumentException(
                "Expecting response with key {!r} to command {!r} but got {!r}".format(key, cmd, resp))
        return resp[len(key) + 1:]

    @staticmethod
    def _parse_int(resp: str, cmd: str, key: str = "") -> int:
        """Parse integer response from instrument.

        In some cases, the instrument response is formatted as "key=value".
        This function will parse that format if the expected key is specified.

        :argument resp: Response string from instrument.
        :argument cmd: Command string (for error messages).
        :argument key: Optional expected key for responses in key=value format.
        :return: Integer value.
        :raises QMI_InstrumentException: In case of unexpected response format.
        """
        if key:
            # Extract value part from "key=value" response.
            resp = PI_E873._parse_response_item(resp, cmd, key)
        try:
            return int(resp, 0)  # must also support hexadecimal format
        except ValueError:
            raise QMI_InstrumentException("Expecting integer response to command {!r} but got {!r}".format(cmd, resp))

    @staticmethod
    def _parse_float(resp: str, cmd: str, key: str = "") -> float:
        """Parse floating point response from instrument.

        :argument resp: Response string from instrument.
        :argument cmd: Command string (for error messages).
        :argument key: Optional expected key for responses in key=value format.
        :return: Floating point value.
        :raises QMI_InstrumentException: In case of unexpected response format.
        """
        if key:
            # Extract value part from "key=value" response.
            resp = PI_E873._parse_response_item(resp, cmd, key)
        try:
            return float(resp)
        except ValueError:
            raise QMI_InstrumentException("Expecting integer response to command {!r} but got {!r}".format(cmd, resp))

    def _check_error(self, expect_stop: bool = False) -> None:
        """Read error code from the instrument and raise exception in case of error."""
        cmd = "ERR?"
        resp = self._ask(cmd)
        err = self._parse_int(resp, cmd)
        # Ignore STOP error following a STP or HLT command.
        if err != 0 and ((not expect_stop) or err != 10):
            err_str = self.ERROR_CODES.get(err, "unknown")
            raise QMI_InstrumentException("Instrument reports error {} ({})".format(err, err_str))

    def _get_float_param(self, item: str, param: int) -> float:
        """Read floating point parameter from controller."""
        key = "{} 0X{:X}".format(item, param)
        cmd = "SPA? {}".format(key)
        resp = self._ask(cmd)
        return self._parse_float(resp, cmd, key=key)

    def _get_char_param(self, item: str, param: int) -> str:
        """Read string parameter from controller."""
        key = "{} 0X{:X}".format(item, param)
        cmd = "SPA? {}".format(key)
        resp = self._ask(cmd)
        return self._parse_response_item(resp, cmd, key=key)

    @rpc_method
    def reset(self) -> None:
        """Reboot the instrument, returning (most) settings to their defaults."""
        _logger.info("[%s] reboot", self._name)
        self._write("RBT")
        # Delay until controller is ready to handle new commands.
        # If a new command is sent too quickly, the controller may stop responding.
        time.sleep(1.0)
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        cmd = "*IDN?"
        resp = self._ask(cmd)
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to {!r}, got {!r}".format(cmd, resp))
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def get_stage_info(self) -> StageInfo:
        """Read information about the connected motor stage."""
        stage_type = self._get_char_param(self.axis_id, 0x0f000100)
        stage_serial = self._get_char_param(self.axis_id, 0x0f000200)
        stage_date = self._get_char_param(self.axis_id, 0x0f000300)
        stage_version = self._get_char_param(self.axis_id, 0x0f000400)
        return StageInfo(type=stage_type,
                         serial_number=stage_serial,
                         assembly_date=stage_date,
                         hw_version=stage_version)

    @rpc_method
    def get_error(self) -> int:
        """Return last error code and clear error register.

        Note most commands functions in this driver will automatically check
        the error register after sending the command.

        :return: Error core, or 0 if no error occurred since last command.
        """
        cmd = "ERR?"
        resp = self._ask(cmd)
        return self._parse_int(resp, cmd)

    @rpc_method
    def get_system_status(self) -> SystemStatus:
        """Request system status information.

        :return: 16-bit status code
        """
        cmd = "\x04"  # shortcut for "SRG?"
        resp = self._ask(cmd)
        w = self._parse_int(resp, cmd)
        # Decode status word.
        return SystemStatus(negative_limit_switch=((w & 1) != 0),
                            reference_point_switch=((w & 2) != 0),
                            positive_limit_switch=((w & 4) != 0),
                            digital_input=(((w & 0x10) != 0),
                                           ((w & 0x20) != 0),
                                           ((w & 0x40) != 0),
                                           ((w & 0x80) != 0)),
                            error_flag=((w & 0x100) != 0),
                            servo_mode=((w & 0x1000) != 0),
                            in_motion=((w & 0x2000) != 0),
                            on_target=((w & 0x8000) != 0))

    @rpc_method
    def stop_all(self) -> None:
        """Stop motion abruptly and stop macro execution."""
        _logger.debug("[%s] stop all axes", self._name)
        cmd = "\x18"  # shortcut for "STP"
        self._write(cmd)
        self._check_error(expect_stop=True)

    @rpc_method
    def stop_smooth(self) -> None:
        """Stop motion smoothly (taking deceleration into account)."""
        _logger.debug("[%s] halt axis", self._name)
        self._write("HLT")
        self._check_error(expect_stop=True)

    @rpc_method
    def get_physical_unit(self) -> str:
        """Return physical unit used for axis positions."""
        return self._get_char_param(self.axis_id, 0x07000601)

    @rpc_method
    def get_position_range(self) -> Tuple[float, float]:
        """Return range of commandable positions.

        :return: Range as tuple (min_pos, max_pos) in physical units.
        """
        cmd = "TMN? {}".format(self.axis_id)
        resp = self._ask(cmd)
        pmin = self._parse_float(resp, cmd, key=self.axis_id)
        cmd = "TMX? {}".format(self.axis_id)
        resp = self._ask(cmd)
        pmax = self._parse_float(resp, cmd, key=self.axis_id)
        return (pmin, pmax)

    @rpc_method
    def get_max_position_error(self) -> float:
        """Return the maximum allowed position error before the controller stops."""
        return self._get_float_param(self.axis_id, 0x8)

    @rpc_method
    def get_max_velocity(self) -> float:
        """Return the maximum closed-loop velocity in phys_unit/second."""
        return self._get_float_param(self.axis_id, 0xa)

    @rpc_method
    def get_max_acceleration(self) -> float:
        """Return the maximum closed-loop acceleration in phys_unit/second/second."""
        return self._get_float_param(self.axis_id, 0x4a)

    @rpc_method
    def get_max_deceleration(self) -> float:
        """Return the maximum closed-loop deceleration in phys_unit/second/second."""
        return self._get_float_param(self.axis_id, 0x4b)

    @rpc_method
    def get_reference_signal_mode(self) -> ReferenceSignalMode:
        """Return the method used by the motor controller to find the reference point."""
        v = self._get_float_param(self.axis_id, 0x70)
        return ReferenceSignalMode(int(v))

    @rpc_method
    def get_reference_velocity(self) -> float:
        """Return the velocity used for reference moves."""
        return self._get_float_param(self.axis_id, 0x50)

    @rpc_method
    def set_acceleration(self, accel: float) -> None:
        """Set acceleration for closed-loop motion.

        :argument accel: Acceleration in phys_unit/second/second.
        """
        _logger.debug("[%s] set acceleration %f", self._name, accel)
        self._write("ACC {} {:.8f}".format(self.axis_id, accel))
        self._check_error()

    @rpc_method
    def get_acceleration(self) -> float:
        """Get acceleration for closed-loop motion.

        :return: Acceleration in phys_unit/second/second.
        """
        cmd = "ACC? {}".format(self.axis_id)
        resp = self._ask(cmd)
        return self._parse_float(resp, cmd, key=self.axis_id)

    @rpc_method
    def set_deceleration(self, decel: float) -> None:
        """Set deceleration for closed-loop motion.

        :argument decel: Deceleration in phys_unit/second/second.
        """
        _logger.debug("[%s] set deceleration %f", self._name, decel)
        self._write("DEC {} {:.8f}".format(self.axis_id, decel))
        self._check_error()

    @rpc_method
    def get_deceleration(self) -> float:
        """Get deceleration for closed-loop motion.

        :return: Deceleration in phys_unit/second/second.
        """
        cmd = "DEC? {}".format(self.axis_id)
        resp = self._ask(cmd)
        return self._parse_float(resp, cmd, key=self.axis_id)

    @rpc_method
    def set_velocity(self, velocity: float) -> None:
        """Set velocity for closed-loop motion.

        :argument velocity: Velocity is phys_unit/second.
        """
        _logger.debug("[%s] set velocity %f", self._name, velocity)
        if velocity < 0:
            raise QMI_InstrumentException("Invalid velocity {}".format(velocity))
        self._write("VEL {} {:.8f}".format(self.axis_id, velocity))
        self._check_error()

    @rpc_method
    def get_velocity(self) -> float:
        """Get velocity for closed-loop motion.

        :return: Velocity in phys_unit/second.
        """
        cmd = "VEL? {}".format(self.axis_id)
        resp = self._ask(cmd)
        return self._parse_float(resp, cmd, key=self.axis_id)

    @rpc_method
    def set_servo_mode(self, enable: bool) -> None:
        """Enable or disable closed-loop servo operation.

        Servo mode must be enabled for reference moves and for closed-loop positioning.
        """
        _logger.debug("[%s] set servo mode %d", self._name, enable)
        state = 1 if enable else 0
        self._write("SVO {} {}".format(self.axis_id, state))
        self._check_error()

    @rpc_method
    def get_servo_mode(self) -> bool:
        """Return True if closed-loop servo mode is active."""
        cmd = "SVO? {}".format(self.axis_id)
        resp = self._ask(cmd)
        v = self._parse_int(resp, cmd, key=self.axis_id)
        return v == 1

    @rpc_method
    def set_reference_definition_mode(self, force_reference: bool) -> None:
        """Set reference point definition mode.

        :argument force_reference: True if a reference move is required for
            closed-loop operation; False if relative moves are allowed on
            an unreferenced axis.
        """
        _logger.debug("[%s] set reference definition mode %d", self._name, force_reference)
        mode = "1" if force_reference else "0"
        self._write("RON {} {}".format(self.axis_id, mode))
        self._check_error()

    @rpc_method
    def get_reference_definition_mode(self) -> bool:
        """Return reference point definition mode.

        :return: True if a reference move is required for closed-loop operation;
            False if relative moves are allowed on an unreferenced axis.
        """
        cmd = "RON? {}".format(self.axis_id)
        resp = self._ask(cmd)
        v = self._parse_int(resp, cmd, key=self.axis_id)
        return v == 1

    @rpc_method
    def reference_move(self,
                       target: ReferenceTarget = ReferenceTarget.REFERENCE_POINT) -> None:
        """Start a reference move to a well-defined position.

        When the axis reaches the target position, the absolute position
        of the axis is reset to the known position of the target.
        From that moment on, the axis is referenced and absolute closed-loop
        motion is possible.

        Servo mode must be enabled before calling this function.
        See set_servo_mode().

        Motion of the axis may continue after this function returns.
        Call get_system_status() to determine when motion is complete.
        Call stop_smooth() to abort the reference move.

        :argument target: Target of reference move.
            REFERENCE_POINT means move to the positive or negative axis
            limit (depending on stage parameters), then move back to the
            reference point.
            POSITIVE_LIMIT means move to the positive axis limit.
            NEGATIVE_LIMIT means move to the negative axis limit.
        """
        _logger.debug("[%s] start reference move", self._name)
        if target == ReferenceTarget.POSITIVE_LIMIT:
            self._write("FPL")
        elif target == ReferenceTarget.NEGATIVE_LIMIT:
            self._write("FNL")
        else:
            self._write("FRF")
        self._check_error()

    @rpc_method
    def get_reference_result(self) -> bool:
        """Return True if the axis is referenced (absolute position is known).

        :return: True if axis is referenced, False if axis is not referenced.
        """
        cmd = "FRF? {}".format(self.axis_id)
        resp = self._ask(cmd)
        v = self._parse_int(resp, cmd, key=self.axis_id)
        return v == 1

    @rpc_method
    def move_absolute(self, position: float) -> None:
        """Start closed-loop motion to absolute position.

        The axis must be referenced before absolute motion is possible.
        See reference_move().

        Motion of the axis may continue after this function returns.
        Call get_system_status() to determine when motion is complete.
        Call stop_smooth() to abort the reference move.

        :argument position: Target position in physical units.
        """
        _logger.debug("[%s] absolute move to %f", self._name, position)
        self._write("MOV {} {:.8f}".format(self.axis_id, position))
        self._check_error()

    @rpc_method
    def move_relative(self, displacement: float) -> None:
        """Start closed-loop motion to a target relative to the current position.

        Before calling this function, servo mode must be enabled and either
        the axis must be referenced or using an unreferenced axis must be
        allowed. See set_reference_definition_mode().

        Motion of the axis may continue after this function returns.
        Call get_system_status() to determine when motion is complete.
        Call stop_smooth() to abort the reference move.

        :argument displacement: Displacement (in physical units) from current
            position to target.
        """
        _logger.debug("[%s] relative move by %f", self._name, displacement)
        self._write("MVR {} {:.8f}".format(self.axis_id, displacement))
        self._check_error()

    @rpc_method
    def get_target_position(self) -> float:
        """Get target position of axis.

        :return: Target position in physical units.
        """
        cmd = "MOV? {}".format(self.axis_id)
        resp = self._ask(cmd)
        return self._parse_float(resp, cmd, key=self.axis_id)

    @rpc_method
    def get_position(self) -> float:
        """Get current absolute position of axis.

        :return: Current position in physical units.
        """
        cmd = "POS? {}".format(self.axis_id)
        resp = self._ask(cmd)
        return self._parse_float(resp, cmd, key=self.axis_id)

    @rpc_method
    def wait_motion_complete(self, timeout: Optional[float] = None) -> bool:
        """Wait until the current motion ends.

        :argument timeout: Maximum time to wait in seconds, or None to wait indefinitely.
        :return: True if motion complete, False if timeout expired before motion complete.
        """
        _logger.debug("[%s] wait until motion complete", self._name)

        endtime = None  # type: Optional[float]
        if timeout is not None:
            endtime = time.monotonic() + timeout

        while True:
            status = self.get_system_status()
            if not status.in_motion:
                return True
            if endtime is not None:
                t = time.monotonic()
                if t >= endtime:
                    return False
            time.sleep(0.02)

    @rpc_method
    def set_trigger_inmotion(self, dig_out: int) -> None:
        """Set digital output to be active as the axis is in motion.

        :argument dig_out: Digital output line (range 1 to 4)
        """

        if dig_out not in (1, 2, 3, 4):
            raise QMI_InstrumentException("Invalid digital output line {}".format(dig_out))

        _logger.debug("[%s] set trigger InMotion dig_out=%d", self._name, dig_out)

        # Set axis 1.
        self._write("CTO {} 2 {}".format(dig_out, self.axis_id))

        # Set trigger mode InMotion.
        self._write("CTO {} 3 6".format(dig_out))
        self._check_error()

    @rpc_method
    def set_trigger_position_offset(self, dig_out: int, step: float, start: float, stop: float) -> None:
        """Set digital output to pulse at specified position intervals.

        The first pulse is triggered when the axis has reached the specified offset position.
        Subsequent pulses are triggered each time the axis position equals the sum of the
        last trigger position and the specified step size. Trigger output ends when the
        axis position exceeds the specified stop position.

        :argument dig_out: Digital output line (range 1 to 4).
        :argument step: Position increment (physical units) between output pulses.
            This parameter must be negative if the axis moves in negative direction.
        :argument start: Position (physical units) of first output pulse..
        :argument stop: Position (physical units) where the output pulse stops.
        """

        if dig_out not in (1, 2, 3, 4):
            raise QMI_InstrumentException("Invalid digital output line {}".format(dig_out))

        _logger.debug("[%s] set trigger Position+Offset dig_out=%d", self._name, dig_out)

        # Set axis 1.
        self._write("CTO {} 2 {}".format(dig_out, self.axis_id))

        # Set TriggerStep.
        self._write("CTO {} 1 {:.8f}".format(dig_out, step))

        # Set TriggerPosition.
        self._write("CTO {} 10 {:.8f}".format(dig_out, start))

        # Set StopThreshold.
        self._write("CTO {} 9 {:.8f}".format(dig_out, stop))

        # Set trigger mode Position+Offset
        self._write("CTO {} 3 7".format(dig_out))
        self._check_error()

    @rpc_method
    def set_trigger_output_state(self, dig_out: int, enable: bool) -> None:
        """Enable or disable trigger output on the specified digital output line."""
        if dig_out not in (1, 2, 3, 4):
            raise QMI_InstrumentException("Invalid digital output line {}".format(dig_out))
        _logger.debug("[%s] set trigger state dig_out=%d enable=%d", self._name, dig_out, enable)
        mode = 1 if enable else 0
        self._write("TRO {} {}".format(dig_out, mode))
        self._check_error()

    @rpc_method
    def get_trigger_output_state(self, dig_out: int) -> bool:
        """Return True if trigger output is enabled on the specified digital output line."""
        if dig_out not in (1, 2, 3, 4):
            raise QMI_InstrumentException("Invalid digital output line {}".format(dig_out))
        cmd = "TRO? {}".format(dig_out)
        resp = self._ask(cmd)
        v = self._parse_int(resp, cmd, key=str(dig_out))
        return v == 1

    @rpc_method
    def set_digital_output(self, dig_out: int, state: bool) -> None:
        """Switch the specified digital output line to the specified state.

        This command must not be used on digital lines for which
        the trigger output is enabled.

        :argument dig_out: Digital output line (range 1 to 4).
        :argument state: True to set line high, False to set line low.
        """
        if dig_out not in (1, 2, 3, 4):
            raise QMI_InstrumentException("Invalid digital output line {}".format(dig_out))
        _logger.debug("[%s] set digital output %d = %d", self._name, dig_out, state)
        v = 1 if state else 0
        self._write("DIO {} {}".format(dig_out, v))
        self._check_error()

    @rpc_method
    def get_digital_input(self, dig_in: int) -> bool:
        """Read the state of the specified digital input line.

        :argument dig_in: Digital input line (range 1 to 4).
        :return: True if the input signal is high, False if the signal is low.
        """
        if dig_in not in (1, 2, 3, 4):
            raise QMI_InstrumentException("Invalid digital input line {}".format(dig_in))
        cmd = "DIO? {}".format(dig_in)
        resp = self._ask(cmd)
        v = self._parse_int(resp, cmd, key=str(dig_in))
        return v == 1

    @rpc_method
    def define_macro(self, name: str, commands: List[str]) -> None:
        """Define a new macro.

        :argument name: Name of the new macro.
        :argument commands: List of command strings to put in the macro.
        """
        cmd = "MAC BEG {}".format(name)
        self._write(cmd)
        for cmd in commands:
            time.sleep(0.01)  # avoid overflowing the controller input buffer
            self._write(cmd)
        cmd = "MAC END"
        self._write(cmd)
        self._check_error()

    @rpc_method
    def delete_macro(self, name: str) -> None:
        """Delete the specified macro."""
        self._write("MAC DEL {}".format(name))
        self._check_error()

    @rpc_method
    def get_defined_macros(self) -> List[str]:
        """Return a list of names of all defined macros."""
        cmd = "MAC?"
        resp = self._ask(cmd)
        return resp.splitlines()

    @rpc_method
    def start_macro(self,
                    name: str,
                    arg1: Optional[str] = None,
                    arg2: Optional[str] = None,
                    repeat: int = 1) -> None:
        """Start the specified macro one or more times.

        This function returns immediately after starting the macro.
        While the macro executes, the controller can process other commands.
        Only one macro can run at a time.

        If any command executed by the macro causes an error,
        the error status will appear in the global error register.
        A subsequent direct command to the controller may then
        report the pending error which was caused by the macro.
        To avoid this, call get_error() after macro execution completes
        to reset the global error register.

        Call stop_all() to abort all running macros.

        :argument arg1: Optional argument to load into VAR 1.
        :argument arg2: Optional argument to load into VAR 2.
        :argument repeat: Number of executions of the macro (default 1).
        """
        if (arg1 is None) and (arg2 is not None):
            raise QMI_InstrumentException("Can not call macro without arg1 but with arg2")
        if repeat < 1:
            raise QMI_InstrumentException("Can not execute macro fewer than 1 times")
        args = ""
        if arg1 is not None:
            args += " " + arg1
        if arg2 is not None:
            args += " " + arg2
        if repeat == 1:
            cmd = "MAC START {}{}".format(name, args)
        else:
            cmd = "MAC NSTART {} {}{}".format(name, repeat, args)
        self._write(cmd)
        self._check_error()

    @rpc_method
    def get_running_macros(self) -> List[str]:
        """Return a list of names of currently running macros."""
        cmd = "RMC?"
        resp = self._ask(cmd)
        return resp.splitlines()

    @rpc_method
    def set_variable(self, name: str, value: Optional[str]) -> None:
        """Set the value of a global variable.

        :argument name: Name of the variable.
        :argument value: New value for the variable, or None to delete the variable.
        """
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9]{0,7}$", name):
            raise ValueError("Invalid variable name {!r}".format(name))
        if value is not None:
            cmd = "VAR {} {}".format(name, value)
        else:
            cmd = "VAR {}".format(name)
        self._write(cmd)
        self._check_error()

    @rpc_method
    def get_variable(self, name: str) -> str:
        """Get the value of a global variable.

        :argument name: Name of the variable.
        :return: Current value of the variable.
        """
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9]{0,7}$", name):
            raise ValueError("Invalid variable name {!r}".format(name))
        cmd = "VAR? {}".format(name)
        resp = self._ask(cmd)
        return self._parse_response_item(resp, cmd, key=name)

    @rpc_method
    def get_variables(self) -> Mapping[str, str]:
        """Get all global variables.

        :return: Dictionary of name, value pairs.
        """
        cmd = "VAR?"
        resp = self._ask(cmd)
        ret = {}
        for line in resp.splitlines():
            p = line.find("=")
            if p < 0:
                raise QMI_InstrumentException(
                    "Expecting response format key=value but got {!r}".format(line))
            ret[line[:p]] = line[p + 1:]
        return ret
