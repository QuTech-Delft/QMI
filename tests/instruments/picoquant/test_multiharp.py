import ctypes
import time
import unittest
from fractions import Fraction
from unittest.mock import patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.instruments.picoquant.support._mhlib_function_signatures import _mhlib_function_signatures
from qmi.instruments.picoquant import PicoQuant_MultiHarp150

from tests.patcher import PatcherQmiContext as QMI_Context


class MultiHarpOldLibrayTestCase(unittest.TestCase):

    def test_initialize_excepts_valid_mode_but_too_old_lib(self):
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_mhlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._multiharp: PicoQuant_MultiHarp150 = PicoQuant_MultiHarp150(
            QMI_Context("Test_multiharp"), 'multiharp', '1111111'
        )

        self._library_mock.MH_GetLibraryVersion.return_value = 0
        self._library_mock.MH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'2.222')
        string_buffer2 = ctypes.create_string_buffer(b'1111111')
        retvals = (string_buffer, string_buffer2)

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', side_effect=retvals):
            self._multiharp.open()

        self._library_mock.MH_Initialize.return_value = 0
        with self.assertRaises(ValueError):
            self._multiharp.initialize('T3', 'INTERNAL')

        self._library_mock.MH_CloseDevice.return_value = 0
        self._multiharp.close()


class MultiharpMethodsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_mhlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._multiharp: PicoQuant_MultiHarp150 = PicoQuant_MultiHarp150(
            QMI_Context("test_multiharp"), 'multiharp', '1111111'
        )

        self._library_mock.MH_GetLibraryVersion.return_value = 0
        self._library_mock.MH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'1111111')

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', return_value=string_buffer):
            self._multiharp.open()

    def tearDown(self) -> None:
        self._library_mock.MH_CloseDevice.return_value = 0
        self._multiharp.close()

    def test_open_mh(self):
        """Test MultiHarp open where regular open fails and we need to get the SN with a query."""
        self._library_mock.MH_CloseDevice.return_value = 0
        self._multiharp.close()

        self._library_mock.MH_GetLibraryVersion.return_value = 0
        self._library_mock.MH_OpenDevice.return_value = 0
        self._library_mock.MH_Initialize.return_value = 0
        self._library_mock.MH_GetSerialNumber.return_value = 0

        string_buffer_lib = ctypes.create_string_buffer(8)
        string_buffer_lib.value = b'1.23.4'
        string_buffer_sn1 = ctypes.create_string_buffer(8)
        string_buffer_sn1.value = b''
        string_buffer_sn2 = ctypes.create_string_buffer(8)
        string_buffer_sn2.value = b'1111111'

        with patch('sys.platform', 'linux1'):
            with patch('ctypes.create_string_buffer', side_effect=[string_buffer_lib, string_buffer_sn1, string_buffer_sn2]):
                self._multiharp.open()

            self._library_mock.MH_Initialize.assert_called_once()
            self._library_mock.MH_GetSerialNumber.assert_called_once()

    def test_initialize(self):

        self._library_mock.MH_Initialize.return_value = 0

        self._multiharp.initialize('T2', 'INTERNAL')

    def test_initialize_excepts_measurement_running(self):
        self._library_mock.MH_Initialize.return_value = 0
        self._library_mock.MH_StartMeas.return_value = 0
        self._multiharp.start_measurement(1000)
        with self.assertRaises(QMI_InvalidOperationException):
            self._multiharp.initialize('T2', 'INTERNAL')

    def test_initialize_excepts_invalid_mode(self):
        self._library_mock.MH_Initialize.return_value = 0
        with self.assertRaises(ValueError):
            self._multiharp.initialize('T4', 'INTERNAL')

    def test_initialise_raises_libraryError(self):

        self._library_mock.MH_Initialize.return_value = -1
        self._library_mock.MH_GetErrorString.return_value = 0

        error_string = 'error string'
        ctype_err_string = ctypes.create_string_buffer(error_string.encode('ASCII'), 40)

        with self.assertRaises(QMI_InstrumentException), \
                patch('ctypes.create_string_buffer', return_value=ctype_err_string):

            self._multiharp.initialize('T2', 'INTERNAL')

    def test_get_hardware_info(self):

        self._library_mock.MH_GetHardwareInfo.return_value = 0
        expected_hardware_info = 'abcdefgh', '12345678', '23456789'

        model_string_buffer = ctypes.create_string_buffer(expected_hardware_info[0].encode('ASCII'), 24)
        partno = ctypes.create_string_buffer(expected_hardware_info[1].encode('ASCII'), 8)
        version = ctypes.create_string_buffer(expected_hardware_info[2].encode('ASCII'), 8)

        with patch('ctypes.create_string_buffer', side_effect=[model_string_buffer, partno, version]):
            hardware_info = self._multiharp.get_hardware_info()

        self.assertTupleEqual(hardware_info, expected_hardware_info)

    def test_get_features(self):

        self._library_mock.MH_GetFeatures.return_value = 0

        bitpattern = 0x0009

        with patch('ctypes.c_int', return_value=ctypes.c_int(bitpattern)):
            features = self._multiharp.get_features()

        self.assertIn('DLL', features)
        self.assertIn('LOWRES', features)

    def test_module_info(self):
        self._library_mock.MH_GetNumOfModules.return_value = 0
        self._library_mock.MH_GetModuleInfo.return_value = 0

        expected_module_info = [(1, 2), (3, 4)]

        values = [2, 1, 2, 3, 4]
        patcher = patch('ctypes.c_int', side_effect=[ctypes.c_int(value) for value in values])

        with patcher:
            module_info = self._multiharp.get_module_info()

        for actual, expected in zip(module_info, expected_module_info):
            self.assertTupleEqual(actual, expected)

    def test_get_debug_info(self):
        self._library_mock.MH_GetDebugInfo.return_value = 0
        expected_debug_info = 'foo bar baz'

        string_buffer = ctypes.create_string_buffer(expected_debug_info.encode('ASCII'), 65536)

        with patch('ctypes.create_string_buffer', return_value=string_buffer):
            debug_info = self._multiharp.get_debug_info()

        self.assertEqual(debug_info, expected_debug_info)

    def test_set_sync_channel_offset(self):

        self._library_mock.MH_SetSyncChannelOffset.return_value = 0
        self._multiharp.set_sync_channel_offset(99999)
        self._library_mock.MH_SetSyncChannelOffset.assert_called_once_with(0, 99999)

    def test_set_sync_dead_time(self):

        self._library_mock.MH_SetSyncDeadTime.return_value = 0
        self._multiharp.set_sync_dead_time(0, 160000)
        self._library_mock.MH_SetSyncDeadTime.assert_called_once_with(0, 0, 160000)

    def test_set_input_edge_trigger(self):

        self._library_mock.MH_SetInputEdgeTrg.return_value = 0
        self._multiharp.set_input_edge_trigger(1, 1000, 'RISING')
        self._library_mock.MH_SetInputEdgeTrg.assert_called_once_with(0, 1, 1000, 1)

    def test_set_input_channel_dead_time(self):

        self._library_mock.MH_SetInputDeadTime.return_value = 0
        self._multiharp.set_input_channel_dead_time(1, 0, 800)
        self._library_mock.MH_SetInputDeadTime.assert_called_once_with(0, 1, 0, 800)

    def test_set_measurement_control(self):

        self._library_mock.MH_SetMeasControl.return_value = 0
        self._multiharp.set_measurement_control('SINGLESHOT_CTC', 'RISING', 'FALLING')
        self._library_mock.MH_SetMeasControl.assert_called_once_with(0, 0, 1, 0)

    def test_set_trigger_output(self):

        self._library_mock.MH_SetTriggerOutput.return_value = 0
        self._multiharp.set_trigger_output(16777215)
        self._library_mock.MH_SetTriggerOutput.assert_called_once_with(0, 16777215)

    def test_get_all_count_rates(self):

        self._library_mock.MH_GetNumOfInputChannels.return_value = 0
        self._library_mock.MH_GetAllCountRates.return_value = 0

        num_channels = 4
        expected_sync_rate = 10
        expected_input_rates = (11, 12, 13, 14)

        values = (num_channels, expected_sync_rate, *expected_input_rates)
        with patch('ctypes.c_int', side_effect=[ctypes.c_int(value) for value in values]):
            sync_rate, input_rates = self._multiharp.get_all_count_rates()

        self.assertEqual(sync_rate, expected_sync_rate)

    def test_get_flags(self):

        self._library_mock.MH_GetFlags.return_value = 0

        flag_bitset = 0b01

        with patch('ctypes.c_int', return_value=ctypes.c_int(flag_bitset)):
            flags = self._multiharp.get_flags()

        self.assertIn("OVERFLOW", flags)

    def test_get_warnings(self):

        self._library_mock.MH_GetWarnings.return_value = 0

        flag_bitset = 0b01

        with patch('ctypes.c_int', return_value=ctypes.c_int(flag_bitset)):
            flags = self._multiharp.get_warnings()

        self.assertIn("SYNC_RATE_ZERO", flags)

    def test_set_sync_edge_trigger(self):

        self._library_mock.MH_SetSyncEdgeTrg.return_value = 0
        self._multiharp.set_sync_edge_trigger(-1200, 'RISING')
        self._library_mock.MH_SetSyncEdgeTrg.assert_called_once_with(0, -1200, 1)

    def test_get_start_time(self):

        self._library_mock.MH_GetStartTime.return_value = 0

        with patch('ctypes.c_uint', return_value=ctypes.c_uint(1)):
            start_time = self._multiharp.get_start_time()

        self.assertEqual(start_time, Fraction((1 << 64) | (1 << 32) | 1, 1000000000000))

    def test_get_start_time2(self):

        self._library_mock.MH_GetStartTime.return_value = 0

        picoseconds = (10 << 64) | (9 << 32) | 8

        expected_start_time = Fraction(picoseconds, 1000000000000)

        values = (10, 9, 8)
        with patch('ctypes.c_uint', side_effect=[ctypes.c_uint(value) for value in values]):
            start_time = self._multiharp.get_start_time()

        self.assertEqual(start_time, expected_start_time)

    def test_get_histogram(self):
        """Test on get_histogram function without 'clear' input variable"""
        self._library_mock.MH_GetHistogram.return_value = 0

        self._multiharp.get_histogram(1, 0)
        self._library_mock.MH_GetHistogram.assert_called()
        self.assertEqual(len(self._library_mock.MH_GetHistogram.call_args_list[0][0]), 4)

    def test_get_all_histograms(self):
        """Test on get_all_histograms function."""
        self._library_mock.MH_GetNumOfInputChannels.return_value = 0
        self._library_mock.MH_GetAllHistograms.return_value = 0
        no_of_channels = 2
        # Mock with no_of_channels that will have 65536 data entry points
        with patch('ctypes.c_int', return_value=ctypes.c_int(no_of_channels)):
            retval = self._multiharp.get_all_histograms()
            self.assertTupleEqual(retval.shape, (no_of_channels, 65536))
            self._library_mock.MH_GetAllHistograms.assert_called()
            self.assertEqual(len(self._library_mock.MH_GetAllHistograms.call_args_list[0][0]), 2)

    def test_read_fifo(self):
        self._library_mock.MH_ReadFiFo.return_value = 0
        self._library_mock.MH_StartMeas.return_value = 0
        self._library_mock.MH_StopMeas.return_value = 0
        self._library_mock.MH_Initialize.return_value = 0

        self._multiharp.initialize('T2', 'INTERNAL')
        self._multiharp.start_measurement(1)
        time.sleep(0.01)
        self._multiharp.stop_measurement()

        self._library_mock.MH_ReadFiFo.assert_called()
        self.assertEqual(len(self._library_mock.MH_ReadFiFo.call_args_list[0][0]), 3)


if __name__ == '__main__':
    unittest.main()
