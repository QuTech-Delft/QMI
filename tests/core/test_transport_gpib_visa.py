import sys
import unittest.mock

import pyvisa.errors

sys.modules["usb.core"] = unittest.mock.Mock()
sys.modules["usb.core.find"] = unittest.mock.Mock()

from qmi.core.exceptions import QMI_TimeoutException
with unittest.mock.patch("sys.platform", "win32"):
    from qmi.core.transport_gpib_visa import QMI_VisaGpibTransport


class TestQmiVisaGpibTransport(unittest.TestCase):
    """Test QMI_VisaGpibTransport."""

    def test_create_default_object(self):
        """Test instantiating the class with default values."""
        primary_addr = 1
        default_secondary_addr = None
        default_board = None
        default_timeout = 30
        expected_dev_str = f"QMI_VisaGpibTransport GPIB::{primary_addr}::INSTR"

        dev = QMI_VisaGpibTransport(primary_addr)
        dev_str = str(dev)

        self.assertIsNotNone(dev)
        self.assertEqual(expected_dev_str, dev_str)
        self.assertEqual(primary_addr, dev._primary_addr)
        self.assertEqual(default_board, dev._board)
        self.assertEqual(default_secondary_addr, dev._secondary_addr)
        self.assertEqual(default_timeout, dev._connect_timeout)

    def test_create_object(self):
        """Test instantiating the class with custom values."""
        primary_addr = 1
        board = 0
        secondnr = 2
        timeout = 0.1
        expected_dev_str = f"QMI_VisaGpibTransport GPIB{board}::{primary_addr}::{secondnr}::INSTR"

        dev = QMI_VisaGpibTransport(primary_addr, board=board, secondary_addr=secondnr, connect_timeout=timeout)
        dev_str = str(dev)

        self.assertIsNotNone(dev)
        self.assertEqual(expected_dev_str, dev_str)
        self.assertEqual(primary_addr, dev._primary_addr)
        self.assertEqual(board, dev._board)
        self.assertEqual(secondnr, dev._secondary_addr)
        self.assertEqual(timeout, dev._connect_timeout)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_open_close(self, mock):
        """Test opening and closing the instrument."""
        primary_nr = 1
        default_timeout = 30 * 1000
        terminations = '\n'
        dev = QMI_VisaGpibTransport(primary_nr)
        dev.open()
        dev.close()

        mock.assert_called_once_with()
        mock().open_resource.assert_called_once_with(
            f"GPIB::{primary_nr}::INSTR",
            open_timeout=default_timeout,
            write_termination=terminations,
            read_termination=terminations
        )

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_write(self, mock):
        """Test writing some data to the instrument."""
        data = bytes("data".encode())

        dev = QMI_VisaGpibTransport(1)
        dev.open()
        dev.write(data)
        dev.close()

        mock().open_resource().write_raw.assert_called_once_with(data)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read(self, mock):
        """Test reading something from the instrument."""
        expected = b"0"

        mock().open_resource().read_raw.return_value = expected
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        ret = dev.read(1, timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_raises_exception(self, mock):
        """A test to see that read raises QMI_TimeoutException """
        # Arrange
        timeout_error = pyvisa.errors.VI_ERROR_TMO
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(timeout_error)
        expected = QMI_TimeoutException(str(pyvisa.errors.VisaIOError(timeout_error)))
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        with self.assertRaises(QMI_TimeoutException) as exc:
            dev.read(1, timeout=0.001)

        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(repr(exc.exception), repr(expected))

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_until(self, mock):
        """This should forward the executions to read_until_timeout, so we test both in one go."""
        expected = b"01234"

        mock().open_resource().read_raw.return_value = expected
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        ret = dev.read_until(b"T3000", timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_until_timeout_does_not_raise_timeout_exception(self, mock):
        """This tests that read_until_timeout catches timeout exception and returns empty bytes."""
        timeout_error = pyvisa.errors.VI_ERROR_TMO
        expected = b""
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(timeout_error)

        dev = QMI_VisaGpibTransport(1)
        dev.open()
        ret = dev.read_until_timeout(10, timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_discard_read(self, mock):
        """See that discard_read tries to read whatever is in the incoming instrument buffer.
        """
        expected = b"01234"

        mock().open_resource().read_raw.return_value = expected
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        # Read should empty the read buffer
        dev.discard_read()

        dev.close()

        mock().open_resource().read_raw.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_discard_read_does_not_except(self, mock):
        """See that discard_read passes QMI_TimeoutException if read buffer and incoming instrument buffer are empty."""
        timeout_error = pyvisa.errors.VI_ERROR_TMO
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(timeout_error)
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        dev.discard_read()
        dev.close()

        mock().open_resource().read_raw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
