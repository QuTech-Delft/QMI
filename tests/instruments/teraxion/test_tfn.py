"""Unit-tests for Teraxion TFN."""
from datetime import datetime
import unittest
from unittest.mock import call, patch

from qmi.core.context import QMI_Context
from qmi.instruments.teraxion.tfn import Teraxion_TFN, Teraxion_TFNChannelPlan, Teraxion_TFNElement, Teraxion_TFNSettings, Teraxion_TFNStatus


class TestTeraxionTfn(unittest.TestCase):

    def setUp(self):
        qmi_context = unittest.mock.MagicMock(spec=QMI_Context)
        qmi_context.name = "mock_context"

        # Add patches
        with patch("qmi.instruments.teraxion.tfn.create_transport") as self._transport_mock:
            self.tfn = Teraxion_TFN(qmi_context, "teraxion_tfn", "")
        self.tfn.open()

    def tearDown(self) -> None:
        self.tfn.close()

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_firmware_version_gets_firmware_version(self, ask_mock):
        """Test get firmware version, gets firmware version."""
        # Arrange
        expected_version = "1.0"
        expected_command = "S600fP S6106P"
        ask_mock.return_value = "001000000100"

        # Act
        ver = self.tfn.get_firmware_version()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(ver, expected_version)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_manufacturer_name_gets_manufacturer_name(self, ask_mock):
        """Test get manufacturer name, gets manufacturer name."""
        # Arrange
        expected_manufacturer_name = "TeraXion"
        expected_command = "S600eP S61ffP"
        ask_mock.return_value = "001000005465726158696F6E00"

        # Act
        manufacturer_name = self.tfn.get_manufacturer_name()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(manufacturer_name, expected_manufacturer_name)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_model_number_gets_model_number(self, ask_mock):
        """Test get model number, gets model number."""
        # Arrange
        expected_model_number = "TFN-XXXX"
        expected_command = "S6027P S61ffP"
        ask_mock.return_value = "0010000054464E2D5858585800"

        # Act
        model_number = self.tfn.get_model_number()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(model_number, expected_model_number)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_serial_number_gets_serial_number(self, ask_mock):
        """Test get serial number, gets serial number."""
        # Arrange
        expected_serial_number = "Txxxxxx"
        expected_command = "S6029P S61ffP"
        ask_mock.return_value = "001000005478787878787800"

        # Act
        serial_number = self.tfn.get_serial_number()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(serial_number, expected_serial_number)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_idn_sends_get_idn_command(self, ask_mock):
        """Test get idn, sends gets idn command."""
        # Arrange
        expected_vendor = "TeraXion"
        expected_model_number = "TFN-XXXX"
        expected_serial_number = "Txxxxxx"
        expected_version = "1.0"
        expected_manufactuer_name_command = "S600eP S61ffP"
        expected_model_number_command = "S6027P S61ffP"
        expected_serial_number_command = "S6029P S61ffP"
        expected_firmware_version_command = "S600fP S6106P"

        ask_mock.side_effect = ["001000005465726158696F6E00", "0010000054464E2D5858585800", "001000005478787878787800", "001000000100"]

        # Act
        idn = self.tfn.get_idn()

        # Assert
        ask_mock.assert_has_calls([call(expected_manufactuer_name_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT),
                                  call(expected_model_number_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT),
                                  call(expected_serial_number_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT),
                                  call(expected_firmware_version_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)])
        self.assertEqual(idn.vendor, expected_vendor)
        self.assertEqual(idn.model, expected_model_number)
        self.assertEqual(idn.serial, expected_serial_number)
        self.assertEqual(idn.version, expected_version)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_manufacturing_date_gets_manufacturing_date(self, ask_mock):
        """Test get manufacturing number, gets manufacturing date."""
        # Arrange
        expected_date = datetime.strptime("20231120", "%Y%m%d").date()
        expected_command = "S602bP S61ffP"
        ask_mock.return_value = "00100000323032333131323000"

        # Act
        manufacturing_date = self.tfn.get_manufacturing_date()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(manufacturing_date, expected_date)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_status_gets_status(self, ask_mock):
        """Test get status, gets status."""
        # Arrange
        expected_status = Teraxion_TFNStatus(False, False, False, True, False, False, False, False, False, False, False, False, False, False)
        expected_command = "S6000P S6104P"
        ask_mock.return_value = "00100000"

        # Act
        status = self.tfn.get_status()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(status, expected_status)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.write")
    def test_reset_resets(self, write_mock):
        """Test reset, resets."""
        # Arrange
        expected_command = "S6028P"

        # Act
        self.tfn.reset()

        # Assert
        write_mock.assert_called_once_with(expected_command)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_set_frequency_sets_frequency(self, ask_mock):
        """Test set frequency, sets frequency."""
        # Arrange
        set_freq = 192400
        expected_command = "S602e483be400P L000a S6108P"

        # Act
        self.tfn.set_frequency(set_freq)

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_frequency_gets_frequency(self, ask_mock):
        """Test get frequency, gets frequency."""
        # Arrange
        expected_freq = 192400
        expected_command = "S602fP S6108P"
        ask_mock.return_value = "00100000483be400"

        # Act
        freq = self.tfn.get_frequency()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(freq, expected_freq)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_rtd_temp_given_element_gets_rtd_temp(self, ask_mock):
        """Test get RTD temperature given the element, gets the RTD temperature."""
        # Arrange
        expected_temp = 8918
        expected_command = "S601704P S6106P"
        ask_mock.return_value = "0010000022D6"

        # Act
        temp = self.tfn.get_rtd_temperature(Teraxion_TFNElement.CASE)

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(temp, expected_temp)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_enable_device_sends_enable_device_command(self, ask_mock):
        """Test enable device, sends enable device command."""
        # Arrange
        expected_command = "S601eP L000a S6104P"

        # Act
        self.tfn.enable_device()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_disable_device_sends_disable_device_command(self, ask_mock):
        """Test disable device, sends disable device command."""
        # Arrange
        expected_command = "S601fP L000a S6104P"

        # Act
        self.tfn.disable_device()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_enable_tecs_on_startup_sends_set_startup_byte_command(self, ask_mock):
        """Test enable tecs on startup, sends startup byte command."""
        # Arrange
        expected_command = "S603401P L000a S6105P"

        # Act
        self.tfn.enable_tecs_on_startup()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_disable_tecs_on_startup_sends_set_startup_byte_command(self, ask_mock):
        """Test disable tecs on startup, sends startup byte command."""
        # Arrange
        expected_command = "S603400P L000a S6105P"

        # Act
        self.tfn.disable_tecs_on_startup()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_startup_byte_sends_get_startup_byte_command(self, ask_mock):
        """Test get startup byte, gets startup byte."""
        # Arrange
        expected_command = "S6035P S6105P"
        ask_mock.return_value = "0010000001"

        # Act
        startup_byte = self.tfn.get_startup_byte()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertTrue(startup_byte)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_nominal_settings_gets_nominal_settings(self, ask_mock):
        """Test get nominal settings, gets nominal settings."""
        # Arrange
        expected_settings = Teraxion_TFNSettings(192400, 0)
        expected_command = "S6037P S610cP"
        ask_mock.return_value = "00100000483be40000000000"

        # Act
        settings = self.tfn.get_nominal_settings()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(settings, expected_settings)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_save_nominal_settings_sends_save_nominal_settings_command(self, ask_mock):
        """Test save nominal settings, saves nominal settings."""
        # Arrange
        expected_command = "S6036P L000a S610cP"

        # Act
        self.tfn.save_nominal_settings()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_channel_plan_gets_channel_plan(self, ask_mock):
        """Test get channel plan, gets channel plan."""
        # Arrange
        expected_channel_plan = Teraxion_TFNChannelPlan(193420, 193370, 1)
        expected_command = "S603bP S6110P"
        ask_mock.return_value = "00100000483CE300483CD68000000001"

        # Act
        channel_plan = self.tfn.get_channel_plan()

        # Assert
        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(channel_plan, expected_channel_plan)

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.write")
    def test_set_i2c_address_sends_set_i2c_address_command(self, write_mock):
        """Test set i2c address, sends set i2c address command."""
        # Arrange
        expected_command = "S60420060P"

        # Act
        self.tfn.set_i2c_address(96)

        # Assert
        write_mock.assert_called_once_with(expected_command)