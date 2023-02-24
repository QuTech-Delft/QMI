"""Unit test for Rohde&Schwarz SMBV100a."""
import logging
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.rohde_schwarz.smbv100a import RohdeSchwarz_SMBV100A


class TestSMBV100A(unittest.TestCase):

    def setUp(self):
        qmi.start("TestSMBV100AContext")
        # Add patches
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.create_transport', spec=QMI_TcpTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.instr: RohdeSchwarz_SMBV100A = qmi.make_instrument("SMBV100a", RohdeSchwarz_SMBV100A, "")
        self.instr = cast(RohdeSchwarz_SMBV100A, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_reset(self):
        """Test reset."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        expected_calls = [
            call("*CLS"),
            call("*RST")
        ]

        self.instr.reset()

        self._scpi_mock.write.assert_has_calls(expected_calls)
        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_error(self):
        """Test command with error response."""
        self._scpi_mock.ask.return_value = "1,\"Huge error\""
        expected_calls = [
            call("*CLS"),
            call("*RST")
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.reset()

        self._scpi_mock.write.assert_has_calls(expected_calls)
        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")
    
    def test_get_idn(self):
        """Test ident. """
        vendor = "vendor"
        model = "model"
        serial = "serial"
        version = "version"
        self._scpi_mock.ask.return_value = f"{vendor},{model},{serial},{version}"

        ident = self.instr.get_idn()

        self._scpi_mock.ask.assert_called_once_with("*IDN?")
        self.assertEqual(ident.vendor, vendor)
        self.assertEqual(ident.model, model)
        self.assertEqual(ident.serial, serial)
        self.assertEqual(ident.version, version)

    def test_wrong_idn_response(self):
        """Test ident."""
        self._scpi_mock.ask.return_value = "nonsense"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

        self._scpi_mock.ask.assert_called_once_with("*IDN?")

    def test_start_calibration_for_all(self):
        """Test start calibration for all."""
        self.instr.start_calibration(all=True)

        self._scpi_mock.write.assert_called_once_with("CAL:ALL:MEAS?")

    def test_start_calibration_for_frequency_and_level(self):
        """Test start calibration for frequency and level."""
        self.instr.start_calibration(cal_iqm=False)
        expected_calls = [
            call("CAL:FREQ:MEAS?"),
            call("CAL:LEV:MEAS?")
        ]

        self._scpi_mock.write.assert_has_calls(expected_calls)
    
    def test_start_calibration_for_frequency_level_and_iqm(self):
        """Test start calibration for frequency, level and IQM."""
        self.instr.start_calibration()
        expected_calls = [
            call("CAL:FREQ:MEAS?"),
            call("CAL:LEV:MEAS?"),
            call("IQ:SOUR ANAL"),
            call("IQ:STAT ON"),
            call("CAL:IQM:LOC?")
        ]

        self._scpi_mock.write.assert_has_calls(expected_calls)

    def test_check_if_calibrating(self):
        """Test that ongoing calibration inhibits interactions with the instrument."""
        # Device doesn't respond during calibration
        self._transport_mock.read_until.side_effect = QMI_TimeoutException

        self.instr.start_calibration()

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_poll_calibration_in_progress(self):
        """Test calibration state polling."""
        # Device doesn't respond during calibration
        self._transport_mock.read_until.side_effect = QMI_TimeoutException

        self.instr.start_calibration()
        result = self.instr.poll_calibration()

        self.assertIsNone(result)

    def test_poll_calibration_not_started(self):
        """Test calibration state polling."""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.poll_calibration()

    def test_poll_calibration_result_ok(self):
        """Test calibration state polling."""
        # Calibration result.
        calibration_result = 123
        self._transport_mock.read_until.return_value = bytes(str(calibration_result).encode("ascii")) + b"\r\n"

        # Calibration state query response.
        self._scpi_mock.ask.return_value = "0,\"No error\""

        self.instr.start_calibration()
        result = self.instr.poll_calibration()

        self.assertEqual(result, calibration_result)
        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_poll_calibration_error(self):
        """Test calibration state polling."""
        logging.getLogger("qmi.instruments.rohde_schwarz.rs_base_signal_gen").setLevel(logging.ERROR)

        # Calibration result.
        calibration_result = 456
        self._transport_mock.read_until.return_value = bytes(str(calibration_result).encode("ascii")) + b"\r\n"

        # Calibration state query response.
        self._scpi_mock.ask.return_value = "1,\"Some error\""

        self.instr.start_calibration()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.poll_calibration()

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_wrong_float_value(self):
        """Test wrong float value response."""
        self._scpi_mock.ask.return_value = "not a float"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_frequency()

    def test_wrong_bool_value(self):
        """Test wrong bool value response."""
        self._scpi_mock.ask.return_value = "not a bool"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_output_state()

    def test_get_set_frequency(self):
        """Test get/set frequency."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_frequency()

        self._scpi_mock.ask.assert_called_once_with(":FREQ?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_frequency(target_value)

        self._scpi_mock.write.assert_called_once_with(f":FREQ {target_value}")

    def test_get_set_phase(self):
        """Test get/set phase."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_phase()

        self._scpi_mock.ask.assert_called_once_with(":PHAS?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_phase(target_value)

        self._scpi_mock.write.assert_called_once_with(f":PHAS {target_value}")

    def test_get_set_ref_source(self):
        """Test get/set reference source."""
        # Test get.
        value = "INT"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_reference_source()

        self._scpi_mock.ask.assert_called_once_with(":ROSC:SOUR?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("INT", "int", "EXT", "ext"):
            self.instr.set_reference_source(target_value)

            self._scpi_mock.write.assert_called_once_with(f":ROSC:SOUR {target_value.upper()}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_reference_source("theoracle")

    def test_get_set_output_policy(self):
        """Test get/set output policy."""
        # Test get.
        value = "OFF"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_power_on_output_policy()

        self._scpi_mock.ask.assert_called_once_with(":OUTP:PON?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("OFF", "off", "UNCH", "unch"):
            self.instr.set_power_on_output_policy(target_value)

            self._scpi_mock.write.assert_called_once_with(f":OUTP:PON {target_value.upper()}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_power_on_output_policy("chaos")

    def test_get_set_power(self):
        """Test get/set power."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_power()

        self._scpi_mock.ask.assert_called_once_with(":POW?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_power(target_value)

        self._scpi_mock.write.assert_called_once_with(f":POW {target_value}")

    def test_get_set_output_state(self):
        """Test get/set output state."""
        # Test get.
        value = "0"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_output_state()

        self._scpi_mock.ask.assert_called_once_with(":OUTP?")
        self.assertEqual(result, False)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_output_state(target_value)

            self._scpi_mock.write.assert_called_once_with(":OUTP {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_pulsemod_enable(self):
        """Test get/set pulse modulation."""
        # Test get.
        value = "0"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_pulsemod_enabled()

        self._scpi_mock.ask.assert_called_once_with(":PULM:STAT?")
        self.assertEqual(result, False)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_pulsemod_enabled(target_value)

            self._scpi_mock.write.assert_called_once_with(":PULM:STAT {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_ref_frequency(self):
        """Test get/set reference frequency."""
        # Test get.
        value = "10MHZ"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_external_reference_frequency()

        self._scpi_mock.ask.assert_called_once_with(":ROSC:EXT:FREQ?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("5MHZ", "10MHZ", "5MHz", "10mhz"):
            self.instr.set_external_reference_frequency(target_value)

            self._scpi_mock.write.assert_called_once_with(f":ROSC:EXT:FREQ {target_value.upper()}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_external_reference_frequency("10000MHZ")

    def test_get_set_iq_enable(self):
        """Test get/set IQ enable."""
        # Test get.
        value = "1"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_enabled()

        self._scpi_mock.ask.assert_called_once_with(":IQ:STAT?")
        self.assertEqual(result, True)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_iq_enabled(target_value)

            self._scpi_mock.write.assert_called_once_with(":IQ:STAT {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()
    
    def test_set_sig_for_iq_mod_with_valid_signal(self):
        """Test setting the input signal for I/Q modulation with valid inputs."""
        valid_sigs = ['BAS', 'ANAL', 'DIFF']
        for sig in valid_sigs:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % sig, sig=sig):
                self.instr.set_sig_for_iq_mod(sig)
                self._scpi_mock.write.assert_called_once_with('IQ:SOUR %s' % sig)
            self._scpi_mock.reset_mock()
    
    def test_set_sig_for_iq_mod_with_invalid_signal(self):
        """Test setting the input signal for I/Q modulation with invalid inputs."""
        valid_sigs = ['SWE', 'CW', 'FIX']
        for sig in valid_sigs:
            self._scpi_mock.ask.return_value = "Values that can be set are BAS,ANAL,DIFF"
            with self.subTest("Testing %s" % sig, sig=sig):
                with self.assertRaises(ValueError):
                    self.instr.set_sig_for_iq_mod(sig)
            self._scpi_mock.reset_mock()
    
    def test_set_iq_mod(self):
        """Test turning on and off I/Q modulation."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        # test turn on
        self.instr.set_iq_mod(True)
        self._scpi_mock.write.assert_called_once_with("IQ:STAT ON")
        self._scpi_mock.reset_mock()
        # test turn off
        self.instr.set_iq_mod(False)
        self._scpi_mock.write.assert_called_once_with("IQ:STAT OFF")

    def test_activate_iq_mod(self):
        """Test activating I/Q modulation."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.activate_iq_mod()
        self._scpi_mock.write.assert_called_once_with("IQ:STAT ON")

    def test_deactivate_iq_mod(self):
        """Test deactivating I/Q modulation."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.deactivate_iq_mod()
        self._scpi_mock.write.assert_called_once_with("IQ:STAT OFF")

    def test_set_iq(self):
        """Test activating/deactivating I/Q modulation with analog signal."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        # test activating
        expected_calls = [
            call("IQ:SOUR ANAL"),
            call("IQ:STAT ON")
        ]

        self.instr.set_iq(True)
        self._scpi_mock.write.assert_has_calls(expected_calls)
        self._scpi_mock.reset_mock()
        # test deactivating
        expected_calls = [
            call("IQ:SOUR ANAL"),
            call("IQ:STAT OFF")
        ]

        self.instr.set_iq(False)
        self._scpi_mock.write.assert_has_calls(expected_calls)

    def test_set_freq_mode_with_valid_signal(self):
        """Test setting RF frequency mode with valid inputs."""
        valid_modes = ['FIX', 'LIST', 'SWE', 'CW']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_freq_mode(mode)
                self._scpi_mock.write.assert_called_once_with('SOUR:FREQ:MODE %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_freq_mode_with_invalid_signal(self):
        """Test setting RF frequency mode with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are FIX,LST,SWE,CW"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_freq_mode(mode)
            self._scpi_mock.reset_mock()

    def test_set_sweep_frequency_start(self):
        """Test setting start frequency for sweep"""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        freq = 10.5
        self.instr.set_sweep_frequency_start(freq)
        self._scpi_mock.write.assert_called_once_with("FREQ:STAR 10.5 Hz")

    def test_set_sweep_frequency_stop(self):
        """Test setting stop frequency for sweep"""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        freq = 100.5
        self.instr.set_sweep_frequency_stop(freq)
        self._scpi_mock.write.assert_called_once_with("FREQ:STOP 100.5 Hz")

    def test_set_sweep_frequency_step(self):
        """Test setting frequency step for sweep"""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        freq = 2
        self.instr.set_sweep_frequency_step(freq)
        self._scpi_mock.write.assert_called_once_with("SWE:STEP:LIN 2 Hz")

    def test_enable_list_mode(self):
        """Test enabling of list mode."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.enable_list_mode()

        self._scpi_mock.write.assert_called_once_with("SOUR:FREQ:MODE LIST")

    def test_set_list_processing_mode_with_valid_signal(self):
        """Test setting RF frequency mode with valid inputs."""
        valid_modes = ['AUTO', 'STEP']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_list_processing_mode(mode)
                self._scpi_mock.write.assert_called_once_with('LIST:MODE %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_list_processing_mode_with_invalid_signal(self):
        """Test setting RF frequency mode with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are AUTO,STEP"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_list_processing_mode(mode)
            self._scpi_mock.reset_mock()

    def test_enable_list_step_mode(self):
        """Test enabling of step-by-step processing of list."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.enable_list_step_mode()

        self._scpi_mock.write.assert_called_once_with("LIST:MODE STEP")

    def test_set_trigger_source_processing_lists_with_valid_signal(self):
        """Test setting the trigger source processing lists with valid inputs."""
        valid_modes = ['AUTO', 'IMM', 'SING', 'EXT']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_trigger_source_processing_lists(mode)
                self._scpi_mock.write.assert_called_once_with('LIST:TRIG:SOUR %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_trigger_source_processing_lists_with_invalid_signal(self):
        """Test setting the trigger source processing lists with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are AUTO,STEP"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_trigger_source_processing_lists(mode)
            self._scpi_mock.reset_mock()

    def test_set_list_ext_trigger_source(self):
        """Test triggering of list externally."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.set_list_ext_trigger_source()

        self._scpi_mock.write.assert_called_once_with("LIST:TRIG:SOUR EXT")

    def test_set_freq_sweep_mode_with_valid_signal(self):
        """Test setting the frequency sweep mode with valid inputs."""
        valid_modes = ['STEP', 'AUTO']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_freq_sweep_mode(mode)
                self._scpi_mock.write.assert_called_once_with('SOUR:SWE:FREQ:MODE %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_freq_sweep_mode_with_invalid_signal(self):
        """Test setting the frequency sweep mode with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are AUTO,STEP"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_freq_sweep_mode(mode)
            self._scpi_mock.reset_mock()

    def test_set_freq_sweep_spacing_mode_with_valid_signal(self):
        """Test setting the frequency sweep spacing mode with valid inputs."""
        valid_modes = ['LIN', 'LOG']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_freq_sweep_spacing_mode(mode)
                self._scpi_mock.write.assert_called_once_with('SOUR:SWE:FREQ:SPAC %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_freq_sweep_spacing_mode_with_invalid_signal(self):
        """Test setting the frequency sweep spacing mode with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are LIN,LOG"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_freq_sweep_spacing_mode(mode)
            self._scpi_mock.reset_mock()

    def test_set_trig_source_freq_sweep_with_valid_signal(self):
        """Test setting the trigger source for the RF frequency sweep with valid inputs."""
        valid_modes = ['AUTO', 'SING', 'EXT', 'EAUT']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_trig_source_freq_sweep(mode)
                self._scpi_mock.write.assert_called_once_with('TRIG:FSW:SOUR %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_trig_source_freq_sweep_with_invalid_signal(self):
        """Test setting the trigger source for the RF frequency sweep with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are AUTO,SING,EXT,EAUT"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_trig_source_freq_sweep(mode)
            self._scpi_mock.reset_mock()

    def test_set_freq_mode_sig_gen_with_valid_signal(self):
        """Test setting the trigger source for the RF frequency sweep with valid inputs."""
        valid_modes = ['CW', 'FIX', 'SWE', 'LIST']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % mode, mode=mode):
                self.instr.set_freq_mode_sig_gen(mode)
                self._scpi_mock.write.assert_called_once_with('SOUR:FREQ:MODE %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_freq_mode_sig_gen_with_invalid_signal(self):
        """Test setting the trigger source for the RF frequency sweep with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are CW,FIX,SWE,LIST"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_freq_mode_sig_gen(mode)
            self._scpi_mock.reset_mock()

    def test_enable_ext_freq_sweep_mode(self):
        """Test enabling of sweep mode with externally triggered input."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.enable_ext_freq_sweep_mode()

        expected_calls = [
            call("SOUR:SWE:FREQ:MODE STEP"),
            call("SOUR:SWE:FREQ:SPAC LIN"),
            call("TRIG:FSW:SOUR EXT"),
            call("SOUR:FREQ:MODE SWE")
        ]

        self._scpi_mock.write.assert_has_calls(expected_calls)

    def test_reset_sweep(self):
        """Test resetting of active sweeps to starting point."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.reset_sweep()

        self._scpi_mock.write.assert_called_once_with("SOUR:SWE:RES:ALL")

    def test_reset_list_mode(self):
        """Test resetting of active sweeps to starting point."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.reset_list_mode()

        self._scpi_mock.write.assert_called_once_with("SOUR:LIST:RES")

    def test_learn_list(self):
        """Test learning of the list."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.learn_list()

        self._scpi_mock.write.assert_called_once_with("SOUR:LIST:LEAR")

    def test_reset_list(self):
        """Test learning of the list."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.reset_list()

        self._scpi_mock.write.assert_called_once_with("ABOR:LIST")

    def test_load_fplist(self):
        """Test loading of frequency and power list."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        actual_start_freq = 1
        actual_stop_freq = 10
        actual_num_steps = 10
        actual_unit_freq = "Hz"
        actual_start_pow = 11
        actual_stop_pow = 20
        actual_unit_pow = "dB"
        actual_flist = "1.0Hz,2.0Hz,3.0Hz,4.0Hz,5.0Hz,6.0Hz,7.0Hz,8.0Hz,9.0Hz,10.0Hz"
        actual_plist = "11.0dB,12.0dB,13.0dB,14.0dB,15.0dB,16.0dB,17.0dB,18.0dB,19.0dB,20.0dB"    
        expected_calls = [
            call('SOUR:LIST:SEL "list_%s_%s_%s"'%(actual_start_freq, actual_stop_freq, actual_num_steps)),
            call('SOUR:LIST:FREQ ' + actual_flist),
            call('SOUR:LIST:POW ' + actual_plist)
        ]

        self.instr.load_fplist(fstart=actual_start_freq, fstop=actual_stop_freq, funit=actual_unit_freq, 
            number_of_steps=actual_num_steps, pstart=actual_start_pow, pstop=actual_stop_pow, punit=actual_unit_pow)

        self._scpi_mock.write.assert_has_calls(expected_calls)

    def test_get_errors_with_no_error(self):
        """Test no errors in queue."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.get_errors()

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_get_errors_with_errors(self):
        """Test errors in queue."""
        self._scpi_mock.ask.return_value = "1,\"Some error\""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_errors()

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_get_error_queue_length(self):
        """Test error queue length."""
        expected = 1
        self._scpi_mock.ask.return_value = expected
        actual = self.instr.get_error_queue_length()

        self.assertEqual(actual, expected)

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:COUN?")


class TestSMBV100APowerLimited(unittest.TestCase):

    def setUp(self):
        qmi.start("TestSMBV100APLContext")
        # Add patches
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.ScpiProtocol', autospec=True)
        self._scpi_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.maxpower = 10
        self.instr: RohdeSchwarz_SMBV100A = qmi.make_instrument("SMBV100A", RohdeSchwarz_SMBV100A, "", self.maxpower)
        self.instr = cast(RohdeSchwarz_SMBV100A, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_set_power_below_max(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "0,\"No error\""  # query to error state
        ]
        target_value = 0.5 * self.maxpower

        self.instr.set_power(target_value)

        self._scpi_mock.write.assert_called_once_with(f":POW {target_value}")

    def test_set_power_above_max_ok(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        self.instr.set_power(target_value)

        self._scpi_mock.write.assert_called_once_with(f":POW {target_value}")

    def test_set_power_above_max_fail1(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "OFF",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_power(target_value)

        self._scpi_mock.write.assert_not_called()

    def test_set_power_above_max_fail2(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "ON",  # response to query pulsemod enabled
            "INT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_power(target_value)

        self._scpi_mock.write.assert_not_called()

    def test_set_power_above_max_fail3(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "INV",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_power(target_value)

        self._scpi_mock.write.assert_not_called()

    def test_set_output_enable_below_max(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            0.5 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_output_state(True)

        self._scpi_mock.write.assert_called_once_with(":OUTP 1")

    def test_set_output_enable_above_max_ok(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_output_state(True)

        self._scpi_mock.write.assert_called_once_with(":OUTP 1")

    def test_set_output_enable_above_max_fail1(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "OFF",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_state(True)

        self._scpi_mock.write.assert_not_called()

    def test_set_output_enable_above_max_fail2(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "ON",  # response to query pulsemod enabled
            "INT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_state(True)

        self._scpi_mock.write.assert_not_called()

    def test_set_output_enable_above_max_fail3(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "INV",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_state(True)

        self._scpi_mock.write.assert_not_called()

    def test_set_pulsemod_enable_below_max(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            0.5 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_enabled(False)

        self._scpi_mock.write.assert_called_once_with(":PULM:STAT 0")

    def test_set_pulsemod_enable_above_max_ok(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_enabled(True)

        self._scpi_mock.write.assert_called_once_with(":PULM:STAT 1")

    def test_set_pulsemod_enable_above_max_fail(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pulsemod_enabled(False)

        self._scpi_mock.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()