"""Instrument driver for the AimTTi TGF3000 Series and TGF4000 Series Function Generator / Frequency Counter."""

import enum
import logging
import math
import time
from typing import NamedTuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class FrequencyMeasurement(NamedTuple):
    """Frequency measurement produced by the instrument.

    Attributes:
        timestamp: Approximate POSIX timestamp of measurement.
        frequency: Measured frequency in Hz.
    """
    timestamp: float
    frequency: float


class WaveformType(enum.Enum):
    """Waveform types."""
    SINE = "SINE"
    SQUARE = "SQUARE"
    RAMP = "RAMP"
    NOISE = "NOISE"


class CounterInputChannel(enum.Enum):
    """Counter input channels."""
    TRIG_IN = "DC"
    REF_IN = "AC"


class TT_TGF_3000_4000_Series(QMI_Instrument):
    """Instrument driver for the TGF3000 and TGF4000 Series function generators.

    This driver has been tested with TGF3162 and TGF4242.
    It probably works with all TGF3000 and TGF4000 Series instruments.

    This driver supports only a subset of the functionality of the instrument.
    """

    # Instrument should respond within 4 seconds.
    RESPONSE_TIMEOUT = 4.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver.

        To access the instrument via Ethernet, provide a transport descriptor like::
          "tcp:172.16.0.100".

        This driver does not support connecting to the instrument via USB.

        Parameters:
            context:    QMI_Context instance.
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor for the SCPI channel.
        """
        super().__init__(context, name)

        self._scpi_transport = create_transport(transport, default_attributes={"port": 9221})
        self._scpi_protocol = ScpiProtocol(self._scpi_transport,
                                           command_terminator="\n",
                                           response_terminator="\r\n",
                                           default_timeout=self.RESPONSE_TIMEOUT)

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._scpi_transport.open()
        try:
            # Clear error queue to avoid reporting stale errors.
            self._scpi_protocol.write("*CLS")
        except OSError:
            self._scpi_transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._scpi_transport.close()

    def _write(self, cmd: str) -> None:
        """Send a SCPI command."""
        self._scpi_protocol.write(cmd)

    def _ask(self, cmd: str) -> str:
        """Send an SCPI command, then read and return the response."""
        return self._scpi_protocol.ask(cmd)

    @staticmethod
    def _check_channel(channel: int) -> None:
        """Check that the channel number is valid."""
        if channel not in (1, 2):
            raise ValueError(f"Invalid channel number {channel!r}")

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""

        # Read error queue.
        resp = self._ask("EER?")

        # Extract error code; 0 means no error occurred.
        try:
            error_code = int(resp)
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response to 'EER?': {resp!r}")

        if error_code != 0:
            # Report error.
            raise QMI_InstrumentException(f"Instrument returned error code {error_code}")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning most settings to defaults."""
        self._write("*CLS")
        self._write("*RST")
        self._check_error()

    @rpc_method
    def set_output_enabled(self, channel: int, enable: bool) -> None:
        """Enable or disable the specified output channel.

        Parameters:
            channel: Channel index (1 or 2).
            enable:  True to enable output, False to disable.
        """
        self._check_channel(channel)
        arg = "ON" if enable else "OFF"
        self._write(f"CHN {channel};OUTPUT {arg}")
        self._check_error()

    @rpc_method
    def set_output_inverted(self, channel: int, invert: bool) -> None:
        """Enable or disable inverted output.

        Parameters:
            channel: Channel index (1 or 2).
            invert:  True to enable inverted output; False to disable.
        """
        self._check_channel(channel)
        arg = "INVERT" if invert else "NORMAL"
        self._write(f"CHN {channel};OUTPUT {arg}")
        self._check_error()

    @rpc_method
    def set_output_load_impedance(self, channel: int, impedance: float) -> None:
        """Configure the assumed load impedance.

        Note: The actual output impedance of the instrument is fixed at 50 Ohm.
        This command configures the assumed impedance of the load that is
        connected to the output. This affects the calculation of output voltage levels.

        Parameters:
            channel:    Channel index (1 or 2).
            impedance:  Assumed load impedance in Ohm, range 1 to 10000, or `math.inf` to assume open circuit.
        """
        self._check_channel(channel)
        arg = "OPEN" if math.isinf(impedance) else f"{impedance:.0f}"
        self._write(f"CHN {channel};ZLOAD {arg}")
        self._check_error()

    @rpc_method
    def set_waveform(self, channel: int, waveform: WaveformType) -> None:
        """Set waveform type.

        This driver currently supports only a subset of the waveforms

        This command may fail if the selected waveform does not support
        the current frequency. In that case, the frequency must first
        be adjusted by calling `set_frequency()`.

        Parameters:
            channel:  Channel index (1 or 2).
            waveform: Waveform type (a `WaveformType.XXX` constant).
        """
        self._check_channel(channel)
        arg = WaveformType(waveform).value
        self._write(f"CHN {channel};WAVE {arg}")
        self._check_error()

    @rpc_method
    def set_frequency(self, channel: int, frequency: float) -> None:
        """Change the output frequency.

        This function is only supported for waveform types SINE, SQUARE and RAMP.

        Parameters:
            channel:   Channel index (1 or 2).
            frequency: Frequency in Hz.
        """
        self._check_channel(channel)
        self._write(f"CHN {channel};FREQ {frequency:.6f}")
        self._check_error()

    @rpc_method
    def set_square_duty_cycle(self, channel: int, duty_cycle: float) -> None:
        """Set the duty cycle of the square wave.

        This function is only supported for waveform type SQUARE.

        Parameters:
            channel:    Channel index (1 or 2).
            duty_cycle: Duty cycle as a percentage between  0.0 and 100.0;
                        actual range also depends on the frequency.
        """
        self._check_channel(channel)
        self._write(f"CHN {channel};SQRSYMM {duty_cycle:.3f}")
        self._check_error()

    @rpc_method
    def set_ramp_symmetry(self, channel: int, symmetry: float) -> None:
        """Set the symmetry of the ramp waveform.

        The symmetry represents the duration of the rising edge as a percentage
        of the waveform period.

        Symmetry level 50% means a symmetric triangular wave where rising edge
        and falling edge have the same duration.
        Symmetry level 0% means instantaneous rise followed by slow falling edge.
        Symmetry level 100% means slow rising edge followed by instantaneous drop.

        This function is only supported for waveform type RAMP.

        Parameters:
            channel:   Channel index (1 or 2).
            symmetry:  Symmetry as a percentage in range 0.0 to 100.0.
        """
        self._check_channel(channel)
        self._write(f"CHN {channel};RMPSYMM {symmetry:.3f}")
        self._check_error()

    @rpc_method
    def set_amplitude(self, channel: int, amplitude: float, offset: float) -> None:
        """Set output amplitude and offset.

        Note that both amplitude and offset are configured with respect to
        an assumed output load impedance. If the configured impedance does not
        match the actual load impedance, the actual output voltage will not
        match the configured voltage.

        Parameters:
            channel:   Channel index (1 or 2).
            amplitude: Peak-to-peak signal amplitude in Vpp.
            offset:    Offset level in Volt.
        """
        self._check_channel(channel)
        self._write(f"CHN {channel};AMPL {amplitude:.3f};DCOFFS {offset:.3f}")
        self._check_error()

    @rpc_method
    def set_phase(self, channel: int, phase: float) -> None:
        """Set the phase offset of the waveform.

        Parameters:
            channel:    Channel index (1 or 2).
            phase:      Phase offset in degrees (range 0.0 to 360.0).
        """
        self._check_channel(channel)
        self._write(f"CHN {channel};PHASE {phase:.3f}")
        self._check_error()

    @rpc_method
    def get_external_reference_enabled(self) -> bool:
        """Return True if the external reference clock input is selected."""
        resp = self._ask("CLKSRC?")
        if resp.strip().upper() == "EXT":
            return True
        elif resp.strip().upper() == "INT":
            return False
        raise QMI_InstrumentException(f"Unexpected response to CLKSRC?, got {resp!r}")

    @rpc_method
    def set_external_reference_enabled(self, enable: bool) -> None:
        """Enable or disable external 10 MHz reference clock input.

        Parameters:
            enable: True to enable the external reference clock input;
                    False to select the internal reference clock.
        """
        arg = "EXT" if enable else "INT"
        self._write(f"CLKSRC {arg}")
        self._check_error()

    @rpc_method
    def set_counter_enabled(self, enable: bool) -> None:
        """Enable or disable the frequency counter function.

        Parameters:
            enable: True to enable the frequency counter; False to disable.
        """
        arg = "ON" if enable else "OFF"
        self._write(f"CNTRSWT {arg}")
        self._check_error()

    @rpc_method
    def set_counter_input(self, input: CounterInputChannel) -> None:
        """Select the counter input channel.

        Parameters:
            input: `CounterInputChannel.TRIG_IN` or `CounterInputChannel.REF_IN`.
        """
        arg = CounterInputChannel(input).value
        self._write(f"CNTRCPLNG {arg}")
        self._check_error()

    @rpc_method
    def read_frequency(self) -> FrequencyMeasurement:
        """Read the currently measured counter value.

        This function only supports frequency measurement mode.
        The alternative measurement modes (period, width and duty-cycle) are
        not supported.

        Returns:
            Measured frequency as a `FrequencyMeasurement` tuple.
        """

        resp = self._ask("CNTRVAL?")
        timestamp = time.time()

        if not resp.endswith("Hz"):
            raise QMI_InstrumentException(
                f"Unexpected response to 'CNTRVAL?': {resp!r}. Is counter in frequency mode?")

        try:
            # Strip "Hz" suffix and convert to floating point.
            frequency = float(resp[:-2])
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response to 'CNTRVAL?': {resp!r}")

        return FrequencyMeasurement(timestamp, frequency)

    @rpc_method
    def set_local(self) -> None:
        """Switch the instrument to local mode.

        Every remote command or query causes the instrument to enter remote mode.
        In remote mode, most front-panel keys are not functional.

        This function returns the instrument to `local` mode.
        It is equivalent to pushing the "LOCAL" button on the front panel.
        """
        self._write("LOCAL")


class TT_TGF3162(TT_TGF_3000_4000_Series):
    """Instrument driver for the AimTTi TGF3162 signal generator / frequency counter."""
    pass
