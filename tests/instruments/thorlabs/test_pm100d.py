import sys
import unittest, unittest.mock
sys.modules["usb.core"] = unittest.mock.Mock()
sys.modules["usb.core.find"] = unittest.mock.Mock()
from typing import NamedTuple
import time

from qmi.instruments.thorlabs import SensorInfo
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM10x
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.context import QMI_Context

UsbDevice = NamedTuple('UsbDeviceInfo',
                        [('idProduct', hex),
                         ('idVendor', hex),
                         ('serial_number', str)])


class TestThorlabsPM10x(unittest.TestCase):

    def setUp(self) -> None:
        qmi_context = unittest.mock.MagicMock(spec=QMI_Context)
        qmi_context.name = "mock_context"

        self.vendor_id = "0x1313"
        self.product = "PM16_120"
        self.product_id = "0x807b"
        self.serialnr = "P0024208"
        self.transport_id = f"usbtmc:vendorid={self.vendor_id}:productid={self.product_id}:serialnr={self.serialnr}"
        with unittest.mock.patch("qmi.instruments.thorlabs.pm100d.create_transport") as self._transport:
            self.thorlabs = Thorlabs_PM10x(qmi_context, "powermeter", self.transport_id)

    def test_open_close(self):
        self.thorlabs.open()
        self.thorlabs.close()
        self._transport.assert_called_once_with(self.transport_id)
        self.thorlabs._transport.open.assert_called_once_with()
        self.thorlabs._transport.close.assert_called_once_with()

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_idn(self, mock_read):
        """See that the get_idn method returns the expected QMI_InstrumentIdentification object"""
        mock_read.return_value = f"vendor={self.vendor_id},model={self.product},serial={self.serialnr},version=1.2.3"
        expected_vendor = f"vendor={self.vendor_id}"
        expected_model = f"model={self.product}"
        expected_serial = f"serial={self.serialnr}"
        expected_version = "version=1.2.3"

        self.thorlabs.open()
        msg = self.thorlabs.get_idn()
        self.thorlabs.close()

        self.assertEqual(msg.vendor, expected_vendor)
        self.assertEqual(msg.model, expected_model)
        self.assertEqual(msg.serial, expected_serial)
        self.assertEqual(msg.version, expected_version)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_idn_error(self, mock_read):
        """See that the get_idn method raises an exception at wrong number of returned words"""
        mock_read.return_value = f"vendor={self.vendor_id},model={self.product},serial={self.serialnr}"

        with self.assertRaises(QMI_InstrumentException):
            self.thorlabs.open()
            self.thorlabs.get_idn()

        self.thorlabs.close()

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_reset(self, mock_read):
        """See that the reset method calls 'ask' twice"""
        mock_read.side_effect = ["OK", '+0,"No error"']

        self.thorlabs.open()
        self.thorlabs.reset()
        self.thorlabs.close()

        self.assertEqual(2, mock_read.call_count)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_reset_error(self, mock_read):
        """See that the reset method raises an error at error check"""
        mock_read.side_effect = ["NOK", '+1,"Some error"']

        with self.assertRaises(QMI_InstrumentException):
            self.thorlabs.open()
            self.thorlabs.reset()

        self.thorlabs.close()

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_sensor_info(self, mock_read):
        """See that a SensorInfo object is returned."""
        expected = "SYST:SENS:IDN?"
        mock_read.return_value = f"name=powermeter,serial={self.serialnr},cal_msg=info,type=dunno,subtype=huh,3"

        self.thorlabs.open()
        msg = self.thorlabs.get_sensor_info()
        self.thorlabs.close()

        self.assertEqual(type(msg), SensorInfo)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_sensor_info_error(self, mock_read):
        """See that an exception is raised with wrong number of returned words"""
        mock_read.return_value = f"name=powermeter,serial={self.serialnr},cal_msg=info,type=dunno,3"

        with self.assertRaises(QMI_InstrumentException):
            self.thorlabs.open()
            self.thorlabs.get_sensor_info()

        self.thorlabs.close()

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_timestamped_power(self, mock_read):
        """See that a power reading with a timestamp is returned"""
        ref_timestamp = time.time()
        power = 100.0
        expected = "MEAS:POW?"
        mock_read.return_value = str(power)

        self.thorlabs.open()
        timestamp, msg = self.thorlabs.get_timestamped_power()
        self.thorlabs.close()

        self.assertEqual(msg, power)
        self.assertGreaterEqual(timestamp, ref_timestamp)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_power(self, mock_read):
        """Test that only power reading is returned"""
        power = 100.0
        expected = "MEAS:POW?"
        mock_read.return_value = str(power)

        self.thorlabs.open()
        msg = self.thorlabs.get_power()
        self.thorlabs.close()

        self.assertEqual(msg, power)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_range(self, mock_read):
        """Test that range value is returned."""
        range = 9.99
        expected = "SENS:POW:RANG?"
        mock_read.return_value = str(range)

        self.thorlabs.open()
        msg = self.thorlabs.get_range()
        self.thorlabs.close()

        self.assertEqual(msg, range)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_range_in_use(self, mock_read):
        """Test that range value is returned."""
        range = 9.99
        expected = "SENS:POW:RANG?"
        mock_read.return_value = str(range)

        self.thorlabs.open()
        msg = self.thorlabs.get_range_in_use()
        self.thorlabs.close()

        self.assertEqual(msg, range)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.write")
    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_set_range(self, mock_read, mock_write):
        """Test that range value can be set."""
        range = 10.0
        expected = f"SENS:POW:RANG {range}"
        mock_read.return_value = '+0,"No error"'

        self.thorlabs.open()
        self.thorlabs.set_range(range)
        self.thorlabs.close()

        mock_write.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_autorange(self, mock_read):
        """Test that autorange value is returned."""
        expected = "SENS:POW:RANG:AUTO?"
        mock_read.return_value = True

        self.thorlabs.open()
        msg = self.thorlabs.get_autorange()
        self.thorlabs.close()

        self.assertTrue(msg)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.write")
    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_set_autorange(self, mock_read, mock_write):
        """Test that autorange can be set."""
        autorange = False
        expected = "SENS:POW:RANG:AUTO {}".format(1 if autorange else 0)
        mock_read.return_value = '+0,"No error"'

        self.thorlabs.open()
        self.thorlabs.set_autorange(autorange)
        self.thorlabs.close()

        mock_write.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_wavelength(self, mock_read):
        """Test that wavelength value is returned."""
        wavelength = 564.7
        expected = "SENS:CORR:WAV?"
        mock_read.return_value = str(wavelength)

        self.thorlabs.open()
        msg = self.thorlabs.get_wavelength()
        self.thorlabs.close()

        self.assertEqual(msg, wavelength)
        mock_read.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.write")
    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_set_wavelength(self, mock_read, mock_write):
        """Test that range value is returned."""
        wavelength = 563.2
        expected = "SENS:CORR:WAV {}".format(wavelength)
        mock_read.return_value = '+0,"No error"'

        self.thorlabs.open()
        self.thorlabs.set_wavelength(wavelength)
        self.thorlabs.close()

        mock_write.assert_called_once_with(expected)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_current(self, mock_read):
        """Test that current value is returned."""
        current = 1.2
        expected = "MEAS:CURR?"
        mock_read.return_value = str(current)

        self.thorlabs.open()
        msg = self.thorlabs.get_current()
        self.thorlabs.close()

        self.assertEqual(msg, current)
        mock_read.assert_called_once_with(expected)


if __name__ == '__main__':
    unittest.main()
