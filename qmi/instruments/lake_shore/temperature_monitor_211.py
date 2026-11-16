"""
Instrument driver for the Lake Shore Model 211 Temperature Monitor.
The device is connected over USB (RS232 adapter) and the serial interface.

The manual (section 4.1.5, Message Flow Control) requires that no new communication is started within 50 ms after
a command has been transmitted or a query response has been received, and that communication is not initiated more
than 20 times per second. The driver enforces this by waiting, before each command or query, until at least
``COMMAND_GUARD_TIME`` seconds have passed since the previous communication completed. Since every communication then
starts at least 50 ms after the previous one, the 20 messages per second limit is also respected. The instrument
typically needs around 10 ms to begin a response, which is covered by the response timeout.
"""

import logging
import time

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class LakeShore_Model211(QMI_Instrument):
    """Instrument driver for the Lake Shore Model 211 Temperature Monitor.

    Attributes:
        DEFAULT_RESPONSE_TIMEOUT: Default response timeout in seconds.
        COMMAND_GUARD_TIME: Minimum idle time in seconds between the end of one communication and the start of the
            next one, as required by the manual.
    """

    _rpc_constants = {"DEFAULT_RESPONSE_TIMEOUT", "COMMAND_GUARD_TIME"}

    DEFAULT_RESPONSE_TIMEOUT = 1.0
    COMMAND_GUARD_TIME = 0.05

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the monitor with a QMI context and serial transport.

        Parameters:
            context: QMI context that owns this instrument.
            name: Name used to identify this instrument in QMI.
            transport: Transport string for the USB serial adapter.
        """
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": 9600, "bytesize": 7, "parity": "E", "stopbits": 1}
        )
        self._scpi_protocol = ScpiProtocol(
            self._transport,
            command_terminator="\r\n",
            response_terminator="\r\n",
            default_timeout=self.DEFAULT_RESPONSE_TIMEOUT,
        )
        # Monotonic time at which the last communication with the instrument completed.
        self._last_communication_end = float("-inf")

    def _wait_for_guard_time(self) -> None:
        """Sleep until the guard time since the end of the previous communication has passed."""
        remaining = self._last_communication_end + self.COMMAND_GUARD_TIME - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    def _write(self, cmd: str) -> None:
        """Send a command to the monitor, respecting the message flow control rules.

        Parameters:
            cmd: SCPI command.
        """
        self._wait_for_guard_time()
        try:
            self._scpi_protocol.write(cmd)
        finally:
            self._last_communication_end = time.monotonic()

    def _ask(self, cmd: str) -> str:
        """Send a query to the monitor and return its response, respecting the message flow control rules.

        Parameters:
            cmd: SCPI query command.

        Returns:
            Response from the monitor.
        """
        self._wait_for_guard_time()
        try:
            return self._scpi_protocol.ask(cmd)
        finally:
            self._last_communication_end = time.monotonic()

    def _ask_float(self, cmd: str) -> float:
        """Send a query and parse its response as a floating-point value.

        Parameters:
            cmd: SCPI query command.

        Returns:
            Numeric response from the monitor.

        Raises:
            QMI_InstrumentException: If the response is not a valid float.
        """
        _logger.debug("[%s] Querying monitor with %s", self._name, cmd)
        resp = self._ask(cmd)
        try:
            value = float(resp)
        except ValueError as err:
            _logger.warning("[%s] Invalid numeric response to %s: %r", self._name, cmd, resp)
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}") from err
        _logger.debug("[%s] %s returned %s", self._name, cmd, value)
        return value

    @rpc_method
    def open(self) -> None:
        """Open the serial connection to the temperature monitor."""
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the serial connection to the temperature monitor."""
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read and parse the monitor identification response.

        Returns:
            Identification containing the vendor, model, serial number, and firmware.

        Raises:
            QMI_InstrumentException: If the response does not contain four fields.
        """
        _logger.debug("[%s] Querying instrument identification", self._name)
        resp = self._ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            _logger.warning("[%s] Unexpected response to *IDN?: %r", self._name, resp)
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")
        return QMI_InstrumentIdentification(
            vendor=words[0].strip(), model=words[1].strip(), serial=words[2].strip(), version=words[3].strip()
        )

    @rpc_method
    def reset(self) -> None:
        """Send the standard SCPI reset command to the monitor."""
        _logger.info("[%s] Resetting temperature monitor", self._name)
        return self._write("*RST")

    @rpc_method
    def get_status(self) -> str:
        """Read the monitor's status register as a string."""
        _logger.debug("[%s] Reading monitor status register", self._name)
        return self._ask("RDGST?")

    @rpc_method
    def get_error(self) -> bool:
        """Return whether the monitor's status register reports an error."""
        if self.get_status() != "000":
            _logger.warning("[%s] Monitor status register reports an error", self._name)
            return True
        else:
            return False

    @rpc_method
    def get_temperature_celsius(self) -> float:
        """Read the measured temperature in degrees Celsius."""
        return self._ask_float("CRDG?")

    @rpc_method
    def get_temperature_fahrenheit(self) -> float:
        """Read the measured temperature in degrees Fahrenheit."""
        return self._ask_float("FRDG?")

    @rpc_method
    def get_temperature_kelvin(self) -> float:
        """Read the measured temperature in kelvin."""
        return self._ask_float("KRDG?")

    @rpc_method
    def get_sensor_units_input(self) -> float:
        """Read the sensor input in the units defined by its input curve."""
        return self._ask_float("SRDG?")

    @rpc_method
    def get_input_type(self) -> str:
        """Read the configured sensor input type."""
        _logger.debug("[%s] Reading configured sensor input type", self._name)
        return self._ask("INTYPE?")

    @rpc_method
    def get_input_curve(self) -> str:
        """Read the number of the configured sensor input curve."""
        _logger.debug("[%s] Reading configured sensor input curve", self._name)
        return self._ask("INCRV?")

    @rpc_method
    def get_alarm(self) -> str:
        """Read the monitor's alarm configuration and state."""
        _logger.debug("[%s] Reading alarm configuration and state", self._name)
        return self._ask("ALARM?")
