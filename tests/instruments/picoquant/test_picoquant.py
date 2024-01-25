import ctypes
import sys
import time
from typing import Any

import unittest
from unittest.mock import patch, call

from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.instruments.picoquant._picoquant import _PicoquantHarp

from tests.patcher import PatcherQmiContext as QMI_Context


_shlib_function_signatures = [
        ('SH_GetLibraryVersion', ctypes.c_int, [('vers', ctypes.POINTER(ctypes.c_char))]),
        ('SH_GetErrorString', ctypes.c_int, [('errstring', ctypes.POINTER(ctypes.c_char)), ('errcode', ctypes.c_int)]),
        ('SH_OpenDevice', ctypes.c_int, [('devidx', ctypes.c_int), ('serial', ctypes.POINTER(ctypes.c_char))]),
        ('SH_CloseDevice', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('SH_Initialize', ctypes.c_int, [('devidx', ctypes.c_int), ('mode', ctypes.c_int), ('refsource', ctypes.c_int)]),
        ('SH_GetHardwareInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('model', ctypes.POINTER(ctypes.c_char)), ('partno', ctypes.POINTER(ctypes.c_char)), ('version', ctypes.POINTER(ctypes.c_char))]),
        ('SH_GetSerialNumber', ctypes.c_int, [('devidx', ctypes.c_int), ('serial', ctypes.POINTER(ctypes.c_char))]),
        ('SH_GetFeatures', ctypes.c_int, [('devidx', ctypes.c_int), ('features', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetBaseResolution', ctypes.c_int, [('devidx', ctypes.c_int), ('resolution', ctypes.POINTER(ctypes.c_double)), ('binsteps', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetNumOfInputChannels', ctypes.c_int, [('devidx', ctypes.c_int), ('nchannels', ctypes.POINTER(ctypes.c_int))]),
        ('SH_SetSyncDiv', ctypes.c_int, [('devidx', ctypes.c_int), ('div', ctypes.c_int)]),
        ('SH_SetSyncEdgeTrg', ctypes.c_int, [('devidx', ctypes.c_int), ('level', ctypes.c_int), ('edge', ctypes.c_int)]),
        ('SH_SetSyncChannelOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('value', ctypes.c_int)]),
        ('SH_SetSyncDeadTime', ctypes.c_int, [('devidx', ctypes.c_int), ('on', ctypes.c_int), ('deadtime', ctypes.c_int)]),
        ('SH_SetInputEdgeTrg', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('level', ctypes.c_int), ('edge', ctypes.c_int)]),
        ('SH_SetInputChannelOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('value', ctypes.c_int)]),
        ('SH_SetInputDeadTime', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('on', ctypes.c_int), ('deadtime', ctypes.c_int)]),
        ('SH_SetInputChannelEnable', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('enable', ctypes.c_int)]),
        ('SH_SetStopOverflow', ctypes.c_int, [('devidx', ctypes.c_int), ('stop_ovfl', ctypes.c_int), ('stopcount', ctypes.c_uint)]),
        ('SH_SetBinning', ctypes.c_int, [('devidx', ctypes.c_int), ('binning', ctypes.c_int)]),
        ('SH_SetOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('offset', ctypes.c_int)]),
        ('SH_SetHistoLen', ctypes.c_int, [('devidx', ctypes.c_int), ('lencode', ctypes.c_int), ('actuallen', ctypes.POINTER(ctypes.c_int))]),
        ('SH_SetMeasControl', ctypes.c_int, [('devidx', ctypes.c_int), ('control', ctypes.c_int), ('startedge', ctypes.c_int), ('stopedge', ctypes.c_int)]),
        ('SH_SetTriggerOutput', ctypes.c_int, [('devidx', ctypes.c_int), ('period', ctypes.c_int)]),
        ('SH_ClearHistMem', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('SH_StartMeas', ctypes.c_int, [('devidx', ctypes.c_int), ('tacq', ctypes.c_int)]),
        ('SH_StopMeas', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('SH_CTCStatus', ctypes.c_int, [('devidx', ctypes.c_int), ('ctcstatus', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetHistogram', ctypes.c_int, [('devidx', ctypes.c_int), ('chcount', ctypes.POINTER(ctypes.c_uint)), ('channel', ctypes.c_int)]),
        ('SH_GetAllHistograms', ctypes.c_int, [('devidx', ctypes.c_int), ('chcount', ctypes.POINTER(ctypes.c_uint))]),
        ('SH_GetResolution', ctypes.c_int, [('devidx', ctypes.c_int), ('resolution', ctypes.POINTER(ctypes.c_double))]),
        ('SH_GetSyncPeriod', ctypes.c_int, [('devidx', ctypes.c_int), ('period', ctypes.POINTER(ctypes.c_double))]),
        ('SH_GetSyncRate', ctypes.c_int, [('devidx', ctypes.c_int), ('syncrate', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetCountRate', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('cntrate', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetAllCountRates', ctypes.c_int, [('devidx', ctypes.c_int), ('syncrate', ctypes.POINTER(ctypes.c_int)), ('cntrates', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetFlags', ctypes.c_int, [('devidx', ctypes.c_int), ('flags', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetElapsedMeasTime', ctypes.c_int, [('devidx', ctypes.c_int), ('elapsed', ctypes.POINTER(ctypes.c_double))]),
        ('SH_GetStartTime', ctypes.c_int, [('devidx', ctypes.c_int), ('timedw2', ctypes.POINTER(ctypes.c_uint)), ('timedw1', ctypes.POINTER(ctypes.c_uint)), ('timedw0', ctypes.POINTER(ctypes.c_uint))]),
        ('SH_GetWarnings', ctypes.c_int, [('devidx', ctypes.c_int), ('warnings', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetWarningsText', ctypes.c_int, [('devidx', ctypes.c_int), ('text', ctypes.POINTER(ctypes.c_char)), ('warnings', ctypes.c_int)]),
        ('SH_SetMarkerHoldoffTime', ctypes.c_int, [('devidx', ctypes.c_int), ('holdofftime', ctypes.c_int)]),
        ('SH_SetMarkerEdges', ctypes.c_int, [('devidx', ctypes.c_int), ('me1', ctypes.c_int), ('me2', ctypes.c_int), ('me3', ctypes.c_int), ('me4', ctypes.c_int)]),
        ('SH_SetMarkerEnable', ctypes.c_int, [('devidx', ctypes.c_int), ('en1', ctypes.c_int), ('en2', ctypes.c_int), ('en3', ctypes.c_int), ('en4', ctypes.c_int)]),
        ('SH_ReadFiFo', ctypes.c_int, [('devidx', ctypes.c_int), ('buffer', ctypes.POINTER(ctypes.c_uint)), ('nactual', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetDebugInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('debuginfo', ctypes.POINTER(ctypes.c_char))]),
        ('SH_GetNumOfModules', ctypes.c_int, [('devidx', ctypes.c_int), ('nummod', ctypes.POINTER(ctypes.c_int))]),
        ('SH_GetModuleInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('modidx', ctypes.c_int), ('modelcode', ctypes.POINTER(ctypes.c_int)), ('versioncode', ctypes.POINTER(ctypes.c_int))]),
        ('SH_WRabbitGetMAC', ctypes.c_int, [('devidx', ctypes.c_int), ('mac_addr', ctypes.POINTER(ctypes.c_char))]),
        ('SH_WRabbitSetMAC', ctypes.c_int, [('devidx', ctypes.c_int), ('mac_addr', ctypes.POINTER(ctypes.c_char))]),
        ('SH_WRabbitGetInitScript', ctypes.c_int, [('devidx', ctypes.c_int), ('initscript', ctypes.POINTER(ctypes.c_char))]),
        ('SH_WRabbitSetInitScript', ctypes.c_int, [('devidx', ctypes.c_int), ('initscript', ctypes.POINTER(ctypes.c_char))]),
        ('SH_WRabbitGetSFPData', ctypes.c_int, [('devidx', ctypes.c_int), ('sfpnames', ctypes.POINTER(ctypes.c_char)), ('dTxs', ctypes.POINTER(ctypes.c_int)), ('dRxs', ctypes.POINTER(ctypes.c_int)), ('alphas', ctypes.POINTER(ctypes.c_int))]),
        ('SH_WRabbitSetSFPData', ctypes.c_int, [('devidx', ctypes.c_int), ('sfpnames', ctypes.POINTER(ctypes.c_char)), ('dTxs', ctypes.POINTER(ctypes.c_int)), ('dRxs', ctypes.POINTER(ctypes.c_int)), ('alphas', ctypes.POINTER(ctypes.c_int))]),
        ('SH_WRabbitInitLink', ctypes.c_int, [('devidx', ctypes.c_int), ('link_on', ctypes.c_int)]),
        ('SH_WRabbitSetMode', ctypes.c_int, [('devidx', ctypes.c_int), ('bootfromscript', ctypes.c_int), ('reinit_with_mode', ctypes.c_int), ('mode', ctypes.c_int)]),
        ('SH_WRabbitSetTime', ctypes.c_int, [('devidx', ctypes.c_int), ('timehidw', ctypes.c_uint), ('timelodw', ctypes.c_uint)]),
        ('SH_WRabbitGetTime', ctypes.c_int, [('devidx', ctypes.c_int), ('timehidw', ctypes.POINTER(ctypes.c_uint)), ('timelodw', ctypes.POINTER(ctypes.c_uint)), ('subsec16ns', ctypes.POINTER(ctypes.c_uint))]),
        ('SH_WRabbitGetStatus', ctypes.c_int, [('devidx', ctypes.c_int), ('wrstatus', ctypes.POINTER(ctypes.c_int))]),
        ('SH_WRabbitGetTermOutput', ctypes.c_int, [('devidx', ctypes.c_int), ('buffer', ctypes.POINTER(ctypes.c_char)), ('nchar', ctypes.POINTER(ctypes.c_int))])
    ]


class _LibWrapper:

    def __init__(self, t: str):

        if not sys.platform.startswith("linux"):
            raise ValueError("Unsupported platform.")

        if t == "SH":
            self._lib = ctypes.cdll.LoadLibrary("libsh000.so")
            self.annotate_function_signatures(_shlib_function_signatures)
            self._prefix = "SH"
        else:
            raise ValueError("Unknown library: {lib}.".format(lib=t))

    def __getattr__(self, item: str) -> Any:
        attr_name = "{prefix}_{item}".format(prefix=self._prefix, item=item)
        attr = getattr(self._lib, attr_name)

        def wrap_fun(*args, **kwargs):
            errcode = attr(*args, **kwargs)
            if errcode != 0:
                raise QMI_InstrumentException(f"Interaction with PicoQuant library failed, errorcode [{errcode}].")
        return wrap_fun

    def annotate_function_signatures(self, sigs) -> None:
        """Annotate functions present in the MultiHarp shared library according to their function signatures."""
        function_signatures = sigs

        for (name, restype, argtypes) in function_signatures:
            try:
                func = getattr(self._lib, name)
                func.restype = restype
                func.argtypes = [argtype for (argname, argtype) in argtypes]
            except AttributeError:
                # Ignore functions that cannot be found.
                pass


class PicoQuant_SomeHarp000(_PicoquantHarp):
    """Instrument driver for the PicoQuant SomeHarp 000."""

    _MODEL = "SH"
    _MAXDEVNUM = 8
    _TTREADMAX = 131072

    @property
    def _max_dev_num(self):
        return self._MAXDEVNUM

    @property
    def _ttreadmax(self):
        return self._TTREADMAX

    @property
    def _lib(self) -> _LibWrapper:
        if self._lazy_lib is None:
            self._lazy_lib = _LibWrapper('SH')
        return self._lazy_lib

    @property
    def _model(self):
        return self._MODEL


class PicoQuantSomeHarpOpenTestCase(unittest.TestCase):

    def setUp(self) -> None:
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_open_close(self):
        """Test regular open where SN is returned immediately."""
        someharp = PicoQuant_SomeHarp000(QMI_Context("test_someharp"), 'someharp', '1111111')

        self._library_mock.SH_GetLibraryVersion.return_value = 0
        self._library_mock.SH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(8)
        string_buffer.value = b'1111111'

        with patch('sys.platform', 'linux1'):
            with patch('ctypes.create_string_buffer', return_value=string_buffer):
                someharp.open()

            someharp.close()

    def test_open_model_not_implemented_exception(self):
        """Test that model type 'SH' raises an exception if no device serial number is immediately received."""
        someharp = PicoQuant_SomeHarp000(QMI_Context("test_someharp"), 'someharp', '1111111')

        self._library_mock.SH_GetLibraryVersion.return_value = 0
        self._library_mock.SH_OpenDevice.return_value = 0
        self._library_mock.SH_CloseDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(8)
        string_buffer.value = b''

        with patch('sys.platform', 'linux1'):
            with patch('ctypes.create_string_buffer', return_value=string_buffer):
                with self.assertRaises(NotImplementedError):
                    someharp.open()

    def test_open_excepts_wrong_serial(self):
        """When trying to find an instrument with a wrong serial, we fail after _MAXDEVNUM SH_OpenDevice calls."""
        wrong_serial = '1111111'
        serial = '1111112'
        someharp = PicoQuant_SomeHarp000(QMI_Context("test_someharp"), 'someharp', serial)

        self._library_mock.SH_GetLibraryVersion.return_value = 0
        self._library_mock.SH_OpenDevice.return_value = 0
        self._library_mock.SH_CloseDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(8)
        string_buffer.value = bytes(wrong_serial.encode())
        expected_exception = f"No device with serial number {serial!r} found."
        expected_calls = [call(i, string_buffer) for i in range(PicoQuant_SomeHarp000._MAXDEVNUM)]

        with patch('sys.platform', 'linux1'), self.assertRaises(QMI_InstrumentException) as exc:
            with patch('ctypes.create_string_buffer', return_value=string_buffer):
                someharp.open()

            self._library_mock.SH_OpenDevice.assert_has_calls(expected_calls)
            self.assertEqual(expected_exception, str(exc.exception))


class PicoQuantSomeHarpTestCase(unittest.TestCase):

    def setUp(self) -> None:
        patcher = patch('ctypes.cdll.LoadLibrary', spec=ctypes.CDLL)
        self._library_mock = patcher.start().return_value

        function_names, _, _ = zip(*_shlib_function_signatures)
        self._library_mock.mock_add_spec(function_names, spec_set=True)

        self.addCleanup(patcher.stop)

        self._someharp = PicoQuant_SomeHarp000(QMI_Context("test_someharp"), 'someharp', '1111111')

        self._library_mock.SH_GetLibraryVersion.return_value = 0
        self._library_mock.SH_OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'1111111')

        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', return_value=string_buffer):
            self._someharp.open()

    def tearDown(self) -> None:
        self._library_mock.SH_CloseDevice.return_value = 0
        self._someharp.close()

    def test_get_error_string(self):
        """Test that get_error_string can be called and returns a string."""
        self._library_mock.SH_GetErrorString.return_value = 0
        expected_error_string = "Device is busy."

        error_code = -1
        string_buffer = ctypes.create_string_buffer(expected_error_string.encode('ASCII'))

        with patch('ctypes.create_string_buffer', return_value=string_buffer):
            error_string = self._someharp.get_error_string(error_code)

        self._library_mock.SH_GetErrorString.assert_called_once_with(string_buffer, error_code)
        self.assertEqual(error_string, expected_error_string)

    def test_get_hardware_info(self):

        self._library_mock.SH_GetHardwareInfo.return_value = 0
        expected_hardware_info = 'abcdefgh', '12345678', '23456789'

        model_string_buffer = ctypes.create_string_buffer(expected_hardware_info[0].encode('ASCII'), 24)
        partno = ctypes.create_string_buffer(expected_hardware_info[1].encode('ASCII'), 8)
        version = ctypes.create_string_buffer(expected_hardware_info[2].encode('ASCII'), 8)

        with patch('ctypes.create_string_buffer', side_effect=[model_string_buffer, partno, version]):
            hardware_info = self._someharp.get_hardware_info()

        self.assertTupleEqual(hardware_info, expected_hardware_info)

    def test_get_serial_number(self):
        self._library_mock.SH_GetSerialNumber.return_value = 0
        expected_serial_number = "1111111"

        string_buffer = ctypes.create_string_buffer(expected_serial_number.encode('ASCII'))

        with patch('ctypes.create_string_buffer', return_value=string_buffer):
            serial_number = self._someharp.get_serial_number()

        self.assertEqual(serial_number, expected_serial_number)

    def test_get_base_resolution(self):
        self._library_mock.SH_GetBaseResolution.return_value = 0

        expected_resolution = 0.1
        expected_binsteps = 10

        resolution_patcher = patch('ctypes.c_double', return_value=ctypes.c_double(expected_resolution))
        binsteps_patcher = patch('ctypes.c_int', return_value=ctypes.c_int(expected_binsteps))

        with resolution_patcher, binsteps_patcher:
            resolution, binsteps = self._someharp.get_base_resolution()

        self.assertEqual(resolution, expected_resolution)
        self.assertEqual(binsteps, expected_binsteps)

    def test_get_number_of_input_channels(self):
        self._library_mock.SH_GetNumOfInputChannels.return_value = 0

        expected_channels = 4

        with patch('ctypes.c_int', return_value=ctypes.c_int(expected_channels)):
            channels = self._someharp.get_number_of_input_channels()

        self.assertEqual(channels, expected_channels)

    def test_set_sync_divider(self):

        self._library_mock.SH_SetSyncDiv.return_value = 0
        self._someharp.set_sync_divider(5)
        self._library_mock.SH_SetSyncDiv.assert_called_once_with(0, 5)

    def test_set_input_channel_offset(self):

        self._library_mock.SH_SetInputChannelOffset.return_value = 0
        self._someharp.set_input_channel_offset(1, 99999)
        self._library_mock.SH_SetInputChannelOffset.assert_called_once_with(0, 1, 99999)

    def test_set_input_channel_enable(self):

        self._library_mock.SH_SetInputChannelEnable.return_value = 0
        self._someharp.set_input_channel_enable(0, True)
        self._library_mock.SH_SetInputChannelEnable.assert_called_once_with(0, 0, 1)

    def test_set_stop_overflow(self):

        self._library_mock.SH_SetStopOverflow.return_value = 0
        self._someharp.set_stop_overflow(True, 50000)
        self._library_mock.SH_SetStopOverflow.assert_called_once_with(0, 1, 50000)

    def test_set_binning(self):

        self._library_mock.SH_SetBinning.return_value = 0
        self._someharp.set_binning(3)
        self._library_mock.SH_SetBinning.assert_called_once_with(0, 3)

    def test_set_offset(self):

        self._library_mock.SH_SetOffset.return_value = 0
        self._someharp.set_offset(100000)
        self._library_mock.SH_SetOffset.assert_called_once_with(0, 100000)

    def test_set_histogram_length(self):

        self._library_mock.SH_SetHistoLen.return_value = 0

        expected_actual_length_code = 5

        with patch('ctypes.c_int', return_value=ctypes.c_int(5)) as patcher:
            actual_length = self._someharp.set_histogram_length(6)
            self._library_mock.SH_SetHistoLen.assert_called_once_with(0, 6, patcher.return_value)

        self.assertEqual(actual_length, expected_actual_length_code)

    def test_set_measurement_control(self):
        """Should raise NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self._someharp.set_measurement_control("a", "b", "c")

    def test_clear_histogram_memory(self):

        self._library_mock.SH_ClearHistMem.return_value = 0
        self._someharp.clear_histogram_memory()
        self._library_mock.SH_ClearHistMem.assert_called_once_with(0)

    def test_start_measurement(self):

        self._library_mock.SH_StartMeas.return_value = 0
        self._someharp.start_measurement(100)
        self._library_mock.SH_StartMeas.assert_called_once_with(0, 100)

    def test_stop_measurement(self):

        self._library_mock.SH_StopMeas.return_value = 0
        self._someharp.stop_measurement()
        self._library_mock.SH_StopMeas.assert_called_once_with(0)

    def test_get_measurement_active(self):

        self._library_mock.SH_CTCStatus.return_value = 0

        with patch('ctypes.c_int', return_value=ctypes.c_int(0)):
            is_running = self._someharp.get_measurement_active()

        self.assertTrue(is_running)

    def test_get_measurement_start_time(self):

        self._library_mock.SH_StartMeas.return_value = 0
        current_time = time.time()

        self._someharp.start_measurement(100)
        posix_time = self._someharp.get_measurement_start_time()
        self.assertAlmostEqual(current_time, posix_time, places=1)

    def test_get_measurement_running_already(self):

        self._library_mock.SH_StartMeas.return_value = 0
        self._someharp.start_measurement(100)
        with self.assertRaises(QMI_InvalidOperationException):
            self._someharp.start_measurement(1)

    def test_get_events(self):

        events = self._someharp.get_events()
        self.assertEqual(len(events), 0)

    def test_get_timestamped_events(self):

        timestamps, events = self._someharp.get_timestamped_events()
        self.assertEqual(timestamps, 0.0)
        self.assertEqual(len(events), 0)

    def test_get_resolution(self):

        self._library_mock.SH_GetResolution.return_value = 0

        expected_resolution = 80.0

        with patch('ctypes.c_double', return_value=ctypes.c_double(expected_resolution)):
            resolution = self._someharp.get_resolution()

        self.assertEqual(resolution, expected_resolution)

    def test_get_sync_rate(self):

        self._library_mock.SH_GetSyncRate.return_value = 0

        expected_sync_rate = 5000

        with patch('ctypes.c_int', return_value=ctypes.c_int(expected_sync_rate)):
            sync_rate = self._someharp.get_sync_rate()

        self.assertEqual(sync_rate, expected_sync_rate)

    def test_get_count_rate(self):

        self._library_mock.SH_GetCountRate.return_value = 0

        expected_count_rate = 5000

        with patch('ctypes.c_int', return_value=ctypes.c_int(expected_count_rate)) as patcher:
            count_rate = self._someharp.get_count_rate(1)
            self._library_mock.SH_GetCountRate.assert_called_once_with(0, 1, patcher.return_value)

        self.assertEqual(count_rate, expected_count_rate)

    def test_get_elapsed_measurement_time(self):

        self._library_mock.SH_GetElapsedMeasTime.return_value = 0

        expected_elapsed = 1000.0

        with patch('ctypes.c_double', return_value=ctypes.c_double(expected_elapsed)):
            elapsed = self._someharp.get_elapsed_measurement_time()

        self.assertEqual(elapsed, expected_elapsed)

    def test_get_sync_period(self):

        self._library_mock.SH_GetSyncPeriod.return_value = 0

        expected_sync_period = 3.14

        with patch('ctypes.c_double', return_value=ctypes.c_double(expected_sync_period)):
            sync_period = self._someharp.get_sync_period()

        self.assertEqual(sync_period, expected_sync_period)

    def test_set_marker_edges(self):

        self._library_mock.SH_SetMarkerEdges.return_value = 0
        self._someharp.set_marker_edges('RISING', 'FALLING', 'RISING', 'FALLING')
        self._library_mock.SH_SetMarkerEdges.assert_called_once_with(0, 1, 0, 1, 0)

    def test_set_marker_enable(self):

        self._library_mock.SH_SetMarkerEnable.return_value = 0
        self._someharp.set_marker_enable(True, False, True, False)
        self._library_mock.SH_SetMarkerEnable.assert_called_once_with(0, 1, 0, 1, 0)

        # ensure bool`s are converted to int`s.
        expect_int_arg = self._library_mock.SH_SetMarkerEnable.call_args_list[0][0][1]
        self.assertEqual(type(expect_int_arg), int)

    def test_set_marker_holdoff_time(self):
        """Test set_marker_holdoff_time function"""
        self._library_mock.SH_SetMarkerHoldoffTime.return_value = 0

        holdoff_time = 25500

        self._someharp.set_marker_holdoff_time(holdoff_time)
        self._library_mock.SH_SetMarkerHoldoffTime.assert_called_once_with(0, holdoff_time)

    def test_get_histogram_with_clear(self):
        """Test on get_histogram function without 'clear' input variable"""
        self._library_mock.SH_GetHistogram.return_value = 0

        self._someharp.get_histogram(1)
        self._library_mock.SH_GetHistogram.assert_called()
        self.assertEqual(len(self._library_mock.SH_GetHistogram.call_args_list[0][0]), 3)

    def get_warnings_text(self):
        """Test get warnings texts can be called and returns text."""
        expected_text = "This is the final warning."
        string_buffer = ctypes.create_string_buffer(expected_text.encode('ASCII'))

        with patch('ctypes.create_string_buffer', return_value=string_buffer):
            warnings_text = self._someharp.get_warnings_text()

        self._someharp.get_warnings_text.assertCalled()
        self.assertEqual(expected_text, warnings_text)

    def test_get_module_info(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.get_module_info()

    def test_set_sync_cfd(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.set_sync_cfd(1, 2)

    def test_set_input_cfd(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.set_input_cfd(1, 2, 3)

    def test_set_sync_offset(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.set_sync_offset(4)

    def test_set_sync_channel_offset(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.set_sync_channel_offset(5)

    def test_get_flags(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.get_flags()

    def get_all_histograms(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.get_all_histograms()

    def get_warnings(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.get_warnings()

    def test_set_trigger_output(self):
        """Should raise NotImplementedError"""
        with self.assertRaises(NotImplementedError):
            self._someharp.set_trigger_output(111)

    def test_set_block_events(self):

        self._someharp.set_block_events(True)

    def test_set_event_filter(self):

        self._someharp.set_event_filter(True)

    def test_set_realtime_histogram(self):

        self._someharp.set_realtime_histogram([0, 1, 2], 1, 100, 0)

    def test_set_realtime_histogram_raises_ValueError(self):

        with self.assertRaises(ValueError):
            self._someharp.set_realtime_histogram([0, 1, 2], 0, 100, 0)

    def test_set_realtime_countrate(self):

        self._someharp.set_realtime_countrate((10, 100), 10)


if __name__ == '__main__':
    unittest.main()
