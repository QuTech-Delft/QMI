"""Instrument driver for the Siglent SSA3000X spectrum analyzer."""

import logging
import time
from typing import List, Tuple

import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport


_logger = logging.getLogger(__name__)


class SSA3000X(QMI_Instrument):
    """Instrument driver for the Siglent SSA3000X spectrum analyzer."""

    # trace format constants
    _ASCii = "ASCii"
    _FLOAT = "REAL"
    _TRACE_FORMATS = [_ASCii, _FLOAT]

    _RESP_TERMINATOR = "\n"  # Responses have this unconventional terminator
    _TIMEOUT = 2.0  # Can't find value in datasheet. This is best guess, based on testing.

    _CHANNEL_COUNT = 4

    def __init__(self, context: QMI_Context, name: str, transport_descr: str):
        """ """
        super().__init__(context, name)

        self._transport = create_transport(transport_descr)
        self._scpi = ScpiProtocol(transport=self._transport,
                                  response_terminator=self._RESP_TERMINATOR,
                                  default_timeout=self._TIMEOUT)

    def _ask(self, *args, **kwargs) -> str:
        """Helper method to cleanup up the data from the SSA3000X"""
        return self._scpi.ask(*args, **kwargs).replace('\0', '')

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to instrument")
        self._transport.open()

        time.sleep(self._TIMEOUT)
        self._transport.discard_read()  # discard welcome message

        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to instrument")
        super().close()
        self._transport.close()

    @rpc_method
    def get_id(self) -> str:
        """ Query device identification string.

        Returns:
            Device identification string.
        """
        return self._ask("*IDN?", discard=True)

    @rpc_method
    def get_freq_span(self) -> float:
        """ Get the frequency span.

        Returns:
            Frequency span in Hz.
        """
        resp = self._ask(":FREQ:SPAN?", discard=True)
        try:
            return float(resp)
        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid frequency span, received {resp!r}.") from err

    @rpc_method
    def set_freq_span(self, span_freq: float) -> None:
        """ Sets the frequency span.

        Note:
            Setting the span to 0 Hz puts the analyzer into zero span.

        Parameters:
            span_freq: Frequency span in Hz [0 or 100 to 3.2e9].
        """
        if not (span_freq == 0. or 100. <= span_freq <= 3.2e9):
            raise ValueError(f"Invalid frequency span {span_freq}. Must be 0, or between 100 and 3.2e9.")
        
        self._scpi.write(f":FREQ:SPAN {span_freq/1e9:1.9f} GHz")

    @rpc_method
    def get_freq_center(self) -> float:
        """ Get the center frequency.

        Returns:
            Center frequency in Hz.
        """
        resp = self._ask(":FREQ:CENT?", discard=True)
        try:
            return float(resp)
        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid center frequency, received {resp!r}.") from err

    @rpc_method
    def set_freq_center(self, center_freq: float) -> None:
        """ Sets the center frequency of the spectrum analyzer.

        Parameters:
            center_freq: Center frequency in Hz. If zero span, center frequency can be 0 ~ 3.2 GHz,
                         else 50 Hz ~ 3.199999950 GHz.
        """
        # Frequency span determines range check.
        if self.get_freq_span() == 0:
            if not 0 <= center_freq <= 3.2e9:
                raise ValueError(f"Device has zero span. Center frequency must be between 0 Hz and 3.2 GHz, but is {center_freq}!")
        else:
            if not 50 <= center_freq <= 3.19999995e9:
                raise ValueError(f"Center frequency must be between 50 Hz and 3.199999950 GHz, but is {center_freq}!")

        self._scpi.write(f":FREQ:CENT {center_freq/1e9:1.9f} GHz")

    @rpc_method
    def get_freq_start(self) -> float:
        """ Get the start frequency.

        Returns:
            Start frequency in Hz.
        """
        resp = self._ask(":FREQ:STAR?", discard=True)
        try:
            return float(resp)
        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid start frequency, received {resp!r}.") from err

    @rpc_method
    def get_freq_stop(self) -> float:
        """ Get the stop frequency.

        Returns:
            Stop frequency in Hz.
        """
        resp = self._ask(":FREQ:STOP?", discard=True)
        try:
            return float(resp)
        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid stop frequency, received {resp!r}.") from err

    @rpc_method
    def get_trace_format(self) -> str:
        """ Get the format of the trace data.

        Returns:
            "REAL": single precision floating point values
            "ASCii": ASCii string representation of values
        """
        resp = self._ask(":FORM?", discard=True)
        if resp not in self._TRACE_FORMATS:
            raise QMI_InstrumentException(f"{resp!r} is not a acceptable format {self._TRACE_FORMATS}.")
        return resp

    @rpc_method
    def get_trace(self, channel: int) -> List[float]:
        """ Retrieve trace data from specified channel.

        Parameters:
            Channel for which trace should be retreived.

        Returns:
            The trace data as a list of floats.
        """
        self._validate_channel(channel)
        # Check trace format
        fmt = self.get_trace_format()
        if fmt != self._ASCii:
            raise QMI_InstrumentException(f"Trace format should be {self._ASCii!r}, not {fmt!r}")
        # Read trace data
        resp = self._ask(f":TRAC:DATA? {channel}", discard=True)
        try:
            values_str = resp.split(',')[:-1]  # strip the trailing ','
            return [float(val) for val in values_str]
        except ValueError as err:
            # Raise if either split() or float() fails
            raise QMI_InstrumentException("Trace data could not be coverted to list of floats.") from err

    @rpc_method
    def get_spectrum(self, channel: int) -> Tuple[np.ndarray, np.ndarray]:
        """ Retrieve spectrum data from the specified channel.

        Arguments:
            Channel for which spectrum should be retreived.

        Returns:
            Tuple containing the frequency and amplitude data of the trace of the specified channel.
        """
        self._validate_channel(channel)

        start = self.get_freq_start()
        stop = self.get_freq_stop()
        trace = self.get_trace(channel)

        if start >= stop:
            raise QMI_InstrumentException(f"Start frequency ({start}) is greater or equal to stop frequency ({stop})!")

        if len(trace) == 0:
            raise QMI_InstrumentException("Zero trace data received!")

        ampl = np.array(trace)
        freq = np.linspace(start, stop, len(ampl))

        return freq, ampl

    def _validate_channel(self, channel: int):
        if not 1 <= channel <= self._CHANNEL_COUNT:
            raise QMI_UsageException(f"Channel has to be between 1 and {self._CHANNEL_COUNT}, but is {channel}.")
