import unittest
from unittest.mock import patch

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.instruments.anapico import Anapico_Apsin


class AnapicoApsinTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.transport_patch = patch("qmi.instruments.anapico.apsin.create_transport", autospec=create_transport)
        self.transport_patch.start()
        self.scpi_patch = patch("qmi.instruments.anapico.apsin.ScpiProtocol", autospec=ScpiProtocol)
        self.scpi_patch.start()
        self.apsin = Anapico_Apsin(QMI_Context("test_apsin"), name="apsin", transport="mock")

    def tearDown(self) -> None:
        self.transport_patch.stop()
        self.scpi_patch.stop()

    def test_open(self):
        """Test that the instrument can be opened."""
        # Act
        self.apsin.open()
        # Assert
        self.assertFalse(self.apsin._power_unit_configured)
        self.apsin._transport.open.assert_called_once_with()
        self.apsin._scpi_protocol.write.assert_called_once_with("*CLS")
        self.apsin._scpi_protocol.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_open_with_exception(self):
        """Force an exception at SCPI call and see it gets caught."""
        # Arrange
        self.apsin._scpi_protocol.write = Exception("Fail")
        # Act
        with self.assertRaises(Exception):
            self.apsin.open()

        self.apsin._transport.open.assert_called_once_with()
        self.apsin._transport.close.assert_called_once_with()

    def test_close(self):
        """Test the close call."""
        # Arrange
        self.apsin.open()
        # Act
        self.apsin.close()
        # Assert
        self.apsin._transport.close.assert_called_once_with()

    def test_reset(self):
        """Test the reset method."""
        # Arrange
        expected_write_calls = ["*CLS", "*RST"]
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.reset()
        # Assert
        self.apsin._scpi_protocol.ask.assert_called_with(expected_ask_call)
        self.assertEqual(2, self.apsin._scpi_protocol.ask.call_count)
        self.assertEqual(2, self.apsin._transport.discard_read.call_count)
        for call in expected_write_calls:
            self.apsin._scpi_protocol.write.assert_any_call(call)

    def test_check_error_excepts(self):
        """Test the case where a command returns an error and except in _check_error."""
        # Arrange
        error = "1: Some kind of error"
        expected_error_str = "Instrument returned error: {}".format(error)
        self.apsin._scpi_protocol.ask.side_effect = ["0, No error", error]
        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.apsin.reset()

        self.assertEqual(expected_error_str, str(exc.exception))

    def test_get_idn(self):
        """Test the get_idn returns an instrument identification."""
        # Arrange
        vendor = "Vendor"
        model = "Model"
        serial = "Serial"
        version = "Version"
        self.apsin._scpi_protocol.ask.return_value = f"{vendor},{model},{serial},{version}\r\n"
        # Act
        idn = self.apsin.get_idn()
        # assert
        self.apsin._scpi_protocol.ask.assert_called_once_with("*IDN?")
        self.assertEqual(vendor, idn.vendor)
        self.assertEqual(model, idn.model)
        self.assertEqual(serial, idn.serial)
        self.assertEqual(version, idn.version)

    def test_get_idn_excepts(self):
        """Test that the get_idn excepts if not 4 words are returned."""
        # Arrange
        self.apsin._scpi_protocol.ask.side_effect = ["A,B,C\r\n", "1, 2, 3, 4, 5\r\n"]
        # Act
        for _ in range(2):
            with self.assertRaises(QMI_InstrumentException) as exc:
                self.apsin.get_idn()

            self.assertIn("Unexpected response to *IDN?", str(exc.exception))

    def test_get_output_enabled(self):
        """Test the get_output_enabled function."""
        # Arrange
        expected_call = ":OUTP?"
        self.apsin._scpi_protocol.ask.return_value = "1"
        # Act
        enabled = self.apsin.get_output_enabled()
        # Assert
        self.assertTrue(enabled)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_ask_bool_excepts(self):
        """Test the _ask_bool function excepts at some invalid response with some command."""
        # Arrange
        expected_call = ":OUTP?"
        self.apsin._scpi_protocol.ask.return_value = "2"
        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.apsin.get_output_enabled()

        # Assert
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_output_enabled_enable(self):
        """Test set_output_enabled function with enabling."""
        # Arrange
        enable = True
        expected_write_call = f":OUTP {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_output_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_output_enabled_disable(self):
        """Test set_output_enabled function with disabling."""
        # Arrange
        enable = False
        expected_write_call = f":OUTP {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_output_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_frequency(self):
        """Test get_frequency function."""
        # Arrange
        expected_frequency = 123.45
        expected_ask_call = ":FREQ?"
        self.apsin._scpi_protocol.ask.return_value = f"{expected_frequency}\r\n"
        # Act
        freq = self.apsin.get_frequency()
        # Assert
        self.assertEqual(freq, expected_frequency)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_ask_float_excepts(self):
        """Test that the _ask_float excepts with invalid return value at some command."""
        # Arrange
        expected_ask_call = ":FREQ?"
        self.apsin._scpi_protocol.ask.return_value = f"off\r\n"
        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.apsin.get_frequency()

        # Assert
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_frequency(self):
        """Test set_frequency call."""
        # Arrange
        frequency = 432.15
        expected_write_call = f":FREQ {frequency}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_frequency(frequency)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_phase(self):
        # Arrange
        expected_phase = 3.141
        expected_ask_call = ":PHAS?"
        self.apsin._scpi_protocol.ask.return_value = f"{expected_phase}\r\n"
        # Act
        freq = self.apsin.get_phase()
        # Assert
        self.assertEqual(freq, expected_phase)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_phase(self):
        """Test set_phase call."""
        # Arrange
        phase = 0.0
        expected_write_call = f":PHAS {phase}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_phase(phase)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_power(self):
        """Test get_power method."""
        # Arrange
        self.apsin._power_unit_configured = True  # First emulate already configured power unit
        expected_power = 99.999
        expected_write_call = ":UNIT:POW DBM"
        expected_ask_calls = [":POW?", ":SYST:ERR:ALL?"]
        self.apsin._scpi_protocol.ask.side_effect = [f"{expected_power}", "0, No error", f"{expected_power}"]
        # Act
        power_1 = self.apsin.get_power()
        # Assert
        self.assertEqual(expected_power, power_1)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_calls[0])
        self.apsin._scpi_protocol.write.assert_not_called()
        # Re-arrange
        self.apsin._power_unit_configured = False  # Then force to call for starting power unit first.
        # Second Act
        power_2 = self.apsin.get_power()
        # Assert
        self.assertTrue(self.apsin._power_unit_configured)
        self.assertEqual(expected_power, power_2)
        self.apsin._scpi_protocol.ask.assert_any_call(expected_ask_calls[1])
        self.assertEqual(3, self.apsin._scpi_protocol.ask.call_count)
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)

    def test_set_power(self):
        # Arrange
        self.apsin._power_unit_configured = True  # Emulate already configured power unit
        power = 99.999
        expected_write_call = f":POW {power}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_power(power)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_pulsemod_enabled(self):
        """Test the get_pulsemod_enabled function."""
        # Arrange
        expected_call = ":PULM:STAT?"
        self.apsin._scpi_protocol.ask.return_value = "0"
        # Act
        enabled = self.apsin.get_pulsemod_enabled()
        # Assert
        self.assertFalse(enabled)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_pulsemod_enabled_enable(self):
        """Test set_pulsemod_enabled function with enabling."""
        # Arrange
        enable = True
        expected_write_call = f":PULM:STAT {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_pulsemod_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_pulsemod_enabled_disable(self):
        """Test set_pulsemod_enabled function with disabling."""
        # Arrange
        enable = False
        expected_write_call = f":PULM:STAT {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_pulsemod_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_pulsemod_ext_source_is_ext(self):
        """Test the get_pulsemod_ext_source function returning "EXT"."""
        # Arrange
        expected_call = ":PULM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "EXT"
        # Act
        ext_source = self.apsin.get_pulsemod_ext_source()
        # Assert
        self.assertTrue(ext_source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_pulsemod_ext_source_is_int(self):
        """Test the get_pulsemod_ext_source function returning "INT"."""
        # Arrange
        expected_call = ":PULM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "INT"
        # Act
        ext_source = self.apsin.get_pulsemod_ext_source()
        # Assert
        self.assertFalse(ext_source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_pulsemod_ext_source_excepts(self):
        """Test the get_pulsemod_ext_source function excepts on wrong response."""
        # Arrange
        expected_call = ":PULM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "OUT"
        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.apsin.get_pulsemod_ext_source()

        # Assert
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_pulsemod_ext_source_to_ext(self):
        """Test set_pulsemod_ext_source function with setting to "EXT"."""
        # Arrange
        ext = True
        expected_write_call = ":PULM:SOUR EXT"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_pulsemod_ext_source(ext)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_pulsemod_ext_source_to_int(self):
        """Test set_pulsemod_ext_source function with disabling."""
        # Arrange
        ext = False
        expected_write_call = ":PULM:SOUR INT"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_pulsemod_ext_source(ext)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_pulsemod_polarity_is_inv(self):
        """Test the get_pulsemod_polarity function returning "INV"."""
        # Arrange
        expected_call = ":PULM:POL?"
        self.apsin._scpi_protocol.ask.return_value = "INV"
        # Act
        polarity = self.apsin.get_pulsemod_polarity()
        # Assert
        self.assertTrue(polarity)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_pulsemod_polarity_is_int(self):
        """Test the get_pulsemod_polarity function returning "NORM"."""
        # Arrange
        expected_call = ":PULM:POL?"
        self.apsin._scpi_protocol.ask.return_value = "NORM"
        # Act
        polarity = self.apsin.get_pulsemod_polarity()
        # Assert
        self.assertFalse(polarity)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_pulsemod_polarity_excepts(self):
        """Test the get_pulsemod_polarity function excepts on wrong response."""
        # Arrange
        expected_call = ":PULM:POL?"
        self.apsin._scpi_protocol.ask.return_value = "0"
        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.apsin.get_pulsemod_polarity()

        # Assert
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_pulsemod_polarity_to_inv(self):
        """Test set_pulsemod_polarity function with setting to "INV"."""
        # Arrange
        inv = True
        expected_write_call = ":PULM:POL INV"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_pulsemod_polarity(inv)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_pulsemod_polarity_to_norm(self):
        """Test set_pulsemod_polarity function with disabling."""
        # Arrange
        inv = False
        expected_write_call = ":PULM:POL NORM"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_pulsemod_polarity(inv)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_am_enabled(self):
        """Test the get_am_enabled function."""
        # Arrange
        expected_call = ":AM:STAT?"
        self.apsin._scpi_protocol.ask.return_value = "ON"
        # Act
        enabled = self.apsin.get_am_enabled()
        # Assert
        self.assertTrue(enabled)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_am_enabled_enable(self):
        """Test set_am_enabled function with enabling."""
        # Arrange
        enable = True
        expected_write_call = f":AM:STAT {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_am_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_am_enabled_disable(self):
        """Test set_am_enabled function with disabling."""
        # Arrange
        enable = False
        expected_write_call = f":AM:STAT {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_am_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_am_ext_source_is_ext(self):
        """Test the get_am_ext_source function returning "EXT"."""
        # Arrange
        expected_call = ":AM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "EXT"
        # Act
        ext_source = self.apsin.get_am_ext_source()
        # Assert
        self.assertTrue(ext_source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_am_ext_source_is_int(self):
        """Test the get_am_ext_source function returning "INT"."""
        # Arrange
        expected_call = ":AM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "INT"
        # Act
        ext_source = self.apsin.get_am_ext_source()
        # Assert
        self.assertFalse(ext_source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_am_ext_source_to_ext(self):
        """Test set_am_ext_source function with setting to "EXT"."""
        # Arrange
        ext = True
        expected_write_call = ":AM:SOUR EXT"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_am_ext_source(ext)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_am_ext_source_to_int(self):
        """Test set_am_ext_source function with setting to "INT"."""
        # Arrange
        ext = False
        expected_write_call = ":AM:SOUR INT"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_am_ext_source(ext)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_am_sensitivity(self):
        # Arrange
        expected_am_sensitivity = 3.141
        expected_ask_call = ":AM:SENS?"
        self.apsin._scpi_protocol.ask.return_value = f"{expected_am_sensitivity}\r\n"
        # Act
        freq = self.apsin.get_am_sensitivity()
        # Assert
        self.assertEqual(freq, expected_am_sensitivity)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_am_sensitivity(self):
        """Test set_am_sensitivity call."""
        # Arrange
        am_sensitivity = 0.0
        expected_write_call = f":AM:SENS {am_sensitivity}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_am_sensitivity(am_sensitivity)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_fm_enabled(self):
        """Test the get_fm_enabled function."""
        # Arrange
        expected_call = ":FM:STAT?"
        self.apsin._scpi_protocol.ask.return_value = "OFF"
        # Act
        enabled = self.apsin.get_fm_enabled()
        # Assert
        self.assertFalse(enabled)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_fm_enabled_enable(self):
        """Test set_fm_enabled function with enabling."""
        # Arrange
        enable = True
        expected_write_call = f":FM:STAT {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_fm_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_fm_enabled_disable(self):
        """Test set_fm_enabled function with disabling."""
        # Arrange
        enable = False
        expected_write_call = f":FM:STAT {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_fm_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_fm_ext_source_is_ext(self):
        """Test the get_fm_ext_source function returning "EXT"."""
        # Arrange
        expected_call = ":FM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "EXT"
        # Act
        ext_source = self.apsin.get_fm_ext_source()
        # Assert
        self.assertTrue(ext_source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_fm_ext_source_is_int(self):
        """Test the get_fm_ext_source function returning "INT"."""
        # Arrange
        expected_call = ":FM:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = "INT"
        # Act
        ext_source = self.apsin.get_fm_ext_source()
        # Assert
        self.assertFalse(ext_source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_fm_ext_source_to_ext(self):
        """Test set_fm_ext_source function with setting to "EXT"."""
        # Arrange
        ext = True
        expected_write_call = ":FM:SOUR EXT"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_fm_ext_source(ext)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_fm_ext_source_to_int(self):
        """Test set_fm_ext_source function with setting to "INT"."""
        # Arrange
        ext = False
        expected_write_call = ":FM:SOUR INT"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_fm_ext_source(ext)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_fm_sensitivity(self):
        # Arrange
        expected_fm_sensitivity = 3.141
        expected_ask_call = ":FM:SENS?"
        self.apsin._scpi_protocol.ask.return_value = f"{expected_fm_sensitivity}\r\n"
        # Act
        freq = self.apsin.get_fm_sensitivity()
        # Assert
        self.assertEqual(freq, expected_fm_sensitivity)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_fm_sensitivity(self):
        """Test set_fm_sensitivity call."""
        # Arrange
        fm_sensitivity = 0.0
        expected_write_call = f":FM:SENS {fm_sensitivity}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_fm_sensitivity(fm_sensitivity)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_fm_coupling(self):
        """Test the get_fm_coupling function."""
        # Arrange
        expected_coupling = "AC"
        expected_call = ":FM:COUP?"
        self.apsin._scpi_protocol.ask.return_value = expected_coupling
        # Act
        coupling = self.apsin.get_fm_coupling()
        # Assert
        self.assertEqual(expected_coupling, coupling)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_fm_coupling(self):
        """Test set_fm_coupling function."""
        # Arrange
        coupling = "dc"
        expected_write_call = f":FM:COUP {coupling.upper()}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_fm_coupling(coupling)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_fm_coupling_excepts(self):
        """Test set_fm_coupling function excepts with invalid value."""
        # Arrange
        coupling = "Thunderstruck"
        # Act
        with self.assertRaises(ValueError):
            self.apsin.set_fm_coupling(coupling)

        self.apsin._scpi_protocol.write.assert_not_called()
        self.apsin._scpi_protocol.ask.assert_not_called()

    def test_get_reference_source(self):
        """Test the get_reference_source function."""
        # Arrange
        expected_source = "INT"
        expected_call = ":ROSC:SOUR?"
        self.apsin._scpi_protocol.ask.return_value = expected_source
        # Act
        source = self.apsin.get_reference_source()
        # Assert
        self.assertEqual(expected_source, source)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_reference_source(self):
        """Test set_reference_source function."""
        # Arrange
        source = "int"
        expected_write_call = f":ROSC:SOUR {source.upper()}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_reference_source(source)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_reference_source_excepts(self):
        """Test set_reference_source function excepts with invalid value."""
        # Arrange
        source = "ULT"
        # Act
        with self.assertRaises(ValueError):
            self.apsin.set_reference_source(source)

        self.apsin._scpi_protocol.write.assert_not_called()
        self.apsin._scpi_protocol.ask.assert_not_called()

    def test_get_external_reference_frequency(self):
        """Test get_external_reference_frequency function."""
        # Arrange
        expected_external_reference_frequency = 123.45E-5
        expected_ask_call = ":ROSC:EXT:FREQ?"
        self.apsin._scpi_protocol.ask.return_value = f"{expected_external_reference_frequency}\r\n"
        # Act
        freq = self.apsin.get_external_reference_frequency()
        # Assert
        self.assertEqual(freq, expected_external_reference_frequency)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_external_reference_frequency(self):
        """Test set_external_reference_frequency call."""
        # Arrange
        external_reference_frequency = 432.15E-6
        expected_write_call = f":ROSC:EXT:FREQ {external_reference_frequency}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_external_reference_frequency(external_reference_frequency)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_get_reference_is_locked(self):
        """Test the get_reference_is_locked function."""
        # Arrange
        expected_call = ":ROSC:LOCK?"
        self.apsin._scpi_protocol.ask.return_value = "1"
        # Act
        locked = self.apsin.get_reference_is_locked()
        # Assert
        self.assertTrue(locked)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_get_reference_output_enabled(self):
        """Test the get_reference_output_enabled function."""
        # Arrange
        expected_call = ":ROSC:OUTP?"
        self.apsin._scpi_protocol.ask.return_value = "OFF"
        # Act
        enabled = self.apsin.get_reference_output_enabled()
        # Assert
        self.assertFalse(enabled)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_call)

    def test_set_reference_output_enabled_enable(self):
        """Test set_reference_output_enabled function with enabling."""
        # Arrange
        enable = True
        expected_write_call = f":ROSC:OUTP {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_reference_output_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)

    def test_set_reference_output_enabled_disable(self):
        """Test set_reference_output_enabled function with disabling."""
        # Arrange
        enable = False
        expected_write_call = f":ROSC:OUTP {int(enable)}"
        expected_ask_call = ":SYST:ERR:ALL?"
        self.apsin._scpi_protocol.ask.return_value = "0, No error"
        # Act
        self.apsin.set_reference_output_enabled(enable)
        # Assert
        self.apsin._scpi_protocol.write.assert_called_once_with(expected_write_call)
        self.apsin._scpi_protocol.ask.assert_called_once_with(expected_ask_call)


if __name__ == '__main__':
    unittest.main()
