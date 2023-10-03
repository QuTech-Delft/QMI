import os
import tempfile
import unittest
import unittest.mock
from unittest.mock import patch
import pathlib

import numpy as np

from qmi.core.exceptions import QMI_InstrumentException, QMI_ConfigurationException
from qmi.instruments.adwin.adwin import Adwin_Base
from qmi.utils.adwin_manager import AdwinProgramLibrary, AdwinProcess, AdwinManager, ProgramInfo
from qmi.utils.adbasic_compiler import AdbasicCompilerException, AdbasicError

CONFIG_BASE = """# Comment
{
    # File name of the top-level ".bas" file without the ".bas" extension.
    "file": "program_key_error",

    # Process slot number on the ADwin (range 1 to 10).
    "slot": 9,

    # Event trigger source (either "timer" or "external").
    "trigger": "external",

    # Process priority (integer between -10 and +10 for low priority, or 1000 for high priority).
    "priority": 1000,

    # True to discover parameters by parsing the ADbasic source code.
    "parse_parameters": true
}
"""


def write_source_file(tempdir, file_name, content):
    with open(os.path.join(tempdir, file_name), "w") as outf:
        outf.write(content)


class AdwinProgramLibraryTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._test_data_dir = os.path.join(os.path.dirname(__file__), 'data')
        # Load adwin program library with default parameters; processor = T12, HW = PII
        self._adwin_program_library = AdwinProgramLibrary(self._test_data_dir, self._test_data_dir)

    def test_list_programs(self):
        # arrange
        expected_program_list = ["program_a", "program_b", "program_c", "program_d", "program_e"]

        # act
        program_list = self._adwin_program_library.list_programs()

        # assert
        self.assertTrue(all(program in expected_program_list for program in program_list))

    def test_get_program_info(self):
        """Get program info from configuration for loaded programs"""
        # act
        prog_a_info = self._adwin_program_library.get_program_info("program_a")
        param_a_info = prog_a_info.param_info
        prog_b_info = self._adwin_program_library.get_program_info("program_b")
        param_b_info = prog_b_info.param_info
        prog_c_info = self._adwin_program_library.get_program_info("program_c")
        param_c_info = prog_c_info.param_info

        # assert
        self.assertIn("foo", param_a_info.param.keys())
        self.assertIn("bar", param_a_info.param.keys())
        self.assertIn("foobar", param_b_info.param.keys())
        self.assertIn("foo", param_c_info.param.keys())
        self.assertIn("bar", param_c_info.param.keys())

    def test_get_program_info_from_config_file(self):
        """Now test the same from the file using the ProgramInfo class method."""
        # act
        prog_a_conf = os.path.join(self._test_data_dir, "program_a.conf")
        prog_a_info = ProgramInfo.from_config_file(prog_a_conf, self._test_data_dir)
        param_a_info = prog_a_info.param_info
        prog_b_conf = os.path.join(self._test_data_dir, "program_b.conf")
        prog_b_info = ProgramInfo.from_config_file(prog_b_conf, self._test_data_dir)  # , processor_type="T12.1")
        param_b_info = prog_b_info.param_info
        prog_c_conf = os.path.join(self._test_data_dir, "program_c.conf")
        prog_c_info = ProgramInfo.from_config_file(prog_c_conf, self._test_data_dir)  # , processor_type="T11")
        param_c_info = prog_c_info.param_info

        # assert
        self.assertIn("foo", param_a_info.param.keys())
        self.assertIn("bar", param_a_info.param.keys())
        self.assertIn("foobar", param_b_info.param.keys())
        self.assertIn("foo", param_c_info.param.keys())
        self.assertIn("bar", param_c_info.param.keys())

    def test_get_program_info_false_parse_parameters(self):
        """parse_parameters is now set as 'false', so specific read of 'par', 'fpar', and 'par_array' will be done"""
        # act
        prog_d_info = self._adwin_program_library.get_program_info("program_d")
        param_d_info = prog_d_info.param_info

        # assert
        self.assertIn("uno", param_d_info.param.keys())
        self.assertIn("due.zero", param_d_info.param.keys())
        self.assertIn("tres_quattro", param_d_info.param.keys())

    def test_get_program_info_twice(self):
        """Second 'get' should return info immediately without reading config"""
        # act
        prog_d_info = self._adwin_program_library.get_program_info("program_d")
        prog_d_info_again = self._adwin_program_library.get_program_info("program_d")

        # assert
        self.assertEqual(prog_d_info, prog_d_info_again)

    def test_get_program_info_raises_exception(self):
        """Should raise exception due to double variable name 'uno'"""
        # assert
        with self.assertRaises(QMI_ConfigurationException):
            self._adwin_program_library.get_program_info("program_e")

    @patch("qmi.utils.adwin_manager.compile_program")
    def test_compile_fail(self, patser):
        """Test the compile function fails at compiling the fake program, as expected"""
        # arrange
        message = "no real message"
        error = AdbasicError(
            error_number=2,
            error_description="test error",
            error_line="well I wanted it to err",
            filename="this file",
            line_number=5
        )
        patser.side_effect = AdbasicCompilerException(message, [error])
        patser.start()
        # act
        with self.assertRaises(AdbasicCompilerException) as ad_err:
            self._adwin_program_library.compile("program_d")

        self.assertEqual(ad_err.exception.adbasic_errors, [error])
        self.assertEqual(ad_err.exception.message, message)
        patser.stop()

    def test_config_has_wrong_key(self):
        """Test that wrong key in the config file raises exception."""
        file_name = "bas.conf"
        expected_exc = f"Error reading Adwin program config {file_name}"
        config_with_wrong_key = CONFIG_BASE.replace("slot", "plot")
        with tempfile.TemporaryDirectory(prefix="bastest") as tempdir:
            with self.assertRaises(QMI_ConfigurationException) as exc:
                write_source_file(tempdir, file_name, config_with_wrong_key)
                AdwinProgramLibrary(tempdir, tempdir)

            self.assertEqual(str(exc.exception), expected_exc)

    def test_config_has_wrong_slot_number(self):
        """Test that wrong slot number in the config file raises exception."""
        file_name = "bas.conf"
        expected_exc = "Invalid ADwin process slot number 0 for program 'bas'"
        config_with_wrong_key = CONFIG_BASE.replace('"slot": 9', '"slot": 0')
        with tempfile.TemporaryDirectory(prefix="bastest") as tempdir:
            with self.assertRaises(QMI_ConfigurationException) as exc:
                write_source_file(tempdir, file_name, config_with_wrong_key)
                AdwinProgramLibrary(tempdir, tempdir)

            self.assertEqual(str(exc.exception), expected_exc)

    def test_config_has_wrong_trigger(self):
        """Test that wrong slot number in the config file raises exception."""
        file_name = "bas.conf"
        expected_exc = "Invalid ADwin process trigger 'internal' for program 'bas'"
        config_with_wrong_key = CONFIG_BASE.replace('"trigger": "external"', '"trigger": "internal"')
        with tempfile.TemporaryDirectory(prefix="bastest") as tempdir:
            with self.assertRaises(QMI_ConfigurationException) as exc:
                write_source_file(tempdir, file_name, config_with_wrong_key)
                AdwinProgramLibrary(tempdir, tempdir)

            self.assertEqual(str(exc.exception), expected_exc)

    def test_config_has_wrong_priority_number(self):
        """Test that wrong priority number in the config file raises exception."""
        file_name = "bas.conf"
        expected_exc = "Invalid ADwin process priority 100 for program 'bas'"
        config_with_wrong_key = CONFIG_BASE.replace('"priority": 1000', '"priority": 100')
        with tempfile.TemporaryDirectory(prefix="bastest") as tempdir:
            with self.assertRaises(QMI_ConfigurationException) as exc:
                write_source_file(tempdir, file_name, config_with_wrong_key)
                AdwinProgramLibrary(tempdir, tempdir)

            self.assertEqual(str(exc.exception), expected_exc)

    def test_config_has_wrong_parameters(self):
        """Test that wrong slot number in the config file raises exception."""
        file_name = "bas.conf"
        expected_exc = "Invalid configuration for ADwin program 'bas': " + \
                       "Can not parse source code and specify explicit parameters"
        config_with_wrong_key = CONFIG_BASE[:-3] + ',\n\n\t"par": {"uno": 1}\n}'
        with tempfile.TemporaryDirectory(prefix="bastest") as tempdir:
            with self.assertRaises(QMI_ConfigurationException) as exc:
                write_source_file(tempdir, file_name, config_with_wrong_key)
                AdwinProgramLibrary(tempdir, tempdir)

            self.assertEqual(str(exc.exception), expected_exc)


class AdwinProcessTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._test_data_dir = os.path.join(pathlib.Path(__file__).parent, 'data')

        self._adwin_program_library = AdwinProgramLibrary(self._test_data_dir, self._test_data_dir)
        self._adwin_program_library_b = AdwinProgramLibrary(self._test_data_dir, self._test_data_dir, "T12.1")
        self._adwin_program_library_d = AdwinProgramLibrary(self._test_data_dir, self._test_data_dir, "T11", "GII")

        self._adwin_mock = unittest.mock.MagicMock(spec=Adwin_Base)
        self._adwin_mock.is_process_running.return_value = False

        proc_a_info = self._adwin_program_library.get_program_info("program_a")
        proc_b_info = self._adwin_program_library_b.get_program_info("program_b")
        proc_d_info = self._adwin_program_library_d.get_program_info("program_d")

        self._adwin_mock.get_processor_type.return_value = "T12"
        self._adwin_proc = AdwinProcess(self._adwin_mock, "program_a", proc_a_info)
        self._adwin_mock.get_processor_type.return_value = "T12.1"
        self._adwin_proc_b = AdwinProcess(self._adwin_mock, "program_b", proc_b_info)
        self._adwin_mock.get_processor_type.return_value = "T11"
        self._adwin_proc_d = AdwinProcess(self._adwin_mock, "program_d", proc_d_info)

    def test_program_library_instances(self):
        """Test that the hardware and processor types are set correctly in the different program libraries."""
        expected_a = ["T12", "PII"]  # Defaults
        expected_b = ["T12.1", "PII"]
        expected_d = ["T11", "GII"]

        check_list_a = [self._adwin_program_library._processor_type, self._adwin_program_library._hardware_type]
        check_list_b = [self._adwin_program_library_b._processor_type, self._adwin_program_library_b._hardware_type]
        check_list_d = [self._adwin_program_library_d._processor_type, self._adwin_program_library_d._hardware_type]

        self.assertListEqual(expected_a, check_list_a)
        self.assertListEqual(expected_b, check_list_b)
        self.assertListEqual(expected_d, check_list_d)

        self.assertEqual(expected_a[0], self._adwin_proc._processor_type)
        self.assertEqual(expected_b[0], self._adwin_proc_b._processor_type)
        self.assertEqual(expected_d[0], self._adwin_proc_d._processor_type)

    def test_load(self):
        """Test loading without starting process"""
        file = os.path.join(pathlib.Path(__file__).parent, "data", "program_a")
        slot = 9
        expected_load_bin_file = f"{file}" + ".TC{}".format(slot % 10)
        self._adwin_proc.load()
        self._adwin_mock.load_process.assert_called_once_with(expected_load_bin_file)

    def test_load_b(self):
        """Test loading without starting process, with T12.1 processor"""
        file = os.path.join(pathlib.Path(__file__).parent, "data", "program_b")
        slot = 10
        expected_load_bin_file = f"{file}" + ".TC{}".format(slot % 10)
        self._adwin_proc_b.load()
        self._adwin_mock.load_process.assert_called_once_with(expected_load_bin_file)

    def test_load_d(self):
        """Test loading without starting process, with T11 processor"""
        file = os.path.join(pathlib.Path(__file__).parent, "data", "program_d")
        slot = 10
        expected_load_bin_file = f"{file}" + ".TB{}".format(slot % 10)
        self._adwin_proc_d.load()
        self._adwin_mock.load_process.assert_called_once_with(expected_load_bin_file)

    def test_start_with_params(self):
        self._adwin_proc.start_with_params(foo=10, Bar=11)

        self._adwin_mock.is_process_running.assert_called_once_with(9)

        self._adwin_mock.set_par.assert_has_calls([unittest.mock.call(1, 10), unittest.mock.call(2, 11)])

    def test_dont_start_with_params_if_running(self):
        self._adwin_mock.is_process_running.return_value = True
        with self.assertRaises(QMI_InstrumentException):
            self._adwin_proc.start_with_params(foo=10, Bar=11)

    def test_start(self):
        self._adwin_proc.start()
        self._adwin_mock.is_process_running.assert_called_once_with(9)

    def test_dont_start_if_running(self):
        self._adwin_mock.is_process_running.return_value = True
        with self.assertRaises(QMI_InstrumentException):
            self._adwin_proc.start()

    def test_stop(self):
        """Test stopping a process"""
        self._adwin_proc.stop()
        self._adwin_mock.stop_process.assert_called_once()

    def test_is_running(self):
        """Test the 'is_running' call"""
        is_it = self._adwin_proc.is_running()
        self.assertFalse(is_it)
        self._adwin_mock.is_process_running.assert_called_once_with(9)

    def test_wait_for_process(self):
        """Test the 'wait_for_process' call"""
        timeout = 0.01
        self._adwin_proc.wait_for_process(timeout)
        self._adwin_mock.wait_for_process.assert_called_once_with(9, timeout)

    def test_get_par(self):
        """Test getting parameters"""
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_fpar.side_effect = [1.0]
        self._adwin_mock.get_data.side_effect = [np.array([1000])]

        self._adwin_proc.start()
        par_foo = self._adwin_proc.get_par('foo')
        par_bar = self._adwin_proc.get_par('bar')
        par_baz = self._adwin_proc.get_par('baz')
        par_elem_boo = self._adwin_proc.get_par('elem_boo')

        self.assertEqual(par_foo, 10)
        self.assertEqual(par_bar, 100)
        self.assertAlmostEqual(par_baz, 1.0)
        self.assertEqual(par_elem_boo, 1000)

    def test_get_par_case_insensitive(self):
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_fpar.side_effect = [1.0]
        self._adwin_mock.get_data.side_effect = [np.array([1000])]

        self._adwin_proc.start()
        par_foo = self._adwin_proc.get_par('Foo')
        par_bar = self._adwin_proc.get_par('BAR')
        par_baz = self._adwin_proc.get_par('baz')
        par_elem_boo = self._adwin_proc.get_par('elem_boo')

        self.assertEqual(par_foo, 10)
        self.assertEqual(par_bar, 100)
        self.assertAlmostEqual(par_baz, 1.0)
        self.assertEqual(par_elem_boo, 1000)

    def test_set_par(self):
        self._adwin_proc.start()
        self._adwin_proc.set_par('Foo', 100)
        self._adwin_proc.set_par('BAR', 10)
        self._adwin_proc.set_par('baz', 2.0)
        self._adwin_proc.set_par('eLeM_BoO', 8)

        self._adwin_mock.set_par.assert_has_calls([unittest.mock.call(1, 100), unittest.mock.call(2, 10)])
        self._adwin_mock.set_fpar.assert_has_calls([unittest.mock.call(5, 2.0)])
        self._adwin_mock.set_data.assert_has_calls([unittest.mock.call(10, 1., np.array([8]))])

    def test_set_par_case_insensitive(self):
        self._adwin_proc.start()
        self._adwin_proc.set_par('Foo', 100)
        self._adwin_proc.set_par('BAR', 10)
        self._adwin_proc.set_par('baz', 2.0)
        self._adwin_proc.set_par('eLeM_BoO', 8)

        self._adwin_mock.set_par.assert_has_calls([unittest.mock.call(1, 100), unittest.mock.call(2, 10)])
        self._adwin_mock.set_fpar.assert_has_calls([unittest.mock.call(5, 2.0)])
        self._adwin_mock.set_data.assert_has_calls([unittest.mock.call(10, 1., np.array([8]))])

    def test_set_par_fail_if_set_float_for_int_par(self):
        self._adwin_proc.start()
        with self.assertRaises(TypeError):
            self._adwin_proc.set_par('Foo', 1.0)

    def test_set_par_raise_exception_when_invalid_key(self):
        self._adwin_proc.start()
        with self.assertRaises(ValueError):
            self._adwin_proc.set_par('non_existing_par', 1.0)

    def test_get_par_multiple(self):
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_fpar.side_effect = [1.0]
        self._adwin_mock.get_data.side_effect = [np.array([1000])]

        self._adwin_proc.start()
        params = self._adwin_proc.get_par_multiple(['foo', 'bar', 'baz', 'elem_boo'])

        self.assertDictEqual(params, {'foo': 10, 'bar': 100, 'baz': 1.0, 'elem_boo': 1000})

    def test_get_par_multiple_case_insensitive(self):
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_fpar.side_effect = [1.0]
        self._adwin_mock.get_data.side_effect = [np.array([1000])]

        self._adwin_proc.start()
        params = self._adwin_proc.get_par_multiple(['foo', 'Bar', 'baz', 'elem_BOO'])

        self.assertDictEqual(params, {'foo': 10, 'Bar': 100, 'baz': 1.0, 'elem_BOO': 1000})

    def test_get_par_multiple_case_exception(self):
        """Test that invalid parameter raises ValueError"""
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_par.side_effect = [10, 100]
        self._adwin_mock.get_fpar.side_effect = [1.0]
        self._adwin_mock.get_data.side_effect = [np.array([1000])]

        self._adwin_proc.start()
        with self.assertRaises(ValueError):
            self._adwin_proc.get_par_multiple(['goo'])

    def test_set_par_multiple(self):
        self._adwin_proc.start()
        params = {'foo': 10, 'bar': 100, 'baz': 2.0, 'elem_boo': 8}
        self._adwin_proc.set_par_multiple(params)

        self._adwin_mock.set_par.assert_has_calls([unittest.mock.call(1, 10), unittest.mock.call(2, 100)])
        self._adwin_mock.set_fpar.assert_has_calls([unittest.mock.call(5, 2.0)])
        self._adwin_mock.set_data.assert_has_calls([unittest.mock.call(10, 1., np.array([8]))])

    def test_set_par_multiple_case_insensitive(self):
        self._adwin_proc.start()
        params = {'foo': 10, 'Bar': 100, 'baz': 2.0, 'eLeM_BoO': 8}
        self._adwin_proc.set_par_multiple(params)

        self._adwin_mock.set_par.assert_has_calls([unittest.mock.call(1, 10), unittest.mock.call(2, 100)])
        self._adwin_mock.set_fpar.assert_has_calls([unittest.mock.call(5, 2.0)])
        self._adwin_mock.set_data.assert_has_calls([unittest.mock.call(10, 1., np.array([8]))])

    def test_set_par_multiple_fails_when_float_for_int_par(self):
        self._adwin_proc.start()
        params = {'foo': 1.0}
        with self.assertRaises(TypeError):
            self._adwin_proc.set_par_multiple(params)

    def test_set_par_multiple_invalid_parameter(self):
        self._adwin_proc.start()
        params = {'goo': 1.0}
        with self.assertRaises(ValueError):
            self._adwin_proc.set_par_multiple(params)

    def test_get_data_length(self):
        self._adwin_mock.get_data_length.side_effect = [100]

        self._adwin_proc.start()
        length = self._adwin_proc.get_data_length('boo')

        self.assertEqual(length, 100)

    def test_get_data(self):
        expected_data = np.array([1, 2, 3, 4])
        self._adwin_mock.get_data.side_effect = [expected_data]

        self._adwin_proc.start()
        data = self._adwin_proc.get_data('boo', 1, 4)

        np.testing.assert_array_equal(data, expected_data)

    def test_get_full_data(self):
        expected_data = np.array([1, 2, 3, 4])
        self._adwin_mock.get_full_data.side_effect = [expected_data]

        self._adwin_proc.start()
        data = self._adwin_proc.get_full_data('boo')

        np.testing.assert_array_equal(data, expected_data)

    def test_set_data(self):
        self._adwin_proc.start()
        data = np.array([1, 2, 3, 4])
        self._adwin_proc.set_data('boo', 1, data)

        self._adwin_mock.set_data.assert_has_calls([unittest.mock.call(10, 1, data)])

    def test_get_fifo_filled(self):
        self._adwin_mock.get_fifo_filled.return_value = 10

        self._adwin_proc.start()
        fifo_room = self._adwin_proc.get_fifo_filled('boo')

        self.assertEqual(fifo_room, 10)

    def test_get_fifo_room(self):
        self._adwin_mock.get_fifo_room.return_value = 10

        self._adwin_proc.start()
        fifo_room = self._adwin_proc.get_fifo_room('boo')

        self.assertEqual(fifo_room, 10)

    def test_read_fifo(self):
        expected_fifo = np.array([1, 2, 3, 4])
        self._adwin_mock.read_fifo.return_value = expected_fifo

        self._adwin_proc.start()
        fifo = self._adwin_proc.read_fifo('boo', 4)

        np.testing.assert_array_equal(fifo, expected_fifo)

    def test_write_fifo(self):
        self._adwin_proc.start()
        data = np.array([1, 2, 3, 4])
        self._adwin_proc.write_fifo('boo', data)

        self._adwin_mock.write_fifo.assert_has_calls([unittest.mock.call(10, data)])


class TestAdwinManagerTestCase(unittest.TestCase):

    def setUp(self):
        self._test_data_dir = os.path.join(os.path.dirname(__file__), 'data')
        # adwin library gets the default processor type "T12" and harware type "PII".
        self._adwin_program_library = AdwinProgramLibrary(self._test_data_dir, self._test_data_dir)

        self._adwin_mock = unittest.mock.MagicMock(spec=Adwin_Base)
        self._adwin_mock.is_process_running.return_value = False

    def test_duplicate_auto_load_program_exception(self):
        """See that same process number cannot be used twice to load programs"""
        # Arrange
        expected = "Duplicate auto_load program in process slot number 10 (program_c)"
        auto_load_programs = ["program_a", "program_b", "program_c"]
        # Act & Assert
        with self.assertRaises(ValueError) as exc:
            AdwinManager(self._adwin_mock, self._adwin_program_library, auto_load_programs)

        self.assertEqual(exc.exception.args[0], expected)

    def test_auto_load_unknown_program_exception(self):
        """See that unknown program name raises exception"""
        # Arrange
        expected = "Unknown program 'program_x' in auto_load_programs"
        auto_load_programs = ["program_a", "program_b", "program_x"]
        # Act & Assert
        with self.assertRaises(ValueError) as exc:
            AdwinManager(self._adwin_mock, self._adwin_program_library, auto_load_programs)

        self.assertEqual(exc.exception.args[0], expected)

    def test_get_adwin(self):
        """Test that we get the same adwin object using the `get_adwin` method"""
        # Arrange
        auto_load_programs = ["program_a", "program_b"]
        self._adwin_manager = AdwinManager(self._adwin_mock, self._adwin_program_library, auto_load_programs)

        # Act
        adwin_copy = self._adwin_manager.get_adwin()

        # Assert
        self.assertIs(self._adwin_mock, adwin_copy)

    def test_get_program_library(self):
        """Test that we get the same program library object using the `get_program_library` method"""
        # Arrange
        auto_load_programs = ["program_a", "program_b"]
        self._adwin_manager = AdwinManager(self._adwin_mock, self._adwin_program_library, auto_load_programs)

        # Act
        program_library_copy = self._adwin_manager.get_program_library()

        # Assert
        self.assertIs(self._adwin_program_library, program_library_copy)

    def test_reboot(self):
        """Test that reboot reloads the program libraries"""
        # Arrange
        auto_load_programs = ["program_a", "program_b"]
        self._adwin_manager = AdwinManager(self._adwin_mock, self._adwin_program_library, auto_load_programs)
        program_list_expected = self._adwin_manager.list_programs()

        # Act
        self._adwin_manager.reboot()

        # Assert
        self.assertListEqual(program_list_expected, self._adwin_manager.list_programs())

    def test_get_process(self):
        """Test that we generate an AdwinProcess instance with `get_process` method"""
        # Arrange
        expected_instance_type = AdwinProcess
        auto_load_programs = ["program_a", "program_b"]
        self._adwin_manager = AdwinManager(self._adwin_mock, self._adwin_program_library, auto_load_programs)

        # Act
        adwin_process_copy = self._adwin_manager.get_process("program_a")

        # Assert
        self.assertIsInstance(adwin_process_copy, expected_instance_type)


if __name__ == '__main__':
    unittest.main()
