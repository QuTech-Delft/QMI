"""Unit-tests for Santec TSL-570 driver class."""
import logging
import random
import unittest
from unittest.mock import call, patch, Mock
import numpy as np

import qmi
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport

from qmi.instruments.santec.tsl_570 import Santec_Tsl570


class TestSantecTsl570OpenClose(unittest.TestCase):

    def setUp(self):
        logging.getLogger("qmi.instruments.santec.tsl_570").setLevel(logging.CRITICAL)
        qmi.start("TestSantecTsl570ClassContext")
        # Add patches
        patcher = patch('qmi.instruments.santec.tsl_570.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = patch('qmi.instruments.santec.tsl_570.ScpiProtocol', autospec=ScpiProtocol)
        self._scpi_mock = patcher2.start()
        self.addCleanup(patcher2.stop)
        self._scpi_mock.write = Mock()
        # Make DUT
        self.instr: Santec_Tsl570 = Santec_Tsl570(qmi.context(), "Santec_laser", "")

    def tearDown(self):
        qmi.stop()
        logging.getLogger("qmi.instruments.santec.tsl_570").setLevel(logging.NOTSET)

    def test_open_close(self):
        """open() command not just opens the instrument, but immediately also checks the wavelength/frequency
        range and the power unit to set the power level range. Test the whole shebang.

        close() command then just closes the connection to the instrument and the transport.
        """
        # Initially, the wavelength and power range should be bare data classes
        expected_initial_out = "<class 'qmi.instruments.santec.tsl_570._{rng}Range'>"
        self.assertEqual(expected_initial_out.format(rng="Wavelength"), str(self.instr._wavelength_range))
        self.assertEqual(expected_initial_out.format(rng="Frequency"), str(self.instr._frequency_range))
        self.assertEqual(expected_initial_out.format(rng="PowerLevel"), str(self.instr._power_level_range))
        # Arrange
        expected_wl_min = 1200.0
        expected_wl_max = 1700.0
        expected_freq_min = 175.0
        expected_freq_max = 250.0
        power_unit = 0  # "dBm"
        expected_power_min = -15.0
        expected_power_max = 13.0

        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_wl_min}\r",
            f"{expected_wl_max}\r",
            f"{expected_freq_min}\r",
            f"{expected_freq_max}\r",
            f"{power_unit}\r"
        ]
        expected_calls = [
            call().ask(":WAV:MIN?"),
            call().ask(":WAV:MAX?"),
            call().ask(":WAV:FREQ:MIN?"),
            call().ask(":WAV:FREQ:MAX?"),
            call().ask(":POW:UNIT?")
        ]
        # Act
        self.instr.open()
        # Assert
        self._transport_mock.assert_called_once()
        self.assertEqual(expected_wl_min, self.instr._wavelength_range.min)
        self.assertEqual(expected_wl_max, self.instr._wavelength_range.max)
        self.assertEqual(expected_power_min, self.instr._power_level_range.min)
        self.assertEqual(expected_power_max, self.instr._power_level_range.max)
        self._scpi_mock.assert_has_calls(expected_calls, any_order=True)
        # Test close
        self.instr.close()
        self._transport_mock.assert_called_once()

    def test_open_close_alternate_unit(self):
        """Test the open() - close() but with in milliwatt units"""
        # Arrange
        expected_wl_min = 1200.0
        expected_wl_max = 1700.0
        expected_freq_min = 175.0
        expected_freq_max = 250.0
        power_unit = 1  # "mW"
        expected_power_min = 0.04
        expected_power_max = 20.0
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_wl_min}\r",
            f"{expected_wl_max}\r",
            f"{expected_freq_min}\r",
            f"{expected_freq_max}\r",
            f"{power_unit}\r"
        ]
        expected_calls = [
            call().ask(":WAV:MIN?"),
            call().ask(":WAV:MAX?"),
            call().ask(":WAV:FREQ:MIN?"),
            call().ask(":WAV:FREQ:MAX?"),
            call().ask(":POW:UNIT?")
        ]
        # Act
        self.instr.open()
        # Assert
        self._transport_mock.assert_called_once()
        self.assertEqual(expected_wl_min, self.instr._wavelength_range.min)
        self.assertEqual(expected_wl_max, self.instr._wavelength_range.max)
        self.assertEqual(expected_freq_min, self.instr._frequency_range.min)
        self.assertEqual(expected_freq_max, self.instr._frequency_range.max)
        self.assertEqual(expected_power_min, self.instr._power_level_range.min)
        self.assertEqual(expected_power_max, self.instr._power_level_range.max)
        self._scpi_mock.assert_has_calls(expected_calls)
        # Test close
        self.instr.close()
        self._transport_mock.assert_called_once()


class TestSantecTsl570ClassMethods(unittest.TestCase):

    def setUp(self):
        # Make as standard to open in wavelength and dBm mode.
        self.wl_min = 1200.0
        self.wl_max = 1700.0
        self.freq_min = 175.0
        self.freq_max = 250.0
        power_unit = 0  # "dBm"
        self.power_min = -15.0
        self.power_max = 13.0

        logging.getLogger("qmi.instruments.santec.tsl_570").setLevel(logging.CRITICAL)
        qmi.start("TestSantecTsl570ClassContext")
        # Add patches
        patcher = patch('qmi.instruments.santec.tsl_570.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = patch('qmi.instruments.santec.tsl_570.ScpiProtocol', autospec=ScpiProtocol)
        self._scpi_mock = patcher2.start()
        self.addCleanup(patcher2.stop)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.wl_min}\r",
            f"{self.wl_max}\r",
            f"{self.freq_min}\r",
            f"{self.freq_max}\r",
            f"{power_unit}\r"
        ]
        self._scpi_mock.write = Mock()
        # Make DUT
        self.instr: Santec_Tsl570 = Santec_Tsl570(qmi.context(), "RSB100a", "")
        self.instr.open()
        # Reset the SCPI mock for further tests
        self._scpi_mock.reset_mock()

    def tearDown(self):
        self.instr.close()
        qmi.stop()
        logging.getLogger("qmi.instruments.santec.tsl_570").setLevel(logging.NOTSET)

    def test_wrong_int_value(self):
        """Test a call that uses _ask_int to see that it raises an error at wrong response"""
        self._scpi_mock(self._transport_mock).ask.side_effect = ["not an int"]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_coherence_control_status()

    def test_wrong_float_value(self):
        """Test a call that uses _ask_float to see that it raises an error at wrong response"""
        self._scpi_mock(self._transport_mock).ask.side_effect = ["not a float"]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_wavelength()

    def test_wrong_bool_value(self):
        """Test a call that uses _ask_bool to see that it raises an error at wrong response"""
        self._scpi_mock(self._transport_mock).ask.side_effect = ["not a bool"]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.operation_complete()

    def test_get_idn(self):
        """Test ident. """
        vendor = "vendor"
        model = "model"
        serial = "serial"
        version = "version"
        self._scpi_mock(self._transport_mock).ask.side_effect = [f"{vendor},{model},{serial},{version}"]

        ident = self.instr.get_idn()

        self._scpi_mock.assert_has_calls([call().ask("*IDN?")])
        self.assertEqual(ident.vendor, vendor)
        self.assertEqual(ident.model, model)
        self.assertEqual(ident.serial, serial)
        self.assertEqual(ident.version, version)

    def test_wrong_idn_response(self):
        """Test ident. raises QMI_InstrumentException by a non-sense response."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ["nonsense"]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

        self._scpi_mock.assert_has_calls([call().ask("*IDN?")])

    def test_reset(self):
        """Test reset."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ['0,"No error"', "No alerts."]

        self.instr.reset()

        self._scpi_mock.assert_has_calls([call().write("*RST")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ERR?")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ALER?")])

    def test_clear(self):
        """Test clear."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ['0,"No error"', "No alerts."]

        self.instr.clear()

        self._scpi_mock.assert_has_calls([call().write("*CLS")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ERR?")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ALER?")])

    def test_operation_completed(self):
        """Test getting OPC status."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ["1"]

        opc = self.instr.operation_complete()

        self.assertTrue(opc)
        self._scpi_mock.assert_has_calls([call().ask("*OPC?")])

    def test_error(self):
        """Test command with error and alert responses. '0,"No error"' should be returned when no further
        errors or alerts are present."""
        # Arrange
        error_code = -410
        alert_code = "No27."
        expected_error = [Santec_Tsl570.ERRORS_TABLE[error_code]]
        expected_alert = [Santec_Tsl570.ALERTS_TABLE[alert_code]]
        expected_exception = f"Command *RST resulted in errors: {expected_error + expected_alert}"
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{error_code}",
            '0,"No error"',
            f"{alert_code}",
            "No alerts."
        ]
        expected_write_calls = [
            call().write("*RST")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.reset()
        # Assert
        self.assertEqual(expected_exception, str(exc.exception))
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_errors(self):
        """Test the get_errors returns list of errors."""
        error_code = -102
        alert_code = "No07."
        expected_error = [Santec_Tsl570.ERRORS_TABLE[error_code]]
        expected_alert = [Santec_Tsl570.ALERTS_TABLE[alert_code]]
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{error_code}",
            '0,"No error"',
            f"{alert_code}",
            "No alerts."
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        response = self.instr.get_errors()
        # Assert
        self.assertEqual(expected_error + expected_alert, response)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_wavelength_in_nm(self):
        """Test setting the wavelength in nm."""
        input_wl = 1450
        expected_dec = 4  # resolution is 0.1pm, so we should use 4 decimals
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV {input_wl:.{expected_dec}f}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_wavelength(input_wl)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_wavelength_in_nm_excepts(self):
        """Test setting the wavelength in nm with values out-of-bounds."""
        input_wl = [self.wl_min - 1, self.wl_max + 1]
        # Act
        for inp in input_wl:
            with self.assertRaises(ValueError):
                self.instr.set_wavelength(inp)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_wavelength_in_nm(self):
        """Test getting the wavelength in nm."""
        wl = 1450.0
        expected_wl = round(wl, 4)  # We use 4 decimals for rounding output wl.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{wl}"
        ]
        expected_ask_calls = [
            call().ask(":WAV?"),
        ]
        # Act
        wavelength = self.instr.get_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_minimum_wavelength_in_nm(self):
        """Test getting the minimum wavelength in nm."""
        expected_wl = round(self.wl_min, 4)  # We use 4 decimals for rounding output wl.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.wl_min}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:MIN?"),
        ]
        # Act
        wavelength = self.instr.get_minimum_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_maximum_wavelength_in_nm(self):
        """Test getting the maximum wavelength in nm."""
        expected_wl = round(self.wl_max, 4)  # We use 4 decimals for rounding output wl.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.wl_max}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:MAX?"),
        ]
        # Act
        wavelength = self.instr.get_maximum_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_frequency_in_thz(self):
        """Test setting the frequency in thz."""
        input_freq = 231.0
        expected_dec = 5  # resolution is 10MHz, so we should use 5 decimals
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:FREQ {input_freq:.{expected_dec}f}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_frequency(input_freq)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_frequency_in_thz_excepts(self):
        """Test setting the frequency in thz with values out-of-bounds."""
        input_freq = [self.freq_min - 1, self.freq_max + 1]
        # Act
        for inp in input_freq:
            with self.assertRaises(ValueError):
                self.instr.set_frequency(inp)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_frequency_in_thz(self):
        """Test getting the frequency in THz."""
        freq = 200.0
        expected_freq = round(freq, 5)  # We use 5 decimals for rounding output freq.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{freq}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:FREQ?"),
        ]
        # Act
        frequency = self.instr.get_frequency()
        # Assert
        self.assertEqual(expected_freq, frequency)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_minimum_frequency_in_thz(self):
        """Test getting the minimum frequency in THz."""
        expected_freq = round(self.freq_min, 5)  # We use 5 decimals for rounding output freq.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.freq_min}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:FREQ:MIN?"),
        ]
        # Act
        frequency = self.instr.get_minimum_frequency()
        # Assert
        self.assertEqual(expected_freq, frequency)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_maximum_frequency_in_thz(self):
        """Test getting the maximum frequency in THz."""
        expected_freq = round(self.freq_max, 5)  # We use 5 decimals for rounding output freq.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.freq_max}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:FREQ:MAX?"),
        ]
        # Act
        frequency = self.instr.get_maximum_frequency()
        # Assert
        self.assertEqual(expected_freq, frequency)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_wavelength_unit(self):
        """Test setting the wavelength unit."""
        expected_units = [1, 0]  # is ["THz", "nm"]
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts.",
            '0,"No error"',
            "No alerts.",
        ]
        expected_calls = [
            call().write(f":WAV:UNIT {expected_units[0]}"),
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
            call().write(f":WAV:UNIT {expected_units[1]}"),
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
        ]
        # Act
        self.instr.set_wavelength_unit_to_thz()
        self.instr.set_wavelength_unit_to_nm()

        # Assert
        self._scpi_mock.assert_has_calls(expected_calls)

    def test_get_wavelength_unit_nm(self):
        """Test getting the wavelength unit as nm."""
        expected_unit = "nm"
        self._scpi_mock(self._transport_mock).ask.side_effect = ["0"]
        expected_ask_calls = [
            call().ask(":WAV:UNIT?"),
        ]
        # Act
        unit = self.instr.get_wavelength_unit()
        # Assert
        self.assertEqual(expected_unit, unit)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_wavelength_unit_thz(self):
        """Test getting the wavelength unit as THz."""
        expected_unit = "THz"
        self._scpi_mock(self._transport_mock).ask.side_effect = ["1"]
        expected_ask_calls = [
            call().ask(":WAV:UNIT?"),
        ]
        # Act
        unit = self.instr.get_wavelength_unit()
        # Assert
        self.assertEqual(expected_unit, unit)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_wavelength_fine(self):
        """Test setting the wavelength fine-tuning value."""
        input_wl_fine = 55.0
        expected_dec = 2  # resolution is 0.01, so we should use 2 decimals
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:FIN {input_wl_fine:.{expected_dec}f}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_wavelength_fine(input_wl_fine)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_wavelength_fine_excepts(self):
        """Test setting the wavelength fine-tuning value out-of-bounds."""
        input_wl_fine = [-100.1, 100.1]  # Range is [-100.0, 100.0]
        # Act
        for inp in input_wl_fine:
            with self.assertRaises(ValueError):
                self.instr.set_wavelength_fine(inp)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_wavelength_fine(self):
        """Test getting the wavelength fine-tuning value."""
        wl = 1450.0
        expected_wl = round(wl, 5)  # We use 5 decimals for rounding output wl.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{wl}"
        ]
        expected_ask_calls = [
            call().ask(":WAV?"),
        ]
        # Act
        wavelength = self.instr.get_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_disable_finetuning_operation(self):
        """Test disabling the fine-tuning operation."""
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts.",
        ]
        expected_write_calls = [
            call().write(":WAV:FIN:DIS"),
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.disable_finetuning_operation()

        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls, any_order=True)
        self._scpi_mock.assert_has_calls(expected_ask_calls, any_order=True)

    def test_set_coherence_control_status(self):
        """Test setting the coherence control_status."""
        inputs = [True, "OFF"]
        expected_control_status = [1, 0]  # is ["ON", "OFF"]
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts.",
            '0,"No error"',
            "No alerts.",
        ]
        expected_write_calls = [
            call().write(f":COHC {expected_control_status[0]}"),
            call().write(f":COHC {expected_control_status[1]}"),
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
        ]
        # Act
        for e, inp in enumerate(inputs):
            self.instr.set_coherence_control_status(inp)

        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls, any_order=True)
        self._scpi_mock.assert_has_calls(expected_ask_calls, any_order=True)

    def test_set_coherence_control_status_excepts(self):
        """See that the function excepts if invalid string is given as input."""
        with self.assertRaises(AssertionError):
            self.instr.set_coherence_control_status("AAN")

    def test_get_coherence_control_status(self):
        """Test getting the coherence control_status."""
        expected_control_status = "OFF"
        self._scpi_mock(self._transport_mock).ask.side_effect = ["0"]
        expected_ask_calls = [
            call().ask(":COHC?"),
        ]
        # Act
        control_status = self.instr.get_coherence_control_status()
        # Assert
        self.assertEqual(expected_control_status, control_status)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_optical_output_status(self):
        """Test setting the optical output_status."""
        inputs = [True, "OFF"]
        expected_output_status = [1, 0]  # is ["ON", "OFF"]
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts.",
            '0,"No error"',
            "No alerts.",
        ]
        expected_write_calls = [
            call().write(f":POW:STAT {expected_output_status[0]}"),
            call().write(f":POW:STAT {expected_output_status[1]}"),
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
        ]
        # Act
        for e, inp in enumerate(inputs):
            self.instr.set_optical_output_status(inp)

        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls, any_order=True)
        self._scpi_mock.assert_has_calls(expected_ask_calls, any_order=True)

    def test_set_optical_output_status_excepts(self):
        """See that the function excepts if invalid string is given as input."""
        with self.assertRaises(AssertionError):
            self.instr.set_optical_output_status("UIT")

    def test_get_optical_output_status(self):
        """Test getting the optical output_status."""
        expected_output_status = "ON"
        self._scpi_mock(self._transport_mock).ask.side_effect = ["1"]
        expected_ask_calls = [
            call().ask(":POW:STAT?"),
        ]
        # Act
        output_status = self.instr.get_optical_output_status()
        # Assert
        self.assertEqual(expected_output_status, output_status)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_power_level_in_dbm(self):
        """Test setting the power_level in dbm."""
        input_pow = 2
        expected_dec = 2  # resolution is 0.01dbm, so we should use 2 decimals
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            "0",
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":POW {input_pow:.{expected_dec}f}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_power_level(input_pow)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_power_level_in_dbm_excepts(self):
        """Test setting the power_level in dbm with values out-of-bounds."""
        input_pow = [self.power_min - 1, self.power_max + 1]
        self._scpi_mock(self._transport_mock).ask.side_effect = ["0", "0"]
        # Act
        for inp in input_pow:
            with self.assertRaises(ValueError):
                self.instr.set_power_level(inp)

        # Assert
        self._scpi_mock.assert_has_calls([call().ask(":POW:UNIT?")])

    def test_get_power_level_in_dbm(self):
        """Test getting the power_level in dbm."""
        pow = 9.0
        expected_pow = round(pow, 2)  # We use 2 decimals for rounding output pow.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{pow}"
        ]
        expected_ask_calls = [
            call().ask(":POW?"),
        ]
        # Act
        power_level = self.instr.get_power_level()
        # Assert
        self.assertEqual(expected_pow, power_level)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_minimum_power_level_in_dbm(self):
        """Test getting the minimum power_level in dbm."""
        # Arrange
        expected_pow = round(self.power_min, 2)  # We use 2 decimals for rounding output pow.
        # Act
        power_level = self.instr.get_minimum_power_level()
        # Assert
        self.assertEqual(expected_pow, power_level)
        self._scpi_mock.assert_not_called()

    def test_get_maximum_power_level_in_dbm(self):
        """Test getting the maximum power_level in dbm."""
        # Arrange
        expected_pow = round(self.power_max, 5)  # We use 5 decimals for rounding output pow.
        # Act
        power_level = self.instr.get_maximum_power_level()
        # Assert
        self.assertEqual(expected_pow, power_level)
        self._scpi_mock.assert_not_called()

    def test_get_power_level_in_mw(self):
        """Test getting the power_level in mW."""
        pow = 2.0
        expected_pow = round(pow, 2)  # We use 2 decimals for rounding output pow.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{pow}"
        ]
        expected_ask_calls = [
            call().ask(":POW?"),
        ]
        # Act
        power_level = self.instr.get_power_level()
        # Assert
        self.assertEqual(expected_pow, power_level)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_minimum_power_level_in_mw(self):
        """Test getting the minimum power_level in mW."""
        expected_pow = round(self.power_min, 2)  # We use 2 decimals for rounding output pow.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.power_min}"
        ]
        # Act
        power_level = self.instr.get_minimum_power_level()
        # Assert
        self.assertEqual(expected_pow, power_level)
        self._scpi_mock.assert_called_once()

    def test_get_maximum_power_level_in_mw(self):
        """Test getting the maximum power_level in mW."""
        expected_pow = round(self.power_max, 5)  # We use 5 decimals for rounding output pow.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{self.power_max}"
        ]
        # Act
        power_level = self.instr.get_maximum_power_level()
        # Assert
        self.assertEqual(expected_pow, power_level)
        self._scpi_mock.assert_called_once()

    def test_set_power_level_unit(self):
        """Test setting the power_level unit."""
        expected_units = [1, 0]  # is ["mW", "dbm"]
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts.",
            '0,"No error"',
            "No alerts.",
        ]
        expected_calls = [
            call().write(f":POW:UNIT {expected_units[0]}"),
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
            call().write(f":POW:UNIT {expected_units[1]}"),
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?"),
        ]
        # Act
        self.instr.set_power_level_unit_to_mw()
        self.instr.set_power_level_unit_to_dbm()

        # Assert
        self._scpi_mock.assert_has_calls(expected_calls)

    def test_get_power_level_unit_dbm(self):
        """Test getting the power_level unit as dbm."""
        expected_unit = "dBm"
        self._scpi_mock(self._transport_mock).ask.side_effect = ["0"]
        expected_ask_calls = [
            call().ask(":POW:UNIT?"),
        ]
        # Act
        unit = self.instr.get_power_level_unit()
        # Assert
        self.assertEqual(expected_unit, unit)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_power_level_unit_mw(self):
        """Test getting the power_level unit as mW."""
        expected_unit = "mW"
        self._scpi_mock(self._transport_mock).ask.side_effect = ["1"]
        expected_ask_calls = [
            call().ask(":POW:UNIT?"),
        ]
        # Act
        unit = self.instr.get_power_level_unit()
        # Assert
        self.assertEqual(expected_unit, unit)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_start_wavelength_in_nm(self):
        """Test setting the sweep_start_wavelength in nm."""
        input_wl = 1450
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:STAR {input_wl}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_start_wavelength(input_wl)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_start_wavelength_in_nm_excepts(self):
        """Test setting the sweep_start_wavelength in nm with values out-of-bounds."""
        input_wl = [self.wl_min - 1, self.wl_max + 1]
        # Act
        for inp in input_wl:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_start_wavelength(inp)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_start_wavelength_in_nm(self):
        """Test getting the sweep_start_wavelength in nm."""
        wl = 1450.0
        expected_wl = round(wl, 4)  # We use 4 decimals for rounding output wl.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{wl}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:STAR?"),
        ]
        # Act
        wavelength = self.instr.get_sweep_start_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_stop_wavelength_in_nm(self):
        """Test setting the sweep_stop_wavelength in nm."""
        input_wl = 1450
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:STOP {input_wl}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_stop_wavelength(input_wl)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_stop_wavelength_in_nm_excepts(self):
        """Test setting the sweep_stop_wavelength in nm with values out-of-bounds."""
        input_wl = [self.wl_min - 1, self.wl_max + 1]
        # Act
        for inp in input_wl:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_stop_wavelength(inp)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_stop_wavelength_in_nm(self):
        """Test getting the sweep_stop_wavelength in nm."""
        wl = 1450.0
        expected_wl = round(wl, 4)  # We use 4 decimals for rounding output wl.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{wl}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:STOP?"),
        ]
        # Act
        wavelength = self.instr.get_sweep_stop_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_start_frequency_in_thz(self):
        """Test setting the sweep_start_frequency in thz."""
        input_freq = 201
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:FREQ:SWE:STAR {input_freq}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_start_frequency(input_freq)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_start_frequency_in_thz_excepts(self):
        """Test setting the sweep_start_frequency in thz with values out-of-bounds."""
        input_freq = [self.freq_min - 1, self.freq_max + 1]
        # Act
        for inp in input_freq:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_start_frequency(inp)

        # Assert

        self._scpi_mock.assert_not_called()

    def test_get_sweep_start_frequency_in_thz(self):
        """Test getting the sweep_start_frequency in thz."""
        freq = 1450.0
        expected_freq = round(freq, 5)  # We use 5 decimals for rounding output freq.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{freq}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:FREQ:SWE:STAR?"),
        ]
        # Act
        frequency = self.instr.get_sweep_start_frequency()
        # Assert
        self.assertEqual(expected_freq, frequency)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_stop_frequency_in_thz(self):
        """Test setting the sweep_stop_frequency in thz."""
        input_freq = 201
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:FREQ:SWE:STOP {input_freq}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_stop_frequency(input_freq)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_stop_frequency_in_thz_excepts(self):
        """Test setting the sweep_stop_frequency in thz with values out-of-bounds."""
        input_freq = [self.freq_min - 1, self.freq_max + 1]
        # Act
        for inp in input_freq:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_stop_frequency(inp)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_stop_frequency_in_thz(self):
        """Test getting the sweep_stop_frequency in thz."""
        freq = 1450.0
        expected_freq = round(freq, 5)  # We use 5 decimals for rounding output freq.
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{freq}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:FREQ:SWE:STOP?"),
        ]
        # Act
        frequency = self.instr.get_sweep_stop_frequency()
        # Assert
        self.assertEqual(expected_freq, frequency)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_mode(self):
        """Test setting the sweep_mode."""
        mode = random.randint(0, 3)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:MOD {mode}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_mode(mode)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_mode_excepts(self):
        """Test setting the sweep_mode in with values out-of-bounds."""
        input_mode = [-1, 4]
        # Act
        for mode in input_mode:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_mode(mode)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_mode(self):
        """Test getting the sweep_mode."""
        expected_mode = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_mode}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:MOD?"),
        ]
        # Act
        mode = self.instr.get_sweep_mode()
        # Assert
        self.assertEqual(expected_mode, mode)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_speed(self):
        """Test setting the sweep_speed."""
        speed = random.choice([1, 2, 5, 10, 20, 50, 100, 200])
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:SPE {speed}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_speed(speed)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_speed_excepts(self):
        """Test setting the sweep_speed in with values out-of-bounds."""
        input_speed = [0, 199]
        # Act
        for speed in input_speed:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_speed(speed)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_speed(self):
        """Test getting the sweep_speed in nm/s."""
        expected_speed = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_speed}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:SPE?"),
        ]
        # Act
        speed = self.instr.get_sweep_speed()
        # Assert
        self.assertEqual(expected_speed, speed)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_cycles(self):
        """Test setting the sweep_cycles."""
        cycles = random.randint(0, 999)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:CYCL {cycles}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_cycles(cycles)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_cycles_excepts(self):
        """Test setting the sweep_cycles in with values out-of-bounds."""
        input_cycles = [-1, 1000]
        # Act
        for cycles in input_cycles:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_cycles(cycles)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_cycles(self):
        """Test getting the sweep_cycles."""
        expected_cycles = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_cycles}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:CYCL?"),
        ]
        # Act
        cycles = self.instr.get_sweep_cycles()
        # Assert
        self.assertEqual(expected_cycles, cycles)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_dwell(self):
        """Test setting the sweep_dwell."""
        dwell = float(random.randint(0, 999))
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:DWEL {dwell}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_dwell(dwell)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_dwell_excepts(self):
        """Test setting the sweep_dwell in with values out-of-bounds."""
        input_dwell = [-0.1, 1000.0]
        # Act
        for dwell in input_dwell:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_dwell(dwell)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_dwell(self):
        """Test getting the sweep_dwell."""
        expected_dec = 1  # should be 1 decimal accuracy
        expected_dwell = 2.0
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_dwell:.{expected_dec}f}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:DWEL?"),
        ]
        # Act
        dwell = self.instr.get_sweep_dwell()
        # Assert
        self.assertEqual(expected_dwell, dwell)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_delay(self):
        """Test setting the sweep_delay."""
        delay = float(random.randint(0, 999))
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:DEL {delay}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_delay(delay)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_delay_excepts(self):
        """Test setting the sweep_delay in with values out-of-bounds."""
        input_delay = [-0.1, 1000.0]
        # Act
        for delay in input_delay:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_delay(delay)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_delay(self):
        """Test getting the sweep_delay."""
        expected_dec = 1  # should be 1 decimal accuracy
        expected_delay = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_delay:.{expected_dec}f}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:DEL?"),
        ]
        # Act
        delay = self.instr.get_sweep_delay()
        # Assert
        self.assertEqual(expected_delay, delay)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_state(self):
        """Test setting the sweep_state."""
        state = random.randint(0, 1)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":WAV:SWE:STAT {state}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_sweep_state(state)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_sweep_state_excepts(self):
        """Test setting the sweep_state in with values out-of-bounds."""
        input_state = [-1, 2]
        # Act
        for state in input_state:
            with self.assertRaises(ValueError):
                self.instr.set_sweep_state(state)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_sweep_state(self):
        """Test getting the sweep_state."""
        expected_state = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_state}"
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:STAT?"),
        ]
        # Act
        state = self.instr.get_sweep_state()
        # Assert
        self.assertEqual(expected_state, state)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_trigger_output_timing_mode(self):
        """Test setting the trigger_output_timing_mode."""
        mode = random.randint(0, 3)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":TRIG:OUTP {mode}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_trigger_output_timing_mode(mode)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_trigger_output_timing_mode_excepts(self):
        """Test setting the trigger_output_timing_mode in with values out-of-bounds."""
        input_mode = [-1, 4]
        # Act
        for mode in input_mode:
            with self.assertRaises(ValueError):
                self.instr.set_trigger_output_timing_mode(mode)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_trigger_output_timing_mode(self):
        """Test getting the trigger_output_timing_mode."""
        expected_mode = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_mode}"
        ]
        expected_ask_calls = [
            call().ask(":TRIG:OUTP?"),
        ]
        # Act
        mode = self.instr.get_trigger_output_timing_mode()
        # Assert
        self.assertEqual(expected_mode, mode)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_trigger_output_period_mode(self):
        """Test setting the trigger_output_period_mode."""
        mode = random.randint(0, 1)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":TRIG:OUTP:SETT {mode}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_trigger_output_period_mode(mode)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_trigger_output_period_mode_excepts(self):
        """Test setting the trigger_output_period_mode in with values out-of-bounds."""
        input_mode = [-1, 2]
        # Act
        for mode in input_mode:
            with self.assertRaises(ValueError):
                self.instr.set_trigger_output_period_mode(mode)

        # Assert
        self._scpi_mock.assert_not_called()

    def test_get_trigger_output_period_mode(self):
        """Test getting the trigger_output_period_mode."""
        expected_mode = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_mode}"
        ]
        expected_ask_calls = [
            call().ask(":TRIG:OUTP:SETT?"),
        ]
        # Act
        mode = self.instr.get_trigger_output_period_mode()
        # Assert
        self.assertEqual(expected_mode, mode)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_trigger_output_step(self):
        """Test setting the trigger_output_step."""
        dec = 4  # Response in 4 decimal accuracy
        sweep_stop_wl, sweep_start_wl = 1360.0, 1280.0
        wl_range = sweep_stop_wl - sweep_start_wl
        step = random.uniform(0.0001, wl_range)
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{sweep_stop_wl}",
            f"{sweep_start_wl}",
            '0,"No error"',
            "No alerts."
        ]
        expected_write_calls = [
            call().write(f":TRIG:OUTP:STEP {step:.{dec}f}")
        ]
        expected_ask_calls = [
            call().ask(":SYST:ERR?"),
            call().ask(":SYST:ALER?")
        ]
        # Act
        self.instr.set_trigger_output_step(step)
        # Assert
        self._scpi_mock.assert_has_calls(expected_write_calls)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_set_trigger_output_step_excepts(self):
        """Test setting the trigger_output_step in with values out-of-bounds."""
        sweep_stop_wl, sweep_start_wl = 1360.0, 1280.0
        wl_range = sweep_stop_wl - sweep_start_wl
        input_step = [0.0000, wl_range + 0.0001]
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{sweep_stop_wl}",
            f"{sweep_start_wl}",
            f"{sweep_stop_wl}",
            f"{sweep_start_wl}",
        ]
        expected_ask_calls = [
            call().ask(":WAV:SWE:STOP?"),
            call().ask(":WAV:SWE:STAR?"),
            call().ask(":WAV:SWE:STOP?"),
            call().ask(":WAV:SWE:STAR?")
        ]
        # Act
        for step in input_step:
            with self.assertRaises(ValueError):
                self.instr.set_trigger_output_step(step)

        # Assert
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_get_trigger_output_step(self):
        """Test getting the trigger_output_step."""
        expected_dec = 1  # should be 1 decimal accuracy
        expected_step = 2
        self._scpi_mock(self._transport_mock).ask.side_effect = [
            f"{expected_step:.{expected_dec}f}"
        ]
        expected_ask_calls = [
            call().ask(":TRIG:OUTP:STEP?"),
        ]
        # Act
        step = self.instr.get_trigger_output_step()
        # Assert
        self.assertEqual(expected_step, step)
        self._scpi_mock.assert_has_calls(expected_ask_calls)

    def test_issue_soft_trigger(self):
        """Test issue_soft_trigger."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ['0,"No error"', "No alerts."]

        self.instr.issue_soft_trigger()

        self._scpi_mock.assert_has_calls([call().write(":TRIG:INP:SOFT")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ERR?")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ALER?")])

    def test_readout_points(self):
        """Test getting number of readout points."""
        readout_points = 124
        self._scpi_mock(self._transport_mock).ask.side_effect = [f"{readout_points}"]

        points = self.instr.readout_points()

        self.assertEqual(readout_points, points)
        self._scpi_mock.assert_has_calls([call().ask(":READ:POIN?")])

    def test_readout_data(self):
        """Test reading out data."""
        # Let's make 200 data point readings
        expected_data_points = 200
        expected_data = [round(random.uniform(self.wl_min, self.wl_max), 4) for _ in range(expected_data_points)]
        binary_data = b''.join([int(d * 1e4).to_bytes(4, byteorder="little") for d in expected_data])
        self._scpi_mock(self._transport_mock).read_binary_data.side_effect = [
            binary_data
        ]
        expected_write_calls = [
            call().write(":READout:DATa?"),
        ]
        # Act
        data = self.instr.readout_data()
        # Assert
        # Use numpy list assertion as otherwise some float inaccuracy errors appear
        np.testing.assert_allclose(expected_data, data, rtol=1e-4)
        self._scpi_mock.assert_has_calls(expected_write_calls)

    def test_shutdown(self):
        """Test shutdown."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ['0,"No error"', "No alerts."]

        self.instr.shutdown()

        self._scpi_mock.assert_has_calls([call().write(":SPEC:SHUT")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ERR?")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ALER?")])

    def test_reboot(self):
        """Test reboot."""
        self._scpi_mock(self._transport_mock).ask.side_effect = ['0,"No error"', "No alerts."]

        self.instr.reboot()

        self._scpi_mock.assert_has_calls([call().write(":SPECial:REBoot")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ERR?")])
        self._scpi_mock.assert_has_calls([call().ask(":SYST:ALER?")])
