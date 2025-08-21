"""
Manage access to programs and data on the ADwin.
"""

import json
import logging
import os
import os.path
from dataclasses import field
from collections.abc import Iterable
from typing import Any, NamedTuple

import numpy as np

from qmi.core.config import load_config_file
from qmi.core.config_struct import config_struct_from_dict, configstruct
from qmi.core.exceptions import (QMI_ConfigurationException,
                                 QMI_InstrumentException)
from qmi.instruments.adwin.adwin import Adwin_Base
from qmi.utils.adbasic_compiler import check_compiler_result, compile_program
from qmi.utils.adbasic_parser import (ArrayElemDesc, FParDesc, ParameterDesc,
                                      ParameterInfo, ParDesc,
                                      analyze_parameter_info,
                                      parse_adbasic_program)

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@configstruct
class CfgAdwinProgram:
    """Configuration for a specific Adwin program.

    Parameters:
        file:       File name of the top-level ".bas" file without the ".bas" extension.
                    This file name is interpreted relative to the Adwin program directory.
        slot:       Process ("slot") number in the ADwin (range 1 to 10). Not the same as physical encasing slots.
        trigger:    Event trigger source, either "timer" or "external".
        priority:   Process priority, either an integer between -10 and +10 for a low priority process,
                    or 1000 for a high priority process.
        parse_parameters: True to discover parameters by parsing the ADbasic source code.
        par:        Dictionary mapping parameter name to global Par_nn index.
        fpar:       Dictionary mapping parameter name to global FPar_nn index.
        data:       Dictionary mapping array name to global Data_nnn index.
        par_array:  Dictionary mapping parameter name to list [nnn, k] referring to array element Data_nnn[k].
    """
    file:       str
    slot:       int
    trigger:    str
    priority:   int
    parse_parameters: bool = False
    par:        dict[str, int] = field(default_factory=dict)
    fpar:       dict[str, int] = field(default_factory=dict)
    data:       dict[str, int] = field(default_factory=dict)
    par_array:  dict[str, tuple[int, int]] = field(default_factory=dict)  # Tuple does not get parsed correctly in JSON!


class ProgramInfo(NamedTuple):
    """Information about an ADwin program.

    Attributes:
        file:       Path name to the top-level ".bas" file without the ".bas" extension.
        slot:       Process slot number in the ADwin (range 1 to 10). Not the same as physical encasing slots.
        trigger:    Event trigger source, either "timer" or "external".
        priority:   Process priority, either an integer between -10 and +10 for a low priority process,
                    or 1000 for a high priority process.
        parameters: Information about parameters and data arrays in the ADbasic program.
    """
    file: str
    slot: int
    trigger: str
    priority: int
    param_info: ParameterInfo

    @classmethod
    def from_config(cls, config: CfgAdwinProgram, program_dir: str) -> 'ProgramInfo':
        """Create a ProgramInfo from a CfgAdwinProgram instance.

        Parameters:
            config: Adwin program configuration.
            program_dir: directory where adwin program files are located.

        Returns:
            Instance of ProgramInfo.

        Raises:
            QMI_ConfigurationException: If an error occurs while reading parameter configuration data.
            ParseException: If an error occurs while parsing the ADbasic source code.
        """
        filename = os.path.join(program_dir, config.file)

        if config.parse_parameters:
            # Get parameter info by parsing the ADbasic source code.
            symbols = parse_adbasic_program(f"{filename}.bas", program_dir)
            param_info = analyze_parameter_info(symbols)

        else:
            # Use explicitly specified parameters.
            param_items: list[tuple[str, ParameterDesc]] = []
            for (name, par_index) in config.par.items():
                param_items.append((name, ParDesc(par_index)))
            for (name, fpar_index) in config.fpar.items():
                param_items.append((name, FParDesc(fpar_index)))
            for (name, ref) in config.par_array.items():
                (data_index, elem_index) = ref
                param_items.append((name, ArrayElemDesc(data_index, elem_index)))

            param: dict[str, ParameterDesc] = {}
            for (name, desc) in param_items:
                if name in param:
                    raise QMI_ConfigurationException(
                        f"Duplicate use of parameter name {name!r} in ADwin program \"{config.file!r}\"!"
                    )
                param[name] = desc

            param_info = ParameterInfo(param=param, data=config.data)

        # Create program information structure.
        return cls(file=filename,
                   slot=config.slot,
                   trigger=config.trigger.lower(),
                   priority=config.priority,
                   param_info=param_info)

    @classmethod
    def from_config_file(cls, config_file: str, program_dir: str) -> 'ProgramInfo':
        """Create a ProgramInfo from a program configurations file.

        Parameters:
            config_file: A configuration file with Adwin program configuration(s).
            program_dir: directory where adwin program files are located.

        Returns:
            Instance of ProgramInfo.
        """
        config_dict = load_config_file(config_file)
        config = config_struct_from_dict(config_dict, CfgAdwinProgram)
        return cls.from_config(config, program_dir)


class AdwinProgramLibrary:
    """Manage a collection of ADwin programs."""

    def __init__(
            self,
            program_dir: str,
            config_dir: str,
            processor_type: str = "T12",
            hardware_type: str = "PII"
    ) -> None:
        """Initialize a collection of ADwin programs.

        Parameters:
            program_dir:     Directory where ADbasic source code and compiled programs are located.
                             File names of programs are interpreted relative to this directory.
            config_dir:      Directory where program-specific configuration files are located.
            processor_type:  Parameter to select a specific processor type "T<x>", where <x> is 11, 12 or 12.1.
                             Default is 'T12'
            hardware_type:   Parameter to select a specific processor type "<x>", where <x> is P, PII, G, GII
                             (P=pro, G=Gold). Default is 'PII'.
        """
        self._program_dir = program_dir
        self._config_dir = config_dir
        self._processor_type = processor_type
        self._hardware_type = hardware_type
        self._program_config: dict[str, CfgAdwinProgram] = {}
        self._program_info_cache: dict[str, ProgramInfo] = {}
        self._read_program_config_files()

    def _read_program_config_files(self) -> None:
        """Scan the configuration directory and read program-specific configuration files."""

        file_names = os.listdir(self._config_dir)

        for file_name in file_names:
            if not file_name.startswith("."):
                (prog_name, ext) = os.path.splitext(file_name)
                if (ext == ".conf") and (not prog_name.startswith("_")):
                    _logger.debug("Reading Adwin program config %s", file_name)
                    full_name = os.path.join(self._config_dir, file_name)
                    try:
                        cfg_dict = load_config_file(full_name)
                        prog_cfg = config_struct_from_dict(cfg_dict, CfgAdwinProgram)
                    except (json.JSONDecodeError, QMI_ConfigurationException) as exc:
                        raise QMI_ConfigurationException(
                            f"Error reading Adwin program config {file_name}") from exc
                    self._check_program_config(prog_name, prog_cfg)
                    self._program_config[prog_name] = prog_cfg

    @staticmethod
    def _check_program_config(prog_name: str, prog_cfg: CfgAdwinProgram) -> None:

        if prog_cfg.slot < 1 or prog_cfg.slot > 10:
            raise QMI_ConfigurationException(
                f"Invalid ADwin process slot number {prog_cfg.slot} for program {prog_name!r}"
            )

        if prog_cfg.trigger.lower() not in ("timer", "external"):
            raise QMI_ConfigurationException(
                f"Invalid ADwin process trigger {prog_cfg.trigger!r} for program {prog_name!r}"
            )

        if ((prog_cfg.priority < -10) or (prog_cfg.priority > 10)) and (prog_cfg.priority != 1000):
            raise QMI_ConfigurationException(
                f"Invalid ADwin process priority {prog_cfg.priority} for program {prog_name!r}"
            )

        if prog_cfg.parse_parameters and (prog_cfg.par or prog_cfg.fpar or prog_cfg.data or prog_cfg.par_array):
            raise QMI_ConfigurationException(f"Invalid configuration for ADwin program {prog_name!r}"
                                             + ": Can not parse source code and specify explicit parameters")

    def list_programs(self) -> list[str]:
        """Return a list of available programs."""
        return list(self._program_config.keys())

    def get_program_info(self, program_name: str) -> ProgramInfo:
        """Return information about the specified program.

        This function may read a program-specific configuration file or
        parse the ADbasic source code to obtain information about the
        parameters and data arrays used by this program.

        Parameters:
            program_name: Unique name of the program, used to identify
                          this program within the ADwin configuration data.

        Returns:
            Information about the specified program.

        Raises:
            KeyError: If the specified program name is unknown.
            QMI_ConfigurationException: If an error occurs while reading parameter configuration data.
            ParseException: If an error occurs while parsing the ADbasic source code.
        """

        # Return cached information if available.
        info = self._program_info_cache.get(program_name)
        if info is not None:
            return info

        # Create program info from config
        info = ProgramInfo.from_config(self._program_config[program_name], self._program_dir)

        # Add to cached information
        self._program_info_cache[program_name] = info

        return info

    def compile(self, program_name: str) -> None:
        """Compile the specified program with the ADbasic compiler.

        Parameters:
            program_name: Unique name of the program.

        Raises:
            KeyError: If the specified program name is unknown.
            AdbasicCompilerException: If an error occurs while compiling the program.
        """

        # Look up in program table.
        prog_cfg = self._program_config[program_name]

        _logger.info("Compiling ADbasic program %s", program_name)

        # Run the compiler in the directory that contains the ".bas" file.
        # This implies that include files are resolved relative to the location of the .bas file.
        working_dir = os.path.join(self._program_dir, os.path.dirname(prog_cfg.file))
        basic_filename = os.path.basename(prog_cfg.file) + ".bas"

        # Run compiler.
        result = compile_program(basic_filename,
                                 processor_type=self._processor_type,
                                 hardware_type=self._hardware_type,
                                 trigger=prog_cfg.trigger,
                                 process_number=prog_cfg.slot,
                                 priority=prog_cfg.priority,
                                 working_dir=working_dir,
                                 pretty_print=False)

        # Raise exception if compiler failed.
        check_compiler_result(basic_filename, result)


class AdwinProcess:
    """Access a specific process running on a specific ADwin.

    An instance of this class represents a specific process on a specific
    ADwin instrument.  The process may be in one of several states:
    running, loaded but not yet running, or not yet loaded.

    If the process is loaded (and possibly running), data may be transferred
    from Python to the ADwin process and vice versa.

    Global parameters and data arrays are accessed by name. These names are
    mapped to `Par_nn`, `FPar_nn` and `Data_nn` indices by lookup in a
    name table. This table is either specified explicitly as part of
    the ADwin configuration, or derived from parsing the ADbasic code.
    """

    def __init__(self, adwin: Adwin_Base, name: str, program_info: ProgramInfo) -> None:
        """Initialize this object instance.

        This does not yet access the ADwin and/or start the process.

        Parameters:
            adwin:      Adwin instrument driver.
            name:       Program name.
            program_info: Information about the ADwin program.
        """
        self._name = name
        self._adwin = adwin
        self._file_name = program_info.file
        self._process_number = program_info.slot
        self._param_info = program_info.param_info
        self._processor_type = adwin.get_processor_type()

    @staticmethod
    def _get_dict_item_case_insensitive(key: str, dict_items: dict[str, Any]):
        for dict_item_key in dict_items.keys():
            if key.lower() == dict_item_key.lower():
                return dict_items[dict_item_key]
        raise KeyError("Key not found!")

    def _get_par_desc(self, par_name):
        try:
            return self._get_dict_item_case_insensitive(par_name, self._param_info.param)
        except KeyError:
            raise ValueError(f"Unknown parameter {par_name} for process {self._name}")

    def _get_data_idx(self, data_name):
        try:
            return self._get_dict_item_case_insensitive(data_name, self._param_info.data)
        except KeyError:
            raise ValueError(f"Unknown data array {data_name} for process {self._name}")

    def load(self) -> None:
        """Load the Adwin process but do not start it yet.

        If a process is already running in the same process slot number, that process will be stopped.
        """
        if "T12" in self._processor_type.upper():
            bin_file = self._file_name + f".TC{self._process_number % 10}"  # T12 and T12.1

        else:
            bin_file = self._file_name + f".TB{self._process_number % 10}"  # T11 gets extension "TB{}".

        self._adwin.stop_process(self._process_number)
        self._adwin.wait_for_process(self._process_number, Adwin_Base.PROCESS_STOP_TIMEOUT)
        self._adwin.load_process(bin_file)

    def start(self) -> None:
        """Start running the Adwin process.

        The process must already have been loaded by calling the `load()` method.
        The process must not already be running.

        This function will not initialize or modify any parameters before starting the process.

        Raise:
            QMI_InstrumentException: If the process is already running.
        """
        if self._adwin.is_process_running(self._process_number):
            raise QMI_InstrumentException(
                f"Can not start Adwin process {self._name}, process {self._process_number} already running"
            )
        self._adwin.start_process(self._process_number)

    def start_with_params(self, **kwargs: Any) -> None:
        """Send parameter values to the Adwin, then start running the Adwin process.

        The process must already have been loaded by calling the `load()` method.
        The process must not already be running.

        Parameters for the Adwin process may be specified as keyword parameters to this function.
        These parameters will be sent to the Adwin prior to starting the process.

        Notes:
            Parameter name lookup is performed case-insensitive.

        Raise:
            QMI_InstrumentException: If the process is already running.
        """

        # Check that process is not running.
        if self._adwin.is_process_running(self._process_number):
            raise QMI_InstrumentException(
                f"Can not start Adwin process {self._name}, process {self._process_number} already running"
            )

        # Set parameters. Fill-in zero for unspecified parameters.
        params = {}
        for par_name in self._param_info.param.keys():
            try:
                params[par_name] = self._get_dict_item_case_insensitive(par_name, kwargs)
            except KeyError:
                params[par_name] = 0
        self.set_par_multiple(params)

        # Start process.
        self._adwin.start_process(self._process_number)

    def stop(self) -> None:
        """Stop running the Adwin process."""
        self._adwin.stop_process(self._process_number)
        self._adwin.wait_for_process(self._process_number, Adwin_Base.PROCESS_STOP_TIMEOUT)

    def is_running(self) -> bool:
        """Return True if the Adwin process is currently running.

        It is assumed that the process is already loaded. This function only
        checks whether any process is running in the specified slot number.
        It can not guarantee that the running process matches the expected program.
        """
        return self._adwin.is_process_running(self._process_number)

    def wait_for_process(self, timeout: float) -> None:
        """Wait until the Adwin process has stopped.

        Parameters:
            timeout: Maximum time to wait (seconds).

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the process does not stop before timeout occurs.
        """
        self._adwin.wait_for_process(self._process_number, timeout)

    def get_par(self, par_name: str) -> int | float:
        """Return the current value of the specified parameter.

        Notes:
            Parameter name lookup is performed case-insensitive.

        Parameters:
            par_name: Parameter name.

        Returns:
            Value of the parameter.
        """
        param_desc = self._get_par_desc(par_name)
        if isinstance(param_desc, ParDesc):
            return self._adwin.get_par(param_desc.par_index)
        elif isinstance(param_desc, FParDesc):
            return self._adwin.get_fpar(param_desc.fpar_index)
        elif isinstance(param_desc, ArrayElemDesc):
            elems = self._adwin.get_data(param_desc.data_index, param_desc.elem_index, 1)
            return elems[0]
        else:
            raise ValueError(f"Unknown parameter {par_name} for process {self._name}")

    def set_par(self, par_name: str, value: int | float) -> None:
        """Change the value of the specified parameter.

        Notes:
            Parameter name lookup is performed case-insensitive.

        Parameters:
            par_name: Parameter name.
            value: New value to write to the parameter.
        """
        param_desc = self._get_par_desc(par_name)
        if isinstance(param_desc, ParDesc):
            if not isinstance(value, int):
                raise TypeError(f"Expecting integer value for parameter {par_name} but got {value}")
            self._adwin.set_par(param_desc.par_index, value)
        elif isinstance(param_desc, FParDesc):
            self._adwin.set_fpar(param_desc.fpar_index, value)
        elif isinstance(param_desc, ArrayElemDesc):
            elems = np.array([value])
            self._adwin.set_data(param_desc.data_index, param_desc.elem_index, elems)
        else:
            raise ValueError(f"Unknown parameter {par_name} for process {self._name}")

    @staticmethod
    def _find_sequential_ranges(seq: Iterable[int]) -> list[tuple[int, int]]:
        """Find sequential ranges of in a sequence of integers."""
        sorted_seq = sorted(seq)
        ret = []
        if sorted_seq:
            start_range = sorted_seq[0]
            end_range = sorted_seq[0]
            for value in sorted_seq[1:]:
                if value == end_range + 1:
                    end_range = value
                elif value > end_range:
                    ret.append((start_range, end_range))
                    start_range = value
                    end_range = value
            ret.append((start_range, end_range))
        return ret

    def get_par_multiple(self, params: list[str]) -> dict[str, int | float]:
        """Fetch multiple parameter values from the Adwin.

        Notes:
            Parameter name lookup is performed case-insensitive.
        """

        # Initialize result.
        result: dict[str, int | float] = {}

        # Initialize an index of array elements to be fetched.
        params_data: dict[int, dict[int, str]] = {}

        # Fetch Par_nn and FPar_nn parameters.
        # Also build the index of array elements to be fetched.
        for par_name in params:
            param_desc = self._get_par_desc(par_name)
            if isinstance(param_desc, ParDesc):
                result[par_name] = self._adwin.get_par(param_desc.par_index)
            elif isinstance(param_desc, FParDesc):
                result[par_name] = self._adwin.get_fpar(param_desc.fpar_index)
            elif isinstance(param_desc, ArrayElemDesc):
                if param_desc.data_index not in params_data:
                    params_data[param_desc.data_index] = {}
                params_data[param_desc.data_index][param_desc.elem_index] = par_name
            else:
                raise ValueError(f"Unknown parameter {par_name} for process {self._name}")

        # Fetch array parameters.
        for data_index in sorted(params_data.keys()):
            data_elems = params_data[data_index]
            # Merge sequential index ranges within array.
            for (elem_index_start, elem_index_end) in self._find_sequential_ranges(data_elems.keys()):
                num_elems = elem_index_end + 1 - elem_index_start
                values = self._adwin.get_data(data_index, elem_index_start, num_elems)
                for k in range(num_elems):
                    par_name = data_elems[elem_index_start + k]
                    result[par_name] = values[k]

        return result

    def set_par_multiple(self, params: dict[str, int | float]) -> None:
        """Send multiple parameter values to the Adwin.

        Notes:
            Parameter name lookup is performed case-insensitive.
        """

        # Initialize an index of array elements to be uploaded.
        params_data: dict[int, dict[int, int | float]] = {}

        # Upload Par_nn and FPar_nn parameters.
        # Also fill the index of array elements to be uploaded.
        for (par_name, par_value) in params.items():
            param_desc = self._get_par_desc(par_name)
            if isinstance(param_desc, ParDesc):
                if not isinstance(par_value, int):
                    raise TypeError(f"Expecting integer value for parameter {par_name} but got {par_value}")
                self._adwin.set_par(param_desc.par_index, par_value)
            elif isinstance(param_desc, FParDesc):
                self._adwin.set_fpar(param_desc.fpar_index, par_value)
            elif isinstance(param_desc, ArrayElemDesc):
                if param_desc.data_index not in params_data:
                    params_data[param_desc.data_index] = {}
                params_data[param_desc.data_index][param_desc.elem_index] = par_value
            else:
                raise ValueError(f"Unknown parameter {par_name} for process {self._name}")

        # Upload array parameters.
        for data_index in sorted(params_data.keys()):
            data_elems = params_data[data_index]
            # Merge sequential index ranges within array.
            for (elem_index_start, elem_index_end) in self._find_sequential_ranges(data_elems.keys()):
                values = [data_elems[i] for i in range(elem_index_start, elem_index_end + 1)]
                self._adwin.set_data(data_index, elem_index_start, np.array(values))

    def get_data_length(self, data_name: str) -> int:
        """Return the length of the specified global Data array.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the data array.

        Returns:
            Number of elements in the array.
        """
        data_idx = self._get_data_idx(data_name)
        return self._adwin.get_data_length(data_idx)

    def get_data(self, data_name: str, first_index: int, count: int) -> np.ndarray:
        """Read values from a global DATA array.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the data array.
            first_index: First index into the data array (>= 1).
            count: Number of elements to read from the data array.

        Returns:
            1D Numpy array with data values.
        """
        data_idx = self._get_data_idx(data_name)
        return self._adwin.get_data(data_idx, first_index, count)

    def get_full_data(self, data_name: str) -> np.ndarray:
        """Read all elements from a global Data array.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the data array.

        Returns:
            1D Numpy array with data values.
        """
        data_idx = self._get_data_idx(data_name)
        return self._adwin.get_full_data(data_idx)

    def set_data(self, data_name: str, first_index: int, value: np.ndarray | list[int] | list[float]) -> None:
        """Write values to a global Data array.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the data array.
            first_index: First index into the data array (>= 1).
            value: List of values to write to the data array.
        """
        data_idx = self._get_data_idx(data_name)
        self._adwin.set_data(data_idx, first_index, value)

    def get_fifo_filled(self, data_name: str) -> int:
        """Return the number of values waiting in the FIFO.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the data array (to look up in the Adwin configuration).

        Returns:
            Number of FIFO entries currently in use.
        """
        data_idx = self._get_data_idx(data_name)
        return self._adwin.get_fifo_filled(data_idx)

    def get_fifo_room(self, data_name: str) -> int:
        """Return the number of values that can be added to the FIFO without overflowing it.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the FIFO data array.

        Returns:
            Number of empty FIFO entries available.
        """
        data_idx = self._get_data_idx(data_name)
        return self._adwin.get_fifo_room(data_idx)

    def read_fifo(self, data_name: str, count: int) -> np.ndarray:
        """Read data from a global FIFO variable.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the FIFO data array.
            count: Number of values to read from the FIFO.

        Returns:
            1D Numpy array containing the FIFO elements.
        """
        data_idx = self._get_data_idx(data_name)
        return self._adwin.read_fifo(data_idx, count)

    def write_fifo(self, data_name: str, value: np.ndarray | list[int] | list[float]) -> None:
        """Write data to a global FIFO variable.

        Notes:
            Data name lookup is performed case-insensitive.

        Parameters:
            data_name: Name of the FIFO data array.
            value: Array of values to write to the FIFO.
        """
        data_idx = self._get_data_idx(data_name)
        self._adwin.write_fifo(data_idx, value)


class AdwinManager:
    """Provide convenient access to ADwin processes.

    An instance of this class manages the processes running on a specific ADwin instrument.
    """

    def __init__(self,
                 adwin: Adwin_Base,
                 program_library: AdwinProgramLibrary,
                 auto_load_programs: list[str]
                 ) -> None:
        self._adwin = adwin
        self._program_library = program_library
        self._auto_load_programs = auto_load_programs
        self._check_auto_load_processnrs()

    def _check_auto_load_processnrs(self) -> None:
        """Sanity check for process number conflicts among automatically loaded programs."""
        numbers_used: set[int] = set()
        program_names = set(self._program_library.list_programs())
        for program_name in self._auto_load_programs:
            if program_name not in program_names:
                raise ValueError(f"Unknown program {program_name!r} in auto_load_programs")
            program_info = self._program_library.get_program_info(program_name)
            if program_info.slot in numbers_used:
                raise ValueError(
                    f"Duplicate auto_load program in process slot number {program_info.slot} ({program_name})"
                )
            numbers_used.add(program_info.slot)

    def get_adwin(self) -> Adwin_Base:
        """Return the Adwin instrument driver used by this manager."""
        return self._adwin

    def get_program_library(self) -> AdwinProgramLibrary:
        """Return the Adwin program library used by this manager."""
        return self._program_library

    def reboot(self) -> None:
        """Reboot the Adwin system, clear data and restart programs.

        This function must be called after power-on, before communication
        with the Adwin is possible. This function may be called again
        to perform a full reset.

        This function boots the Adwin, removes all processes and data.
        It then loads the default processes as specified in the Adwin configuration.
        """
        self._adwin.reboot()
        self._adwin.check_ready()

        # Reload standard processes.
        for program_name in self._auto_load_programs:
            adwin_process = self.get_process(program_name)
            adwin_process.load()

    def list_programs(self) -> list[str]:
        """Return a list of available programs."""
        return self._program_library.list_programs()

    def get_process(self, program_name: str) -> AdwinProcess:
        """Get an `AdwinProcess` instance for the specified program."""
        program_info = self._program_library.get_program_info(program_name)
        return AdwinProcess(self._adwin, program_name, program_info)
