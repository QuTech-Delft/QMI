"""
Module for the APT protocol used by Thorlabs. The documentation for the protocol can be found
here https://www.thorlabs.com/Software/Motion%20Control/APT_Communications_Protocol.pdf
"""

from ctypes import sizeof
from enum import Enum
import logging
import time
from typing import Any, Union

from qmi.core.transport import QMI_Transport
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


class AptProtocol:
    """
    Implement the Thorlabs APT protocol primitives.
    """

    HEADER_SIZE_BYTES = 6

    def __init__(
        self,
        transport: QMI_Transport,
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

    def create(self, msg_type: _AptMessage, **kwargs: Any) -> _AptMessage:
        return msg_type.create(
            dest=self._apt_device_address,
            source=self._host_address,
            **kwargs
        )

    def send_message(self, msg: _AptMessage) -> None:
        """Encode and send a binary message to the instrument."""
        self._transport.write(bytes(msg))

    def read_message(self, timeout: float) -> _AptMessage:
        """Read and decode a binary message from the instrument."""

        # Read message header.
        data = self._transport.read(nbytes=6, timeout=timeout)

        # Decode message header.
        hdr = _AptMessageHeader.from_buffer_copy(data)

        # Long APT messages are identified by bit 7 in the destination field.
        if (hdr.dest & 0x80) != 0:
            # This is a long APT message (header + data). Read the additional data.
            try:
                # Since we already received a partial message, the timeout
                # only needs to account for the time it takes to receive
                # the payload data. (The instrument will probably transmit
                # the entire message as fast as possible).
                # 50 ms should be more than enough.
                data += self._transport.read(nbytes=hdr.data_length, timeout=0.050)
            except QMI_TimeoutException:
                # Discard pending data after receiving a partial message.
                self._transport.discard_read()
                raise QMI_InstrumentException(
                    "Received partial message (message_id=0x{:04x}, data_length={})".format(
                        hdr.message_id, hdr.data_length
                    )
                )

        # Decode the complete message.
        message_type = APT_MESSAGE_TYPE_TABLE.get(hdr.message_id)
        if message_type is None:
            # Discard pending data after receiving a bad message.
            self._transport.discard_read()
            raise QMI_InstrumentException(
                "Received unknown message id 0x{:04x} from instrument".format(hdr.message_id)
            )

        if len(data) != sizeof(message_type):
            # Discard pending data after receiving a bad message.
            self._transport.discard_read()
            raise QMI_InstrumentException(
                ("Received incorrect message length for message id 0x{:04x} "
                + "(got {} bytes while expecting {} bytes)").format(
                    hdr.message_id, len(data), sizeof(message_type)
                )
            )

        # Decode received message.
        return message_type.from_buffer_copy(data)

    def wait_message(self, message_type: _AptMessage, timeout: float) -> _AptMessage:
        """Wait for a specific message type from the instrument.

        Any other (valid) messages received from the instrument will be discarded.

        Parameters:
            message_type:   Type of message to wait for.
            timeout:        Maximum time to wait for the message in seconds.

        Returns:
            The received message.

        Raises:
            QMI_TimeoutException: If the expected message is not received within the timeout.
            QMI_InstrumentException: If an invalid message is received.
        """

        end_time = time.monotonic() + timeout
        while True:

            # Read next message from instrument.
            tmo = max(end_time - time.monotonic(), 0)
            msg = self.read_message(timeout=tmo)

            if isinstance(msg, message_type):
                # Got the expected message.
                return msg

            # Discard message and continue waiting.
            _logger.debug("Ignoring APT message %s (message_id=0x%04x)",
                          type(msg).__name__, msg.message_id)

            if time.monotonic() > end_time:
                raise QMI_TimeoutException(f"Expected message type {message_type} not received.")

    def ask(self, request_msg: _AptMessage, reply_msg: Union[_AptMessage, _AptMessageHeader]) -> _AptMessage:
        """A helper function for requests that expect a response.

        Parameters:
            request_msg: The request message to be sent.
            reply_msg:   The reply message expected to be received.
        """
        self.send_message(request_msg)
        return self.wait_message(type(reply_msg), timeout=self._timeout)
