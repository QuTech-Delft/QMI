import logging
from unittest import TestCase
from unittest.mock import patch, Mock, call

import numpy.testing
from numpy import nan

from qmi.core.exceptions import QMI_InvalidOperationException, QMI_InstrumentException
from qmi.instruments.high_finesse import HighFinesse_Wlm
from qmi.instruments.high_finesse.support import (
    wlmData,
    WlmGetErr,
)
from tests.patcher import QMI_Context

# Disable all logging
logging.disable(logging.CRITICAL)


@patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
class TestHighFinesse_Wlm(TestCase):
    """Test the behavior of the High Finesse driver (with the actual dll mocked)."""
    def setUp(self):
        # Start QMI context
        self.ctx = QMI_Context("highfinesse_wlm_client")

    def test_open(self, dll_patcher):
        """The connection should be 'open' after open() was (implicitly) called."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertTrue(wlm.is_open())

        dll_patcher.assert_called_once()

    def test_open_error(self, dll_patcher):
        """The driver should give an error when an open connection is opened again."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InvalidOperationException) as exc:
                wlm.open()

        self.assertEqual("Operation not allowed on open instrument wlm", str(exc.exception))

    def test_close(self, dll_patcher):
        """The connection should not be open after close() is called."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount = {0: 0}.get

        wlm = HighFinesse_Wlm(Mock(), "support")
        self.assertFalse(wlm.is_open())
        wlm.open()
        self.assertTrue(wlm.is_open())
        wlm.close()
        self.assertFalse(wlm.is_open())

    def test_close_error(self, dll_patcher):
        """Calling close() is not allowed when open() has not been called (implicitly)."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount = {0: 0}.get
        wlm = HighFinesse_Wlm(Mock(), "support")

        with self.assertRaises(QMI_InvalidOperationException) as exc:
            wlm.close()

        self.assertEqual("Operation not allowed on closed instrument support", str(exc.exception))

    def test_get_version(self, dll_patcher):
        """The driver should give the version string in the right format."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWLMVersion.side_effect = {0: 1, 1: 12, 2: 0, 3: 20.4}.get

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertEqual(wlm.get_version(), "WLM Version: [1.12.0.20.4]")

        wlm._lib.dll.GetWLMVersion.assert_has_calls([call(0), call(1), call(2), call(3)])

    def test_get_idn(self, dll_patcher):
        """The driver should give the version string in the right format."""
        model = 6
        version = 123
        revision = 4321
        sw_ver = f"{version}.{revision}"
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWLMVersion.side_effect = {0: model, 1: version, 2: revision, 3: 987.654}.get

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            idn = wlm.get_idn()
            self.assertEqual(idn.vendor, "HighFinesse")
            self.assertEqual(idn.model, f"WLM-{model}")
            self.assertIsNone(idn.serial)
            self.assertEqual(idn.version, sw_ver)

        wlm._lib.dll.GetWLMVersion.assert_has_calls([call(0), call(1), call(2), call(3)])

    def test_get_operation_state(self, dll_patcher):
        """Test a happy flow with getting an operation state."""
        expected_op_state = 0  # stopped
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetOperationState.return_value = expected_op_state

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertEqual(expected_op_state, wlm.get_operation_state())

        wlm._lib.dll.GetOperationState.assert_called_once_with(expected_op_state)

    def test_get_frequency(self, dll_patcher):
        """The driver should return the frequency value that the library outputs."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetFrequencyNum.return_value = 42.

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertEqual(42., wlm.get_frequency(1))

        wlm._lib.dll.GetFrequencyNum.assert_called_once_with(1, 0.0)

    def test_get_frequency_error(self, dll_patcher):
        """The get_frequency() method should raise an error when the library gave an error code."""
        expected_error = 0.  # The call returns a double
        enum_name = f"WlmGetErr.{WlmGetErr(expected_error).name}"
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetFrequencyNum.return_value = expected_error

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_frequency(1)

        self.assertEqual(f"Error received from library call 'GetFrequencyNum': {enum_name}", str(exc.exception))

    def test_get_frequency_error_unknown(self, dll_patcher):
        """The get_frequency() method should raise an error when the library gave an error code."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetFrequencyNum.return_value = -42

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_frequency(1)

        self.assertEqual("Error received from library call 'GetFrequencyNum': -42", str(exc.exception))

    def test_get_wavelength(self, dll_patcher):
        """The driver should return the wavelength value that the library outputs."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWavelengthNum.return_value = 42.

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertEqual(42., wlm.get_wavelength(1))

        wlm._lib.dll.GetWavelengthNum.assert_called_once_with(1, 0.0)

    def test_get_wavelength_error(self, dll_patcher):
        """The get_wavelength() method should raise an error when the library gave an error code."""
        expected_error = -5.  # The call returns a double
        enum_name = f"WlmGetErr.{WlmGetErr(expected_error).name}"
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWavelengthNum.return_value = expected_error

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_wavelength(1)

        self.assertEqual(f"Error received from library call 'GetWavelengthNum': {enum_name}", str(exc.exception))

    def test_get_wavelength_channel_error(self, dll_patcher):
        """The get_wavelength() method should raise an error when the library gave an error code."""
        invalid_channel = 9
        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_wavelength(invalid_channel)

        self.assertEqual(f"Channel number out of range: {invalid_channel}", str(exc.exception))

    def test_get_power(self, dll_patcher):
        """The driver should return the power value that the library outputs."""
        expected_power = 1.23
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetPowerNum.return_value = expected_power

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertEqual(expected_power, wlm.get_power(1))

        wlm._lib.dll.GetPowerNum.assert_called_once_with(1, 0.0)

    def test_get_power_error(self, dll_patcher):
        """The get_power() method should raise an error when the library gave an error code."""
        expected_error = -2.  # The call returns a double
        enum_name = f"WlmGetErr.{WlmGetErr(expected_error).name}"
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetPowerNum.return_value = expected_error

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_power(1)

        self.assertEqual(f"Error received from library call 'GetPowerNum': {enum_name}", str(exc.exception))

    def test_get_power_returns_nan(self, dll_patcher):
        """The get_power() method allows NaN as a valid return value."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetPowerNum.return_value = nan

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
             power = wlm.get_power(1)

        numpy.testing.assert_equal(nan, power)

    def test_set_data_pattern_defaults(self, dll_patcher):
        """Test the set_data_patterns calls SetPattern with default index and i_enable."""
        default_index, default_enable = 1, True
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.SetPattern.return_value = 1  # no errors

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertIsNone(wlm.set_data_pattern())

        wlm._lib.dll.SetPattern.assert_called_once_with(default_index, default_enable)

    def test_set_data_pattern_inputs(self, dll_patcher):
        """Test the set_data_patterns calls SetPattern with correct index and i_enable."""
        expected_index, expected_enable = 4, False
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.SetPattern.return_value = 1  # no errors

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            self.assertIsNone(wlm.set_data_pattern(expected_index, expected_enable))

        wlm._lib.dll.SetPattern.assert_called_once_with(expected_index, expected_enable)

    def test_set_data_pattern_invalid_index(self, dll_patcher):
        """Test the set_data_patterns calls SetPattern with correct index and i_enable."""
        invalid_index = 10
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(ValueError):
                wlm.set_data_pattern(invalid_index)

    def test_get_data_pattern_data(self, dll_patcher):
        """Test get_data_pattern_data for getting data."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetPatternDataNum.return_value = 1  # exporting was enabled

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            data = wlm.get_data_pattern_data(1, 1, 2048)

        self.assertEqual(2048, data.size)
        wlm._lib.dll.GetPatternDataNum.assert_called_once()

    def test_get_data_pattern_data_invalid_index(self, dll_patcher):
        """Test get_data_pattern_data excepts with invalid index number."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(ValueError):
                wlm.get_data_pattern_data(1, 6, 2048)

    def test_get_data_pattern_data_pattern_not_enabled(self, dll_patcher):
        """Test get_data_pattern_data when the channel/index was not enabled."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetPatternDataNum.return_value = 0  # exporting was disabled

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            data = wlm.get_data_pattern_data(1, 1, 2048)

        self.assertEqual(2048, data.size)
        wlm._lib.dll.GetPatternDataNum.assert_called_once()

    def test_get_data_pattern_data_error(self, dll_patcher):
        """Test get_data_pattern_data excepts with error code."""
        wlmData.dll = dll_patcher.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetPatternDataNum.return_value = -6  # not available

        with HighFinesse_Wlm(self.ctx, "wlm") as wlm:
            with self.assertRaises(QMI_InstrumentException):
                wlm.get_data_pattern_data(1, 1, 2048)
