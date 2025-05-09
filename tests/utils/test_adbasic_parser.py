#! /usr/bin/env python

"""Unit tests for ADbasic parser."""
import logging
import os.path
import tempfile
import argparse
import unittest
from unittest import mock
import io
import contextlib

from qmi.utils.adbasic_parser import (
    ParDesc, FParDesc, ArrayElemDesc, ParseException, SymbolInfo,
    parse_adbasic_program, analyze_parameter_info, run)


TEST_PROGRAM_FILE = "program.bas"
TEST_PROGRAM = r"""' Test program for ADbasic parser.

#Include ADwinPro_All.inc
#Include .\testprog.inc  ' this include file will also be parsed

' Some misc defines
#Define Pi 3.14159
#DEFINE Symbol_name Value

' Define named parameters.
#Define PAR_one Par_1
#Define PAR_float FPar_1

' Define data arrays.
#Define DATA_params Data_10

' Define parameters located in array elements.
#Define PAR_elem_one DATA_params[1]
#Define PAR_elem_three DATA_params[3]

Dim Data_10[5] As Long

Init:

Event:
"""

TEST_PROGRAM_NO_INCLUDES_FILE = "program_noinc.bas"
TEST_PROGRAM_NO_INCLUDES = r"""' Test program for ADbasic parser.

#Include /  ' this missing include file should cause logger warning

' Some misc defines
#DEFINE Symbol_name Value
#Define Pi 3.14159

Init:

Event:
"""

TEST_INCLUDE_FILE = "testprog.inc"
TEST_INCLUDE = r"""' Test include file for ADbasic parser.

#define testsym 31
#Define PAR_TWO PAR_2
#Define DATA_result Data_11
"""


def write_source_files(tempdir):
    with open(os.path.join(tempdir, TEST_PROGRAM_FILE), "w") as outf:
        outf.write(TEST_PROGRAM)
    with open(os.path.join(tempdir, TEST_INCLUDE_FILE), "w") as outf:
        outf.write(TEST_INCLUDE)


def write_source_file(tempdir, fn, content):
    with open(os.path.join(tempdir, fn), "w") as outf:
        outf.write(content)


class TestAdbasicParser(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="qmitest")
        self.tempdir_name = self.tempdir.name

    def tearDown(self):
        self.tempdir.cleanup()

    def test_parse_symbols(self):

        write_source_files(self.tempdir_name)
        filename = os.path.join(self.tempdir_name, TEST_PROGRAM_FILE)
        symbols = parse_adbasic_program(filename, self.tempdir_name)

        expect_symbols = [
            (TEST_PROGRAM_FILE, 7, "Pi", "3.14159"),
            (TEST_PROGRAM_FILE, 8, "Symbol_name", "Value"),
            (TEST_PROGRAM_FILE, None, "PAR_one", "Par_1"),
            (TEST_PROGRAM_FILE, None, "PAR_float", "FPar_1"),
            (TEST_PROGRAM_FILE, None, "DATA_params", "Data_10"),
            (TEST_PROGRAM_FILE, None, "PAR_elem_one", "DATA_params[1]"),
            (TEST_PROGRAM_FILE, None, "PAR_elem_three", "DATA_params[3]"),
            (TEST_INCLUDE_FILE, 3, "testsym", "31"),
            (TEST_INCLUDE_FILE, None, "PAR_TWO", "PAR_2"),
            (TEST_INCLUDE_FILE, None, "DATA_result", "Data_11")
        ]

        self.assertEqual(len(symbols), len(expect_symbols))

        for (symbol, expect) in zip(symbols, expect_symbols):
            file_path = symbol.filename.replace("\\", "/").replace("/./", "/")
            expect_dir = self.tempdir_name.replace("\\", "/") + "/"
            self.assertEqual(file_path, expect_dir + expect[0])
            if expect[1] is not None:
                self.assertEqual(symbol.line_nr, expect[1])

            self.assertEqual(symbol.label, expect[2])
            self.assertEqual(symbol.value, expect[3])

    def test_parse_symbols_no_dots(self):
        """Test the path is returned into a subfolder if no dots present."""
        global TEST_PROGRAM
        TEST_PROGRAM = TEST_PROGRAM.replace(".\\", "subfolder\\")
        write_source_files(self.tempdir_name)
        subdir = os.path.join(self.tempdir_name, "subfolder")
        os.mkdir(subdir)
        write_source_file(subdir, TEST_INCLUDE_FILE, TEST_INCLUDE)
        filename = os.path.join(self.tempdir_name, TEST_PROGRAM_FILE)
        symbols = parse_adbasic_program(filename, self.tempdir_name)

        expect_symbols = [
            (TEST_PROGRAM_FILE, 7, "Pi", "3.14159"),
            (TEST_PROGRAM_FILE, 8, "Symbol_name", "Value"),
            (TEST_PROGRAM_FILE, None, "PAR_one", "Par_1"),
            (TEST_PROGRAM_FILE, None, "PAR_float", "FPar_1"),
            (TEST_PROGRAM_FILE, None, "DATA_params", "Data_10"),
            (TEST_PROGRAM_FILE, None, "PAR_elem_one", "DATA_params[1]"),
            (TEST_PROGRAM_FILE, None, "PAR_elem_three", "DATA_params[3]"),
            ("subfolder/" + TEST_INCLUDE_FILE, 3, "testsym", "31"),
            ("subfolder/" + TEST_INCLUDE_FILE, None, "PAR_TWO", "PAR_2"),
            ("subfolder/" + TEST_INCLUDE_FILE, None, "DATA_result", "Data_11")
        ]
        self.assertEqual(len(symbols), len(expect_symbols))

        for (symbol, expect) in zip(symbols, expect_symbols):
            file_path = symbol.filename.replace("\\", "/").replace("/./", "/")
            expect_dir = self.tempdir_name.replace("\\", "/") + "/"
            self.assertEqual(file_path, expect_dir + expect[0])
            if expect[1] is not None:
                self.assertEqual(symbol.line_nr, expect[1])

            self.assertEqual(symbol.label, expect[2])
            self.assertEqual(symbol.value, expect[3])

    def test_param_info(self):
        # Arrange
        expect_params = [
            ("one", ParDesc, {"par_index": 1}),
            ("TWO", ParDesc, {"par_index": 2}),
            ("float", FParDesc, {"fpar_index": 1}),
            ("elem_one", ArrayElemDesc, {"data_index": 10, "elem_index": 1}),
            ("elem_three", ArrayElemDesc, {"data_index": 10, "elem_index": 3})
        ]

        expect_data = [
            ("params", 10),
            ("result", 11)
        ]
        write_source_files(self.tempdir_name)
        filename = os.path.join(self.tempdir_name, TEST_PROGRAM_FILE)
        symbols = parse_adbasic_program(filename, self.tempdir_name)

        # Act
        param_info = analyze_parameter_info(symbols)

        # Assert
        self.assertEqual(str(param_info.param["one"]), "Par_1")
        self.assertEqual(str(param_info.param["float"]), "FPar_1")
        self.assertEqual(str(param_info.param["elem_one"]), "Data_10[1]")
        self.assertEqual(len(param_info.param), len(expect_params))
        for (name, cls, args) in expect_params:
            desc = param_info.param[name]
            self.assertIsInstance(desc, cls)
            for (arg_name, arg_val) in args.items():
                self.assertEqual(getattr(desc, arg_name), arg_val)

        self.assertEqual(len(param_info.data), len(expect_data))
        for (name, index) in expect_data:
            self.assertEqual(param_info.data[name], index)

    def test_wrong_symbol_definition_format(self):
        """Test wrong symbol definition format"""

        logging.getLogger("qmi.utils.adbasic_parser").setLevel(logging.CRITICAL)
        wrong_symbol_info = SymbolInfo(
            filename="program.bas",
            line_nr=1,
            label="DATA_params",
            value="Date_10"
        )
        param_info = analyze_parameter_info([wrong_symbol_info])
        self.assertEqual(0, len(param_info.param))
        self.assertEqual(0, len(param_info.data))

    def test_duplicate_case(self):
        """Test duplicate definition of this symbol with different case"""
        expected_exc = "program.bas, line 2: Duplicate definition of symbol DATA_Params with different case"
        wrong_symbol_info = [SymbolInfo(
            filename="program.bas",
            line_nr=1,
            label="DATA_params",
            value="Data_10"
            ),
            SymbolInfo(
                filename="program.bas",
                line_nr=2,
                label="DATA_Params",
                value="Data_10"
            )
        ]
        with self.assertRaises(ParseException) as exc:
            analyze_parameter_info(wrong_symbol_info)

        self.assertEqual(str(exc.exception), expected_exc)

    def test_duplicate_index(self):
        """Test duplicate definition of this symbol with different index"""
        expected_exc = "program.bas, line 1: Duplicate definition of symbol DATA_params for different data array"
        wrong_symbol_info = [SymbolInfo(
            filename="program.bas",
            line_nr=1,
            label="DATA_params",
            value="Data_10"
            ),
            SymbolInfo(
                filename="program.bas",
                line_nr=1,
                label="DATA_params",
                value="Data_9"
            )
        ]
        with self.assertRaises(ParseException) as exc:
            analyze_parameter_info(wrong_symbol_info)

        self.assertEqual(str(exc.exception), expected_exc)

    def test_duplicate_use(self):
        """Test duplicate use of the same Data_nnn array under different names"""
        expected_exc = "program.bas, line 1: Symbol DATA_rapams is a duplicate reference to Data_10"
        wrong_symbol_info = [SymbolInfo(
            filename="program.bas",
            line_nr=1,
            label="DATA_params",
            value="Data_10"
            ),
            SymbolInfo(
                filename="program.bas",
                line_nr=1,
                label="DATA_rapams",
                value="Data_10"
            )
        ]
        with self.assertRaises(ParseException) as exc:
            analyze_parameter_info(wrong_symbol_info)

        self.assertEqual(str(exc.exception), expected_exc)


class TestParseException(unittest.TestCase):

    def test_init(self):
        """Test that __init__ works"""
        # Arrange
        filename = "foo.bar"
        line_nr = 42
        message = "barfood"
        expected_string = "{}, line {}: {}".format(filename, line_nr, message)

        # Act
        parse_exception_instance = ParseException(filename, line_nr, message)

        # Assert
        self.assertEqual(str(parse_exception_instance), expected_string)


class TestParseAdbasicProgram(unittest.TestCase):

    def test_parse_adbasic_program_empty_filename_raises_exception(self):
        """See that exception is raised with empty file name"""
        with self.assertRaises(FileNotFoundError):
            parse_adbasic_program("", "")
            

class TestMain(unittest.TestCase):

    def setUp(self) -> None:
        global TEST_PROGRAM
        # Change back
        TEST_PROGRAM = TEST_PROGRAM.replace("subfolder\\", ".\\")
        self.tempdir = tempfile.TemporaryDirectory(prefix="qmitest")
        write_source_files(self.tempdir.name)
        self.filename = os.path.join(self.tempdir.name, TEST_PROGRAM_FILE)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_run(self):
        """Test that the run function parses the input files correctly and the print statement prints symbols of type
        symbol_name only (so, not symbols without '_')."""
        # Arrange
        expected = [
        "PAR_{:32} = Par_1".format("one"),
        "PAR_{:32} = Par_2".format("TWO"),
        "PAR_{:32} = FPar_1".format("float"),
        "PAR_{:32} = Data_10[1]".format("elem_one"),
        "PAR_{:32} = Data_10[3]".format("elem_three"),
        "DATA_{:32} = Data_10".format("params"),
        "DATA_{:32} = Data_11".format("result"),
        ""
        ]
        with mock.patch("argparse.ArgumentParser.parse_args", return_value=argparse.Namespace(filename=self.filename)):
            # Act
            with io.StringIO() as buf:
                with contextlib.redirect_stdout(buf):
                    run()

                stdout_result = buf.getvalue()

        # Assert
        self.assertListEqual(stdout_result.split("\n"), expected)


class TestNoIncludeFilesMain(unittest.TestCase):

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="qmitest")
        write_source_file(self.tempdir.name, TEST_PROGRAM_NO_INCLUDES_FILE, TEST_PROGRAM_NO_INCLUDES)
        self.filename = os.path.join(self.tempdir.name, TEST_PROGRAM_NO_INCLUDES_FILE)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_run(self):
        """Test that no include file creates a logger warning"""
        # Arrange
        with mock.patch("argparse.ArgumentParser.parse_args", return_value=argparse.Namespace(filename=self.filename)):
            with mock.patch("logging.Logger.warning") as warn:
                # Act
                run()
                # Assert
                warn.assert_called_once_with("Absolute include path not supported: %r", r"/")


if __name__ == "__main__":
    unittest.main()
