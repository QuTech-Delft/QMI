"""Instrument driver for using the Pololu Maestro to control servo motors (e.g. HiTEC HS-5485HB).
Written by Yanik Herrmann (y.s.herrmann@tudelft.nl).

This code is adapted from a similar project, written by Steven Jacobs and changed to work in Python3 and QMI.
The original code can be found in https://github.com/FRC4564/Maestro.
Be sure the Maestro is configured for "USB Dual Port" serial mode, which is not the default.
Configuration and test can be done by using the manufacturer's software: https://www.pololu.com/docs/0J40/3.a
Manual: https://www.pololu.com/docs/0J40. We assume default settings for the servo.

Tested with the Pololu Micro Maestro 6 Servo Controller.
"""

import logging
from typing import List
from time import sleep

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.core.exceptions import QMI_InstrumentException

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Pololu_Maestro(QMI_Instrument):
    """Instrument driver for the Pololu Maestro servo controller."""

    # Instrument should respond within 2 seconds.
    DEFAULT_BAUD_RATE = 9600
    RESPONSE_TIMEOUT = 2.0
    AVAILABLE_CHANNELS = 6
    DEFAULT_MAX_PULSE_WIDTH = 8000  # Default config is max 20ms pulse width, in 0.25 us steps.
    DEFAULT_SERVO_PERIOD = 0.020  # Default servo pulse period is 20ms.
    DEFAULT_MIN = 4000
    DEFAULT_MAX = 5500

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": self.DEFAULT_BAUD_RATE})
        # This device number defaults to 0x0C (or 12 in decimal).
        device_nr = 0x0C
        # Command lead-in and device number are sent for each Pololu serial command.
        self._cmd_lead_in = chr(0xAA) + chr(device_nr)
        # Track target value for each servo. The function is_moving() will
        # use the Target vs Current servo's value to determine if movement is occurring.
        # Up to 6 servos on a Maestro, (0-5). Targets start at 0 (no move).
        self.targets: List[int] = [0] * self.AVAILABLE_CHANNELS
        # Servo minimum and maximum targets can be restricted to protect components.
        # Min, Max and Center determined with the manufacturer software Pololu Maestro Control Center
        # for servo controller HiTEC HS-5485HB.
        self.minimums: List[int] = [self.DEFAULT_MIN] * self.AVAILABLE_CHANNELS
        self.maximums: List[int] = [self.DEFAULT_MAX] * self.AVAILABLE_CHANNELS

    @staticmethod
    def _command_compiler(cmd: int, channel: int, value: int) -> str:
        """Compiles the command into one command string. The input target value must be divided into
        the least significant and the most significant bits."""
        lsb = value & 0x7F  # 7 bits for least significant byte
        msb = (value >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd_str = chr(cmd) + chr(channel) + chr(lsb) + chr(msb)
        return cmd_str

    def _get_errors(self) -> bool:
        """Check if controller detected errors. Return true if errors are detected."""
        self._transport.discard_read()  # Discard possible read buffer
        cmd = self._cmd_lead_in + chr(0x21)  # or 0xA1 which returns answ[0] as 16
        self._transport.write(bytes(cmd, "latin-1"))
        answ = self._transport.read(nbytes=2, timeout=self.RESPONSE_TIMEOUT)
        if (answ[0] == 0) and (answ[1] == 0):  # answ[1] should be 16 but always returns 0... Why?
            return False
        else:
            _logger.error("Problem with Maestro Micro Servo Controller, error bits:%i,%i" % (answ[0], answ[1]))
            return True

    def _write(self, cmd: str) -> None:
        """Send command to instrument.

        Parameters:
            cmd: The command string to be written
        """
        cmd = self._cmd_lead_in + cmd
        # Send command.
        self._transport.write(bytes(cmd, "latin-1"))
        sleep(len(cmd) / self.DEFAULT_BAUD_RATE * 100)  # Sleep over the bits to be sent
        if self._get_errors():
            raise QMI_InstrumentException(f"Pololu Maestro servo command {cmd} resulted in error.")

    def _ask(self, cmd: str) -> int:
        """Send command to instrument.

        Parameters:
            cmd: The command string to be written

        Raises:
            QMI_InstrumentException if the servo command returns an error.

        Returns:
            The sum of the high and the low bit (8-bits).
        """
        cmd = self._cmd_lead_in + cmd
        if self._get_errors():
            raise QMI_InstrumentException(f"Pololu Maestro servo query {cmd} resulted in error.")

        # Send command.
        self._transport.write(bytes(cmd, "latin-1"))
        sleep(len(cmd) / self.DEFAULT_BAUD_RATE * 100)  # Sleep over the bits to be sent
        # Read back the response bits
        lsb = ord(self._transport.read(nbytes=1, timeout=self.RESPONSE_TIMEOUT))
        msb = ord(self._transport.read(nbytes=1, timeout=self.RESPONSE_TIMEOUT))

        if self._get_errors():
            raise QMI_InstrumentException(f"Pololu Maestro servo query {cmd} resulted in error.")

        return (msb << 8) + lsb

    def _check_channel(self, channel):
        """Internal function to check the channel number"""
        if channel < 0 or channel >= self.AVAILABLE_CHANNELS:
            raise ValueError(
                f"Maestro Micro Servo Controller has channels 0 to {self.AVAILABLE_CHANNELS - 1}."
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
    def set_target_value(self, channel: int, value: int) -> None:
        """Set channel to a specified target value. The target value is of units 0.25us. For example, if you want to set
        the target to 1500 µs, you need to give as input 6000:
        (1500×4 = 6000 = 01011101110000 in binary)
        Servo will begin moving based on Speed and Acceleration parameters previously set.
        
        Parameters:
            channel: Channel number.
            value: The target value in quarter microseconds.
        """
        self._check_is_open()
        self._check_channel(channel)
        
        # If Min/Max is defined and target is below/above force to Min/Max
        target = value
        if target < self.minimums[channel]:
            target = self.minimums[channel]
            _logger.warning("Target value for channel %i below minimum. Setting to %i", channel, target)
        elif self.maximums[channel] < target:
            target = self.maximums[channel]
            _logger.warning("Target value for channel %i above maximum. Setting to %i", channel, target)

        cmd = self._command_compiler(0x04, channel, target)
        self._write(cmd)
        self.targets[channel] = target

    @rpc_method
    def get_target_values(self) -> List[int]:
        """Return the current target values list."""
        return self.targets
        
    @rpc_method
    def get_value(self, channel: int) -> int:
        """Get the current value of the device on the specified channel in quarter-microseconds.

        Parameters:
            channel: The channel number.
            
        Returns:
            The current value bit.
        """
        self._check_is_open()
        self._check_channel(channel)

        cmd = chr(0x10) + chr(channel)
        return self._ask(cmd)

    @rpc_method
    def set_speed(self, channel: int, speed: int) -> None:
        """Set speed of channel in steps between 0 and 1000. This option specifies the speed of the servo in units of
        0.25 us / 10 ms => speed * 1 us / 40 ms.
        
        Parameters:
            channel: The channel number.
            speed: The target speed.

        Raises:
            ValueError if speed not in range 0-1000.
        """
        self._check_is_open()
        self._check_channel(channel)
        if not 0 <= speed <= 1000:
            _logger.error("Speed can only be set as an integer between 0 (unrestricted) and 1000.")
            raise ValueError("Speed can only be set as an integer between 0 (unrestricted) and 1000.")

        cmd = self._command_compiler(0x07, channel, speed)
        self._write(cmd)

    @rpc_method
    def set_acceleration(self, channel: int, acceleration: int) -> None:
        """Set acceleration of channel in steps between 0 and 255. This option specifies the acceleration of the servo
        in units of 0.25 us / 10 ms / 80 ms => acceleration * 1 us / 3.2 ms .

        Parameters:
            channel: The channel number.
            acceleration: The target acceleration.

        Raises:
            ValueError if acceleration not within 0 to 255
        """
        self._check_is_open()
        self._check_channel(channel)
        if not 0 <= acceleration < 256:
            _logger.error("Speed can only be set between 0 (unrestricted) and 255.")
            raise ValueError("Speed can only be set between 0 (unrestricted) and 255.")

        cmd = self._command_compiler(0x09, channel, acceleration)
        self._write(cmd)

    @rpc_method
    def go_home(self):
        """Send all servos and outputs to their home values."""
        self._check_is_open()
        self._write(chr(0x22))

    @rpc_method
    def move_up(self, channel: int) -> None:
        """Moves the servo to maximal value.

        Parameters:
            channel: The channel number.
        """
        self._check_is_open()
        self._check_channel(channel)
        self.set_target_value(channel, self.maximums[channel])

    @rpc_method
    def move_down(self, channel: int) -> None:
        """Moves the servo to minimal value.

        Parameters:
            channel: The channel number.
        """
        self._check_is_open()
        self._check_channel(channel)
        self.set_target_value(channel, self.minimums[channel])

    @rpc_method
    def is_moving(self, channel: int) -> bool:
        """This method checks if the servo is still moving.

        Return:
            True if servo is still moving, otherwise False.
        """
        cmd = chr(0x10) + chr(channel)  # This is a bit of repetition, but calling other RPC commands inside
        value_now = self._ask(cmd)  # RPC commands with high frequency can cause issues. Use internal calls.
        if not value_now == self.targets[channel]:
            # It could be that the target value is not reached due to a block. Check if the
            # current position changes over time. If yes, it is still moving.
            sleep(self.DEFAULT_SERVO_PERIOD)
            value_again = self._ask(cmd)
            if value_again != value_now:
                return True

        return False

    @rpc_method
    def set_min(self, channel: int, value: int) -> None:
        """Replace a minimum value for a channel.

        Parameters:
            channel: The channel number.
            value: The new minimum target value.
        """
        if value < 0 or value >= self.maximums[channel]:
            raise ValueError(f"Minimum value invalid, should be in range [0-{self.maximums[channel] - 1}")

        self.minimums[channel] = value

    @rpc_method
    def set_max(self, channel: int, value: int) -> None:
        """Replace a maximum value for a channel.

        Parameters:
            channel: The channel number.
            value: The new maximum target value.
        """
        if value <= self.minimums[channel] or value > self.DEFAULT_MAX_PULSE_WIDTH:
            raise ValueError(f"Maximum value invalid, should be in range [{self.minimums[channel] + 1}" +
                             f"-{self.DEFAULT_MAX_PULSE_WIDTH}]")

        self.maximums[channel] = value
