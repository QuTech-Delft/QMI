import struct
import unittest
import unittest.mock

from qmi.core.exceptions import QMI_TimeoutException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs.apt_packets import _AptMsgMoveCompleted, _AptMsgMoveHome, _AptMsgMoveHomed
from qmi.instruments.thorlabs.apt_protocol import AptProtocol


class TestAptProtocolReadMessage(unittest.TestCase):
    """Tests for `AptProtocol.read_message`, see issue #271."""

    def setUp(self):
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._protocol = AptProtocol(self._transport_mock)

    def test_read_message_does_not_sleep_waiting_for_header(self):
        """`read_message` must read the header directly instead of sleeping the full timeout first, even when
        the header is not yet available in the buffer."""
        header = struct.pack("<HBBBB", _AptMsgMoveHomed.MESSAGE_ID, 1, 0, 0x01, 0x50)
        self._transport_mock._safe_serial.in_waiting = 0  # Header is not yet available.
        self._transport_mock.read.return_value = header

        with unittest.mock.patch("qmi.instruments.thorlabs.apt_protocol.time.sleep") as mock_sleep:
            msg = self._protocol.read_message(timeout=0.3)

        mock_sleep.assert_not_called()
        self._transport_mock.read.assert_called_once_with(nbytes=AptProtocol.HEADER_SIZE_BYTES, timeout=0.3)
        self.assertIsInstance(msg, _AptMsgMoveHomed)


class TestAptProtocolSendMessage(unittest.TestCase):
    """Tests for `AptProtocol.send_message`, see issue #271."""

    def setUp(self):
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._transport_mock._safe_serial.out_waiting = 0
        self._protocol = AptProtocol(self._transport_mock)
        self._new_msg = self._protocol.create(_AptMsgMoveHome, chan_ident=1)

    def test_send_message_without_pending_data(self):
        """If nothing is buffered, `send_message` writes immediately without reading anything."""
        self._transport_mock._safe_serial.in_waiting = 0

        self._protocol.send_message(self._new_msg)

        self._transport_mock.read.assert_not_called()
        self._transport_mock.discard_read.assert_not_called()
        self._transport_mock.write.assert_called_once_with(bytes(self._new_msg))

    def test_send_message_completes_partial_pending_message_before_discarding(self):
        """A message that is only partially buffered must be read out as a whole message (not discarded as raw
        bytes), so that its tail is not left behind to be misread as the header of the next reply."""
        pending = self._protocol.create(
            _AptMsgMoveCompleted, chan_ident=1, position=0, velocity=0, reserved=0, status_bits=0
        )
        pending_bytes = bytes(pending)  # 20 bytes: a 6-byte header plus 14 bytes of data.
        self.assertEqual(20, len(pending_bytes))

        # Only part of the header has arrived so far; by the time it has been read in full, nothing remains.
        in_waiting_values = iter([4, 0])
        type(self._transport_mock._safe_serial).in_waiting = unittest.mock.PropertyMock(
            side_effect=lambda: next(in_waiting_values)
        )
        self._transport_mock.read.side_effect = [pending_bytes[:6], pending_bytes[6:]]

        self._protocol.send_message(self._new_msg)

        self._transport_mock.read.assert_has_calls([
            unittest.mock.call(nbytes=6, timeout=AptProtocol._PENDING_MESSAGE_TIMEOUT),
            unittest.mock.call(nbytes=14, timeout=0.050),
        ])
        self._transport_mock.discard_read.assert_not_called()
        self._transport_mock.write.assert_called_once_with(bytes(self._new_msg))

    def test_send_message_discards_unparseable_pending_data(self):
        """If the pending bytes cannot be completed into a full message in time, discard the whole buffer instead
        of leaving a half-consumed message behind."""
        self._transport_mock._safe_serial.in_waiting = 4  # Only part of the header has arrived, and never completes.
        self._transport_mock.read.side_effect = QMI_TimeoutException("Timeout after 4 bytes while expecting 6")

        self._protocol.send_message(self._new_msg)

        self._transport_mock.read.assert_called_once_with(nbytes=6, timeout=AptProtocol._PENDING_MESSAGE_TIMEOUT)
        self._transport_mock.discard_read.assert_called_once()
        self._transport_mock.write.assert_called_once_with(bytes(self._new_msg))


if __name__ == "__main__":
    unittest.main()
