#! /usr/bin/env python

"""Unit tests for ADbasic compiler."""

import sys
import contextlib
import io
import logging
import subprocess
from collections import namedtuple
from typing import cast
import argparse
import fnmatch
import unittest
from unittest import mock

import qmi
# We want to import the actual CONSTANT executable lines, dependent on OS, from the module under test
with mock.patch("sys.platform", "linux1"):
    from qmi.utils.adbasic_compiler import ADBASIC_COMPILER_EXECUTABLE as LINUX_EXECUTABLE
    from qmi.utils.adbasic_compiler import LINUX_LIBRARY_DIR, LINUX_INCLUDE_DIR

del sys.modules["qmi.utils.adbasic_compiler"]  # Need to delete this in between, otherwise it won't "reload"
with mock.patch("sys.platform", "win32"):
    from qmi.utils.adbasic_compiler import ADBASIC_COMPILER_EXECUTABLE as WINDOWS_EXECUTABLE

from qmi.utils.adbasic_compiler import (
    AdbasicResult, AdbasicCompilerException, check_compiler_result, run_adbasic_compiler, print_adbasic_compiler_help,
    compile_program, run
    )


class TestRunAdBasicCompiler(unittest.TestCase):

    def setUp(self) -> None:
        self.adwin_dir = {"linux1": "/path/to/adwin", "win32": r"C:\path\to\adwin"}

    def tearDown(self):
        logging.getLogger("qmi.utils.adbasic_compiler").setLevel(logging.NOTSET)

    def test_run_adbasic_compiler(self):
        """Test that adbasic compiler works on linux and windows"""
        # Arrange
        excpected_returncode = 0
        # run_adbasic_compiler arguments
        exec_dir = {"linux1": "/bin/adbasic", "win32": r"\ADbasic\ADbasic_C.exe"}
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        working_dir = None
        parse_stderr = True
        remove_c_directory = False
        pretty_print = False

        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=excpected_returncode,
                         stdout=b"some stdout line\n", stderr=b"")

        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = LINUX_EXECUTABLE
            full_dir = self.adwin_dir[sys.platform] + exec_dir[sys.platform]
            expected_command_line_linux = full_dir + " " + " ".join(map(str, adbasic_arguments))
            adbasic_result_linux = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12.1", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = WINDOWS_EXECUTABLE
            full_dir = self.adwin_dir[sys.platform] + exec_dir[sys.platform]
            expected_command_line_win = full_dir + " " + " ".join(map(str, adbasic_arguments))
            adbasic_result_win = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12.1", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

        # Assert
        self.assertEqual(adbasic_result_linux.command_line, expected_command_line_linux)
        self.assertEqual(adbasic_result_linux.returncode, excpected_returncode)
        self.assertEqual(adbasic_result_win.command_line, expected_command_line_win)
        self.assertEqual(adbasic_result_win.returncode, excpected_returncode)

    def test_run_adbasic_compiler_returns_error_and_warning(self):
        """Test that adbasic compiler returns errors and warnings correctly"""
        # Suppress logging.
        logging.getLogger("qmi.utils.adbasic_compiler").setLevel(logging.CRITICAL)

        # Arrange
        expected_returncode = 99
        f = "bad_input.bas"
        inv_opt = "-explode"
        exp_descriptions = ["Small error", "Another error", "Invalid command line option: {}".format(inv_opt),
                            "Compilation aborted !"]
        exp_lines = ["2", "", "", ""]
        exp_numbers = [1, 1, 0, 0]
        exp_line_numbers = [3, 0, 0, 0]
        exp_filenames = [f, f, "", ""]
        error1 = "Error: No: {} {} line: {} file: {} line no.: {} ".format(1, exp_descriptions[0], 2, f, 3)
        error2 = "Error: No: {} {} file: {} ".format(1, exp_descriptions[1], f)
        error3 = "Invalid Option: {}".format(inv_opt)
        error4 = "Compilation aborted !"
        warning1 = "{} error.s., {} warning.s.".format(4, 0)
        warning2 = "002b:fixme:ver:SomeCommandToFix (0x33f1d0 (nil)): stub\n"
        stderr_string = "\r\n".join([error1, error2, error3, error4, warning1, warning2])
        # run_adbasic_compiler arguments
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        working_dir = None
        parse_stderr = True
        remove_c_directory = False
        pretty_print = False

        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=expected_returncode,
                         stdout=b"some stdout line\n", stderr=bytes(stderr_string, encoding="ASCII"))

        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            adbasic_result_linux = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            adbasic_result_win = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

        # Assert
        for e, error in enumerate(adbasic_result_linux.errors):
            self.assertEqual(error.error_description, exp_descriptions[e])
            self.assertEqual(error.error_line, exp_lines[e])
            self.assertEqual(error.error_number, exp_numbers[e])
            self.assertEqual(error.filename, exp_filenames[e])
            self.assertEqual(error.line_number, exp_line_numbers[e])

        for e, error in enumerate(adbasic_result_win.errors):
            self.assertEqual(error.error_description, exp_descriptions[e])
            self.assertEqual(error.error_line, exp_lines[e])
            self.assertEqual(error.error_number, exp_numbers[e])
            self.assertEqual(error.filename, exp_filenames[e])
            self.assertEqual(error.line_number, exp_line_numbers[e])

    def test_run_adbasic_compiler_returns_success_on_warnings(self):
        """Test that adbasic compiler returns errors and warnings correctly"""
        # Suppress logging.
        logging.getLogger("qmi.utils.adbasic_compiler").setLevel(logging.CRITICAL)

        # Arrange
        expected_returncode = 0
        warning1 = "{} error.s., {} warning.s.".format(4, 0)
        warning2 = "002b:fixme:ver:SomeCommandToFix (0x33f1d0 (nil)): stub\n"
        stderr_string = "\r\n".join([warning1, warning2])
        # run_adbasic_compiler arguments
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        working_dir = None
        parse_stderr = True
        remove_c_directory = False
        pretty_print = False

        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=expected_returncode,
                         stdout=b"some stdout line\n", stderr=bytes(stderr_string, encoding="ASCII"))

        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            adbasic_result_linux = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            adbasic_result_win = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )
            
        # Assert
        self.assertTrue(adbasic_result_linux.success)
        self.assertTrue(adbasic_result_win.success)

    def test_run_adbasic_compiler_returns_failure_on_errors(self):
        """Test that adbasic compiler returns errors and warnings correctly"""
        # Suppress logging.
        logging.getLogger("qmi.utils.adbasic_compiler").setLevel(logging.CRITICAL)

        # Arrange
        expected_returncode = 0
        f = "bad_input.bas"
        inv_opt = "-explode"
        exp_descriptions = ["Small error", "Another error", "Invalid command line option: {}".format(inv_opt),
                            "Compilation aborted !"]
        error1 = "Error: No: {} {} line: {} file: {} line no.: {} ".format(1, exp_descriptions[0], 2, f, 3)
        error2 = "Error: No: {} {} file: {} ".format(1, exp_descriptions[1], f)
        error3 = "Invalid Option: {}".format(inv_opt)
        error4 = "Compilation aborted !"
        stderr_string = "\r\n".join([error1, error2, error3, error4])
        # run_adbasic_compiler arguments
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        working_dir = None
        parse_stderr = True
        remove_c_directory = False
        pretty_print = False

        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=expected_returncode,
                         stdout=b"some stdout line\n", stderr=bytes(stderr_string, encoding="ASCII"))

        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            adbasic_result_linux = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            adbasic_result_win = run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )
            
        # Assert
        self.assertFalse(adbasic_result_linux.success)
        self.assertFalse(adbasic_result_win.success)

    def test_run_adbasic_compiler_does_not_raise_FileNotFoundError(self):
        """Test that adbasic compiler works passes FileNotFoundError on fictive C directory removal"""
        # Arrange
        excpected_returncode = 0
        # run_adbasic_compiler arguments
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        working_dir = "non-existent"
        parse_stderr = True
        remove_c_directory = True
        pretty_print = False

        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=excpected_returncode,
                         stdout=b"some stdout line\n", stderr=b"")

        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            run_adbasic_compiler(
                self.adwin_dir[sys.platform], "T12", adbasic_arguments, working_dir, parse_stderr, remove_c_directory,
                pretty_print
                )

    def test_run_adbasic_compiler_raises_AdbasicCompilerException(self):
        """Test that adbasic compiler works raises AdbasicCompilerException on errative stderr lines"""
        # Arrange
        expected_returncode = 99
        error1 = "Liirum laarum pimpeli pompeli"  # nonsense
        warning1 = "{} warning.s., {} error.s.".format(4, 0)  # wrong order
        warning2 = "002b:todo:ver:SomeCommandToFix (0x33f1d0 (nil)): stub\n"  # 'todo' instead of 'fixme'
        tests = [error1, warning1, warning2]
        for test_string in tests:
            stderr_string = f"{test_string}\r\n".encode("ASCII")
            # run_adbasic_compiler arguments
            adbasic_arguments = ["ls", "-l", "/dev/null"]
            working_dir = None
            parse_stderr = True
            remove_c_directory = False
            pretty_print = False

            run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=expected_returncode,
                             stdout=b"some stdout line\n", stderr=bytes(stderr_string))

            # Act
            with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
                # Assert
                with self.assertRaises(AdbasicCompilerException):
                    run_adbasic_compiler(
                        self.adwin_dir[sys.platform], "T11", adbasic_arguments, working_dir, parse_stderr,
                        remove_c_directory, pretty_print
                        )

            with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
                # Assert
                with self.assertRaises(AdbasicCompilerException):
                    run_adbasic_compiler(
                        self.adwin_dir[sys.platform], "T11", adbasic_arguments, working_dir, parse_stderr,
                        remove_c_directory, pretty_print
                        )

    def test_print_adbasic_compiler_help_T11(self):
        """Test that print_adbasic_compiler_help() works on linux and windows"""
        # Arrange
        adbasic_arguments = ["/P11", "/H"]
        help_test = "adbasic compiler help text\n"
        expected_stdout = mock.call("\x1b[32m(stdout)\x1b[0m", help_test)
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=bytes(help_test.encode()), stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            with mock.patch("builtins.print") as print_patch:
                print_adbasic_compiler_help(self.adwin_dir[sys.platform], "T11")

            print_patch.assert_has_calls([expected_stdout])

    def test_print_adbasic_compiler_help_T12(self):
        """Test that print_adbasic_compiler_help() works on linux and windows"""
        # Arrange
        adbasic_arguments = ["/P12", "/H"]
        help_test = "adbasic compiler help text\n"
        expected_stdout = mock.call("\x1b[32m(stdout)\x1b[0m", help_test)
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=bytes(help_test.encode()), stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            with mock.patch("builtins.print") as print_patch:
                print_adbasic_compiler_help(self.adwin_dir[sys.platform], "T12")

            print_patch.assert_has_calls([expected_stdout])

    def test_print_adbasic_compiler_help_T121(self):
        """Test that print_adbasic_compiler_help() works on linux and windows"""
        # Arrange
        adbasic_arguments = ["/P121", "/H"]
        help_test = "adbasic compiler help text\n"
        expected_stdout = mock.call("\x1b[32m(stdout)\x1b[0m", help_test)
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=bytes(help_test.encode()), stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            with mock.patch("builtins.print") as print_patch:
                print_adbasic_compiler_help(self.adwin_dir[sys.platform], "T12.1")

            print_patch.assert_has_calls([expected_stdout])


class TestCompileProgram(unittest.TestCase):

    def test_compile_program_T12(self):
        """Test compile_program() function"""
        basic_filename = "program.bas"
        trigger = "external"  # external or timer
        process_number = 2  # 1-10
        processor_type = "T12"
        hardware_type = "PII"
        priority = 0  # -10-10 or PRIO_HIGH
        working_dir = None
        keep_c_files = False
        default_adwindir = {"linux1": "/opt/adwin", "win32": r"C:\ADwin"}
        pretty_print = False

        exec_dir = {"linux1": "/bin/adbasic", "win32": r"\ADbasic\ADbasic_C.exe"}
        adbasic_arguments = ["/P12", "/H"]
        help_test = "adbasic compiler help text\n"
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=bytes(help_test.encode()), stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = LINUX_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            inc_dir = default_adwindir[sys.platform] + "/" + LINUX_INCLUDE_DIR
            lib_dir = default_adwindir[sys.platform] + "/" + LINUX_LIBRARY_DIR
            expected_command_line_linux = "{} /M /P12 /SPII /EE /PN2 /PL0 /O2 /IP{} /LP{} {}".format(
                full_dir, inc_dir, lib_dir, basic_filename
                )
            adbasic_result_linux = compile_program(
                basic_filename,
                trigger,
                process_number,
                processor_type,
                hardware_type,
                priority,
                working_dir,
                keep_c_files,
                default_adwindir[sys.platform],
                pretty_print
            )

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = WINDOWS_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            expected_command_line_win = "{} /M /P12 /SPII /EE /PN2 /PL0 /O2 {}".format(full_dir, basic_filename)
            adbasic_result_win = compile_program(
                basic_filename,
                trigger,
                process_number,
                processor_type,
                hardware_type,
                priority,
                working_dir,
                keep_c_files,
                default_adwindir[sys.platform],
                pretty_print
            )

        # Assert
        self.assertEqual(adbasic_result_linux.command_line, expected_command_line_linux)
        self.assertEqual(adbasic_result_win.command_line, expected_command_line_win)

    def test_compile_program_T11(self):
        """Test compile_program() function"""
        basic_filename = "program.bas"
        trigger = "external"  # external or timer
        process_number = 2  # 1-10
        processor_type = "T11"
        hardware_type = "GII"
        priority = 0  # -10-10 or PRIO_HIGH
        working_dir = None
        keep_c_files = False
        default_adwindir = {"linux1": "/opt/adwin", "win32": r"C:\ADwin"}
        pretty_print = False

        exec_dir = {"linux1": "/bin/adbasic", "win32": r"\ADbasic\ADbasicCompiler.exe"}
        adbasic_arguments = ["/P11", "/H"]
        help_test = "adbasic compiler help text\n"
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=bytes(help_test.encode()), stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = LINUX_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            inc_dir = default_adwindir[sys.platform] + "/" + LINUX_INCLUDE_DIR
            lib_dir = default_adwindir[sys.platform] + "/" + LINUX_LIBRARY_DIR
            expected_command_line_linux = "{} /M /P11 /SGII /EE /PN2 /PL0 /O2 /IP{} /LP{} {}".format(
                full_dir, inc_dir, lib_dir, basic_filename
                )
            adbasic_result_linux = compile_program(
                basic_filename,
                trigger,
                process_number,
                processor_type,
                hardware_type,
                priority,
                working_dir,
                keep_c_files,
                default_adwindir[sys.platform],
                pretty_print
            )

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = WINDOWS_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            expected_command_line_win = "{} /M /P11 /SGII /EE /PN2 /PL0 /O2 {}".format(full_dir, basic_filename)
            adbasic_result_win = compile_program(
                basic_filename,
                trigger,
                process_number,
                processor_type,
                hardware_type,
                priority,
                working_dir,
                keep_c_files,
                default_adwindir[sys.platform],
                pretty_print
            )

        # Assert
        self.assertEqual(adbasic_result_linux.command_line, expected_command_line_linux)
        self.assertEqual(adbasic_result_win.command_line, expected_command_line_win)


class TestCheckCompilerResult(unittest.TestCase):
    
    def test_check_compiler_result(self):
        # Arrange
        error, to_compile = "An error", "bla"
        expected = ["ADbasic compiler reported error when compiling '{}' (exit status 1)".format(to_compile),
                    ["{}".format(error)]]
        expected2 = "ADbasic compiler reported error when compiling '{}' (exit status 1)\n".format(to_compile) +\
                    "  {}".format(error)
        ResultStruct = namedtuple("ResultStruct", "success returncode errors")
        result = ResultStruct(success=False, returncode=1, errors=[error])
        result = cast(AdbasicResult, result)
        # Act & Assert
        with self.assertRaises(AdbasicCompilerException) as exc:
            check_compiler_result(to_compile, result)

        self.assertEqual(exc.exception.args[0][0], expected[0])
        self.assertEqual(exc.exception.args[0][1], expected[1])
        self.assertEqual(str(exc.exception), expected2)


class TestMain(unittest.TestCase):

    def test_run_T11(self):
        """Test that the argument parsing and running on run() method works both on linux and windows"""
        # Arrange
        default_adwindir = {"linux1": "/opt/adwin", "win32": r"C:\ADwin"}
        exec_dir = {"linux1": "/bin/adbasic", "win32": r"\ADbasic\ADbasicCompiler.exe"}
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=b"some stdout text", stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = LINUX_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            expected_stdout_linux = [
                "(stdout) some stdout text",
                "Executed command line:",
                "{} /P11 /H".format(full_dir),
                "Execution time: 0.00? seconds.",  # ? is wildcard
                "Performing exit(0), bye!",
                ""
                ]
            with mock.patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                adwin_dir=default_adwindir[sys.platform],
                compiler_help="no help",
                keep_c_files=True,
                library=False,
                trigger="external",
                process_number=1,
                processor_type="T11",
                filename="bla.bas"
            )):
                with io.StringIO() as buf:
                    with contextlib.redirect_stdout(buf):
                        run()

                    linux_prints = buf.getvalue()

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = WINDOWS_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            expected_stdout_win = [
                "(stdout) some stdout text",
                "Executed command line:",
                "{} /P11 /H".format(full_dir),
                "Execution time: 0.00? seconds.",  # ? is wildcard
                "Performing exit(0), bye!",
                ""
                ]
            with mock.patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                adwin_dir=default_adwindir[sys.platform],
                compiler_help="no help",
                keep_c_files=True,
                library=False,
                trigger="external",
                process_number=1,
                processor_type="T11",
                filename="bla.bas"
            )):
                with io.StringIO() as buf:
                    with contextlib.redirect_stdout(buf):
                        run()

                    win_prints = buf.getvalue()

        # Test differently as sometimes there's a delay in execution and it might take some milliseconds
        for e, prt in enumerate(linux_prints.split("\n\n")):
            self.assertTrue(fnmatch.fnmatch(prt.strip(), expected_stdout_linux[e]))
        for e, prt in enumerate(win_prints.split("\n\n")):
            self.assertTrue(fnmatch.fnmatch(prt.strip(), expected_stdout_win[e]))

    def test_run_T12(self):
        """Test that the argument parsing and running on run() method works both on linux and windows"""
        # Arrange
        default_adwindir = {"linux1": "/opt/adwin", "win32": r"C:\ADwin"}
        exec_dir = {"linux1": "/bin/adbasic", "win32": r"\ADbasic\ADbasic_C.exe"}
        adbasic_arguments = ["ls", "-l", "/dev/null"]
        run_return = subprocess.CompletedProcess(args=adbasic_arguments, returncode=0,
                         stdout=b"some stdout text", stderr=b"")
        # Act
        with mock.patch("sys.platform", "linux1"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = LINUX_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            expected_stdout_linux = [
                "(stdout) some stdout text",
                "Executed command line:",
                "{} /P12 /H".format(full_dir),
                "Execution time: 0.00? seconds.",  # ? is wildcard
                "Performing exit(0), bye!",
                ""
                ]
            with mock.patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                adwin_dir=default_adwindir[sys.platform],
                compiler_help="no help",
                keep_c_files=True,
                library=False,
                trigger="external",
                process_number=1,
                processor_type="T12",
                filename="bla.bas"
            )):
                with io.StringIO() as buf:
                    with contextlib.redirect_stdout(buf):
                        run()

                    linux_prints = buf.getvalue()

        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run", return_value=run_return):
            qmi.utils.adbasic_compiler.ADBASIC_COMPILER_EXECUTABLE = WINDOWS_EXECUTABLE
            full_dir = default_adwindir[sys.platform] + exec_dir[sys.platform]
            expected_stdout_win = [
                "(stdout) some stdout text",
                "Executed command line:",
                "{} /P12 /H".format(full_dir),
                "Execution time: 0.00? seconds.",  # ? is wildcard
                "Performing exit(0), bye!",
                ""
                ]
            with mock.patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(
                adwin_dir=default_adwindir[sys.platform],
                compiler_help="no help",
                keep_c_files=True,
                library=False,
                trigger="external",
                process_number=1,
                processor_type="T12",
                filename="bla.bas"
            )):
                with io.StringIO() as buf:
                    with contextlib.redirect_stdout(buf):
                        run()

                    win_prints = buf.getvalue()

        # Test differently as sometimes there's a delay in execution and it might take some milliseconds
        for e, prt in enumerate(linux_prints.split("\n\n")):
            self.assertTrue(fnmatch.fnmatch(prt.strip(), expected_stdout_linux[e]))
        for e, prt in enumerate(win_prints.split("\n\n")):
            self.assertTrue(fnmatch.fnmatch(prt.strip(), expected_stdout_win[e]))


if __name__ == "__main__":
    unittest.main()
