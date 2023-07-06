"""
Instrument driver for the Tektronix AFG31000 series arbitrary function generator.
"""

import enum
import logging
import math
import re
from typing import Tuple, Type, TypeVar, Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport


# Type variable.
_EnumTypeVar = TypeVar("_EnumTypeVar", bound=enum.Enum)

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Waveform(enum.Enum):
    """Waveform shape."""
    SINE = "SIN"
    SQUARE = "SQU"
    PULSE = "PULS"
    RAMP = "RAMP"
    NOISE = "PRN"
    DC = "DC"
    SINC = "SINC"
    GAUSS = "GAUS"
    LORENTZ = "LOR"
    EXP_RISE = "ERIS"
    EXP_DECAY = "EDEC"
    HAVERSINE = "HAV"
    EMEMORY = "EMEM"
    EFILE = "EFIL"


class BurstMode(enum.Enum):
    """Burst mode."""
    TRIGGERED = "TRIG"
    GATED = "GAT"


class TriggerEdge(enum.Enum):
    """Trigger edge."""
    RISING = "POS"
    FALLING = "NEG"


class Tektronix_AFG31000(QMI_Instrument):
    """Instrument driver for the Tektronix AFG31000 series arbitrary function generator.

    This driver has been tested with the AFG31022 but probably works with all AFG31000 series instruments.

    This driver communicates with the instrument via USB or via Ethernet.
    """

    # Response timeout in seconds.
    RESPONSE_TIMEOUT = 5.0

    # The instrument returns a value above this threshold to indicate infinity.
    _INFINITY_THRESHOLD = 1.0e30

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        To connect to the instrument via Ethernet, specify transport descriptor
          "tcp:<IP-address>".

        To connect to the instrument via USB, specify transport descriptor
          "usbtmc:vendorid=0x0699:productid=0x0356:serialnr=....".

        Parameters:
            context:    QMI context.
            name:       Name for this instrument instance.
            transport:  Transport descriptor to access this instrument.
        """

        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"port": 5025})
        self._scpi_transport = ScpiProtocol(self._transport, default_timeout=self.RESPONSE_TIMEOUT)

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()
        try:
            # Clear error queue to avoid reporting stale errors.
            self._scpi_transport.write("*CLS")
        except OSError:
            self._transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _ask_int(self, cmd: str) -> int:
        """Query an integer value from the instrument."""
        resp = self._scpi_transport.ask(cmd)
        resp = resp.strip()
        try:
            return int(resp)
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response to {cmd!r}: {resp!r}")

    def _ask_float(self, cmd: str) -> float:
        """Query a floating point value from the instrument."""
        resp = self._scpi_transport.ask(cmd)
        resp = resp.strip()
        try:
            return float(resp)
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response to {cmd!r}: {resp!r}")

    def _ask_enum(self, cmd: str, typ: Type[_EnumTypeVar]) -> _EnumTypeVar:
        """Query a mnemonic response from the instrument."""
        resp = self._scpi_transport.ask(cmd)
        resp = resp.strip()
        try:
            return typ(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response to {cmd!r}: {resp!r}")

    @staticmethod
    def _check_channel(channel: int) -> None:
        """Check that the channel number is valid."""
        if channel not in (1, 2):
            raise ValueError(f"Invalid channel number {channel!r}")

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""

        # Wait until previous command finished.
        self._scpi_transport.ask("*OPC?")

        # Read error queue.
        resp = self._scpi_transport.ask("SYST:ERR?")
        if not re.match(r"^\s*[+-]?0\s*,", resp):
            # An error occurred. Clear the error queue, in case there are more pending errors.
            self._scpi_transport.write("*CLS")
            # Report the error.
            raise QMI_InstrumentException(f"Instrument returned error: {resp}")

    @rpc_method
    def reset(self) -> None:
        """Reset most instrument settings to factory defaults.

        This function is equivalent to the "default" button on the front panel.
        """
        self._scpi_transport.write("*CLS")
        self._scpi_transport.write("*RST")
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._scpi_transport.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to '*IDN?': {resp!r}")
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def get_external_reference_enabled(self) -> bool:
        """Return True if the external reference clock input is selected."""
        class RefSource(enum.Enum):
            """Enum for type of RF reference source."""
            INTERNAL = "INT"
            EXTERNAL = "EXT"
        refsource = self._ask_enum("SOURCE:ROSCILLATOR:SOURCE?", RefSource)
        return refsource == RefSource.EXTERNAL

    @rpc_method
    def set_external_reference_enabled(self, enable: bool) -> None:
        """Choose internal or external reference clock source.

        Parameters:
            enable: True to select the external 10 MHz reference clock input.
                    False to select the internal reference source.
        """
        arg = "EXT" if enable else "INT"
        self._scpi_transport.write(f"SOURCE:ROSCILLATOR:SOURCE {arg}")
        self._check_error()

    @rpc_method
    def get_output_enabled(self, channel: int) -> bool:
        """Return True if the specified output is enabled.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            True if the specified output is enabled, False if disabled.
        """
        self._check_channel(channel)
        resp = self._ask_int(f"OUTPUT{channel}:STATE?")
        return resp != 0

    @rpc_method
    def set_output_enabled(self, channel: int, enable: bool) -> None:
        """Enable or disable the specified output channel.

        Parameters:
            channel: Output channel (1 or 2).
            enable:  True to enable the output, False to disable.
        """
        self._check_channel(channel)
        arg = 1 if enable else 0
        self._scpi_transport.write(f"OUTPUT{channel}:STATE {arg}")
        self._check_error()

    @rpc_method
    def get_waveform(self, channel: int) -> Waveform:
        """Return the current waveform for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            A `Waveform` constant.
        """
        self._check_channel(channel)
        return self._ask_enum(f"SOURCE{channel}:FUNCTION:SHAPE?", Waveform)

    @rpc_method
    def set_waveform(self, channel: int, waveform: Waveform) -> None:
        """Set the waveform for the specified channel.

        Selecting a waveform that is not compatible with the current modulation type,
        will cause the modulation type to be set to `Continuous`.

        Parameters
            channel: Output channel (1 or 2).
            waveform: A `Waveform` constant specifying the new waveform.
                      Waveforms `EMEMORY` and `EFILE` are currently not supported by this driver.
        """
        self._check_channel(channel)
        arg = Waveform(waveform).value
        self._scpi_transport.write(f"SOURCE{channel}:FUNCTION:SHAPE {arg}")
        self._check_error()

    @rpc_method
    def get_sweep_enabled(self, channel: int) -> bool:
        """Return True if frequency sweeping is enabled for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            True if frequency sweeping is enabled, False if disabled.
        """
        class FrequencyMode(enum.Enum):
            """Enum for type of frequency mode."""
            CW = "CW"
            SWEEP = "SWE"
        self._check_channel(channel)
        mode = self._ask_enum(f"SOURCE{channel}:FREQUENCY:MODE?", FrequencyMode)
        return mode == FrequencyMode.SWEEP

    @rpc_method
    def get_continuous_frequency(self, channel: int) -> float:
        """Return the frequency of the output waveform.

        This command is not available when frequency sweeping is enabled.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            Output frequency in Hz.
        """
        self._check_channel(channel)
        return self._ask_float(f"SOURCE{channel}:FREQUENCY:CW?")

    @rpc_method
    def set_continuous_frequency(self, channel: int, frequency: float) -> None:
        """Set the channel to fixed frequency mode with the specified frequency.

        This command disables frequency sweeping and enables fixed frequency (continuous) mode.

        Parameters:
            channel: Output channel (1 or 2).
            frequency: New output frequency in Hz.
        """
        self._check_channel(channel)
        self._scpi_transport.write(f"SOURCE{channel}:FREQUENCY:MODE CW")
        self._scpi_transport.write(f"SOURCE{channel}:FREQUENCY:CW {frequency:.6f}")
        self._check_error()

    @rpc_method
    def get_amplitude(self, channel: int) -> Tuple[float, float]:
        """Return the current output amplitude levels.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            Tuple (low, high) of output levels in Volt.
        """
        self._check_channel(channel)
        vlow = self._ask_float(f"SOURCE{channel}:VOLTAGE:LEVEL:LOW?")
        vhigh = self._ask_float(f"SOURCE{channel}:VOLTAGE:LEVEL:HIGH?")
        return (vlow, vhigh)

    @rpc_method
    def set_amplitude(self, channel: int, vlow: float, vhigh: float) -> None:
        """Set the output amplitude levels for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).
            vlow:    Low output amplitude in Volt.
            vhigh:   High output amplitude in Volt.
        """
        self._check_channel(channel)
        self._scpi_transport.write(f"SOURCE{channel}:VOLTAGE:LEVEL:LOW {vlow:.4f}")
        self._scpi_transport.write(f"SOURCE{channel}:VOLTAGE:LEVEL:HIGH {vhigh:.4f}")
        self._check_error()

    @rpc_method
    def get_pulse_duty_cycle(self, channel: int) -> float:
        """Return the current pulse duty cycle for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            Duty cycle as a percentage between 0.0 and 100.0.
        """
        self._check_channel(channel)
        return self._ask_float(f"SOURCE{channel}:PULSE:DCYCLE?")

    @rpc_method
    def set_pulse_duty_cycle(self, channel: int, duty_cycle: float) -> None:
        """Set the pulse duty cycle for the specified channel.

        This function also configures the instrument to hold the duty cycle fixed
        when the pulse frequency is changed (thus changing the pulse width).

        Parameters:
            channel: Output channel (1 or 2).
            duty_cycle: New duty cycle as a percentage between 0.0 and 100.0.
                        The valid range also depends on the pulse frequency
                        and the transition times.
        """
        self._check_channel(channel)
        self._scpi_transport.write(f"SOURCE{channel}:PULSE:HOLD DUTY")
        self._scpi_transport.write(f"SOURCE{channel}:PULSE:DCYCLE {duty_cycle:.6f}")
        self._check_error()

    @rpc_method
    def get_pulse_delay(self, channel: int) -> float:
        """Return the current pulse delay for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            Pulse lead delay in seconds.
        """
        self._check_channel(channel)
        return self._ask_float(f"SOURCE{channel}:PULSE:DELAY?")

    @rpc_method
    def set_pulse_delay(self, channel: int, delay: float) -> None:
        """Set pulse delay for the specified channel.

        The minimum allowed pulse delay is 0.
        The maximum allowed pulse delay depends on the pulse period and duty cycle.
        The pulse delay must be less than the pulse period.
        In burst mode, the delayed pulse must end before a non-delayed next pulse would have started.

        Parameters:
            channel: Output channel (1 or 2).
            delay:   New pulse lead delay in seconds.
        """
        self._check_channel(channel)
        self._scpi_transport.write(f"SOURCE{channel}:PULSE:DELAY {delay:.11f}")
        self._check_error()

    @rpc_method
    def get_burst_mode(self, channel: int) -> BurstMode:
        """Return the current burst mode for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            `BurstMode.TRIGGERED` or `BurstMode.GATED`.
        """
        self._check_channel(channel)
        return self._ask_enum(f"SOURCE{channel}:BURST:MODE?", BurstMode)

    @rpc_method
    def set_burst_mode(self, channel: int, mode: BurstMode) -> None:
        """Set the burst mode of the specified channel.

        Parameters:
            channel: Output channel (1 or 2).
            mode:    Burst mode (`BurstMode.TRIGGERED` or `BurstMode.GATED`).
        """
        self._check_channel(channel)
        arg = BurstMode(mode).value
        self._scpi_transport.write(f"SOURCE{channel}:BURST:MODE {arg}")
        self._check_error()

    @rpc_method
    def get_burst_count(self, channel: int) -> Union[int, float]:
        """Return the number of cycles in burst mode.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            Number of cycles per output burst, or `math.inf` for infinite cycles.
        """
        self._check_channel(channel)
        val = self._ask_float(f"SOURCE{channel}:BURST:NCYCLES?")
        if val > self._INFINITY_THRESHOLD:
            return math.inf
        return int(val)

    @rpc_method
    def set_burst_count(self, channel: int, cycles: Union[int, float]) -> None:
        """Set the number of cycles in burst mode.

        Parameters:
            channel: Output channel (1 or 2).
            cycles:  Number of cycles, range 1 to 10**6, or `math.inf` for infinite cycles.
        """
        self._check_channel(channel)
        arg = "INF" if math.isinf(cycles) else str(cycles)
        self._scpi_transport.write(f"SOURCE{channel}:BURST:NCYCLES {arg}")
        self._check_error()

    @rpc_method
    def get_burst_enabled(self, channel: int) -> bool:
        """Return True if burst mode is enabled for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            True if burst mode is enabled for the specified channel, False if disabled.
        """
        self._check_channel(channel)
        resp = self._ask_int(f"SOURCE{channel}:BURST:STATE?")
        return resp != 0

    @rpc_method
    def set_burst_enabled(self, channel: int, enable: bool) -> None:
        """Enable or disable burst mode for the specified channel.

        Parameters:
            channel: Output channel (1 or 2).
            enable:  True to enable burst mode, False to disable.
        """
        self._check_channel(channel)
        arg = 1 if enable else 0
        self._scpi_transport.write(f"SOURCE{channel}:BURST:STATE {arg}")
        self._check_error()

    @rpc_method
    def get_external_trigger_enabled(self) -> bool:
        """Return True if the external trigger input is enabled."""
        class TriggerSource(enum.Enum):
            """Enum for type of trigger source."""
            TIMER = "TIM"
            EXTERNAL = "EXT"
        trigger = self._ask_enum("TRIGGER:SOURCE?", TriggerSource)
        return trigger == TriggerSource.EXTERNAL

    @rpc_method
    def set_external_trigger_enabled(self, enable: bool) -> None:
        """Enable or disable the external trigger input.

        Parameters:
            enable: True to select the external trigger input.
                    False to select the internal timer as trigger source.
        """
        arg = "EXT" if enable else "TIM"
        self._scpi_transport.write(f"TRIGGER:SOURCE {arg}")
        self._check_error()

    @rpc_method
    def get_trigger_edge(self) -> TriggerEdge:
        """Return the current trigger edge.

        Returns:
            `TriggerEdge.RISING` or `TriggerEdge.FALLING`.
        """
        return self._ask_enum("TRIGGER:SLOPE?", TriggerEdge)

    @rpc_method
    def set_trigger_edge(self, edge: TriggerEdge) -> None:
        """Set the trigger edge.

        Parameters:
            edge: Either `TriggerEdge.RISING` or `TriggerEdge.FALLING`.
        """
        arg = TriggerEdge(edge).value
        self._scpi_transport.write(f"TRIGGER:SLOPE {arg}")
        self._check_error()

    @rpc_method
    def get_output_load_impedance(self, channel: int) -> float:
        """Return the configured load impedance of the specified output channel.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            Assumed load impedance in Ohm, or `math.inf` for open circuit.
        """
        self._check_channel(channel)
        imp = self._ask_float(f"OUTPUT{channel}:IMPEDANCE?")
        if imp > self._INFINITY_THRESHOLD:
            return math.inf
        return imp

    @rpc_method
    def set_output_load_impedance(self, channel: int, impedance: float) -> None:
        """Configure the load impedance of the specified output channel.

        Note: The `output impedance` of the instrument is fixed at 50 Ohm.
        This command configures the impedance of the load that is assumed to
        be connected to the output. This affects the calculation of output amplitudes.

        Parameters:
            channel: Output channel (1 or 2).
            impedance: Load impedance in Ohm, range 1 to 10000, or `math.inf` to assume open circuit.
        """
        self._check_channel(channel)
        arg = "INF" if (impedance > self._INFINITY_THRESHOLD) else f"{impedance:.1f}"
        self._scpi_transport.write(f"OUTPUT{channel}:IMPEDANCE {arg}")
        self._check_error()

    @rpc_method
    def get_output_inverted(self, channel: int) -> bool:
        """Return True if the output polarity of the specified channel is inverted.

        Parameters:
            channel: Output channel (1 or 2).

        Returns:
            True if polarity is inverted, False if polarity is normal.
        """
        class Polarity(enum.Enum):
            """Enum for polarity of output."""
            NORMAL = "NORM"
            INVERTED = "INV"
        self._check_channel(channel)
        polarity = self._ask_enum(f"OUTPUT{channel}:POLARITY?", Polarity)
        return polarity == Polarity.INVERTED

    @rpc_method
    def set_output_inverted(self, channel: int, enable: bool) -> None:
        """Enable or disable inverted output polarity.

        Parameters:
            channel: Output channel (1 or 2).
            enable:  True to select inverted output, False to select normal output polarity.
        """
        self._check_channel(channel)
        arg = "INV" if enable else "NORM"
        self._scpi_transport.write(f"OUTPUT{channel}:POLARITY {arg}")
        self._check_error()

    @rpc_method
    def set_display_brightness(self, brightness: float) -> None:
        """Set brightness of the touchscreen display.

        Parameters:
            brightness: Display brightness in range 0.0 to 1.0.
                        Value 0.0 is the lowest brightness but does not
                        completely disable the display.
        """
        self._scpi_transport.write(f"DISPLAY:BRIGHTNESS {brightness:.3f}")
        self._check_error()
