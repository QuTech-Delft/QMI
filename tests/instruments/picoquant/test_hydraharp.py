import ctypes
import time
import unittest
from unittest.mock import patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.instruments.picoquant.support._hhlib_function_signatures import _hhlib_function_signatures
from qmi.instruments.picoquant import PicoQuant_HydraHarp400

from tests.patcher import PatcherQmiContext as QMI_Context


class HydraHarpOldLibrayTestCase(unittest.TestCase):

    def test_initialize_excepts_valid_mode_but_too_old_lib(self):
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_hhlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._hydraharp: PicoQuant_HydraHarp400 = PicoQuant_HydraHarp400(
            QMI_Context("Test_hydraharp"), 'hydraharp', '1111111'
        )

        self._library_mock.HH_GetLibraryVersion.return_value = 0
        self._library_mock.HH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'2.222')
        string_buffer2 = ctypes.create_string_buffer(b'1111111')
        retvals = (string_buffer, string_buffer2)

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', side_effect=retvals):
            self._hydraharp.open()

        self._library_mock.HH_Initialize.return_value = 0
        with self.assertRaises(ValueError):
            self._hydraharp.initialize('T3', 'INTERNAL')

        self._library_mock.HH_CloseDevice.return_value = 0
        self._hydraharp.close()


class HydraHarpMethodsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_hhlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._hydraharp: PicoQuant_HydraHarp400 = PicoQuant_HydraHarp400(
            QMI_Context("test_hydraharp"), 'hydraharp', '1111111'
        )

        self._library_mock.HH_GetLibraryVersion.return_value = 0
        self._library_mock.HH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'1111111')

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', return_value=string_buffer):
            self._hydraharp.open()

    def tearDown(self) -> None:
        self._library_mock.HH_CloseDevice.return_value = 0
        self._hydraharp.close()

    def test_open_hh(self):
        """Test HydraHarp open where regular open fails and we need to get the SN with a query."""
        self._library_mock.HH_CloseDevice.return_value = 0
        self._hydraharp.close()

        self._library_mock.HH_GetLibraryVersion.return_value = 0
        self._library_mock.HH_OpenDevice.return_value = 0
        self._library_mock.HH_Initialize.return_value = 0
        self._library_mock.HH_GetSerialNumber.return_value = 0

        string_buffer_lib = ctypes.create_string_buffer(8)
        string_buffer_lib.value = b'1.23.4'
        string_buffer_sn1 = ctypes.create_string_buffer(8)
        string_buffer_sn1.value = b''
        string_buffer_sn2 = ctypes.create_string_buffer(8)
        string_buffer_sn2.value = b'1111111'

        with patch('sys.platform', 'linux1'):
            with patch('ctypes.create_string_buffer', side_effect=[string_buffer_lib, string_buffer_sn1, string_buffer_sn2]):
                self._hydraharp.open()

            self._library_mock.HH_Initialize.assert_called_once()
            self._library_mock.HH_GetSerialNumber.assert_called_once()

    def test_initialize(self):
        self._library_mock.HH_Initialize.return_value = 0
        self._hydraharp.initialize('T2', 'INTERNAL')

    def test_initialize_excepts_measurement_running(self):
        self._library_mock.HH_Initialize.return_value = 0
        self._library_mock.HH_StartMeas.return_value = 0
        self._hydraharp.start_measurement(1000)
        with self.assertRaises(QMI_InvalidOperationException):
            self._hydraharp.initialize('T2', 'INTERNAL')

    def test_initialize_excepts_invalid_mode(self):
        self._library_mock.HH_Initialize.return_value = 0
        with self.assertRaises(ValueError):
            self._hydraharp.initialize('T4', 'INTERNAL')

    def test_initialize_raises_libraryError(self):

        self._library_mock.HH_Initialize.return_value = -1
        self._library_mock.HH_GetErrorString.return_value = 0

        error_string = 'error string'
        ctype_err_string = ctypes.create_string_buffer(error_string.encode('ASCII'), 40)

        with self.assertRaises(QMI_InstrumentException), \
                patch('ctypes.create_string_buffer', return_value=ctype_err_string):

            self._hydraharp.initialize('T2', 'INTERNAL')

    def test_get_features(self):
        self._library_mock.HH_GetFeatures.return_value = 0
        bitpattern = 0x0001

        with patch('ctypes.c_int', return_value=ctypes.c_int(bitpattern)):
            features = self._hydraharp.get_features()

        self.assertIn('DLL', features)

    def test_module_info(self):
        self._library_mock.HH_GetNumOfModules.return_value = 0
        self._library_mock.HH_GetModuleInfo.return_value = 0
        modules = 2
        expected_module_info = [(1, 2), (3, 4)]
        values = [modules, 1, 2, 3, 4]
        patcher = patch('ctypes.c_int', side_effect=[ctypes.c_int(value) for value in values])

        with patcher:
            module_info = self._hydraharp.get_module_info()

        for actual, expected in zip(module_info, expected_module_info):
            self.assertTupleEqual(actual, expected)

    def test_get_debug_info(self):
        self._library_mock.HH_GetHardwareDebugInfo.return_value = 0
        expected_debug_info = 'foo bar baz'
        string_buffer = ctypes.create_string_buffer(expected_debug_info.encode('ASCII'), 65536)

        with patch('ctypes.create_string_buffer', return_value=string_buffer):
            debug_info = self._hydraharp.get_debug_info()

        self.assertEqual(debug_info, expected_debug_info)

    def test_set_measurement_control(self):
        self._library_mock.HH_SetMeasControl.return_value = 0
        self._hydraharp.set_measurement_control('SINGLESHOT_CTC', 'RISING', 'FALLING')
        self._library_mock.HH_SetMeasControl.assert_called_once_with(0, 0, 1, 0)

    def test_get_flags(self):
        self._library_mock.HH_GetFlags.return_value = 0
        flag_bitset = 0b01

        with patch('ctypes.c_int', return_value=ctypes.c_int(flag_bitset)):
            flags = self._hydraharp.get_flags()

        self.assertIn("OVERFLOW", flags)

    def test_get_warnings(self):
        self._library_mock.HH_GetWarnings.return_value = 0
        flag_bitset = 0b01

        with patch('ctypes.c_int', return_value=ctypes.c_int(flag_bitset)):
            flags = self._hydraharp.get_warnings()

        self.assertIn("SYNC_RATE_ZERO", flags)

    def test_set_sync_channel_offset(self):

        self._library_mock.HH_SetSyncChannelOffset.return_value = 0
        self._hydraharp.set_sync_channel_offset(99999)
        self._library_mock.HH_SetSyncChannelOffset.assert_called_once_with(0, 99999)

    def test_set_marker_enable(self):
        self._library_mock.HH_SetMarkerEnable.return_value = 0
        self._hydraharp.set_marker_enable(True, False, True, False)
        self._library_mock.HH_SetMarkerEnable.assert_called_once_with(0, 1, 0, 1, 0)

    def test_set_marker_holdoff_time(self):
        self._library_mock.HH_SetMarkerHoldoffTime.return_value = 0
        self._hydraharp.set_marker_holdoff_time(123456)
        self._library_mock.HH_SetMarkerHoldoffTime.assert_called_once_with(0, 123456)

    def test_calibrate(self):
        self._library_mock.HH_Calibrate.return_value = 0
        self._hydraharp.calibrate()
        self._library_mock.HH_Calibrate.assert_called_once_with(0)

    def test_set_sync_cfd(self):
        self._library_mock.HH_SetSyncCFD.return_value = 0
        self._hydraharp.set_sync_cfd(100, 30)
        self._library_mock.HH_SetSyncCFD.assert_called_once_with(0, 100, 30)

    def test_input_cfd(self):
        self._library_mock.HH_SetInputCFD.return_value = 0
        self._hydraharp.set_input_cfd(2, 100, 30)
        self._library_mock.HH_SetInputCFD.assert_called_once_with(0, 2, 100, 30)

    def test_read_fifo(self):
        self._library_mock.HH_ReadFiFo.return_value = 0
        self._library_mock.HH_StartMeas.return_value = 0
        self._library_mock.HH_StopMeas.return_value = 0
        self._library_mock.HH_Initialize.return_value = 0

        self._hydraharp.initialize('T2', 'INTERNAL')
        self._hydraharp.start_measurement(1)
        time.sleep(0.01)
        self._hydraharp.stop_measurement()

        self._library_mock.HH_ReadFiFo.assert_called()
        self.assertEqual(len(self._library_mock.HH_ReadFiFo.call_args_list[0][0]), 4)


if __name__ == '__main__':
    unittest.main()
