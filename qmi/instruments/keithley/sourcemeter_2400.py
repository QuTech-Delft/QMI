"""
Instrument driver for the Keithley 2400 series SourceMeter.

This is a limited driver, supporting resetting the instrument, configuring a fixed voltage or current source,
selecting the sense function, reading out the measured voltage and switching the output on and off.
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


class Keithley_Sourcemeter2400(QMI_Instrument):
    """Instrument driver for the Keithley 2400 series SourceMeter.

    This driver implements the basic features of the instrument: resetting, configuring a fixed
    voltage or current source, selecting the sense function, reading out the measured voltage and
    switching the output on and off.
    """

    _rpc_constants = {"GPIB_DEFAULT_ADDR"}
    _rpc_properties = {"DEFAULT_RESPONSE_TIMEOUT"}

    # Default GPIB primary address of the instrument.
    GPIB_DEFAULT_ADDR = 24

    # Default RS-232 communication attributes, matching the instrument's default front panel settings.
    SERIAL_DEFAULT_ATTRIBUTES = {"baudrate": 9600, "bytesize": 8, "parity": 'N', "stopbits": 1, "rtscts": False}

    # Response timeout for normal commands, in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # Response timeout for the reset command, in seconds.
    RESET_RESPONSE_TIMEOUT = 30.0

    def __init__(self, context: QMI_Context, name: str, transport: str, serial_terminator: str = "\r") -> None:
        """Initialize the instrument driver.

        The instrument can be controlled over GPIB or RS-232. The transport descriptor must use one of QMI's
        ``gpib:`` or ``serial:`` interfaces, e.g. ``gpib:18`` or ``serial:COM3:baudrate=19200``.

        For RS-232, the baud rate, flow control and terminator must match the instrument's front panel
        COMMUNICATION settings. The driver defaults are 9600 baud, 8N1 and no flow control.

        Parameters:
            name:               Name for this instrument instance.
            transport:          QMI transport descriptor to connect to the instrument.
            serial_terminator:  Message terminator for RS-232. Must match the instrument's RS-232 TERMINATOR
                                 setting. Not used for GPIB, where a LF terminator is used.
        """
        super().__init__(context, name)
        transport_type = transport.partition(":")[0].lower()
        if transport_type == "gpib":
            self._transport = create_transport(transport, default_attributes={"primary_addr": self.GPIB_DEFAULT_ADDR})
            terminator = "\n"

        elif transport_type == "serial":
            self._transport = create_transport(transport, default_attributes=self.SERIAL_DEFAULT_ATTRIBUTES)
            terminator = serial_terminator

        else:
            raise ValueError(f"Invalid transport string type {transport_type!r} for Keithley 2400.")

        self._scpi_protocol = ScpiProtocol(
            self._transport,
            command_terminator=terminator,
            response_terminator=terminator,
        )

    @staticmethod
    def _validate_function(function: str | SourceFunction) -> SourceFunction:
        """Validate and normalize a source function input to a SourceFunction instance."""
        return function if isinstance(function, SourceFunction) else SourceFunction(function)

    def _ask(self, cmd: str) -> str:
        """Send a query to the instrument and return the response."""
        self._check_is_open()
        return self._scpi_protocol.ask(cmd, timeout=self.DEFAULT_RESPONSE_TIMEOUT)

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
            # so that get_measured_voltage() can parse it unambiguously.
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

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._ask("*IDN?")
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
    def set_source_function(self, function: str | SourceFunction) -> None:
        """Select the source function of the instrument.

        Parameters:
            function: Source function, SourceFunction.VOLTAGE / "VOLT" or SourceFunction.CURRENT / "CURR".
        """
        function = self._validate_function(function)
        self._check_is_open()
        self._scpi_protocol.write(f":SOUR:FUNC:MODE {function.value}")

    @rpc_method
    def get_source_function(self) -> str:
        """Return the currently selected source function, as its SCPI string value."""
        resp = self._ask(":SOUR:FUNC:MODE?").strip()
        try:
            return SourceFunction(resp).value
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to :SOUR:FUNC:MODE?, got {resp!r}") from exc

    @rpc_method
    def set_fixed_mode(self, function: str | SourceFunction) -> None:
        """Set the source mode of the given function to fixed, i.e. sourcing a constant level.

        Parameters:
            function: Source function to set to fixed mode, SourceFunction.VOLTAGE / "VOLT" or
                       SourceFunction.CURRENT / "CURR".
        """
        function = self._validate_function(function)
        self._check_is_open()
        self._scpi_protocol.write(f":SOUR:{function.value}:MODE FIXED")

    @rpc_method
    def get_function_mode(self, function: str | SourceFunction) -> str:
        """Get the source mode of the given function.

        Parameters:
            function: Source function to query, SourceFunction.VOLTAGE / "VOLT" or
                       SourceFunction.CURRENT / "CURR".

        Returns:
            mode: "FIXED" for fixed-level sourcing mode.
        """
        function = self._validate_function(function)
        return self._ask(f":SOUR:{function.value}:MODE?").strip()

    @rpc_method
    def set_source_voltage(self, voltage: float) -> None:
        """Set the fixed source voltage level.

        Parameters:
            voltage: Source voltage level in Volt.
        """
        self._check_is_open()
        self._scpi_protocol.write(f":SOUR:VOLT {voltage:.6g}")

    @rpc_method
    def get_source_voltage(self) -> float:
        """Return the fixed source voltage level in Volt."""
        return self._ask_float(":SOUR:VOLT?")

    @rpc_method
    def set_source_current(self, current: float) -> None:
        """Set the fixed source current level.

        Parameters:
            current: Source current level in Ampere.
        """
        self._check_is_open()
        self._scpi_protocol.write(f":SOUR:CURR {current:.6g}")

    @rpc_method
    def get_source_current(self) -> float:
        """Return the fixed source current level in Ampere."""
        return self._ask_float(":SOUR:CURR?")

    @rpc_method
    def set_sense_function(self, function: str | SenseFunction) -> None:
        """Set the (single) sense function.

        Parameters:
            function: Sense function, SenseFunction.VOLTAGE / "VOLT:DC" or SenseFunction.CURRENT / "CURR:DC".
        """
        function = function if isinstance(function, SenseFunction) else SenseFunction(function)
        self._check_is_open()
        self._scpi_protocol.write(f":SENS:FUNC '{function.value}'")

    @rpc_method
    def get_sense_function(self) -> SenseFunction:
        """Return the currently selected sense function."""
        resp = self._ask(":SENS:FUNC?").strip()
        first = resp.split(",")[0].strip().strip('"').strip("'")
        try:
            return SenseFunction(first)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to :SENS:FUNC?, got {resp!r}") from exc

    @rpc_method
    def get_measured_voltage(self) -> float:
        """Trigger a measurement and return the _measured_ voltage.

        Voltage must be enabled as sense function and the output must be on.

        Returns:
            voltage: The measured voltage in volts.
        """
        self._check_is_open()
        # Only return the voltage reading, instead of the default voltage, current, resistance, time and status.
        self._scpi_protocol.write(":FORM:ELEM VOLT")
        return self._ask_float(":READ?")

    @rpc_method
    def set_output_state(self, enable: bool) -> None:
        """Enable or disable the instrument output.

        Parameters:
            enable: True to switch the output on, False to switch it off.
        """
        self._check_is_open()
        self._scpi_protocol.write(f":OUTP {'ON' if enable else 'OFF'}")

    @rpc_method
    def get_output_state(self) -> bool:
        """Return True if the output is on, False if it is off.

        Raises:
            QMI_InstrumentException: If the response is not as expected.
        """
        self._check_is_open()
        resp = self._ask(":OUTP?").strip()
        if resp not in ("0", "1"):
            raise QMI_InstrumentException(f"Unexpected response to :OUTP?, got {resp!r}")
        return resp == "1"
