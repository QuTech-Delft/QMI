import unittest
from unittest.mock import Mock, MagicMock, patch
import os

import qmi
from qmi.instruments.jpe import Jpe_CPSC, StatusPositionControl
from qmi.core.exceptions import QMI_InstrumentException

readlines_mock = Mock()


class PopenMock:
    stdin = Mock(write=MagicMock())
    stdout = Mock(readlines=readlines_mock)

    def __init__(self, args="wine", stdin=None, stdout=None, cwd=None, env=None):
        pass

    def wait(self):
        pass


class RunMock:
    stdin = Mock(write=MagicMock())
    stdout = ""
    arg_list = []

    def __init__(self, arg_list, stdin=None, stdout=None, encoding=None, check=False):
        self.arg_list = arg_list

    def wait(self):
        pass


class InstanceCreationTestCase(unittest.TestCase):

    def test_default_directory(self):
        """Test that the behaviour is as expected when using default directory while creating instance."""
        if os.path.isdir(Jpe_CPSC.DEFAULT_CPSC_DIR):
            expected_sn = "@1234-567890"
            expected_dir = Jpe_CPSC.DEFAULT_CPSC_DIR
            jpe = Jpe_CPSC(qmi.core.context.QMI_Context("JPE"), "JPE test", expected_sn[1:])  # strip '@' from SN
            self.assertEqual(jpe._serial_number, expected_sn)
            self.assertEqual(jpe._cpsp_dir, expected_dir)

        else:
            with self.assertRaises(QMI_InstrumentException):
                Jpe_CPSC(qmi.core.context.QMI_Context("JPE"), "JPE test", "1234")

    def test_custom_directory(self):
        """Test that a custom directory, set as local directory, does run without exceptions"""
        expected_sn = "@1234-567890"
        expected_dir = os.path.dirname(__file__)
        expected_cmd = os.path.join(expected_dir, "cacli.exe")
        jpe = Jpe_CPSC(qmi.core.context.QMI_Context("JPE"), "JPE test", expected_sn[1:], expected_dir)
        self.assertEqual(jpe._serial_number, expected_sn)
        self.assertEqual(jpe._cpsp_dir, expected_dir)
        self.assertEqual(jpe._cpsp_cmd, expected_cmd)

    def test_faulty_custom_directory(self):
        """Test that a custom directory that does not exist raises an exception"""
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            Jpe_CPSC(qmi.core.context.QMI_Context("JPE"), "JPE test", "1234", r"Q:\utech\QID\QMI")


@patch("sys.platform", "linux1")
class MethodsLinuxTestCase(unittest.TestCase):

    @patch("sys.platform", "linux1")
    def setUp(self):
        # First mock is for the Linux WinE opener
        readlines_mock.side_effect = [["b".encode(), "l".encode(), "a".encode()]]
        self._popen_patcher = patch("qmi.instruments.jpe.cpsc.Popen", new=PopenMock)
        self._popen_patcher.start()
        self.sn = "@1234-567890"
        path = os.path.dirname(__file__)
        self.cmd = os.path.join(path, "cacli.exe")
        self.jpe = Jpe_CPSC(qmi.core.context.QMI_Context("JPE"), "JPE test", self.sn, path)

    @patch("sys.platform", "linux1")
    def tearDown(self):
        if self.jpe._is_open:
            self.jpe.close()

        self._popen_patcher.stop()

    def test_01_open(self):
        """Test opening the instrument in Linux."""
        self.jpe.open()
        self.assertTrue(self.jpe._is_open)

    @patch("sys.platform", "linux1")
    def test_02_close(self):
        """Test closing the instrument in Linux."""
        self.jpe.open()
        self.jpe.close()
        self.assertFalse(self.jpe._is_open)

    def test_03_get_idn(self):
        """Test that the IDN request is correctly made and returns QMI_InstrumentIdentification instance."""
        expected_vendor = "JPE"
        expected_model = "CPSC"
        expected_serial = self.sn
        expected_version = "bla"

        self.jpe.open()
        val = self.jpe.get_idn()
        self.assertEqual(type(val), qmi.core.instrument.QMI_InstrumentIdentification)
        self.assertEqual(val.vendor, expected_vendor)
        self.assertEqual(val.model, expected_model)
        self.assertEqual(val.serial, expected_serial)
        self.assertEqual(val.version, expected_version)
        self.assertEqual(self.jpe._version_string, expected_version)

    def test_04_move(self):
        """See that the move command works as expected on Linux."""
        expected_call = bytes(f"{self.cmd} {self.sn} ".encode()) + b"MOV 2 0 10 100 0 295 CBS10-RLS 1.0\r\n"
        response = "Actuating the stage."
        # self._popen_patcher.stop()
        readlines_mock.side_effect = [[c.encode() for c in response]]
        # self._popen_patcher = patch("qmi.instruments.jpe.cpsc.Popen", new=PopenMock)
        # self._popen_patcher.start()
        self.jpe.open()
        self.jpe.move(2, 0)  # Utilize the default values of the rest of the arguments
        self.jpe._proc_popen.stdin.write.assert_called_with(expected_call)


@patch("sys.platform", "win32")
class MethodsWindowsOnlyTestCase(unittest.TestCase):

    @patch("sys.platform", "win32")
    def setUp(self):
        self._run_patcher = patch("qmi.instruments.jpe.cpsc.run", new=RunMock)
        self._run_patcher.start()
        self.sn = "@1234-567890"
        path = os.path.dirname(__file__)
        self.cmd = os.path.join(path, "cacli.exe")
        self.jpe = Jpe_CPSC(qmi.core.context.QMI_Context("JPE"), "JPE test", self.sn, path)

    @patch("sys.platform", "win32")
    def tearDown(self):
        if self.jpe._is_open:
            self.jpe.close()

        self._run_patcher.stop()

    def test_01_open(self):
        """Test opening the instrument in Windows."""
        self.jpe.open()
        self.assertTrue(self.jpe._is_open)

    def test_02_close(self):
        """Test closing the instrument in Windows."""
        self.jpe.open()
        self.jpe.close()
        self.assertFalse(self.jpe._is_open)

    def test_03_get_idn(self):
        """Test that the IDN request is correctly made and returns QMI_InstrumentIdentification instance."""
        expected_vendor = "JPE"
        expected_model = "CPSC"
        expected_serial = self.sn
        expected_version = "vla"
        self._run_patcher.new.stdout = "vla"

        self.jpe.open()
        val = self.jpe.get_idn()
        self.assertEqual(type(val), qmi.core.instrument.QMI_InstrumentIdentification)
        self.assertEqual(val.vendor, expected_vendor)
        self.assertEqual(val.model, expected_model)
        self.assertEqual(val.serial, expected_serial)
        self.assertEqual(val.version, expected_version)
        self.assertEqual(self.jpe._version_string, expected_version)

    def test_04_get_all_modules_info(self):
        """Test getting all module information."""
        expected_module_a = "moduleA"
        expected_module_b = "moduleB"
        self._run_patcher.new.stdout = f"{expected_module_a},{expected_module_b}"
        self.jpe.open()
        val = self.jpe.get_info_all_modules()
        self.assertEqual(val[0], expected_module_a)
        self.assertEqual(val[1], expected_module_b)

    def test_05_get_module_info(self):
        """Test getting specific module info."""
        expected_module_a = "moduleA"
        self._run_patcher.new.stdout = f" {expected_module_a} "  # see that spaces are also stripped
        self.jpe.open()
        val = self.jpe.get_info_module(1)
        self.assertEqual(val, expected_module_a)

    def test_06_request_fail_safe_state(self):
        """See that the requesting the error works and a string is returned."""
        expected_error = "No Error"
        self._run_patcher.new.stdout = f" {expected_error}"  # see that spaces are also stripped
        self.jpe.open()
        val = self.jpe.request_fail_safe_state("1")
        self.assertEqual(val, expected_error)

    def test_07_move(self):
        """See that the move command works as expected on Windows."""
        expected_args = [f"{self.cmd}", f"{self.sn}", "MOV", "2", "0", "10", "100", "0", "295", "CBS10-RLS", "1.0"]
        response = "Actuating the stage."
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.move(2, 0)  # Utilize the default values of the rest of the arguments
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_08_stop(self):
        """Test stop command."""
        address = 1
        expected_args = [f"{self.cmd}", f"{self.sn}", "STP", f"{address}"]
        response = "Stopping the stage."
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.stop(address)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_09_enable_scan_mode(self):
        """Test enable scan mode command."""
        address = 1
        value = 1023
        expected_args = [f"{self.cmd}", f"{self.sn}", "SDC", f"{address}", f"{value}"]
        response = "Scan mode enabled."
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.enable_scan_mode(address, value)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_10_use_external_input(self):
        """Test setting external input mode."""
        address = 1
        direction = 0
        expected_args = [f"{self.cmd}", f"{self.sn}", "EXT", f"{address}", f"{direction}", "10", "100", "295",
                         "CBS10-RLS", "1.0"]
        response = "External mode enabled."
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.use_external_input(address, direction)  # Utilize the default values of the rest of the arguments
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_11_get_current_position(self):
        """Test that current position value is returned as a float."""
        address = 3
        channel = 2
        expected_response = 1.0
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.get_current_position(address, channel)
        self.assertEqual(pos, expected_response)

    def test_12_get_current_position_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        channel = 2
        unexpected_response = "ERROR: SomeError"
        expected_error_msg = f"Erroneous response from position query SDC {address} {channel} CBS10-RLS:" +\
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.get_current_position(address, channel)
            self.assertEqual(exc[2], expected_error_msg)

    def test_13_get_current_position_of_all_3_channels(self):
        """Test that current position values are returned as a list of floats."""
        address = 3
        expected_response = [1.0, 2.0, 3.0]
        response = f"{expected_response[0]},{expected_response[1]},{expected_response[2]}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.get_current_position_of_all_3_channels(address)
        self.assertListEqual(pos, expected_response)

    def test_14_get_current_position_of_all_3_channels_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        unexpected_response = "1.0,3.0,ERROR: SomeError"
        expected_error_msg = f"Erroneous response from position query PGVA {address} CBS10-RLS:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.get_current_position_of_all_3_channels(address)
            self.assertEqual(exc[2], expected_error_msg)

    def test_15_set_negative_end_stop(self):
        """Test setting negative end stop command."""
        address = 3
        channel = 2
        expected_args = [f"{self.cmd}", f"{self.sn}", "MIS", f"{address}", f"{channel}"]
        expected_response = "Minimum position set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.set_negative_end_stop(address, channel)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_16_set_positive_end_stop(self):
        """Test setting positive end stop command."""
        address = 3
        channel = 2
        expected_args = [f"{self.cmd}", f"{self.sn}", "MAS", f"{address}", f"{channel}"]
        expected_response = "Maximum position set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.set_positive_end_stop(address, channel)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_17_read_negative_end_stop(self):
        """Test reading negative end stop value command returns float."""
        address = 3
        channel = 2
        expected_response = -1.0E-7
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.read_negative_end_stop(address, channel)
        self.assertEqual(pos, expected_response)

    def test_18_read_negative_end_stop_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        channel = 2
        unexpected_response = "Minimum and maximum end-stops reset."
        expected_error_msg = f"Erroneous response from position query MIR {address} {channel} CBS10-RLS:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.read_negative_end_stop(address, channel)
            self.assertEqual(exc[2], expected_error_msg)

    def test_19_read_positive_end_stop(self):
        """Test reading positive end stop value command returns float."""
        address = 3
        channel = 2
        expected_response = 1.0E-7
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.read_positive_end_stop(address, channel)
        self.assertEqual(pos, expected_response)

    def test_20_read_positive_end_stop_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        channel = 2
        unexpected_response = "Minimum and maximum end-stops reset."
        expected_error_msg = f"Erroneous response from position query MAR {address} {channel} CBS10-RLS:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.read_positive_end_stop(address, channel)
            self.assertEqual(exc[2], expected_error_msg)

    def test_21_reset_end_stops(self):
        """Test resetting the end stop values command."""
        address = 3
        channel = 2
        expected_args = [f"{self.cmd}", f"{self.sn}", "MMR", f"{address}", f"{channel}"]
        expected_response = "Minimum and maximum end-stops reset."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.reset_end_stops(address, channel)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_22_set_excitation_duty_cycle(self):
        """Test setting excitation duty cycle command."""
        address = 3
        duty = 30
        expected_args = [f"{self.cmd}", f"{self.sn}", "EXS", f"{address}", f"{duty}"]
        expected_response = "Excitation duty cycle set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.set_excitation_duty_cycle(address, duty)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_23_read_excitation_duty_cycle(self):
        """Test reading excitation duty cycle command returns integer."""
        address = 3
        expected_response = 30
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.read_excitation_duty_cycle(address)
        self.assertEqual(pos, expected_response)

    def test_24_read_excitation_duty_cycle_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        unexpected_response = "30.0"
        expected_error_msg = f"Erroneous response from position query EXR {address}:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.read_excitation_duty_cycle(address)
            self.assertEqual(exc[2], expected_error_msg)

    def test_25_save_rsm_setting(self):
        """Test save RSM setting command."""
        address = 3
        expected_args = [f"{self.cmd}", f"{self.sn}", "RSS", f"{address}"]
        expected_response = "Settings stored in flash."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.save_rsm_settings(address)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_26_get_current_counter_value(self):
        """Test get current counter value command returns an integer."""
        address = 3
        channel = 2
        expected_response = 12345
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.get_current_counter_value(address, channel)
        self.assertEqual(pos, expected_response)

    def test_27_get_current_counter_value_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        channel = 2
        unexpected_response = "1234.5"
        expected_error_msg = f"Erroneous response from position query CGV {address} {channel}:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.get_current_counter_value(address, channel)
            self.assertEqual(exc[2], expected_error_msg)

    def test_28_reset_counter_value(self):
        """Test reset counter value command."""
        address = 3
        channel = 2
        expected_args = [f"{self.cmd}", f"{self.sn}", "CSZ", f"{address}", f"{channel}"]
        expected_response = "Position counter set to 0."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.reset_counter_value(address, channel)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_29_get_current_encoder_signal_value(self):
        """Test get current encoder signal value command returns an integer"""
        address = 3
        channel = 2
        expected_response = 123
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        pos = self.jpe.get_current_encoder_signal_value(address, channel)
        self.assertEqual(pos, expected_response)

    def test_30_get_current_encoder_signal_value_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        channel = 2
        unexpected_response = "1.23"
        expected_error_msg = f"Erroneous response from position query DGV {address} {channel}:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.get_current_encoder_signal_value(address, channel)
            self.assertEqual(exc[2], expected_error_msg)

    def test_31_auto_oem_calibration(self):
        """Test auto OEM calibration command."""
        address = 1
        channel = 0
        cadm2 = 6
        temp = 298
        expected_args = [f"{self.cmd}", f"{self.sn}", "OEMC", f"{address}", f"{channel}", f"{cadm2}", f"{temp}",
                         "CBS10-RLS"]
        response = "Channel calibrated."
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.auto_oem_calibration(address,channel, cadm2, temp)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_32_request_calibration_values(self):
        """Test requesting calibration values command returns a list of integers."""
        address = 3
        channel = 2
        expected_response = [1, 12, 123]
        response = f"{expected_response[0]},{expected_response[1]},{expected_response[2]}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        values = self.jpe.request_calibration_values(address, channel)
        self.assertListEqual(values, expected_response)

    def test_33_request_calibration_values_excepts(self):
        """See that an exception is raised with an erroneous response."""
        address = 3
        channel = 2
        unexpected_response = "1,12.0,123"
        expected_error_msg = f"Erroneous response from calibration value query MLS {address} {channel}:" + \
                             f"{unexpected_response}"
        response = f"{unexpected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.jpe.request_calibration_values(address, channel)
            self.assertEqual(exc[2], expected_error_msg)

    def test_34_set_detector_gain(self):
        """Test set detector gain command."""
        address = 3
        channel = 2
        gain = 30
        expected_args = [f"{self.cmd}", f"{self.sn}", "DSG", f"{address}", f"{channel}", f"{gain}"]
        expected_response = "Detector gain set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.set_detector_gain(address, channel, gain)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_35_set_upper_threshold(self):
        """Test setting upper threshold command."""
        address = 3
        channel = 2
        ut = 130
        expected_args = [f"{self.cmd}", f"{self.sn}", "DSH", f"{address}", f"{channel}", f"{ut}"]
        expected_response = "Detector upper threshold set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.set_upper_threshold(address, channel, ut)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_36_set_lower_threshold(self):
        """Test setting lower threshold."""
        address = 3
        channel = 2
        lt = 13
        expected_args = [f"{self.cmd}", f"{self.sn}", "DSL", f"{address}", f"{channel}", f"{lt}"]
        expected_response = "Detector lower threshold set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.set_lower_threshold(address, channel, lt)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_37_save_detector_settings(self):
        """Test saving detector settings command."""
        address = 2
        expected_args = [f"{self.cmd}", f"{self.sn}", "MSS", f"{address}"]
        expected_response = "Detector settings stored in flash."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.save_detector_settings(address)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_38_enable_servodrive(self):
        """Test enabling servo drive command."""
        freq = 10
        stage = "Stage"
        df = 2.0
        temp = 4
        expected_args = [f"{self.cmd}", f"{self.sn}", "FBEN", f"{stage}", f"{freq}", f"{stage}", f"{freq}", f"{stage}",
                         f"{freq}", f"{df}", f"{temp}"]
        expected_response = "Control loop enabled."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.enable_servodrive(stage, freq, stage, freq, stage, freq, df, temp)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_39_disable_servodrive(self):
        """Test disabling servo drive command."""
        expected_args = [f"{self.cmd}", f"{self.sn}", "FBXT"]
        expected_response = "Control loop disabled."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.disable_servodrive()
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_40_move_to_setpoint(self):
        """Test move to setpoint command."""
        sp1 = 1E-9
        sp2 = 2E-9
        sp3 = 3E-9
        abs = 0
        expected_args = [f"{self.cmd}", f"{self.sn}", "FBCS", f"{sp1}", f"{abs}", f"{sp2}", f"{abs}", f"{sp3}",
                         f"{abs}"]
        expected_response = "Control loop setpoints set."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.move_to_setpoint(sp1, sp2, sp3, abs)
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_41_emergency_stop(self):
        """Test emergency stop command."""
        expected_args = [f"{self.cmd}", f"{self.sn}", "FBES"]
        expected_response = "Control loop emergency stop enabled."
        response = f"{expected_response}"
        self._run_patcher.new.stdout = response
        self.jpe.open()
        self.jpe.emergency_stop()
        self.assertEqual(self.jpe._proc_run.arg_list, expected_args)

    def test_42_get_status_position_control(self):
        """Test get status position control returns a string of comma-separated statuses"""
        response = "1,0,0,0,0,-8528,-11864,42770"
        self._run_patcher.new.stdout = response
        expected_status = StatusPositionControl(*map(int, response.split(",")))
        self.jpe.open()
        status = self.jpe.get_status_position_control()
        self.assertEqual(status, expected_status)


if __name__ == '__main__':
    unittest.main()
