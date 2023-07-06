"""
Instrument driver for the Stanford Research Systems DC205 voltage source.
"""

import logging
from typing import List

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Execution error codes returned by the DC205.
EXECUTION_ERRORS = {
    0: "Ok",
    1: "Illegal value",
    2: "Wrong token",
    3: "Invalid bit",
    4: "Queue full",
    5: "Not compatible",
}

# Command error codes returned by the DC205.
COMMAND_ERRORS = {
    0: "Ok",
    1: "Illegal command",
    2: "Undefined command",
    3: "Illegal query",
    4: "Illegal set",
    5: "Missing parameter",
    6: "Extra parameter",
    7: "Null parameter",
    8: "Parameter buffer overflow",
    9: "Bad floating-point",
    10: "Bad integer",
    11: "Bad integer token",
    12: "Bad token value",
    13: "Bad hex block",
    14: "Unknown token",
}


class SRS_DC205(QMI_Instrument):
    """Instrument driver for the Stanford Research Systems DC205 voltage source.

    This driver implements most basic features of the instrument.
    Linear voltage scanning is not supported by this driver.
    """

    # Response timeout for normal commands.
    COMMAND_RESPONSE_TIMEOUT = 2.0

    # Response timeout for reset command.
    RESET_RESPONSE_TIMEOUT = 5.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Arguments:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
                            The transport descriptor will typically specify a
                            serial port and baud rate, for example
                            "serial:/dev/ttyUSB0:baudrate=115200".
        """
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": 115200}
        )
        self._scpi_protocol = ScpiProtocol(
            self._transport,
            command_terminator="\n",
            response_terminator="\n",
            default_timeout=self.COMMAND_RESPONSE_TIMEOUT,
        )

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()
        # The DC205 supports several different response termination styles.
        # Make sure that the instrument is configured for the style expected by the ScpiProtocol handler.
        try:
            self._transport.write(b"\nTERM LF\n")
        except Exception:
            self._transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _check_error(self, cmd: str) -> None:
        """Read the instrument error status and raise an exception if an error occurred."""
        resp = self._scpi_protocol.ask("LEXE?; LCME?")
        words = resp.split(";")
        if len(words) != 2:
            raise QMI_InstrumentException(
                f"Unexpected response to LEXE?;LCME?, got {resp!r}"
            )
        execution_error = int(words[0].strip())
        command_error = int(words[1].strip())
        if execution_error != 0:
            error_str = EXECUTION_ERRORS.get(execution_error, "unknown")
            raise QMI_InstrumentException(
                f"Instrument returned execution error after {cmd!r}: {execution_error} ({error_str})"
            )
        if command_error != 0:
            error_str = COMMAND_ERRORS.get(execution_error, "unknown")
            raise QMI_InstrumentException(
                f"Instrument returned command error after {cmd!r}: {command_error} ({error_str})"
            )

    def _set_command(self, cmd: str) -> None:
        self._check_is_open()
        self._scpi_protocol.write(cmd)
        self._check_error(cmd)

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating-point response."""
        self._check_is_open()
        resp = self._scpi_protocol.ask(cmd)
        try:
            return float(resp)
        except ValueError as exc:
            raise QMI_InstrumentException(
                f"Unexpected response to command {cmd!r}: {resp!r}"
            ) from exc

    def _ask_token(self, cmd: str, tokens: List[str]) -> int:
        """Read a token response from the instrument.

        The instrument can report a token value either as an integer
        or as a short string. This function accepts both forms and always
        returns the integer value.
        """
        self._check_is_open()
        resp = self._scpi_protocol.ask(cmd)
        resp = resp.strip()
        if resp in tokens:
            return tokens.index(resp)
        try:
            tok = int(resp)
        except ValueError as exc:
            raise QMI_InstrumentException(
                f"Unexpected response to command {cmd!r}: {resp!r}"
            ) from exc
        if tok >= len(tokens):
            raise QMI_InstrumentException(
                f"Unexpected response to command {cmd!r}: {resp!r}"
            )
        return tok

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""

        self._check_is_open()

        # Clear error registers.
        self._scpi_protocol.ask("LEXE?; LCME?", timeout=self.RESET_RESPONSE_TIMEOUT)

        # Reset instrument.
        self._scpi_protocol.write("*RST")

        # Wait until reset finished.
        self._scpi_protocol.ask("*OPC?", timeout=self.RESET_RESPONSE_TIMEOUT)

        # Check for errors occurred during reset.
        self._check_error("*RST")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")
        return QMI_InstrumentIdentification(
            vendor=words[0].strip(),
            model=words[1].strip(),
            serial=words[2].strip(),
            version=words[3].strip(),
        )

    @rpc_method
    def get_range(self) -> int:
        """Read the output voltage range.

        The output range is always bipolar.
        Thus, range setting 1 means -1 .. +1 Volt; range setting 10 means -10 .. +10 Volt, etc.

        Returns:
            Output range in Volt. Possible return values are 1, 10 and 100.
        """
        tok = self._ask_token(cmd="RNGE?", tokens=["RANGE1", "RANGE10", "RANGE100"])
        return [1, 10, 100][tok]

    @rpc_method
    def set_range(self, volt_range: int) -> None:
        """Set the output voltage range.

        This command may not be used while the output is enabled.

        Parameters:
            volt_range: Output range in Volt. Allowed values are 1, 10 and 100.
        """
        if volt_range not in (1, 10, 100):
            raise ValueError("Invalid voltage range")
        self._set_command(f"RNGE RANGE{int(volt_range)}")

    @rpc_method
    def get_output_enabled(self) -> bool:
        """Return True if the output is enabled, False if the output is disabled."""
        tok = self._ask_token(cmd="SOUT?", tokens=["OFF", "ON"])
        return tok != 0

    @rpc_method
    def set_output_enabled(self, enable: bool) -> None:
        """Enable or disable the output."""
        self._set_command(f"SOUT {int(enable)}")

    @rpc_method
    def get_voltage(self) -> float:
        """Return the DC voltage setting in Volt.

        Note that this returns the voltage *setting* of the instrument.
        The instrument does not measure the *actual* voltage on its output.
        """
        return self._ask_float("VOLT?")

    @rpc_method
    def set_voltage(self, voltage: float) -> None:
        """Set the DC voltage setting in Volt."""
        self._set_command(f"VOLT {voltage:.6f}")

    @rpc_method
    def get_output_floating(self) -> bool:
        """Return True if floating output is enabled, False if output is ground-referenced."""
        tok = self._ask_token(cmd="ISOL?", tokens=["GROUND", "FLOAT"])
        return tok != 0

    @rpc_method
    def set_output_floating(self, enable: bool) -> None:
        """Enable or disable floating output."""
        self._set_command(f"ISOL {int(enable)}")

    @rpc_method
    def get_sensing_enabled(self) -> bool:
        """Return True if remote sensing is enabled, otherwise return False.

        When sensing is enabled, the instrument operates in 4-wire mode, using the SENSE input terminals.
        When sensing is disabled, the instrument operates in 2-wire mode and the SENSE inputs are ignored.
        """
        tok = self._ask_token(cmd="SENS?", tokens=["TWOWIRE", "FOURWIRE"])
        return tok != 0

    @rpc_method
    def set_sensing_enabled(self, enable: bool) -> None:
        """Enable or disable remote sensing mode."""
        self._set_command(f"SENS {int(enable)}")

    @rpc_method
    def get_interlock_status(self) -> bool:
        """Return True if the safety interlock is closed, False if the interlock is open.

        The interlock needs to be closed to operate the instrument in the 100V range.
        """
        tok = self._ask_token(cmd="ILOC?", tokens=["OPEN", "CLOSED"])
        return tok != 0

    @rpc_method
    def get_overloaded(self) -> bool:
        """Return True if the instrument is in overload condition, otherwise return False."""
        tok = self._ask_token(cmd="OVLD?", tokens=["OKAY", "OVLD"])
        return tok != 0
