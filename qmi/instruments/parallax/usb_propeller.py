"""Instrument driver for the Parallax USB Propeller, for servo control."""

import logging
import struct
from time import sleep
from typing import List, Optional, Union

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Parallax_UsbPropeller(QMI_Instrument):
    """Instrument driver for the Parallax USB Propeller for servo control."""
    DEFAULT_BAUDRATE = 2400
    RESPONSE_TIMEOUT = 1.0
    AVAILABLE_CHANNELS = 16
    MAX_SPEED = 64
    MAX_PULSE_WIDTH = 1024  # Would be about 2.048 ms
    DEFAULT_MIN = 500  # 1 ms
    DEFAULT_MAX = 688  # 1.376 ms

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": self.DEFAULT_BAUDRATE, "timeout": self.RESPONSE_TIMEOUT}
        )
        self._endline = b"\r"
        self._ramp_speed: List[int] = [0] * self.AVAILABLE_CHANNELS  # Keep track of the ramp speed
        # Track target value for each servo. Targets start at 0 (= no move).
        self.targets: List[int] = [0] * self.AVAILABLE_CHANNELS
        # Servo minimum and maximum targets can be restricted to protect components.
        self.minimums: List[int] = [self.DEFAULT_MIN] * self.AVAILABLE_CHANNELS
        self.maximums: List[int] = [self.DEFAULT_MAX] * self.AVAILABLE_CHANNELS

    def _check_channel(self, channel: int) -> None:
        """Check the channel number."""
        if not 0 <= channel < self.AVAILABLE_CHANNELS:
            raise ValueError(f"Invalid channel number. Must be in range 0-{self.AVAILABLE_CHANNELS - 1}")

    def _write(self, cmd: str, channel: Optional[int] = None) -> None:
        """Writes a command to servo. The command consists of 6 character bytes (c), followed by an
        unsigned integer (B) and closed off with a character byte, which is carriage return.

        Parameters:
            cmd:        The string to write.
            channel:    Channel number.
        """
        # Determine struct.pack string
        pack_string = "ccc"  # Start with the obligatory "!SC" string
        bytes_list: List[Optional[bytes]] = [b"!", b"S", b"C"] + [None] * 5
        count = 3
        for c in cmd:
            pack_string += "c"  # add all command string characters
            bytes_list[count] = c.encode()
            count += 1

        if channel is not None:
            pack_string += "B"  # Add channel number integer
            bytes_list[count] = channel  # type: ignore
            count += 1

        pack_string += "c"  # Add endline
        bytes_list[-1] = self._endline
        l = [pack_string] + bytes_list
        message = struct.pack(*l)  # type: ignore
        self._transport.write(message)
        sleep(len(bytes_list) / self.DEFAULT_BAUDRATE)  # Sleep some bits to let the message arrive

    def _write_value(self, channel: int, value: int, default: bool = False) -> None:
        """Set default or new target value. Default value consists of four character bytes (c),
        followed by three unsigned integers (B), closing off with a character byte, which is carriage return.
        Setting new value consists of three character bytes (c), followed by four unsigned integers (B),
        closing off with a character byte, which is carriage return.

        Parameters:
            channel:        Channel number.
            value:          The target value. The modulo 256 of this is the lowbyte and 8-bit right shift the highbyte.
            default:        If setting default value, True. If setting new target value, False.
        """
        target = value
        ramp_speed = self._ramp_speed[channel]
        if target < self.minimums[channel]:
            target = self.minimums[channel]
            _logger.warning("Target value for channel %i below minimum. Setting to %i", channel, target)
        elif self.maximums[channel] < target:
            target = self.maximums[channel]
            _logger.warning("Target value for channel %i above maximum. Setting to %i", channel, target)

        if default:
            message = struct.pack(
                "ccccBBBc", b"!", b"S", b"C", b"D", channel, target % 256, target >> 8, self._endline
            )
        else:
            message = struct.pack(
                "cccBBBBc", b"!", b"S", b"C", channel, ramp_speed, target % 256, target >> 8, self._endline
            )

        self._transport.write(message)
        sleep(8 / self.DEFAULT_BAUDRATE)  # Sleep some bits to let the message arrive

    def _ask(self, cmd: str, channel: Optional[int] = None) -> Union[int, str]:
        """Writing a query and receiving a response. The query consists of 6 character bytes (c), followed by an
        unsigned integer (B) and closed off with a character byte, which is carriage return. This query always
        returns 3 bytes.

        Parameters:
            cmd:        The query string to write.
            channel:    Channel number.

        Returns:
            The position value of the channel left-shifted by 8 bits (highbyte) and added to it is the lowbyte.
        """
        self._transport.discard_read()
        self._write(cmd, channel)
        # Read answer bytes
        result = self._transport.read(nbytes=3, timeout=self.RESPONSE_TIMEOUT)
        read_channel, highbyte, lowbyte = struct.unpack("BBB", result)
        if chr(highbyte) == "." and 48 <= read_channel < 58 and 48 <= lowbyte < 58:
            return chr(read_channel) + chr(highbyte) + chr(lowbyte)  # It is a reply to FW version number request.

        elif chr(read_channel) == "C" and chr(highbyte) == "L" and chr(lowbyte) == "R":
            return "CLR"  # It is a reply to clear channel EEPROM command.

        elif chr(read_channel) + chr(highbyte) in ["BR", "PM", "DL"]:
            return lowbyte  # It is a reply to Baud rate set, port range set or startup servo mode set command

        assert read_channel == channel

        return (highbyte << 8) + lowbyte

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
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        version = str(self._ask("VER?"))
        return QMI_InstrumentIdentification(vendor="Parallax", model="USB Propeller", serial=None, version=version)

    @rpc_method
    def set_target_value(self, channel: int, value: int) -> None:
        """Set Servo channel to move given value time with certain ramp speed. The time value represents a pulse width
        with 2us increments. For example, to send a 1 ms pulse to a channel you would use a pulse width value of 500
        (500 x 2 us = 1000 us = 1 ms).

        Parameters:
            channel:        The channel number.
            value:          The servo target move value [1-1024], in 2us increments.
        """
        self._check_is_open()
        self._check_channel(channel)
        if not 0 < value <= self.MAX_PULSE_WIDTH:
            raise ValueError(f"Invalid move value {value}. Must be in range 1-{self.MAX_PULSE_WIDTH}.")

        self._write_value(channel, value)
        self.targets[channel] = value

    @rpc_method
    def set_default_move(self, channel: int, value: int) -> None:
        """Set Servo channel default move time at start-up. This value is then stored in EEPROM. The time value
        represents a pulse width with 2us increments. For example, to send a 1 ms pulse to a channel you would use a
        pulse width value of 500 (500 x 2 us = 1000 us = 1 ms).

        Parameters:
            channel:        The channel number.
            value:          The servo target move value [1-1024].
        """
        self._check_is_open()
        self._check_channel(channel)
        if not 0 < value <= self.MAX_PULSE_WIDTH:
            raise ValueError(f"Invalid move value {value}. Must be in range 1-{self.MAX_PULSE_WIDTH}.")

        self._write_value(channel, value, default=True)

    @rpc_method
    def get_target_values(self) -> List[int]:
        """Return the current target values list."""
        return self.targets

    @rpc_method
    def get_value(self, channel: int) -> int:
        """Return current value of a servo channel.

        Parameters:
            channel:        The channel number.

        Returns:
            The channel position.
        """
        self._check_is_open()
        self._check_channel(channel)
        return int(self._ask("RSP", channel))

    @rpc_method
    def set_speed(self, channel: int, speed: int) -> None:
        """Set speed of channel in steps between 0 and 64. This option specifies the speed of the servo.

        Parameters:
            channel:    The channel number.
            speed:      The servo ramp speed value [0-63].


        Raises:
            ValueError if speed not in range 0-1000.
        """
        self._check_is_open()
        self._check_channel(channel)
        if not 0 <= speed < self.MAX_SPEED:
            raise ValueError(f"Invalid ramp speed value {speed}. Must be in range 0-{self.MAX_SPEED -1}")

        self._ramp_speed[channel] = speed

    @rpc_method
    def get_speed(self, channel: int) -> int:
        """Get ramp speed of a channel.

        Parameters:
            channel:    The channel number.

        Returns:
            speed: The servo ramp speed value of the channel [0-63].
        """
        return self._ramp_speed[channel]

    @rpc_method
    def set_baud_rate(self, baud_rate: int) -> None:
        """Set the servo baud rate.

        Parameters:
            baud_rate:      The new baud rate, either as 0, 1, 2400 or 38400. 0 == 2400 and 1 == 38400

        Raises:
            ValueError if input baud_rate is not valid.
            AssertionError if returned baud_rate_set is not the same as the set baud rate.
        """
        self._check_is_open()
        valid_values = [0, 1, 2400, 38400]
        if baud_rate not in valid_values:
            raise ValueError(f"Invalid baud rate {baud_rate}. Should be one of valid values {valid_values}")

        # As we can give as input 0 or 1 only, set to 0 or 1
        if baud_rate == 2400:
            baud_rate = 0
        elif baud_rate == 38400:
            baud_rate = 1

        baud_rate_set = self._ask("SBR", baud_rate)
        if baud_rate == 0:
            assert baud_rate_set == 0

        else:
            assert baud_rate_set == 1

    @rpc_method
    def set_software_port_range(self, port_range: int) -> None:
        """Set software port range to 0-15 or 16-31.

        Parameters:
            port_range:     The new port range, either as 0 for 0-15 or 1 for 16-31.

        Raises:
            ValueError if input port_range is not valid.
            AssertionError if returned port_range_set is not the same as the set port range.
        """
        self._check_is_open()
        if port_range not in [0, 1]:
            raise ValueError(f"Invalid port range {port_range}. The valid values are 0 for 0-15 or 1 for 16-31.")

        port_range_set = self._ask("PSS", port_range)
        assert port_range_set == port_range

    @rpc_method
    def disable_servo_channel(self, channel: int) -> None:
        """Disable a servo channel. This will cause any connected servo to become lax and not try to hold its position.

        Parameters:
            channel:        The channel number.
        """
        self._check_is_open()
        self._check_channel(channel)
        self._write("PSD", channel)

    @rpc_method
    def enable_servo_channel(self, channel: int) -> None:
        """Enable a servo channel. Enabling a channel will cause it to move to the last position it was commanded to,
        or the startup default if no other position commands have been sent since power up/reset.

        Parameters:
            channel:        The channel number.
        """
        self._check_is_open()
        self._check_channel(channel)
        self._write("PSE", channel)

    @rpc_method
    def set_startup_servo_mode(self, servo_mode: int) -> None:
        """Set startup servo mode to either center at startup or to use custom positions stored in EEPROM.

        Parameters:
            servo_mode:     The new servo mode, either as 0 for center or 1 for custom from EEPROM.

        Raises:
            ValueError if input servo_mode is not valid.
            AssertionError if returned servo_mode_set is not the same as the set servo mode.
        """
        self._check_is_open()
        if servo_mode not in [0, 1]:
            raise ValueError(f"Invalid servo mode {servo_mode}. The valid values are 0 for custom or 1 for EEPROM.")

        servo_mode_set = self._ask("EDD", servo_mode)
        assert servo_mode_set == servo_mode

    @rpc_method
    def clear(self) -> None:
        """This command will set all custom settings, like Port Mode, Servo Disabled, Startup Mode and Default
        Positions, of the servo back to default.

        Raises:
            AssertionError if returned message after clear is not "CLR".
        """
        self._check_is_open()
        response = self._ask("LEAR")
        assert response == "CLR"

    @rpc_method
    def move_up(self, channel: int) -> None:
        """Moves the servo to maximal value.

        Parameters:
            channel:        The channel number.
        """
        self._check_is_open()
        self._check_channel(channel)
        self.set_target_value(channel, self.maximums[channel])

    @rpc_method
    def move_down(self, channel: int) -> None:
        """Moves the servo to minimal value.

        Parameters:
            channel:        The channel number.
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
        self._check_is_open()
        self._check_channel(channel)
        value_now = self._ask("RSP", channel)
        if not value_now == self.targets[channel]:
            return True

        return False

    @rpc_method
    def set_min(self, channel: int, value: int) -> None:
        """Replace the minimum value for a channel.

        Parameters:
            channel:        The channel number.
            value:          The new minimum target value.
        """
        self._check_channel(channel)
        if value < 0 or value >= self.maximums[channel]:
            raise ValueError(f"Minimum value {value} invalid, should be in range [0-{self.maximums[channel] - 1}")

        self.minimums[channel] = value

    @rpc_method
    def set_max(self, channel: int, value: int) -> None:
        """Replace the maximum value for a channel.

        Parameters:
            channel:        The channel number.
            value:          The new maximum target value.
        """
        self._check_channel(channel)
        if value <= self.minimums[channel] or value > self.MAX_PULSE_WIDTH:
            raise ValueError(f"Maximum value {value} invalid, should be in range [{self.minimums[channel] + 1}" +
                             f"-{self.MAX_PULSE_WIDTH}]")

        self.maximums[channel] = value
