"""Instrument driver for the Quantum Composers 9530 pulse generator."""

import enum
import logging
from typing import Tuple, Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class RefClkSource(enum.Enum):
    """Reference clock sources.

    Attributes:
        INTERNAL: Internal clock source.
        EXTERNAL: External clock input.
        EXTPLL:   External clock signal with PLL.
    """
    INTERNAL = "INT"
    EXTERNAL = "EXT"
    EXTPLL = "XPL"


class PulseMode(enum.Enum):
    """Pulse generator modes.

    Attributes:
        NORMAL: Generate continuous pulse sequence (every input event causes an output pulse).
        SINGLE: Generate just one pulse after the output is enabled.
        BURST:  Generate a fixed number of pulses after the output is enabled; then suppress further pulses.
        DUTYCYCLE: Keep alternating between generating a fixed number of pulses and suppressing
                   a fixed number of pulses.
    """
    NORMAL = "NORM"
    SINGLE = "SING"
    BURST = "BURS"
    DUTYCYCLE = "DCYC"


class TriggerMode(enum.Enum):
    """Trigger modes."""
    DISABLED = "DIS"
    ENABLED = "TRIG"
    DUAL = "DUAL"


class TriggerEdge(enum.Enum):
    """Trigger on rising or falling edge."""
    RISING = "RIS"
    FALLING = "FALL"


class OutputDriver(enum.Enum):
    """Output driver type.

    Attributes:
        TTL: Fast driver with fixed 4 Volt output level (into 1 kOhm).
        ADJUSTABLE: Slower driver with programmable output level.
    """
    TTL = "TTL"
    ADJUSTABLE = "ADJ"


# Table for decoding error responses.
_ERROR_MESSAGES = {
    1: "Incorrect prefix",
    2: "Missing command keyword",
    3: "Invalid command keyword",
    4: "Missing parameter",
    5: "Invalid parameter",
    6: "Query only, command needs a question mark",
    7: "Invalid query, command does not have a query form",
    8: "Command unavailable in current system state"
}


class QuantumComposers_PulseGenerator9530(QMI_Instrument):
    """Instrument driver for the Quantum Composers 9530 pulse generator.

    This driver can be used to communicate with the instrument via USB or
    Ethernet (TCP), depending on the specified transport descriptor.
    """

    # Instrument should respond within 2 seconds.
    RESPONSE_TIMEOUT = 2.0

    def __init__(self, context: QMI_Context, name: str, scpi_transport: str) -> None:
        """Initialize driver.

        Depending on the transport descriptor, the instrument may be accessed
        either via USB or via Ethernet. For example::
          "tcp:172.16.3.83:2101"
          or "serial:/dev/serial/by-id/usb-FTDI_FT232R_..."

        Parameters:
            context: QMI context that will manage this RPC object.
            name: Unique name for this RPC object instance.
            scpi_transport: QMI transport descriptor to connect to the instrument.
        """

        # NOTE: The instrument uses an SCPI-like command language, but generates
        # non-compliant response messages. For this reason, the ScpiProtocol
        # class can not be used. Instead the command interaction is implemented
        # within this driver.

        super().__init__(context, name)
        default_attributes = {
            "port": 2101,      # default TCP port number for Digi Connect module
            "baudrate": 38400  # default baud rate when connected via USB
        }
        self._transport = create_transport(scpi_transport, default_attributes=default_attributes)

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @staticmethod
    def _parse_error_response(response: str) -> str:
        """Decode an error response from the instrument and return a human-readable error message."""

        # In case of an error, the device responds with "?<N>"
        # where <N> is a a numeric error code.
        if response.startswith("?"):
            try:
                errcode = int(response[1:])
                return _ERROR_MESSAGES[errcode]
            except ValueError:
                # Invalid error response format; ignore.
                pass
            except KeyError:
                # Unknown error code; ignore.
                pass
        return repr(response)

    @staticmethod
    def _parse_bool(response: str) -> bool:
        """Parse a boolean response from the instrument."""
        response = response.strip()
        if response == "0":
            return False
        if response == "1":
            return True
        raise QMI_InstrumentException(f"Unexpected response {response!r} while expecting boolean")

    @staticmethod
    def _parse_int(response: str) -> int:
        """Parse an integer response from the instrument."""
        try:
            return int(response.strip())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response {response!r} while expecting integer")

    @staticmethod
    def _parse_float(response: str) -> float:
        """Parse a floating point response from the instrument."""
        try:
            return float(response.strip())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unexpected response {response!r} while expecting float")

    def _ask(self, cmd: str) -> str:
        """Send query to instrument and return response from instrument.

        Parameters:
            cmd: SCPI command string.

        Returns:
            Response message with message terminator removed.
        """

        # Send command.
        raw_cmd = cmd.encode("ascii") + b"\r\n"
        self._transport.write(raw_cmd)

        # Read response.
        raw_response = self._transport.read_until(
            message_terminator=b"\n",
            timeout=self.RESPONSE_TIMEOUT)
        return raw_response.rstrip().decode("ascii")

    def _cmd(self, cmd: str) -> None:
        """Send a (non-query) command to the instrument.

        Parameters:
            cmd: SCPI command string.
        """

        # Send command and read response.
        response = self._ask(cmd)

        # Check that command was accepted.
        response = response.strip()
        if response.lower() != "ok":
            _logger.error("[%s] Error from instrument, cmd=%r, response=%r", self._name, cmd, response)
            errmsg = self._parse_error_response(response)
            raise QMI_InstrumentException(f"Error response from instrument: {errmsg}")

    @staticmethod
    def _check_range(value: Union[int, float],
                     minval: Union[int, float, None],
                     maxval: Union[int, float, None]
                     ) -> None:
        """Check that the parameter value is in the allowed range, otherwise raise ValueError."""
        if (((minval is not None) and (value < minval))
                or ((maxval is not None) and (value > maxval))):
            raise ValueError("Parameter value out of range")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
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
        self._check_is_open()
        self._cmd("*RST")

    @rpc_method
    def get_num_channels(self) -> int:
        """Return the number of output channels of the instrument."""
        self._check_is_open()
        resp = self._ask(":INST:CAT?")
        channel_names = resp.split(",")
        if channel_names[0].strip().upper() != "T0":
            _logger.error("[%s] Got unexpected list of channels: %s", self._name, resp)
            raise QMI_InstrumentException(f"Instrument reports unexpected channel list: {resp}")
        return len(channel_names) - 1

    @rpc_method
    def get_refclk_source(self) -> RefClkSource:
        """Return the current reference clock source."""
        self._check_is_open()
        resp = self._ask(":PULSE0:ICL:MOD?")
        resp = resp.rstrip("?")  # The instrument returns "XPL?" when the PLL is not locked.
        try:
            return RefClkSource(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unsupported reference clock source {resp!r}")

    @rpc_method
    def is_refclk_pll_locked(self) -> bool:
        """Return True if the reference clock PLL is locked to the external input signal."""
        self._check_is_open()
        resp = self._ask(":PULSE0:ICL:MOD?")
        # The instrument returns "XPL" when the PLL is locked, "XPL?" when the PLL is not locked.
        return (resp.upper() == RefClkSource.EXTPLL.value)

    @rpc_method
    def set_refclk_source(self, source: RefClkSource) -> None:
        """Change the reference clock source.

        Parameters:
            source: New reference clock source (one of the `RefClkSource` constants).
        """
        self._check_is_open()
        source_str = RefClkSource(source).value
        self._cmd(f":PULSE0:ICL:MOD {source_str}")

    @rpc_method
    def get_refclk_rate(self) -> int:
        """Return the expected frequency of the external reference clock in MHz."""
        self._check_is_open()
        resp = self._ask(":PULSE0:ICL:RAT?")
        return self._parse_int(resp)

    @rpc_method
    def set_refclk_rate(self, rate: int) -> None:
        """Change the expected frequency of the external reference clock.

        This parameter is only applicable when an external reference clock source is selected.

        Parameters:
            rate: Expected frequency of the input signal in MHz
                  as an integer (valid range 10 to 100 MHz).
        """
        self._check_range(rate, 10, 100)
        self._check_is_open()
        self._cmd(f":PULSE0:ICL:RAT {rate}")

    @rpc_method
    def get_refclk_level(self) -> float:
        """Return the threshold level for the external clock input in Volt."""
        self._check_is_open()
        resp = self._ask(":PULSE0:ICL:LEV?")
        return self._parse_float(resp)

    @rpc_method
    def set_refclk_level(self, level: float) -> None:
        """Change the threshold level for the external clock input.

        The threshold should be set to 50% of the input signal amplitude.
        This level is only applicable when an external reference clock source is selected.

        Parameters:
            level: Threshold level in Volt (valid range 0.02 to 2.5 Volt).
        """
        self._check_range(level, 0.02, 2.5)
        self._check_is_open()
        self._cmd(f":PULSE0:ICL:LEV {level:.3f}")

    @rpc_method
    def set_refclk_external(self, rate: int, level: float, use_pll: bool) -> None:
        """Configure the instrument to use an external reference clock input.

        Parameters:
            rate:       External clock frequency in MHz (valid range 10 to 100).
            level:      Input threshold level in Volt; should be set to 50% of the signal amplitude
                        (valid range 0.02 to 2.5).
            use_pll:    True to use a PLL to lock to the external input signal.
        """
        source = RefClkSource.EXTPLL if use_pll else RefClkSource.EXTERNAL
        self.set_refclk_source(source)
        self.set_refclk_rate(rate)
        self.set_refclk_level(level)

    @rpc_method
    def get_output_enabled(self) -> bool:
        """Return the global output enable state that applies to all channels."""
        self._check_is_open()
        resp = self._ask(":PULSE0:STAT?")
        return self._parse_bool(resp)

    @rpc_method
    def set_output_enabled(self, enable: bool) -> None:
        """Enable or disable pulse generation.

        This controls a global on/off switch that starts or stops pulse generation
        on all enabled channels. Each channel also has a separate on/off switch
        which only affects that specific channel.

        Parameters:
            enable: True to enable pulse generation (equivalent to pressing the RUN button).
                    False to disable pulse generation (equivalent to pressing the STOP button).
        """
        self._check_is_open()
        arg = 1 if enable else 0
        self._cmd(f":PULSE0:STAT {arg}")

    @rpc_method
    def get_t0_period(self) -> float:
        """Return the T0 pulse interval in seconds."""
        self._check_is_open()
        resp = self._ask(":PULSE0:PER?")
        return self._parse_float(resp)

    @rpc_method
    def set_t0_period(self, period: float) -> None:
        """Change the T0 pulse interval.

        Parameters:
            period: New pulse interval in seconds (valid range 50.0e-9 to 5000.0).
        """
        # Warning: Instrument freaks out when the period value has too many significant digits.
        # Sending fixed point format with 9 digits following the decimal point seems safe.
        self._check_range(period, 50.0e-9, 5000.0)
        self._check_is_open()
        self._cmd(f":PULSE0:PER {period:.9f}")

    @rpc_method
    def get_t0_mode(self) -> PulseMode:
        """Return the T0 pulse generation mode."""
        self._check_is_open()
        resp = self._ask(":PULSE0:MOD?")
        try:
            return PulseMode(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unsupported pulse mode {resp!r}")

    @rpc_method
    def set_t0_mode(self, mode: PulseMode) -> None:
        """Change the T0 pulse generation mode.

        Parameters:
            mode: New pulse generation mode (one of the `PulseMode` constants).
        """
        self._check_is_open()
        mode_str = PulseMode(mode).value
        self._cmd(f":PULSE0:MOD {mode_str}")

    @rpc_method
    def get_t0_burst_count(self) -> int:
        """Return the number of T0 pulses when operating in burst mode."""
        self._check_is_open()
        resp = self._ask(":PULSE0:BCO?")
        return self._parse_int(resp)

    @rpc_method
    def set_t0_burst_count(self, count: int) -> None:
        """Set the number of T0 pulses to generate when operating in burst mode.

        Parameters:
            count: Number of T0 pulses to generate after the output is enabled.
                   Valid range is 1 to 10**6.
        """
        self._check_range(count, 1, 10**6)
        self._check_is_open()
        self._cmd(f":PULSE0:BCO {count}")

    @rpc_method
    def get_t0_duty_cycle(self) -> Tuple[int, int]:
        """Return the parameters for T0 duty cycle mode.

        Returns:
            Tuple (num_pulse, num_skip).
        """
        self._check_is_open()
        resp = self._ask(":PULSE0:PCO?")
        num_pulse = self._parse_int(resp)
        resp = self._ask(":PULSE0:OCO?")
        num_skip = self._parse_int(resp)
        return (num_pulse, num_skip)

    @rpc_method
    def set_t0_duty_cycle(self, num_pulse: int, num_skip: int) -> None:
        """Change the parameters for T0 duty cycle mode.

        Parameters:
            num_pulse: Number of pulses to generate (valid range 1 to 10**6).
            num_skip: Number of pulses to skip (valid range 1 to 10**6).
        """
        self._check_range(num_pulse, 1, 10**6)
        self._check_range(num_skip, 1, 10**6)
        self._check_is_open()
        self._cmd(f":PULSE0:PCO {num_pulse}")
        self._cmd(f":PULSE0:OCO {num_skip}")

    @rpc_method
    def get_trigger_mode(self) -> TriggerMode:
        """Return the T0 trigger mode."""
        self._check_is_open()
        resp = self._ask(":PULSE0:TRIG:MOD?")
        try:
            return TriggerMode(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unsupported trigger mode {resp!r}")

    @rpc_method
    def set_trigger_mode(self, mode: TriggerMode) -> None:
        """Change the T0 trigger mode.

        Parameters:
            mode: New trigger mode (one of the `TriggerMode` constants).
        """
        self._check_is_open()
        mode_str = TriggerMode(mode).value
        self._cmd(f":PULSE0:TRIG:MOD {mode_str}")

    @rpc_method
    def get_trigger_edge(self) -> TriggerEdge:
        """Return the active edge for the T0 trigger."""
        self._check_is_open()
        resp = self._ask(":PULSE0:TRIG:EDGE?")
        try:
            return TriggerEdge(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unsupported trigger edge {resp!r}")

    @rpc_method
    def set_trigger_edge(self, edge: TriggerEdge) -> None:
        """Change the active edge for the T0 trigger.

        Parameters:
            mode: New active trigger edge (one of the `TriggerEdge` constants).
        """
        self._check_is_open()
        edge_str = TriggerEdge(edge).value
        self._cmd(f":PULSE0:TRIG:EDGE {edge_str}")

    @rpc_method
    def get_trigger_level(self) -> float:
        """Return the T0 trigger level in Volt."""
        self._check_is_open()
        resp = self._ask(":PULSE0:TRIG:LEVEL?")
        return self._parse_float(resp)

    @rpc_method
    def set_trigger_level(self, level: float) -> None:
        """Change the T0 trigger level.

        Parameters:
            level: New trigger level in Volt (valid range 0.2 .. 15).
        """
        self._check_range(level, 0.2, 15.0)
        self._check_is_open()
        self._cmd(f":PULSE0:TRIG:LEVEL {level:.3f}")

    @rpc_method
    def get_channel_enabled(self, channel: int) -> bool:
        """Return the output enable state for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
        """
        if channel < 1:
            raise ValueError("Invalid channel index")
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:STAT?")
        return self._parse_bool(resp)

    @rpc_method
    def set_channel_enabled(self, channel: int, enable: bool) -> None:
        """Enable or disable output for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
            enable:  `True` to enable the channel, `False` to disable.
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        arg = 1 if enable else 0
        self._cmd(f":PULSE{channel}:STAT {arg}")

    @rpc_method
    def get_channel_width(self, channel: int) -> float:
        """Return the configured pulse width for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.

        Returns:
            Configured pulse width in seconds.
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:WIDT?")
        return self._parse_float(resp)

    @rpc_method
    def set_channel_width(self, channel: int, width: float) -> None:
        """Configure pulse width for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
            width:   New pulse width in seconds (valid range 10e-9 .. 999.9).
        """
        self._check_range(channel, 1, None)
        self._check_range(width, 10.0e-9, 999.9)
        self._check_is_open()
        self._cmd(f":PULSE{channel}:WIDT {width:.11f}")

    @rpc_method
    def get_channel_delay(self, channel: int) -> float:
        """Return the configured delay for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.

        Returns:
            Configured delay in seconds.
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:DEL?")
        return self._parse_float(resp)

    @rpc_method
    def set_channel_delay(self, channel: int, delay: float) -> None:
        """Configure delay for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
            delay:   New delay in seconds (valid range -99.9 .. 999.9).
        """
        self._check_range(channel, 1, None)
        self._check_range(delay, -99.9, 999.9)
        self._check_is_open()
        self._cmd(f":PULSE{channel}:DEL {delay:.11f}")

    @rpc_method
    def get_channel_mode(self, channel: int) -> PulseMode:
        """Return the pulse generation mode of the specified channel."""
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:CMOD?")
        try:
            return PulseMode(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unsupported pulse mode {resp!r}")

    @rpc_method
    def set_channel_mode(self, channel: int, mode: PulseMode) -> None:
        """Change the pulse generation mode of the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
            mode:    New pulse mode (one of the `PulseMode` constants).
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        mode_str = PulseMode(mode).value
        self._cmd(f":PULSE{channel}:CMOD {mode_str}")

    @rpc_method
    def get_channel_burst_count(self, channel: int) -> int:
        """Return the number of pulses to output when operating in burst mode."""
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:BCO?")
        return self._parse_int(resp)

    @rpc_method
    def set_channel_burst_count(self, channel: int, count: int) -> None:
        """Set the number of T0 pulses to generate when operating in burst mode.

        These parameters only has effect when the channel is operating in `PulseMode.BURST` mode.

        Parameters:
            channel:    Channel index in range 1 .. `num_channels`.
            count:      Number of pulses to generate after the output is enabled.
                        Valid range is 1 to 10**6.
        """
        self._check_range(channel, 1, None)
        self._check_range(count, 1, 10**6)
        self._check_is_open()
        self._cmd(f":PULSE{channel}:BCO {count}")

    @rpc_method
    def get_channel_duty_cycle(self, channel: int) -> Tuple[int, int]:
        """Return the duty cycel parameters for the specified channel.

        Returns:
            Tuple (num_pulse, num_skip).
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:PCO?")
        num_pulse = self._parse_int(resp)
        resp = self._ask(f":PULSE{channel}:OCO?")
        num_skip = self._parse_int(resp)
        return (num_pulse, num_skip)

    @rpc_method
    def set_channel_duty_cycle(self, channel: int, num_pulse: int, num_skip: int) -> None:
        """Change the duty cycle parameters for the specified channel.

        These parameters only have effect when the channel is operating in `PulseMode.DUTYCYCLE` mode.

        Parameters:
            channel:    Channel index in range 1 .. `num_channels`.
            num_pulse:  Number of pulses to generate (valid range 1 to 10**6).
            num_skip:   Number of pulses to skip (valid range 1 to 10**6).
        """
        self._check_range(channel, 1, None)
        self._check_range(num_pulse, 1, 10**6)
        self._check_range(num_skip, 1, 10**6)
        self._check_is_open()
        self._cmd(f":PULSE{channel}:PCO {num_pulse}")
        self._cmd(f":PULSE{channel}:OCO {num_skip}")

    @rpc_method
    def get_output_driver(self, channel: int) -> OutputDriver:
        """Return the current output mode for the specified channel."""
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:OUTP:MODE?")
        try:
            return OutputDriver(resp.upper())
        except ValueError:
            # pylint: disable=raise-missing-from
            raise QMI_InstrumentException(f"Unsupported output mode {resp!r}")

    @rpc_method
    def set_output_driver(self, channel: int, mode: OutputDriver) -> None:
        """Change the output mode for the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
            mode:    New output mode (one of the `OutputDriver` constants).
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        mode_str = OutputDriver(mode).value
        self._cmd(f":PULSE{channel}:OUTP:MODE {mode_str}")

    @rpc_method
    def get_output_amplitude(self, channel: int) -> float:
        """Return the current output amplitude in Volt.

        The returned value only applies when the output mode is `OutputMode.ADJUSTABLE`.
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:OUTP:AMPL?")
        return self._parse_float(resp)

    @rpc_method
    def set_output_amplitude(self, channel: int, amplitude: float) -> None:
        """Change the output amplitude of the specified channel..

        The specified amplitude represents the open-circuit voltage of the output.
        The output channels have 50 Ohm output impedance. As a result, the voltage
        levels will drop to 50% of the specified amplitude when a 50 Ohm load
        is connected to the output port.

        This setting only applies when the output mode is `OutputMode.ADJUSTABLE`.

        Parameters:
            channel:    Channel index in range 1 .. `num_channels`.
            amplitude:  New output-high level in Volt (valid range 2.0 to 20.0).
        """
        self._check_range(channel, 1, None)
        self._check_range(amplitude, 2.0, 20.0)
        self._check_is_open()
        self._cmd(f":PULSE{channel}:OUTP:AMPL {amplitude:.3f}")

    @rpc_method
    def get_output_inverted(self, channel: int) -> bool:
        """Return True if the specified channel is active low."""
        self._check_range(channel, 1, None)
        self._check_is_open()
        resp = self._ask(f":PULSE{channel}:POL?")
        return resp.upper() != "NORM"

    @rpc_method
    def set_output_inverted(self, channel: int, invert: bool) -> None:
        """Change the output polarity of the specified channel.

        Parameters:
            channel: Channel index in range 1 .. `num_channels`.
            invert:  True to select active low output, False to select active high.
        """
        self._check_range(channel, 1, None)
        self._check_is_open()
        arg = "INV" if invert else "NORM"
        self._cmd(f":PULSE{channel}:POL {arg}")

    @rpc_method
    def set_display_enabled(self, enable: bool) -> None:
        """Enable or disable the display on the front panel of the instrument.

        Disabling the display also blocks the front panel keys, except for
        the power button which always works.

        Parameters:
            enable: True to enable display and keypad, False to disable.
        """
        self._check_is_open()
        arg = 1 if enable else 0
        self._cmd(f":DISP:ENAB {arg}")
