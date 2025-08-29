"""
Module for the APT protocol used by Thorlabs. The documentation for the protocol can be found
here https://www.thorlabs.com/Software/Motion%20Control/APT_Communications_Protocol.pdf
"""

from ctypes import sizeof
from dataclasses import dataclass
from enum import Enum
import logging
import time
from serial import SerialException
from typing import Any

from qmi.core.transport import QMI_SerialTransport
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.instruments.thorlabs.apt_packets import _AptMessage, _AptMessageHeader, APT_MESSAGE_TYPE_TABLE

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class AptChannelState(Enum):
    """Channel state"""
    ENABLE = 0x01
    DISABLE = 0x02


class AptChannelStopMode(Enum):
    """Channel stop mode"""
    IMMEDIATE = 0x01
    PROFILED = 0x02


class AptChannelJogDirection(Enum):
    """Jog direction"""
    FORWARD = 0x01
    BACKWARD = 0x02


class AptChannelHomeDirection(Enum):
    """Possible values for the ``home_direction`` field in the homing parameters."""
    FORWARD = 0x01
    REVERSE = 0x02


class AptChannelHomeLimitSwitch(Enum):
    """Possible values for the ``limit_switch`` field in the homing parameters."""
    REVERSE = 0x01
    FORWARD = 0x04


@dataclass
class VelocityParams:
    """Velocity parameters for the controller.

    Attributes:
        max_velocity:    Maximum velocity in degrees/second or mm/second.
        acceleration:    Acceleration in degrees/second/second or mm/second/second.
    """
    max_velocity: float
    acceleration: float


@dataclass
class HomeParams:
    """Homing parameters for the controller.

    Attributes:
        home_direction:  Direction of moving to home (1 = forward, 2 = reverse).
        limit_switch:    Limit switch to use for homing (1 = reverse, 4 = forward).
        home_velocity:   Homing velocity in degrees/second or mm/second.
        offset_distance: Distance of home position from home limit switch (in degrees or mm).
    """
    home_direction:     AptChannelHomeDirection
    limit_switch:       AptChannelHomeLimitSwitch
    home_velocity:      float
    offset_distance:    float


@dataclass
class MotorStatus:
    """Status bits of motor controller.

    Note: Some of the status bits do not seem to work with the K10CR1.

    Attributes:
        moving_forward:     True if the motor is moving in forward direction.
        moving_reverse:     True if the motor is moving in reverse direction.
                            It looks like `move_forward` and `move_reverse` are both
                            active when the stage is moving, regardless of the actual
                            direction of movement.
        jogging_forward:    True if the motor is jogging in forward direction.
        jogging_reverse:    True if the motor is jogging in reverse direction.
                            It looks like `jogging_reverse` is also active when jogging
                            in forward direction, while `jogging_forward` is never active.
        homing:             True if the motor is homing.
        homed:              True if homing has been completed.
        motion_error:       True if an excessive position error is detected.
        current_limit:      True if the motor current limit has been reached.
        channel_enabled:    True if the motor drive channel is enabled.
    """
    forward_limit:      bool
    reverse_limit:      bool
    moving_forward:     bool
    moving_reverse:     bool
    jogging_forward:    bool
    jogging_reverse:    bool
    homing:             bool
    homed:              bool
    tracking:           bool
    settled:            bool
    motion_error:       bool
    current_limit:      bool
    channel_enabled:    bool


class AptProtocol:
    """
    Implement the Thorlabs APT protocol primitives.
    """

    HEADER_SIZE_BYTES = 6

    def __init__(
        self,
        transport: QMI_SerialTransport,
        apt_device_address: int = 0x50,
        host_address: int = 0x01,
        default_timeout: float | None = None,
    ):
        """Initialize the Thorlabs APT protocol handler.

        Parameters:
            transport:          Instance of `QMI_Transport` to use for sending APT commands to the instrument.
            apt_device_address: The address of the APT device. By default it is 0x50 which is a generic USB hardware
                                unit.
            host_address:       The address of the host that sends and receives messages. By default it is 0x01 which
                                is a host controller such as a PC.
            default_timeout:    Optional default response timeout in seconds.
                                The default is to wait indefinitely until a response is received.
        """
        self._transport = transport
        self._timeout = default_timeout
        self._apt_device_address = apt_device_address
        self._host_address = host_address

    def _clear_buffer(self) -> bytes:
        """Reads and clears the buffer. Suppress the timeout exception if no old message is in the buffer.

        Returns:
            pending_msg: Collected message bytes from the buffer or empty bytes string.
        """
        pending_msg = b""
        while self._transport._safe_serial.in_waiting > 0:
            _logger.debug("waiting to receive %i bytes.", self._transport._safe_serial.in_waiting)
            try:
                pending_msg += self._transport.read(self._transport._safe_serial.in_waiting, timeout=0.0)
            except SerialException:
                break

        return pending_msg

    def create(self, msg_type: _AptMessage, **kwargs: Any) -> _AptMessage:
        """Call for creating and returning a message instance. Valid for request and get messages.

        Returns:
            apt_message: The created message instance.
        """
        return msg_type.create(
            dest=self._apt_device_address,
            source=self._host_address,
            **kwargs
        )

    def send_message(self, msg: _AptMessage) -> None:
        """Encode and send a binary message to the instrument. Before sending a new command, do a non-blocking read
        to consume a potential old message from the instrument. This prevents a buildup of unhandled notification
        messages from the instrument after several move_XXX() commands.

        Parameters:
            msg: An `_AptMessage` instance.
        """
        pending_msg = self._clear_buffer()
        _logger.debug("Pending message %s (message_id=0x%04x): %s", type(msg).__name__, msg.message_id, pending_msg)

        self._transport.write(bytes(msg))

    def read_message(self, timeout: float | None) -> _AptMessage:
        """Read and decode a binary message from the instrument.

        Parameters:
            timeout: A timeout value for reading the messages.

        Returns:
            message: The obtained message instance with data from the buffer.

        Raises:
            QMI_InstrumentException: If an unknown or partial message is received.
        """

        # Read message header. If the header is not ready, double the timeout.
        if self._transport._safe_serial.in_waiting < self.HEADER_SIZE_BYTES:
            if timeout is not None:
                time.sleep(timeout)

        data = self._transport.read(nbytes=self.HEADER_SIZE_BYTES, timeout=timeout)

        # Decode message header.
        hdr = _AptMessageHeader.from_buffer_copy(data)
        # Decode the complete message.
        message_type = APT_MESSAGE_TYPE_TABLE.get(hdr.message_id)
        if message_type is None:
            # Discard pending data after receiving a bad message. Usually happens only when (too) many commands
            # are sent to the device in quick succession.
            self._transport.discard_read()
            raise QMI_InstrumentException(
                "Received unknown message id 0x{:04x} from instrument".format(hdr.message_id)
            )

        # Long APT messages are identified by bit 7 in the destination field.
        if (hdr.dest & 0x80) != 0:
            # This is a long APT message (header + data). Read the additional data.
            while len(data) < sizeof(message_type):
                try:
                    # Since we already received a partial message, the timeout
                    # only needs to account for the time it takes to receive
                    # the payload data. (The instrument will probably transmit
                    # the entire message as fast as possible).
                    data += self._transport.read(nbytes=hdr.data_length, timeout=0.050)
                except QMI_TimeoutException:
                    # Discard data after receiving a partial message.
                    partial_msg = self._clear_buffer()
                    raise QMI_InstrumentException(
                        "Received partial message (message_id=0x{:04x}, data_length={}, data={!r})".format(
                            hdr.message_id, hdr.data_length, partial_msg
                        )
                    )

        # Decode received message.
        return message_type.from_buffer_copy(data)

    def wait_message(self, message_type: type, timeout: float | None) -> _AptMessage:
        """Wait for a specific message type from the instrument.

        Any other (valid) messages received from the instrument will be discarded.

        Parameters:
            message_type:   Type of message to wait for.
            timeout:        Maximum time to wait for the message in seconds.

        Returns:
            The received message.

        Raises:
            QMI_TimeoutException: If the expected message is not received within the timeout.
        """

        end_time = time.monotonic() + timeout if timeout is not None else time.monotonic()
        while True:

            # Read next message from instrument.
            msg = self.read_message(timeout=timeout)
            if isinstance(msg, message_type):
                # Got the expected message.
                return msg

            # Discard message and continue waiting.
            _logger.debug("Ignoring APT message %s (message_id=0x%04x)",
                          type(msg).__name__, msg.message_id)

            if time.monotonic() > end_time:
                raise QMI_TimeoutException(f"Expected message type {message_type} not received.")

    def ask(self, request_msg: _AptMessage, reply_msg: _AptMessage | _AptMessageHeader) -> _AptMessage:
        """A helper function for requests that expect a response.

        Parameters:
            request_msg: The request message to be sent.
            reply_msg:   The reply message expected to be received.
        """
        self.send_message(request_msg)
        while self._transport._safe_serial.out_waiting > 0:
            _logger.debug("waiting for device to receive %i bytes.", self._transport._safe_serial.out_waiting)

        return self.wait_message(type(reply_msg), timeout=self._timeout)
