"""
Instrument driver for the Keithley 2400 series SourceMeter.
"""
import logging
from enum import Enum

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class SourceFunction(Enum):
    """Source function of the instrument."""
    VOLTAGE = "VOLT"
    CURRENT = "CURR"


class SenseFunction(Enum):
    """Sense function of the instrument."""
    VOLTAGE = "VOLT:DC"
    CURRENT = "CURR:DC"
    RESISTANCE = "RES"


class Keithley_Sourcemeter2400(QMI_Instrument):
    """Instrument driver for the Keithley 2400 series SourceMeter.

    This driver implements the basic features of the instrument: resetting, configuring a fixed
    voltage or current source, selecting the sense function, reading out the measured voltage and
    switching the output on and off.
    """

    # Response timeout for normal commands, in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # Response timeout for the reset command, in seconds.
    RESET_RESPONSE_TIMEOUT = 10.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:      Name for this instrument instance.
            transport: QMI transport descriptor to connect to the instrument, for example
                       "gpib:board=0:primary_addr=24" for a GPIB connection, or
                       "serial:/dev/ttyUSB0:baudrate=9600" for an RS-232 connection.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 9600})
        self._scpi_protocol = ScpiProtocol(
            self._transport,
            command_terminator="\n",
            response_terminator="\n",
            default_timeout=self.DEFAULT_RESPONSE_TIMEOUT,
        )

    def _check_error(self, cmd: str) -> None:
        """Read the instrument error queue and raise an exception if an error occurred."""
        resp = self._scpi_protocol.ask(":SYST:ERR?")
        words = resp.split(",", 1)
        try:
            code = int(words[0].strip())
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to :SYST:ERR?, got {resp!r}") from exc
        if code != 0:
            message = words[1].strip() if len(words) > 1 else ""
            raise QMI_InstrumentException(f"Instrument returned error after {cmd!r}: {code} ({message})")

    def _set_command(self, cmd: str) -> None:
        """Send a command to the instrument and check for errors."""
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
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}") from exc

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()
        try:
            # Restrict the response of READ?/MEASure queries to the voltage reading only,
            # so that measure_voltage() can parse it unambiguously.
            self._scpi_protocol.write(":FORM:ELEM VOLT")
        except Exception:
            self._transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        self._check_is_open()
        self._scpi_protocol.write("*RST")
        self._scpi_protocol.ask("*OPC?", timeout=self.RESET_RESPONSE_TIMEOUT)
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
    def set_source_function(self, function: SourceFunction) -> None:
        """Select the source function of the instrument.

        Parameters:
            function: Source function, either SourceFunction.VOLTAGE or SourceFunction.CURRENT.
        """
        self._set_command(f":SOUR:FUNC:MODE {function.value}")

    @rpc_method
    def get_source_function(self) -> SourceFunction:
        """Return the currently selected source function."""
        self._check_is_open()
        resp = self._scpi_protocol.ask(":SOUR:FUNC:MODE?").strip()
        try:
            return SourceFunction(resp)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to :SOUR:FUNC:MODE?, got {resp!r}") from exc

    @rpc_method
    def set_source_voltage(self, voltage: float) -> None:
        """Set the fixed source voltage level.

        Parameters:
            voltage: Source voltage level in Volt.
        """
        self._set_command(f":SOUR:VOLT:LEV {voltage:.6g}")

    @rpc_method
    def get_source_voltage(self) -> float:
        """Return the fixed source voltage level in Volt."""
        return self._ask_float(":SOUR:VOLT:LEV?")

    @rpc_method
    def set_source_current(self, current: float) -> None:
        """Set the fixed source current level.

        Parameters:
            current: Source current level in Ampere.
        """
        self._set_command(f":SOUR:CURR:LEV {current:.6g}")

    @rpc_method
    def get_source_current(self) -> float:
        """Return the fixed source current level in Ampere."""
        return self._ask_float(":SOUR:CURR:LEV?")

    @rpc_method
    def set_sense_function(self, function: SenseFunction) -> None:
        """Select the sense function of the instrument.

        Parameters:
            function: Sense function, one of SenseFunction.VOLTAGE, SenseFunction.CURRENT
                      or SenseFunction.RESISTANCE.
        """
        self._set_command(f':SENS:FUNC:ON "{function.value}"')

    @rpc_method
    def get_sense_function(self) -> SenseFunction:
        """Return the currently selected sense function."""
        self._check_is_open()
        resp = self._scpi_protocol.ask(":SENS:FUNC:ON?").strip()
        first = resp.split(",")[0].strip().strip('"')
        try:
            return SenseFunction(first)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to :SENS:FUNC:ON?, got {resp!r}") from exc

    @rpc_method
    def measure_voltage(self) -> float:
        """Trigger a measurement and return the measured voltage in Volt."""
        return self._ask_float(":READ?")

    @rpc_method
    def set_output_enabled(self, enable: bool) -> None:
        """Enable or disable the instrument output.

        Parameters:
            enable: True to switch the output on, False to switch it off.
        """
        self._set_command(f":OUTP {int(enable)}")

    @rpc_method
    def get_output_enabled(self) -> bool:
        """Return True if the output is enabled, False if the output is disabled."""
        self._check_is_open()
        resp = self._scpi_protocol.ask(":OUTP?").strip()
        return resp in ("1", "ON")
