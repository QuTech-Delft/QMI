"""Driver for the adbasic command line script.

It is recommended to use this script instead of directly invoking /opt/adwin/bin/adbasic.
It provides much nicer formatting of compiler errors, a working exit code, and help.
"""

import argparse
import logging
import os
from pathlib import Path
import re
import sys
import shutil
import subprocess
import time
from typing import NamedTuple

import colorama

from qmi.core.exceptions import QMI_RuntimeException


# Value used to mark high process priority.
PRIO_HIGH = 1000

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

LINUX_INCLUDE_DIR = "share/adbasic/Inc"
LINUX_LIBRARY_DIR = "share/adbasic/Lib"
# Determine default ADwin software location based on OS.
if "linux" in sys.platform or "darwin" in sys.platform:
    DEFAULT_ADWINDIR = "/opt/adwin"
    ADBASIC_COMPILER_EXECUTABLE = {"T11": "bin/adbasic", "T12": "bin/adbasic", "T12.1": "bin/adbasic"}

else:
    DEFAULT_ADWINDIR = "C:\\ADwin"
    ADBASIC_COMPILER_EXECUTABLE = {
        "T11": "ADbasic\\ADbasicCompiler.exe",
        "T12": "ADbasic\\ADbasic_C.exe",
        "T12.1": "ADbasic\\ADbasic_C.exe"
    }


class AdbasicError(NamedTuple):
    """Information from one error message from the ADbasic compiler."""
    error_number: int
    error_description: str
    error_line: str
    filename: str
    line_number: int

    def __str__(self) -> str:
        msg = ""
        if self.filename:
            msg += "[" + self.filename
            if self.line_number:
                msg += f":{self.line_number}"
            msg += "] "
        if self.error_number:
            msg += f"Error {self.error_number}: "
        msg += self.error_description
        if self.error_line:
            msg += f" ({self.error_line.strip()!r})"
        return msg


class AdbasicResult(NamedTuple):
    """Information from a run of the ADbasic compiler."""
    command_line: str
    duration: float
    returncode: int
    success: bool
    errors: list[AdbasicError]
    warnings: list[AdbasicError]


class AdbasicCompilerException(QMI_RuntimeException):
    """Raised when an error occurs while compiling ADbasic code."""

    def __init__(self, message: str, errors: list[AdbasicError]) -> None:
        super().__init__([message, errors])
        self.adbasic_errors = errors
        self.message = message

    def __str__(self) -> str:
        error_message = self.message
        for error in self.adbasic_errors:
            error_message += "\n  " + str(error)
        return error_message
    
    def __reduce__(self):
        return (AdbasicCompilerException, (self.message, self.adbasic_errors))


def _extract_lines(lines_bin: bytes) -> list[str]:
    """Extract lines from compiler output stream."""
    lines = lines_bin.decode("ascii", errors='replace').split("\r\n")
    while len(lines) > 0 and lines[-1] in ["", "\n"]:
        lines = lines[:-1]
    return lines


def _parse_stderr_lines(stderr_lines: list[str]) -> tuple[list[AdbasicError], list[AdbasicError]]:
    """Parse stderr output from the compiler."""

    error_line_v1_pattern_string = r"Error: No: ([0-9]+) (.*?) line: (.*?) file: (.*?) line no\.: ([0-9]+) "
    error_line_v1_pattern = re.compile(error_line_v1_pattern_string)

    error_line_v2_pattern_string = r"Error: No: ([0-9]+) (.*?) file: ([^ ]*) "
    error_line_v2_pattern = re.compile(error_line_v2_pattern_string)

    error_invalid_option_pattern_string = r"Invalid Option: ([^ ]+)"
    error_invalid_option_pattern        = re.compile(error_invalid_option_pattern_string)

    compilation_aborted_line_pattern_string = r"Compilation aborted !"
    compilation_aborted_line_pattern = re.compile(compilation_aborted_line_pattern_string)

    error_warning_count_line_pattern_string = r"([0-9]+) error.s., ([0-9]+) warning.s."
    error_warning_count_line_pattern = re.compile(error_warning_count_line_pattern_string)

    fixme_line_pattern_string = r"([0-9a-fA-F]+):fixme:([:a-zA-Z]+) .+"
    fixme_warning_count_line_pattern = re.compile(fixme_line_pattern_string, re.DOTALL)

    errors: list[AdbasicError] = []
    warnings: list[AdbasicError] = []

    for line in stderr_lines:

        # Parse stderr line(s).
        while len(line) != 0:
            match = error_line_v1_pattern.match(line)
            if match:
                (error_number, error_description, error_line, filename, line_number) = match.groups()
                error_number_int = int(error_number)
                line_number_int = int(line_number)
                error = AdbasicError(error_number_int, error_description, error_line, filename, line_number_int)
                errors.append(error)
                line = line[match.end():]
                continue

            match = error_line_v2_pattern.match(line)
            if match:
                (error_number, error_description, filename) = match.groups()
                error_number_int = int(error_number)
                error = AdbasicError(error_number_int, error_description, "", filename, 0)
                errors.append(error)
                line = line[match.end():]
                continue

            match = error_invalid_option_pattern.match(line)
            if match:
                (invalid_option, ) = match.groups()
                error = AdbasicError(0, f"Invalid command line option: {invalid_option}", "", "", 0)
                errors.append(error)
                line = line[match.end():]
                continue

            match = compilation_aborted_line_pattern.match(line)
            if match:
                error_description = match.group(0)
                error = AdbasicError(0, error_description, "", "", 0)
                errors.append(error)
                line = line[match.end():]
                continue

            match = error_warning_count_line_pattern.match(line)
            if match:
                error_count = int(match.group(1))
                warning_count = int(match.group(2))
                if (error_count > 0) or (warning_count > 0):
                    error = AdbasicError(0, match.group(0), "", "", 0)
                    warnings.append(error)
                line = line[match.end():]
                continue

            match = fixme_warning_count_line_pattern.match(line)
            if match:
                warning_count = int("0x" + match.group(1), 16)
                if warning_count > 0:
                    error = AdbasicError(0, match.group(0), "", "", 0)
                    warnings.append(error)
                line = line[match.end():]
                continue

            raise AdbasicCompilerException(f"Unrecognized ADbasic error string: {line!r}", [])

    return errors, warnings


def _library_path_arguments(adwin_dir: str) -> list[str]:
    """Return ADbasic command-line arguments to specify the include path and library path."""

    # The Linux version of the compiler needs an explicit path to the standard library.
    if "linux" in sys.platform or "darwin" in sys.platform:
        include_file_path = Path(adwin_dir, LINUX_INCLUDE_DIR)
        library_file_path = Path(adwin_dir, LINUX_LIBRARY_DIR)
        include_path_argument = "/IP" + include_file_path.as_posix()
        library_path_argument = "/LP" + library_file_path.as_posix()
        return [include_path_argument, library_path_argument]
    else:
        return []


def run_adbasic_compiler(
    adwin_dir: str,
    processor_type: str,
    adbasic_arguments: list[str],
    working_dir: str | None = None,
    parse_stderr: bool = True,
    remove_c_directory: bool = False,
    pretty_print: bool = False
) -> AdbasicResult:
    """Run the ADbasic compiler.

    Parameters:
        adwin_dir:          Base directory of ADwin software installation (e.g. /opt/adwin).
        processor_type:     The type of processor the command is run for.
        adbasic_arguments:  List of command-line options for the ADbasic compiler.
        working_dir:        Working directory when running the compiler.
        parse_stderr:       True to parse error messages from the ADbasic compiler and return them.
                            False to ignore error messages from the compiler.
        remove_c_directory: True to remove the directory with intermediate C files from the compiler.
        pretty_print:       True to print compiler messages in pretty colors.
                            False to log messages via the Python log system.

    Returns:
        AdbasicResult: Tuple containing results from the compilation process.
                       If `parse_stderr` is True, this result will contain parsed compiler error messages.

    Raises:
        AdbasicCompilerException: If an unexpected error occurs while interacting with the ADbasic compiler.
    """
    # Determine compiler command
    compiler_command = ADBASIC_COMPILER_EXECUTABLE[processor_type]
    # Determine path to ADbasic compiler.
    adbasic_executable_p = Path(adwin_dir, compiler_command)
    if "linux" in sys.platform or "darwin" in sys.platform:
        adbasic_executable = adbasic_executable_p.as_posix()

    else:
        adbasic_executable = str(adbasic_executable_p).replace("/", "\\")

    run_args = [adbasic_executable] + adbasic_arguments
    _logger.debug("Running %s", " ".join(f"{arg!r}" for arg in run_args))

    command_line = " ".join(run_args)

    t1 = time.monotonic()

    # pylint: disable=subprocess-run-check
    completed_process = subprocess.run(args=run_args, capture_output=True, cwd=working_dir)

    t2 = time.monotonic()
    duration = (t2 - t1)

    if remove_c_directory:
        if working_dir:
            temp_c_dir = os.path.join(working_dir, "c")
        else:
            temp_c_dir = "c"
        try:
            shutil.rmtree(temp_c_dir)
        except FileNotFoundError:
            pass

    stdout_lines = _extract_lines(completed_process.stdout)
    stderr_lines = _extract_lines(completed_process.stderr)

    for line in stdout_lines:
        if pretty_print:
            print(colorama.Fore.GREEN + "(stdout)" + colorama.Style.RESET_ALL, line)
        else:
            _logger.debug("ADbasic stdout: %s", line)

    if parse_stderr:

        # Parse errors and warnings.
        (errors, warnings) = _parse_stderr_lines(stderr_lines)

        # Log parsed errors.
        for error in errors:
            if pretty_print:
                print(f"{colorama.Fore.RED}(error){colorama.Style.RESET_ALL}", str(error))
            else:
                _logger.error("ADbasic error: %s", str(error))
        for error in warnings:
            if pretty_print:
                print(f"{colorama.Fore.RED}(warning){colorama.Style.RESET_ALL}", str(error))
            else:
                _logger.warning("ADbasic warning: %s", str(error))

    else:
        errors = []
        warnings = []

        # Log raw errors.
        for line in stderr_lines:
            if pretty_print:
                print(colorama.Fore.RED + "(stderr)" + colorama.Style.RESET_ALL, line)
            else:
                _logger.error("ADbasic stderr: %s", line)

    # The returncode may be 0 even if compilation failed, especially under Linux.
    # We therefore assume the compiler was successful only if returncode is 0
    # and there are no messages on the stderr stream.
    success = (completed_process.returncode == 0) and (not errors)

    return AdbasicResult(command_line, duration, completed_process.returncode, success, errors, warnings)


def print_adbasic_compiler_help(adwin_dir: str, processor_type: str) -> AdbasicResult:
    # The /<processor_type> is needed to select the ADbasic-to-C compile path.
    adbasic_arguments = [f"/P{processor_type.lstrip('T').replace('.', '')}", "/H"]
    return run_adbasic_compiler(
        adwin_dir,
        processor_type,
        adbasic_arguments,
        working_dir=None,
        parse_stderr=False,
        remove_c_directory=False,
        pretty_print=True
    )


def compile_program(
    basic_filename: str,
    trigger: str,
    process_number: int,
    processor_type: str,
    hardware_type: str,
    priority: int = PRIO_HIGH,
    working_dir: str | None = None,
    keep_c_files: bool = False,
    adwin_dir: str = DEFAULT_ADWINDIR,
    pretty_print: bool = False
) -> AdbasicResult:
    """Compile an ADbasic program.

    The ADbasic compiler expects that include files can be found relative
    to the current working directory.

    If compilation is successful, an executable file will be created in
    the same directory as the source file. The name of this file is based
    on the name of the source file, with the ".bas" extension replaced
    by ".TCn" depending on the process number.

    Parameters:
        basic_filename: File name of the ADbasic .bas file to compile.
        trigger:        Select event trigger mechanism, either "external" or "timer".
        process_number: Select process number, range 1 to 10.
        processor_type: Select processor type "T<x>", where <x> is 11, 12 or 12.1.
        hardware_type:  The hardware that is used for compilation. Possible choices P, PII, G, GII (P=pro, G=Gold)
        priority:       Process priority, integer in range -10 to 10 for low priority,
                        or PRIO_HIGH for high priority.
        working_dir:    Working directory when running the compiler.
                        This determines the base directory for searching include files.
                        Pass None to keep the current working directory of the process.
        keep_c_files:   Keep 'c' directory containing intermediate C files from ADbasic compiler.
                        This only works under Linux.
        adwin_dir:      Base directory of ADwin software installation.
        pretty_print:   True to print compiler messages in pretty colors.
                        False to log messages via the Python log system.

    Returns:
        AdbasicResult: Tuple containing results and error messages (if any) from the compilation process.
                        If compilation is successful, the `success` field of this tuple will be True.
                        If compilation fails, the `success` field will be False and the `errors` field will contain
                        a list of error messages from the compiler.

    Raises:
        AdbasicCompilerException: If an unexpected error occurs while interacting with the ADbasic compiler.
    """
    # The /M instructs the compiler to produce an executable.
    # The /<processor_type> is needed to select the ADbasic-to-C compile path.

    if trigger == "external":
        trigger_argument = "/EE"
    else:
        trigger_argument = "/ET"

    if priority == PRIO_HIGH:
        priority_argument = "/PH"
    elif -10 <= priority <= 10:
        priority_argument = f"/PL{int(priority)}"
    else:
        raise ValueError(f"Invalid process priority {priority!r}")

    process_number_argument = f"/PN{process_number}"
    optimization_level_argument = "/O2"

    adbasic_arguments = [
        "/M",
        f"/P{processor_type.lstrip('T').replace('.', '')}",
        f"/S{hardware_type}",  # Adwin type, SPII for Pro II, SGII for Gold II
        trigger_argument,
        process_number_argument,
        priority_argument,
        optimization_level_argument
    ]
    adbasic_arguments += _library_path_arguments(adwin_dir)
    adbasic_arguments.append(basic_filename)

    return run_adbasic_compiler(
        adwin_dir,
        processor_type,
        adbasic_arguments,
        working_dir,
        parse_stderr=True,
        remove_c_directory=not keep_c_files,
        pretty_print=pretty_print
    )


def compile_library(
    basic_filename: str,
    processor_type: str,
    hardware_type: str,
    working_dir: str | None = None,
    keep_c_files: bool = False,
    adwin_dir: str = DEFAULT_ADWINDIR,
    pretty_print: bool = False
) -> AdbasicResult:

    # The /L instructs the compiler to produce a library.
    # The /<processor_type> is needed to select the ADbasic-to-C compile path.
    # The /<hardware_type> is needed for the compiler info.
    # The optimization level argument is "/O2"

    adbasic_arguments = [
        "/L",
        f"/P{processor_type.lstrip('T').replace('.', '')}",
        f"/S{hardware_type}",
        "/O2"
    ]
    adbasic_arguments += _library_path_arguments(adwin_dir)
    adbasic_arguments.append(basic_filename)

    return run_adbasic_compiler(
        adwin_dir,
        processor_type,
        adbasic_arguments,
        working_dir,
        parse_stderr=True,
        remove_c_directory=not keep_c_files,
        pretty_print=pretty_print
    )


def check_compiler_result(basic_filename: str, result: AdbasicResult) -> None:
    """Check that the compiler run was successful.

    Parameters:
        basic_filename: File name of the ADbasic .bas file.
        result:         Result from running the compiler.

    Raises:
        AdbasicCompilerException: If the compiler was not successful.
    """
    if not result.success:
        raise AdbasicCompilerException(
            "ADbasic compiler reported error when compiling {!r} (exit status {})".format(
                basic_filename, result.returncode
            ), result.errors
        )


def run():

    exitcode = 0

    DEFAULT_TRIGGER_MECHANISM = "external"
    DEFAULT_PROCESSOR_TYPE = "T12"
    DEFAULT_HARDWARE_TYPE = "PII"
    DEFAULT_PROCESS_NUMBER = 1

    parser = argparse.ArgumentParser(
        description="Python wrapper for the ADbasic script, with improved error reporting.")

    parser.add_argument("--adwin-dir", default=DEFAULT_ADWINDIR,
                        help=f"base directory of ADwin software installation (default: {DEFAULT_ADWINDIR!r})")
    parser.add_argument("--compiler-help", action="store_true",
                        help="show help of the underlying ADbasic compiler")
    parser.add_argument("-k", "--keep-c-files", action="store_true",
                        help="keep local 'c' directory containing intermediate C files from ADbasic compiler")
    parser.add_argument("-l", "--library", action="store_true",
                        help="compile a library instead of a binary executable")
    parser.add_argument("-P", "--processor-type", choices=["T11", "T12", "T12.1"],
                        default=DEFAULT_PROCESSOR_TYPE,
                        help=f"select ADwin processor type (default: {DEFAULT_PROCESSOR_TYPE!r})")
    parser.add_argument("-H", "--hardware-type", choices=["P", "PII", "G", "GII"],
                        default=DEFAULT_HARDWARE_TYPE,
                        help=f"select ADwin hardware type (default: {DEFAULT_HARDWARE_TYPE!r})")
    parser.add_argument("-t", "--trigger", choices=["external", "timer"], default=DEFAULT_TRIGGER_MECHANISM,
                        help=f"select event trigger mechanism (default: {DEFAULT_TRIGGER_MECHANISM!r})")
    parser.add_argument("-p", "--process-number", type=int, default=DEFAULT_PROCESS_NUMBER,
                        help=f"select process number, range 1..10 (default: {DEFAULT_PROCESS_NUMBER})")
    parser.add_argument("filename", nargs='?', help="file name of the adbasic .bas file")

    args = parser.parse_args()

    colorama.init()
    try:
        result = None
        if args.compiler_help:
            result = print_adbasic_compiler_help(args.adwin_dir, args.processor_type)
        elif args.filename is None:
            parser.print_usage()
        elif args.library:
            result = compile_library(
                args.filename,
                processor_type=args.processor_type,
                hardware_type=args.hardware_type,
                working_dir=None,
                keep_c_files=args.keep_c_files,
                adwin_dir=args.adwin_dir,
                pretty_print=True
            )
            if not result.success:
                exitcode = 1
        else:
            result = compile_program(
                args.filename,
                args.trigger,
                args.process_number,
                args.processor_type,
                hardware_type=args.hardware_type,
                priority=PRIO_HIGH,
                working_dir=None,
                keep_c_files=args.keep_c_files,
                adwin_dir=args.adwin_dir,
                pretty_print=True
            )
            if not result.success:
                exitcode = 1

        if result is not None:
            print()
            print("Executed command line:")
            print()
            print(f"    {result.command_line}")
            print()
            print(f"Execution time: {result.duration:.3f} seconds.")
            print()
            print(f"Performing exit({exitcode}), bye!")
            print()
    finally:
        colorama.deinit()

    return exitcode


if __name__ == "__main__":
    sys.exit(run())
