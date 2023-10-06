import sys
import unittest.mock
sys.modules["usb.core"] = unittest.mock.Mock()
sys.modules["usb.core.find"] = unittest.mock.Mock()

from qmi.core.exceptions import QMI_TimeoutException, QMI_EndOfInputException
# For not causing an error by missing pyvisa library in the pipeline tests, we mock also the pyvisa existence
import tests.core.pyvisa_stub
sys.modules["pyvisa"] = tests.core.pyvisa_stub
sys.modules["pyvisa.errors"] = tests.core.pyvisa_stub.errors
from qmi.core.transport_gpib_visa import QMI_VisaGpibTransport
patcher = unittest.mock.patch("pyvisa.errors")


class TestQmiVisaGpibTransport(unittest.TestCase):
    """Test QMI_VisaGpibTransport."""

    def test_create_default_object(self):
        """Test instantiating the class with default values."""
        devicenr = 1
        default_if_id = ""
        default_timeout = 30

        dev = QMI_VisaGpibTransport(devicenr)

        self.assertIsNotNone(dev)
        self.assertEqual(devicenr, dev._devicenr)
        self.assertEqual(default_if_id, dev._if_id)
        self.assertIsNone(dev._secondnr)
        self.assertEqual(default_timeout, dev._timeout)

    def test_create_object(self):
        """Test instantiating the class with custom values."""
        devicenr = 1
        if_id = 0
        secondnr = 2
        timeout = 0.1

        dev = QMI_VisaGpibTransport(devicenr, if_id=if_id, secondnr=secondnr, timeout=timeout)

        self.assertIsNotNone(dev)
        self.assertEqual(devicenr, dev._devicenr)
        self.assertEqual(if_id, dev._if_id)
        self.assertEqual(secondnr, dev._secondnr)
        self.assertEqual(timeout, dev._timeout)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_open_close(self, mock):
        """Test opening and closing the instrument."""
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        dev.close()

        mock.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_write(self, mock):
        """Test writing some data to the instrument."""
        data = bytes("data".encode())

        dev = QMI_VisaGpibTransport(1)
        dev.open()
        dev.write(data)
        dev.close()

        mock().write_raw.assert_called_once_with(data)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_read(self, mock):
        """Test reading something from the instrument."""
        expected = b"0"

        mock().read_raw.return_value = expected
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        ret = dev.read(1, timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    @unittest.mock.patch("pyvisa.errors.VisaIOError", new_callable=lambda: tests.core.pyvisa_stub.VisaIOError)
    def test_read_raises_exception(self, exc_mock, mock):
        """A test to see that read raises QMI_TimeoutException """
        # Arrange
        timeout_error = tests.core.pyvisa_stub.VI_ERROR_TMO
        mock().read_raw.side_effect = exc_mock(timeout_error)
        expected = QMI_TimeoutException(str(tests.core.pyvisa_stub.VisaIOError(timeout_error)))
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        with self.assertRaises(QMI_TimeoutException) as exc:
            dev.read(1, timeout=0.001)

        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(repr(exc.exception), repr(expected))

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_read_until(self, mock):
        """This should forward the executions to read_until_timeout, so we test both in one go."""
        expected = b"01234"

        mock().read_raw.return_value = expected
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        ret = dev.read_until(b"T3000", timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_discard_read(self, mock):
        """See that discard_read either empties the read buffer, or if it is already empty,
        it tries to read whatever is in the incoming instrument buffer.
        """
        expected = b"01234"

        mock().read_raw.return_value = expected
        dev = QMI_VisaGpibTransport(1)
        dev._read_buffer = b"somestuff"
        dev.open()
        # First read should empty the read buffer
        dev.discard_read()

        self.assertEqual(bytes(), dev._read_buffer)
        mock().read_raw.assert_not_called()

        # Second read should clear up incoming readout
        dev.discard_read()
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(bytes(), dev._read_buffer)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_discard_read_does_not_except(self, mock):
        """See that discard_read does not except even if read buffer and incoming instrument buffer are empty."""
        dev = QMI_VisaGpibTransport(1)
        dev.open()
        dev.discard_read()
        dev.close()

        mock().read_raw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
