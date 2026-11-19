import sys
import unittest.mock

import usb.core

sys.modules["usb.core"] = unittest.mock.Mock()
sys.modules["usb.core.find"] = unittest.mock.Mock()

from qmi.core.transport_usbtmc_pyusb import QMI_PyUsbTmcTransport
from qmi.core.exceptions import QMI_TimeoutException, QMI_EndOfInputException
import pyvisa.errors
from qmi.core.transport_usbtmc_visa import QMI_VisaUsbTmcTransport


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

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_list_resources(self, mock):
        """Test static method list_resources. Make sure two correct resources are formatted and one
        incorrect resource is ignored."""
        # correct resources
        vendorid_1 = 0x0699
        productid_1 = 0x3000
        serialnr_1 = "XYZ"
        vendorid_3 = 0xbebe
        productid_3 = 0xcafe
        serialnr_3 = "ABC"
        # VISA-style resource strings as returned by pyvisa.ResourceManager.list_resources(). Resource "2" is
        # malformed and should be ignored.
        visa_resources = [
            f"USB1::0x{vendorid_1:04x}::0x{productid_1:04x}::{serialnr_1}::INSTR",
            "USB2::x0699::x3000::IJK::INSTR",
            f"USBTMC::0x{vendorid_3:04x}::0x{productid_3:04x}::{serialnr_3}::INSTR",
        ]
        mock().list_resources.return_value = visa_resources
        # QMI-style transport strings.
        qmi_str_1 = f"usbtmc:vendorid=0x{vendorid_1:04x}:productid=0x{productid_1:04x}:serialnr={serialnr_1}"
        qmi_str_3 = f"usbtmc:vendorid=0x{vendorid_3:04x}:productid=0x{productid_3:04x}:serialnr={serialnr_3}"
        expected_output = [qmi_str_1, qmi_str_3]
        # Act
        output = QMI_VisaUsbTmcTransport.list_resources()
        # Assert
        self.assertListEqual(expected_output, output)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_open_close(self, mock):
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.close()

        mock().open_resource.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_write(self, mock):
        data = bytes("data".encode())

        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.write(data)
        dev.close()

        mock().open_resource().write_raw.assert_called_once_with(data)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read(self, mock):
        expected = b"0"

        mock().open_resource().read_raw.return_value = expected
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
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
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
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
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
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

        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read_until_timeout(10, timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_discard_read(self, mock):
        """See that discard_read empties the read buffer, and
        it tries to read whatever is in the incoming instrument buffer.
        """
        expected = b"01234"

        mock().open_resource().read_raw.return_value = expected
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        # Discard read should empty the read buffer and read instrument data
        dev.discard_read()
        dev.close()

        mock().open_resource().read_raw.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_discard_read_does_not_except(self, mock):
        """See that discard_read passes QMI_TimeoutException if read buffer and incoming instrument buffer are empty."""
        timeout_error = pyvisa.errors.VI_ERROR_TMO
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(timeout_error)
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.discard_read()
        dev.close()

        mock().open_resource().read_raw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
