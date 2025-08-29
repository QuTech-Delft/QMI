"""Module that defines packet formats for the UDP Responder.
"""

import enum
import ctypes
import logging
from typing import ClassVar

from qmi.core.exceptions import QMI_RuntimeException

_logger = logging.getLogger(__name__)

# The magic number to recognize QMI UDP packets.
MAGIC = 0x00494d51  # Magic value. This is stored little endian, and then reads 'QMI\0' in ASCII.


class QMI_LittleEndianStructure(ctypes.LittleEndianStructure):
    """The standard ctypes LittleEndianStructure, with a proper repr() function."""

    def __repr__(self) -> str:
        fstr_list = []
        for (fname, ftype, *_) in self._fields_:
            value = getattr(self, fname)
            if isinstance(value, (QMI_LittleEndianStructure, int, float, bytes)):
                vstr = repr(value)
            elif isinstance(value, ctypes.Array):
                vstr = f"[{', '.join((repr(e) for e in value))}]"
            else:
                _logger.error("Unhandled type: %s %s", type(value), value)
                vstr = repr(value)
            fstr = f"{fname}={vstr}"
            fstr_list.append(fstr)
        return f"{self.__class__.__name__}({', '.join(fstr_list)})"


@enum.unique
class QMI_UdpResponderMessageTypeTag(enum.Enum):
    # Requests sent by qmitool or similar tools.
    CONTEXT_INFO_REQUEST  = 0x201 # Broadcast or targeted.
    CONTEXT_KILL_REQUEST  = 0x202 # Broadcast or targeted.
    # Packets sent by the Contexts.
    CONTEXT_INFO_RESPONSE = 0x101 #
    CONTEXT_STARTUP       = 0x102 # Broadcast.
    CONTEXT_SHUTDOWN      = 0x103 # Broadcast.


class QMI_UdpResponderPacketHeader(QMI_LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('magic'         , ctypes.c_uint32),  # Value: 0x00494d51 ('QMI\0').
        ('pkt_type_tag'  , ctypes.c_uint16),  # Entry from QMI_UdpResponderMessageTypeTag.
        ('pkt_id'        , ctypes.c_uint64),  # This message's ID.
        ('pkt_timestamp' , ctypes.c_double),  # This message's POSIX timestamp.
    ]

class QMI_UdpResponderContextDescriptor(QMI_LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('pid'           , ctypes.c_int32    ),  # PID of the process that owns the QMI_Context.
        ('name'          , ctypes.c_char * 64),  # Name of the context
        ('workgroup_name', ctypes.c_char * 64),
        ('port'          , ctypes.c_int32    )   # Listening TCP port of the context. (-1) means: no port.
    ]

# Concrete packets follow below:

class QMI_UdpResponderContextInfoRequestPacket(QMI_UdpResponderPacketHeader):
    _pack_ = 1
    _fields_ = [
        ('workgroup_name_filter', ctypes.c_char * 64),
        ('context_name_filter', ctypes.c_char * 64)
    ]  # No extra fields.

    @staticmethod
    def create(
        pkt_id: int,
        pkt_timestamp: float,
        workgroup_name_filter: bytes,
        context_name_filter: bytes
    ) -> 'QMI_UdpResponderContextInfoRequestPacket':
        return QMI_UdpResponderContextInfoRequestPacket(
            MAGIC,
            QMI_UdpResponderMessageTypeTag.CONTEXT_INFO_REQUEST.value,
            pkt_id,
            pkt_timestamp,
            workgroup_name_filter,
            context_name_filter
        )


class QMI_UdpResponderContextInfoResponsePacket(QMI_UdpResponderPacketHeader):
    _pack_ = 1
    _fields_ = [
        ('request_pkt_id'        , ctypes.c_uint64                  ),
        ('request_pkt_timestamp' , ctypes.c_double                  ),
        ('context'               , QMI_UdpResponderContextDescriptor)
    ]

    @staticmethod
    def create(
        pkt_id: int,
        pkt_timestamp: float,
        request_pkt_id: int,
        request_pkt_timestamp: float,
        context_pid: int,
        context_name: bytes,
        workgroup_name: bytes,
        context_port: int
    ) -> 'QMI_UdpResponderContextInfoResponsePacket':
        context_descriptor = QMI_UdpResponderContextDescriptor(context_pid, context_name, workgroup_name, context_port)
        return QMI_UdpResponderContextInfoResponsePacket(
            MAGIC, QMI_UdpResponderMessageTypeTag.CONTEXT_INFO_RESPONSE.value,
            pkt_id,
            pkt_timestamp,
            request_pkt_id,
            request_pkt_timestamp,
            context_descriptor
        )


class QMI_UdpResponderKillRequestPacket(QMI_UdpResponderPacketHeader):
    _pack_ = 1
    _fields_: ClassVar[list] = []  # No extra fields.

    @staticmethod
    def create(pkt_id: int, pkt_timestamp: float) -> 'QMI_UdpResponderKillRequestPacket':
        return QMI_UdpResponderKillRequestPacket(
            MAGIC,
            QMI_UdpResponderMessageTypeTag.CONTEXT_KILL_REQUEST.value,
            pkt_id,
            pkt_timestamp
        )


_packet_type_lookup = {
    QMI_UdpResponderMessageTypeTag.CONTEXT_INFO_REQUEST  : QMI_UdpResponderContextInfoRequestPacket,
    QMI_UdpResponderMessageTypeTag.CONTEXT_KILL_REQUEST  : QMI_UdpResponderKillRequestPacket,
    QMI_UdpResponderMessageTypeTag.CONTEXT_INFO_RESPONSE : QMI_UdpResponderContextInfoResponsePacket
}


def unpack_qmi_udp_packet(packet: bytes) -> QMI_UdpResponderPacketHeader:

    packet_size = len(packet)

    if packet_size < ctypes.sizeof(QMI_UdpResponderPacketHeader):
        raise QMI_RuntimeException("Bad QMI UDP packet: too short.")

    header = QMI_UdpResponderPacketHeader.from_buffer_copy(packet)

    if header.magic != MAGIC:
        raise QMI_RuntimeException("Bad QMI UDP packet: bad magic field.")

    packet_type_tag = QMI_UdpResponderMessageTypeTag(header.pkt_type_tag)

    packet_type = _packet_type_lookup.get(packet_type_tag)
    if packet_type is None:
        raise QMI_RuntimeException("Bad QMI UDP packet: unknown packet type tag.")

    expected_packet_size = ctypes.sizeof(packet_type)

    if packet_size != expected_packet_size:
        raise QMI_RuntimeException(
            "Bad UDP packet: unexpected size (tag = {}, actual = {}, expected = {})".format(
                packet_type_tag, packet_size, expected_packet_size
            )
        )

    return packet_type.from_buffer_copy(packet)
