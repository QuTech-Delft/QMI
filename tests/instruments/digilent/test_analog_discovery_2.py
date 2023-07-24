import logging
import unittest
import unittest.mock

import numpy as np
import pydwf
import pydwf.utilities
from pydwf.core.dwf_device import DwfDevice

import qmi
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_InstrumentException, QMI_UsageException, \
    QMI_TimeoutException
from qmi.instruments.digilent import Digilent_AnalogDiscovery2, OnClose, Filter


class AnalogDiscovery2OpenCloseTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._device_mock = unittest.mock.MagicMock(spec=DwfDevice)

        patcher = unittest.mock.patch('pydwf.DwfLibrary')
        self._dwf_lib_mock = patcher.start().return_value

        open_patcher = unittest.mock.patch('pydwf.utilities.openDwfDevice', return_value=self._device_mock)
        self._open_dwf_device_mock = open_patcher.start()

        self.addCleanup(patcher.stop)
        self.addCleanup(open_patcher.stop)

        qmi.start('analog_discovery_openclose_test')

        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)
        self._ad2: Digilent_AnalogDiscovery2 = qmi.make_instrument('AD2', Digilent_AnalogDiscovery2, '210321AD12A4')

    def tearDown(self) -> None:
        qmi.stop()
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_open_close(self):

        self._ad2.open()
        self._ad2.close()

        self._open_dwf_device_mock.assert_called_once_with(self._dwf_lib_mock, serial_number_filter='210321AD12A4')

    def test_open_fail_when_not_found(self):

        def raise_value_error(lib, serial_number_filter):
            raise ValueError('Fake value error')

        self._open_dwf_device_mock.side_effect = raise_value_error

        with self.assertRaises(ValueError):
            self._ad2.open()

    def test_open_raises_instrument_exception_when_lib_error(self):

        def raise_value_error(lib, serial_number_filter):
            raise pydwf.DwfLibraryError(code=pydwf.DwfErrorCode.UnknownError, msg='Fake lib error')

        self._open_dwf_device_mock.side_effect = raise_value_error

        with self.assertRaises(QMI_InstrumentException):
            self._ad2.open()

    def test_open_fails_when_opened_double(self):

        self._ad2.open()
        with self.assertRaises(QMI_InvalidOperationException):
            self._ad2.open()
        self._ad2.close()

    def test_close_fails_when_closed_before_opened(self):

        with self.assertRaises(QMI_InvalidOperationException):
            self._ad2.close()

    def test_raise_usage_exception_when_invoke_method_without_open(self):

        with self.assertRaises(QMI_UsageException):
            self._ad2.prepare_analog_output_channel_for_static_output(1, 1.5)

        with self.assertRaises(QMI_UsageException):
            self._ad2.set_analog_output_voltage_output(1, 1.5)

        with self.assertRaises(QMI_UsageException):
            self._ad2.get_analog_output_voltage_output(1)

        with self.assertRaises(QMI_UsageException):
            self._ad2.set_device_on_close(OnClose.SHUTDOWN)

        with self.assertRaises(QMI_UsageException):
            self._ad2.reset_analog_input()

        with self.assertRaises(QMI_UsageException):
            self._ad2.prepare_analog_input_sample(1, 10.0, 0.001)

        with self.assertRaises(QMI_UsageException):
            self._ad2.get_analog_input_sample(1)

        with self.assertRaises(QMI_UsageException):
            self._ad2.get_analog_input_acquire_samples(1)

        with self.assertRaises(QMI_UsageException):
            self._ad2.prepare_analog_input_record(1, 10.0, 1.0, 0.001)

        with self.assertRaises(QMI_UsageException):
            self._ad2.get_analog_input_record(1)


class AnalogDiscovery2ErrorTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._device_mock = unittest.mock.MagicMock(spec=DwfDevice)

        patcher = unittest.mock.patch('pydwf.DwfLibrary')
        self._dwf_lib_mock = patcher.start().return_value

        open_patcher = unittest.mock.patch('pydwf.utilities.openDwfDevice', return_value=self._device_mock)
        self._open_dwf_device_mock = open_patcher.start()

        self.addCleanup(patcher.stop)
        self.addCleanup(open_patcher.stop)

        qmi.start('analogdiscovery2_error_test')

    def tearDown(self) -> None:
        qmi.stop()
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_close_raises_instrument_error_when_lib_error(self):
        def raise_value_error():
            raise pydwf.DwfLibraryError(code=pydwf.DwfErrorCode.UnknownError, msg='Fake lib error')
        self._device_mock.close.side_effect = raise_value_error

        ad2: Digilent_AnalogDiscovery2 = qmi.make_instrument('AD2', Digilent_AnalogDiscovery2, '210321AD12A4')

        ad2.open()

        with self.assertRaises(QMI_InstrumentException):
            ad2.close()

        # Really close now to avoid ResourceWarning.
        self._device_mock.close.side_effect = None
        ad2.close()


class AnalogDiscovery2MethodsTestCase(unittest.TestCase):

    def setUp(self) -> None:

        self._device_mock = unittest.mock.MagicMock(spec=DwfDevice)

        patcher = unittest.mock.patch('pydwf.DwfLibrary')
        self._dwf_lib_mock = patcher.start().return_value

        open_patcher = unittest.mock.patch('pydwf.utilities.openDwfDevice', return_value=self._device_mock)
        self._open_dwf_device_mock = open_patcher.start()

        self.addCleanup(patcher.stop)
        self.addCleanup(open_patcher.stop)

        qmi.start('analogdiscovery2_methods_test')
        self._ad2: Digilent_AnalogDiscovery2 = qmi.make_instrument('AD2', Digilent_AnalogDiscovery2, '210321AD12A4')

        self._analog_out_mock = unittest.mock.create_autospec(spec=pydwf.core.dwf_device.AnalogOut)
        self._device_mock.analogOut = self._analog_out_mock

        self._analog_in_mock = unittest.mock.create_autospec(spec=pydwf.core.dwf_device.AnalogIn)
        self._device_mock.analogIn = self._analog_in_mock

        self._ad2.open()

    def tearDown(self) -> None:
        self._ad2.close()
        qmi.stop()

    def test_prepare_analog_output_channel_for_static_output(self):
        self._ad2.prepare_analog_output_channel_for_static_output(1, 5.5)

        self._analog_out_mock.nodeFunctionSet.assert_called_with(
            1, pydwf.DwfAnalogOutNode.Carrier, pydwf.DwfAnalogOutFunction.Square
        )
        self._analog_out_mock.idleSet.assert_called_with(1, pydwf.DwfAnalogOutIdle.Initial)
        self._analog_out_mock.nodeAmplitudeSet.assert_called_with(1,  pydwf.DwfAnalogOutNode.Carrier, 5.5)
        self._analog_out_mock.nodeEnableSet.assert_called_with(1,  pydwf.DwfAnalogOutNode.Carrier, True)

    def raise_digilent_waveform_library_error(self, *args):
        raise pydwf.DwfLibraryError(code=pydwf.DwfErrorCode.UnknownError, msg='Fake lib error')

    def test_prepare_analog_output_channel_for_static_output_raises_qmi_instrument_error(self):
        self._analog_out_mock.nodeFunctionSet.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.prepare_analog_output_channel_for_static_output(1, 1.0)

    def test_set_analog_output_voltage_output(self):
        self._ad2.set_analog_output_voltage_output(1, 1.5)
        self._analog_out_mock.nodeAmplitudeSet.assert_called_with(1, pydwf.DwfAnalogOutNode.Carrier, 1.5)

    def test_set_analog_output_voltage_output_raises_qmi_instrument_error(self):
        self._analog_out_mock.nodeAmplitudeSet.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.set_analog_output_voltage_output(1, 1.0)

    def test_get_analog_output_voltage_output(self):
        expected_voltage = 1.5
        self._analog_out_mock.nodeAmplitudeGet.return_value = expected_voltage

        voltage = self._ad2.get_analog_output_voltage_output(1)

        self._analog_out_mock.nodeAmplitudeGet.assert_called_with(1, pydwf.DwfAnalogOutNode.Carrier)

        self.assertEqual(voltage, expected_voltage)

    def test_get_analog_output_voltage_output_raises_qmi_instrument_error(self):
        self._analog_out_mock.nodeAmplitudeGet.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.get_analog_output_voltage_output(1)

    def test_set_device_on_close(self):
        self._ad2.set_device_on_close(OnClose.SHUTDOWN)
        self._device_mock.paramSet.assert_called_with(pydwf.DwfDeviceParameter.OnClose, OnClose.SHUTDOWN.value)

    def test_set_device_on_close_raises_qmi_instrument_error(self):
        self._device_mock.paramSet.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.set_device_on_close(OnClose.SHUTDOWN)

    def test_reset_analog_input(self):
        self._ad2.reset_analog_input()
        self._analog_in_mock.reset.assert_called()

    def test_reset_analog_input_raises_qmi_instrument_error(self):
        self._analog_in_mock.reset.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.reset_analog_input()

    def test_prepare_analog_input_sample(self):
        expected_channel, expected_range, expected_freq = (1, 10.0, 0.001)
        self._ad2.prepare_analog_input_sample(expected_channel, expected_range, expected_freq)

        self._analog_in_mock.channelEnableSet.assert_called_with(expected_channel, True)
        self._analog_in_mock.frequencySet.assert_called_with(expected_freq)

        self._analog_in_mock.channelOffsetSet.assert_called_with(expected_channel, 0.0)
        self._analog_in_mock.channelRangeSet.assert_called_with(expected_channel, expected_range)
        self._analog_in_mock.channelFilterSet.assert_called_with(expected_channel, pydwf.DwfAnalogInFilter(Filter.AVERAGE.value))
        self._analog_in_mock.configure.assert_called_with(False, False)

    def test_prepare_analog_input_sample_with_buffer_size(self):
        expected_channel, expected_range, expected_freq = (1, 10.0, 0.001)
        self._ad2.prepare_analog_input_sample(expected_channel, expected_range, expected_freq,
                                              voltage_offset=0.0,
                                              buffer_size=1024)

        self._analog_in_mock.channelEnableSet.assert_called_with(expected_channel, True)
        self._analog_in_mock.frequencySet.assert_called_with(expected_freq)

        self._analog_in_mock.channelOffsetSet.assert_called_with(expected_channel, 0.0)
        self._analog_in_mock.channelRangeSet.assert_called_with(expected_channel, expected_range)
        self._analog_in_mock.channelFilterSet.assert_called_with(expected_channel, pydwf.DwfAnalogInFilter(Filter.AVERAGE.value))
        self._analog_in_mock.configure.assert_called_with(False, False)
        self._analog_in_mock.bufferSizeSet.assert_called_with(1024)

    def test_prepare_analog_input_sample_raises_qmi_instrument_error(self):
        self._analog_in_mock.channelEnableSet.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            expected_channel, expected_range, expected_freq = (1, 10.0, 0.001)
            self._ad2.prepare_analog_input_sample(expected_channel, expected_range, expected_freq)

    def test_get_analog_input_sample(self):
        expected_sample_value = 6.62607
        self._analog_in_mock.statusSample.return_value = expected_sample_value
        sample = self._ad2.get_analog_input_sample(1)

        self._analog_in_mock.status.assert_called_with(False)
        self._analog_in_mock.statusSample.assert_called_with(1)
        self.assertEqual(sample, expected_sample_value)

    def test_get_analog_input_sample_raises_qmi_instrument_error(self):
        self._analog_in_mock.status.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.get_analog_input_sample(1)

    def test_get_analog_input_acquire_samples(self):
        expected_buffer_size = 1024
        expected_samples = np.ones(expected_buffer_size, dtype=np.float64)
        self._analog_in_mock.status.side_effect = [pydwf.DwfState.Running, pydwf.DwfState.Done]
        self._analog_in_mock.bufferSizeGet.return_value = expected_buffer_size
        self._analog_in_mock.statusData.return_value = expected_samples

        samples = self._ad2.get_analog_input_acquire_samples(1)

        self._analog_in_mock.configure.assert_called_with(True, True)
        self._analog_in_mock.status.assert_called_with(True)
        self._analog_in_mock.bufferSizeGet.assert_called()
        self._analog_in_mock.statusData.assert_called_with(1, expected_buffer_size)

        np.testing.assert_array_equal(expected_samples, samples)

    def test_get_analog_input_acquire_samples_raises_qmi_instrument_error(self):
        self._analog_in_mock.configure.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.get_analog_input_acquire_samples(1)

    def test_get_analog_input_acquire_samples_raises_qmi_timeout_exceptions(self):
        with self.assertRaises(QMI_TimeoutException):
            self._ad2.get_analog_input_acquire_samples(1, 0.0000000001)

    def test_prepare_analog_input_record(self):
        self._ad2.prepare_analog_input_record(1, 10.0, 1.0, 0.001)

        self._analog_in_mock.channelEnableSet.assert_called_with(1, True)
        self._analog_in_mock.channelOffsetSet.assert_called_with(1, 0.0)
        self._analog_in_mock.channelRangeSet.assert_called_with(1, 10.0)
        self._analog_in_mock.acquisitionModeSet.assert_called_with(pydwf.DwfAcquisitionMode.Record)
        self._analog_in_mock.frequencySet.assert_called_with(0.001)
        self._analog_in_mock.recordLengthSet.assert_called_with(1.0)
        self._analog_in_mock.channelFilterSet.assert_called_with(1, pydwf.DwfAnalogInFilter(Filter.AVERAGE.value))

    def test_prepare_analog_input_record_raises_qmi_instrument_error(self):
        self._analog_in_mock.channelEnableSet.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.prepare_analog_input_record(1, 10.0, 1.0, 0.001)

    def test_get_analog_input_record(self):
        self._analog_in_mock.status.return_value = pydwf.DwfState.Running
        self._analog_in_mock.statusRecord.return_value = (5, 0, 0)
        self._analog_in_mock.statusData.return_value = np.ones(5, dtype=np.float64)

        sample_record = self._ad2.get_analog_input_record(1, 10)

        np.testing.assert_array_equal(np.ones(10, dtype=np.float64), sample_record)

    def test_get_analog_input_record_advanced(self):
        self._analog_in_mock.status.side_effect = [pydwf.DwfState.Config, pydwf.DwfState.Prefill,
                                                   pydwf.DwfState.Armed, pydwf.DwfState.Running,
                                                   pydwf.DwfState.Running, pydwf.DwfState.Running]
        self._analog_in_mock.statusRecord.side_effect = [(0, 0, 0), (5, 0, 0), (6, 0, 0)]
        self._analog_in_mock.statusData.return_value = np.ones(5, dtype=np.float64)
        self._analog_in_mock.recordLengthGet.return_value = 10
        self._analog_in_mock.frequencyGet.return_value = 1.0

        sample_record = self._ad2.get_analog_input_record(1)

        np.testing.assert_array_equal(np.ones(10, dtype=np.float64), sample_record)

    def test_get_analog_input_record_raises_qmi_instrument_error(self):
        self._analog_in_mock.configure.side_effect = self.raise_digilent_waveform_library_error
        with self.assertRaises(QMI_InstrumentException):
            self._ad2.get_analog_input_record(1, 10)

    def test_get_analog_input_record_data_lost_raises_instrument_error(self):
        self._analog_in_mock.status.return_value = pydwf.DwfState.Running
        self._analog_in_mock.statusRecord.return_value = (5, 1, 0)
        self._analog_in_mock.statusData.return_value = np.ones(5, dtype=np.float64)

        with self.assertRaises(QMI_InstrumentException):
            self._ad2.get_analog_input_record(1, 10)

    def test_get_analog_input_record_corrupt_raises_instrument_error(self):
        self._analog_in_mock.status.return_value = pydwf.DwfState.Running
        self._analog_in_mock.statusRecord.return_value = (5, 0, 1)
        self._analog_in_mock.statusData.return_value = np.ones(5, dtype=np.float64)

        with self.assertRaises(QMI_InstrumentException):
             self._ad2.get_analog_input_record(1, 10)


if __name__ == '__main__':
    unittest.main()
