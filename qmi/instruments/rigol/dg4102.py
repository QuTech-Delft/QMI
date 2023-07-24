"""
Instrument driver for the Rigol DG4102 Function/Arbitrary Waveform Generator.
The instrument class is adapted from the very similar class Rohde und Schwarz SGS100A.
Written by Matthew Weaver and Yanik Herrmann (m.j.weaver@tudelft.nl).
"""

import logging
import re

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Rigol_Dg4102(QMI_Instrument):
    """Instrument driver for the Rigol DG4102 Function/Arbitrary Waveform Generator."""

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 1.0

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 init_source: int = 1
                 ) -> None:
        """Initialize the instrument driver.

        Parameters:
            context:        The QMI context.
            name:           Name for this instrument instance.
            transport:      QMI transport descriptor to connect to the instrument.
            init_source:    The initial source to control. This can be changed via set_source.
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport = create_transport(transport, default_attributes={"port": 5555})
        self._scpi_protocol = ScpiProtocol(self._transport, default_timeout=self._timeout)
        self._channel = init_source

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        super().open()
        self._transport.open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        self._transport.close()
        super().close()

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating point response.

        Parameters:
            cmd: The query string.
        """
        resp = self._scpi_protocol.ask(cmd)
        try:
            return float(resp)
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    def _ask_bool(self, cmd: str) -> bool:
        """Send a query and return a boolean response.
        
        Parameters:
            cmd: The query string.
        """
        resp = self._scpi_protocol.ask(cmd)
        value = resp.strip().upper()
        if value in ("1", "ON"):
            return True
        elif value in ("0", "OFF"):
            return False
        else:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error.
        
        Raises:
            QMI_InstrumentException if response error code is not 0.
        """
        resp = self._scpi_protocol.ask("SYSTem:ERRor?")
        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*0\s*,", resp):
            # Some error occurred.
            raise QMI_InstrumentException("Instrument returned error: {}".format(resp))

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version. 
        
        Returns:
            QMI_InstrumentIdentification instance.
        """
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(resp))
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def set_source(self, new_source: int) -> None:
        """Choose which source channel to control.

        Parameters:
            new_source: The new source channel number.
        """
        self._channel = new_source

    @rpc_method
    def get_source(self) -> int:
        """Return the source channel which is currently controlled

        Returns:
            The current source channel number.
        """
        return self._channel

    @rpc_method
    def get_output_state(self) -> bool:
        """Return True if output is enabled, False if output is disabled.

        Returns:
            output_state: The output state.
        """
        output_state = self._ask_bool(":OUTP{}?".format(self._channel))
        # For some reason the response to OUTP? terminates with '\n\n' instead of the usual '\n'.
        # This clears the extra empty line.
        self._scpi_protocol.ask("")
        return output_state

    @rpc_method
    def set_output_state(self, enable: bool) -> None:
        """Enable or disable output

        Parameters:
            enable: The new output state. True for "ON", False for "OFF".
        """
        self._scpi_protocol.write(":OUTP{} {}".format(self._channel, "ON" if enable else "OFF"))
        self._check_error()

    @rpc_method
    def get_waveform(self) -> str:
        """Return the current waveform.

        Returns:
            The current waveform text.
        """
        cmd = ":SOURce{}:FUNCtion?".format(self._channel)
        return self._scpi_protocol.ask(cmd)

    @rpc_method
    def set_waveform(self, waveform: str) -> None:
        """Set the waveform of a channel.

        Parameters:
            waveform: The new waveform type. Allowed waveforms are:
                      SINusoid|SQUare|RAMP|PULSe|NOISe|USER|HARMonic|CUSTom|DC
        """
        self._scpi_protocol.write(":SOURce{}:FUNCtion {}".format(self._channel, waveform))
        self._check_error()

    @rpc_method
    def get_frequency(self) -> float:
        """Return the current frequency of a channel in Hz.

        Returns:
            The frequency of a channel.
        """
        return self._ask_float(":SOURce{}:FREQ?".format(self._channel))

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """Set the frequency of a channel in Hz.

        Parameters:
            frequency: The new channel frequency.
        """
        self._scpi_protocol.write(":SOURce{}:FREQ {}".format(self._channel, frequency))
        self._check_error()

    @rpc_method
    def get_amplitude(self) -> float:
        """Return the current amplitude of a channel in V.

        Returns:
            The channel amplitude.
        """
        return self._ask_float(":SOURce{}:VOLT?".format(self._channel))

    @rpc_method
    def set_amplitude(self, amplitude: float) -> None:
        """Set the amplitude of a channel in V.

        Parameters:
            amplitude: The new channel amplitude.
        """
        self._scpi_protocol.write(":SOURce{}:VOLT {}".format(self._channel, amplitude))
        self._check_error()

    @rpc_method
    def get_offset(self) -> float:
        """Return the current offset of a channel in V.

        Returns:
            The channel offset voltage.
        """
        return self._ask_float(":SOURce{}:VOLTage:OFFSet?".format(self._channel))

    @rpc_method
    def set_offset(self, offset: float) -> None:
        """Set the offset of a channel in V.

        Parameters:
            offset: The new channel offset voltage.
        """
        self._scpi_protocol.write(":SOURce{}:VOLTage:OFFSet {}".format(self._channel, offset))
        self._check_error()

    @rpc_method
    def get_phase(self) -> float:
        """Return the current phase of a channel in deg.

        Returns:
            The channel phase.
        """
        return self._ask_float(":SOURce{}:PHASe?".format(self._channel))

    @rpc_method
    def set_phase(self, phase: float) -> None:
        """Set the phase of a channel in deg.

        Parameters:
            phase: The new channel phase.
        """
        self._scpi_protocol.write(":SOURce{}:PHASe {}".format(self._channel, phase))
        self._check_error()
