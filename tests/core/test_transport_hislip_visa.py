"""Unit tests for qmi.core.transport_hislip_visa.QMI_HislipTransport."""

import unittest.mock

import pyvisa.errors

from qmi.core.exceptions import (
    QMI_EndOfInputException, QMI_InstrumentException, QMI_TimeoutException, QMI_TransportDescriptorException
)
from qmi.core.transport_hislip_visa import DEFAULT_HISLIP_PORT, DEFAULT_HISLIP_SUB_ADDRESS, QMI_HislipTransport


class TestQmiHislipTransportInit(unittest.TestCase):
    """Test QMI_HislipTransport instantiation and descriptor validation."""

    def test_create_default_object(self):
        """Test instantiating the class with default sub-address and port."""
        ip_address = "192.168.1.10"
        expected_visa_resource = f"TCPIP::{ip_address}::{DEFAULT_HISLIP_SUB_ADDRESS},{DEFAULT_HISLIP_PORT}::INSTR"

        dev = QMI_HislipTransport(ip_address)

        self.assertEqual(ip_address, dev._ip_address)
        self.assertEqual(DEFAULT_HISLIP_SUB_ADDRESS, dev._sub_address)
        self.assertEqual(DEFAULT_HISLIP_PORT, dev._port)
        self.assertEqual(expected_visa_resource, dev._visa_resource)
        self.assertEqual(f"QMI_HislipTransport {expected_visa_resource}", str(dev))

    def test_create_object(self):
        """Test instantiating the class with a custom sub-address and port."""
        ip_address = "10.0.0.5"
        sub_address = "hislip1"
        port = 5025
        expected_visa_resource = f"TCPIP::{ip_address}::{sub_address},{port}::INSTR"

        dev = QMI_HislipTransport(ip_address, sub_address=sub_address, port=port)

        self.assertEqual(ip_address, dev._ip_address)
        self.assertEqual(sub_address, dev._sub_address)
        self.assertEqual(port, dev._port)
        self.assertEqual(expected_visa_resource, dev._visa_resource)

    def test_invalid_host_raises_exception(self):
        """Test that an invalid IP address/host name is rejected."""
        with self.assertRaises(QMI_TransportDescriptorException):
            QMI_HislipTransport("invalid_hostname")

    def test_invalid_port_raises_exception(self):
        """Test that an out-of-range port number is rejected."""
        with self.assertRaises(QMI_TransportDescriptorException):
            QMI_HislipTransport("192.168.1.10", port=0)

        with self.assertRaises(QMI_TransportDescriptorException):
            QMI_HislipTransport("192.168.1.10", port=100000)


class TestQmiHislipTransportMethods(unittest.TestCase):
    """Test QMI_HislipTransport methods, with the PyVISA resource manager mocked out."""

    def setUp(self):
        self.ip_address = "192.168.1.10"

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_open_close(self, mock):
        """Test opening and closing the instrument."""
        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.close()

        mock.assert_called_once_with()
        mock().open_resource.assert_called_once_with(dev._visa_resource)
        mock().open_resource().close.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_open_raises_instrument_exception(self, mock):
        """Test that a PyVISA I/O error while opening is translated to a QMI_InstrumentException."""
        mock().open_resource.side_effect = pyvisa.errors.VisaIOError(pyvisa.errors.VI_ERROR_TMO)
        dev = QMI_HislipTransport(self.ip_address)

        with self.assertRaises(QMI_InstrumentException):
            dev.open()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_write(self, mock):
        """Test writing some data to the instrument."""
        data = b"data"

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.write(data)
        dev.close()

        mock().open_resource().write_raw.assert_called_once_with(data)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read(self, mock):
        """Test reading the expected number of bytes from the instrument."""
        expected = b"0"
        mock().open_resource().read_raw.return_value = expected

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        ret = dev.read(1, timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(expected, ret)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_wrong_length_raises_exception(self, mock):
        """Test that receiving an unexpected number of bytes raises QMI_EndOfInputException."""
        nbytes = 2
        buf = b"0"
        mock().open_resource().read_raw.return_value = buf

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        with self.assertRaises(QMI_EndOfInputException):
            dev.read(nbytes, timeout=0.001)

        dev.close()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_timeout_raises_exception(self, mock):
        """Test that a PyVISA timeout error is translated to QMI_TimeoutException."""
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(pyvisa.errors.VI_ERROR_TMO)

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        with self.assertRaises(QMI_TimeoutException):
            dev.read(1, timeout=0.001)

        dev.close()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_other_visa_error_raises_end_of_input_exception(self, mock):
        """Test that a non-timeout PyVISA I/O error is translated to QMI_EndOfInputException."""
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(pyvisa.errors.VI_ERROR_TMO - 1)

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        with self.assertRaises(QMI_EndOfInputException):
            dev.read(1, timeout=0.001)

        dev.close()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_until(self, mock):
        """This should forward the execution to read_until_timeout, so we test both in one go."""
        expected = b"01234"
        mock().open_resource().read_raw.return_value = expected

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        ret = dev.read_until(b"ignored_terminator", timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(expected, ret)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_until_timeout_does_not_raise_timeout_exception(self, mock):
        """Test that read_until_timeout catches a PyVISA timeout error and returns empty bytes."""
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(pyvisa.errors.VI_ERROR_TMO)

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        ret = dev.read_until_timeout(10, timeout=0.001)
        dev.close()

        mock().open_resource().read_raw.assert_called_once()
        self.assertEqual(b"", ret)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_discard_read(self, mock):
        """Test that discard_read tries to read whatever is in the incoming instrument buffer."""
        mock().open_resource().read_raw.return_value = b"01234"

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.discard_read()
        dev.close()

        mock().open_resource().read_raw.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_discard_read_does_not_except(self, mock):
        """Test that discard_read swallows a timeout when there is nothing to discard."""
        mock().open_resource().read_raw.side_effect = pyvisa.errors.VisaIOError(pyvisa.errors.VI_ERROR_TMO)

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.discard_read()
        dev.close()

        mock().open_resource().read_raw.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_query(self, mock):
        """Test that query() is delegated directly to the underlying PyVISA resource."""
        mock().open_resource().query.return_value = "response"

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        ret = dev.query("*IDN?")
        dev.close()

        mock().open_resource().query.assert_called_once_with("*IDN?")
        self.assertEqual("response", ret)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_clear(self, mock):
        """Test that clear() is delegated directly to the underlying PyVISA resource."""
        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.clear()
        dev.close()

        mock().open_resource().clear.assert_called_once()

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_read_stb(self, mock):
        """Test that read_stb() is delegated directly to the underlying PyVISA resource."""
        mock().open_resource().read_stb.return_value = 0x40

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        ret = dev.read_stb()
        dev.close()

        mock().open_resource().read_stb.assert_called_once()
        self.assertEqual(0x40, ret)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_timeout_none_is_forwarded_as_infinite(self, mock):
        """Test that a None timeout is forwarded to PyVISA as None, instead of e.g. zero."""
        mock().open_resource().read_raw.return_value = b"0"

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.read(1, timeout=None)
        dev.close()

        self.assertIsNone(mock().open_resource().timeout)

    @unittest.mock.patch("pyvisa.ResourceManager")
    def test_timeout_is_converted_to_milliseconds(self, mock):
        """Test that a finite timeout (in seconds) is converted to milliseconds for PyVISA."""
        mock().open_resource().read_raw.return_value = b"0"

        dev = QMI_HislipTransport(self.ip_address)
        dev.open()
        dev.read(1, timeout=0.25)
        dev.close()

        self.assertEqual(250, mock().open_resource().timeout)


if __name__ == "__main__":
    unittest.main()
