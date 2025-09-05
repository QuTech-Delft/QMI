"""Instrument driver for the Pololu maestro servo controller"""

import logging
from typing import Dict, Generator, List, Optional, Tuple
from time import sleep

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.core.exceptions import QMI_InstrumentException
import warnings

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Pololu_Maestro(QMI_Instrument):
    """Instrument driver for the Pololu Maestro servo controller."""

    # Baudrate of instrument.
    BAUDRATE = 9600

    # Instrument should respond within 2 seconds.
    RESPONSE_TIMEOUT = 2.0

    # Default number of channels.
    DEFAULT_NUM_CHANNELS = 6

    # Default minimum and maximum settable values.
    # These are determined by the bit lengths for the values (16 bits)
    DEFAULT_MIN_VALUE = 0
    DEFAULT_MAX_VALUE = 16383

    # Default minimum and maximum accleration.
    DEFAULT_MIN_ACCELERATION = 0
    DEFAULT_MAX_ACCELERATION = 255

    # Errors.
    ERRORS = {
        1: "Serial signal error: A hardware-level error that occurs when a byte’s stop bit is not detected at the\
            expected place. This can occur if you are communicating at a baud rate that differs from the Maestro’s\
            baud rate.",
        2: "Serial overrun error: A hardware-level error that occurs when the UART’s internal buffer fills up. This\
            should not occur during normal operation.",
        4: "Serial bugger full: A firmware-level error that occurs when the firmware’s buffer for bytes received on\
            the RX line is full and a byte from RX has been lost as a result. This error should not occur during normal\
            operation.",
        8: "Serial CRC error: This error occurs when the Maestro is running in CRC-enabled mode and the cyclic\
            redundancy check (CRC) byte at the end of the command packet does not match what the Maestro has\
            computed as that packet’s CRC. In such a case, the Maestro ignores the command packet and generates a\
            CRC error.",
        16: "Serial protocol error: This error occurs when the Maestro receives an incorrectly formatted or\
             nonsensical command packet. For example, if the command byte does not match a known command or an unfinished\
             command packet is interrupted by another command packet, this error occurs.",
        32: "Serial timeout: When the serial timeout is enabled, this error occurs whenever the timeout period has\
             elapsed without the Maestro receiving any valid serial commands. This timeout error can be used to make\
             the servos return to their home positions in the event that serial communication between the Maestro and its\
             controller is disrupted.",
        64: "Script stack error: This error occurs when a bug in the user script has caused the stack to overflow or\
             underflow. Any script command that modifies the stack has the potential to cause this error. The stack depth\
             is 32 on the Micro Maestro and 126 on the Mini Maestros.",
        128: "Script call stack error: This error occurs when a bug in the user script has caused the call stack to\
              overflow or underflow. An overflow can occur if there are too many levels of nested subroutines, or a subroutine\
              calls itself too many times. The call stack depth is 10 on the Micro Maestro and 126 on the Mini Maestros. An\
              underflow can occur when there is a return without a corresponding subroutine call. An underflow will occur if\
              you run a subroutine using the “Restart Script at Subroutine” serial command and the subroutine terminates with a\
              return command rather than a quit command or an infinite loop.",
        256: "Script program counter error: This error occurs when a bug in the user script has caused the program counter\
              (the address of the next instruction to be executed) to go out of bounds. This can happen if your program is not\
              terminated by a quit, return, or infinite loop."
    }

    def __init__(
            self, context: QMI_Context, name: str, transport: str, num_channels: int = DEFAULT_NUM_CHANNELS,
            channels_min_max_targets: Optional[Dict[int, Tuple[int, int]]] = None,
            channels_min_max_speeds: Optional[Dict[int, Tuple[int, int]]] = None,
            channels_min_max_accelerations: Optional[Dict[int, Tuple[int, int]]] = None) -> None:
        """Initialize driver.

        Parameters:
            context:                        The QMI context
            name:                           The name of the instrument instance
            transport:                      QMI transport descriptor to connect to the instrument.
            num_channels:                   Number of channels that can be controlled via the controller.
            channels_min_max_targets:       The minimum and maximum target values for each channel as dictionary, where the value is a tuple
                                            of the min and max.
            channels_min_max_speeds:        The minimum and maximum target values for each channel as dictionary, where the value is a tuple
                                            of the min and max.
            channels_min_max_accelerations: The minimum and maximum target values for each channel as dictionary, where the value is a tuple
                                            of the min and max.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={
                                           "baudrate": self.BAUDRATE})
        # This device number defaults to 0x0C (or 12 in decimal).
        device_nr = 0x0C
        # Command lead-in and device number are sent for each Pololu serial command.
        self._cmd_lead_in = chr(0xAA) + chr(device_nr)
        # Track the target value of each channel
        self._targets: List[int] = [0] * num_channels
        # Store the minimum and maximum target values of each channel
        self._min_target_values: List[int] = [
            self.DEFAULT_MIN_VALUE] * num_channels
        self._max_target_values: List[int] = [
            self.DEFAULT_MAX_VALUE] * num_channels

        channels_min_max_targets = channels_min_max_targets if channels_min_max_targets else {}
        channels_min_max_speeds = channels_min_max_speeds if channels_min_max_speeds else {}
        channels_min_max_accelerations = channels_min_max_accelerations if channels_min_max_accelerations else {}
        # Overwrite channels that have a provided min/max target value
        for c in channels_min_max_targets.keys():
            self._min_target_values[c] = channels_min_max_targets[c][0]
            self._max_target_values[c] = channels_min_max_targets[c][1]
        # Store the minimum and maximum speeds of each channel
        self._min_speeds: List[int] = [
            self.DEFAULT_MIN_VALUE] * num_channels
        self._max_speeds: List[int] = [
            self.DEFAULT_MAX_VALUE] * num_channels
        # Overwrite channels that have a provided min/max speed
        for c in channels_min_max_speeds.keys():
            self._min_speeds[c] = channels_min_max_speeds[c][0]
            self._max_speeds[c] = channels_min_max_speeds[c][1]
        # Store the minimum and maximum accelerations of each channel
        self._min_accelerations: List[int] = [
            self.DEFAULT_MIN_ACCELERATION] * num_channels
        self._max_accelerations: List[int] = [
            self.DEFAULT_MAX_ACCELERATION] * num_channels
        # Overwrite channels that have a provided min/max acceleration
        for c in channels_min_max_accelerations.keys():
            self._min_accelerations[c] = channels_min_max_accelerations[c][0]
            self._max_accelerations[c] = channels_min_max_accelerations[c][1]

        self._num_channels = num_channels

    @staticmethod
    def _compile_write_command(cmd: int, channel: int, value: int) -> str:
        """Compile the command into one command string. The input target value must be divided into
        the least significant and the most significant byte.

        Parameters:
            channel:    Channel number.
            value:      Value for the command.
        """
        lsb = value & 0x7F
        msb = (value >> 7) & 0x7F
        return chr(cmd) + chr(channel) + chr(lsb) + chr(msb)

    def _get_high_bits(self, num: int) -> Generator[int, None, None]:
        """Get the bits that are set high.

        Returns:
            Bits that are high.
        """
        while num:
            bit = num & (~num+1)
            yield bit
            num ^= bit

    def _get_errors(self) -> List[str]:
        """Get errors.

        Returns:
            List of errors.
        """
        self._transport.discard_read()  # Discard possible read buffer
        cmd = self._cmd_lead_in + chr(0x21)
        self._transport.write(bytes(cmd, "latin-1"))
        bin_err = self._transport.read(
            nbytes=2, timeout=self.RESPONSE_TIMEOUT)
        int_err = int.from_bytes(bin_err, "big")
        errors = []
        # loop over bits and log the errors
        for b in self._get_high_bits(int_err):
            errors.append(self.ERRORS[b])

        return errors

    def _write(self, cmd: str) -> None:
        """Send write command to instrument.

        Parameters:
            cmd: The command string to be written
        """
        cmd = self._cmd_lead_in + cmd
        self._transport.write(bytes(cmd, "latin-1"))
        # Sleep over the bits to be sent
        sleep(len(cmd) / self.BAUDRATE * 100)

        errs = self._get_errors()
        if errs:
            formatted_errs = '\n'.join(map(str, errs))
            raise QMI_InstrumentException(
                f"Pololu Maestro servo command {cmd} resulted in the following error(s).\n{formatted_errs}")

    def _ask(self, cmd: str) -> int:
        """Send ask command to instrument.

        Parameters:
            cmd: The command string to be written.

        Raises:
            QMI_InstrumentException if the servo command returns an error.

        Returns:
            The queried value.
        """
        cmd = self._cmd_lead_in + cmd
        self._transport.write(bytes(cmd, "latin-1"))
        # Sleep over the bits to be sent
        sleep(len(cmd) / self.BAUDRATE * 100)
        # Read back the response bits
        lsb = ord(self._transport.read(
            nbytes=1, timeout=self.RESPONSE_TIMEOUT))
        msb = ord(self._transport.read(
            nbytes=1, timeout=self.RESPONSE_TIMEOUT))

        errs = self._get_errors()
        if errs:
            formatted_errs = '\n'.join(map(str, errs))
            raise QMI_InstrumentException(
                f"Pololu Maestro servo command {cmd} resulted in the following error(s).\n{formatted_errs}")

        return (msb << 8) + lsb

    def _check_channel(self, channel) -> None:
        """Check the channel number.

        Raises:
            ValueError the controller does not support that channel.
        """
        if channel < 0 or channel >= self._num_channels:
            raise ValueError(
                f"Maestro Micro Servo Controller has channels 0 to {self._num_channels - 1}."
            )

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)
        self._transport.close()
        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        return QMI_InstrumentIdentification(
            vendor="Pololu", model="Maestro Micro Servo Controller", serial=None, version=None
        )

    @rpc_method
    def set_target(self, channel: int, value: int) -> None:
        """Set channel to a specified target value. The target value is of units 0.25us. For example, if you want to
        set the target to 1500 us, you need to give as input 6000:
        (1500×4 = 6000 = 01011101110000 in binary)
        Servo will begin moving based on speed and acceleration parameters previously set.
        This method will check against the maximum and minimum target value of the channel. If the value to be set is
        out of the min/max range, the method will set the target value to the min/max.

        Parameters:
            channel:    Channel number.
            value:      The target value in units of quarter microseconds.
        """
        self._check_is_open()
        self._check_channel(channel)

        target = value
        if target < self._min_target_values[channel]:
            target = self._min_target_values[channel]
            _logger.warning(
                "Target value for channel %i below minimum. Setting to %i", channel, target)
        elif self._max_target_values[channel] < target:
            target = self._max_target_values[channel]
            _logger.warning(
                "Target value for channel %i above maximum. Setting to %i", channel, target)

        cmd = self._compile_write_command(0x04, channel, target)
        self._write(cmd)
        self._targets[channel] = target

    @rpc_method
    def get_targets(self) -> List[int]:
        """Get the current targets for each channel.

        Returns:
            The target values for each channel.
        """
        return self._targets

    @rpc_method
    def get_position(self, channel: int) -> int:
        """Get the current position of the specified channel in quarter-microseconds.

        Parameters:
            channel: The channel number.

        Returns:
            The position in quarter-microsecond units.
        """
        self._check_is_open()
        self._check_channel(channel)

        cmd = chr(0x10) + chr(channel)
        return self._ask(cmd)

    @rpc_method
    def set_speed(self, channel: int, speed: int) -> None:
        """Set speed of channel. This option specifies the speed of the servo in units of
        0.25 us / 10 ms => speed * 1 us / 40 ms.

        Parameters:
            channel:    The channel number.
            speed:      The target speed.

        Raises:
            ValueError if speed is out of allowable range.
        """
        self._check_is_open()
        self._check_channel(channel)
        min_speed = self._min_speeds[channel]
        max_speed = self._max_speeds[channel]
        if not min_speed <= speed <= max_speed:
            err_msg = f"Set speed [{speed}] not in the allowed range [{min_speed}, {max_speed}]"
            raise ValueError(err_msg)

        cmd = self._compile_write_command(0x07, channel, speed)
        self._write(cmd)

    @rpc_method
    def set_acceleration(self, channel: int, acceleration: int) -> None:
        """Set acceleration of a channel. This option specifies the acceleration of the servo
        in units of 0.25 us / 10 ms / 80 ms => acceleration * 1 us / 3.2 ms .

        Parameters:
            channel:        The channel number.
            acceleration:   The target acceleration.

        Raises:
            ValueError if acceleration not within 0 to 255
        """
        self._check_is_open()
        self._check_channel(channel)
        min_acc = self._min_accelerations[channel]
        max_acc = self._max_accelerations[channel]
        if not min_acc <= acceleration <= max_acc:
            err_msg = f"Set acceleration [{acceleration}] not in the allowed range [{min_acc}, {max_acc}]"
            raise ValueError(err_msg)

        cmd = self._compile_write_command(0x09, channel, acceleration)
        self._write(cmd)

    @rpc_method
    def go_home(self):
        """Send all servos and outputs to their home values."""
        self._check_is_open()
        self._write(chr(0x22))

    @rpc_method
    def set_min_target(self, channel: int, value: int) -> None:
        """Set the minimum target value for a channel.

        Parameters:
            channel:    The channel number.
            value:      The new minimum target value.
        """
        if value < self.DEFAULT_MIN_VALUE or value > self._max_target_values[channel]:
            raise ValueError(
                f"Minimum value invalid, should be in range [{self.DEFAULT_MIN_VALUE},\
                    {self._max_target_values[channel]}")

        self._min_target_values[channel] = value

    @rpc_method
    def get_min_target(self, channel: int) -> int:
        """Get the minimum target value for a channel.

        Parameters:
            channel:    The channel number.
        """
        return self._min_target_values[channel]

    @rpc_method
    def set_max_target(self, channel: int, value: int) -> None:
        """Set the maximum target that can be set for a channel.

        Parameters:
            channel:    The channel number.
            value:      The new maximum target value.
        """
        if value <= self._min_target_values[channel] or value > self.DEFAULT_MAX_VALUE:
            raise ValueError(
                f"Maximum value invalid, should be in range [{self._min_target_values[channel] + 1},\
                    {self.DEFAULT_MAX_VALUE}]")

        self._max_target_values[channel] = value

    @rpc_method
    def get_max_target(self, channel: int) -> int:
        """Get the maximum target that can be set for a channel.

        Parameters:
            channel:    The channel number.
        """
        return self._max_target_values[channel]

    @rpc_method
    def set_max(self, channel: int, value: int) -> None:
        """Set the maximum target that can be set for a channel.

        Parameters:
            channel:    The channel number.
            value:      The new maximum target value.
        """
        warnings.warn(
            f"{self.set_max.__name__} has been deprecated. Please use {self.set_max_target.__name__}.",
            DeprecationWarning)
        self.set_max_target(channel, value)

    @rpc_method
    def set_min(self, channel: int, value: int) -> None:
        """Set the minimum target that can be set for a channel.

        Parameters:
            channel:    The channel number.
            value:      The new maximum target value.
        """
        warnings.warn(
            f"{self.set_min.__name__} has been deprecated. Please use {self.set_min_target.__name__}.",
            DeprecationWarning)
        self.set_min_target(channel, value)

    @rpc_method
    def set_target_value(self, channel: int, value: int) -> None:
        """Set channel to a specified target value. The target value is of units 0.25us. For example, if you want to
        set the target to 1500 us, you need to give as input 6000:
        (1500×4 = 6000 = 01011101110000 in binary)
        Servo will begin moving based on speed and acceleration parameters previously set.
        This method will check against the maximum and minimum target value of the channel. If the value to be set is
        out of the min/max range, the method will set the target value to the min/max.

        Parameters:
            channel:    Channel number.
            value:      The target value in units of quarter microseconds.
        """
        warnings.warn(
            f"{self.set_target_value.__name__} has been deprecated. Please use {self.set_target.__name__}.",
            DeprecationWarning)
        self.set_target(channel, value)

    @rpc_method
    def get_value(self, channel: int) -> int:
        """Get the current position of the specified channel in quarter-microseconds.

        Parameters:
            channel: The channel number.

        Returns:
            The position in quarter-microsecond.
        """
        warnings.warn(
            f"{self.get_value.__name__} has been deprecated. Please use {self.get_position.__name__}.",
            DeprecationWarning)
        return self.get_position(channel)

    @rpc_method
    def move_up(self, channel: int) -> None:
        """Move the servo to maximal value.

        Parameters:
            channel: The channel number.
        """
        warnings.warn(
            f"{self.move_up.__name__} has been deprecated. There is no replacement for this.",
            DeprecationWarning)

    @rpc_method
    def move_down(self, channel: int) -> None:
        """Move the servo to minimal value.

        Parameters:
            channel: The channel number.
        """
        warnings.warn(
            f"{self.move_down.__name__} has been deprecated. There is no replacement for this.",
            DeprecationWarning)
