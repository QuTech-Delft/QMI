"""Instrument driver for the Zürich Instruments HDAWG."""

import enum
import logging
import json
import os.path
import re
import time
from typing import TYPE_CHECKING, Any, cast
import warnings

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_ApplicationException, QMI_RuntimeException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

import jsonschema  # type: ignore
import numpy as np

# Lazy import of the zhinst module. See the function _import_modules() below.
if TYPE_CHECKING:
    import zhinst
    import zhinst.core
    import zhinst.toolkit
    import zhinst.toolkit.driver
    import zhinst.toolkit.driver.nodes.awg as awg
    import zhinst.toolkit.exceptions
    import zhinst.utils
    from zhinst.core import ziDAQServer
    from zhinst.toolkit import Waveforms
    from zhinst.toolkit.driver.devices import HDAWG
    from zhinst.toolkit.driver.modules.base_module import ZIModule
else:
    zhinst, awg = None, None
    ziDAQServer, HDAWG, Waveforms, ZIModule = None, None, None, None

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Sequencer code replacement variables must start with a literal $, followed by at least one letter followed by zero or
# more alphanumeric characters or underscores.
SEQC_PAR_PATTERN = re.compile(r"\$[A-Za-z][A-Za-z0-9_]*", re.ASCII)
# The possible parameter table entries.
PARAMETERS_TABLE = {
    "waveform": [
        "index", "length", "samplingRateDivider", "awgChannel0", "awgChannel1", "precompClear", "playZero",
        "playHold"
    ],
    "phase0": ["value", "increment"],
    "phase1": ["value", "increment"],
    "amplitude0": ["value", "increment", "register"],
    "amplitude1": ["value", "increment", "register"],
}


def _import_modules() -> None:
    """Import the zhinst library.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global zhinst, awg, ziDAQServer, Waveforms, HDAWG, ZIModule
    if zhinst is None:
        import zhinst
        import zhinst.core
        import zhinst.toolkit
        import zhinst.toolkit.driver
        import zhinst.toolkit.driver.nodes.awg as awg
        import zhinst.toolkit.exceptions
        import zhinst.utils
        from zhinst.core import ziDAQServer
        from zhinst.toolkit import Waveforms
        from zhinst.toolkit.driver.devices import HDAWG
        from zhinst.toolkit.driver.modules.base_module import ZIModule


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
        COMPILE_TIMEOUT:      The default timeout in seconds for a program compilation.
        UPLOAD_TIMEOUT:       The default timeout in seconds for uploading a compiled program.
        POLL_PERIOD:          The polling period in seconds for poll wait loops.
        NUM_AWGS:             The number of AWG cores.
        NUM_CHANNELS:         The number of AWG channels.
        TRIGGER_LEVEL_RANGE:  The range of possible settable trigger levels.
    """

    _rpc_constants = ["COMPILE_TIMEOUT", "UPLOAD_TIMEOUT", "POLL_PERIOD", "NUM_AWGS", "NUM_CHANNELS"]
    COMPILE_TIMEOUT = 30
    UPLOAD_TIMEOUT = 30
    POLL_PERIOD = 1.0
    NUM_AWGS = 4
    NUM_CHANNELS = 8
    # Class constants
    TRIGGER_LEVEL_RANGE = (-10, 10)

    def __init__(
        self, context: QMI_Context, name: str, server_host: str, server_port: int, device_name: str, grouping: int = 2
    ) -> None:
        """Initialize the driver.

        Parameters:
            name:        Name for this instrument instance.
            server_host: Host where the ZI data server process is running.
            server_port: TCP port there the ZI data server process can be reached.
            device_name: Name of the HDAWG device (typically "devNNNN").
            grouping:    The grouping to use. Options are 0 (4x2), 1 (2x4) and 2 (1x8, default).
        """
        if grouping not in range(3):
            raise ValueError(f"Invalid grouping number: {grouping}")

        super().__init__(context, name)
        # Class attributes
        self._server_host = server_host
        self._server_port = server_port
        self._device_name = device_name
        self._grouping = grouping
        # ZI HDAWG server, module and device
        self._daq_server: None | ziDAQServer = None
        self._awg_module: None | ZIModule = None
        self._device: None | HDAWG = None

        # Import the "zhinst" modules.
        _import_modules()

        # Create mapping
        self._awg_channel_map: list[awg.AWG] = []

        # Connect to Zurich Instruments Data Server
        self._session = zhinst.toolkit.Session(self._server_host, self._server_port)

        # Flags
        self._last_compilation_successful = False

    @property
    def daq_server(self) -> "ziDAQServer":
        assert self._daq_server is not None
        return self._daq_server

    @property
    def awg_module(self) -> "ZIModule":
        assert self._awg_module is not None
        return self._awg_module

    @property
    def device(self) -> "HDAWG":
        assert self._device is not None
        return self._device

    @property
    def awg_channel_map(self) -> "list[awg.AWG]":
        """Channel map for AWG channels to correct AWG node|core, based on channel range 0-7."""
        return [
            self.device.awgs[awg_channel // 2] for awg_channel in range(self.NUM_CHANNELS)
        ]

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
    def _add_command_table_entries(
            command_table: "zhinst.toolkit.CommandTable", command_table_entries: list[dict[str, Any]]
    ) -> "zhinst.toolkit.CommandTable":
        """A method to add new command table entries to the 'CommandTable.table' object in the new zhinst.toolkit way.
        To strictly comply with schema, no possibility of simple dictionary update or such has been made available.

        Parameters:
            command_table:         A 'CommandTable' object, preferably obtained from the node itself.
            command_table_entries: A list of indexed entries which should get added to the command table.

        Returns:
            command_table: The updated command table.
        """
        # Create the command table from the provided entries.
        for entry in command_table_entries:
            e = command_table.table[entry["index"]]
            for parameter, values in PARAMETERS_TABLE.items():
                if parameter in entry:
                    for value in values:
                        if value in entry[parameter]:
                            setattr(getattr(e, parameter), value, entry[parameter][value])

        return command_table

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

    @staticmethod
    def _control_waveform_inputs(
        markers: None | np.ndarray, wave1: np.ndarray, wave2: None | np.ndarray
    ) -> tuple[np.ndarray, ...]:
        """Helper function to turn 'None' inputs into zero arrays or in case of wave2, into
        the wave 1's imaginary part if wave 1 is an array of complex numbers."""
        if markers is None:
            markers = np.zeros(wave1.shape)
        if wave2 is None:
            if np.iscomplexobj(wave1):
                wave1, wave2 = wave1.real, wave1.imag

            else:
                wave2 = np.zeros(wave1.shape)

        return markers, wave1, wave2

    def _get_int(self, node_path: str, awg_channel: None | int = None) -> int:
        """Get an integer value from the nodetree.

        Parameters:
            node_path:   The path to the node to be queried.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.

        Returns:
            integer: Value from node tree.
        """
        if not node_path.startswith(f"/{self._device_name}"):
            node_path = f"/{self._device_name}/{node_path}".replace("//", "/")

        if awg_channel is not None:
            awg_node = self.awg_channel_map[awg_channel]
            return awg_node.root.connection.getInt(node_path)

        return self.daq_server.getInt(node_path)

    def _get_double(self, node_path: str, awg_channel: None | int = None) -> float:
        """Get a double value from the nodetree.

        Parameters:
            node_path:   The path to the node to be queried.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.

        Returns:
            double: Value from node tree.
        """
        if not node_path.startswith(f"/{self._device_name}"):
            node_path = f"/{self._device_name}/{node_path}".replace("//", "/")

        if awg_channel is not None:
            awg_node = self.awg_channel_map[awg_channel]
            return awg_node.root.connection.getDouble(node_path)

        return self.daq_server.getDouble(node_path)

    def _get_string(self, node_path: str, awg_channel: None | int = None) -> str:
        """Get a string value from the nodetree.

        Parameters:
            node_path:   The path to the node to be queried.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.

        Returns:
            string: Value from node tree.
        """
        if not node_path.startswith(f"/{self._device_name}"):
            node_path = f"/{self._device_name}/{node_path}".replace("//", "/")

        if awg_channel is not None:
            awg_node = self.awg_channel_map[awg_channel]
            return awg_node.root.connection.getString(node_path)

        return self.daq_server.getString(node_path)

    def _set_value(self, node_path: str, value: str | int | float, awg_channel: None | int = None) -> None:
        """Set a value in the nodetree. Can be a string, integer, or a floating point number.

        Parameters:
            node_path:   The path to the node to be queried.
            value:       Value to set for the node.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        if not node_path.startswith(f"/{self._device_name}"):
            node_path = f"/{self._device_name}/{node_path}".replace("//", "/")

        if awg_channel is not None:
            awg_node = self.awg_channel_map[awg_channel]
            awg_node.root.connection.set(node_path, value)
            return

        self.daq_server.set(node_path, value)

    def _set_int(self, node_path: str, value: int, awg_channel: None | int = None) -> None:
        """Set an integer value in the device node tree.

        Parameters:
            node_path:   Path in the device tree, relative to the "/devNNNN/" subtree.
            value:       Integer value to write.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        if not node_path.startswith(f"/{self._device_name}"):
            node_path = f"/{self._device_name}/{node_path}".replace("//", "/")

        if awg_channel is not None:
            awg_node = self.awg_channel_map[awg_channel]
            awg_node.root.connection.set(node_path, value)
            return

        self.daq_server.setInt(node_path, value)

    def _set_double(self, node_path: str, value: float, awg_channel: None | int = None) -> None:
        """Set a floating point value in the device node tree.

        Parameters:
            node_path:   Path in the device tree, relative to the "/devNNNN/" subtree.
            value:       Floating point value to write.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        if not node_path.startswith(f"/{self._device_name}"):
            node_path = f"/{self._device_name}/{node_path}".replace("//", "/")

        if awg_channel is not None:
            awg_node = self.awg_channel_map[awg_channel]
            awg_node.root.connection.set(node_path, value)
            return

        self.daq_server.setDouble(node_path, value)

    def _wait_compile(self) -> CompilerStatus:
        """Wait until the compilation is done or timeout. See also
        https://docs.zhinst.com/labone_api_user_manual/modules/awg/index.html
        for how to query the progress.

        Parameters:
            sequencer_program:  A sequencer program as a string.

        Raises:
            RuntimeError:       If the compilation does not finish within the 'self.COMPILE_TIMEOUT' period.

        Returns:
            compilation_status: The obtained compiler status after compiler was finished.
        """
        # Poll the AWG module to check compilation progress.
        compilation_start_time = time.monotonic()
        _logger.debug("Compilation started ... ")
        compilation_status = CompilerStatus(self.awg_module.getInt("compiler/status"))
        while compilation_status == CompilerStatus.NOT_READY:
            time.sleep(self.POLL_PERIOD)
            compilation_status = CompilerStatus(self.awg_module.getInt("compiler/status"))
            if time.monotonic() - compilation_start_time > self.COMPILE_TIMEOUT:
                raise QMI_TimeoutException(f"Compilation process timed out (timeout={self.COMPILE_TIMEOUT})")

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
            RuntimeError: If the upload does not finish within the 'self.UPLOAD_TIMEOUT' period.

        Returns:
            upload_status: The obtained upload status after upload was finished.
        """
        # Poll the AWG module to check ELF upload progress.
        upload_start_time = time.monotonic()
        _logger.debug("Polling ELF upload status ...")
        upload_status = UploadStatus(self.awg_module.getInt("elf/status"))
        while upload_status == 2:
            time.sleep(self.POLL_PERIOD)
            upload_status = UploadStatus(self.awg_module.getInt("elf/status"))
            upload_progress = self.awg_module.getDouble("progress")
            if time.monotonic() - upload_start_time > self.UPLOAD_TIMEOUT:
                raise QMI_TimeoutException(
                    f"Upload process timed out (timeout={self.UPLOAD_TIMEOUT}) at {upload_progress * 100}%"
                )

        upload_end_time = time.monotonic()
        _logger.debug(
            "ELF upload finished in %.1f seconds (status=%d)", upload_end_time - upload_start_time, upload_status
        )
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
            _logger.error("ELF upload failed.")
            ok_to_proceed = False
        elif upload_result == UploadStatus.BUSY:
            # Upload still in progress; we should never get here.
            _logger.error("ELF upload in progress but aborted for unknown reason.")
            ok_to_proceed = False
        elif upload_result == UploadStatus.WAITING:
            _logger.error("ELF upload not in progress.")
            ok_to_proceed = False
        else:
            raise ValueError(f"Unknown upload status: {upload_result}")

        return ok_to_proceed

    @rpc_method
    def open(self) -> None:
        """We connect to a specific HDAWG via a DAQ Server, which is a process running on some computer."""

        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        self._daq_server = self._session.daq_server

        # Connect to the device.
        self._device = cast(HDAWG, self._session.connect_device(self._device_name))
        self._awg_module = self._session.modules.awg.raw_module

        self.awg_module.set("device", self._device_name)
        super().open()
        # Set the core YxZ channels grouping
        self.set_channel_grouping(self._grouping)
        self.awg_module.set("index", 0)  # Set initially as 0, 0 is valid for all grouping modes.
        self.awg_module.execute()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()

        _logger.info("[%s] Closing connection to instrument", self._name)
        # Check if the AWG thread is running.
        if not self.awg_module.finished():
            # Stop the AWG module thread.
            self.awg_module.finish()

        # Verify that the AWG thread is no longer running.
        assert self.awg_module.finished()
        self._awg_module = None

        self._session.disconnect_device(self._device_name)
        self._daq_server = None

        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        version_info = self.daq_server.get("/zi/about/version")["zi"]["about"]["version"]
        return QMI_InstrumentIdentification(
            vendor="Zurich Instruments",
            model=self._get_string("features/devtype"),
            serial=self._get_string("features/serial"),
            version=version_info["value"][0],
        )

    @rpc_method
    def get_node_string(self, node_path: str, awg_channel: None | int = None) -> str:
        """Get a string value for the node.

        Parameters:
            node_path: The node to query.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.

        Returns:
            string: Value for the given node.
        """
        self._check_is_open()
        _logger.info("[%s] Getting string value for node [%s]", self._name, node_path)

        return self._get_string(node_path, awg_channel)

    @rpc_method
    def set_node_value(self, node_path: str, value: int | float | str, awg_channel: None | int = None) -> None:
        """Write a value to the device node tree.

        Requires LabOne version 21.08 or newer.

        Parameters:
            node_path: Path in the device tree, relative to the "/devNNNN/" subtree.
            value:     Value to write.
        """
        self._set_value(node_path, value, awg_channel)

    @rpc_method
    def get_node_int(self, node_path: str, awg_channel: None | int = None) -> int:
        """Get an integer value in the device node tree.

        Parameters:
            node_path:   Path in the device tree, relative to the "/devNNNN/" subtree.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        return self._get_int(node_path, awg_channel)

    @rpc_method
    def set_node_int(self, node_path: str, value: int, awg_channel: None | int = None) -> None:
        """Set an integer value in the device node tree.

        Parameters:
            node_path:   Path in the device tree, relative to the "/devNNNN/" subtree.
            value:       Integer value to write.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        self._set_int(node_path, value, awg_channel)

    @rpc_method
    def get_node_double(self, node_path: str, awg_channel: None | int = None) -> float:
        """Get a floating point value in the device node tree.

        Parameters:
            node_path:   Path in the device tree, relative to the "/devNNNN/" subtree.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        return self._get_double(node_path, awg_channel)

    @rpc_method
    def set_node_double(self, node_path: str, value: float, awg_channel: None | int = None) -> None:
        """Set a floating point value in the device node tree.

        Parameters:
            node_path:   Path in the device tree, relative to the "/devNNNN/" subtree.
            value:       Floating point value to write.
            awg_channel: Optional, an AWG channel to get the node for. Default is None.
        """
        self._set_double(node_path, value, awg_channel)

    @rpc_method
    def get_channel_grouping(self) -> int:
        """Get the channel grouping of the device.

        Returns:
            grouping: Current channel grouping.
                      0 = 4x2 channels;
                      1 = 2x4 channels;
                      2 = 1x8 channels.
        """
        self._check_is_open()
        grouping = self._get_int("system/awg/channelgrouping")
        return grouping

    @rpc_method
    def set_channel_grouping(self, grouping: int) -> None:
        """Set the channel grouping of the device.

        Parameters:
            grouping: Channel grouping to set. Possible values are:
                      0 = 4x2 (2x2) channels;
                      1 = 2x4 (1x4) channels;
                      2 = 1x8 channels (HDAWG8 only).
        """
        if grouping not in range(3):
            raise ValueError(f"Unsupported channel grouping: {grouping}.")

        self._check_is_open()
        self._set_int("system/awg/channelgrouping", grouping)
        self._grouping = grouping

    @rpc_method
    def set_awg_module_index(self, index: int):
        """Set the AWG module index. Possible values are dependent on grouping and are:
         - 0 for 1x8 group mode;
         - 0,1 for 2x4 group mode;
         - 0,1,2,3 for 4x2 group mode.

        NOTE: It is possible to set any value regardless of the mode, so it is up to the user to control
              if the given index is valid.

        Parameters:
            index: AWG module index number.

        Raises:
            ValueError: If the given index value is invalid.
        """
        if index not in range(self.NUM_AWGS):
            raise ValueError(f"Index number {index} is invalid.")

        self.awg_module.set("index", index)

    @rpc_method
    def get_awg_module_index(self) -> int:
        """Get the current AWG module index. Possible values are dependent on grouping.

        Returns:
            index: AWG module index number.
        """
        return self.awg_module.getInt("index")

    @rpc_method
    def get_awg_module_enabled(self) -> int:
        """Return the current enable status of the AWG module.

        Returns:
            1 - If the AWG sequencer is currently running.
            0 - If the AWG sequencer is not running.

        Raises:
            ValueError: AWG index number is invalid.
        """
        self._check_is_open()
        return self.awg_module.getInt("awg/enable")

    @rpc_method
    def set_awg_module_enabled(self, value: int) -> None:
        """Enable or disable the AWG module.

        Enabling the AWG starts execution of the currently loaded sequencer program. This is equal to calling
        'awg_module.execute()'. Disabling is equal to 'awg_module.finish()'.

        Parameters:
            value: 1 to enable the AWG module, 0 to disable.

        Raises:
            ValueError: AWG module enable value is invalid.
        """
        value = int(value)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if value not in (0, 1):
            raise ValueError("Invalid value")

        self._check_is_open()
        self.awg_module.set("awg/enable", value)

    @rpc_method
    def get_awg_core_enabled(self, awg_core: int) -> int:
        """Return the current enable status of the AWG module.

        Parameters:
            awg_core: AWG core number.

        Returns:
            1 - If the AWG sequencer is currently running.
            0 - If the AWG sequencer is not running.

        Raises:
            ValueError: AWG core number is not valid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")

        self._check_is_open()
        return self.device.awgs[awg_core].enable()

    @rpc_method
    def set_awg_core_enabled(self, awg_core: int, value: int) -> None:
        """Enable or disable an AWG core.

        Uploading a sequencer program or waveform or command table is possible only while the AWG core is disabled.

        Parameters:
            awg_core: AWG core number.
            value:    1 to enable the AWG core, 0 to disable.

        Raises:
            ValueError: - AWG core number is not valid.
                        - AWG core enable value is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")

        value = int(value)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if value not in (0, 1):
            raise ValueError("Invalid enable value")

        self._check_is_open()
        self.device.awgs[awg_core].enable(value)

    @rpc_method
    def upload_sequencer_program(self, awg_channel: int, sequencer_program: str) -> None:
        """A sequencer program is compiled and uploaded using the toolkit's load_sequencer_program function.
        It is recommended to follow-up this command with the `self.channel_ready(awg_channel)` call before
        trying to upload the command table or to activate the sequencer.

        NOTE: If using this in grouping mode 2 (1x8), valid channel values for the sequencer programs are
              1 and 2 ONLY. It is not recommended to use in that grouping mode as the programs might need editing.

        Parameters:
            awg_channel:       AWG channel number to compile the program for, in range 0...7.
            sequencer_program: The sequencer program as a string.
        """
        try:
            # Load sequencer program. Equivalent to compiling and uploading.
            result = self.awg_channel_map[awg_channel].load_sequencer_program(sequencer_program)
            result_ok = result["messages"] == ""
            if not result_ok:
                raise RuntimeError

        except (RuntimeError, TimeoutError) as err:
            _logger.exception(f"Loading sequencer program %s failed: %s", sequencer_program, str(err))
            raise QMI_RuntimeException("Loading sequencer program failed.") from err

        self._last_compilation_successful = True
        return

    @rpc_method
    def compile_sequencer_program(self, awg_channel: int, sequencer_program: str) -> tuple[bytes, Any]:
        """Compile the given sequencer program for specific AWG channel, which is translated into the
        respective AWG core.

        Parameters:
            awg_channel:       The AWG channel to compile the program for.
            sequencer_program: The sequencer program as a string.

        Returns:
            compiled_program: The compiled program as bytes.
            compiler_output:  Output of the compilation.
        """
        self._check_is_open()
        _logger.info("[%s] Compiling sequencer program", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]

        compiled_program, compiler_output = awg_node.compile_sequencer_program(sequencer_program)
        _logger.debug(f"Compilation Info:\n{compiler_output}")

        return compiled_program, compiler_output

    @rpc_method
    def upload_compiled_program(self, awg_channel: int, compiled_program: bytes) -> Any:
        """Upload the given compiled program for specific AWG channel. The AWG channel is translated into the
        respective AWG core number.

        Parameters:
            awg_channel:      The AWG channel to upload the program to.
            compiled_program: The compiled program to upload.

        Returns:
            upload_info: The returned value from the upload command.
        """
        self._check_is_open()
        _logger.info("[%s] Uploading sequencer program", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]

        upload_info = awg_node.elf.data(compiled_program)
        _logger.debug(f"Upload Info:\n{upload_info}")

        return upload_info

    @rpc_method
    def compile_and_upload(
        self,
        sequencer_program: str,
        replacements: None | dict[str, str | int | float] = None,
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
        replacements = replacements or {}
        # Perform parameter replacements.
        sequencer_program = self._process_parameter_replacements(sequencer_program, replacements)
        self._check_program_not_empty(sequencer_program)
        self._last_compilation_successful = False
        # Compile and upload for current AWG module index.
        self.awg_module.set("compiler/upload", 1)
        self.awg_module.set("compiler/sourcestring", sequencer_program)
        # Check for compiling timeout
        compilation_status = self._wait_compile()
        result_ok = self._interpret_compilation_result_is_ok(compilation_status)
        if not result_ok:
            raise QMI_RuntimeException("Compilation did not succeed.")

        # Poll the AWG module to check ELF upload progress.
        upload_status = self._wait_upload()
        result_ok = self._interpret_upload_result_is_ok(upload_status)
        if not result_ok:
            raise QMI_RuntimeException("ELF upload did not succeed.")

        self._last_compilation_successful = True

    @rpc_method
    def compilation_successful(self) -> bool:
        """Query result of compilation process (sequence compilation and ELF upload).

        Note: This will only return a meaningful value after starting at least one compilation process. The method
              returns False if there was no previous compilation result.
        """
        return self._last_compilation_successful

    @rpc_method
    def get_sequence_snippet(self, waveforms: "Waveforms") -> str:
        """Get a sequencer code snippet that defines the given waveforms.

        Parameters:
            waveforms:  Waveforms to generate snippet for.

        Returns:
            Sequencer code snippet as a string.
        """
        _logger.info("[ZurichInstruments_HDAWG]: Generating sequencer code snippet for waveforms")
        return waveforms.get_sequence_snippet()

    @rpc_method
    def write_to_waveform_memory(self, awg_channel: int, waveforms: "Waveforms", indexes: None | list = None) -> None:
        """Write waveforms to the waveform memory. The waveforms must already be assigned in the sequencer program.

        Parameters:
            awg_channel: AWG channel number [0-7].
            waveforms:   Waveforms to write.
            indexes:     List of indexes to upload. Default is None, which uploads all waveforms.
        """
        self._check_is_open()
        _logger.info("[%s] Writing waveforms to waveform memory", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]
        awg_node.write_to_waveform_memory(waveforms, indexes) if indexes else awg_node.write_to_waveform_memory(
            waveforms
        )

    @rpc_method
    def read_from_waveform_memory(self, awg_channel: int, indexes: None | list[int] = None) -> "Waveforms":
        """Read waveforms from the waveform memory for an AWG channel.

        Parameters:
            awg_channel: AWG channel number [0-7].
            indexes:     List of indexes to read. Default is None, which uploads all waveforms.

        Returns:
            Waveforms from waveform memory.
        """
        self._check_is_open()
        _logger.info("[%s] Reading waveforms from waveform memory", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]

        return awg_node.read_from_waveform_memory(indexes) if indexes else awg_node.read_from_waveform_memory()

    @rpc_method
    def validate_waveforms(
        self,
        awg_channel: int,
        waveforms: "Waveforms",
        compiled_sequencer_program: None | bytes = None,
    ) -> None:
        """Validate if the waveforms match the sequencer program.

        Parameters:
            awg_channel:                AWG channel number [0-7].
            waveforms:                  Waveforms to validate.
            compiled_sequencer_program: Optional sequencer program.
                                        If this is not provided then information from the device is used.
        """
        self._check_is_open()
        _logger.info("[%s] Validating waveforms", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]
        waveforms.validate(
            compiled_sequencer_program if compiled_sequencer_program else awg_node.waveform.descriptors()
        )

    @rpc_method
    def upload_waveform(
        self,
        awg_channel: int,
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
            awg_channel:     AWG channel number [0-7].
            waveform_index:  0-based index of the waveform array.
            wave1:           Array containing waveform floating point samples in range -1.0 .. +1.0
                             for the first core channel. Note that if wave1 is a complex array, the
                             imaginary part will be treated as wave2.
            wave2:           Array containing waveform floating point samples in range -1.0 .. +1.0
                             for the second core channel.
            markers:         Array containing integer values where the 4 least significant bits of
                             each sample represent the 4 marker channels.
        """
        self._check_is_open()
        waveform = Waveforms()
        markers, wave1, wave2 = self._control_waveform_inputs(markers, wave1, wave2)

        waveform[waveform_index] = (wave1, wave2, markers)
        self.validate_waveforms(awg_channel, waveform)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]
        awg_node.write_to_waveform_memory(waveform)

    @rpc_method
    def upload_waveforms(
        self,
        unpacked_waveforms: list[tuple[int, int, np.ndarray, None | np.ndarray, None | np.ndarray]],
        batch_size: int = 50,
    ) -> None:
        """Upload a set of new waveform data to the AWG. Works as singular waveform uploading, but creating a
        list of tuple sets of waveforms, and uploading all in one command, speeds up the upload significantly.

        Large sets of waveforms need to be batched to avoid running out of memory.

        The loop that creates the unpacked waveforms loops such that:
        - outer loop: for waveform count, sequence in enumerate(waveforms)
          - inner loop: for awg_core in range(4)

        Parameters:
            unpacked_waveforms: List of tuples, each tuple is a collection of AWG core number, waveform sequence index,
                                wave1, wave2 and markers.
            batch_size:         Large sets of waveforms take plenty of memory. This makes the waveforms to be sent with
                                maximum sized batches. Default size is 50 waveform entries.
        """
        self._check_is_open()

        waves_set = []
        for wf_count, sequence in enumerate(unpacked_waveforms):
            awg_core, waveform_index, wave1, wave2, markers = sequence
            markers, wave1, wave2 = self._control_waveform_inputs(markers, wave1, wave2)
            wave_raw = zhinst.utils.convert_awg_waveform(wave1, wave2, markers)
            waveform_address = f"/{self._device_name}/awgs/{awg_core}/waveform/waves/{waveform_index}"
            waves_set.append((waveform_address, wave_raw))
            # Check set size against batch size
            if wf_count % batch_size == batch_size - 1:
                # send a batch and reset list
                self.daq_server.set(waves_set)
                waves_set = []

        # Send also any possible remains of the last batch (or if there were less than batch_size waveforms)
        if len(waves_set):
            self.daq_server.set(waves_set)

    @rpc_method
    def upload_waveforms_per_awg_core(
        self, unpacked_waveforms: list[tuple[int, int, np.ndarray, None | np.ndarray, None | np.ndarray]]
    ) -> None:
        """Upload a set of new waveform data to the AWG. Works as singular waveform uploading, but organizing waveforms
        into Waveforms objects per AWG channel pairs. Then upload is done per one AWG channel pair at a time.

        The loop that creates the unpacked waveforms loops such that:
        - outer loop: for waveform_index, sequence in enumerate(waveforms)
          - inner loop: for awg_core in range(4), where channels are paired per core:
              channel_a = 2 * awg_core + 1  # 1, 3, 5, 7
              channel_b = 2 * awg_core + 2  # 2, 4, 6, 8

        Parameters:
            unpacked_waveforms: List of tuples, each tuple is a collection of AWG core index, waveform sequence index,
                                wave1, wave2 and markers.
        """
        self._check_is_open()

        waveforms = {}
        for sequence in unpacked_waveforms:
            awg_core, waveform_index, wave1, wave2, markers = sequence
            markers, wave1, wave2 = self._control_waveform_inputs(markers, wave1, wave2)
            if awg_core not in waveforms:
                waveforms[awg_core] = Waveforms()

            waveforms[awg_core][waveform_index] = (wave1, wave2, markers)

        for awg_core in waveforms.keys():
            self.device.awgs[awg_core].write_to_waveform_memory(waveforms[awg_core])

    @rpc_method
    def get_schema(self, awg_channel: int) -> dict[str, Any]:
        """Get the schema for the respective core of the channel from the device.

        Parameters:
            awg_channel: AWG channel number [0-7].

        Returns:
            schema: The node's validation schema.
        """
        self._check_is_open()
        _logger.info("[%s] Getting schema for channel [%d]", self._name, awg_channel)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]

        return awg_node.commandtable.load_validation_schema()

    @rpc_method
    def get_command_table(self, awg_channel: int) -> "zhinst.toolkit.CommandTable":
        """Get the command table for the respective core of the channel from the device.

        Parameters:
            awg_channel: AWG channel number [0-7].

        Returns:
            command_table: The command table.
        """
        self._check_is_open()
        _logger.info("[%s] Getting command table for channel [%d]", self._name, awg_channel)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]

        return awg_node.commandtable.load_from_device()

    @rpc_method
    def upload_command_table(
        self, awg_core: int, command_table_entries: list[dict[str, Any]], save_as_file: bool = False
    ) -> None:
        """Upload a new command table to the AWG.

        Command tables are needed for using e.g. `assignWaveIndex` and must be uploaded before the sequencer program
        is executed. Do not upload while a program is running. Note that each core that is used by the sequencer
        script needs a valid command table and that grouped cores need the same command table. In 1x8 mode all 4
        cores thus need identical tables. In 2x4 mode, cores 0 and 1 need identical tables, and 2 and 3 need also
        identical table between them. In grouping mode 4x2 all the tables can be different. Note that for cores which
        have no sequencer program in the core group, no command table can be uploaded.

        A template command table for the node is created based on the schema obtained from the node. The input command
        table entries are then added into the command table. The resulting table is validated before uploading.

        At the time of the writing this version of the driver, the schema is based on draft 7:
        https://json-schema.org/draft-07.

        Parameters:
            awg_core:               0-based number of AWG core to apply the table to (0 .. 3).
            command_table_entries:  Actual command table as a list of entries (dicts).
            save_as_file:           Set to True to save the validated JSON command table in a file. Default is False.

        Raises:
            ValueError:   Invalid AWG core number.
            ValueError:   Validation of the command table failed.
            ValueError:   Invalid value in the command table despite successful validation.
            RuntimeError: If the upload of command table on core awg_core failed. In 2x4 and 4x2 grouping modes the
                          reason often is that there are no waveforms and | or sequencers uploaded to the respective
                          group, e.g. in 2x4 mode, waveforms were uploaded on channels 0...3, but then trying to upload
                          command table to core 2 or 3 which refer now to channels 4...7. Otherwise, could be and
                          error in the JSON file with similar channel number vs core number mismatch.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("AWG core number is not valid.")

        self._check_is_open()
        awg_node = self.device.awgs[awg_core]
        # Get schema from the device and use it to create an empty command table
        schema = awg_node.commandtable.load_validation_schema()
        command_table = zhinst.toolkit.CommandTable(schema)
        command_table = self._add_command_table_entries(command_table, command_table_entries)
        if save_as_file:
            # Save command table as a JSON file.
            try:
                # Convert the command table to JSON.
                command_table_as_json = json.dumps(command_table.as_dict(), allow_nan=False, separators=(",", ":"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid value in command table.") from exc

            with open(os.path.join(f"{os.path.dirname(__file__)}", f"cmd_table_{awg_core}.json"), "w") as out:
                out.write(command_table_as_json)

        # Upload command table
        upload_start_time = time.monotonic()  # For debug purposes only
        try:
            awg_node.commandtable.upload_to_device(command_table, validate=True, check_upload=True)
        except RuntimeError as exc:
            _logger.error("The upload of command table on core %s failed.", awg_core, exc_info=exc)
            raise RuntimeError(f"The upload of command table on core {awg_core} failed.") from exc
        except zhinst.toolkit.exceptions.ValidationError as exc:
            _logger.exception("The provided command table is not valid", exc_info=exc)
            raise ValueError("Invalid command table.") from exc

        _logger.debug(
            "Command Table upload finished in %.1f seconds (status=%d)",
            time.monotonic() - upload_start_time, awg_node.commandtable.check_status()
        )

    @rpc_method
    def sync(self) -> None:
        """Synchronise the state of the AWG.

        This call ensures that all previous settings have taken effect on the instrument, and stale data is flushed
        from local buffers. The sync is performed for all devices connected to the DAQ server.
        """
        self._check_is_open()
        _logger.info("[%s] Synchronising state of AWG", self._name)
        self._session.sync()

    @rpc_method
    def enable_sequencer(self, awg_channel: int, disable_when_finished: bool = True) -> None:
        """Enable the sequencer.

        Parameters:
            awg_channel:           AWG channel number [0-7].
            disable_when_finished: Flag to disable sequencer after it finishes execution. Default is True.
        """
        self._check_is_open()
        _logger.info("[%s] Enabling sequencer", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]
        awg_node.enable_sequencer(single=disable_when_finished)

    @rpc_method
    def channel_ready(self, awg_channel: int) -> bool:
        """Query if the AWG channel is ready. Recommended to use after respective channel's
        'load_sequencer_program' call."""
        start_time = time.monotonic()
        while not self.awg_channel_map[awg_channel].ready():
            time.sleep(self.POLL_PERIOD)
            if time.monotonic() - start_time > (self.COMPILE_TIMEOUT + self.UPLOAD_TIMEOUT):
                return False

        return True

    @rpc_method
    def wait_done(self, awg_channel: int, timeout: float = 10.0) -> None:
        """Wait for AWG sequencer to finish.

        Parameters:
            awg_channel: AWG channel number [0-7].
            timeout:     Optional timeout in seconds. Default is 10s.
        """
        self._check_is_open()
        _logger.info("[%s] Waiting for sequencer to finish", self._name)
        # Get the AWG node/core
        awg_node = self.awg_channel_map[awg_channel]
        awg_node.wait_done(timeout=timeout)

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
        if value not in range(3):
            raise ValueError("Unsupported reference clock source.")

        self._check_is_open()
        _logger.info("[%s] Setting reference clock source to [%d]", self._name, value)
        self.device.system.clocks.referenceclock.source(value)

    @rpc_method
    def get_reference_clock_status(self) -> int:
        """Return the status of the reference clock.

        Returns:
            0: The reference clock is locked.
            1: There was an error locking to the reference clock.
            2: The device is busy locking the reference clock.
        """
        self._check_is_open()
        _logger.info("[%s] Getting status of reference clock", self._name)
        return self.device.system.clocks.referenceclock.status()

    @rpc_method
    def set_sample_clock_frequency(self, frequency: float) -> None:
        """Set the base sample clock frequency.

        Changing the sample clock temporarily interrupts the AWG sequencers.

        Parameters:
            frequency: New base sample clock frequency in Hz (range 100.0e6 to 2.4e9).
        """
        self._check_is_open()
        _logger.info("[%s] Setting sample clock frequency to [%d]", self._name, frequency)
        self.device.system.clocks.sampleclock.freq(frequency)

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
        return self.device.system.clocks.sampleclock.status()

    @rpc_method
    def set_marker_source(self, marker: int, value: int) -> None:
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

        Values 8 to 15 select the external trigger signals from marker inputs 1 to 8.

        Value 17 sets the marker output to a constant high level.
        Value 18 sets the marker output to a constant low level.

        Parameters:
            marker: Marker index in the range 0 to 7, corresponding to marker outputs 1 to 8 on the front panel.
            value:  Selected marker source as defined above.

        Raises:
            ValueError: By invalid marker index value.
            ValueError: By invalid trigger source value.
        """
        if marker < 0 or marker >= self.NUM_CHANNELS:
            raise ValueError("Invalid marker index.")
        if value not in range(16) and value not in (17, 18):
            raise ValueError(f"Invalid trigger source: {value}.")

        self._check_is_open()
        self._set_int(f"triggers/out/{marker}/source", value)

    @rpc_method
    def set_marker_delay(self, marker: int, value: float) -> None:
        """Set the output delay for a specific marker output.

        Trigger delay, controls the fine delay of the marker output. The resolution is 78 ps.

        Parameters:
            marker: Marker index in the range 0 to 7, corresponding to marker outputs 1 to 8 on the front panel.
            value:  Delay in seconds.

        Raises:
            ValueError: By invalid marker index value.
        """
        if marker not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid marker index.")

        self._check_is_open()
        self._set_double(f"triggers/out/{marker}/delay", value)

    @rpc_method
    def get_trigger_level(self, trigger: int) -> float:
        """Get the trigger voltage level of a specific trigger input.

        Parameters:
            trigger: Trigger index in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.

        Returns:
            value:   Trigger level in Volt, range -10.0 to +10.0 exclusive.

        Raises:
            ValueError: By invalid trigger index value.
        """
        if trigger not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid trigger index.")

        self._check_is_open()
        return self.device.triggers.in_[trigger].level()

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
        if trigger not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid trigger index.")
        if not self.TRIGGER_LEVEL_RANGE[0] < value < self.TRIGGER_LEVEL_RANGE[1]:
            raise ValueError("Invalid trigger level.")

        self._check_is_open()
        self.device.triggers.in_[trigger].level(value)

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
        if trigger not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid trigger index.")
        if value not in (0, 1):
            raise ValueError("Invalid impedance setting.")

        self._check_is_open()
        _logger.info(
            "[%s] Setting trigger impedance of channel %d to %s",
            self._name,
            trigger,
            "50 Ohm" if value else "1 kOhm",
        )
        self.device.triggers.in_[trigger].imp50(value)

    @rpc_method
    def set_dig_trigger_source(self, awg_core: int, trigger: int, value: int) -> None:
        """Select the source of a specific digital trigger channel.

        There are two digital trigger channels which can be accessed in the
        sequencer program via calls to "waitDigTrigger()" and "playWaveDigTrigger()".

        Parameters:
            awg_core: AWG core number.
            trigger:  Digital trigger index in the range 0 to 1, corresponding to digital triggers 1 and 2.
            value:    Trigger source in the range 0 to 7, corresponding to trigger inputs 1 to 8 on the front panel.

        Raises:
            ValueError: - AWG core number is not valid.
                        - Digital trigger index is invalid.
                        - Trigger source value is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")
        if trigger not in (0, 1):
            raise ValueError("Invalid digital trigger index.")
        if value not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid trigger source.")

        self._check_is_open()
        self.device.awgs[awg_core].auxtriggers[trigger].channel(value)

    @rpc_method
    def set_dig_trigger_slope(self, awg_core: int, trigger: int, value: int) -> None:
        """Set the trigger slope of a specific digital trigger channel.

        There are two digital trigger channels which can be accessed in the
        sequencer program vi calls to "waitDigTrigger()" and "playWaveDigTrigger()".

        Parameters:
            awg_core: AWG core number.
            trigger:  Digital trigger index in the range 0 to 1, corresponding to digital triggers 1 and 2.
            value:    Trigger slope:
                        0 - level sensitive (trigger on high signal);
                        1 - trigger on rising edge;
                        2 - trigger on falling edge;
                        3 - trigger on rising and falling edge.

        Raises:
            ValueError: - AWG core number is not valid.
                        - Digital trigger index is invalid.
                        - Trigger slope value is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")
        if trigger < 0 or trigger > 1:
            raise ValueError("Invalid digital trigger index.")
        if value < 0 or value > 3:
            raise ValueError("Invalid trigger slope.")

        self._check_is_open()
        self.device.awgs[awg_core].auxtriggers[trigger].slope(value)

    @rpc_method
    def get_dio_mode(self) -> int:
        """Get the current DIO control mode.

        Returns:
            mode: The current DIO mode (0, 1, 2 or 3).
        """
        self._check_is_open()
        return self.device.dios[0].mode()

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
            mode: Mode to use (0, 1, 2 or 3).

        Raises:
            ValueError: If mode is not valid.
        """
        if not 0 <= mode <= 3:
            raise ValueError("Invalid DIO mode.")

        self._check_is_open()
        self.device.dios[0].mode(mode)

    @rpc_method
    def set_dio_drive(self, mask: int) -> None:
        """Define input/output direction of DIO signals.

        Parameters:
            mask:   4-bit mask, e.g. '0b0101', where each bit configures the direction of
                    a group of 8 DIO signals. Bit value 0 sets the DIO signals to input mode,
                    value 1 sets the signals to output mode.

        Raises:
            ValueError: If DIO signals direction mask is not valid.
        """
        if not 0 <= mask <= 15:
            raise ValueError("Invalid value for mask.")

        self._check_is_open()
        self.device.dios[0].drive(mask)

    @rpc_method
    def set_digital_output(self, value: bool):
        """Set digital output for all digital channels configured as outputs.

        Parameters:
            value: Set to high (True) or low (False).
        """
        self._check_is_open()
        self.device.dios[0].output(int(value))

    @rpc_method
    def set_dio_valid_index(self, awg_core: int, index: int) -> None:
        """Set the DIO bit to use as the VALID signal to indicate a valid input is available.

        Parameters:
            awg_core: The AWG core to set the DIO bit index.
            index:    The DIO VALID bit index number.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")

        index = int(index)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if index < 0 or index > 31:
            raise ValueError("Invalid DIO VALID bit index.")

        self._check_is_open()
        self.device.awgs[awg_core].dio.valid.index(index)

    @rpc_method
    def set_dio_polarity(self, awg_core: int, polarity: int | str) -> None:
        """Set polarity of the VALID bit that indicates that a valid input is available.

        Parameters:
            awg_core: The AWG core to set the DIO bit index.
            polarity: The polarity value. Possible values are:
                      - 0 or "none": None - VALID bit is ignored.
                      - 1 or "low": Low - VALID bit must be logical zero.
                      - 2 or "high": High - VALID bit must be logical high.
                      - 3 or "both": Both - VALID bit may be logical high or zero.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")

        if isinstance(polarity, str):
            polarity = polarity.lower()
            if polarity in ["0", "1 ", "2", "3"]:
                # int was inputted as string, convert...
                polarity = int(polarity)

            elif polarity not in ["none", "low", "high", "both"]:
                raise ValueError(f"Invalid polarity type {polarity}")

        else:
            polarity = int(polarity)  # Conversion just in case input is e.g. float. ZhInst checks the type.
            if polarity not in range(4):
                raise ValueError("Invalid DIO polarity value.")

        self._check_is_open()
        self.device.awgs[awg_core].dio.valid.polarity(polarity)

    @rpc_method
    def set_dio_strobe_index(self, awg_core: int, value: int) -> None:
        """Select the DIO strobe index to be used as a trigger for playback.

        The sequencer program uses this trigger by calling "playWaveDIO()".

        Parameters:
            awg_core: AWG core number.
            value:    DIO bit index in the range 0 to 31.

        Raises:
            ValueError: - AWG core number is not valid.
                        - DIO bit index is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")

        value = int(value)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if value < 0 or value > 31:
            raise ValueError("Invalid DIO strobe index.")

        self._check_is_open()
        self._set_int(f"awgs/{awg_core}/dio/strobe/index", value)

    @rpc_method
    def set_dio_strobe_slope(self, awg_core: int, value: int) -> None:
        """Select the signal edge that should activate the strobe trigger.

        Parameters:
            awg_core: AWG core number.
            value:    Slope type:
                            0 - off;
                            1 - trigger on rising edge;
                            2 - trigger on falling edge;
                            3 - trigger on rising and falling edge.

        Raises:
            ValueError: - AWG core number is not valid.
                        - DIO strobe slope value is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")
        if value < 0 or value > 3:
            raise ValueError("Invalid slope.")

        self._check_is_open()
        self._set_int(f"awgs/{awg_core}/dio/strobe/slope", value)

    @rpc_method
    def get_output_amplitude(self, awg_core: int, channel: int) -> float:
        warnings.warn(
            f"{self.get_output_amplitude.__name__} is now deprecated. Please use {self.get_output_gain.__name__}. " +
            "We reserve this function for the future to use getting the sine peak amplitude" +
            " (../sines/{awg_core}/amplitudes/{channel}).", DeprecationWarning
        )
        awg_channel = awg_core * 2 + channel
        return self.get_output_gain(awg_channel)

    @rpc_method
    def set_output_amplitude(self, awg_core: int, channel: int, value: float) -> None:
        warnings.warn(
            f"{self.set_output_amplitude.__name__} is now deprecated. Please use {self.set_output_gain.__name__}." +
            "We reserve this function for the future to use setting the sine peak amplitude" +
            " (../sines/{awg_core}/amplitudes/{channel}).", DeprecationWarning
        )
        awg_channel = awg_core * 2 + channel
        # Set the same value for both gains
        self.set_output_gain(awg_channel, value, 2)

    @rpc_method
    def get_output_gain(self, awg_channel: int, gain_index: int = 0) -> float | tuple[float, float]:
        """Get the output scaling factor[s] (gain[s]) of the specified channel.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            gain_index:  Gain index number to obtain the gain for. Set as 2 if both values are requested.
                         Default index is 0.

        Raises:
            ValueError: - AWG channel number is invalid.
                        - Gain index was given, but was not 0, 1 or 2.

        Returns:
            gains: A dimensionless scaling factor applied to the digital signal or list of
                   two scaling factors.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError(f"Invalid channel number {awg_channel}.")

        if gain_index not in (0, 1, 2):
            raise ValueError(f"Invalid gain index {gain_index}.")

        self._check_is_open()
        awg_core = awg_channel // 2
        channel = awg_channel % 2
        if gain_index in (0, 1):
            return self._get_double(f"awgs/{awg_core}/outputs/{channel}/gains/{gain_index}")

        else:
            gain_0 = self._get_double(f"awgs/{awg_core}/outputs/{channel}/gains/0")
            gain_1 = self._get_double(f"awgs/{awg_core}/outputs/{channel}/gains/1")
            return gain_0, gain_1

    @rpc_method
    def set_output_gain(
        self, awg_channel: int, value: float | list[float, float], gain_index: int = 0) -> None:
        """Set the output scaling factor[s] (gain[s]) of the specified channel.

        The gain is a dimensionless scaling factor applied to the digital signal.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       Gain or list of two gains in range -1...+1. See Table 4.22 in HDAWG user manual revision 26.01
            gain_index:  Gain index number to obtain the gain for. Set as 2 if both values are requested.
                         Default index is 0.

        Raises:
            ValueError: - AWG channel number is invalid.
                        - Gain index was given, but was not 0, 1 or 2.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError(f"Invalid channel number {awg_channel}.")

        if gain_index not in (0, 1, 2):
            raise ValueError(f"Invalid gain index {gain_index}.")

        self._check_is_open()
        awg_core = awg_channel // 2
        channel = awg_channel % 2
        if gain_index in (0, 1):
            if isinstance(value, list | tuple):
                _logger.warning(
                    f"[{self._name}]: Gain index set as {gain_index}, but two gain values given." +
                    f"Setting only the respective value ({value[gain_index]}) from the inputs."
                )
                value = value[gain_index]

            self._set_double(f"awgs/{awg_core}/outputs/{channel}/gains/{gain_index}", value)

        else:
            if isinstance(value, list | tuple):
                # Set one value per index
                self._set_double(f"awgs/{awg_core}/outputs/{channel}/gains/0", value[0])
                self._set_double(f"awgs/{awg_core}/outputs/{channel}/gains/1", value[1])
            else:
                # Set the same gain for both indexes
                self._set_double(f"awgs/{awg_core}/outputs/{channel}/gains/0", value)
                self._set_double(f"awgs/{awg_core}/outputs/{channel}/gains/1", value)

    @rpc_method
    def get_output_channel_hold(self, awg_channel: int) -> int:
        """Get whether the last sample is held for the specified channel.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.

        Raises:
            ValueError: AWG channel number is invalid.

        Returns:
            0: If last sample is not held.
            1: If last sample is held.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError(f"Invalid channel number {awg_channel}.")

        self._check_is_open()
        awg_core = awg_channel // 2
        channel = awg_channel % 2
        return self._get_int(f"awgs/{awg_core}/outputs/{channel}/hold")

    @rpc_method
    def set_output_channel_hold(self, awg_channel: int, value: int) -> None:
        """Set whether the last sample should be held for the specified channel.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       Hold state; 0 = False, 1 = True.

        Raises:
            ValueError: - AWG channel number is invalid.
                        - Invalid hold state value.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError(f"Invalid channel number {awg_channel}.")
        if value not in (0, 1):
            raise ValueError("Invalid hold state.")

        self._check_is_open()
        awg_core = awg_channel // 2
        channel = awg_channel % 2
        self._set_int(f"awgs/{awg_core}/outputs/{channel}/hold", value)

    @rpc_method
    def get_output_channel_on(self, awg_channel: int) -> int:
        """Get the specified wave output channel state.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.

        Returns:
            channel_state: 0 = output off, 1 = output on.

        Raises:
            ValueError: Output channel number is invalid.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        self._check_is_open()
        return self._get_int(f"sigouts/{awg_channel}/on")

    @rpc_method
    def set_output_channel_on(self, awg_channel: int, value: int) -> None:
        """Set the specified wave output channel on or off.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       Output state; 0 = output off, 1 = output on.

        Raises:
            ValueError: - Output channel number is invalid.
                        - Invalid output channel state value.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        value = int(value)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if value not in (0, 1):
            raise ValueError("Invalid on/off state.")

        self._check_is_open()
        self._set_int(f"sigouts/{awg_channel}/on", value)

    @rpc_method
    def set_output_channel_range(self, awg_channel: int, value: float) -> None:
        """Set voltage range of the specified wave output channel. The available ranges are, based on testing,
        0.2V, 0.4V, 0.6V, 0.8V, 1V, 1.5V, 2V, 3V, 4V and 5V.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       Output range in Volt. The instrument selects the next higher available range.

        Raises:
            ValueError: - Output channel number is invalid.
                        - Voltage range is invalid.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        value = float(value)  # Conversion just in case input is e.g. int. ZhInst checks the type.
        if not 0.2 <= value <= 5.0:
            raise ValueError(f"Invalid channel output range: {value}.")

        self._check_is_open()
        self._set_double(f"sigouts/{awg_channel}/range", value)

    @rpc_method
    def set_output_channel_offset(self, awg_channel: int, value: float) -> None:
        """Set the DC offset voltage for the specified wave output channel.

        The DC offset is only active in amplified mode, not in direct mode.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       Offset in Volt, in range -1.25 to +1.25 V.

        Raises:
            ValueError: - Output channel number is invalid.
                        - Voltage offset is invalid.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        value = float(value)  # Conversion just in case input is e.g. int. ZhInst checks the type.
        if not -1.25 <= value <= 1.25:
            raise ValueError("Invalid offset value.")

        self._check_is_open()
        self._set_double(f"sigouts/{awg_channel}/offset", value)

    @rpc_method
    def get_output_channel_delay(self, awg_channel: int) -> float:
        """Return output delay for fine alignment of the specified wave output channel.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.

        Raises:
            ValueError: Output channel number is invalid.

        Returns:
            Delay in seconds.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        self._check_is_open()
        return self._get_double(f"sigouts/{awg_channel}/delay")

    @rpc_method
    def set_output_channel_delay(self, awg_channel: int, value: float) -> None:
        """Set output delay for fine alignment of the specified wave output channel.

        Changing the delay setting may take several seconds.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       Delay in seconds, range 0 to 26e-9.

        Raises:
            ValueError: - Output channel number is invalid.
                        - Delay value is invalid.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        value = float(value)  # Conversion just in case input is e.g. int. ZhInst checks the type.
        if not 0 <= value < 26e-9:
            raise ValueError("Invalid delay setting.")

        self._check_is_open()
        self._set_double(f"sigouts/{awg_channel}/delay", value)

    @rpc_method
    def set_output_channel_direct(self, awg_channel: int, value: int) -> None:
        """Enable or disable the direct output path for the specified wave output channel.

        The direct output path bypasses the output amplifier and offset circuits,
        and fixes the output range to 800 mV.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       1 to enable the direct output path, 0 to disable.

        Raises:
            ValueError: - Output channel number is invalid.
                        - Direct value is invalid.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError("Invalid channel index.")

        value = int(value)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if value not in (0, 1):
            raise ValueError("Invalid value.")

        self._check_is_open()
        self._set_int(f"sigouts/{awg_channel}/direct", value)

    @rpc_method
    def set_output_channel_filter(self, awg_channel: int, value: int) -> None:
        """Enable or disable the analog output filter for the specified wave output channel.

        Parameters:
            awg_channel: Channel index in the range 0 to 7, corresponding to wave outputs 1 to 8 on the front panel.
            value:       1 to enable the output filter, 0 to disable.

        Raises:
            ValueError: - Output channel number is invalid.
                        - Filter value is invalid.
        """
        if awg_channel not in range(self.NUM_CHANNELS):
            raise ValueError(f"Invalid output channel: {awg_channel}.")

        value = int(value)  # Conversion just in case input is e.g. bool. ZhInst checks the type.
        if value not in (0, 1):
            raise ValueError("Invalid value.")

        self._check_is_open()
        self._set_int(f"sigouts/{awg_channel}/filter", value)

    @rpc_method
    def get_user_register(self, awg_core: int, reg: int) -> int:
        """Return the value of the specified user register.

        Parameters:
            awg_core: AWG core number.
            reg:      Register index in the range 0 to 15.

        Returns:
            value: User register value.

        Raises:
            ValueError: - AWG core number is not valid.
                        - Register index is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")
        if not 0 <= reg <= 15:
            raise ValueError("Invalid register index.")

        self._check_is_open()
        return self._get_int(f"awgs/{awg_core}/userregs/{reg}")

    @rpc_method
    def set_user_register(self, awg_core: int, reg: int, value: int) -> None:
        """Change the value of the specified user register.

        Parameters:
            awg_core: AWG core number.
            reg:      Register index in the range 0 to 15.
            value:    Integer value to write to the register.

        Raises:
            ValueError: - AWG core number is not valid.
                        - Register index is invalid.
        """
        if awg_core not in range(self.NUM_AWGS):
            raise ValueError("Invalid AWG core number.")
        if not 0 <= reg <= 15:
            raise ValueError("Invalid register index")

        self._check_is_open()
        self._set_int(f"awgs/{awg_core}/userregs/{reg}", value)
