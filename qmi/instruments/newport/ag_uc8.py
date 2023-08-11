"""Instrument driver for the Newport Agilis AG-UC8 Piezo Stepper Controller."""

import enum
import logging
import re
import time
from typing import Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

# Global variable holding the logger for this module.
from qmi.core.transport import create_transport

_logger = logging.getLogger(__name__)


class AxisStatus(enum.IntEnum):
    """Axis status codes."""

    READY = 0
    STEPPING = 1
    JOGGING = 2
    MOVING_TO_LIMIT = 3


class Newport_AG_UC8(QMI_Instrument):
    """Instrument driver for the Newport AG-UC8 Piezo Stepper Controller."""

    _rpc_constants = ["ERROR_CODES", "SPEED_TABLE"]

    # Meaning of error codes returned by the device.
    ERROR_CODES = {
        0: "No error",
        -1: "Unknown command",
        -2: "Axis out of range",
        -3: "Wrong format for parameter",
        -4: "Parameter out of range",
        -5: "Not allowed in local mode",
        -6: "Not allowed in current state",
    }

    # Meaning of speed settings.
    SPEED_TABLE = {
        1: "5 steps/second at defined step amplitude",
        2: "100 steps/second at maximum step amplitude",
        3: "1700 steps/second at maximum step amplitude",
        4: "666 steps/second at defined step amplitude",
    }

    # By default, expect response to command within 1 second.
    RESPONSE_TIMEOUT = 1.0

    # Some commands (position measurement and absolute move) can take
    # up to 2 minutes to complete.
    SLOW_RESPONSE_TIMEOUT = 120.0

    # After a command which does not generate a response, a short
    # delay is needed before we can send the following command.
    COMMAND_DELAY = 0.005

    # Delay after changing channels.
    CHANNEL_SWITCH_DELAY = 0.02

    # After a reset command, a longer delay is needed before
    # we can send the following command.
    RESET_DELAY = 0.05

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver.

        The instrument is typically accessed via the USB serial port,
        e.g. "serial:/dev/ttyUSBn" or "serial:COM3".

        :argument name: Name for this instrument instance.
        :argument transport: QMI transport descriptor for command interface.
        """
        super().__init__(context, name)
        self._transport = create_transport(
            transport,
            default_attributes={
                "baudrate": 921600,
                "bytesize": 8,
                "parity": "N",
                "stopbits": 1,
            },
        )
        self._current_channel: Optional[int] = None

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()

        # Do not assume any specific channel is selected.
        self._current_channel = None
        # Set controller in remote mode (otherwise many commands don't work).
        self._write("MR")
        # Check error status.
        self._check_error("MR")

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        self._transport.close()
        super().close()

    def _write(self, cmd: str) -> None:
        """Send command to instrument and check instrument responds with "OK"."""
        self._check_is_open()

        # Send command, terminated with \r\n.
        rawcmd = cmd.encode("ascii") + b"\r\n"
        self._transport.write(rawcmd)

        # Sleep until command completed.
        time.sleep(self.COMMAND_DELAY)

    def _ask(self, cmd: str, timeout: float) -> str:
        """Send command to instrument and return response from instrument."""
        self._check_is_open()

        # Send command, terminated with \r\n.
        rawcmd = cmd.encode("ascii") + b"\r\n"
        self._transport.write(rawcmd)

        # Read response.
        resp = self._transport.read_until(message_terminator=b"\n", timeout=timeout)
        resp = resp.rstrip(b"\r\n")

        return resp.decode("ascii", errors="replace")

    def _get_attribute(self, cmd: str, timeout: float = RESPONSE_TIMEOUT) -> int:
        """Send the specified command to the device and expect an integer value as result.

        This function expects that the device answers with a single line,
        containing an echo of the command immediately followed by an integer value.

        :argument cmd: Command to send to the device.
        :return: Integer value returned by the device.
        :raises QMI_InstrumentException: If the device sends an unexpected answer.
        """
        resp = self._ask(cmd, timeout=timeout)
        basecmd = re.sub(r"[0-9?]+$", "", cmd, count=1)  # strip argument and '?' marker
        if resp.startswith(basecmd):
            try:
                return int(resp[len(basecmd):].strip())
            except ValueError:
                # Invalid numeric format.
                # Ignore error; it will be reported below.
                pass

        _logger.warning("Unexpected response to command %s: %r", cmd, resp)
        raise QMI_InstrumentException(f"Unexpected response to command {cmd}: '{resp}'")

    @rpc_method
    def get_last_error(self) -> int:
        """Send a TE command (get error of previous command) and return
        a numerical error code. This function is called automatically after each command sent
        to the device.

        Raises:
            QMI_InstrumentException: When a command results in error.

        Returns:
            error: Integer error code for previous command. Value 0 means no error (success).
                   See class attribute ERROR_CODES for the meaning of the codes.
        """
        return self._get_attribute("TE")

    def _check_error(self, cmd: str) -> None:
        """Check the error status of the motor controller.

        :argument cmd: Most recent command.
        :raises QMI_InstrumentException: If the controller returns an error code.
        """
        err = self.get_last_error()
        if err != 0:
            errstr = self.ERROR_CODES.get(err, "unknown")
            _logger.warning("Command %s failed with error %d (%s)", cmd, err, errstr)
            raise QMI_InstrumentException(
                f"Command {cmd} failed with error {err} ({errstr})"
            )

    def _get_axis_attribute(
        self, attr: str, axis: int, timeout: float = RESPONSE_TIMEOUT
    ) -> int:
        """Read the specified axis attribute and return an integer value.

        Parameters:
            attr: The axis attribute to be obtained.
            axis: The axis number. Must be 1 or 2.
            timeout: Timeout for instrument response.

        Raises:
            QMI_UsageException: If invalid axis index is given as input.

        Returns:
            The value of the queried attribute on selected axis.
        """
        if axis not in (1, 2):
            raise QMI_UsageException(f"Invalid axis index {axis}")
        return self._get_attribute(f"{axis}{attr}", timeout)

    def _set_axis_attribute(self, attr: str, axis: int, value: int) -> None:
        """Set the specified axis attribute.

        Parameters:
            attr: The axis attribute to be set.
            axis: The axis number. Must be 1 or 2.
            value: An integer value for the attribute.

        Raises:
            QMI_UsageException: If invalid axis index is given as input.
        """
        if axis not in (1, 2):
            raise QMI_UsageException(f"Invalid axis index {axis}")

        cmd = f"{axis}{attr}{value}"
        self._write(cmd)
        self._check_error(cmd)

    @rpc_method
    def reset(self) -> None:
        """Reset the motor controller. Re-enables remote mode afterwards"""
        _logger.info("[%s] reset", self._name)
        self._current_channel = None
        self._write("RS")
        # Sleep until reset completed.
        time.sleep(self.RESET_DELAY)
        # Switch controller to remote mode (many commands require remote mode).
        self._write("MR")
        # Check error status.
        self._check_error("MR")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._ask("VE", timeout=self.RESPONSE_TIMEOUT)
        words = resp.strip().split()
        if len(words) == 2:
            model = words[0]
            version = words[1]
        else:
            _logger.warning("Unexpected response to VE command: %r", resp)
            raise QMI_InstrumentException(
                f"Unexpected response to VE command: '{resp}'"
            )
        return QMI_InstrumentIdentification(
            vendor="Newport", model=model, serial=None, version=version
        )

    @rpc_method
    def select_channel(self, channel: int) -> None:
        """Select the specified channel.

        The selected channel is attached to the motor drive electronics.
        This function is called automatically by methods which have a
        "channel" parameter.

        Changing the channel is only allowed when the axis is not moving.

        Parameters:
            channel: The channel number. Must in range 1-4.

        Raises:
            QMI_UsageException: By invalid channel number input.
        """

        # Check channel index.
        if channel not in (1, 2, 3, 4):
            raise QMI_UsageException(f"Invalid channel index {channel}")

        # Select channel, unless the channel is already selected.
        if self._current_channel != channel:
            self._write(f"CC{channel}")
            self._check_error("CC")
            time.sleep(self.CHANNEL_SWITCH_DELAY)
            self._current_channel = channel

    @rpc_method
    def get_limit_status(self, channel: int) -> Tuple[bool, bool]:
        """Get the limit switch status for the specified channel.

        :argument channel: Channel index (range 1 .. 4).
        :raises: QMI_InstrumentException if invalid response is received.
        :return: Tuple (axis1_limit_active, axis2_limit_active).
        """
        self.select_channel(channel)
        value = self._get_attribute("PH")
        if value == 0:
            return (False, False)
        elif value == 1:
            return (True, False)
        elif value == 2:
            return (False, True)
        elif value == 3:
            return (True, True)
        raise QMI_InstrumentException(f"Invalid response to PH command: '{value}'")

    @rpc_method
    def get_step_delay(self, axis: int) -> int:
        """Get step delay.
        :argument axis: Axis index (1 .. 2).
        :return: Step delay in units of 10 us.
        """
        return self._get_axis_attribute("DL?", axis)

    @rpc_method
    def set_step_delay(self, axis: int, value: int) -> None:
        """Set step delay.

        :argument axis: Axis index (1 .. 2).
        :argument value: Step delay in units of 10 us (range 1 .. 200000).
        """
        self._set_axis_attribute("DL", axis, value)

    @rpc_method
    def get_step_amplitude(self, axis: int, direction: int) -> int:
        """Get step amplitude.

        :argument axis: Axis index (1 .. 2).
        :argument direction: Direction (0=positive, 1=negative).
        :raises: QMI_UsageException by invalid direction index number.
        :return: Step amplitude (1 .. 50).
        """
        if direction == 0:
            attr = "SU+?"
        elif direction == 1:
            attr = "SU-?"
        else:
            raise QMI_UsageException(f"Invalid direction index {direction}")
        return self._get_axis_attribute(attr, axis)

    @rpc_method
    def set_step_amplitude(self, axis: int, direction: int, value: int) -> None:
        """Set step amplitude.

        :argument axis: Axis index (1 .. 2).
        :argument direction: Step direction (0=positive, 1=negative).
        :argument value: New step amplitude (1 .. 50).
        :raises: QMI_UsageException by invalid direction index number.
        """
        if direction == 0:
            attr = "SU+"
        elif direction == 1:
            attr = "SU-"
        else:
            raise QMI_UsageException(f"Invalid direction index {direction}")
        self._set_axis_attribute(attr, axis, value)

    @rpc_method
    def get_step_count(self, axis: int) -> int:
        """Get accumulated number of steps since last reset of the step counter.

        :argument axis: Axis index (1 .. 2).
        :return: Number of steps (difference between positive and negative steps).
        """
        return self._get_axis_attribute("TP", axis)

    @rpc_method
    def clear_step_count(self, axis: int) -> None:
        """Reset the step counter to zero.

        :argument axis: Axis index (1 .. 2).
        :raises: QMI_UsageException by invalid axis index number.
        """
        if axis not in (1, 2):
            raise QMI_UsageException(f"Invalid axis index {axis}")
        cmd = f"{axis}ZP"
        self._write(cmd)
        self._check_error(cmd)

    @rpc_method
    def get_axis_status(self, axis: int) -> AxisStatus:
        """Get status of the axis.

        :argument axis: Axis index (1 .. 2).
        :return: Axis status.
        """
        value = self._get_axis_attribute("TS", axis)
        return AxisStatus(value)

    @rpc_method
    def jog(self, channel: int, axis: int, speed: int) -> None:
        """Start moving in specified direction at specified speed.

        :argument channel: Channel index (1 .. 4).
        :argument axis: Axis index (1 .. 2).
        :argument speed: Speed and direction.
            0 = stop moving.
            positive values 1 .. 4 = move in positive direction.
            negative values -1 .. -4 = move in negative direction.
            See Newport_AG_UC8.SPEED_TABLE for the speed levels.
        """
        self.select_channel(channel)
        self._set_axis_attribute("JA", axis, speed)

    @rpc_method
    def move_limit(self, channel: int, axis: int, speed: int) -> None:
        """Start moving to positive or negative limit.

        :argument channel: Channel index (1 .. 4).
        :argument axis: Axis index (1 .. 2).
        :argument speed: Speed and direction.
            0 = stop moving.
            positive values 1 .. 4 = move in positive direction.
            negative values -1 .. -4 = move in negative direction.
            See Newport_AG_UC8.SPEED_TABLE for the speed levels.
        """
        self.select_channel(channel)
        self._set_axis_attribute("MV", axis, speed)

    @rpc_method
    def measure_position(self, channel: int, axis: int) -> int:
        """Measure current position along the specified axis.

        This is a slow command which may take up to 2 minutes to finish.
        It moves the axis to both limits, then back to its (approximate)
        original position.

        :argument channel: Channel index (1 .. 4).
        :argument axis: Axis index (1 .. 2).
        :return: Position in range 0 .. 1000 representing the current
            position in units of 1/1000 of the total axis range.
        """
        self.select_channel(channel)
        return self._get_axis_attribute("MA", axis, timeout=self.SLOW_RESPONSE_TIMEOUT)

    @rpc_method
    def move_abs(self, channel: int, axis: int, position: int) -> int:
        """Move to absolute position.

        This is a slow command which may take up to 2 minutes to finish.
        It moves the axis to both limits, then to its destination position.

        :argument channel: Channel index (1 .. 4).
        :argument axis: Axis index (1 .. 2).
        :argument position: Target position in range 0 .. 1000, in units
            of 1/1000 of the total axis range.
        """
        self.select_channel(channel)
        return self._get_axis_attribute(
            f"PA{position}", axis, timeout=self.SLOW_RESPONSE_TIMEOUT
        )

    @rpc_method
    def move_rel(self, channel: int, axis: int, steps: int) -> None:
        """Start relative movement.

        :argument channel: Channel index (1 .. 4).
        :argument axis: Axis index (1 .. 2).
        :argument steps: Number of steps to move relative to the current position.
            Positive values move in positive direction;
            negative values move in negative direction.
        :raises: QMI_UsageException by input steps number out of range.
        """
        if abs(steps) > 2**31:
            raise QMI_UsageException(f"Number of steps out of range {steps}")
        self.select_channel(channel)
        self._set_axis_attribute("PR", axis, steps)

    @rpc_method
    def stop(self, axis: int) -> None:
        """Stop current movement.

        :argument axis: Axis index (1 .. 2).
        :raises: QMI_UsageException by invalid axis index number.
        """
        if axis not in (1, 2):
            raise QMI_UsageException(f"Invalid axis index {axis}")
        self._write(f"{axis}ST")
