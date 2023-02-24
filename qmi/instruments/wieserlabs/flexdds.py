"""
Instrument driver for the Wieserlabs FlexDDS-NG Dual signal source.
"""

import enum
import logging
import re
from typing import NamedTuple, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class OutputChannel(enum.IntEnum):
    """FlexDDS commands can be specified to apply to one or both of the output channels."""
    OUT0 = 0
    OUT1 = 1
    BOTH = 2


class DdsRegister(enum.IntEnum):
    """Register names and addresses of the AD9910 DDS."""
    CFR1 = 0x00
    CFR2 = 0x01
    ADAC = 0x03
    IOUR = 0x04
    FTW  = 0x07
    POW  = 0x08
    ASF  = 0x09
    DRL  = 0x0B
    DRSS = 0x0C
    DRR  = 0x0D
    STP0 = 0x0E
    STP1 = 0x0F
    STP2 = 0x10
    STP3 = 0x11
    STP4 = 0x12
    STP5 = 0x13
    STP6 = 0x14
    STP7 = 0x15
    RAMB = 0x16
    RAM32E = 0x17
    RAM64C = 0x18
    RAM64E = 0x19


class DcpRegister(enum.IntEnum):
    """Register names and addresses of the DCP."""
    CFG_BNC_A   = 0x080
    CFG_BNC_B   = 0x081
    CFG_BNC_C   = 0x082
    CFG_UPDATE  = 0x084
    CFG_OSK     = 0x085
    CFG_DRCTL   = 0x086
    CFG_DRHOLD  = 0x087
    CFG_PROFILE = 0x088
    AM_S0       = 0x100
    AM_S1       = 0x101
    AM_O        = 0x102
    AM_O0       = 0x103
    AM_O1       = 0x104
    AM_CFG      = 0x105


class PllStatus(NamedTuple):
    """PLL status of the Wieserlabs FlexDDS."""
    pll1_lock:      bool
    pll2_lock:      bool
    holdover:       bool
    clkin0_lost:    bool
    clkin1_lost:    bool


class Wieserlabs_FlexDDS_NG_Dual(QMI_Instrument):
    """Instrument driver for the Wieserlabs FlexDDS-NG Dual signal source.

    The instrument is based on two AD9910 direct digital synthesizer (DDS)
    chips, one for each output channel. The instrument also contains one
    DDS Command Processor (DCP) for each channel. The DCP can be used to
    program the DDS and to enable analog modulation modes.

    This driver provides a simple, limited, high-level interface to the instrument
    through the methods `set_single_tone()`, `set_amplitude_modulation()` and
    `set_frequency_modulation()`. These methods support only a subset of
    the features of the instrument.

    This driver also provides a low-level interface to the instrument through
    the the `dcp_XXX()` methods. These methods support more functionality
    (however waiting, triggering and digital I/O are still not supported).
    Detailed understanding of the FlexDDS user manual and the AD9910 datasheet
    are needed to use the low-level interface.
    """

    # Response timeout for normal commands.
    COMMAND_RESPONSE_TIMEOUT = 2.0

    # Frequency resolution in Hz.
    # Only integer multiples of this frequency can be represented exactly.
    FREQUENCY_RESOLUTION = 1.0e9 / 2**32

    # Max 400 MHz.
    MAX_FREQUENCY = 400.0e6

    # Maximum analog input level in Volt.
    MAX_ANALOG_INPUT_VOLT = 0.5

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialize the instrument driver.

        Arguments:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
                        The transport descriptor will typically specify a
                        serial port and baud rate, for example
                        "serial:/dev/ttyACM0:baudrate=115200".
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200})

    def _write(self, cmd: str) -> None:
        """Send a command to the instrument."""
        self._transport.write(cmd.encode("ascii") + b"\r")

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()

        try:
            # Discard any pending data from the instrument.
            self._transport.discard_read()

            # By default the FlexDDS starts in "interactive" mode. This means
            # it sends interactive prompts, command echos, and log messages.
            # Switch it to non-interactive mode to get only meaningful responses.
            self._write("")  # flush potential partial command string
            self._write("interactive off")

            # Discard response up to the point where interactive mode stops.
            _resp = self._transport.read_until(b"Interactive off\r\n", timeout=self.COMMAND_RESPONSE_TIMEOUT)

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
    def get_version(self) -> str:
        """Read the instrument version string."""
        self._transport.discard_read()  # Discard potential replies from previous commands.
        self._write("version")

        # The reply format to the "version" command is not very well specified.
        # It typically starts with 'Version: "version_string" (other stuff...)'
        # and ends with 'USER: ...'.
        version_string = None
        while True:
            resp = self._transport.read_until(b"\n", self.COMMAND_RESPONSE_TIMEOUT)
            resp_str = resp.decode("latin1")
            version_match = re.match(r'^Version:\s*"([^"]+)"', resp_str)
            if version_match:
                version_string = version_match.group(1)
            if resp_str.find("USER:") >= 0:
                break  # this was the last line of the reply

        if version_string is None:
            raise QMI_InstrumentException("Unexpected reply to 'version' command")

        return version_string

    @rpc_method
    def get_pll_status(self) -> PllStatus:
        """Read the PLL status.

        This is an undocumented command.
        The meaning of the result is not fully understood, however it
        seems that the attribute `pll1_lock` shows whether the 10 MHz
        external reference is detected.
        """
        self._transport.discard_read()  # Discard potential replies from previous commands.
        self._write("lmkpll")

        # Read results.
        # The reply format is not fully specified, but generally looks something like this:
        #
        # LMK PLL status: rv=666
        #   DLD (lock detect): PLL1: *UNLOCK*   PLL2: locked      BOTH: *UNLOCK*
        #   Holdover . . . . : *ACTIVE*
        #   DAC. . . . . . . : low
        #   LOS (signal loss): CLKIN0: *LOST*       CLKIN1: not lost
        #   CLKIN selected . : CLKIN0: *SELECT*     CLKIN1: (unsel)
        #
        pll1_lock: Optional[bool] = None
        pll2_lock: Optional[bool] = None
        holdover: Optional[bool] = None
        clkin0_lost: Optional[bool] = None
        clkin1_lost: Optional[bool] = None
        while True:
            resp = self._transport.read_until(b"\n", self.COMMAND_RESPONSE_TIMEOUT)
            resp_str = resp.decode("latin1")
            lock_match = re.match(r"^\s*DLD.*PLL1:\s*(\*UNLOCK\*|locked)\s*PLL2:\s*(\*UNLOCK\*|locked)", resp_str)
            if lock_match:
                pll1_lock = (lock_match.group(1) == "locked")
                pll2_lock = (lock_match.group(2) == "locked")
            holdover_match = re.match(r"^\s*Holdover.*:\s*(\*ACTIVE\*|inact)", resp_str)
            if holdover_match:
                holdover = (holdover_match.group(1) == "*ACTIVE*")
            loss_match = re.match(r"^\s*LOS.*CLKIN0:\s*(\*LOST\*|not lost)\s*CLKIN1:\s*(\*LOST\*|not lost)", resp_str)
            if loss_match:
                clkin0_lost = (loss_match.group(1) == "*LOST*")
                clkin1_lost = (loss_match.group(2) == "*LOST*")
            if resp_str.find("CLKIN selected") >= 0:
                break  # this was the last line of the reply

        if ((pll1_lock is None) or (pll2_lock is None) or (holdover is None)
                or (clkin0_lost is None) or (clkin1_lost is None)):
            raise QMI_InstrumentException("Unexpected reply to 'lmkpll' command")

        return PllStatus(pll1_lock=pll1_lock,
                         pll2_lock=pll2_lock,
                         holdover=holdover,
                         clkin0_lost=clkin0_lost,
                         clkin1_lost=clkin1_lost)

    @staticmethod
    def _format_channel(channel: OutputChannel) -> str:
        """Return the output channel selector in the format expected by the instrument."""
        if channel == OutputChannel.OUT0:
            return "0"
        elif channel == OutputChannel.OUT1:
            return "1"
        else:
            return ""  # omit channel number to select both channels

    @staticmethod
    def _calc_reg_cfr1(invsinc_filter: bool = True,
                       sine_output: bool = True,
                       osk_enable: bool = False,
                       manual_osk: bool = False,
                       auto_osk: bool = False
                       ) -> int:
        """Calculate a value for the CFR1 register of the AD9910 DDS.

        Parameters:
            invsinc_filter:   Enable inverse Sinc filter.
            sine_output:      True to select sine output; False to select cosine output.
            osk_enable:       Enable OSK mode.
            manual_osk:       Enable manual OSK via external OSK pin (when osk_enable is also True).
            auto_osk:         Enable automatic OSK (when osk_enable is also True).
        """

        # Bits 7..0 are not writable.
        # We set these to their default values.
        value = 0x00000002

        if manual_osk:
            value |= (1 << 23)
        if invsinc_filter:
            value |= (1 << 22)
        if sine_output:
            value |= (1 << 16)
        if osk_enable:
            value |= (1 << 9)
        if auto_osk:
            value |= (1 << 8)

        return value

    @staticmethod
    def _calc_reg_cfr2(ampl_scale_en: bool = False,
                       match_latency: bool = True,
                       hold_last_value: bool = True,
                       parallel_data_en: bool = False,
                       fm_gain: int = 0
                       ) -> int:
        """Calculate a value for the CFR2 register of the AD9910 DDS.

        Parameters:
            ampl_scale_en:    Enable amplitude scaling (if False, amplitudes settings are ignored)
            match_latency:    Simultaneously apply changes to amplitude, phase and frequency.
            hold_last_value:  Hold last value of the parallel data port when the DCP does not send a new word.
            parallel_data_en: Enable the parallel data port (analog modulation modes).
            fm_gain:          Shift count for frequency modulation data.
        """

        fm_gain = int(fm_gain)
        if fm_gain < 0 or fm_gain > 15:
            raise ValueError("Invalid shift count")

        # Bits 23..22, bits 11..9 and bit 5 are not writable.
        # We set these to their default values.
        value = 0x00400800

        if ampl_scale_en:
            value |= (1 << 24)
        if match_latency:
            value |= (1 << 7)
        if hold_last_value:
            value |= (1 << 6)
        if parallel_data_en:
            value |= (1 << 4)
        value |= (fm_gain & 15)

        return value

    @staticmethod
    def _calc_reg_stp(ampl_scale: int, phase_offset: int, ftw: int) -> int:
        """Calculate a value for the STP0 ... STP7 registers of the AD9910 DDS.

        Parameters:
            ampl_scale:     Amplitude scale factor, unsigned 14-bit integer.
            phase_offset:   Phase offset, unsigned 16-bit integer, in steps of (2*pi / 2**16) radians.
            ftw:            Frequency tuning word, unsigned 32-bit integer, in steps of (1 GHz / 2**32).
        """
        if (not isinstance(ampl_scale, int)) or (ampl_scale < 0) or (ampl_scale >= 2**14):
            raise ValueError("Invalid ampl_scale parameter")
        if (not isinstance(phase_offset, int)) or (phase_offset < 0) or (phase_offset >= 2**16):
            raise ValueError("Invalid phase_offset parameter")
        if (not isinstance(ftw, int)) or (ftw < 0) or (ftw >= 2**32):
            raise ValueError("Invalid ftw parameter")
        return ((ampl_scale << 48)
                | (phase_offset << 32)
                | ftw)

    @staticmethod
    def _calc_ampl_scale(amplitude: float) -> int:
        """Convert amplitude scale factor from floating point range 0 ... 1.0 to 14-bit word for DDS."""
        return max(0, min(2**14 - 1, int(round(amplitude * (2**14 - 1)))))

    @staticmethod
    def _calc_phase_offset(phase: float) -> int:
        """Convert phase offset from floating point range 0 ... 1.0 to 16-bit word for DDS."""
        return max(0, min(2**16 - 1, int(round(phase * 2**16))))

    @staticmethod
    def _calc_ftw(frequency: float) -> int:
        """Convert frequency from floating point in Hz to 32-bit frequency tuning word."""
        return max(0, min(2**32 - 1, int(round(frequency / 1.0e9 * 2**32))))

    @staticmethod
    def _wrap_signed(value: int, wordlength: int) -> int:
        """Encode a signed integer as a two's complement representation in an unsigned word."""
        return value & (2**wordlength - 1)

    @rpc_method
    def dds_reset(self, channel: OutputChannel) -> None:
        """Reset both the DDS and the DCP for the specified channel(s).

        Resetting will disable the output channel and reset all DDS registers
        to their default settings. It will also stop the DCP and discard
        any pending DCP instructions.

        This command takes effect immediately.
        """
        self._transport.discard_read()  # Discard potential replies from previous commands.
        chan_str = self._format_channel(channel)
        self._write("dds {} reset".format(chan_str))

        # Wait for the response string from the reset command.
        while True:
            resp = self._transport.read_until(b"\n", self.COMMAND_RESPONSE_TIMEOUT)
            resp_str = resp.decode("latin1")
            if resp_str.startswith("DDS reset OK"):
                break

    @rpc_method
    def dcp_start(self, channel: OutputChannel) -> None:
        """Start the DCP for the specified channel(s).

        When started, the DCP will begin executing instructions from
        the DCP FIFO. The DCP will continue to run until it is explicitly
        disabled (via `dcp_stop()`) or until it is reset (via `dds_reset()`).

        Starting the DCP will also flush pending instructions from the
        input queue to the DCP FIFO.

        This command takes effect immediately.
        """
        chan_str = self._format_channel(channel)
        self._write("dcp {} start".format(chan_str))

    @rpc_method
    def dcp_stop(self, channel: OutputChannel) -> None:
        """Stop the DCP for the specified channel(s).

        This command takes effect immediately.
        """
        chan_str = self._format_channel(channel)
        self._write("dcp {} stop".format(chan_str))

    @rpc_method
    def dcp_spi_write(self,
                      channel: OutputChannel,
                      register: DdsRegister,
                      value: int,
                      wait_spi: bool = True,
                      flush: bool = False
                      ) -> None:
        """Send an SPI write instruction to the DCP.

        Instructs the DCP to write to the specified register of the AD9910 DDS.

        This instruction will be queued and only takes effect when it has
        been flushed to the DCP, and the DCP is running, and the DCP has
        completed all previous instructions.

        Parameters:
            channel:    Select one or both output channels.
            register:   Destination DDS register.
            value:      Value to write to the DDS register.
            wait_spi:   True to make the DCP wait until the SPI write is finished.
                        False to continue with the next DCP instruction while the
                        SPI write is pending.
            flush:      True to flush DCP instructions to the DCP FIFO.
        """
        chan_str = self._format_channel(channel)
        reg_str = DdsRegister(register).name
        if (not isinstance(value, int)) or (value >= 2**64):
            raise ValueError("Invalid value for register")
        wait_str = (":w" if wait_spi else ":c")
        flush_str = ("!" if flush else "")
        self._write("dcp {} spi:{}=0x{:x}{}{}".format(chan_str, reg_str, value, wait_str, flush_str))

    @rpc_method
    def dcp_register_write(self,
                           channel: OutputChannel,
                           register: DcpRegister,
                           value: int,
                           flush: bool = False
                           ) -> None:
        """Send a register write instruction to the DCP.

        Instructs the DCP to write to the specified DCP register.

        This instruction will be queued and only takes effect when it has
        been flushed to the DCP, and the DCP is running, and the DCP has
        completed all previous instructions.

        Parameters:
            channel:    Select one or both output channels.
            register:   Destination DCP register.
            value:      Value to write to the DCP register.
            flush:      True to flush DCP instructions to the DCP FIFO.
        """
        chan_str = self._format_channel(channel)
        reg_str = DcpRegister(register).name
        if (not isinstance(value, int)) or (value >= 2**32):
            raise ValueError("Invalid value for register")
        flush_str = ("!" if flush else "")
        self._write("dcp {} wr:{}=0x{:x}{}".format(chan_str, reg_str, value, flush_str))

    @rpc_method
    def dcp_update(self,
                   channel: OutputChannel,
                   flush: bool = False
                   ) -> None:
        """Send an update instruction to the DCP.

        Instructs the DCP to pulse the IO_UPDATE signal to the AD9910 DDS.
        A pulse on the IO_UPDATE signal will cause any new values in DDS
        registers to take effect.

        It is important that all SPI write instructions have completed
        before sending the IO_UPDATE pulse. This can be ensured by setting
        `wait_spi=True` on the last call to `dcp_spi_write()`.

        This instruction will be queued and only takes effect when it has
        been flushed to the DCP, and the DCP is running, and the DCP has
        completed all previous instructions.

        Parameters:
            channel:    Select one or both output channels.
            flush:      True to flush DCP instructions to the DCP FIFO.
        """
        chan_str = self._format_channel(channel)
        flush_str = ("!" if flush else "")
        self._write("dcp {} update:u{}".format(chan_str, flush_str))

    @rpc_method
    def set_single_tone(self,
                        channel: OutputChannel,
                        frequency: float,
                        amplitude: float,
                        phase: float
                        ) -> None:
        """Configure the specified channel to produce a single tone.

        The frequency will be rounded to the closest integer multiple of
        the internal frequency resolution (see `Wieserlabs_FlexDDS_NG_Dual.FREQUENCY_RESOLUTION`).

        The amplitude is a linear voltage scale factor, expressed as a fraction
        of the maximum output amplitude: +10 dBm (2 Vpp).

        This function assumes that the FlexDDS is in a "normal" configuration.
        When in doubt, call `dds_reset()` before calling this function.

        Parameters:
            channel:    Select one or both output channels.
            frequency:  Tone frequency in Hz (range 300 kHz ... 400 MHz).
            amplitude:  Amplitude scale factor (range 0.0 ... 1.0).
            phase:      Phase offset as fraction of the full sine wave period (range 0.0 ... 1.0).
        """

        if (frequency < 0) or (frequency > self.MAX_FREQUENCY):
            raise ValueError("Invalid frequency")
        if (amplitude < 0) or (amplitude > 1.0):
            raise ValueError("Invalid amplitude")
        if (phase < 0) or (phase > 1.0):
            raise ValueError("Invalid phase")

        cfr1 = self._calc_reg_cfr1()
        cfr2 = self._calc_reg_cfr2(ampl_scale_en=True,
                                   match_latency=True,
                                   hold_last_value=True,
                                   parallel_data_en=False)
        stp0 = self._calc_reg_stp(ampl_scale=self._calc_ampl_scale(amplitude),
                                  phase_offset=self._calc_phase_offset(phase),
                                  ftw=self._calc_ftw(frequency))

        self.dcp_spi_write(channel, DdsRegister.CFR1, cfr1)
        self.dcp_spi_write(channel, DdsRegister.CFR2, cfr2)
        self.dcp_spi_write(channel, DdsRegister.STP0, stp0, wait_spi=True)
        self.dcp_update(channel)
        self.dcp_start(channel)

    @rpc_method
    def set_amplitude_modulation(self,
                                 channel: OutputChannel,
                                 frequency: float,
                                 base_ampl: float,
                                 phase: float,
                                 mod_input: int,
                                 mod_offset: float,
                                 mod_scale: float
                                 ) -> None:
        """Configure the specified channel for a single tone with analog amplitude modulation.

        The `base_ampl` parameter sets the nominal amplitude scale factor,
        expressed as a fraction of the maximum output amplitude: +10 dBm (2 Vpp).
        This nominal amplitude applies when the modulation level is zero.

        The effective amplitude scale factor can be calculated as follows::

            A = base_ampl + mod_scale * (M + mod_offset)

        where `M` is the signal level of the analog modulation input in Volt (range -0.5 ... +0.5);
              `A` is the effective amplitude scale factor as a fraction of the maximum output level (2 Vpp).

        The effective amplitude scale factor `A` will be clipped to the range 0.0 ... 1.0.

        For example, the following call will configure output channel 0 for 10 MHz output
        with amplitude modulation to span the amplitude range from 0 Vpp (at analog input level -0.5 Volt)
        to 2 Vpp (at analog input level +0.5 Volt)::

            instr.set_amplitude_modulation(channel=OutputChannel.OUT0,
                                           frequency=10.0e6,
                                           base_amplitude=0.5,
                                           phase=0,
                                           mod_input=0,
                                           mod_offset=0,
                                           mod_scale=1.0)

        This function assumes that the FlexDDS is in a "normal" configuration.
        When in doubt, call `dds_reset()` before calling this function.

        Parameters:
            channel:    Select one or both output channels.
            frequency:  Tone frequency in Hz (range 300 kHz ... 400 MHz).
            base_ampl:  Base amplitude scale factor (range -2.0 ... 2.0).
            phase:      Phase offset as fraction of the full sine wave period (range 0.0 ... 1.0).
            mod_input:  Analog input channel for amplitude modulation (0 or 1).
            mod_offset: Offset to add to the analog input signal in Volt (range -0.5 ... +0.5).
            mod_scale:  Scale factor from analog input signal to RF output amplitude,
                        where 1.0 means that the full range of the analog input corresponds
                        to the full range of the output amplitude (range -30.0 ... +30.0).
        """

        if (frequency < 0) or (frequency > self.MAX_FREQUENCY):
            raise ValueError("Invalid frequency")
        if (base_ampl < -2.0) or (base_ampl > 2.0):
            raise ValueError("Invalid base_ampl parameter")
        if (phase < 0) or (phase > 1.0):
            raise ValueError("Invalid phase")
        if mod_input not in (0, 1):
            raise ValueError("Invalid mod_input parameter")
        if abs(mod_offset) > self.MAX_ANALOG_INPUT_VOLT:
            raise ValueError("Invalid mod_offset parameter")
        if (mod_scale < -30.0) or (mod_scale > 30.0):
            raise ValueError("Invalid mod_scale parameter")

        # Amplitude modulation requires the DCP and DDS working together as follows:
        # The DCP samples the analog input signal and converts the level to
        # an unsigned 16-bit word, based on scaling parameters that we specify.
        # The DCP feeds this 16-bit word to the DDS as "parallel data".
        # The DDS uses the 14 most significant bits of the parallel data word
        # as the effective amplitude scale factor.

        # Calculate DDS register values.
        # Enable "parallel data" to allow modulation.
        cfr1 = self._calc_reg_cfr1()
        cfr2 = self._calc_reg_cfr2(ampl_scale_en=True,
                                   match_latency=True,
                                   hold_last_value=True,
                                   parallel_data_en=True)
        stp0 = self._calc_reg_stp(ampl_scale=0,
                                  phase_offset=self._calc_phase_offset(phase),
                                  ftw=self._calc_ftw(frequency))

        # The ADC values from the modulation input are in range (-2**15 ... 2**15-1).
        # Scale the input offset to match that range.
        mod_input_offset_raw = int(round(mod_offset / self.MAX_ANALOG_INPUT_VOLT * 2**15))
        mod_input_offset_raw = self._wrap_signed(mod_input_offset_raw, 18)

        # The offset-corrected ADC values are multiplied by the raw scale factor,
        # then divided by 2**12. Calculate the raw scale factor to match
        # the specified effective scale factor.
        mod_scale_raw = int(round(mod_scale * 2**12))
        mod_scale_raw = self._wrap_signed(mod_scale_raw, 18)

        # A global offset is added to the scaled signal, then the result is
        # clipped to an unsigned 16-bit integer to form the parallel data word
        # for the DDS. The DDS uses the 14 most significant bits of the
        # parallel data word as the effective amplitude scale factor.
        # Scale the base amplitude to 16-bit range to determine the global offset value.
        mod_global_offset_raw = int(round(base_ampl * (2**16 - 4)))
        mod_global_offset_raw = self._wrap_signed(mod_global_offset_raw, 24)

        # Configure DDS.
        self.dcp_spi_write(channel, DdsRegister.CFR1, cfr1)
        self.dcp_spi_write(channel, DdsRegister.CFR2, cfr2)
        self.dcp_spi_write(channel, DdsRegister.STP0, stp0, wait_spi=True)

        # Configure modulation registers.
        self.dcp_register_write(channel, DcpRegister.AM_O, mod_global_offset_raw)
        if mod_input == 0:
            # Use analog input channel 0.
            self.dcp_register_write(channel, DcpRegister.AM_S1, 0)
            self.dcp_register_write(channel, DcpRegister.AM_O0, mod_input_offset_raw)
            self.dcp_register_write(channel, DcpRegister.AM_S0, mod_scale_raw)
        else:
            # Use analog input channel 1.
            self.dcp_register_write(channel, DcpRegister.AM_S0, 0)
            self.dcp_register_write(channel, DcpRegister.AM_O1, mod_input_offset_raw)
            self.dcp_register_write(channel, DcpRegister.AM_S1, mod_scale_raw)

        # Analog modulation config register:
        #   bit 29   = update modulation settings
        #   bits 1:0 = 00 = amplitude modulation
        mod_cfg = (1 << 29) | 0b00
        self.dcp_register_write(channel, DcpRegister.AM_CFG, mod_cfg)

        self.dcp_update(channel)
        self.dcp_start(channel)

    @rpc_method
    def set_frequency_modulation(self,
                                 channel: OutputChannel,
                                 base_freq: float,
                                 amplitude: float,
                                 phase: float,
                                 mod_input: int,
                                 mod_offset: float,
                                 mod_scale: float,
                                 ) -> None:
        """Configure the specified channel for a single tone with analog frequency modulation.

        The `base_freq` parameter sets the nominal output frequency in Hz.
        This nominal frequency applies when the modulation level is zero.

        The effective frequency can be calculated as follows::

            F = base_freq + mod_scale * (M + mod_offset)

        where `M` is the signal level of the analog modulation input in Volt (range -0.5 ... +0.5);
              `F` is the effective frequency in Hz.

        For example, the following call configures output channel 0 for a base output
        frequency of 10 MHz with a 1 MHz modulation range, such that analog input
        -0.5 V results in 9.5 MHz and analog input +0.5 V results in 10.5 MHz::

            instr.set_frequency_modulation(channel=OutputChannel.OUT0,
                                           base_freq=10.0e6,
                                           amplitude=0.5,
                                           phase=0,
                                           mod_input=0,
                                           mod_offset=0,
                                           mod_scale=1.0e6)

        This function assumes that the FlexDDS is in a "normal" configuration.
        When in doubt, call `dds_reset()` before calling this function.

        Parameters:
            channel:    Select one or both output channels.
            base_freq:  Base frequency in Hz (range 300 kHz ... 400 MHz).
            amplitude:  Amplitude scale factor (range 0.0 ... 1.0).
            phase:      Phase offset as fraction of the full sine wave period (range 0.0 ... 1.0).
            mod_input:  Analog input channel for amplitude modulation (0 or 1).
            mod_offset: Offset to add to the analog input signal in Volt (range -0.5 ... +0.5).
            mod_scale:  Frequency shift in Hz corresponding to the peak-to-peak range of the analog input
                        (range -500 MHz ... +500 MHz).
                        This can also be interpreted as a scale factor from analog input to frequency in Hz/Volt.
        """

        if (base_freq < 0) or (base_freq > self.MAX_FREQUENCY):
            raise ValueError("Invalid frequency")
        if (amplitude < 0) or (amplitude > 1.0):
            raise ValueError("Invalid amplitude")
        if (phase < 0) or (phase > 1.0):
            raise ValueError("Invalid phase")
        if mod_input not in (0, 1):
            raise ValueError("Invalid mod_input parameter")
        if abs(mod_offset) > self.MAX_ANALOG_INPUT_VOLT:
            raise ValueError("Invalid mod_offset parameter")
        if (mod_scale < -500.0e6) or (mod_scale > 500.0e6):
            raise ValueError("Invalid mod_scale parameter")

        # Frequency modulation requires the DCP and DDS working together as follows:
        # The DCP samples the analog input signal and converts the level to
        # an unsigned 16-bit word based on scaling parameters that we specify.
        # The DCP feeds this 16-bit word to the DDS as "parallel data".
        # The DDS takes the 16-bit word and shifts left by a shift count that
        # we specify (fm_gain). The result is added to the base FTW register
        # to obtain the effective FTW.

        # Calculate the FM gain (shift factor) required to span the modulation frequency range.
        # Choose fm_gain such that the 16-bit range of the parallel data word is enough
        # (with some margin) to cover the required frequency range.
        # Perhaps even the highest possible value of fm_gain (15) is not enough;
        # in that case the frequency modulation will clip to the achievable range.
        fm_gain = 0
        while (fm_gain < 15) and (((2**16 - 2) << fm_gain) * self.FREQUENCY_RESOLUTION < abs(mod_scale)):
            fm_gain += 1

        # Calculate the frequency tuning word for the base frequency.
        base_ftw = self._calc_ftw(base_freq)

        # Reduce the value of base_ftw such that the base frequency corresponds
        # to the middle of the 16-bit parallel data range (0x8000).
        if base_ftw >= (0x8000 << fm_gain):
            base_ftw -= (0x8000 << fm_gain)
        else:
            # Matching the base frequency to parallel data value 0x8000 requires
            # a negative value for base_ftw, which is not acceptable.
            # Instead choose base_ftw such that the base frequency corresponds to
            # some integer value of the parallel data word as close as possible to 0x8000.
            base_ftw &= ((1 << fm_gain) - 1)

        # Calculate DDS register values.
        # Enable "parallel data" to allow modulation.
        cfr1 = self._calc_reg_cfr1()
        cfr2 = self._calc_reg_cfr2(ampl_scale_en=True,
                                   match_latency=True,
                                   hold_last_value=True,
                                   parallel_data_en=True,
                                   fm_gain=fm_gain)
        stp0 = self._calc_reg_stp(ampl_scale=self._calc_ampl_scale(amplitude),
                                  phase_offset=self._calc_phase_offset(phase),
                                  ftw=base_ftw)

        # The ADC values from the modulation input are in range (-2**15 ... 2**15-1).
        # Scale the input offset to match that range.
        mod_input_offset_raw = int(round(mod_offset / self.MAX_ANALOG_INPUT_VOLT * 2**15))
        mod_input_offset_raw = self._wrap_signed(mod_input_offset_raw, 18)

        # Calculate the effective frequency step corresponding to a single
        # increment of the 16-bit parallel data word.
        mod_step = 2**fm_gain * self.FREQUENCY_RESOLUTION

        # The offset-corrected ADC values are multiplied by the raw scale factor,
        # then divided by 2**12. Calculate the raw scale factor such that the
        # peak-to-peak range of the ADC (2**16 - 1) gets scaled to the desired
        # frequency range.
        mod_scale_raw = int(round(mod_scale / mod_step / (2**16 - 1) * 2**12))
        mod_scale_raw = self._wrap_signed(mod_scale_raw, 18)

        # A global offset is added to the scaled signal, then the result is
        # clipped to an unsigned 16-bit integer to form the parallel data word
        # for the DDS. The DDS shifts and adds this word to the base FTW.
        # Choose the global offset such that it combines with the base FTW
        # to an effective FTW that matches the specified base frequency.
        mod_global_offset_raw = (self._calc_ftw(base_freq) - base_ftw) // 2**fm_gain

        # Configure DDS.
        self.dcp_spi_write(channel, DdsRegister.CFR1, cfr1)
        self.dcp_spi_write(channel, DdsRegister.CFR2, cfr2)
        self.dcp_spi_write(channel, DdsRegister.STP0, stp0)
        self.dcp_spi_write(channel, DdsRegister.FTW, base_ftw, wait_spi=True)

        # Configure modulation registers.
        self.dcp_register_write(channel, DcpRegister.AM_O, mod_global_offset_raw)
        if mod_input == 0:
            # Use analog input channel 0.
            self.dcp_register_write(channel, DcpRegister.AM_S1, 0)
            self.dcp_register_write(channel, DcpRegister.AM_O0, mod_input_offset_raw)
            self.dcp_register_write(channel, DcpRegister.AM_S0, mod_scale_raw)
        else:
            # Use analog input channel 1.
            self.dcp_register_write(channel, DcpRegister.AM_S0, 0)
            self.dcp_register_write(channel, DcpRegister.AM_O1, mod_input_offset_raw)
            self.dcp_register_write(channel, DcpRegister.AM_S1, mod_scale_raw)

        # Analog modulation config register:
        #   bit 29   = update modulation settings
        #   bits 1:0 = 10 = frequency modulation
        mod_cfg = (1 << 29) | 0b10
        self.dcp_register_write(channel, DcpRegister.AM_CFG, mod_cfg)

        self.dcp_update(channel)
        self.dcp_start(channel)

    @rpc_method
    def set_digital_modulation(self,
                               channel: OutputChannel,
                               frequency: float,
                               amplitude: float,
                               phase: float,
                               mod_input: int,
                               mod_invert: bool
                               ) -> None:
        """Configure the specified channel to produce a single tone with digital on/off modulation.

        The frequency will be rounded to the closest integer multiple of
        the internal frequency resolution (see `Wieserlabs_FlexDDS_NG_Dual.FREQUENCY_RESOLUTION`).

        The amplitude is a linear voltage scale factor, expressed as a fraction
        of the maximum output amplitude: +10 dBm (2 Vpp).

        This function assumes that the FlexDDS is in a "normal" configuration.
        When in doubt, call `dds_reset()` before calling this function.

        Parameters:
            channel:    Select one or both output channels.
            frequency:  Tone frequency in Hz (range 300 kHz ... 400 MHz).
            amplitude:  Amplitude scale factor (range 0.0 ... 1.0).
            phase:      Phase offset as fraction of the full sine wave period (range 0.0 ... 1.0).
            mod_input:  Digital input channel for on/off modulation (0 = BNC port A, 1 = BNC port B, 2 = BNC port C).
            mod_invert: True to invert the modulation signal (high TTL signal on BNC input disables the RF output);
                        False to use the non-inverted modulation signal (high TTL signal on BNC enables the RF output).
        """

        if (frequency < 0) or (frequency > self.MAX_FREQUENCY):
            raise ValueError("Invalid frequency")
        if (amplitude < 0) or (amplitude > 1.0):
            raise ValueError("Invalid amplitude")
        if (phase < 0) or (phase > 1.0):
            raise ValueError("Invalid phase")
        if mod_input not in (0, 1, 2):
            raise ValueError("Invalid modulation input channel")

        # Calculate DDS register values.
        # Enable manual OSK mode to allow switching between amplitude 0 and configured amplitude.
        ampl_scale = self._calc_ampl_scale(amplitude)
        cfr1 = self._calc_reg_cfr1(osk_enable=True,
                                   manual_osk=True,
                                   auto_osk=False)
        cfr2 = self._calc_reg_cfr2(ampl_scale_en=True,
                                   match_latency=True,
                                   hold_last_value=True,
                                   parallel_data_en=False)
        stp0 = self._calc_reg_stp(ampl_scale=ampl_scale,
                                  phase_offset=self._calc_phase_offset(phase),
                                  ftw=self._calc_ftw(frequency))

        # Switch the selected BNC port to input mode.
        #   bits 31:30 = WSCT = 00 = write register
        #   bit 9 = DIR       =  0 = input
        #   bit 8 = INV       =  0 = non-inverted
        #   bits 6:0 = OUT_MUX = 0 = not used in input mode
        bnc_reg = [DcpRegister.CFG_BNC_A,
                   DcpRegister.CFG_BNC_B,
                   DcpRegister.CFG_BNC_C][mod_input]
        self.dcp_register_write(OutputChannel.OUT0, bnc_reg, 0)

        # Route the BNC port to the OSK pin of the AD9910.
        cfg_osk = (2 << 9)                          # OPMODE = 2 (route MUX output to OSK)
        cfg_osk |= (1 << 8) if mod_invert else 0    # INV
        cfg_osk |= 5 + 3 * mod_input                # MUX = BNC_IN_[ABC]_LEVEL
        self.dcp_register_write(channel, DcpRegister.CFG_OSK, cfg_osk)

        # Configure DDS.
        # Note in OSK mode the AD9910 will take amplitude from the ASF register, not from STP0.
        self.dcp_spi_write(channel, DdsRegister.CFR1, cfr1)
        self.dcp_spi_write(channel, DdsRegister.CFR2, cfr2)
        self.dcp_spi_write(channel, DdsRegister.STP0, stp0)
        self.dcp_spi_write(channel, DdsRegister.ASF, ampl_scale << 2, wait_spi=True)

        self.dcp_update(channel)
        self.dcp_start(channel)

    @rpc_method
    def set_phase_modulation(self,
                             channel: OutputChannel,
                             frequency: float,
                             amplitude: float,
                             mod_input: int,
                             mod_offset: float,
                             mod_scale: float
                             ) -> None:
        """Configure the specified channel for a single tone with analog phase modulation.

        The effective phase can be calculated as follows::

            P = mod_scale * (M + mod_offset)

        where `M` is the signal level of the analog modulation input in Volt (range -0.5 ... +0.5);
              `P` is the effective phase as fraction of the full sine wave period (range 0.0 ... 1.0).

        The effective phase `P` will be clipped to the range 0.0 ... 1.0.
        It is thus not possible to shift the phase through multiple periods of the sine wave.

        This function assumes that the FlexDDS is in a "normal" configuration.
        When in doubt, call `dds_reset()` before calling this function.

        Parameters:
            channel:    Select one or both output channels.
            frequency:  Tone frequency in Hz (range 300 kHz ... 400 MHz).
            amplitude:  Amplitude scale factor (range 0.0 ... 1.0).
            mod_input:  Analog input channel for amplitude modulation (0 or 1).
            mod_offset: Offset to add to the analog input signal in Volt (range -0.5 ... +0.5).
            mod_scale:  Scale factor from analog input signal to RF phase,
                        where 1.0 means that the full range of the analog input corresponds
                        to one full sine wave period (range -30.0 ... +30.0).
        """

        if (frequency < 0) or (frequency > self.MAX_FREQUENCY):
            raise ValueError("Invalid frequency")
        if (amplitude < -2.0) or (amplitude > 2.0):
            raise ValueError("Invalid amplitude parameter")
        if mod_input not in (0, 1):
            raise ValueError("Invalid mod_input parameter")
        if abs(mod_offset) > self.MAX_ANALOG_INPUT_VOLT:
            raise ValueError("Invalid mod_offset parameter")
        if (mod_scale < -30.0) or (mod_scale > 30.0):
            raise ValueError("Invalid mod_scale parameter")

        # Phase modulation requires the DCP and DDS working together as follows:
        # The DCP samples the analog input signal and converts the level to
        # an unsigned 16-bit word, based on scaling parameters that we specify.
        # The DCP feeds this 16-bit word to the DDS as "parallel data".
        # The DDS uses the the parallel data word as the effective phase,
        # mapping word values 0 .. 2**16 to phase range 0 .. 2*Pi.

        # Calculate DDS register values.
        # Enable "parallel data" to allow modulation.
        cfr1 = self._calc_reg_cfr1()
        cfr2 = self._calc_reg_cfr2(ampl_scale_en=True,
                                   match_latency=True,
                                   hold_last_value=True,
                                   parallel_data_en=True)
        stp0 = self._calc_reg_stp(ampl_scale=self._calc_ampl_scale(amplitude),
                                  phase_offset=0,
                                  ftw=self._calc_ftw(frequency))

        # The ADC values from the modulation input are in range (-2**15 ... 2**15-1).
        # Scale the input offset to match that range.
        mod_input_offset_raw = int(round(mod_offset / self.MAX_ANALOG_INPUT_VOLT * 2**15))
        mod_input_offset_raw = self._wrap_signed(mod_input_offset_raw, 18)

        # The offset-corrected ADC values are multiplied by the raw scale factor,
        # then divided by 2**12. Calculate the raw scale factor to match
        # the specified effective scale factor.
        mod_scale_raw = int(round(mod_scale * 2**12))
        mod_scale_raw = self._wrap_signed(mod_scale_raw, 18)

        # Configure DDS.
        self.dcp_spi_write(channel, DdsRegister.CFR1, cfr1)
        self.dcp_spi_write(channel, DdsRegister.CFR2, cfr2)
        self.dcp_spi_write(channel, DdsRegister.STP0, stp0, wait_spi=True)

        # Configure modulation registers.
        mod_global_offset_raw = 0
        self.dcp_register_write(channel, DcpRegister.AM_O, mod_global_offset_raw)
        if mod_input == 0:
            # Use analog input channel 0.
            self.dcp_register_write(channel, DcpRegister.AM_S1, 0)
            self.dcp_register_write(channel, DcpRegister.AM_O0, mod_input_offset_raw)
            self.dcp_register_write(channel, DcpRegister.AM_S0, mod_scale_raw)
        else:
            # Use analog input channel 1.
            self.dcp_register_write(channel, DcpRegister.AM_S0, 0)
            self.dcp_register_write(channel, DcpRegister.AM_O1, mod_input_offset_raw)
            self.dcp_register_write(channel, DcpRegister.AM_S1, mod_scale_raw)

        # Analog modulation config register:
        #   bit 29   = update modulation settings
        #   bits 1:0 = 01 = phase modulation
        mod_cfg = (1 << 29) | 0b01
        self.dcp_register_write(channel, DcpRegister.AM_CFG, mod_cfg)

        self.dcp_update(channel)
        self.dcp_start(channel)
