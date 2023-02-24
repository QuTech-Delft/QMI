"""Instrument driver for the Siglent SDS1202X-E oscilloscope."""

import logging
from typing import Tuple, Union, NamedTuple
from enum import Enum

import numpy as np

from qmi.core.instrument import QMI_Instrument
from qmi.core.context import QMI_Context
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.core.rpc import rpc_method
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException

_logger = logging.getLogger(__name__)

_TIMEOUT = 2.0  # default per documentation
_SCDP_SIZE = 768066
_MAGIC_NUMBER_FROM_DATASHEET = 25.0
_DEVISIONS_FROM_EDGE_TO_CENTRE = 7.0
_CHANNEL_COUNT = 5


class CommHeader(Enum):
    LONG  = "long"
    SHORT = "short"
    OFF   = "off"


class TriggerCondition(NamedTuple):
    """A NamedTuple to hold parameters returned from 'trse?' query.

    Arguments:
        trig_type: Trigger Type.
        source: Trigger Source.
        hold_type: Trigger Hold type.
        hold_value: Trigger Hold value with unit.
        hold_value2: Second trigger Hold value with unit.
    """
    trig_type: str
    source: str
    hold_type: str
    hold_value: str
    hold_value2: str


def _validate_channel(channel: int, trigger: bool = False) -> str:
    """Validate the channel number is OK and return the correct source string."""
    if not trigger:
        if not 1 <= channel <= _CHANNEL_COUNT - 1:
            raise ValueError(f"Channel has to be between 1 and {_CHANNEL_COUNT - 1}, but is {channel}.")

    else:
        if not 0 <= channel <= _CHANNEL_COUNT:
            raise ValueError(f"Channel has to be between 0 and {_CHANNEL_COUNT}, but is {channel}.")

        if channel == 0:
            return "ex"

        elif channel == 5:
            return "ex5"

    return f"c{channel}"


class SDS1202XE(QMI_Instrument):
    """Instrument driver for the Siglent SDS1202X-E oscilloscope."""
    TIME_DIVISIONS = (
        "1ns", "2ns", "5ns", "10ns", "20ns", "50ns", "100ns", "200ns", "500ns",
        "1us", "2us", "5us", "10us", "20us", "50us", "100us", "200us", "500us",
        "1ms", "2ms", "5ms", "10ms", "20ms", "50ms", "100ms", "200ms", "500ms",
        "1s", "2s", "5s", "10s", "20s", "50s", "100s",
        )
    TRACES = ("MATH", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8",
              "D9", "D10", "D11", "D12", "D13", "D14", "D15")

    def __init__(self, context: QMI_Context, name: str, scpi_transport: str) -> None:
        """ Initialize the driver.

        Arguments:
            name: Name for this instrument instance.
            scpi_transport: QMI transport descriptor for the SCPI channel.
        """
        super().__init__(context, name)

        self._scpi_transport = create_transport(scpi_transport)
        self._scpi_protocol = ScpiProtocol(self._scpi_transport, default_timeout=_TIMEOUT)

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to instrument")
        self._scpi_transport.open()
        super().open()
        # The methods below expect that the command headers are turned OFF in the replies. So turn it OFF by standard.
        self.set_comm_header(CommHeader.OFF)

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to instrument")
        super().close()
        self._scpi_transport.close()

    @rpc_method
    def get_id(self) -> str:
        """ Query oscilloscope identification string.

        Returns:
            Module identification string.
        """
        return self._scpi_protocol.ask("*IDN?")

    @rpc_method
    def set_comm_header(self, fmt: CommHeader):
        """ Set communication header format.

        Arguments:
            header: Header format for communication replies.
        """
        self._scpi_protocol.write(f"chdr {fmt.value}")

    @rpc_method
    def get_voltage_per_division(self, channel: int) -> float:
        """ Query voltage per division for specified channel.

        Arguments:
            channel: Specified channel

        Returns:
            Voltage per division.
        """
        source = _validate_channel(channel)
        resp = self._scpi_protocol.ask(f"{source}:vdiv?")
        try:
            return float(resp)

        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid voltage per division, received {resp!r}.") from err

    @rpc_method
    def set_voltage_per_division(self, channel: int, v_div: float) -> None:
        """ Set voltage per division for specified channel.

        Arguments:
            channel: Specified channel
            v_div: Voltage per division, in Volts
        """
        source = _validate_channel(channel)
        if v_div < 500E-6 or v_div > 10:
            raise ValueError(f"Division voltage given [{v_div}] out of range of 0.5mV - 10V!")

        self._scpi_protocol.write(f"{source}:vdiv {v_div}")

    @rpc_method
    def get_voltage_offset(self, channel: int) -> float:
        """ Query voltage offset for specified channel.

        Arguments:
            channel: Specified channel

        Returns:
            Voltage offset.
        """
        source = _validate_channel(channel)
        resp = self._scpi_protocol.ask(f"{source}:ofst?")
        try:
            return float(resp)

        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid voltage offset, received {resp!r}.") from err

    @rpc_method
    def set_voltage_offset(self, channel: int, offset: float) -> None:
        """ Set voltage offset for specified channel.

        Arguments:
            channel: Specified channel
            offset: Voltage offset, in Volts
        """
        source = _validate_channel(channel)
        self._scpi_protocol.write(f"{source}:ofst {offset}")

    @rpc_method
    def get_time_per_division(self) -> float:
        """ Query time per division for oscilloscope.

        Returns:
            Time per division in seconds.
        """
        resp = self._scpi_protocol.ask("tdiv?")
        try:
            return float(resp)

        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid time per division, received {resp!r}.") from err

    @rpc_method
    def set_time_per_division(self, t_div: int, unit: str = "s") -> None:
        """ Set the horizontal scale (time) per division for oscilloscope. The input values must make one of the pre-
        defined allowed values ranging from 1ns to 100s: [1NS, 2NS, 5NS, 10NS, 20NS, 50NS, 100NS, 200NS, 500NS, 1US,
        2US, 5US, 10US, 20US, 50US, 100US, 200US, 500US, 1MS, 2MS, 5MS, 10MS, 20MS, 50MS, 100MS, 200MS, 500MS, 1S, 2S,
        5S, 10S, 20S, 50S, 100S].

        Arguments:
            t_div: Time per division value, can be [1, 2, 5, 10, 20, 50, 100, 200, 500].
            unit: Time per division unit, can be [ns, us, ms, s].
        """
        t_div_unit = f"{t_div}{unit}"
        if t_div_unit.lower() not in self.TIME_DIVISIONS:
            raise ValueError(f"Invalid time per division input: {t_div_unit}" +
                             " not in list of allowed values.")

        self._scpi_protocol.write(f"tdiv {t_div_unit}")

    @rpc_method
    def get_sample_rate(self) -> float:
        """ Query sample rate for oscilloscope.

        Returns:
            Sample rate.
        """
        resp = self._scpi_protocol.ask("sara?")
        try:
            return float(resp)

        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid sample rate, received {resp!r}.") from err

    @rpc_method
    def get_trigger_coupling(self, channel: int) -> str:
        """Query trigger coupling type of a given channel.

        Parameters:
            channel: The channel number.

        Returns:
            The trigger coupling type.

        """
        source = _validate_channel(channel, True)
        return self._scpi_protocol.ask(f"{source}:trcp?")

    @rpc_method
    def set_trigger_coupling(self, channel: int, coupling: str):
        """Set the trigger coupling type of a given channel.

        Parameters:
            channel: The channel number.
            coupling: The coupling type [AC, DC, HFREJ, LFREJ].
        """
        source = _validate_channel(channel, True)
        if coupling.lower() not in ["ac", "dc", "hfrej", "lfrej"]:
            raise ValueError(f"Invalid channel coupling type {coupling}!")

        self._scpi_protocol.write(f"{source}:trcp {coupling}")

    @rpc_method
    def get_trigger_level(self, channel: int) -> float:
        """Query the trigger level of a given channel.

        Parameters:
            channel: The channel number.

        Returns:
            The trigger level.
        """
        source = _validate_channel(channel, True)
        resp = self._scpi_protocol.ask(f"{source}:trlv?")
        try:
            return float(resp)

        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid trigger level, received {resp!r}.") from err

    @rpc_method
    def set_trigger_level(self, channel: int, trig_level: float) -> None:
        """Set trigger level for a given channel. The trigger level is checked for internal triggers, with the range of
        -4.5*DIV to 4.5*DIV. There is also a limit of -3*DIV to +3*DIV for external trigger levels. If the value is not
        within the range, the controller sets it to the nearest edge value. Note that the trigger range might not be
        centered to 0V, but at the current offset value.

        Parameters:
            channel: The channel number.
            trig_level: Trigger level voltage (Volts).
        """
        source = _validate_channel(channel, True)
        self._scpi_protocol.write(f"{source}:trlv {trig_level}")

    @rpc_method
    def get_trigger_mode(self):
        """Query the oscilloscope trigger mode.

        Returns:
            The trigger mode.
        """
        return self._scpi_protocol.ask("trmd?")

    @rpc_method
    def set_trigger_mode(self, mode: str):
        """Set the oscilloscope trigger mode.

        Parameters:
            mode: The oscilloscope trigger mode [AUTO, NORM, SINGLE, STOP].
        """
        if mode.lower() not in ["auto", "norm", "single", "stop"]:
            raise ValueError(f"Invalid oscilloscope trigger mode {mode}!")

        self._scpi_protocol.write(f"trmd {mode}")

    @rpc_method
    def get_trigger_select(self) -> TriggerCondition:
        """Get the selected trigger condition for waveform acquisition.

        Returns:
            trigger_parameters: NamedTuple holding the received parameters parsed from the response string:
            trig_type, source, hold_type, hold_value[, hold_value2].
        """
        resp = self._scpi_protocol.ask("trse?")
        trig_type, source, hold_type, hold_value, hold_value2 = resp.split(",")
        return TriggerCondition(
            trig_type=trig_type,
            source=source,
            hold_type=hold_type,
            hold_value=hold_value,
            hold_value2=hold_value2
        )

    @rpc_method
    def get_trigger_slope(self, channel: int) -> str:
        """Get the trigger slope setting of a specific channel.

        Parameters:
            channel: The channel number.

        Returns:
            The trigger slope of selected channel
        """
        source = _validate_channel(channel, True)
        return self._scpi_protocol.ask(f"{source}:trsl?")

    @rpc_method
    def set_trigger_slope(self, channel: int, slope: str) -> None:
        """Set the trigger slope for a specific channel.

        Parameters:
            channel: The channel number.
            slope: The slope type, must be one of following values: NEG, POS, WINDOW

        Returns:
            The trigger slope of selected channel
        """
        source = _validate_channel(channel, True)
        if slope.lower() not in ["neg", "pos", "window"]:
            raise ValueError(f"Invalid channel trigger slope {slope}!")

        self._scpi_protocol.write(f"{source}:trsl {slope}")

    @rpc_method
    def arm_trigger(self):
        """Start a new signal acquisition."""
        self._scpi_protocol.write("arm")

    @rpc_method
    def stop_acquisition(self):
        """Stop acquisition."""
        self._scpi_protocol.write("stop")

    @rpc_method
    def get_trigger_state(self) -> int:
        """Query the internal state change register. Not that this query returns only values of 0th bit or 13th bit.

        Returns:
            Value in range of 16 bits. 0: No signal acquired, register is cleared. 1: A new signal has been acquired.
            8192: Trigger is ready, no acquisition. 8193: Trigger is ready, acquisition stopped.
        """
        resp = self._scpi_protocol.ask("inr?")
        try:
            return int(resp)

        except ValueError as err:
            raise QMI_InstrumentException(f"Invalid state change register value, received {resp!r}.") from err

    @rpc_method
    def screen_dump(self) -> bytes:
        """ Query oscilloscope for screen dump.

        Returns:
            Raw bytes of a bitmap of the oscilloscope display.
        """
        self._scpi_protocol.write("SCDP")
        dump = self._scpi_transport.read(_SCDP_SIZE, _TIMEOUT)
        term = self._scpi_transport.read(1, _TIMEOUT)
        if term != b'\n':
            raise QMI_InstrumentException(f"Expected '\\n', but received {term!r} instead.")
        return dump

    @rpc_method
    def get_waveform(self, channel: Union[int, str]) -> bytes:
        """ Saves and acquires the raw bytes of a waveform trace for a specified source from the oscilloscope
        waveform memory. This can come from analog or digital channels or from FFT waveform ("MATH").

        Arguments:
            channel: Specific channel number for channels C1-C4 OR trace source from list {MATH,D0,D1,D2,...,D15}

        Returns:
            Raw bytes of the waveform.
        """
        if type(channel) is int:
            source = _validate_channel(channel)

        elif type(channel) is str:
            ch = str(channel)
            if ch.upper() in self.TRACES:
                source = channel

            else:
                raise QMI_UsageException(f"Cannot acquire a waveform trace from source {channel}.")

        else:
            raise QMI_UsageException(f"Cannot acquire a waveform trace from source {channel}.")

        self._scpi_protocol.write(f"{source}:wf? dat2")  # save waveform to memory

        # read and verify response header
        header = self._scpi_transport.read(5, _TIMEOUT)
        if header != b"DAT2,":
            raise QMI_InstrumentException(f"Invalid response header, expected b\'DAT2,\', received {header!r}.")

        waveform = self._scpi_protocol.read_binary_data()  # read data

        # read and verify terminator
        term = self._scpi_transport.read(1, _TIMEOUT)
        if term != b'\n':
            raise QMI_InstrumentException(f"Invalid terminator, expected b\'\\n\', received {term!r}.")

        return waveform

    @rpc_method
    def trace_dump(self, channel: int) -> Tuple[np.ndarray, np.ndarray]:
        """Query oscilloscope for trace dump of specified channel. See page 331 from Programming guide [PG01-E02C]

        Arguments:
            channel: Channel which trace should be dumped.

        Returns:
            Tuple containing the time and voltage data of the trace of the specified channel.
        """
        self._scpi_transport.discard_read()  # clear buffer
        self.set_comm_header(CommHeader.OFF)
        vdiv = self.get_voltage_per_division(channel)
        ofst = self.get_voltage_offset(channel)
        tdiv = self.get_time_per_division()
        sara = self.get_sample_rate()
        trace = self.get_waveform(channel)

        # convert data to volts
        vdata = np.frombuffer(trace, dtype='i1').astype(float) * vdiv / _MAGIC_NUMBER_FROM_DATASHEET - ofst
        # generate time data
        tdata = np.arange(vdata.size) * 1.0 / sara - tdiv * _DEVISIONS_FROM_EDGE_TO_CENTRE

        return tdata, vdata
