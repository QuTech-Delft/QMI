"""Instrument driver for the Zürich Instruments HDAWG."""

import logging
import re
import typing
from typing import List, Optional, Union, Dict

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from zhinst.toolkit.driver.nodes.awg import AWG


# Lazy import of the zhinst module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    import zhinst.toolkit
    from zhinst.toolkit.driver.nodes.awg import AWG
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
        import zhinst.toolkit
        import zhinst.toolkit.driver
        import zhinst.toolkit.driver.devices
        import zhinst.toolkit.driver.nodes
        import zhinst.toolkit.driver.nodes.awg
        import zhinst.toolkit.nodetree
        import zhinst.toolkit.session


# Sequencer code replacement variables must start with a literal $, followed by at least one letter followed by zero or
# more alphanumeric characters or underscores.
SEQC_PAR_PATTERN = re.compile(r"\$[A-Za-z][A-Za-z0-9_]*", re.ASCII)


class ZurichInstruments_HDAWG(QMI_Instrument):
    """Instrument driver for the Zürich Instruments HDAWG."""

    GENERATOR_WAIT_TIME_S = 30

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

        self._device: zhinst.toolkit.driver.devices.DeviceType

        # Import the "zhinst" module.
        _import_modules()

        # Connect to Zurich Instruments Data Server
        self._session = zhinst.toolkit.Session(self._server_host, self._server_port)

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        # Connect to the device.
        self._device = self._session.connect_device(self._device_name)

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("[%s] Closing connection to instrument", self._name)

        # Disconnect from devices
        self._session.disconnect_device(self._device_name)

        super().close()

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

    # def _get_awg_node(self, awg_core: int) -> AWG:
    #     """
    #     Get the AWG node using the core index.

    #     Parameters:
    #         awg_core:   Index for AWG node

    #     Returns:
    #         AWG node
    #     """
    #     return self._device.awgs[awg_core]

    # @rpc_method
    # def load_sequencer_program(self, sequencer_program: str | zhinst.toolkit.Sequence, awg_channel: int) -> None:
    #     """Compile and upload the sequencer program.

    #     Parameters:
    #         sequencer_program:  Sequencer program as a strng or a Sequencer class.
    #         awg_core:           The AWG channel to compile the program for.
    #         replacements:       Optional dictionary of (parameter, value) pairs. Every occurrence of the parameter in the
    #                             sequencer program will be replaced  with the specified value.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Loading sequencer program", self._name)
    #     self._check_program_not_empty(sequencer_program)

    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     # Load sequence program. Equivalent to compiling and uploading.
    #     info = awg_node.load_sequencer_program(sequencer_program)
    #     _logger.debug(f"Loading Sequence Info:\n{info}")

    # @rpc_method
    # def enable_sequencer(self, awg_channel: int) -> None:
    #     """
    #     Enable the sequencer.

    #     Parameters:
    #         awg_channel:   AWG channel to enable.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Enabling sequencer", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     awg_node.enable_sequencer(single=True)

    # @rpc_method
    # def wait_done(self, awg_channel: int) -> None:
    #     """
    #     Wait for AWG to finish.

    #     Parameters:
    #         awg_channel:   AWG channel to wait for.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Waiting for sequencer to finish", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     awg_node.wait_done(timeout=self.GENERATOR_WAIT_TIME_S)

    # @rpc_method
    # def compile_program(self, sequencer_program: str, awg_channel: int) -> bytes:
    #     """
    #     Compile the given sequencer program.

    #     Parameters:
    #         sequencer_program:  The sequencer program as a string.
    #         awg_channel:        The AWG channel to compile the program for.

    #     Returns:
    #         compiled program as bytes.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Compiling sequencer program", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     compiled_program, compiler_output = awg_node.compile_sequencer_program(sequencer_program)
    #     _logger.debug(f"Compilation Info:\n{compiler_output}")

    #     return compiled_program

    # @rpc_method
    # def upload_program(self, compiled_program: bytes, awg_channel: int) -> None:
    #     """
    #     Upload the given compiler program.

    #     Parameters:
    #         compiled_program:   The compiled program to upload.
    #         awg_channel:        The AWG channel to upload the program to.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Uploading sequencer program", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     upload_info = awg_node.elf.data(compiled_program)
    #     _logger.debug(f"Upload Info:\n{upload_info}")

    # @rpc_method
    # def write_to_waveform_memory(
    #     self, awg_channel: int, waveforms: zhinst.toolkit.Waveforms, indexes: List[int] = []
    # ) -> None:
    #     """
    #     Write waveforms to the waveform memory. The waveforms must alredy be assigned in the sequencer program.

    #     Parameters:
    #         awg_channel:    The AWG channel to upload the waveforms to.
    #         waveforms:      Waveforms to write.
    #         indexes:        List of indexes to upload. Default is an empty list, which uploads all waveforms.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Writing waveforms to waveform memory", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     awg_node.write_to_waveform_memory(waveforms, indexes)

    # @rpc_method
    # def read_from_waveform_memory(self, awg_channel: int, indexes: List[int] = []) -> zhinst.toolkit.Waveforms:
    #     """
    #     Read waveforms from the waveform memory.

    #     Parameters:
    #         awg_channel:    The AWG channel to upload the waveforms to.
    #         indexes:        List of indexes to read. Default is an empty list, which uploads all waveforms.

    #     Returns:
    #         Waveforms from waveform memory.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Reading waveforms from waveform memory", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     return awg_node.read_from_waveform_memory(indexes)

    # @staticmethod
    # def get_sequence_snippet(waveforms: zhinst.toolkit.Waveforms) -> str:
    #     """
    #     Get a sequencer code snippet that defines the given waveforms.

    #     Parameters:
    #         waveforms:  Waveforms to generate snippet for.

    #     Returns:
    #         Sequencer code snippet as a string.
    #     """
    #     # TODO: this method does not need an active HDAWG, so no need to check if open
    #     _logger.info("[ZurichInstruments_HDAWG]: Generating sequencer code snippet for waveforms")
    #     return waveforms.get_sequence_snippet()

    # @rpc_method
    # def validate_waveforms(
    #     self, awg_channel: int, waveforms: zhinst.toolkit.Waveforms, compiled_sequencer_program: Optional[bytes] = None
    # ) -> None:
    #     """
    #     Validate if the waveforms match the sequencer program.

    #     Parameters:
    #         awg_channel:                AWG channel.
    #         waveforms:                  Waveforms to validate.
    #         compiled_sequencer_program: Optional sequencer program. If this is not provided then information from the device is used.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Validating waveforms", self._name)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     waveforms.validate(compiled_sequencer_program) if compiled_sequencer_program else waveforms.validate(
    #         awg_node.waveform.descriptors()
    #     )

    # @rpc_method
    # def get_command_table(self, awg_channel: int) -> zhinst.toolkit.CommandTable:
    #     """
    #     Get the command table from the device.

    #     Parameters:
    #         awg_channel:    The AWG channel to get the command table for.
    #     """
    #     self._check_is_open()
    #     _logger.info("[%s] Getting command table for channel [%d]", self._name, awg_channel)
    #     # Get the AWG node/core
    #     awg_node = self._get_awg_node(awg_channel)

    #     return awg_node.commandtable.load_from_device()
