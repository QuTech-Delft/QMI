"""Driver for the NKT Photonics Interbus protocol.

The communication protocol to the laser driver is documented in the "Software Development Kit for NKT Photonics Instruments - Instruction Manual"
document, v 2.1.3, Oct 2018. [Reference 1].

Chapter 2 of this document describes the NKT Photonocs Interbus protocol (physical, framing, CRC, etc.)

This chapter says, at the start:

"This section describes the NKT Photonics Interbus protocol and module hardware integration.
 It is not to be confused with INTERBUS developed by Phoenix Contact."
"""

import enum
import logging
import time
from typing import NamedTuple, Optional

from qmi.core.transport import QMI_Transport
from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class MessageType(enum.Enum):
    NACK              = 0 ; "Response. Message not understood, not applicable, or not allowed (Not acknowledged)."
    CRC_ERROR         = 1 ; "Response. CRC error in received message."
    BUSY              = 2 ; "Response. Cannot respond at the moment. Module too busy."
    ACK               = 3 ; "Response. Received message understood (Acknowledged)."
    READ              = 4 ; "Query. Read the contents of a register."
    WRITE             = 5 ; "Transmission. Write something to a register."
    SET_SINGLE_BIT    = 6 ; "Transmission. Write a logic one to a bit will set the corresponding bit in the register value. Logic zeros have no effect."
    CLEAR_SINGLE_BIT  = 7 ; "Transmission. Writing a logic one to a bit will clear the corresponding bit in the register value. Logic zeros have no effect."
    DATAGRAM          = 8 ; "Response. Register content returned; caused by a previous READ."
    TOGGLE_SINGLE_BIT = 9 ; "Transmission. Writing a logic one to a bit will invert (toggle) the corresponding bit in the register value. Logic zeros have no effect."


class RegisterNumber(enum.Enum):
    MODULE_TYPE    = 0x61 ; "Module type number. Is used to determine what type of module the host is communicating with."
    SERIAL_NUMBER  = 0x64 ; "Firmware version code."
    STATUS_BITS    = 0x66 ; "Status monitor for a module or system."
    ERROR_CODE     = 0x67 ; "Error code as a byte value."


def _crc_ccitt(crc:int , c: int) -> int:

    crc ^= (c << 8)

    for i in range(8):
        xorflag = ((crc & 0x8000) != 0)
        crc = (crc << 1) & 0xffff
        if xorflag:
            crc ^= 0x1021

    return crc


class InterbusMessage(NamedTuple):
    """Message for the NKT Interbus protocol."""
    destination: int
    source: int
    message_type: MessageType
    register_number: int
    data: bytes


def _encode_interbus_message(message: InterbusMessage) -> bytes:
    """Encode an InterbusMessage to a bytes buffer."""

    # First, verify parameters:
    #
    # Destination and source addresses:
    #
    # * Address 0 reserved for 'special purposes'.
    #
    # * Addresses 1.. 160 specifies an NKT module.
    #
    #   The following addresses are assigned be NKT and listed in Chapter 6 of [Reference 1]:
    #
    # * Addresses 161..255 are considered host addresses (from PC or other equipment)
    #
    # Message type:
    #
    # * See the MessageType enumeration type.

    ok = (1 <= message.destination <= 160)
    if not ok:
        raise ValueError("Bad 'destination' value: {!r}".format(message.destination))

    ok = (161 <= message.source <= 255)
    if not ok:
        raise ValueError("Bad 'source' value: {!r}".format(message.source))

    if message.data is not None:
        ok = (0 <= len(message.data) <= 240)
        if not ok:
            raise ValueError("Bad 'data' length: {!r}".format(len(message.data)))

    # Synthesize message.

    register_number = message.register_number

    if isinstance(register_number, RegisterNumber):
        register_number = register_number.value

    encoded_message = bytearray([message.destination, message.source, message.message_type.value, register_number])

    if message.data:
        encoded_message.extend(message.data)

    # Add 16-bit CRC
    crc = 0
    for b in encoded_message:
        crc = _crc_ccitt(crc, b)

    encoded_message.extend(bytes([crc // 256, crc % 256]))

    # Escape 3 specific byte values, making sure they don't occur in the actual message.
    # NOTE: it is important to start with 0x5e, otherwise values will be doubly substituted.
    for value in [0x5e, 0x0d, 0x0a]:
        encoded_message = encoded_message.replace(bytes([value]), bytes([0x5e, value + 0x40]))

    # Add Start-Of-Transmission (SOT) and End-Of-Transmission (EOT) markers.
    encoded_message_b = bytes([13]) + encoded_message + bytes([10])

    return encoded_message_b


def _decode_interbus_message(encoded_message: bytes) -> InterbusMessage:
    """Decode an InterbusMessage to a bytes buffer."""

    if len(encoded_message) < 8:
        raise ValueError("Invalid interbus message (too short)")

    # Check SOT and EOT
    ok = (encoded_message[0] == 13 and encoded_message[-1] == 10)
    if not ok:
        raise ValueError("Invalid interbus message (SOT/EOT)")

    encoded_message = encoded_message[1:-1]  # Get rid of SOT and EOT.

    # Unescape 3 values:
    for value in [0x0a, 0x0d, 0x5e]:
        encoded_message = encoded_message.replace(bytes([0x5e, value + 0x40]), bytes([value]))

    if len(encoded_message) < 6:
        raise ValueError("Invalid interbus message (too short)")

    # Check 16-bit CRC
    crc = 0
    for b in encoded_message:
        crc = _crc_ccitt(crc, b)

    if crc != 0:
        raise ValueError("Bad CRC while decoding NKT Photonics Interbus message.")

    encoded_message = encoded_message[:-2]

    message = InterbusMessage(encoded_message[0], encoded_message[1], MessageType(encoded_message[2]), encoded_message[3], encoded_message[4:])

    return message


class NKTPhotonicsInterbusProtocol:
    """This is a wrapper around a QMI_Transport that provides NKT Photonics Interbus communication primitives."""

    # According to NKT documentation, we must choose an address above 160.
    HOST_BASE_ADDRESS = 161

    # The NKT laser sometimes does not answer a request.
    # In that case we retry the request at most this number of times.
    MAX_RETRY_COUNT = 10

    def __init__(self, transport: QMI_Transport, timeout: float):
        self._transport = transport
        self._timeout = timeout
        self._source_toggle = 1

    def _read_message(self) -> InterbusMessage:
        """Read and decode an NKT Photonics Interbus message over the transport."""
        message = self._transport.read_until(message_terminator=b"\n", timeout=self._timeout)
        decoded_message = _decode_interbus_message(message)
        return decoded_message

    def _send_message(self, message: InterbusMessage) -> None:
        """Encode and send an NKT Photonics Interbus message over the transport."""
        encoded_message = _encode_interbus_message(message)
        self._transport.write(encoded_message)

    def _request_response(
            self,
            destination: int,
            message_type: MessageType,
            register_number: int,
            data: bytes
            ) -> InterbusMessage:
        """Attempt request/response sequence.

        Occasionally, the NKT fails to respond to a request.
        The cause of these failures is not known. The failure rate may vary;
        initial estimate was once per 100,000 requests; recent tests suggest
        one failure per 250 requests.

        When the NKT device fails to respond, we simply retry the request
        until it succeeds or until `MAX_RETRY_COUNT` is exceeded.

        Raises:
            QMI_TimeoutException: When timeout occurs while waiting for a response
                and maximum number of retries is reached.
            QMI_InstrumentException: When an invalid message is received
                and maximum number of retries is reached.
        """

        # Use a source address that is different from the previous request.
        # This avoids accidental processing of a stale response in case
        # the previous request was retried and got two responses.
        self._source_toggle = (self._source_toggle + 1) & 1
        source = self.HOST_BASE_ADDRESS + self._source_toggle

        request = InterbusMessage(destination, source, message_type, register_number, data)

        # Send query.
        self._send_message(request)

        # Wait for response.
        failure_counter = 0
        while True:

            try:
                response = self._read_message()
            except (ValueError, QMI_TimeoutException) as exc:
                # Catch timeout and badly formatted messages.
                _logger.warning("Error while reading response: %s", str(exc))

                # Check if we can try again. If not, re-raise the exception to be handled by the caller.
                failure_counter += 1
                if failure_counter > self.MAX_RETRY_COUNT:
                    if isinstance(exc, ValueError):
                        raise QMI_InstrumentException("Invalid interbus response") from exc
                    else:
                        raise

                # Resend the request
                self._send_message(request)

                # Wait again for a response.
                continue

            # We received a response. Check that it matches the request.
            if (response.source == request.destination) and (response.destination == request.source):
                break

            # We received a valid message that does not match our request.
            _logger.warning("Unexpected response src=%d,dst=%d while expecting src=%d,dst=%d",
                            response.source, response.destination, request.destination, request.source)

            # Check if we can try again. If not, raise an exception to be handled by the caller.
            failure_counter += 1
            if failure_counter > self.MAX_RETRY_COUNT:
                raise QMI_InstrumentException("Unexpected response message, maximum retry count reached")

            # Discard the mismatching message and wait for another message.
            # Do not resend the request, because a reply may already be pending.

        return response

    def get_register(self, destination: int, register_number: int) -> bytes:
        """Read the specified register."""

        response = self._request_response(destination, MessageType.READ, register_number, b"")

        if response.message_type == MessageType.NACK:
            raise QMI_InstrumentException(f"Got NACK response for get_register reg=0x{register_number:x}")
        if response.message_type != MessageType.DATAGRAM:
            raise QMI_InstrumentException(f"Unexpected response for get_register ({response})")
        if response.register_number != register_number:
            raise QMI_InstrumentException(f"Response does not match register number req.reg=0x{register_number:x}"
                                          + f" resp.reg=0x{response.register_number:x}")

        return response.data

    def set_register(self, destination: int, register_number: int, data: Optional[bytes]) -> None:
        """Write to the specified register."""

        if data is None:
            data = b""
        response = self._request_response(destination, MessageType.WRITE, register_number, data)

        if response.message_type == MessageType.NACK:
            raise QMI_InstrumentException(f"Got NACK response for set_register reg=0x{register_number:x}")
        if response.message_type != MessageType.ACK:
            raise QMI_InstrumentException(f"Unexpected response for set_register ({response})")
        if response.register_number != register_number:
            raise QMI_InstrumentException(f"Response does not match register number req.reg=0x{register_number:x}"
                                          + f" resp.reg=0x{response.register_number:x}")
