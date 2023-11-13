import sys
import unittest.mock

import usb.core

sys.modules["usb.core"] = unittest.mock.Mock()
sys.modules["usb.core.find"] = unittest.mock.Mock()

from qmi.core.transport_usbtmc_pyusb import QMI_PyUsbTmcTransport
from qmi.core.exceptions import QMI_TimeoutException, QMI_EndOfInputException
# For not causing an error by missing pyvisa library in the pipeline tests, we mock also the pyvisa existence
import tests.core.pyvisa_stub
sys.modules["pyvisa"] = tests.core.pyvisa_stub
sys.modules["pyvisa.errors"] = tests.core.pyvisa_stub.errors
from qmi.core.transport_usbtmc_visa import QMI_VisaUsbTmcTransport
patcher = unittest.mock.patch("pyvisa.errors")


class TestQmiPyUsbTmcTransport(unittest.TestCase):
    """Test QMI_PyUsbTmcTransport."""
    def test_create_object(self):
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.vendorid, int(0x1234))
        self.assertEqual(dev.productid, int(0x5678))
        self.assertEqual(dev.serialnr, "90")

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_open_close(self, mock):
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.close()

        mock().open.assert_called_once()
        mock().close.assert_called_once()

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_write(self, mock):
        data = b"data"

        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.write(data)
        dev.close()

        mock().write_raw.assert_called_once_with(data)

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_read(self, mock):
        """Test read method works."""
        expected = b"0"
        mock().read_raw.return_value = expected

        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read(1, timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_read_raises_exception(self, mock):
        """A test to see that read raises QMI_EndOfInputException."""
        # Arrange
        nbytes = 2
        buf = b"0"
        mock().read_raw.return_value = buf

        expected = f"The read message did not contain expected bytes of data ({len(buf)} != {nbytes}."
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        with self.assertRaises(QMI_EndOfInputException) as exc:
            dev.read(nbytes, timeout=0.001)

        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(str(exc.exception), str(expected))

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_read_until(self, mock):
        """This should forward the executions to read_until_timeout, so we test both in one go."""
        expected = b"01234"

        mock().read_raw.return_value = expected
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read_until(b"T3000", timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_discard_read_until_timeout_does_not_raise_timeout_exception(self, mock):
        """This tests that read_until_timeout catches timeout exception and returns empty bytes."""
        usberror = usb.core.USBError("Timeout!")
        usberror.errno = 110  # Set for Timeout
        expected = b""
        mock().read_raw.side_effect = [usberror]

        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read_until_timeout(10, timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_discard_read(self, mock):
        """See that discard_read tries to read whatever is in the incoming instrument buffer."""
        expected = b"01234"

        mock().read_raw.return_value = expected
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        # Discard read should empty the read buffer and discard instrument readout.
        dev.discard_read()
        dev.close()

        mock().read_raw.assert_called_once()

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_discard_read_does_not_except(self, mock):
        """See that discard_read passes QMI_TimeoutException if incoming instrument buffer is empty."""
        usberror = usb.core.USBError("Timeout!")
        usberror.errno = 110  # Set for Timeout
        mock().read_raw.side_effect = [usberror]
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.discard_read()
        dev.close()

        mock().read_raw.assert_called_once()


class TestQmiVisaUsbTmcTransport(unittest.TestCase):
    """Test QMI_VisaUsbTmcTransport."""
    def test_create_object(self):
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        self.assertIsNotNone(dev)

    def test_list_resources(self):
        """Test static method list_resources. Make sure two correct resources are formatted and one
        incorrect resource is ignored."""
        # correct resources
        vendorid_1 = tests.core.pyvisa_stub.vendorid_1
        productid_1 = tests.core.pyvisa_stub.productid_1
        serialnr_1 = tests.core.pyvisa_stub.serialnr_1
        vendorid_3 = tests.core.pyvisa_stub.vendorid_3
        productid_3 = tests.core.pyvisa_stub.productid_3
        serialnr_3 = tests.core.pyvisa_stub.serialnr_3
        # QMI-style transport strings. Resource "2" should be invalid and not included.
        qmi_str_1 = f"usbtmc:vendorid=0x{vendorid_1:04x}:productid=0x{productid_1:04x}:serialnr={serialnr_1}"
        qmi_str_3 = f"usbtmc:vendorid=0x{vendorid_3:04x}:productid=0x{productid_3:04x}:serialnr={serialnr_3}"
        expected_output = [qmi_str_1, qmi_str_3]
        # Act
        output = QMI_VisaUsbTmcTransport.list_resources()
        # Assert
        self.assertListEqual(expected_output, output)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_open_close(self, mock):
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.close()

        mock.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_write(self, mock):
        data = bytes("data".encode())

        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.write(data)
        dev.close()

        mock().write_raw.assert_called_once_with(data)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_read(self, mock):
        expected = b"0"

        mock().read_raw.return_value = expected
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
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
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
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
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read_until(b"T3000", timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    @unittest.mock.patch("pyvisa.errors.VisaIOError", new_callable=lambda: tests.core.pyvisa_stub.VisaIOError)
    def test_read_until_timeout_does_not_raise_timeout_exception(self, exc_mock, mock):
        """This tests that read_until_timeout catches timeout exception and returns empty bytes."""
        timeout_error = tests.core.pyvisa_stub.VI_ERROR_TMO
        expected = b""
        mock().read_raw.side_effect = exc_mock(timeout_error)

        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read_until_timeout(10, timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_discard_read(self, mock):
        """See that discard_read empties the read buffer, and
        it tries to read whatever is in the incoming instrument buffer.
        """
        expected = b"01234"

        mock().read_raw.return_value = expected
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        # Discard read should empty the read buffer and read instrument data
        dev.discard_read()
        dev.close()

        mock().read_raw.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    @unittest.mock.patch("pyvisa.errors.VisaIOError", new_callable=lambda: tests.core.pyvisa_stub.VisaIOError)
    def test_discard_read_does_not_except(self, exc_mock, mock):
        """See that discard_read passes QMI_TimeoutException if read buffer and incoming instrument buffer are empty."""
        timeout_error = tests.core.pyvisa_stub.VI_ERROR_TMO
        mock().read_raw.side_effect = exc_mock(timeout_error)
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.discard_read()
        dev.close()

        mock().read_raw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
