import unittest
from unittest.mock import Mock, patch, call


class UART_stub:
    def __init__(self, *args, **kwargs):
        self.deinit_called = False
        self.write_buffer = bytearray()
        self.read_buffer = bytearray()

    def deinit(self):
        self.deinit_called = True

    def write(self, data: bytes):
        self.write_buffer += list(data)

    def readinto(self, buf: bytearray, nbytes: int):
        return buf + bytearray(int(f"{self.read_buffer.pop(0)}").to_bytes())

    def readline(self):
        try:
            return self.read_buffer
        finally:
            self.read_buffer = bytearray()


busio_mock = Mock()
busio_mock.UART = UART_stub
with patch.dict("sys.modules", {"busio": busio_mock}) as sys_patch:
    from qmi.instruments.pololu.qmi_uart import QMI_Uart


class QmiUartTestCase(unittest.TestCase):
    def setUp(self):
        self.uart_mock = Mock()

    def test_something(self):
        busio_mock.UART = self.uart_mock
        qmi_uart = QMI_Uart()
        qmi_uart.open()

        self.assertTrue(qmi_uart._is_open)

        qmi_uart.close()

        self.assertFalse(qmi_uart._is_open)

        busio_mock.UART.deinit.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
