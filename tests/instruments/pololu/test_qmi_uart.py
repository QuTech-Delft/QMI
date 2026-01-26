from queue import Empty
import unittest
from unittest.mock import Mock, patch


class UART_stub:

    class _Uart:

        class Nova:

            class RxdQueue:
                block_count = 0
                def get(self, block):
                    if self.block_count:
                        raise Empty()

                    self.block_count += 1
                    return b"\r"

            def __init__(self):
                self._rxdQueue = self.RxdQueue()

        def __init__(self):
            self._nova = self.Nova()

    def __init__(self, *args, **kwargs):
        self._uart = self._Uart()
        self.deinit_called = False
        self.write_buffer = bytearray()
        self.read_buffer = bytearray()

    def deinit(self):
        self.deinit_called = True

    def write(self, data: bytes):
        self.write_buffer += bytearray(data)

    def readinto(self, buf: bytearray, nbytes: int):
        for _ in range(nbytes):
            buf += bytearray(int(f"{self.read_buffer.pop(0)}").to_bytes())

        return buf


busio_mock = Mock()
busio_mock.UART = UART_stub
with patch.dict("sys.modules", {"busio": busio_mock}) as sys_patch:
    from qmi.instruments.pololu.qmi_uart import QMI_Uart


class QmiUartTestCase(unittest.TestCase):
    def setUp(self):
        self.qmi_uart = QMI_Uart()

    def test_open_close(self):
        """Simple open-close test."""
        self.qmi_uart.open()

        self.assertTrue(self.qmi_uart._is_open)
        self.assertFalse(self.qmi_uart.deinit_called)

        self.qmi_uart.close()

        self.assertFalse(self.qmi_uart._is_open)
        self.assertTrue(self.qmi_uart.deinit_called)

    def test_write(self):
        """Test write function."""
        data = b"01234"
        expected_write = bytearray(data)
        self.qmi_uart.write(data)
        self.qmi_uart.close()

        self.assertEqual(expected_write, self.qmi_uart.write_buffer)

    def test_read_until_timeout(self):
        """Test read_until_timeout function."""
        expected_read = b"01234"
        data = bytearray(expected_read)
        self.qmi_uart.read_buffer = data

        # First read two bytes
        retval = self.qmi_uart.read_until_timeout(2, 1.0)
        self.assertEqual(expected_read[:2], retval)
        # Then try to read 3 bytes, where we are limited by timeout and batch size, and get back only 2.
        retval_2 = self.qmi_uart.read_until_timeout(3, 0.0)
        self.assertEqual(expected_read[2:4], retval_2)
        # Replenish buffer
        self.qmi_uart.read_buffer = data

    def test_read_until_timeout_batch_size_check(self):
        """Test read_until_timeout function with read 5 bytes,
        which triggers the check on remaining buffer size vs batch size.
        """
        expected_read = b"01234"
        data = bytearray(expected_read)
        self.qmi_uart.read_buffer = data

        retval = self.qmi_uart.read_until_timeout(5, 1.0)
        self.assertEqual(expected_read, retval)

        self.qmi_uart.close()

    def test_discard_read(self):
        """Test discard_read to see it reads from "queue"."""
        self.assertEqual(0, self.qmi_uart._uart._nova._rxdQueue.block_count)
        self.qmi_uart.discard_read()
        self.assertEqual(1, self.qmi_uart._uart._nova._rxdQueue.block_count)


if __name__ == '__main__':
    unittest.main()
