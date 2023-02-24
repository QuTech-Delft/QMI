"""Instrument driver for the Thorlabs MFF101/MFF102 motorized flip mounts."""

import logging
import struct
import time
from typing import NamedTuple, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Hardware information returned by instrument.
_HwInfo = NamedTuple('_HwInfo', [
    ('serial_number', int),
    ('model_number', str),
    ('hw_type', int),
    ('fw_version', Tuple[int, int, int]),
    ('hw_version', int),
    ('mod_state', int),
    ('num_channels', int)
])


def _format_msg_hw_req_info(dest: int, source: int) -> bytes:
    """Prepare a HW_REQ_INFO message.

    The controller will answer with MSG_HW_GET_INFO.

    Parameters:
        dest: Destination address.
        source: Source address.
    """
    assert 0 <= dest < 128
    assert 0 <= source < 128
    msg = bytes([0x05, 0x00, 0x00, 0x00, dest, source])
    return msg


def _format_msg_mot_req_statusbits(chan_iden: int, dest: int, source: int) -> bytes:
    """Prepare a MOT_REQ_STATUSBITS message.

    The controller will answer with MSG_MOT_GET_STATUSBITS.

    Parameters:
        chan_iden: Channel identifier.
        dest: Destination address.
        source: Source address.
    """
    assert 0 <= dest < 128
    assert 0 <= source < 128
    msg = bytes([0x29, 0x04, chan_iden, 0x00, dest, source])
    return msg


def _format_msg_mot_move_jog(chan_iden: int, direction: int, dest: int, source: int) -> bytes:
    """Prepare a MOT_MOVE_JOG message.

    The controller will answer with MSG_MOT_MOVE_COMPLETED.

    Parameters:
        chan_iden: Channel identifier.
        direction: Direction to move (0x01=forward, 0x02=reverse).
        dest: Destination address.
        source: Source address.
    """
    assert 0 <= chan_iden <= 255
    assert 0 <= direction <= 255
    assert 0 <= dest < 128
    assert 0 <= source < 128
    msg = bytes([0x6A, 0x04, chan_iden, direction, dest, source])
    return msg


def _parse_msg_hw_get_info(msg: bytes) -> _HwInfo:
    assert len(msg) >= 6
    (message_id,) = struct.unpack_from("<H", msg, 0)
    if message_id != 0x0006:
        raise QMI_InstrumentException("Got message ID {:04x} while expecting MSG_HW_GET_INFO".format(message_id))

    if len(msg) < 90:
        raise QMI_InstrumentException("Got {} bytes while expecting 90 bytes MSG_HW_GET_INFO".format(len(msg)))

    (serial_number,) = struct.unpack_from("<I", msg, 6)
    model_number = msg[10:18].rstrip(b"\x00").decode('ascii', errors='replace')
    (hw_type,) = struct.unpack_from("<H", msg, 18)
    fw_version = (msg[22], msg[21], msg[20])
    (hw_version, mod_state, num_channels) = struct.unpack_from("<HHH", msg, 84)

    return _HwInfo(serial_number, model_number, hw_type, fw_version, hw_version, mod_state, num_channels)


def _parse_msg_mot_get_statusbits(msg: bytes) -> int:
    assert len(msg) >= 6
    (message_id,) = struct.unpack_from("<H", msg, 0)
    if message_id != 0x042A:
        raise QMI_InstrumentException("Got message ID {:04x} while expecting MSG_MOT_GET_STATUSBITS".format(message_id))

    if len(msg) < 12:
        raise QMI_InstrumentException("Got {} bytes while expecting 12 bytes MSG_MOT_GET_STATUSBITS".format(len(msg)))

    (statusbits,) = struct.unpack_from("<I", msg, 8)
    return statusbits


def _parse_msg_mot_move_completed(msg: bytes) -> None:
    assert len(msg) >= 6
    (message_id,) = struct.unpack_from("<H", msg, 0)
    if message_id != 0x0464:
        raise QMI_InstrumentException("Got message ID {:04x} while expecting MSG_MOT_MOVE_COMPLETED".format(message_id))


class Thorlabs_MFF10X(QMI_Instrument):
    """Instrument driver for the Thorlabs MFF101/MFF102 motorized flip mounts."""

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialize driver.

        The flipmount presents itself as an USB serial port.
        The transport descriptor should refer to the serial port device,
        e.g. "serial:/dev/ttyUSB1"

        Parameters:
            name: Name for this instrument instance.
            transport: Transport descriptor to access the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "rtscts": True})

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        self._transport.discard_read()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _read_message(self, timeout: float) -> bytes:
        """Read a binary message from the instrument."""

        assert self._transport is not None
        msg = self._transport.read(nbytes=6, timeout=timeout)

        if (msg[4] & 0x80) != 0:
            # extended message
            (datalen,) = struct.unpack_from("<H", msg, 2)
            if datalen > 255:
                raise QMI_InstrumentException("Received invalid message header from instrument")
            payload = self._transport.read(nbytes=datalen, timeout=timeout)
            msg = msg + payload

        return msg

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""

        self._check_is_open()
        assert self._transport is not None

        req_msg = _format_msg_hw_req_info(dest=0x11, source=0x01)
        self._transport.discard_read()
        self._transport.write(req_msg)

        answer_msg = self._read_message(timeout=1.0)
        hw_info = _parse_msg_hw_get_info(answer_msg)

        return QMI_InstrumentIdentification(vendor="Thorlabs",
                                            model=hw_info.model_number,
                                            serial=str(hw_info.serial_number),
                                            version="{}.{}.{}".format(*hw_info.fw_version))

    @rpc_method
    def get_position(self) -> int:
        """Get current position of flip mount.

        Returns:
            Current position:
                0 = mount in undefined position;
                1 = mount in forward position;
                2 = mount in reverse position.
        """

        self._check_is_open()
        assert self._transport is not None

        req_msg = _format_msg_mot_req_statusbits(chan_iden=1, dest=0x11, source=0x01)
        self._transport.discard_read()
        self._transport.write(req_msg)

        answer_msg = self._read_message(timeout=1.0)
        statusbits = _parse_msg_mot_get_statusbits(answer_msg)

        return statusbits & 3

    @rpc_method
    def move_mount(self,
                   direction: int,
                   wait_complete: bool,
                   timeout: float = 5.0
                   ) -> None:
        """Move the flip mount and wait until move is finished.

        Parameters:
            direction: Direction to move:
                1 = move to forward position;
                2 = move to reverse position.
            wait_complete: True to wait until the move completes.
            timeout: Maximum time to wait for response (seconds).

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the move does not complete within the specified timeout.
        """

        self._check_is_open()
        assert self._transport is not None

        if direction not in (1, 2):
            raise ValueError("Invalid value for parameter 'direction' (must be 1 or 2).")

        req_msg = _format_msg_mot_move_jog(chan_iden=1, direction=direction, dest=0x11, source=0x01)
        self._transport.discard_read()
        self._transport.write(req_msg)

        if wait_complete:
            waited = 0.0
            completed = False
            interval = 0.05
            while (not completed) and (waited < timeout):
                time.sleep(interval)
                waited += interval
                if self.get_position() == direction:
                    completed = True
            if not completed:
                raise QMI_TimeoutException("Timeout while waiting for moving flipmount")
