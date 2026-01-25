"""Instrument driver for the Zürich Instruments HDAWG."""

import enum
import logging
import json
import os.path
import re
import time
from typing import TYPE_CHECKING, Any

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_ApplicationException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method

import jsonschema  # type: ignore
import numpy as np

# Lazy import of the zhinst module. See the function _import_modules() below.
if TYPE_CHECKING:
    import zhinst.core
    import zhinst.utils
    from zhinst.core import ziDAQServer, AwgModule
else:
    zhinst = None
    ziDAQServer, AwgModule = None, None

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Sequencer code replacement variables must start with a literal $, followed by at least one letter followed by zero or
# more alphanumeric characters or underscores.
SEQC_PAR_PATTERN = re.compile(r"\$[A-Za-z][A-Za-z0-9_]*", re.ASCII)


def _import_modules() -> None:
    """Import the zhinst library.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global zhinst, ziDAQServer, AwgModule
    if zhinst is None:
        import zhinst
        import zhinst.core  # pylint: disable=W0621
        import zhinst.utils
        from zhinst.core import ziDAQServer, AwgModule

# Status enumerations.
class CompilerStatus(enum.IntEnum):
    """Enumeration of compiler process status."""
    NOT_READY = -1
    READY = 0
    READY_WITH_ERRORS = 1
    READY_WITH_WARNINGS = 2


class UploadStatus(enum.IntEnum):
    """Enumeration of ELF upload process status."""
    WAITING = -1
    DONE = 0
    FAILED = 1
    BUSY = 2


class ZurichInstruments_HDAWG(QMI_Instrument):
    """Instrument driver for the Zürich Instruments HDAWG.

    Attributes:
        COMPILE_TIMEOUT:      The default timeout for a program compilation.
        UPLOAD_TIMEOUT:       The default timeout for uploading a compiled program
        NUM_AWGS:             The number of AWG cores.
        NUM_CHANNELS:         The number of AWG channels.
        NUM_CHANNELS_PER_AWG: The number of AWG channels per AWG core.
    """

    _rpc_constants = ["COMPILE_TIMEOUT", "UPLOAD_TIMEOUT"]
    COMPILE_TIMEOUT = 30
    UPLOAD_TIMEOUT = 30
    # Class constants
    NUM_AWGS = 4
    NUM_CHANNELS = 8
    NUM_CHANNELS_PER_AWG = 2

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
        # Class attributes
        self._server_host = server_host
        self._server_port = server_port
        self._device_name = device_name
        # ZI HDAWG server, module and device
        self._daq_server: None | ziDAQServer = None
        self._awg_module: None | AwgModule = None

        # Import the "zhinst" module.
        _import_modules()

        # Flags
        self._last_compilation_successful = False

    @property
    def daq_server(self) -> ziDAQServer:
        assert self._daq_server is not None
        return self._daq_server

    @property
    def awg_module(self) -> AwgModule:
        assert self._awg_module is not None
        return self._awg_module

    @staticmethod
    def _process_parameter_replacements(sequencer_program: str, replacements: dict[str, str | int | float]) -> str:
        """Process parameter replacements for sequencer code.

        Parameters:
            sequencer_program: The sequencer code as a string.
            replacements:      The replacement items dictionary.

        Returns:
            sequencer_program: The sequencer code with the replacements.
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
            raise KeyError("Variables left in sequencer program that were not in replacement dictionary: {}".format(
                ', '.join(leftover_parameters)
            ))

        return sequencer_program

    @staticmethod
    def _check_program_not_empty(sequencer_program: str):
        """Check if the program is non-empty (compiler silently ignores empty programs)."""
        # Filter out lines that start with // or /* (comments) or are empty.
        seqc_statements = list(filter(
            lambda s: not (s.startswith("//") or s.startswith("/*") or len(s) == 0),
            [s.strip() for s in sequencer_program.split('\n')]
        ))

        # Check if there are any lines left (we do not check if that is executable code; the compiler will do that).
        if len(seqc_statements) == 0:
            raise QMI_ApplicationException("Source string does not contain executable statements")

    def _get_int(self, node_path: str) -> int:
        """Get an integer value from the nodetree.

        Parameters:
            node_path:      The path to the node to be queried.

        Returns:
            integer value from node tree.
        """
        return self.daq_server.getInt('/' + self._device_name + '/' + node_path)

    def _get_double(self, node_path: str) -> float:
        """Get a double value from the nodetree.

        Parameters:
            node_path:      The path to the node to be queried.

        Returns:
            double value from node tree.
        """
        return self.daq_server.getDouble('/' + self._device_name + '/' + node_path)

    def _get_string(self, node_path: str) -> str:
        """Get a string value from the nodetree.

        Parameters:
            node_path:      The path to the node to be queried.

        Returns:
            string value from node tree.
        """
        return self.daq_server.getString('/' + self._device_name + '/' + node_path)

    def _set_value(self, node_path: str, value: str | int | float) -> None:
        """Set a value in the nodetree. Can be a string, integer, or a floating point number.

        Parameters:
            node_path:      The path to the node to be queried.
            value:          Value to set for the node.
        """
        self.daq_server.set('/' + self._device_name + '/' + node_path, value)

    def _set_int(self, node_path: str, value: int) -> None:
        """Set an integer value in the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value:     Integer value to write.
        """
        self.daq_server.setInt('/' + self._device_name + '/' + node_path, value)

    def _set_double(self, node_path: str, value: float) -> None:
        """Set a floating point value in the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value:     Floating point value to write.
        """
        self.daq_server.setDouble('/' + self._device_name + '/' + node_path, value)

    def _wait_compile(self, sequencer_program: str) -> CompilerStatus:
        """Start a compilation of a sequencer program and wait until the compilation is done or timeout.

        Parameters:
            sequencer_program:  A sequencer program as a string.

        Raises:
            RuntimeError:       If the compilation does now within the 'self.COMPILE_TIMEOUT period.

        Returns:
            compilation_status: the obtained compiler status after compiler was finished.
        """
        # Compile the sequencer program with replacements made.
        self.awg_module.set("compiler/sourcestring", sequencer_program)

        # Poll the AWG module to check compilation progress.
        # See https://docs.zhinst.com/labone_api_user_manual/modules/awg/index.html for how to query
        # the progress. The program is uploaded automatically if the 'compiler/upload' parameter is set to 1.
        compilation_start_time = time.monotonic()
        _logger.debug("Compilation started ... ")
        compilation_status = CompilerStatus(self.awg_module.getInt("compiler/status"))
        while compilation_status == CompilerStatus.NOT_READY:
            time.sleep(0.1)
            compilation_status = CompilerStatus(self.awg_module.getInt("compiler/status"))
            if time.monotonic() - compilation_start_time > self.COMPILE_TIMEOUT:
                raise RuntimeError("Compilation process timed out (timeout={})".format(self.COMPILE_TIMEOUT))

        compilation_end_time = time.monotonic()
        _logger.debug(
            "Compilation finished in %.1f seconds (status=%d)",
            compilation_end_time - compilation_start_time,
            compilation_status
        )
        return compilation_status

    def _interpret_compilation_result_is_ok(self, compilation_result: CompilerStatus) -> bool:
        """Interpret compilation result.

        Parameters:
            compilation_result: The compilation result.

        Raises:
            ValueError: If the compiler result is unknown.

        Returns:
             ok_to_proceed: Result as True (OK) if compiler didn't return any errors, else False.
        """
        if compilation_result == CompilerStatus.READY:
            # Successful compilation; proceed.
            ok_to_proceed = True
        elif compilation_result == CompilerStatus.READY_WITH_ERRORS:
            # Compilation finished with errors.
            error_message = self.awg_module.getString("compiler/statusstring")
            _logger.error("Compilation finished with errors: %s", error_message)
            ok_to_proceed = False
        elif compilation_result == CompilerStatus.READY_WITH_WARNINGS:
            # Compilation finished with warnings.
            warning_message = self.awg_module.getString("compiler/statusstring")
            _logger.warning("Compilation finished with warnings: %s", warning_message)
            ok_to_proceed = True
        else:
            raise ValueError("Unknown compiler status: {}".format(compilation_result))

        return ok_to_proceed

    def _wait_upload(self) -> UploadStatus:
        """Poll ELF upload progress and return upload result.

        Raises:
            RuntimeError: If the upload does not finish with the 'self.UPLOAD_TIMEOUT' period.

        Returns:
            upload_status: The obtained upload status after upload was finished.
        """
        # Poll the AWG module to check ELF upload progress.
        upload_start_time = time.monotonic()
        _logger.debug("Polling ELF upload status ...")
        upload_progress = self.awg_module.getDouble("progress")
        upload_status = self.daq_server.getInt(f"/{self._device_name:s}/awgs/0/ready")
        while upload_progress < 1.0 and upload_status == 0:
            time.sleep(0.1)
            upload_progress = self.awg_module.getDouble("progress")
            upload_status = self.daq_server.getInt(f"/{self._device_name:s}/awgs/0/ready")
            if time.monotonic() - upload_start_time > self.UPLOAD_TIMEOUT:
                raise RuntimeError("Upload process timed out (timeout={})".format(self.UPLOAD_TIMEOUT))

        upload_end_time = time.monotonic()
        _logger.debug(
            "ELF upload finished in %.1f seconds (status=%d)", upload_end_time - upload_start_time, upload_status
        )
        upload_status = UploadStatus(self.awg_module.getInt("elf/status"))
        return upload_status

    def _interpret_upload_result_is_ok(self, upload_result: UploadStatus) -> bool:
        """Interpret upload result.

        Parameters:
            upload_result: The upload result.

        Raises:
            ValueError: If the upload result is unknown.

        Returns:
             ok_to_proceed: Result as True (OK) if upload was successful, else False.
        """

        self._check_is_open()

        if upload_result == UploadStatus.DONE:
            # Successful upload; proceed.
            ok_to_proceed = True
        elif upload_result == UploadStatus.FAILED:
            # Upload failed.
            _logger.error("ELF upload failed")
            ok_to_proceed = False
        elif upload_result == UploadStatus.BUSY:
            # Upload still in progress; we should never get here.
            _logger.error("ELF upload in progress but aborted for unknown reason.")
            ok_to_proceed = False
        else:
            raise ValueError("Unknown upload status: {}".format(upload_result))

        return ok_to_proceed

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        # This may fail!
        self._daq_server = ziDAQServer(self._server_host, self._server_port, api_level=6)

        # Connect to the device via Ethernet.
        # If the device is already connected, this is a no-op.
        self.daq_server.connectDevice(self._device_name, "1GbE")

        self._awg_module = self.daq_server.awgModule()

        self.awg_module.set("device", self._device_name)
        self.awg_module.set("index", 0)  # only support 1x8 mode, so only one AWG module

        # Verify that the AWG thread is not running.
        assert self.awg_module.finished()

        # Start the AWG thread.
        self.awg_module.execute()

        # Verify that the AWG thread is running.
        assert not self.awg_module.finished()

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()

        _logger.info("[%s] Closing connection to instrument", self._name)
        # Verify that the AWG thread is running.
        assert not self.awg_module.finished()

        # Stop the AWG module thread.
        self.awg_module.finish()

        # Verify that the AWG thread is no longer running.
        assert self.awg_module.finished()

        self._awg_module = None

        self.daq_server.disconnect()
        self._daq_server = None

        super().close()

    @rpc_method
    def get_node_string(self, node_path: str) -> str:
        """
        Get a string value for the node.

        Parameters:
            node_path:      The node to query.

        Returns:
            string value for the given node.
        """
        self._check_is_open()
        _logger.info("[%s] Getting string value for node [%s]", self._name, node_path)

        return self._get_string(node_path)

    @rpc_method
    def set_node_value(self, node_path: str, value: int | float | str) -> None:
        """Write a value to the device node tree.

        Requires LabOne version 21.08 or newer.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
            value:      Value to write.
        """
        self._set_value(node_path, value)

    @rpc_method
    def get_node_int(self, node_path: str) -> int:
        """Get an integer value in the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
        """
        return self._get_int(node_path)

    @rpc_method
    def set_node_int(self, node_path: str, value: int) -> None:
        """Set an integer value in the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value: Integer value to write.
        """
        self._set_int(node_path, value)

    @rpc_method
    def get_node_double(self, node_path: str) -> float:
        """Get a floating point value in the device node tree.

        Parameters:
            node_path:  Path in the device tree, relative to the "/devNNNN/" subtree.
        """
        return self._get_double(node_path)

    @rpc_method
    def set_node_double(self, node_path: str, value: float) -> None:
        """Set a floating point value in the device node tree.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value: Floating point value to write.
        """
        self._set_double(node_path, value)

    @rpc_method
    def set_channel_grouping(self, value: int) -> None:
        """Set the channel grouping of the device.

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
        self._set_int("system/awg/channelgrouping", value)

    @rpc_method
    def compile_and_upload(self,
                           sequencer_program: str,
                           replacements: None | dict[str, str | int | float] = None
                           ) -> None:
        """Compile and upload the sequencer_program, after performing textual replacements.

        This function combines compilation followed by upload to the AWG if compilation was successful. This is forced
        by the HDAWG API if the compiler/upload parameter is set to 1.

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
            replacements:      Optional dictionary of (parameter, value) pairs. Every occurrence of the parameter in
                               the sequencer program will be replaced with the specified value.
        """
        self._check_is_open()

        # Perform parameter replacements.
        if replacements is None:
            replacements = {}

        sequencer_program = self._process_parameter_replacements(sequencer_program, replacements)
        self._check_program_not_empty(sequencer_program)

        # Compile.
        compilation_result = self._wait_compile(sequencer_program)
        result_ok = self._interpret_compilation_result_is_ok(compilation_result)
        # Wait for the upload
        if result_ok:
            # Allow some time for upload to start.
            time.sleep(0.2)

            # Wait for upload to finish.
            upload_result = self._wait_upload()
            result_ok = self._interpret_upload_result_is_ok(upload_result)

        # Done; store result.
        self._last_compilation_successful = result_ok

    @rpc_method
    def compilation_successful(self) -> bool:
        """Query result of compilation process (sequence compilation and ELF upload).

        Note: this will only return a meaningful value after starting at least one compilation process. The method
        returns False if there was no previous compilation result.
        """
        return self._last_compilation_successful

    @rpc_method
    def upload_waveform(
        self,
        awg_index: int,
        waveform_index: int,
        wave1: np.ndarray,
        wave2: None | np.ndarray = None,
        markers: None | np.ndarray = None,
    ) -> None:
        """Upload new waveform data to the AWG.

        The AWG must be explicitly disabled by calling `set_awg_module_enabled(0)` before uploading waveforms,
        and re-enabled by calling `set_awg_module_enabled(1)` after uploading waveforms.

        A waveform array inside the AWG can hold interleaved data for up to 2 analog waveforms and 4 marker waveforms.
        If a waveform array contains multiple waveforms, these must all be uploaded together.

        The AWG compiler decides how "wave" variables are mapped to waveform array indexes.
        This can be inspected in the "Waveform Viewer" in the LabOne user interface.

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
        waveform_data = zhinst.utils.convert_awg_waveform(wave1, wave2, markers)
        waveform_address = f"/{self._device_name}/awgs/{awg_index}/waveform/waves/{waveform_index}"
        self.daq_server.setVector(waveform_address, waveform_data)

    @rpc_method
    def upload_waveforms(
        self,
        unpacked_waveforms: list[tuple[int, int, np.ndarray, None | np.ndarray, None | np.ndarray]],
        batch_size: int = 50,
    ) -> None:
        """Upload a set of new waveform data to the AWG. Works as singular waveform uploading, but creating a
        list of tuple sets of waveforms, and uploading all in one command, speeds up the upload significantly.

        Large sets of waveforms need to be batched to avoid running out of memory.

        Parameters:
            unpacked_waveforms: List of tuples, each tuple is a collection of awg_index, waveform sequence index,
                                wave1, wave2 and markers.
            batch_size:         Large sets of waveforms take plenty of memory. This makes the waveforms to be sent with
                                maximum sized batches. Default size is 50 waveform entries.
        """
        self._check_is_open()

        waves_set = []
        for wf_count, sequence in enumerate(unpacked_waveforms):
            awg_index, waveform_index, wave1, wave2, markers = sequence
            wave_raw = zhinst.utils.convert_awg_waveform(wave1, wave2, markers)
            waveform_address = f'/{self._device_name}/awgs/{awg_index}/waveform/waves/{waveform_index}'
            waves_set.append((waveform_address, wave_raw))
            # Check set size against batch size
            if wf_count % batch_size == batch_size - 1:
                # send a batch and reset list
                self.daq_server.set(waves_set)
                waves_set = []

        # Send also any possible remains of the last batch
        if len(waves_set):
            self.daq_server.set(waves_set)

    @rpc_method
    def upload_command_table(
            self, awg_index: int, command_table_entries: list[dict[str, Any]], save_as_file: bool = False
    ) -> None:
        """Upload a new command table to the AWG.

        Command tables are needed for using e.g. `assignWaveIndex` and must be uploaded before the sequencer program
        is executed. Do not upload while a program is running. Note that each core that is used by the sequencer
        script needs a valid command table and that grouped cores need the same command table. In 1x8 mode all 4
        cores thus need identical tables.

        This routine converts the list of entries to JSON and prepends the required headers before uploading.

        The resulting table is checked against the schema before uploading. The schema is loaded from the device.
        At the time of the writing this version of the driver, the schema is based on draft 7:
        https://json-schema.org/draft-07.

        Parameters:
            awg_index:              0-based index of the AWG core to apply the table to (0 .. 3).
            command_table_entries:  Actual command table as a list of entries (dicts).
            save_as_file:           Set to True to save the validated JSON command table in a file. Default is False.

        Raises:
            ValueError:   Invalid schema used (should not happen as it is obtained from the device).
            ValueError:   Validation of the command table failed.
            ValueError:   Invalid value in the command table despite successful validation.
            RuntimeError: If the upload of command table on core {awg_index} failed.
            RuntimeError: If the upload process timed out.
        """
        self._check_is_open()

        # Check AWG core index.
        if awg_index not in (0, 1, 2, 3):
            raise ValueError("AWG index must be in 0 .. 3")

        # Get schema from the device
        schema_node = f"/{self._device_name:s}/awgs/0/commandtable/schema"
        schema = json.loads(
            self.daq_server.get(schema_node, flat=True)[schema_node][0]["vector"]
        )
        # Create the command table from the provided entries.
        command_table = {
            "header": {
                "version": str(schema["version"])
            },
            "table": command_table_entries
        }
        # Validate the table against the schema.
        try:
            jsonschema.validate(instance=command_table, schema=schema, cls=jsonschema.Draft7Validator)
        except jsonschema.exceptions.SchemaError as exc:
            _logger.exception("The provided schema is invalid", exc_info=exc)
            raise ValueError("Invalid schema") from exc
        except jsonschema.exceptions.ValidationError as exc:
            _logger.exception("The provided command table is not valid", exc_info=exc)
            raise ValueError("Invalid command table") from exc

        # Convert the command table to JSON and upload.
        try:
            command_table_as_json = json.dumps(command_table, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid value in command table") from exc

        if save_as_file:
            with open(f"{os.path.dirname(__file__)}/cmd_table_{awg_index}.json", "w") as out:
                out.write(command_table_as_json)

        self.daq_server.setVector(
            "/{}/awgs/{}/commandtable/data".format(self._device_name, awg_index),
            command_table_as_json
        )
        upload_start_time = time.monotonic()
        while True:
            time.sleep(0.01)
            status = self.daq_server.getInt(f"/{self._device_name:s}/awgs/{awg_index}/commandtable/status")
            if status & 0b1:
                # Upload successful, move on the next core
                break
            if status & 0b1000:
                # Error in command table
                raise RuntimeError(f"The upload of command table on core {awg_index} failed.")

            if time.monotonic() - upload_start_time > self.UPLOAD_TIMEOUT:
                raise RuntimeError("Upload process timed out (timeout={})".format(self.UPLOAD_TIMEOUT))

        upload_end_time = time.monotonic()
        _logger.debug(
            "Command Table upload finished in %.1f seconds (status=%d)",
            upload_end_time - upload_start_time,
            status
        )

    @rpc_method
    def sync(self) -> None:
        """Synchronise the state of the AWG.

        This call ensures that all previous settings have taken effect on the instrument, and stale data is flushed
        from local buffers. The sync is performed for all devices connected to the DAQ server.
        """
        self._check_is_open()
        _logger.info("[%s] Synchronising state of AWG", self._name)
        self.daq_server.sync()

    @rpc_method
    def set_reference_clock_source(self, value: int) -> None:
        """Set the clock to be used as the frequency and timebase reference.

        Parameters:
            value:  Clock source to select.
                    0 - internal reference clock;
                    1 - external 10MHz or 100MHz reference clock;
                    2 - a ZSync clock.

        Raises:
            ValueError: By invalid reference clock source input parameter.
        """
        if value not in (0, 1, 2):
            raise ValueError("Unsupported reference clock source")

        self._check_is_open()
        _logger.info("[%s] Setting reference clock source to [%d]", self._name, value)
        self._set_int("system/clocks/referenceclock/source", value)

    @rpc_method
    def get_reference_clock_status(self) -> int:
        """Return the status of the reference clock.

        Returns:
            0: The reference clock is locked.
            1: There was an error locking to the reference clock.
            2: The device is busy locking to the reference clock.
        """
        self._check_is_open()
        _logger.info("[%s] Getting status of reference clock", self._name)
        return self._get_int("system/clocks/referenceclock/status")

    @rpc_method
    def set_sample_clock_frequency(self, frequency: float) -> None:
        """Set the base sample clock frequency.

        Changing the sample clock temporarily interrupts the AWG sequencers.

        Parameters:
            frequency: New base sample clock frequency in Hz (range 100.0e6 to 2.4e9).
        """
        self._check_is_open()
        _logger.info("[%s] Setting sample clock frequency to [%d]", self._name, frequency)
        self._set_double("system/clocks/sampleclock/freq", frequency)

    @rpc_method
    def get_sample_clock_status(self) -> int:
        """Get the status of the sample clock.

        Returns:
            0: The sample clock is valid and locked.
            1: There was an error adjusting the sample clock.
            2: The device is busy adjusting the sample clock.
        """
        self._check_is_open()
        _logger.info("[%s] Getting status of sample clock", self._name)
        return self._get_int("system/clocks/sampleclock/status")

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

        Raises:
            ValueError: By invalid trigger index value.
            ValueError: By invalid marker source value.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        if value not in range(16) and value not in (17, 18):
            raise ValueError("Invalid marker source: {}".format(value))

        self._check_is_open()
        self._set_int("triggers/out/{}/source".format(trigger), value)

    @rpc_method
    def set_marker_delay(self, trigger: int, value: float) -> None:
        """Set the output delay for a specific marker output.

        Trigger delay, controls the fine delay of the trigger output. The resolution is 78 ps.

        Parameters:
            trigger: Marker index in the range 0 to 7, corresponding to marker outputs 1 to 8 on the front panel.
            value:   Delay in seconds.

        Raises:
            ValueError: By invalid trigger index value.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")

        self._check_is_open()
        self._set_double("triggers/out/{}/delay".format(trigger), value)

    @rpc_method
    def set_trigger_level(self, trigger: int, value: float) -> None:
        """Set the trigger voltage level for a specific trigger input.

        Parameters:
            trigger: Trigger index in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.
            value:   Trigger level in Volt, range -10.0 to +10.0 exclusive.

        Raises:
            ValueError: By invalid trigger index value.
            ValueError: By invalid trigger level value.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        if not -10.0 < value < 10.0:
            raise ValueError("Invalid trigger level")

        self._check_is_open()
        self._set_double("triggers/in/{}/level".format(trigger), value)

    @rpc_method
    def set_trigger_impedance(self, trigger: int, value: int) -> None:
        """Set the input impedance of a specific trigger input.

        Parameters:
            trigger: Trigger index in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.
            value:   Impedance setting. 0 = 1 kOhm; 1 = 50 Ohm.

        Raises:
            ValueError: By invalid trigger index value.
            ValueError: By invalid trigger impedance setting.
        """
        if trigger < 0 or trigger >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger index")
        if value not in (0, 1):
            raise ValueError("Invalid impedance setting")

        self._check_is_open()
        _logger.info(
            "[%s] Setting trigger impedance of channel [%d] to [%s]",
            self._name,
            trigger,
            "50 Ohm" if value else "1 kOhm",
        )
        self._set_int("triggers/in/{}/imp50".format(trigger), value)

    @rpc_method
    def set_dig_trigger_source(self, awg: int, trigger: int, value: int) -> None:
        """Select the source of a specific digital trigger channel.

        There are two digital trigger channels which can be accessed in the
        sequencer program via calls to "waitDigTrigger()" and "playWaveDigTrigger()".

        Parameters:
            awg:     AWG module index (must be 0 in 1x8 channel mode).
            trigger: Digital trigger index in the range 0 to 1, corresponding to digital triggers 1 and 2.
            value:   Trigger source in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: Digital trigger index is invalid.
            ValueError: Trigger source value is invalid.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if trigger < 0 or trigger > 1:
            raise ValueError("Invalid digital trigger index")
        if value < 0 or value >= self.NUM_CHANNELS:
            raise ValueError("Invalid trigger source")

        self._check_is_open()
        self._set_int("awgs/{}/auxtriggers/{}/channel".format(awg, trigger), value)

    @rpc_method
    def set_dig_trigger_slope(self, awg: int, trigger: int, value: int) -> None:
        """Set the trigger slope of a specific digital trigger channel.

        There are two digital trigger channels which can be accessed in the
        sequencer program vi calls to "waitDigTrigger()" and "playWaveDigTrigger()".

        Parameters:
            awg:     AWG module index (must be 0 in 1x8 channel mode).
            trigger: Digital trigger index in the range 0 to 1, corresponding to digital triggers 1 and 2.
            value:   Trigger slope.
                     0 - level sensitive (trigger on high signal);
                     1 - trigger on rising edge;
                     2 - trigger on falling edge;
                     3 - trigger on rising and falling edge.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: Digital trigger index is invalid.
            ValueError: Trigger slope value is invalid.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if trigger < 0 or trigger > 1:
            raise ValueError("Invalid digital trigger index")
        if value < 0 or value > 3:
            raise ValueError("Invalid trigger slope")

        self._check_is_open()
        self._set_int("awgs/{}/auxtriggers/{}/slope".format(awg, trigger), value)

    @rpc_method
    def get_output_amplitude(self, awg: int, channel: int) -> float:
        """Get the output amplitude scaling factor of the specified channel.

        Parameters:
            awg:     AWG module index in the range 0 to 3. The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: AWG channel number is invalid.

        Returns:
            amplitude: A dimensionless scaling factor applied to the digital signal.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")

        self._check_is_open()
        return self._get_double(f"awgs/{awg}/outputs/{channel}/amplitude")

    @rpc_method
    def set_output_amplitude(self, awg: int, channel: int, value: float) -> None:
        """Set the output scaling factor of the specified channel.

        The amplitude is a dimensionless scaling factor applied to the digital signal.

        Parameters:
            awg:     AWG module index in the range 0 to 3. The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.
            value:   Amplitude scale factor.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: AWG channel number is invalid.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")

        self._check_is_open()
        self._set_double("awgs/{}/outputs/{}/amplitude".format(awg, channel), value)

    @rpc_method
    def get_output_channel_hold(self, awg: int, channel: int) -> int:
        """Get whether the last sample is held for the specified channel.

        Parameters:
            awg:     AWG module index in the range 0 to 3. The AWG index selects a pair of output channels.
                     Index 0 selects output channels 1 and 2, index 1 selects channels 2 and 3 etc.
            channel: Channel index in the range 0 to 1, selecting the first or second output channel
                     within the selected channel pair.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: AWG channel number is invalid.

        Returns:
            0: If last sample is not held.
            1: If last sample is held.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")

        self._check_is_open()
        return self._get_int(f"awgs/{awg}/outputs/{channel}/hold")

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

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: AWG channel number is invalid.
            ValueError: Invalid hold state value.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if channel < 0 or channel >= self.NUM_CHANNELS_PER_AWG:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid hold state")

        self._check_is_open()
        self._set_int(f"awgs/{awg}/outputs/{channel}/hold", value)

    @rpc_method
    def get_output_channel_on(self, output_channel: int) -> int:
        """Get the specified wave output channel state.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.

        Returns:
            channel_state: 0 = output off, 1 = output on.

        Raises:
            ValueError: Output channel number is invalid.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")

        self._check_is_open()
        return self._get_int("sigouts/{}/on".format(output_channel))

    @rpc_method
    def set_output_channel_on(self, output_channel: int, value: int) -> None:
        """Set the specified wave output channel on or off.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Output state; 0 = output off, 1 = output on.

        Raises:
            ValueError: Output channel number is invalid.
            ValueError: Invalid output channel state value.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid on/off state")

        self._check_is_open()
        self._set_int("sigouts/{}/on".format(output_channel), value)

    @rpc_method
    def set_output_channel_range(self, output_channel: int, value: float) -> None:
        """Set voltage range of the specified wave output channel.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Output range in Volt. The instrument selects the next higher available range.

        Raises:
            ValueError: Output channel number is invalid.
            ValueError: Voltage range is invalid.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value < 0 or value > 5.0:
            raise ValueError("Invalid output range")

        self._check_is_open()
        self._set_double("sigouts/{}/range".format(output_channel), value)

    @rpc_method
    def set_output_channel_offset(self, output_channel: int, value: float) -> None:
        """Set the DC offset voltage for the specified wave output channel.

        The DC offset is only active in amplified mode, not in direct mode.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Offset in Volt, in range -1.25 to +1.25 V.

        Raises:
            ValueError: Output channel number is invalid.
            ValueError: Voltage offset is invalid.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if not -1.25 <= value <= 1.25:
            raise ValueError("Invalid offset value")

        self._check_is_open()
        self._set_double("sigouts/{}/offset".format(output_channel), value)

    @rpc_method
    def get_output_channel_delay(self, output_channel: int) -> float:
        """Return output delay for fine alignment of the specified wave output channel.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.

        Raises:
            ValueError: Output channel number is invalid.

        Returns:
            Delay in seconds.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")

        self._check_is_open()
        return self._get_double("sigouts/{}/delay".format(output_channel))

    @rpc_method
    def set_output_channel_delay(self, output_channel: int, value: float) -> None:
        """Set output delay for fine alignment of the specified wave output channel.

        Changing the delay setting may take several seconds.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          Delay in seconds, range 0 to 26e-9.

        Raises:
            ValueError: Output channel number is invalid.
            ValueError: Delay value is invalid.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if not 0 <= value < 26e-9:
            raise ValueError("Invalid delay setting")

        self._check_is_open()
        self._set_double("sigouts/{}/delay".format(output_channel), value)

    @rpc_method
    def set_output_channel_direct(self, output_channel: int, value: int) -> None:
        """Enable or disable the direct output path for the specified wave output channel.

        The direct output path bypasses the output amplifier and offset circuits,
        and fixes the output range to 800 mV.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          1 to enable the direct output path, 0 to disable.

        Raises:
            ValueError: Output channel number is invalid.
            ValueError: Direct value is invalid.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid value")

        self._check_is_open()
        self._set_int("sigouts/{}/direct".format(output_channel), value)

    @rpc_method
    def set_output_channel_filter(self, output_channel: int, value: int) -> None:
        """Enable or disable the analog output filter for the specified wave output channel.

        Parameters:
            output_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:          1 to enable the output filter, 0 to disable.

        Raises:
            ValueError: Output channel number is invalid.
            ValueError: Filter value is invalid.
        """
        if output_channel < 0 or output_channel >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")
        if value not in (0, 1):
            raise ValueError("Invalid value")

        self._check_is_open()
        self._set_int("sigouts/{}/filter".format(output_channel), value)

    @rpc_method
    def set_dio_mode(self, mode: int) -> None:
        """Set the DIO control mode.

        Available modes are:
            0: manual - control of DIO bits via LabOne user interface.
            1: awg_sequencer_commands - control of DIO bits from sequencer code and forward set values to sequencer
                                        (interface synced to 150 MHz).
            2: dio_codeword - same as (1), but interface is synced to 50 MHz.
            3: qccs - map DIO onto ZSync interface and make it available to the sequencer.

        Parameters:
            mode:   mode to use (0, 1, 2 or 3).

        Raises:
            ValueError: If mode is not valid.
        """
        if not 0 <= mode <= 3:
            raise ValueError("Invalid DIO mode")

        self._check_is_open()
        self._set_int("dios/0/mode", mode)

    @rpc_method
    def set_dio_drive(self, mask: int) -> None:
        """Define input/output direction of DIO signals.

        Parameters:
            mask:   4-bit mask where each bit configures the direction of
                    a group of 8 DIO signals. Bit value 0 sets the DIO signals
                    to input mode, value 1 sets the signals to output mode.
                    Bit 0 corresponds to the least significant byte of the DIO bus, etc.

        Raises:
            ValueError: If DIO signals direction mask is not valid.
        """
        if not 0 <= mask <= 15:
            raise ValueError("Invalid value for mask")

        self._check_is_open()
        self._set_int("dios/0/drive", mask)

    @rpc_method
    def set_dio_strobe_index(self, awg: int, value: int) -> None:
        """Select the DIO index to be used as a trigger for playback.

        The sequencer program uses this trigger by calling "playWaveDIO()".

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            value:  DIO bit index in the range 0 to 31.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: DIO bit index is invalid.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if value < 0 or value > 31:
            raise ValueError("Invalid DIO bit index")

        self._check_is_open()
        self._set_int("awgs/{}/dio/strobe/index".format(awg), value)

    @rpc_method
    def set_dio_strobe_slope(self, awg: int, value: int) -> None:
        """Select the signal edge that should activate the strobe trigger.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            value:  Slope type.
                    0 - off;
                    1 - trigger on rising edge;
                    2 - trigger on falling edge;
                    3 - trigger on rising and falling edge.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: DIO strobe slope value is invalid.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if value < 0 or value > 3:
            raise ValueError("Invalid slope")

        self._check_is_open()
        self._set_int("awgs/{}/dio/strobe/slope".format(awg), value)

    @rpc_method
    def get_user_register(self, awg: int, reg: int) -> int:
        """Return the value of the specified user register.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            reg:    Register index in the range 0 to 15.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: Register index is invalid.

        Returns:
            value: User register value.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if not 0 <= reg <= 15:
            raise ValueError("Invalid register index")

        self._check_is_open()
        return self._get_int("awgs/{}/userregs/{}".format(awg, reg))

    @rpc_method
    def set_user_register(self, awg: int, reg: int, value: int) -> None:
        """Change the value of the specified user register.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).
            reg:    Register index in the range 0 to 15.
            value:  Integer value to write to the register.

        Raises:
            ValueError: AWG index number is invalid.
            ValueError: Register index is invalid.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")
        if not 0 <= reg <= 15:
            raise ValueError("Invalid register index")

        self._check_is_open()
        self._set_int("awgs/{}/userregs/{}".format(awg, reg), value)

    @rpc_method
    def get_awg_module_enabled(self, awg: int) -> int:
        """Return the current enable status of the AWG module.

        Parameters:
            awg:    AWG module index (must be 0 in 1x8 channel mode).

        Raises:
            ValueError: AWG index number is invalid.

        Returns:
            1 - If the AWG sequencer is currently running.
            0 - If the AWG sequencer is not running.
        """
        if awg < 0 or awg >= self.NUM_AWGS:
            raise ValueError("Invalid AWG index")

        self._check_is_open()
        return self._get_int("awgs/{}/enable".format(awg))

    @rpc_method
    def set_awg_module_enabled(self, value: int) -> None:
        """Enable or disable the AWG module.

        Enabling the AWG starts execution of the currently loaded sequencer program.
        Uploading a sequencer program or waveform is only possible while the AWG module is disabled.

        Parameters:
            value: 1 to enable the AWG module, 0 to disable.

        Raises:
            ValueError: AWG module enable value is invalid.
        """
        if value not in (0, 1):
            raise ValueError("Invalid value")

        self._check_is_open()
        self.awg_module.set("awg/enable", value)
