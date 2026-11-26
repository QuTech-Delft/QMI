"""Unit-tests for the Newport 843-R optical power meter driver."""

import logging
import math
import unittest
from unittest.mock import MagicMock, call, patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.instruments.newport.newport_843r import Newport_843R

from tests.patcher import PatcherQmiContext as QMI_Context

MODULE = "qmi.instruments.newport.newport_843r"
SERIAL_NUMBER = "SN12345"


class TestNewport843R(unittest.TestCase):
    """Testcase for the Newport_843R class."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)

        self._ctx = QMI_Context("Newport843RContext")
        self._ctx.start()
        self.addCleanup(self._ctx.stop)

        self.instr = Newport_843R(self._ctx, "pm", SERIAL_NUMBER)

    def tearDown(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.NOTSET)

    def _open_with_mock_transport(self) -> MagicMock:
        """Open the instrument with a mocked low-level USB connection; return that mock."""
        mock_libusb_instance = MagicMock()
        with patch(f"{MODULE}.Newport_843R_libusb", return_value=mock_libusb_instance):
            self.instr.open()
        return mock_libusb_instance

    def test_list_instruments(self):
        """Newport_843R.list_instruments(), happy flow"""
        with patch(f"{MODULE}.Newport_843R_libusb.list_instruments", return_value=["SN1", "SN2"]) as mock_list:
            result = Newport_843R.list_instruments()

        mock_list.assert_called_once_with()
        self.assertEqual(result, ["SN1", "SN2"])

    def test_init(self):
        """Newport_843R.__init__(), happy flow"""
        self.assertEqual(self.instr._serial_number, SERIAL_NUMBER)
        self.assertIsNone(self.instr._instr)
        self.assertEqual(self.instr._last_query_time, 0.0)

    def test_open(self):
        """Newport_843R.open(), happy flow"""
        mock_libusb_instance = MagicMock()
        mock_super = MagicMock()
        with patch(f"{MODULE}.Newport_843R_libusb", return_value=mock_libusb_instance) as mock_libusb_cls, \
             patch(f"{MODULE}.super", mock_super), \
             patch(f"{MODULE}.time.monotonic", return_value=123.5):
            self.instr.open()

        mock_libusb_cls.assert_called_once_with(SERIAL_NUMBER)
        self.assertIs(self.instr._instr, mock_libusb_instance)
        self.assertEqual(self.instr._last_query_time, 123.5)
        mock_super().open.assert_called_once_with()

    def test_open_already_open(self):
        """Newport_843R.open(), already open raises"""
        self._open_with_mock_transport()
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.open()

    def test_close(self):
        """Newport_843R.close(), happy flow"""
        mock_libusb_instance = self._open_with_mock_transport()
        mock_super = MagicMock()
        with patch(f"{MODULE}.super", mock_super):
            self.instr.close()

        mock_libusb_instance.close.assert_called_once_with()
        self.assertIsNone(self.instr._instr)
        mock_super().close.assert_called_once_with()

    def test_close_not_open(self):
        """Newport_843R.close(), not open raises"""
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.close()

    def test_ask(self):
        """Newport_843R.ask(), happy flow"""
        mock_libusb_instance = self._open_with_mock_transport()
        mock_libusb_instance.read_response.return_value = b"*OK\r\n"

        with patch(f"{MODULE}.time.sleep"):
            resp = self.instr.ask("$XX")

        mock_libusb_instance.send_command.assert_called_once_with(b"$XX\r\n")
        mock_libusb_instance.read_response.assert_called_once_with(timeout=5)
        self.assertEqual(resp, "*OK")

    def test_ask_not_open(self):
        """Newport_843R.ask(), not open raises"""
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.ask("$XX")

    def test_ask_invalid_command(self):
        """Newport_843R.ask(), command not starting with '$' raises"""
        self._open_with_mock_transport()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.ask("XX")

    def test_ask_error_response(self):
        """Newport_843R.ask(), error response raises"""
        mock_libusb_instance = self._open_with_mock_transport()
        mock_libusb_instance.read_response.return_value = b"?SOME ERROR\n"

        with patch(f"{MODULE}.time.sleep"):
            with self.assertRaises(QMI_InstrumentException):
                self.instr.ask("$XX")

    def test_ask_unexpected_response(self):
        """Newport_843R.ask(), unexpected response raises"""
        mock_libusb_instance = self._open_with_mock_transport()
        mock_libusb_instance.read_response.return_value = b"GARBAGE\n"

        with patch(f"{MODULE}.time.sleep"):
            with self.assertRaises(QMI_InstrumentException):
                self.instr.ask("$XX")

    def test_reset(self):
        """Newport_843R.reset(), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.reset()
        self.instr.ask.assert_called_once_with("$RE")

    def test_get_idn(self):
        """Newport_843R.get_idn(), happy flow"""
        self.instr.ask = MagicMock(side_effect=["*TYPE SN001 843-R-USB", "*EFv2.1"])
        result = self.instr.get_idn()

        self.instr.ask.assert_has_calls([call("$II"), call("$VE")])
        self.assertEqual(result.vendor, "Newport")
        self.assertEqual(result.model, "843-R-USB")
        self.assertEqual(result.serial, "SN001")
        self.assertEqual(result.version, "v2.1")

    def test_get_idn_invalid_instr_info(self):
        """Newport_843R.get_idn(), invalid $II response raises"""
        self.instr.ask = MagicMock(side_effect=["*TYPE SN001", "*EFv2.1"])
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_get_idn_invalid_version_info(self):
        """Newport_843R.get_idn(), invalid $VE response raises"""
        self.instr.ask = MagicMock(side_effect=["*TYPE SN001 843-R-USB", "*BAD"])
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_get_sensor_info(self):
        """Newport_843R.get_sensor_info(), happy flow"""
        self.instr.ask = MagicMock(return_value="*BT SN001 MyName CAP1")
        result = self.instr.get_sensor_info()

        self.instr.ask.assert_called_once_with("$HI")
        self.assertEqual(result, ("BT", "SN001", "MyName", "CAP1"))

    def test_get_sensor_info_invalid_response(self):
        """Newport_843R.get_sensor_info(), invalid response raises"""
        self.instr.ask = MagicMock(return_value="*BT SN001")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_sensor_info()

    def test_get_filter_mode_in(self):
        """Newport_843R.get_filter_mode(), filter in"""
        self.instr.ask = MagicMock(return_value="*2 OUT IN")
        self.assertTrue(self.instr.get_filter_mode())

    def test_get_filter_mode_out(self):
        """Newport_843R.get_filter_mode(), filter out"""
        self.instr.ask = MagicMock(return_value="*1 OUT IN")
        self.assertFalse(self.instr.get_filter_mode())

    def test_get_filter_mode_not_applicable(self):
        """Newport_843R.get_filter_mode(), sensor without filter support"""
        self.instr.ask = MagicMock(return_value="*1 N/A")
        self.assertFalse(self.instr.get_filter_mode())

    def test_get_filter_mode_invalid_response(self):
        """Newport_843R.get_filter_mode(), invalid response raises"""
        self.instr.ask = MagicMock(return_value="*5 OUT IN")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_filter_mode()

    def test_set_filter_mode_true(self):
        """Newport_843R.set_filter_mode(True), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.set_filter_mode(True)
        self.instr.ask.assert_called_once_with("$FQ 2")

    def test_set_filter_mode_false(self):
        """Newport_843R.set_filter_mode(False), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.set_filter_mode(False)
        self.instr.ask.assert_called_once_with("$FQ 1")

    def test_get_power(self):
        """Newport_843R.get_power(), happy flow"""
        self.instr.ask = MagicMock(return_value="*0.00123")
        self.assertEqual(self.instr.get_power(), 0.00123)

    def test_get_power_over_range(self):
        """Newport_843R.get_power(), over-range response"""
        self.instr.ask = MagicMock(return_value="*OVER")
        self.assertEqual(self.instr.get_power(), math.inf)

    def test_get_timestamped_power(self):
        """Newport_843R.get_timestamped_power(), happy flow"""
        self.instr.ask = MagicMock(return_value="*0.002")
        with patch(f"{MODULE}.time.time", return_value=1700000000.0):
            result = self.instr.get_timestamped_power()

        self.assertEqual(result, (1700000000.0, 0.002))

    def test_get_timestamped_power_over_range(self):
        """Newport_843R.get_timestamped_power(), over-range response"""
        self.instr.ask = MagicMock(return_value="*OVER")
        with patch(f"{MODULE}.time.time", return_value=1700000000.0):
            result = self.instr.get_timestamped_power()

        self.assertEqual(result, (1700000000.0, math.inf))

    def test_do_zero(self):
        """Newport_843R.do_zero(), happy flow"""
        self.instr.ask = MagicMock(side_effect=["*ZE OK", "*ZEROING IN PROGRESS", "*ZEROING COMPLETE"])
        with patch(f"{MODULE}.time.sleep"):
            self.instr.do_zero()

        self.instr.ask.assert_has_calls([call("$ZE"), call("$ZQ"), call("$ZQ")])

    def test_do_zero_failure(self):
        """Newport_843R.do_zero(), zeroing failure raises"""
        self.instr.ask = MagicMock(side_effect=["*ZE OK", "*ZEROING FAILED"])
        with patch(f"{MODULE}.time.sleep"):
            with self.assertRaises(QMI_InstrumentException):
                self.instr.do_zero()

    def test_zero_save(self):
        """Newport_843R.zero_save(), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.zero_save()
        self.instr.ask.assert_called_once_with("$ZS")

    def test_get_available_ranges(self):
        """Newport_843R.get_available_ranges(), happy flow"""
        self.instr.ask = MagicMock(return_value="*2 AUTO 3.00uW 30.0uW 300uW")
        result = self.instr.get_available_ranges()
        self.assertEqual(result, ["3.00uW", "30.0uW", "300uW"])

    def test_get_range(self):
        """Newport_843R.get_range(), happy flow"""
        self.instr.ask = MagicMock(return_value="* 3")
        self.assertEqual(self.instr.get_range(), 3)
        self.instr.ask.assert_called_once_with("$RN")

    def test_get_range_in_use(self):
        """Newport_843R.get_range_in_use(), happy flow"""
        self.instr.ask = MagicMock(return_value="* 1")
        self.assertEqual(self.instr.get_range_in_use(), 1)
        self.instr.ask.assert_called_once_with("$GU")

    def test_set_range(self):
        """Newport_843R.set_range(), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.set_range(2)
        self.instr.ask.assert_called_once_with("$WN 2")

    def test_set_range_autorange_value(self):
        """Newport_843R.set_range(-1), autorange sentinel value"""
        self.instr.ask = MagicMock()
        self.instr.set_range(-1)
        self.instr.ask.assert_called_once_with("$WN -1")

    def test_set_autorange_enable(self):
        """Newport_843R.set_autorange(True), happy flow"""
        self.instr.set_range = MagicMock()
        self.instr.set_autorange(True)
        self.instr.set_range.assert_called_once_with(-1)

    def test_set_autorange_disable(self):
        """Newport_843R.set_autorange(False), happy flow"""
        self.instr.set_range = MagicMock()
        self.instr.get_range_in_use = MagicMock(return_value=2)
        self.instr.set_autorange(False)
        self.instr.get_range_in_use.assert_called_once_with()
        self.instr.set_range.assert_called_once_with(2)

    def test_get_wavelength_range(self):
        """Newport_843R.get_wavelength_range(), happy flow"""
        self.instr.ask = MagicMock(return_value="*CONTINUOUS 400 1100 1 650")
        self.assertEqual(self.instr.get_wavelength_range(), (400, 1100))

    def test_get_wavelength_range_too_short(self):
        """Newport_843R.get_wavelength_range(), response too short raises"""
        self.instr.ask = MagicMock(return_value="*CONTINUOUS 400 1100")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_wavelength_range()

    def test_get_wavelength_range_not_continuous(self):
        """Newport_843R.get_wavelength_range(), non-continuous sensor raises"""
        self.instr.ask = MagicMock(return_value="*STEPPED 400 1100 1 650")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_wavelength_range()

    def test_get_wavelength(self):
        """Newport_843R.get_wavelength(), happy flow"""
        self.instr.ask = MagicMock(return_value="*CONTINUOUS 400 1100 1 650")
        self.assertEqual(self.instr.get_wavelength(), 650)

    def test_get_wavelength_too_short(self):
        """Newport_843R.get_wavelength(), response too short raises"""
        self.instr.ask = MagicMock(return_value="*CONTINUOUS 400 1100")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_wavelength()

    def test_get_wavelength_not_continuous(self):
        """Newport_843R.get_wavelength(), non-continuous sensor raises"""
        self.instr.ask = MagicMock(return_value="*STEPPED 400 1100 1 650")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_wavelength()

    def test_get_wavelength_invalid_index(self):
        """Newport_843R.get_wavelength(), out-of-range index raises"""
        self.instr.ask = MagicMock(return_value="*CONTINUOUS 400 1100 9 650")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_wavelength()

    def test_set_wavelength(self):
        """Newport_843R.set_wavelength(), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.set_wavelength(850)
        self.instr.ask.assert_called_once_with("$WL 850")

    def test_get_available_averaging(self):
        """Newport_843R.get_available_averaging(), happy flow"""
        self.instr.ask = MagicMock(return_value="*1 NONE 1sec 3sec")
        self.assertEqual(self.instr.get_available_averaging(), ["NONE", "1sec", "3sec"])

    def test_get_averaging_mode(self):
        """Newport_843R.get_averaging_mode(), happy flow"""
        self.instr.ask = MagicMock(return_value="*2 NONE 1sec 3sec")
        self.assertEqual(self.instr.get_averaging_mode(), 2)

    def test_set_averaging_mode(self):
        """Newport_843R.set_averaging_mode(), happy flow"""
        self.instr.ask = MagicMock()
        self.instr.set_averaging_mode(1)
        self.instr.ask.assert_called_once_with("$AQ 1")
