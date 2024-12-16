import logging
from unittest import TestCase
from unittest.mock import patch, Mock

import qmi
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_InstrumentException
from qmi.instruments.high_finesse import HighFinesse_WS
from qmi.instruments.high_finesse import wlmData
from qmi.utils.context_managers import open_close, start_stop

# Disable all logging
logging.disable(logging.CRITICAL)


class TestHighFinesse_WS_Linux(TestCase):
    """Test the behavior of the High Finesse driver on a Linux platform."""

    def setUp(self):
        """Make the sys mock say that we run on Linux, so the test is platform-independent."""
        patcher = patch("qmi.instruments.high_finesse.support._library_wrapper.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="linux")
        self.addCleanup(patcher.stop)

    @patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
    def test_init(self, mocker):
        """The LoadDLL function should be called once."""
        wlm = HighFinesse_WS(Mock(), "support")
        self.assertEqual(wlm.get_name(), "support")

        wlm.open()
        mocker.assert_called_once_with("libwlmData.so")
        wlm.close()


class TestHighFinesse_WS_Unknown(TestCase):
    """Test the behavior of the High Finesse driver on an unknown platform (e.g. "cygwin")."""

    def setUp(self):
        """Make the sys mock say that we run on an unsupported platform."""
        patcher = patch("qmi.instruments.high_finesse.support._library_wrapper.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="cygwin")
        self.addCleanup(patcher.stop)

    @patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
    def test_exception_on_open(self, mocker):
        """The LoadDLL function should not be called."""
        with self.assertRaises(OSError) as exc:
            wlm = HighFinesse_WS(Mock(), "support")
            wlm.open()
        self.assertEqual("Unsupported platform", str(exc.exception))
        mocker.assert_not_called()


@patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
class TestHighFinesse_WS(TestCase):
    """Test the behavior of the High Finesse driver (with the actual dll mocked)."""

    def test_open(self, mocker):
        """The connection should be 'open' after open() was (implicitly) called."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            self.assertTrue(wlm.is_open())

    def test_open_error(self, mocker):
        """The driver should give an error when an open connection is opened again."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            with self.assertRaises(QMI_InvalidOperationException) as exc:
                wlm.open()
        self.assertEqual("Operation not allowed on open instrument wlm", str(exc.exception))

    def test_get_version(self, mocker):
        """The driver should give the version string in the right format."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWLMVersion.side_effect = {0: 1, 1: 12, 2: 0, 3: 204}.get

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            self.assertEqual(wlm.get_version(), "WLM Version: [1.12.0.204]")

    def test_get_idn(self, mocker):
        """The driver should give the version string in the right format."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWLMVersion.side_effect = {0: 6, 1: 123, 2: 4321, 3: 6}.get

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            idn = wlm.get_idn()
            self.assertEqual(idn.vendor, "HighFinesse")
            self.assertEqual(idn.model, "WLM-6")
            self.assertEqual(idn.serial, "123")
            self.assertEqual(idn.version, "4321")

    def test_get_frequency(self, mocker):
        """The driver should return the frequency value that the library outputs."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetFrequencyNum.return_value = 42.

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            self.assertEqual(42., wlm.get_frequency(1))

    def test_get_frequency_error(self, mocker):
        """The get_frequency() method should raise an error when the library gave an error code."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetFrequencyNum.return_value = -1.

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_frequency(1)
        self.assertEqual("Error received from library call 'GetFrequencyNum': WS8_ERR.NO_SIGNAL",
                         str(exc.exception))

    def test_get_frequency_error_unknown(self, mocker):
        """The get_frequency() method should raise an error when the library gave an error code."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetFrequencyNum.return_value = -42.

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_frequency(1)
        self.assertEqual("Error received from library call 'GetFrequencyNum': -42.0",
                         str(exc.exception))

    def test_get_wavelength(self, mocker):
        """The driver should return the wavelength value that the library outputs."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWavelengthNum.return_value = 42.

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            self.assertEqual(42., wlm.get_wavelength(1))

    def test_get_wavelength_error(self, mocker):
        """The get_wavelength() method should raise an error when the library gave an error code."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWavelengthNum.return_value = -1.

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_wavelength(1)
        self.assertEqual("Error received from library call 'GetWavelengthNum': WS8_ERR.NO_SIGNAL",
                         str(exc.exception))

    def test_get_wavelength_channel_error(self, mocker):
        """The get_wavelength() method should raise an error when the library gave an error code."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount.side_effect = {0: 1}.get
        wlmData.dll.GetWavelengthNum.return_value = -1.

        with start_stop(qmi, "highfinesse_wlm_client", console_loglevel="WARNING"), open_close(qmi.make_instrument(
                instrument_name="wlm",
                instrument_class=HighFinesse_WS)
        ) as wlm:
            with self.assertRaises(QMI_InstrumentException) as exc:
                wlm.get_wavelength(9)
        self.assertEqual("Channel number out of range: 9",
                         str(exc.exception))

    def test_close(self, mocker):
        """The connection should not be open after close() is called."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount = {0: 0}.get

        wlm = HighFinesse_WS(Mock(), "support")
        self.assertFalse(wlm.is_open())
        wlm.open()
        self.assertTrue(wlm.is_open())
        wlm.close()
        self.assertFalse(wlm.is_open())

    def test_close_error(self, mocker):
        """Calling close() is not allowed when open() has not been called (implicitly)."""
        wlmData.dll = mocker.return_value
        wlmData.dll.GetWLMCount = {0: 0}.get
        wlm = HighFinesse_WS(Mock(), "support")

        with self.assertRaises(QMI_InvalidOperationException) as exc:
            wlm.close()
        self.assertEqual("Operation not allowed on closed instrument support", str(exc.exception))
