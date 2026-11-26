"""Instrument driver for the Signal Hound BB60C Spectrum Analyzer."""

import logging
import re
from io import StringIO

import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class SignalHound_BB60C(QMI_Instrument):
    """Instrument driver for the Signal Hound BB60C Spectrum Analyzer."""

    _rpc_constants = {"DEFAULT_PORT"}
    _rpc_properties = {"DEFAULT_RESPONSE_TIMEOUT", "RESET_TIMEOUT"}
    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0
    RESET_TIMEOUT = 20.0
    DEFAULT_PORT = 5025

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            context: QMI context that owns this instrument.
            name: Name for this instrument instance.
            transport: QMI transport descriptor for connecting to the analyzer.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"port": self.DEFAULT_PORT})
        self._scpi_protocol = ScpiProtocol(self._transport, default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)

    def _ask_float(self, cmd: str) -> float:
        """Send a query and parse its response as a floating-point value."""
        _logger.debug("[%s] Querying analyzer with %s", self._name, cmd)
        resp = self._scpi_protocol.ask(cmd)
        try:
            value = float(resp)
        except ValueError as err:
            _logger.warning("[%s] Invalid numeric response to %s: %r", self._name, cmd, resp)
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}") from err

        return value

    def _ask_int(self, cmd: str) -> int:
        """Send a query and parse its response as an integer."""
        _logger.debug("[%s] Querying analyzer with %s", self._name, cmd)
        resp = self._scpi_protocol.ask(cmd)
        try:
            return int(resp)
        except ValueError as err:
            _logger.warning("[%s] Invalid integer response to %s: %r", self._name, cmd, resp)
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}") from err

    def _ask_bool(self, cmd: str) -> bool:
        """Send a query and parse its response as a boolean value."""
        _logger.debug("[%s] Querying analyzer with %s", self._name, cmd)
        resp = self._scpi_protocol.ask(cmd)
        value = resp.strip().upper()
        if value in ("1", "ON"):
            return True
        elif value in ("0", "OFF"):
            return False
        else:
            _logger.warning("[%s] Invalid boolean response to %s: %r", self._name, cmd, resp)
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}")

    def _write(self, cmd: str) -> None:
        """Send an SCPI command and record it at debug level."""
        _logger.debug("[%s] Sending analyzer command %s", self._name, cmd)
        self._scpi_protocol.write(cmd)

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        resp = self._scpi_protocol.ask("SYSTem:ERRor?")
        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*0\s*,", resp):
            # Some error occurred.
            _logger.warning("[%s] Analyzer reported an error: %s", self._name, resp)
            raise QMI_InstrumentException(f"Instrument returned error: {resp}")

    def _trigger_and_wait_operation_complete(self, timeout: float | None = None) -> None:
        """Start a sweep and wait for the analyzer's operation-complete response.

        Parameters:
            timeout: Maximum wait in seconds; defaults to ``DEFAULT_RESPONSE_TIMEOUT``.

        Raises:
            QMI_InstrumentException: If the response is not an integer or is not 1.
        """
        timeout = timeout or self.DEFAULT_RESPONSE_TIMEOUT
        _logger.debug("[%s] Starting a sweep and waiting for completion", self._name)
        resp = self._scpi_protocol.ask(":INIT; *OPC?", timeout=timeout)
        try:
            resp_int = int(resp)
        except ValueError as err:
            raise QMI_InstrumentException(f"Unexpected response to wait: {resp!r}") from err

        if resp_int != 1:
            raise QMI_InstrumentException(f"Wait returned error {resp_int}")

    @rpc_method
    def open(self) -> None:
        """Open the connection to the spectrum analyzer."""
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the connection to the spectrum analyzer."""
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def reset(self) -> None:
        """Preset the analyzer and check the instrument error queue.

        The preset operation may take up to ``RESET_TIMEOUT`` seconds.

        Raises:
            QMI_InstrumentException: If the preset does not complete or the analyzer reports an error.
        """
        _logger.info("[%s] Presetting Signal Hound BB60C", self._name)
        resp = self._scpi_protocol.ask("SYST:PRES?", timeout=self.RESET_TIMEOUT)
        try:
            resp_int = int(resp)
        except ValueError as err:
            raise QMI_InstrumentException(f"Unexpected response to reset: {resp!r}") from err

        if resp_int != 1:
            raise QMI_InstrumentException(f"Reset returned error {resp_int}")

        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read and parse the analyzer identification response.

        Returns:
            Identification containing the vendor, model, serial number, and firmware.

        Raises:
            QMI_InstrumentException: If the response does not contain four fields.
        """
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")

        return QMI_InstrumentIdentification(
            vendor=words[0].strip(), model=words[1].strip(), serial=words[2].strip(), version=words[3].strip()
        )

    @rpc_method
    def get_frequency_center(self) -> float:
        """Return the analyzer center frequency in Hz."""
        return self._ask_float(":sense:frequency:center?")

    @rpc_method
    def set_frequency_center(self, center: float) -> None:
        """Set the analyzer center frequency.

        Parameters:
            center: Center frequency in Hz.
        """
        self._write(f":sense:frequency:center {center}")
        self._check_error()

    @rpc_method
    def get_frequency_span(self) -> float:
        """Return the analyzer frequency span in Hz."""
        return self._ask_float(":sense:frequency:span?")

    @rpc_method
    def set_frequency_span(self, span: float) -> None:
        """Set the analyzer frequency span.

        Parameters:
            span: Frequency span in Hz.
        """
        self._write(f":sens:frequency:span {span}")
        self._check_error()

    @rpc_method
    def get_reference_level(self) -> float:
        """Return the analyzer reference level in dBm."""
        return self._ask_float(":sens:power:rf:rlev?")

    @rpc_method
    def set_reference_level(self, level: float) -> None:
        """Set the analyzer reference level.

        Parameters:
            level: Reference level in dBm.
        """
        self._write(f":sens:power:rf:rlev {level}")
        self._check_error()

    @rpc_method
    def set_rbw_auto_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic resolution bandwidth selection.

        Parameters:
            enabled: Whether RBW is selected automatically.
        """
        if enabled:
            self._write(":sens:band:res:auto on")
        else:
            self._write(":sens:band:res:auto off")

        self._check_error()

    @rpc_method
    def set_vbw_auto_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic video bandwidth selection.

        Parameters:
            enabled: Whether VBW is selected automatically.
        """
        if enabled:
            self._write(":sens:band:vid:auto on")
        else:
            self._write(":sens:band:vid:auto off")

        self._check_error()

    @rpc_method
    def set_vbw(self, vbw: float) -> None:
        """Set the video bandwidth.

        Parameters:
            vbw: Video bandwidth in Hz.
        """
        self._write(f":sens:band:vid {vbw}")
        self._check_error()

    @rpc_method
    def set_rbw(self, rbw: float) -> None:
        """Set the resolution bandwidth.

        Parameters:
            rbw: Resolution bandwidth in Hz.
        """
        self._write(f":sens:band:res {rbw}")
        self._check_error()

    @rpc_method
    def set_trace_average_count(self, count: int) -> None:
        """Set the number of averages used for the trace.

        Parameters:
            count: Number of trace averages.
        """
        self._write(f":trac:aver:coun {count}")
        self._check_error()

    @rpc_method
    def set_trace_type(self, trace_type: str) -> None:
        """Set the trace type.

        Parameters:
            trace_type: One of ``off``, ``write``, ``average``, ``maxhold``, ``minhold``, or ``minmax``.

        Raises:
            QMI_InstrumentException: If ``trace_type`` is not supported.
        """
        if trace_type.lower() not in ("off", "write", "average", "maxhold", "minhold", "minmax"):
            raise QMI_InstrumentException(f"Invalid trace type: {trace_type}")

        self._write(f":trac:type {trace_type}")
        self._check_error()

    @rpc_method
    def set_trace_index(self, index: int) -> None:
        """Select a trace for subsequent trace operations.

        Parameters:
            index: Trace index from 1 to 6.

        Raises:
            QMI_InstrumentException: If the trace index is outside the supported range.
        """
        if not (1 <= index <= 6):
            raise QMI_InstrumentException(f"Invalid trace index: {index}")

        self._write(f":trac:sel {index}")
        self._check_error()

    @rpc_method
    def set_trace_update_enabled(self, enabled: bool) -> None:
        """Enable or disable trace updates after each sweep.

        Parameters:
            enabled: Whether the active trace updates after acquisition.
        """
        if enabled:
            self._write(":trac:upd on")
        else:
            self._write(":trac:upd off")

        self._check_error()

    @rpc_method
    def set_trace_display_enabled(self, enabled: bool) -> None:
        """Show or hide the active trace on the analyzer display.

        Parameters:
            enabled: Whether the selected trace is displayed.
        """
        if enabled:
            self._write(":trac:disp on")
        else:
            self._write(":trac:disp off")

        self._check_error()

    @rpc_method
    def get_trace(self) -> tuple[np.ndarray, np.ndarray]:
        """Read the active trace and its corresponding frequency axis.

        Returns:
            A pair of NumPy arrays containing frequency values in Hz and trace power values in dBm.
        """
        trace_csv = self._scpi_protocol.ask(":trace:data?")
        trace_power = np.genfromtxt(StringIO(trace_csv), delimiter=",")
        start_freq = self._ask_float("trace:xstart?")
        step_freq = self._ask_float("trace:xinc?")
        trace_freq = np.arange(trace_power.size) * step_freq + start_freq
        return (trace_freq, trace_power)

    @rpc_method
    def set_mode(self, mode: str) -> None:
        """Set the analyzer mode to spectrum analysis (``SA``) or idle (``IDLE``).

        Parameters:
            mode: Supported mode name, either ``SA`` or ``IDLE``.
        """
        if mode not in ["SA", "IDLE"]:
            _logger.warning("[%s] Ignoring unsupported analyzer mode %r", self._name, mode)
        else:
            self._write(f":inst {mode}")

        self._check_error()

    @rpc_method
    def set_continous_enabled(self, enabled: bool) -> None:
        """Enable or disable continuous measurements.

        Parameters:
            enabled: Whether the analyzer should acquire continuously.
        """
        if enabled:
            self._write(":initiate:continuous on")
        else:
            self._write(":initiate:continuous off")

        self._check_error()

    @rpc_method
    def trigger_sweep_and_wait(self, times: int = 1) -> None:
        """Trigger the requested number of sweeps and wait for each to complete.

        Parameters:
            times: Number of sweeps to perform.
        """
        _logger.info("[%s] Triggering %d analyzer sweep(s)", self._name, times)
        for _ in range(times):
            self._trigger_and_wait_operation_complete()

        self._check_error()

    @rpc_method
    def set_freq_sweep_step(self, step: float) -> None:
        """Set the frequency increment used by center-frequency stepping.

        Parameters:
            step: Frequency step in Hz.
        """
        self._write(f":FREQUENCY:CENTER:STEP {step}")
        self._check_error()
