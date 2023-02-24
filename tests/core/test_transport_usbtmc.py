import sys, os
import unittest.mock
sys.modules["usb.core"] = unittest.mock.Mock()
sys.modules["usb.core.find"] = unittest.mock.Mock()

from qmi.core.transport_usbtmc_pyusb import QMI_PyUsbTmcTransport
from qmi.core.exceptions import QMI_TimeoutException
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
    def test_read(self, mock):
        expected = "0"

        mock().read_raw.return_value = expected
        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        ret = dev.read(1, timeout=0.001)
        dev.close()

        mock().read_raw.assert_called_once()
        self.assertEqual(ret, expected)

    @unittest.mock.patch("qmi.core.usbtmc.Instrument")
    def test_write(self, mock):
        data = bytes("data".encode())

        dev = QMI_PyUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.write(data)
        dev.close()

        mock().write_raw.assert_called_once_with(data)


class TestQmiVisaUsbTmcTransport(unittest.TestCase):
    """Test QMI_VisaUsbTmcTransport."""
    def test_create_object(self):
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        self.assertIsNotNone(dev)

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_open_close(self, mock):
        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.close()

        mock.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager.open_resource")
    def test_read(self, mock):
        expected = "0"

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
    def test_write(self, mock):
        data = bytes("data".encode())

        dev = QMI_VisaUsbTmcTransport(0x1234, 0x5678, "90")
        dev.open()
        dev.write(data)
        dev.close()

        mock().write_raw.assert_called_once_with(data)


if __name__ == "__main__":
    unittest.main()
