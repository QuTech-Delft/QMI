"""Parse an ADbasic program.

This module provides functions to parse an ADbasic program and its include files,
extracting information from the symbol definitions in the program.

This module can also be executed with a toplevel ADbasic filename as an argument, to get an overview
of the defined symbols.
"""

import argparse
import logging
import os.path
import re
from typing import NamedTuple

from qmi.core.exceptions import QMI_Exception


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class SymbolInfo(NamedTuple):
    """Symbol defined in the ADbasic program source."""
    filename: str
    line_nr: int
    label: str
    value: str


class ParDesc(NamedTuple):
    """Represents a global Par_nn variable."""
    par_index: int

    def __str__(self) -> str:
        return f"Par_{self.par_index}"


class FParDesc(NamedTuple):
    """Represents a global FPar_nn variable."""
    fpar_index: int

    def __str__(self) -> str:
        return f"FPar_{self.fpar_index}"


class ArrayElemDesc(NamedTuple):
    """Represents an element inside a global Data_nnn array."""
    data_index: int
    elem_index: int

    def __str__(self) -> str:
        return f"Data_{self.data_index}[{self.elem_index}]"


ParameterDesc = ParDesc | FParDesc | ArrayElemDesc


class ParameterInfo(NamedTuple):
    """Represents the collection of externally accessible parameters of an ADbasic program.

    Attributes:
        param:  Mapping from parameter name to a `ParDesc`, `FParDesc` or `ArrayElemDesc` instance.
        data:   Mapping from data name to the index of the global `Data_nnn` array.
    """
    param: dict[str, ParameterDesc]
    data: dict[str, int]


class ParseException(QMI_Exception):
    """Raised when parsing fails."""

    def __init__(self, filename: str, line_nr: int, message: str) -> None:
        super().__init__([filename, line_nr, message])
        self.filename = filename
        self.line_nr = line_nr
        self.message = message

    def __str__(self) -> str:
        return f"{self.filename}, line {self.line_nr}: {self.message}"


def _resolve_include_path(include_path: str, source_file: str, include_dir: str) -> str | None:
    """Resolve the OS path name of an ADbasic include file.

    Only local include paths are processed.
    System-wide includes are rejected and return None.

    Parameters:
        include_path: Include path string as it occurs in the ADbasic source code.
        source_file: File name of the including source file.
        include_dir: Base directory for resolving relative include paths.

    Returns:
        Path name of the OS-level location of the include file, or None if
        this include-file should not be processed.
    """

    # Separate include path into components.
    path_components = include_path.replace("\\", "/").split("/")

    # Check whether the include path consists of only a file name without a directory component.
    # This means it is a system-wide include, so ignore it.
    if len(path_components) <= 1:
        return None

    # Check whether the include path is an absolute path (starts with a "/").
    # We don't support that, so warn and ignore.
    if path_components[0] == "":
        _logger.warning("Absolute include path not supported: %r", include_path)
        return None

    # Check whether the include path uses a parent component "..", or current path component ".".
    if any(comp.startswith("..") or comp.startswith(".") for comp in path_components):
        source_path = os.path.dirname(source_file)
        parent_relative_path = os.path.join(source_path, *path_components)
        norm_relative_path = os.path.normpath(parent_relative_path)
        return norm_relative_path

    # Resolve the include path relative to the local include directory.
    return os.path.join(include_dir, *path_components)


def _parse_single_adbasic_file(filename: str) -> tuple[list[SymbolInfo], list[str]]:
    """Parse a single ADBasic source file and return a tuple of defined symbols and included files.

    Parameters:
        filename: File name of ADBasic source to parse.

    Returns:
        defined_symbols, include_paths: `defined_symbols` is a list of defined symbols and
                                        `include_paths` is a list of included files.
    """

    _logger.debug("Parsing %s", filename)

    with open(filename, "r") as fi:
        source = fi.read()

    # Define a regexp for lines that look like:
    #
    #   #Define SymbolName SymbolValue ' optional comment.
    #
    # This regexp is slightly complex because we have to handle an optional comment at the end of the line.

    re_define = re.compile(r"^\s*#Define\s+(\S+)\s+([^\s']+)\s*(?:'.*)?$", re.ASCII | re.IGNORECASE)

    re_include = re.compile(r"^\s*#Include\s+([^\s']+)\s*(?:'.*)?$", re.ASCII | re.IGNORECASE)

    defined_symbols = []
    include_paths = []

    for (line_nr, line_text) in enumerate(source.splitlines()):

        match = re_define.match(line_text)
        if match is not None:
            (symbol, value) = match.groups()
            symbol_info = SymbolInfo(filename, line_nr + 1, symbol, value)
            defined_symbols.append(symbol_info)

        match = re_include.match(line_text)
        if match is not None:
            include_path = match.group(1)
            include_paths.append(include_path)

    return (defined_symbols, include_paths)


def parse_adbasic_program(filename: str, include_dir: str) -> list[SymbolInfo]:
    """Parse an ADbasic program (and, recursively, its include files) to find #Define lines.

    Parameters:
        filename:    File name of ADBasic source to parse.
        include_dir: Base directory for resolving relative include paths.
                     May be empty to use the current working directory.

    Returns:
        all_defined_symbols: List of SymbolInfo objects to describe defined symbols.
    """

    files_remaining = [filename]

    all_defined_symbols = []

    while files_remaining:
        sourcefile = files_remaining.pop(0)
        (defined_symbols, include_paths) = _parse_single_adbasic_file(sourcefile)
        all_defined_symbols.extend(defined_symbols)

        # Add included files to parse queue.
        for include_path in include_paths:
            resolved_include_path = _resolve_include_path(include_path, sourcefile, include_dir)
            if resolved_include_path:
                files_remaining.append(resolved_include_path)

    return all_defined_symbols


def _extract_data_defines(symbols: list[SymbolInfo]) -> dict[str, int]:
    """Extract data array information from symbol definitions.

    Parameters:
        symbols: List of SymbolInfo objects to describe defined symbols.

    Returns:
        data_info: Data names with respective data indexes as dictionary.
    """

    # Maintain a mapping from uppercase parameter name to the actual case of the name.
    # This is used to check for duplicate definitions because identifiers are case-insensitive in ADbasic.
    name_case_map: dict[str, str] = {}

    data_info: dict[str, int] = {}
    ref_to_name: dict[int, str] = {}

    for symbol in symbols:

        # Only process symbol names that start with "DATA_".
        if not symbol.label.upper().startswith("DATA_"):
            continue

        # Extract data name.
        (_prefix, data_name) = symbol.label.split("_", maxsplit=1)

        # Extract index of the global data array.
        match = re.match(r'^Data_([0-9]+)$', symbol.value, re.IGNORECASE)
        if match:
            data_index = int(match.group(1))
        else:
            _logger.warning("Unrecognized symbol definition format for %r", symbol.label)
            continue

        # Check for duplicate definition of this symbol with different case.
        prev_name = name_case_map.get(data_name.upper())
        if (prev_name is not None) and (prev_name != data_name):
            raise ParseException(
                filename=symbol.filename,
                line_nr=symbol.line_nr,
                message=f"Duplicate definition of symbol {symbol.label} with different case")

        # Check for duplicate definition of this symbol with different data index.
        prev_index = data_info.get(data_name)
        if (prev_index is not None) and (prev_index != data_index):
            raise ParseException(
                filename=symbol.filename,
                line_nr=symbol.line_nr,
                message=f"Duplicate definition of symbol {symbol.label} for different data array"
            )

        # Check for duplicate use of the same Data_nnn array under different names.
        prev_name = ref_to_name.get(data_index)
        if (prev_name is not None) and (prev_name != data_name):
            raise ParseException(
                filename=symbol.filename,
                line_nr=symbol.line_nr,
                message=f"Symbol {symbol.label} is a duplicate reference to {symbol.value}"
            )

        # Store new symbol definition.
        data_info[data_name] = data_index
        ref_to_name[data_index] = data_name
        name_case_map[data_name.upper()] = data_name

    return data_info


def _extract_par_defines(symbols: list[SymbolInfo], data_info: dict[str, int]) -> dict[str, ParameterDesc]:
    """Extract scalar parameter information from symbol definitions.

    Parameters:
        symbols:   List of SymbolInfo objects to describe defined symbols.
        data_info: Data names with respective data indexes as dictionary.

    Returns:
        param_info: Parameter names with parameter description objects as dictionary.
    """

    # Rebuild Data_nnn index using uppercase parameter names for case-insensitive lookup.
    data_info_upper = dict((name.upper(), value) for (name, value) in data_info.items())

    # Maintain a mapping from uppercase parameter name to the actual case of the name.
    # This is used to check for duplicate definitions because identifiers are case-insensitive in ADbasic.
    name_case_map: dict[str, str] = {}

    param_info: dict[str, ParameterDesc] = {}
    ref_to_name: dict[str, str] = {}

    for symbol in symbols:

        # Only process symbol names that start with "PAR_".
        if not symbol.label.upper().startswith("PAR_"):
            continue

        # Extract parameter name.
        (_prefix, param_name) = symbol.label.split("_", maxsplit=1)

        param_desc: ParameterDesc | None = None

        # Try to match parameter in global Par variable.
        if param_desc is None:
            match = re.match(r'^Par_([0-9]+)$', symbol.value, re.IGNORECASE)
            if match:
                par_index = int(match.group(1))
                param_desc = ParDesc(par_index)

        # Try to match parameter in global FPar variable.
        if param_desc is None:
            match = re.match(r'^FPar_([0-9]+)$', symbol.value, re.IGNORECASE)
            if match:
                par_index = int(match.group(1))
                param_desc = FParDesc(par_index)

        # Try to match parameter in data array element.
        if param_desc is None:
            match = re.match(r'^Data_(\S+)\s*\[\s*([0-9]+)\s*]$', symbol.value, re.IGNORECASE)
            if match:
                data_name = match.group(1)
                elem_index = int(match.group(2))
                data_index = data_info_upper.get(data_name.upper())
                if data_index is None:
                    raise ParseException(
                        filename=symbol.filename,
                        line_nr=symbol.line_nr,
                        message=f"Symbol {symbol.label} refers to unknown array {data_name}"
                    )
                data_index = data_info_upper[data_name.upper()]
                param_desc = ArrayElemDesc(data_index, elem_index)

        if param_desc is None:
            _logger.warning("Unrecognized symbol definition format for %r", symbol.label)
            continue

        # Check for duplicate definition of this symbol with different case.
        prev_name = name_case_map.get(param_name.upper())
        if (prev_name is not None) and (prev_name != param_name):
            raise ParseException(
                filename=symbol.filename,
                line_nr=symbol.line_nr,
                message=f"Duplicate definition of symbol {symbol.label} with different case"
            )

        # Check for duplicate definition of this symbol with different data index.
        prev_desc = param_info.get(param_name)
        if (prev_desc is not None) and (type(prev_desc) != type(param_desc) or prev_desc != param_desc):
            raise ParseException(
                filename=symbol.filename,
                line_nr=symbol.line_nr,
                message=f"Duplicate definition of symbol {symbol.label} for different parameter"
            )

        # Check for duplicate use of the same parameter under different names.
        prev_name = ref_to_name.get(repr(param_desc))
        if (prev_name is not None) and (prev_name != param_name):
            raise ParseException(
                filename=symbol.filename,
                line_nr=symbol.line_nr,
                message=f"Symbol {symbol.label} is a duplicate reference to {symbol.value}"
            )

        # Store new symbol definition.
        param_info[param_name] = param_desc
        ref_to_name[repr(param_desc)] = param_name
        name_case_map[param_name.upper()] = param_name

    return param_info


def analyze_parameter_info(symbols: list[SymbolInfo]) -> ParameterInfo:
    """Analyze a set of ADbasic symbol definitions to extract parameter information.

    Only the following types of symbol definitions are processed:
     - `#Define PAR_parname Par_nn` (binds `parname` to global Par variable).
     - `#Define PAR_parname FPar_nn` (binds `parname` to global FPar variable).
     - `#Define DATA_arrayname Data_nnn` (binds `arrayname` to global Data array).
     - `#Define PAR_parname DATA_arrayname[ii]` (binds `parname` to a specific element in a global data array).

    Parameters:
        symbols: List of symbol definitions (as produced by `parse_adbasic_program`).

    Returns:
        ParameterInfo: Instance containing a description of all named parameters and named arrays.
    """

    data_info = _extract_data_defines(symbols)
    param_info = _extract_par_defines(symbols, data_info)
    return ParameterInfo(param_info, data_info)


def print_symbol_info(symbols: list[SymbolInfo]) -> None:
    """Print the result of parse_adbasic_program()."""

    for symbol in symbols:
        print(f"{symbol.filename}, {symbol.line_nr}: #Define {symbol.label} {symbol.value}")


def print_parameter_info(param_info: ParameterInfo) -> None:
    """Print the result of analyze_adbasic_symbols()."""

    sort_order = {
        ParDesc: 1,
        FParDesc: 2,
        ArrayElemDesc: 3 }

    par_items = list(param_info.param.items())
    par_items.sort(key=lambda kv: (sort_order.get(type(kv[1])), tuple(kv[1])))
    for (name, desc) in par_items:
        print(f"PAR_{name:32} = {desc!s}")

    data_items = list(param_info.data.items())
    data_items.sort(key=lambda kv: kv[1])
    for (name, index) in data_items:
        print(f"DATA_{name:32} = Data_{index}")


def run():

    parser = argparse.ArgumentParser(description="Parse ADbasic program and extract #Define'd constants.")
    parser.add_argument("filename", help="toplevel ADbasic file to be analyzed")
    args = parser.parse_args()

    symbols = parse_adbasic_program(args.filename, os.path.dirname(args.filename))

    param_info = analyze_parameter_info(symbols)
    print_parameter_info(param_info)


if __name__ == "__main__":
    run()
