import unittest
from unittest.mock import Mock, patch
import ctypes
import sys

# Existing import of ps3000a might cause a disturbance
if "picosdk.ps3000a" in sys.modules:
    del sys.modules["picosdk.ps3000a"]

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException

# For not causing an error by missing picosdk library in the pipeline tests, we mock also the picosdk existence
import tests.instruments.picotech.picosdk_stub
from tests.instruments.picotech.ps4000a_stub import ps4000a
sys.modules['picosdk'] = tests.instruments.picotech.picosdk_stub
sys.modules['picosdk.ps4000a'] = tests.instruments.picotech.ps4000a_stub
from qmi.instruments.picotech import picoscope4824
from qmi.instruments.picotech import _picoscope
from qmi.instruments.picotech._picoscope import ChannelCoupling, TriggerEdge

patcher = patch("picosdk.ps4000a", autospec=True)
picoscope4824._ps = patcher.start()


class PicoscopeMethodsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        _picoscope._ps = ps4000a
        self._picoscope = picoscope4824.PicoTech_PicoScope4824(
            QMI_Context('test_picoscope_4824'), 'PicoScope', "GR956/0069"
        )
        # Mock the PicoScope "open" function to be able to open the virtual unit.
        self._picoscope._ps = Mock(spec=ps4000a)
        self._picoscope.open()

    def tearDown(self) -> None:
        self._picoscope.close()
        picoscope4824._ps.reset_mock()

    def test_get_serial_number(self):
        """Test query serial number. Mock can only return error code, need to patch the input string."""
        expected = "s1234"
        self._picoscope._ps_attr.ps4000aGetUnitInfo = Mock(return_value=0)
        with patch('ctypes.create_string_buffer', side_effect=[ctypes.c_char_p(bytes(expected.encode()))]):
            sn = self._picoscope.get_serial_number()

        self.assertEqual(sn, expected)

    def test_device_variant(self):
        """Test query device variant. Mock can only return error code, need to patch the input string."""
        expected = "ps4824"
        _picoscope._ps.PICO_INFO["PICO_VARIANT_INFO"] = "4824"
        self._picoscope._ps_attr.ps4000aGetUnitInfo = Mock(return_value=0)
        with patch('ctypes.create_string_buffer', side_effect=[ctypes.c_char_p(bytes(expected.encode()))]):
            variant = self._picoscope.get_device_variant()

        self.assertEqual(variant, expected)

    def test_input_ranges(self):
        """Test query input ranges."""
        sel = range(11)
        vol = [i / 10.0 for i in range(11)]
        expected = dict(zip(sel, vol))

        _picoscope._ps.PICO_VOLTAGE_RANGE = expected
        ranges = self._picoscope.get_input_ranges()
        self.assertDictEqual(expected, ranges)

    def test_set_channel_ok(self):
        """Test setting channel values with no invalid input values."""
        self._picoscope.set_channel(1, True, ChannelCoupling.AC, 0, 1.0)

    def test_set_channel_nok_invalid_channel_index(self):
        """Test setting channel values with invalid channel index numbers."""
        # channel index < 0
        with self.assertRaises(ValueError):
            self._picoscope.set_channel(-1, True, ChannelCoupling.AC, 0, 1.0)

        # channel index >= NUM_CHANNELS
        with self.assertRaises(ValueError):
            self._picoscope.set_channel(picoscope4824.PicoTech_PicoScope4824.NUM_CHANNELS, True,
                                        ChannelCoupling.AC, 0, 1.0)

    def test_set_channel_nok_invalid_input_range(self):
        """Test setting channel values with invalid input range numbers."""
        # input_range < 0
        with self.assertRaises(ValueError):
            self._picoscope.set_channel(0, True, ChannelCoupling.AC, -1, 1.0)

        # input_range >= NUM_INPUT_RANGES
        with self.assertRaises(ValueError):
            self._picoscope.set_channel(1, True, ChannelCoupling.AC,
                                        picoscope4824.PicoTech_PicoScope4824.NUM_INPUT_RANGES, 1.0)

    def test_set_trigger_ok(self):
        """Test setting trigger with valid input values."""
        self._picoscope.set_trigger(False, 1, -10000, TriggerEdge.RISING_OR_FALLING)

    def test_set_trigger_nok_invalid_channel_index(self):
        """Test setting trigger with invalid channel indexes."""
        # channel index < 0
        with self.assertRaises(ValueError):
            self._picoscope.set_trigger(True, -1, -10000, TriggerEdge.RISING)

        # channel index >= NUM_CHANNELS
        with self.assertRaises(ValueError):
            self._picoscope.set_trigger(True, picoscope4824.PicoTech_PicoScope4824.NUM_CHANNELS, -10000,
                                        TriggerEdge.FALLING)

    def test_set_trigger_nok_invalid_threshold(self):
        """Test setting trigger with invalid threshold values."""
        # channel index < MIN_SAMPLE_VALUE
        with self.assertRaises(ValueError):
            self._picoscope.set_trigger(True, 1, picoscope4824.PicoTech_PicoScope4824.MIN_SAMPLE_VALUE - 1,
                                        TriggerEdge.RISING)

        # channel index > MAX_SAMPLE_VALUE
        with self.assertRaises(ValueError):
            self._picoscope.set_trigger(False, 2, picoscope4824.PicoTech_PicoScope4824.MAX_SAMPLE_VALUE + 1,
                                        TriggerEdge.FALLING)

    def test_set_disable_trigger_ok(self):
        """Test disabling all triggers."""
        self._picoscope.disable_trigger()

    def test_stop(self):
        """Test stop function."""
        self._picoscope.stop()

    def test_run_block(self):
        """Test the run_block function."""
        self._picoscope._ps_attr.ps4000aGetTimebase2 = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aRunBlock = Mock(return_value=0)
        self._picoscope.run_block(10, 10, 100)
        picoscope4824._ps.ps4000aGetTimebase2.assert_called_once()
        picoscope4824._ps.ps4000aRunBlock.assert_called_once()

    def test_is_block_ready(self):
        """Test the if_block_ready function. Note that we cannot check for the case is_block_ready returns True."""
        picoscope4824._ps.ps4000aGetTimebase2 = Mock(return_value=0)
        picoscope4824._ps.ps4000aRunBlock = Mock(return_value=0)
        # We need to run first the run_block to be able to run the is_block_ready
        self._picoscope.run_block(10, 10, 100)
        self._picoscope.is_block_ready()

        picoscope4824._ps.ps4000aGetTimebase2.assert_called_once()
        picoscope4824._ps.ps4000aRunBlock.assert_called_once()

    def test_wait_block_ready(self):
        """Test that the wait_block_ready returns normally without timeout."""
        self._picoscope._ps_attr.ps4000aGetTimebase2 = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aRunBlock = Mock(return_value=0)
        # We need to run first the run_block to be able to run the is_block_ready
        self._picoscope.run_block(10, 10, 100)
        with patch('ctypes.c_int16', side_effect=[ctypes.c_int16(1)]):
            self._picoscope.wait_block_ready(1.0)

        picoscope4824._ps.ps4000aGetTimebase2.assert_called_once()
        picoscope4824._ps.ps4000aRunBlock.assert_called_once()

    def test_wait_block_ready_timeout(self):
        """Test the wait_block_ready function with timeout. Note that we can check only that timeout occurs."""
        self._picoscope._ps_attr.ps4000aGetTimebase2 = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aRunBlock = Mock(return_value=0)
        # We need to run first the run_block to be able to run the is_block_ready
        self._picoscope.run_block(10, 10, 100)
        with self.assertRaises(QMI_TimeoutException):
            self._picoscope.wait_block_ready(0.5)

        picoscope4824._ps.ps4000aGetTimebase2.assert_called_once()
        picoscope4824._ps.ps4000aRunBlock.assert_called_once()

    def test_wait_block_ready_invalid_timeout(self):
        """Test the wait_block_ready function returns an error at invalid timeout."""
        with self.assertRaises(ValueError):
            self._picoscope.wait_block_ready(-1.0)

    def test_get_block_data_ok(self):
        """Test the get_block_data function returns data for channels 1 & 3. Only 0 data."""
        channels = [1, 3]
        samples_before = 5
        samples_after = 10
        self._picoscope._ps_attr.ps4000aGetTimebase2 = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aRunBlock = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aSetDataBuffer = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aGetValues = Mock(return_value=0)
        # We need to run first the run_block to be able to run the get_block_data correctly
        self._picoscope.run_block(samples_before, samples_after, 100)
        samples, timebase_interval_ns, overrange = self._picoscope.get_block_data(channels)
        # Assert that we get back samples and overrange for two channels and that the number of channels match the
        # number of channels given in the run_block command.
        self.assertEqual(len(channels), len(samples))
        self.assertEqual(len(channels), len(overrange))
        self.assertEqual(samples_before + samples_after, len(samples[0]))

    def test_get_block_data_nok_invalid_channel_indexes(self):
        """Test the get_block_data function raises an error with wrong number of samples."""
        channels = [-1, 3]
        # channel index < 0
        with self.assertRaises(ValueError):
            self._picoscope.get_block_data(channels)

        channels = [1, picoscope4824.PicoTech_PicoScope4824.NUM_CHANNELS]
        # channel index >= NUM_CHANNELS
        with self.assertRaises(ValueError):
            self._picoscope.get_block_data(channels)

    def test_get_block_data_nok_wrong_number_of_samples(self):
        """Test the get_block_data function raises an error with wrong number of samples."""
        channels = [1, 3]
        samples_before = 10
        samples_after = 10
        picoscope4824._ps.ps4000aGetTimebase2 = Mock(return_value=0)
        picoscope4824._ps.ps4000aRunBlock = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aSetDataBuffer = Mock(return_value=0)
        self._picoscope._ps_attr.ps4000aGetValues = Mock(return_value=0)
        # We need to run first the run_block to be able to run the get_block_data correctly
        self._picoscope.run_block(samples_before, samples_after, 100)
        with patch('ctypes.c_uint32', side_effect=[ctypes.c_uint32(15)]):
            with self.assertRaises(QMI_InstrumentException):
                self._picoscope.get_block_data(channels)

    def test_get_sampling_interval_ok(self):
        """Test that the get_sampling_interval returns correct values for various inputs in range 0...2**32 - 1."""
        input_values = list(range(6)) + [(125 / 12.5) - 1, 2**32 - 1]
        expected = [(e + 1) * 12.5 for e in range(6)] + [125, 2**32 * 12.5]
        for i in range(len(input_values)):
            result = self._picoscope.get_sampling_interval(input_values[i])
            self.assertEqual(expected[i], result)

    def test_get_sampling_interval_out_of_range(self):
        """Test that the get_sampling_interval returns 0 for inputs < 0 and >= 2**32."""
        input_values = [-1, 2**32]
        expected = [0, 0]
        for i in range(len(input_values)):
            result = self._picoscope.get_sampling_interval(input_values[i])
            self.assertEqual(expected[i], result)


if __name__ == "__main__":
    unittest.main()
