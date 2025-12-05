"""Unit-tests for Rohde&Schwarz SMBV100a."""
import unittest
from unittest.mock import Mock, call, patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.rohde_schwarz import RohdeSchwarz_Smbv100a

from tests.patcher import PatcherQmiContext as QMI_Context


class TestSMBV100A(unittest.TestCase):

    def setUp(self):
        ctx = QMI_Context("TestSMBV100AContext")
        # Add patches
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.create_transport', spec=QMI_TcpTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.instr: RohdeSchwarz_Smbv100a = RohdeSchwarz_Smbv100a(ctx, "SMBV100a", "")
        self.instr.open()

    def tearDown(self):
        self.instr.close()

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
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.start_calibration()
        expected_calls = [
            call("CAL:FREQ:MEAS?"),
            call("CAL:LEV:MEAS?"),
            call(":IQ:SOUR ANAL"),
            call(":IQ:STAT 1"),
            call("CAL:IQM:LOC?")
        ]

        self._scpi_mock.write.assert_has_calls(expected_calls)

    def test_check_if_calibrating(self):
        """Test that ongoing calibration inhibits interactions with the instrument."""
        # Device doesn't respond during calibration
        self._transport_mock.read_until.side_effect = QMI_TimeoutException
        self._scpi_mock.ask.return_value = "0,\"No error\""

        self.instr.start_calibration()

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_get_set_external_ref_frequency(self):
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

    def test_set_sig_for_iq_mod_with_valid_signal(self):
        """Test setting the input signal for I/Q modulation with valid inputs."""
        valid_sigs = ['BAS', 'ANAL', 'DIFF']
        for sig in valid_sigs:
            self._scpi_mock.ask.return_value = "0,\"No error\""
            with self.subTest("Testing %s" % sig, sig=sig):
                self.instr.set_sig_for_iq_mod(sig)
                self._scpi_mock.write.assert_called_once_with(f":IQ:SOUR {sig}")
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
    
    def test_set_iq(self):
        """Test activating/deactivating I/Q modulation with analog signal."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        # test activating
        expected_calls = [
            call(":IQ:SOUR ANAL"),
            call(":IQ:STAT 1")
        ]

        self.instr.set_iq(True)
        self._scpi_mock.write.assert_has_calls(expected_calls)
        self._scpi_mock.reset_mock()
        # test deactivating
        expected_calls = [
            call(":IQ:SOUR ANAL"),
            call(":IQ:STAT 0")
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
                self._scpi_mock.write.assert_called_once_with(f"SOUR:FREQ:MODE {mode}")
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
        self._scpi_mock.write.assert_called_once_with(f"FREQ:STAR {freq} Hz")

    def test_set_sweep_frequency_stop(self):
        """Test setting stop frequency for sweep"""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        freq = 100.5
        self.instr.set_sweep_frequency_stop(freq)
        self._scpi_mock.write.assert_called_once_with(f"FREQ:STOP {freq} Hz")

    def test_set_sweep_frequency_step(self):
        """Test setting frequency step for sweep"""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        freq = 2
        self.instr.set_sweep_frequency_step(freq)
        self._scpi_mock.write.assert_called_once_with(f"SWE:STEP:LIN {freq} Hz")

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
                self._scpi_mock.write.assert_called_once_with(f"LIST:MODE {mode}")
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
                self._scpi_mock.write.assert_called_once_with(f"LIST:TRIG:SOUR {mode}")
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
                self._scpi_mock.write.assert_called_once_with(f"SOUR:SWE:FREQ:MODE {mode}")
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
                self._scpi_mock.write.assert_called_once_with(f"SOUR:SWE:FREQ:SPAC {mode}")
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
                self._scpi_mock.write.assert_called_once_with(f"TRIG:FSW:SOUR {mode}")
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
                self.instr.set_freq_mode(mode)
                self._scpi_mock.write.assert_called_once_with('SOUR:FREQ:MODE %s' % mode)
            self._scpi_mock.reset_mock()
    
    def test_set_freq_mode_sig_gen_with_invalid_signal(self):
        """Test setting the trigger source for the RF frequency sweep with invalid inputs."""
        valid_modes = ['BAS', 'ANAL', 'DIFF']
        for mode in valid_modes:
            self._scpi_mock.ask.return_value = "Values that can be set are CW,FIX,SWE,LIST"
            with self.subTest("Testing %s" % mode, mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_freq_mode(mode)
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
        actual_start_freq = 1.0
        actual_stop_freq = 10.0
        actual_num_steps = 10
        actual_unit_freq = "Hz"
        actual_start_pow = 11.0
        actual_stop_pow = 20.0
        actual_unit_pow = "dB"
        actual_flist = "1.0Hz,2.0Hz,3.0Hz,4.0Hz,5.0Hz,6.0Hz,7.0Hz,8.0Hz,9.0Hz,10.0Hz"
        actual_plist = "11.0dB,12.0dB,13.0dB,14.0dB,15.0dB,16.0dB,17.0dB,18.0dB,19.0dB,20.0dB"    
        expected_calls = [
            call(f"SOUR:LIST:SEL 'list_{actual_start_freq}_{actual_stop_freq}_{actual_num_steps}'"),
            call('SOUR:LIST:FREQ ' + actual_flist),
            call('SOUR:LIST:POW ' + actual_plist)
        ]

        self.instr.load_fplist(
            fstart=actual_start_freq, fstop=actual_stop_freq, funit=actual_unit_freq,
            number_of_steps=actual_num_steps, pstart=actual_start_pow, pstop=actual_stop_pow, punit=actual_unit_pow
        )

        self._scpi_mock.write.assert_has_calls(expected_calls)


if __name__ == '__main__':
    unittest.main()
