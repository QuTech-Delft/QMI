import typing
import unittest
from unittest.mock import Mock

from qmi.instruments.picotech import _picoscope
from qmi.core.exceptions import QMI_InstrumentException, QMI_UnknownNameException

import tests.instruments.picotech.picosdk_stub
from tests.instruments.picotech.ps3000a_stub import ps3000a
from tests.instruments.picotech.ps4000a_stub import ps4000a


class PicoscopeFind3000AInstrumentsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._picoscope = _picoscope.PicoTech_PicoScope
        _picoscope.COMMAND_DICT = {}
        _picoscope._ps = tests.instruments.picotech.ps3000a_stub.ps3000a
        _picoscope._ps.ps3000aEnumerateUnits = Mock(return_value=0)

    def test_01_listing_instruments(self):
        """ This test should run without raising any exceptions and update COMMAND_DICT"""
        self.assertDictEqual(_picoscope.COMMAND_DICT, {})
        expected_stop = {"Stop": ps3000a.ps3000aStop}
        instrus = self._picoscope.list_instruments("3000a")
        self.assertIsInstance(instrus, list)
        self.assertTrue(set(expected_stop).issubset(set(_picoscope.COMMAND_DICT)))

    def test_02_err(self):
        """ Test the error self-check function """
        _picoscope._import_modules("3000a")
        with self.assertRaises(QMI_InstrumentException):
            _picoscope._check_error(1)

    def test_03_import_modules_with_wrong_library_errors(self):
        """ Giving different library name as input that what is the library loaded should raise an exception """
        with self.assertRaises(QMI_UnknownNameException):
            _picoscope._import_modules("4000a")

        self.assertDictEqual(_picoscope.COMMAND_DICT, {})


class PicoscopeFind4000AInstrumentsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._picoscope = _picoscope.PicoTech_PicoScope
        _picoscope.COMMAND_DICT = {}
        _picoscope._ps = tests.instruments.picotech.ps4000a_stub.ps4000a
        _picoscope._ps.ps4000aEnumerateUnits = Mock(return_value=0)

    def test_01_listing_instruments(self):
        """ This test should run without raising any exceptions and update COMMAND_DICT"""
        self.assertDictEqual(_picoscope.COMMAND_DICT, {})
        expected_stop = {"Stop": ps4000a.ps4000aStop}
        instrus = self._picoscope.list_instruments("4000a")
        self.assertIsInstance(instrus, list)
        self.assertTrue(set(expected_stop).issubset(set(_picoscope.COMMAND_DICT)))

    def test_02_err(self):
        """ Test the error self-check function """
        _picoscope._import_modules("4000a")
        with self.assertRaises(QMI_InstrumentException):
            _picoscope._check_error(1)

    def test_03_import_modules_with_wrong_library_errors(self):
        """ Giving different library name as input that what is the library loaded should raise an exception """
        with self.assertRaises(QMI_UnknownNameException):
            _picoscope._import_modules("3000a")

        self.assertDictEqual(_picoscope.COMMAND_DICT, {})


class PicotechPicoscopeBaseClassTestCase(unittest.TestCase):
    """Test case for testing the base class functions."""
    def test_not_implemented_methods_raise_exception(self):
        """See that `run_block` and `get_time_resolution` of the base class raise exception when called."""
        with self.assertRaises(NotImplementedError):
            _picoscope.PicoTech_PicoScope(Mock(), "test_run_block", "sn1234").run_block(1, 2, 3)

        with self.assertRaises(NotImplementedError):
            _picoscope.PicoTech_PicoScope(Mock(), "test_get_t_res", "sn1234").get_sampling_interval(1)


if __name__ == "__main__":
    unittest.main()
