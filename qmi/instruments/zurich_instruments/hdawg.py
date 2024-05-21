"""Instrument driver for the Zürich Instruments HDAWG."""

import enum
import logging
import json
import re
import time
import typing
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple, Any

import jsonschema  # type: ignore
import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method


# Lazy import of the zhinst module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    import zhinst.core
    import zhinst.utils
else:
    zhinst = None


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def _import_modules() -> None:
    """
    Import the zhinst library.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global zhinst
    if zhinst is None:
        import zhinst.ziPython  # pylint: disable=W0621
        import zhinst.utils


# Compile and upload timeout in seconds.
_COMPILE_TIMEOUT = 30
_UPLOAD_TIMEOUT = 30

# Location of the default command table schema
_THIS_MODULE_PATH = Path(__file__).resolve()
_DEFAULT_CT_TABLE_SCHEMA_FILENAME = "hdawg_command_table.schema"
_DEFAULT_CT_TABLE_SCHEMA_PATH = Path(_THIS_MODULE_PATH.parent, _DEFAULT_CT_TABLE_SCHEMA_FILENAME)

# Sequencer code replacement variables must start with a literal $, followed by at least one letter followed by zero or
# more alphanumeric characters or underscores.
SEQC_PAR_PATTERN = re.compile(r"\$[A-Za-z][A-Za-z0-9_]*", re.ASCII)


# Status enumerations.
class CompilerStatus(enum.IntEnum):
    """Enumeration of compiler process status."""

    IDLE = -1
    SUCCESS = 0
    FAILED = 1
    COMPLETED_WITH_WARNINGS = 2


class UploadStatus(enum.IntEnum):
    """Enumeration of ELF upload process status."""

    WAITING = -1
    DONE = 0
    FAILED = 1
    BUSY = 2


class ZurichInstruments_HDAWG(QMI_Instrument):
    """Instrument driver for the Zürich Instruments HDAWG."""

    NUM_AWGS = 4
    NUM_CHANNELS = 8
    NUM_CHANNELS_PER_AWG = 2

    CONNECTION_INTERFACE = "1GbE"  # For Ethernet and USB the connection interface is 1GbE

    # Node paths
    AWG_DEVICE = "awgModule/device"
    AWG_INDEX = "awgModule/index"
    AWG_COMPILER_SOURCE_STRING = "awgModule/compiler/sourcestring"
    AWG_COMPILER_STATUS = "awgModule/compiler/status"
    AWG_COMPILER_STATUS_STRING = "awgModule/compiler/status"
    AWG_ELF_STATUS = "awgModule/elf/status"
    AWG_PROGRESS = "awgModule/progress"

    def __init__(self, context: QMI_Context, name: str, server_host: str, server_port: int, device_name: str) -> None:
        """Initialize driver.

        We connect to a specific HDAWG via a Data Server, which is a process running on some computer.

        Parameters:
            name:           Name for this instrument instance.
            server_host:    Host where the ziDataServer process is running.
            server_port:    TCP port there the ziDataServer process can be reached.
            device_name:    Name of the HDAWG device (typically "devNNNN").
        """
        super().__init__(context, name)

        self._server_host = server_host
        self._server_port = server_port
        self._device_name = device_name

        self._daq_server: zhinst.ziPython.ziDAQServer
        self._awg_module: zhinst.ziPython.AwgModule

        self._last_compilation_successful = False

        # Import the "zhinst" module.
        _import_modules()

    def _check_data_server_exists(self) -> None:
        """
        Check if the Zurich Instrument data server exists.

        Raises:
            QMI_InstrumentException if no data server was connected.
        """
        if not self._daq_server:
            raise QMI_InstrumentException("Could not connect to Zurich Instruments Data Server")

    def _check_awg_module_exists(self) -> None:
        """
        Check if the AwgModule exists.

        Raises:
            QMI_InstrumentException if no AwgModule exists.
        """
        if not self._awg_module:
            raise QMI_InstrumentException("Could not create an AwgModule")

        assert self._awg_module is not None

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        # Connect to Zurich Instruments Data Server
        self._daq_server = zhinst.core.ziDAQServer(self._server_host, self._server_port, 6)

        self._check_data_server_exists()

        # Connect to the device via Ethernet.
        self._daq_server.connectDevice(self._device_name, "1GbE")

        # Create an AwgModule object
        self._awg_module = self._daq_server.awgModule()

        self._check_awg_module_exists()

        # Set the target device for the AWG sequencer programs
        self._awg_module.set(self.AWG_DEVICE, self._device_name)
        self._awg_module.set(self.AWG_INDEX, 0)  # only support 1x8 mode, so only one AWG module

        # Verify that the AWG thread is not running.
        if not self._awg_module.finished():
            raise QMI_InstrumentException("AWG thread still running")

        # Start the AWG thread.
        self._awg_module.execute()

        # Verify that the AWG thread is running.
        if self._awg_module.finished():
            raise QMI_InstrumentException("AWG thread not running")

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        self._check_awg_module_exists()

        _logger.info("[%s] Closing connection to instrument", self._name)
        # Verify that the AWG thread is running.
        if self._awg_module.finished():
            raise QMI_InstrumentException("AWG thread not running")

        # Stop the AWG module thread.
        self._awg_module.finish()

        # Verify that the AWG thread is no longer running.
        if not self._awg_module.finished():
            raise QMI_InstrumentException("AWG thread still running")

        self._check_data_server_exists()
        self._daq_server.disconnect()

        super().close()

    def _set_dev_value(self, node_path: str, value: Union[int, float, str]) -> None:
        """Set an arbitrary value in the the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
            value:      Value to write.
        """
        self._check_data_server_exists()
        self._daq_server.set("/" + self._device_name + "/" + node_path, value)

    def _set_dev_int(self, node_path: str, value: int) -> None:
        """Set an integer value in the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
            value:      Integer value to write.
        """
        self._check_data_server_exists()
        self._daq_server.setInt("/" + self._device_name + "/" + node_path, value)

    def _set_dev_double(self, node_path: str, value: float) -> None:
        """Set a floating point value in the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
            value:      Floating point value to write.
        """
        self._check_data_server_exists()
        self._daq_server.setDouble("/" + self._device_name + "/" + node_path, value)

    def _get_dev_int(self, node_path: str) -> int:
        """Return an integer value from the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
        """
        self._check_data_server_exists()
        return self._daq_server.getInt("/" + self._device_name + "/" + node_path)

    def _get_dev_double(self, node_path: str) -> float:
        """Return a floating point value from the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
        """
        self._check_data_server_exists()
        return self._daq_server.getDouble("/" + self._device_name + "/" + node_path)

    @staticmethod
    def _process_parameter_replacements(
        sequencer_program: str, replacements: Dict[str, Union[str, int, float]]
    ) -> str:
        """
        Process parameter replacements for sequencer code.

        Parameters:
            sequencer_program:  Sequencer program to process.
            replacements:       Dictionary of replacements.

        Returns:
            sequencer program with repelacements
        """
        for parameter, replacement in replacements.items():
            # Convert replacements to "str".
            if isinstance(replacement, (int, float)):
                replacement = repr(replacement)

            # At this point, the replacement value should be a string.
            if not isinstance(replacement, str):
                raise ValueError("Cannot handle replacement value of type {!r}".format(type(replacement)))

            # Perform the replacement.
            if SEQC_PAR_PATTERN.fullmatch(parameter):
                # Replace parameter, respecting word boundaries only (note: '$' is already a word boundary)
                parameter_pattern = f"\\{parameter}\\b"  # escape the '$' and add word boundary match
                sequencer_program = re.sub(parameter_pattern, replacement, sequencer_program)
            else:
                raise NameError("Replacement parameter has an invalid name: {}".format(parameter))

        # Check if there are any unreplaced parameters left in the source code; this will not compile.
        leftover_parameters = SEQC_PAR_PATTERN.findall(sequencer_program)
        if leftover_parameters:
            raise KeyError(
                "Variables left in sequencer program that were not in replacement dictionary: {}".format(
                    ", ".join(leftover_parameters)
                )
            )

        return sequencer_program

    @staticmethod
    def _check_program_not_empty(sequencer_program: str) -> None:
        """
        Check if the program is non-empty (compiler silently ignores empty programs).

        Parameters:
            sequencer_program:  Sequencer program to check.
        """
        # Filter out lines that start with // or /* (comments) or are empty.
        seqc_statements = list(
            filter(
                lambda s: not (s.startswith("//") or s.startswith("/*") or len(s) == 0),
                [s.strip() for s in sequencer_program.split("\n")],
            )
        )

        # Check if there are any lines left (we do not check if that is executable code; the compiler will do that).
        if len(seqc_statements) == 0:
            raise ValueError("Source string does not contain executable statements")

    def _wait_compile(self, sequencer_program: str) -> CompilerStatus:
        """
        Start a compilation of a sequencer program.

        Parameters:
            sequencer_program:  Sequencer program to check.

        Returns:
            compilation status
        """

        self._check_is_open()
        self._check_awg_module_exists()

        # Compile the sequencer program with replacements made.
        self._awg_module.set(self.AWG_COMPILER_SOURCE_STRING, sequencer_program)

        # Poll the AWG module to check if compilation progress.
        # See https://docs.zhinst.com/labone_programming_manual/awg_module.html#_awg_module_parameters for how to query
        # the progress.
        compilation_start_time = time.monotonic()
        _logger.debug("Compilation started ... ")
        compilation_status = CompilerStatus(self._awg_module.getInt(self.AWG_COMPILER_STATUS))
        while compilation_status == CompilerStatus.IDLE:
            time.sleep(0.1)
            compilation_status = CompilerStatus(self._awg_module.getInt(self.AWG_COMPILER_STATUS))
            if time.monotonic() - compilation_start_time > _COMPILE_TIMEOUT:
                raise RuntimeError("Compilation process timed out (timeout={})".format(_COMPILE_TIMEOUT))
        compilation_end_time = time.monotonic()
        _logger.debug(
            "Compilation finished in %.1f seconds (status=%d)",
            compilation_end_time - compilation_start_time,
            compilation_status,
        )

        return compilation_status

    def _wait_upload(self) -> UploadStatus:
        """
        Poll ELF upload progress and check result.

        Returns:
            Upload status.
        """

        self._check_is_open()
        self._check_awg_module_exists()

        # Poll the AWG module to check ELF upload progress.
        upload_start_time = time.monotonic()
        _logger.debug("Polling ELF upload status ...")
        upload_progress = self._awg_module.getDouble(self.AWG_PROGRESS)
        upload_status = UploadStatus(self._awg_module.getInt(self.AWG_ELF_STATUS))
        while upload_progress < 1.0 and upload_status in (UploadStatus.WAITING, UploadStatus.DONE, UploadStatus.BUSY):
            time.sleep(0.1)
            upload_progress = self._awg_module.getDouble(self.AWG_PROGRESS)
            upload_status = UploadStatus(self._awg_module.getInt(self.AWG_ELF_STATUS))
            if time.monotonic() - upload_start_time > _UPLOAD_TIMEOUT:
                raise RuntimeError("Upload process timed out (timeout={})".format(_UPLOAD_TIMEOUT))
        upload_end_time = time.monotonic()
        _logger.debug(
            "ELF upload finished in %.1f seconds (status=%d)", upload_end_time - upload_start_time, upload_status
        )

        return upload_status

    def _interpret_compilation_result_is_ok(self, compilation_result: CompilerStatus) -> bool:
        """
        Interpret compilation result.

        Parameters:
            compilation_result: Result of the compilation.

        Returns:
            True if compilation succeed, else False.

        Raises:
            ValueError if the CompilerStatus is not one of READY, READY_WITH_ERRORS, READY_WITH_WARNINGS
        """

        self._check_is_open()
        self._check_awg_module_exists()

        if compilation_result == CompilerStatus.SUCCESS:
            return True
        elif compilation_result == CompilerStatus.FAILED:
            error_message = self._awg_module.getString(self.AWG_COMPILER_STATUS_STRING)
            _logger.error("Compilation finished with errors: %s", error_message)
            return False
        elif compilation_result == CompilerStatus.COMPLETED_WITH_WARNINGS:
            warning_message = self._awg_module.getString(self.AWG_COMPILER_STATUS_STRING)
            _logger.warning("Compilation finished with warnings: %s", warning_message)
            return False
        else:
            raise ValueError("Unknown compiler status: {}".format(compilation_result))

    def _interpret_upload_result_is_ok(self, upload_result: UploadStatus) -> bool:
        """
        Interpret upload result.

        Parameters:
            upload_result: Result of the upload.

        Returns:
            True if compilation succeed, else False.

        Raises:
            ValueError if the UploadStatus is not one of DONE, FAILED, BUSY
        """

        self._check_is_open()
        self._check_awg_module_exists()

        if upload_result == UploadStatus.DONE:
            return True
        elif upload_result == UploadStatus.FAILED:
            _logger.error("ELF upload failed")
            return False
        elif upload_result == UploadStatus.BUSY:
            _logger.error("ELF upload in progress but aborted for unknown reason.")
            return False
        else:
            raise ValueError("Unknown upload status: {}".format(upload_result))

    @rpc_method
    def set_node_value(self, node_path: str, value: Union[int, float, str]) -> None:
        """
        Write an arbitrary value to the device node tree.

        Requires LabOne version 21.08 or newer.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
            value:      Value to write.
        """
        self._set_dev_value(node_path, value)

    @rpc_method
    def get_node_int(self, node_path: str) -> int:
        """
        Get an integer value in the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.

        Returns:
            integer value for node.
        """
        return self._get_dev_int(node_path)

    @rpc_method
    def set_node_int(self, node_path: str, value: int) -> None:
        """
        Set an integer value in the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value: Integer value to write.
        """
        self._set_dev_int(node_path, value)

    @rpc_method
    def get_node_double(self, node_path: str) -> float:
        """
        Get a floating point value in the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.

        Returns:
            floating point value for node.
        """
        return self._get_dev_double(node_path)

    @rpc_method
    def set_node_double(self, node_path: str, value: float) -> None:
        """Set a floating point value in the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value: Floating point value to write.
        """
        self._set_dev_double(node_path, value)

    @rpc_method
    def compile_and_upload(
        self, sequencer_program: str, replacements: Optional[Dict[str, Union[str, int, float]]] = None
    ) -> None:
        """Compile and upload the sequencer_program, after performing textual replacements.

        This function combines compilation followed by upload to the AWG if compilation was successful. This is forced
        by the HDAWG API.

        Notes on parameter replacements:
         - Parameters must adhere to the following format: $[A-Za-z][A-Za-z0-9]+ (literal $, followed by at least one
            letter followed by zero or more alphanumeric characters or underscores). Both the key in the replacements
            dictionary and the parameter reference in the sequencer code must adhere to this format.
         - Replacement respects word boundaries. The inclusion of the '$' allows to concatenate values in the sequencer
            program code, e.g. "wave w = "$TYPE$LENGTH;" to achieve "wave w = "sin1024";", but be careful that you
            don't accidentally create new parameters by concatenation.
         - Replacement values must be of type str, int or float.

        Parameters:
            sequencer_program: Full text of the sequencer script.
            replacements: Optional dictionary of (parameter, value) pairs. Every occurrence of the parameter in the
                          sequencer program will be replaced  with the specified value.
        """

        self._check_is_open()
        self._check_awg_module_exists()

        # Perform parameter replacements.
        if replacements is None:
            replacements = {}
        sequencer_program = self._process_parameter_replacements(sequencer_program, replacements)
        self._check_program_not_empty(sequencer_program)

        # Compile.
        compilation_result = self._wait_compile(sequencer_program)
        result = self._interpret_compilation_result_is_ok(compilation_result)
        if result:
            # Allow some time for upload to start.
            time.sleep(1.0)

            # Wait for upload to finish.
            upload_result = self._wait_upload()
            result = self._interpret_upload_result_is_ok(upload_result)

        # Store result.
        self._last_compilation_successful = result

    @rpc_method
    def compilation_successful(self) -> bool:
        """
        Query result of compilation process (sequence compilation and ELF upload).

        Note: this will only return a meaningful value after starting at least one compilation process. The method
        returns False if there was no previous compilation result.

        Returns:
            True if the compilation was successful, else False.
        """
        return self._last_compilation_successful

    @rpc_method
    def upload_waveform(
        self,
        awg_index: int,
        waveform_index: int,
        wave1: np.ndarray,
        wave2: Optional[np.ndarray] = None,
        markers: Optional[np.ndarray] = None,
    ) -> None:
        """
        Upload new waveform data to the AWG.

        The AWG must be explicitly disabled by calling `set_awg_module_enabled(0)`
        before uploading waveforms, and re-enabled by calling
        `set_awg_module_enabled(1)` after uploading waveforms.

        A waveform array inside the AWG can hold interleaved data
        for up to 2 analog waveforms and 4 marker waveforms.
        If a waveform array contains multiple waveforms, these must
        all be uploaded together.

        The AWG compiler decides how "wave" variables are mapped
        to waveform array indexes. This can be inspected in the
        "Waveform Viewer" in the LabOne user interface.

        Parameters:
            awg_index:       0-based index of the AWG (group of 2 channels).
            waveform_index:  0-based index of the waveform array.
            wave1:           Array containing floating point samples
                             in range -1.0 .. +1.0 for the first waveform.
            wave2:           Array containing floating point samples
                             in range -1.0 .. +1.0 for the second waveform.
            markers:         Array containing integer values where
                             the 4 least significant bits of each sample
                             represent the 4 marker channels.
        """
        self._check_is_open()
        self._check_data_server_exists()
        waveform_data = zhinst.utils.convert_awg_waveform(wave1, wave2, markers)
        waveform_address = f"/{self._device_name}/awgs/{awg_index}/waveform/waves/{waveform_index}"
        self._daq_server.setVector(waveform_address, waveform_data)

    @rpc_method
    def upload_waveforms(
        self,
        unpacked_waveforms: List[Tuple[int, int, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]],
        batch_size: int = 50,
    ) -> None:
        """Upload a set of new waveform data to the AWG. Works as singular waveform uploading, but creating a
        list of tuple sets of waveforms, and uploading all in one command, speeds up the upload significantly.

        Large sets of waveforms need to be batched to avoid running out of memory.

        Parameters:
            unpacked_waveforms: List of Tuples, each tuple is a collection of awg_index, waveform sequence index,
                wave1, wave2 and markers.
            batch_size: Large sets of waveforms take plenty of memory. This makes the waveforms to be sent with
                maximum sized batches. Default size is 50 waveform entries.
        """
        self._check_is_open()
        self._check_data_server_exists()

        waves_set = []
        for wf_count, sequence in enumerate(unpacked_waveforms):
            awg_index, waveform_index, wave1, wave2, markers = sequence
            wave_raw = zhinst.utils.convert_awg_waveform(wave1, wave2, markers)
            waveform_address = f"/{self._device_name}/awgs/{awg_index}/waveform/waves/{waveform_index}"
            waves_set.append((waveform_address, wave_raw))
            # Check set size against batch size
            if wf_count % batch_size == batch_size - 1:
                # send a batch and reset list
                self._daq_server.set(waves_set)
                waves_set = []

        # Send also any possible remains of the last batch
        if len(waves_set):
            self._daq_server.set(waves_set)

    @rpc_method
    def upload_command_table(self, awg_index: int, command_table_entries: List[Dict[str, Any]]) -> None:
        """
        Upload a new command table to the AWG.

        Command tables are needed for using e.g. `assignWaveIndex` and must be uploaded before the sequencer program
        is executed. Do not upload while a program is running. Note that each core that is used by the sequencer
        script needs a valid command table and that grouped cores need the same command table. In 1x8 mode all 4
        cores thus need identical tables.

        This routine converts the list of entries to JSON and prepends the required headers before uploading.

        The resulting table is checked against the schema before uploading. A copy of the schema is included with this
        driver and used by default; the original is available at https://docs.zhinst.com/hdawg/commandtable/v2/schema
        (note: the version on the website of Zurich instruments has a https:// URI and a # (anchor) at the end of the
        $schema attribute, which is not recognised by the jsonschema implementation for Python. The version of the
        file included here has this fixed (see also https://github.com/Julian/jsonschema/issues/569)).

        Parameters:
            awg_index:              0-based index of the AWG core to apply the table to (0 .. 3).
            command_table_entries:  actual command table as a list of entries (dicts).
        """
        self._check_is_open()
        self._check_data_server_exists()

        # Check AWG core index.
        if awg_index not in (0, 1, 2, 3):
            raise ValueError("AWG index must be in 0 .. 3")

        # Create the command table from the provided entries.
        command_table = {
            "$schema": "http://docs.zhinst.com/hdawg/commandtable/v2/schema",
            "header": {"version": "0.2"},
            "table": command_table_entries,
        }

        # Load the validation schema.
        validation_schema_file = _DEFAULT_CT_TABLE_SCHEMA_PATH
        try:
            with open(validation_schema_file, "r") as fhandle:
                validation_schema = json.load(fhandle)
        except json.JSONDecodeError as exc:
            _logger.exception("Error in decoding validation schema", exc_info=exc)
            raise ValueError("Invalid JSON") from exc

        # Validate the table against the schema.
        try:
            jsonschema.validate(command_table, schema=validation_schema)
        except jsonschema.exceptions.SchemaError as exc:
            _logger.exception("The provided schema is invalid", exc_info=exc)
            raise ValueError("Invalid schema") from exc
        except jsonschema.exceptions.ValidationError as exc:
            _logger.exception("The provided command table is not valid", exc_info=exc)
            raise ValueError("Invalid command table") from exc

        # Convert the command table to JSON and upload.
        try:
            command_table_as_json = json.dumps(command_table, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid value in command table") from exc

        self._daq_server.setVector(
            "/{}/awgs/{}/commandtable/data".format(self._device_name, awg_index), command_table_as_json
        )

    @rpc_method
    def sync(self) -> None:
        """
        Synchronize the state of the AWG.

        This call ensures that all previous settings have taken effect on
        the instrument, and stale data is flushed from local buffers.
        """
        self._check_is_open()
        assert self._daq_server is not None
        self._daq_server.sync()

    @rpc_method
    def set_channel_grouping(self, value: int) -> None:
        """
        Set the channel grouping of the device.

        This QMI driver currently supports only channel grouping 2 (1x8 channels).

        Parameters:
            value:  Channel grouping to set.
                    0 = 4x2 channels;
                    1 = 2x4 channels;
                    2 = 1x8 channels.
        """
        if value != 2:
            raise ValueError("Unsupported channel grouping")
        self._check_is_open()
        self._set_dev_int("system/awg/channelgrouping", value)

    @rpc_method
    def set_reference_clock_source(self, value: int) -> None:
        """Enable or disable the use of an external reference clock source.

        Parameters:
            value:  Clock source to select.
                    0 = internal reference clock;
                    1 = external 10 MHz reference clock.
        """
        if value not in (0, 1):
            raise ValueError("Unsupported reference clock source")
        self._check_is_open()
        self._set_dev_int("system/clocks/referenceclock/source", value)

    @rpc_method
    def get_reference_clock_status(self) -> int:
        """Return the status of the reference clock.

        Returns:
            0 if the reference clock is locked;
            1 if there was an error locking to the reference clock;
            2 if the device is busy locking to the reference clock.
        """
        self._check_is_open()
        return self._get_dev_int("system/clocks/referenceclock/status")

    @rpc_method
    def set_sample_clock_frequency(self, value: float) -> None:
        """Change the base sample clock frequency.

        Changing the sample clock temporarily interrupts the AWG sequencers.

        Parameters:
            value: New base sample clock frequency in Hz (range 100.0e6 to 2.4e9).
        """
        self._check_is_open()
        self._set_dev_double("system/clocks/sampleclock/freq", value)

    @rpc_method
    def get_sample_clock_status(self) -> int:
        """Return the status of the sample clock.

        Returns:
            0 if the sample clock is valid and locked;
            1 if there was an error adjusting the sample clock;
            2 if the device is busy adjusting the sample clock.
        """
        self._check_is_open()
        return self._get_dev_int("system/clocks/sampleclock/status")

    @rpc_method
    def set_trigger_impedance(self, trigger: int, value: int) -> None:
        """Set the input impedance of a specific trigger input.

        Parameters:
            trigger: Trigger index in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.
            value:   Impedance setting.
                     0 = 1 kOhm;
                     1 = 50 Ohm.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        if value not in (0, 1):
            raise ValueError("Invalid impedance setting")
        self._check_is_open()
        self._set_dev_int("triggers/in/{}/imp50".format(trigger), value)

    @rpc_method
    def set_trigger_level(self, trigger: int, value: float) -> None:
        """Set the trigger voltage level for a specific trigger input.

        Parameters:
            trigger: Trigger index in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.
            value:   Trigger level in Volt, range -10.0 to +10.0 exclusive.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        if not -10.0 < value < 10.0:
            raise ValueError("Invalid trigger level")
        self._check_is_open()
        self._set_dev_double("triggers/in/{}/level".format(trigger), value)

    @rpc_method
    def set_marker_source(self, trigger: int, value: int) -> None:
        """Select the source for a specific marker output.

        Four types of marker sources are supported.
        Values 0 to 3 select internal signals called "AWG Trigger 1" to "AWG Trigger 4".
        These signals are controlled by the sequencer program via explicit calls to "setTrigger()".

        Values 4 to 7 select marker bits from a currently playing waveform.
        To understand the mapping of marker bits to marker channels, consider channels to be grouped
        into pairs. A specific marker output port can only access marker bits from a waveform that
        is playing within the same channel pair.
        Value 4 selects marker bit 1 of the waveform playing on the first channel of the pair.
        Value 5 selects marker bit 2 of the first channel.
        Value 6 selects marker bit 1 of the second channel.
        Value 7 selects marker bit 2 of the second channel.

        Values 8 to 15 select the external trigger signals from trigger inputs 1 to 8.

        Value 17 sets the marker output to a constant high level.
        Value 18 sets the marker output to a constant low level.

        Parameters:
            trigger: Marker index in the range 0 to 7, corresponding to marker outputs 1 to 8 on the front panel.
            value:   Selected marker source as defined above.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        if value not in range(16) and value not in (17, 18):
            raise ValueError("Invalid marker source: {}".format(value))
        self._check_is_open()
        self._set_dev_int("triggers/out/{}/source".format(trigger), value)

    @rpc_method
    def set_marker_delay(self, trigger: int, value: float) -> None:
        """Set the output delay for a specific marker output.

        Trigger delay, controls the fine delay of the trigger output. The resolution is 78 ps.

        Parameters:
            trigger: Marker index in the range 0 to 7, corresponding to marker outputs 1 to 8 on the front panel.
            value:   Delay in seconds.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        self._check_is_open()
        self._set_dev_double("triggers/out/{}/delay".format(trigger), value)

    @rpc_method
    def set_dig_trigger_source(self, awg: int, trigger: int, value: int) -> None:
        """Select the source of a specific digital trigger channel.

        There are two digital trigger channels which can be acccessed in the
        sequencer program via calls to "waitDigTrigger()" and "playWaveDigTrigger()".

        Parameters:
            awg:     AWG module index (must be 0 in 1x8 channel mode).
            trigger: Digital trigger index in the range 0 to 1, corresponding to digital triggers 1 and 2.
            value:   Trigger source in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if trigger < 0 or trigger > 1:
            raise ValueError("Invalid digital trigger index")
        if value < 0 or value >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger source")
        self._check_is_open()
        self._set_dev_int("awgs/{}/auxtriggers/{}/channel".format(awg, trigger), value)

    @rpc_method
    def set_dig_trigger_slope(self, awg: int, trigger: int, value: int) -> None:
        """Set the trigger slope of a specific digital trigger channel.

        There are two digital trigger channels which can be acccessed in the
        sequencer program vi calls to "waitDigTrigger()" and "playWaveDigTrigger()".

        Parameters:
            awg:     AWG module index (must be 0 in 1x8 channel mode).
            trigger: Digital trigger index in the range 0 to 1, corresponding to digital triggers 1 and 2.
            value:   Trigger slope.
                     0 = level sensitive (trigger on high signal);
                     1 = trigger on rising edge;
                     2 = trigger on falling edge;
                     3 = trigger on rising and falling edge.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if trigger < 0 or trigger > 1:
            raise ValueError("Invalid digital trigger index")
        if value < 0 or value > 3:
            raise ValueError("Invalid trigger slope")
        self._check_is_open()
        self._set_dev_int("awgs/{}/auxtriggers/{}/slope".format(awg, trigger), value)

    @rpc_method
    def get_output_amplitude(self, awg: int, channel: int) -> float:
        """Get the output scaling factor of the specified channel.

        Parameters:
            awg:     AWG module index in the range 0 to 3.
                     The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.
        Returns:
            The output scaling factor, which is a dimensionless scaling factor applied to the digital signal.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")
        self._check_is_open()
        return self._get_dev_double(f"awgs/{awg}/outputs/{channel}/amplitude")

    @rpc_method
    def set_output_amplitude(self, awg: int, channel: int, value: float) -> None:
        """Set the output scaling factor of the specified channel.

        The amplitude is a dimensionless scaling factor applied to the digital signal.

        Parameters:
            awg:     AWG module index in the range 0 to 3.
                     The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.
            value:   Amplitude scale factor.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")
        self._check_is_open()
        self._set_dev_double("awgs/{}/outputs/{}/amplitude".format(awg, channel), value)

    @rpc_method
    def get_output_channel_hold(self, awg: int, channel: int) -> int:
        """Get whether the last sample is held for the specified channel.

        Parameters:
            awg:     AWG module index in the range 0 to 3.
                     The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.
        Returns:
            0 if not last sample is not held;
            1 if last sample is held.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")
        self._check_is_open()
        return self._get_dev_int(f"awgs/{awg}/outputs/{channel}/hold")

    @rpc_method
    def set_output_channel_hold(self, awg: int, channel: int, value: int) -> None:
        """Set whether the last sample should be held for the specified channel.

        Parameters:
            awg:     AWG module index in the range 0 to 3.
                     The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.
            value:   Hold state; 0 = False, 1 = True.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid hold state")
        self._check_is_open()
        self._set_dev_int(f"awgs/{awg}/outputs/{channel}/hold", value)

    @rpc_method
    def get_output_channel_on(self, output_channel: int) -> int:
        """Get the specified wave output channel state: 0 = output off, 1 = output on.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        self._check_is_open()
        return self._get_dev_int("sigouts/{}/on".format(output_channel))

    @rpc_method
    def set_output_channel_on(self, output_channel: int, value: int) -> None:
        """Set the specified wave output channel on or off.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Output state; 0 = output off, 1 = output on.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid on/off state")
        self._check_is_open()
        self._set_dev_int("sigouts/{}/on".format(output_channel), value)

    @rpc_method
    def set_output_channel_range(self, output_channel: int, value: float) -> None:
        """Set output voltage range of the specified wave output channel.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Output range in Volt. The instrument selects the next higher available range.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value < 0 or value > 5.0:
            raise ValueError("Invalid output range")
        self._check_is_open()
        self._set_dev_double("sigouts/{}/range".format(output_channel), value)

    @rpc_method
    def set_output_channel_offset(self, output_channel: int, value: float) -> None:
        """Set the DC offset voltage for the specified wave output channel.

        The DC offset is only active in amplified mode, not in direct mode.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Offset in Volt, in range -1.25 to +1.25 V.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if not -1.25 <= value <= 1.25:
            raise ValueError("Invalid offset value")
        self._check_is_open()
        self._set_dev_double("sigouts/{}/offset".format(output_channel), value)

    @rpc_method
    def get_output_channel_delay(self, output_channel: int) -> float:
        """Return output delay for fine alignment of the the specified wave output channel.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.

        Returns:
            Delay in seconds.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        self._check_is_open()
        return self._get_dev_double("sigouts/{}/delay".format(output_channel))

    @rpc_method
    def set_output_channel_delay(self, output_channel: int, value: float) -> None:
        """Set output delay for fine alignment of the the specified wave output channel.

        Changing the delay setting may take several seconds.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Delay in seconds, range 0 to 26e-9.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if not 0 <= value < 26e-9:
            raise ValueError("Invalid delay setting")
        self._check_is_open()
        self._set_dev_double("sigouts/{}/delay".format(output_channel), value)

    @rpc_method
    def set_output_channel_direct(self, output_channel: int, value: int) -> None:
        """Enable or disable the direct output path for the specified wave output channel.

        The direct output path bypasses the output amplifier and offset circuits,
        and fixes the output range to 800 mV.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          1 to enable the direct output path, 0 to disable.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid value")
        self._check_is_open()
        self._set_dev_int("sigouts/{}/direct".format(output_channel), value)

    @rpc_method
    def set_output_channel_filter(self, output_channel: int, value: int) -> None:
        """Enable or disable the analog output filter for the specified wave output channel.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          1 to enable the output filter, 0 to disable.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid value")
        self._check_is_open()
        self._set_dev_int("sigouts/{}/filter".format(output_channel), value)

    @rpc_method
    def set_dio_mode(self, mode: int) -> None:
        """Set the DIO control mode.

        Available mode are:
            0: manual:                  control of DIO bits via LabOne user interface.
            1: awg_sequencer_commands:  control of DIO bits from sequencer code and forward set values to sequencer
                                        (interface synced to 150 MHz).
            2: dio_codeword             same as (1), but interface is synced to 50 MHz.
            3: qccs                     map DIO onto ZSync interface and make it available to the sequencer.

        Parameters:
            mode:   mode to use (0, 1, 2 or 3).
        """
        if not 0 <= mode <= 3:
            raise ValueError("Invalid DIO mode")
        self._check_is_open()
        self._set_dev_int("dios/0/mode", mode)

    @rpc_method
    def set_dio_drive(self, mask: int) -> None:
        """Define input/output direction of DIO signals.

        Parameters:
            mask:   4-bit mask where each bit configures the direction of
                    a group of 8 DIO signals. Bit value 0 sets the DIO signals
                    to input mode, value 1 sets the signals to output mode.
                    Bit 0 corresponds to the least significant byte of the DIO bus, etc.
        """
        if not 0 <= mask <= 15:
            raise ValueError("Invalid value for mask")
        self._check_is_open()
        self._set_dev_int("dios/0/drive", mask)

    @rpc_method
    def set_dio_strobe_index(self, awg: int, value: int) -> None:
        """Select the DIO index to be used as a trigger for playback.

        The sequencer program uses this trigger by calling "playWaveDIO()".

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            value:  DIO bit index in the range 0 to 31.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if value < 0 or value > 31:
            raise ValueError("Invalid DIO bit index")
        self._check_is_open()
        self._set_dev_int("awgs/{}/dio/strobe/index".format(awg), value)

    @rpc_method
    def set_dio_strobe_slope(self, awg: int, value: int) -> None:
        """Select the signal edge that should activate the strobe trigger.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            value:  Slope type.
                    0 = off;
                    1 = trigger on rising edge;
                    2 = trigger on falling edge;
                    3 = trigger on rising and falling edge.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if value < 0 or value > 3:
            raise ValueError("Invalid slope")
        self._check_is_open()
        self._set_dev_int("awgs/{}/dio/strobe/slope".format(awg), value)

    @rpc_method
    def get_user_register(self, awg: int, reg: int) -> int:
        """Return the value of the specified user register.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            reg:    Register index in the range 0 to 15.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if not 0 <= reg <= 15:
            raise ValueError("Invalid register index")
        self._check_is_open()
        return self._get_dev_int("awgs/{}/userregs/{}".format(awg, reg))

    @rpc_method
    def set_user_register(self, awg: int, reg: int, value: int) -> None:
        """Change the value of the specified user register.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            reg:    Register index in the range 0 to 15.
            value:  Integer value to write to the register.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if not 0 <= reg <= 15:
            raise ValueError("Invalid register index")
        self._check_is_open()
        self._set_dev_int("awgs/{}/userregs/{}".format(awg, reg), value)

    @rpc_method
    def get_awg_module_enabled(self, awg: int) -> int:
        """Return the current enable status of the AWG module.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).

        Returns:
            1 if the AWG sequencer is currently running;
            0 if the AWG sequencer is not running.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        self._check_is_open()
        return self._get_dev_int("awgs/{}/enable".format(awg))

    @rpc_method
    def set_awg_module_enabled(self, value: int) -> None:
        """Enable or disable the AWG module.

        Enabling the AWG starts execution of the currently loaded sequencer program.
        Uploading a sequencer program or waveform is only possible while the AWG module is disabled.

        Parameters:
            value: 1 to enable the AWG module, 0 to disable.
        """
        if value not in (0, 1):
            raise ValueError("Invalid value")
        self._check_is_open()
        assert self._awg_module is not None
        self._awg_module.set("awgModule/awg/enable", value)

    # Obsolete method names for backward compatibility.
    setChannelGrouping = set_channel_grouping
    setReferenceClockSource = set_reference_clock_source
    setTriggerImpedance = set_trigger_impedance
    setTriggerSource = set_marker_source
    setAuxTriggerSlope = set_dig_trigger_slope
    setOutputAmplitude = set_output_amplitude
    setOutputChannelOn = set_output_channel_on
    setOutputChannelRange = set_output_channel_range
    setDioDrive = set_dio_drive
    setDioStrobeIndex = set_dio_strobe_index
    setDioStrobeSlope = set_dio_strobe_slope
    setUserRegister = set_user_register
    setAwgModuleEnabled = set_awg_module_enabled
