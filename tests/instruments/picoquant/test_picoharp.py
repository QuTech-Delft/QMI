import ctypes
import time
import unittest
from unittest.mock import patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.instruments.picoquant.support._phlib_function_signatures import _phlib_function_signatures
from qmi.instruments.picoquant import PicoQuant_PicoHarp300

from tests.patcher import PatcherQmiContext as QMI_Context


class PicoHarpOldLibrayTestCase(unittest.TestCase):

    def test_initialize_excepts_valid_mode_but_too_old_lib(self):
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_phlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._picoharp: PicoQuant_PicoHarp300 = PicoQuant_PicoHarp300(
            QMI_Context("test_picoharp"), 'picoharp', '1111111'
        )

        self._library_mock.PH_GetLibraryVersion.return_value = 0
        self._library_mock.PH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'2.222')
        string_buffer2 = ctypes.create_string_buffer(b'1111111')
        retvals = (string_buffer, string_buffer2)

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', side_effect=retvals):
            self._picoharp.open()

        self._library_mock.PH_Initialize.return_value = 0
        with self.assertRaises(ValueError):
            self._picoharp.initialize('T3')

        self._library_mock.PH_CloseDevice.return_value = 0
        self._picoharp.close()


class PicoHarpMethodsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_phlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._picoharp: PicoQuant_PicoHarp300 = PicoQuant_PicoHarp300(
            QMI_Context("test_picoharp"), 'picoharp', '1111111'
        )

        self._library_mock.PH_GetLibraryVersion.return_value = 0
        self._library_mock.PH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'1111111')

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', return_value=string_buffer):
            self._picoharp.open()

    def tearDown(self) -> None:
        self._library_mock.PH_CloseDevice.return_value = 0
        self._picoharp.close()

    def test_open_ph(self):
        """Test PicoHarp open where regular open fails and we need to get the SN with a query."""
        self._library_mock.PH_CloseDevice.return_value = 0
        self._picoharp.close()

        self._library_mock.PH_GetLibraryVersion.return_value = 0
        self._library_mock.PH_OpenDevice.return_value = 0
        self._library_mock.PH_Initialize.return_value = 0
        self._library_mock.PH_GetSerialNumber.return_value = 0

        string_buffer_lib = ctypes.create_string_buffer(8)
        string_buffer_lib.value = b'1.23.4'
        string_buffer_sn1 = ctypes.create_string_buffer(8)
        string_buffer_sn1.value = b''
        string_buffer_sn2 = ctypes.create_string_buffer(8)
        string_buffer_sn2.value = b'1111111'

        with patch('sys.platform', 'linux1'):
            with patch('ctypes.create_string_buffer', side_effect=[string_buffer_lib, string_buffer_sn1, string_buffer_sn2]):
                self._picoharp.open()

            self._library_mock.PH_Initialize.assert_called_once()
            self._library_mock.PH_GetSerialNumber.assert_called_once()

    def test_initialize(self):
        self._library_mock.PH_Initialize.return_value = 0
        self._picoharp.initialize('T2')

    def test_initialize_excepts_measurement_running(self):
        self._library_mock.PH_Initialize.return_value = 0
        self._library_mock.PH_StartMeas.return_value = 0
        self._picoharp.start_measurement(1000)
        with self.assertRaises(QMI_InvalidOperationException):
            self._picoharp.initialize('T2')

    def test_initialize_excepts_invalid_mode(self):
        self._library_mock.PH_Initialize.return_value = 0
        with self.assertRaises(ValueError):
            self._picoharp.initialize('T4')

    def test_initialise_raises_libraryError(self):

        self._library_mock.PH_Initialize.return_value = -1
        self._library_mock.PH_GetErrorString.return_value = 0

        error_string = 'error string'
        ctype_err_string = ctypes.create_string_buffer(error_string.encode('ASCII'), 40)

        with self.assertRaises(QMI_InstrumentException), \
                patch('ctypes.create_string_buffer', return_value=ctype_err_string):

            self._picoharp.initialize('T2')

    def test_set_sync_offset(self):
        self._library_mock.PH_SetSyncOffset.return_value = 0
        self._picoharp.set_sync_offset(99)
        self._library_mock.PH_SetSyncOffset.assert_called_once_with(0, 99)

    def test_get_features(self):
        self._library_mock.PH_GetFeatures.return_value = 0
        bitpattern = 0x0001

        with patch('ctypes.c_int', return_value=ctypes.c_int(bitpattern)):
            features = self._picoharp.get_features()

        self.assertIn('DLL', features)

    def test_get_hardware_info(self):
        self._library_mock.PH_GetHardwareInfo.return_value = 0
        expected_module_info = ("SomeHarp 000", "98765432", "3.0.0.3")
        values = [b"SomeHarp 000", b"98765432", b"3.0.0.3"]
        patcher = patch('ctypes.create_string_buffer', side_effect=[ctypes.create_string_buffer(value)
                                                                    for value in values])

        with patcher:
            module_info = self._picoharp.get_hardware_info()

        self.assertTupleEqual(module_info, expected_module_info)

    def test_get_debug_info(self):
        self._library_mock.PH_GetHardwareDebugInfo.return_value = 0
        expected_debug_info = 'foo bar baz'
        string_buffer = ctypes.create_string_buffer(expected_debug_info.encode('ASCII'), 65536)

        with patch('ctypes.create_string_buffer', return_value=string_buffer):
            debug_info = self._picoharp.get_debug_info()

        self.assertEqual(debug_info, expected_debug_info)

    def test_get_flags(self):
        self._library_mock.PH_GetFlags.return_value = 0
        flag_bitset = 0b1000000  # = 64 = 0x0040

        with patch('ctypes.c_int', return_value=ctypes.c_int(flag_bitset)):
            flags = self._picoharp.get_flags()

        self.assertIn("OVERFLOW", flags)

    def test_get_warnings(self):
        self._library_mock.PH_GetWarnings.return_value = 0
        flag_bitset = 0b01

        with patch('ctypes.c_int', return_value=ctypes.c_int(flag_bitset)):
            flags = self._picoharp.get_warnings()

        self.assertIn("INP0_RATE_ZERO", flags)

    def test_set_marker_enable(self):
        self._library_mock.PH_SetMarkerEnable.return_value = 0
        self._picoharp.set_marker_enable(True, False, True, False)
        self._library_mock.PH_SetMarkerEnable.assert_called_once_with(0, 1, 0, 1, 0)

    def test_set_marker_holdoff_time(self):
        self._library_mock.PH_SetMarkerHoldoffTime.return_value = 0
        self._picoharp.set_marker_holdoff_time(123456)
        self._library_mock.PH_SetMarkerHoldoffTime.assert_called_once_with(0, 123456)

    def test_calibrate(self):
        self._library_mock.PH_Calibrate.return_value = 0
        self._picoharp.calibrate()
        self._library_mock.PH_Calibrate.assert_called_once_with(0)

    def test_input_cfd(self):
        self._library_mock.PH_SetInputCFD.return_value = 0
        self._picoharp.set_input_cfd(2, 100, 30)
        self._library_mock.PH_SetInputCFD.assert_called_once_with(0, 2, 100, 30)

    def test_read_fifo(self):
        self._library_mock.PH_ReadFiFo.return_value = 0
        self._library_mock.PH_StartMeas.return_value = 0
        self._library_mock.PH_StopMeas.return_value = 0
        self._library_mock.PH_Initialize.return_value = 0

        self._picoharp.initialize('T2')
        self._picoharp.start_measurement(1)
        time.sleep(0.01)
        self._picoharp.stop_measurement()

        self._library_mock.PH_ReadFiFo.assert_called()
        self.assertEqual(len(self._library_mock.PH_ReadFiFo.call_args_list[0][0]), 4)


if __name__ == '__main__':
    unittest.main()

