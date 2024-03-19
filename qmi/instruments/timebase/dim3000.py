"""QMI Instrument driver for the TimeBase DIM3000 AOM driver."""

from dataclasses import dataclass, fields
from enum import IntEnum
import logging
import time
from typing import Dict, Optional, Tuple, Type, TypeVar, Union, ClassVar, get_origin, get_args
import re

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


T = TypeVar("T", bound="DIM3000Base")


class DIM3000SweepMode(IntEnum):
    """Options for frequency sweep mode."""

    OFF = 0
    TRI_INT_TRIG = 1
    TRI_EXT_TRIG = 2
    SAW_INT_TRIG = 3
    SAW_EXT_TRIG = 4


class DIM3000FMDeviation(IntEnum):
    """Options for available frequency deviation during frequency modulation."""

    _3200HZ = 0
    _6400HZ = 1
    _12800HZ = 2
    _25600HZ = 3
    _51200HZ = 4
    _102400HZ = 5
    _204800HZ = 6
    _409600HZ = 7
    _819200HZ = 8
    _1638400HZ = 9
    _3276800HZ = 10
    _6553600HZ = 11
    _13107200HZ = 12
    _26214400HZ = 13
    _52428800HZ = 14
    _104857600HZ = 15


@dataclass(frozen=True)
class DIM3000Base:
    """Base class that gives all dataclasses the factory function."""

    PATTERN: ClassVar[str]
    """RegEx that will be used for pattern matching on the string received from the device."""

    @classmethod
    def from_string(cls: Type[T], string: str) -> T:
        """Factory function for making a dataclass from a string received from device."""

        if (match := re.match(cls.PATTERN, string)) is None:
            raise QMI_InstrumentException(f"Unexpected string returned from device: {string}")

        kwargs: Dict[str, Union[int, float, bool, str, None]] = {}

        for field in fields(cls):
            # remap optional field type
            if get_origin(field.type) is Union:
                field_type = get_args(field.type)[0]
            else:
                field_type = field.type

            # optional fields might not have match, so set to None
            if match[field.name] is None:
                kwargs[field.name] = None
            elif field_type is int:
                kwargs[field.name] = int(match[field.name])
            elif field_type is float:
                kwargs[field.name] = float(match[field.name])
            elif field_type is bool:
                kwargs[field.name] = bool(int(match[field.name]))
            elif field_type is str:
                kwargs[field.name] = match[field.name]
            elif issubclass(field_type, IntEnum):
                kwargs[field.name] = field_type(int(match[field.name]))
            else:
                raise RuntimeError(f"Unexpected type {field_type} for {cls}!")

        return cls(**kwargs)


@dataclass(frozen=True)
class DIM3000DevInfo(DIM3000Base):
    """Dataclass containing device information."""

    PATTERN = r"^Rdev:(?P<dev>\w*)\|" r"Rhv:(?P<hv>\w*)\|" r"Rfv:(?P<fv>\w*)\|" r"Rfb:(?P<fb>\w*)\|" r"Rsn:(?P<sn>\w*)"
    dev: str
    hv: str
    fv: str
    fb: str
    sn: str


@dataclass(frozen=True)
class DIM3000InitData(DIM3000Base):
    """Dataclass containing initial data."""

    PATTERN = (
        r"^Ramoffsmin:(?P<amoffsmin>-?\d*)\|"
        r"Ramoffsmax:(?P<amoffsmax>-?\d*)\|"
        r"Ramoffsnom:(?P<amoffsnom>-?\d*)\|"
        r"(Rbtstat:(?P<btstat>\d)\|)?"
        r"(Radcoffs:(?P<adcoffs>-?\d*)\|)?"
        r"Rinit:(?P<init>\d)"
    )
    amoffsmin: int
    amoffsmax: int
    amoffsnom: int
    btstat: Optional[bool]
    adcoffs: Optional[int]
    init: bool


@dataclass(frozen=True)
class DIM3000Parameters(DIM3000Base):
    """Dataclass containing parameter data."""

    PATTERN = (
        r"^Rfreq:(?P<freq>\d*)\|"
        r"Rampl:(?P<ampl>\d*)\|"
        r"Rout:(?P<out>\d*)\|"
        r"Rpmon:\d*\|"
        r"Rpmfr:\d*\|"
        r"Rpmd:\d*\|"
        r"Rpmphc:\d*\|"
        r"Rswpm:(?P<swpm>\d*)\|"
        r"Rswps:(?P<swps>\d*)\|"
        r"Rswpp:(?P<swpp>\d*)\|"
        r"Rswpf:(?P<swpf>\d*)\|"
        r"Rswpt:(?P<swpt>\d*)\|"
        r"Rfmon:(?P<fmon>\d*)\|"
        r"Rfmdev:(?P<fmdev>\d*)\|"
        r"Rplson:(?P<plson>\d*)\|"
        r"Rplsfr:(?P<plsfr>\d*)\|"
        r"Rplsdt:(?P<plsdt>\d*)\|"
        r"Rffreq:(?P<ffreq>\d*)\|"
        r"Rfampl:(?P<fampl>\d*)\|"
        r"Ramoffs:(?P<amoffs>-?\d*)\|"
        r"Rpcbtemp:(?P<pcbtemp>\d*)\|"
        r"Rrefstat:(?P<refstat>\d*)\|"
        r"Rreflev:(?P<reflev>-?\d*)\|"
        r"Rvcclev:(?P<vcclev>\d*)"
    )
    freq: int
    ampl: float
    out: bool
    swpm: DIM3000SweepMode
    swps: int
    swpp: int
    swpf: int
    swpt: int
    fmon: bool
    fmdev: DIM3000FMDeviation
    plson: bool
    plsfr: int
    plsdt: int
    ffreq: int
    fampl: float
    amoffs: int
    pcbtemp: float
    refstat: bool
    reflev: int
    vcclev: float

    def __post_init__(self):
        # Correct some scaling of parameters
        # Using __setattr__ because this is what is recommended by python when working with frozen classes
        # See https://docs.python.org/3/library/dataclasses.html#frozen-instances
        object.__setattr__(self, "ampl", self.ampl / 10.0)
        object.__setattr__(self, "fampl", self.fampl / 10.0)
        object.__setattr__(self, "pcbtemp", self.pcbtemp / 100.0)
        object.__setattr__(self, "vcclev", self.vcclev / 100.0)


class TimeBase_DIM3000(QMI_Instrument):
    """QMI Instrument driver for the TimeBase DIM3000 AOM driver."""

    _rpc_constants = [
        "FREQ_RANGE",
        "TIME_RANGE",
        "PULSE_FREQ_RANGE",
        "DUTY_CYCLE_RANGE",
        "AM_OFFSET_RANGE",
        "MINIMUM_EXEC_DELAY_S",
    ]

    # Public class constants
    FREQ_RANGE = (10, 400_000_000)
    TIME_RANGE = (4, 262000)
    PULSE_FREQ_RANGE = (20, 1000)
    DUTY_CYCLE_RANGE = (1, 99)
    AM_OFFSET_RANGE = (-255, 25)
    MINIMUM_EXEC_DELAY_S = 0.1  # Maximum execution speed of 10 cmds/sec from manual

    _RESPONSE_TIMEOUT_S = 2.0
    _TERMINATOR = b"\n"

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialization of the TimeBase DIM3000 instrument driver.

        Note:
            Maximum execution speed is about 10 commands/sec.

        Parameters:
            name: Name for this instrument instance.
            transport: Transport descriptor to access the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 19200})
        self._prev_cmd_ts = 0.0

    def _write_par(self, par: str, val: int) -> None:
        """Set a parameter of the device with a specified value."""
        self._check_is_open()
        self._check_cmd_exec_speed(time.monotonic())
        self._transport.write(f"S{par}:{val}".encode("ascii") + self._TERMINATOR)

    def _ask(self, cmd: str) -> str:
        """Send command to instrument and return response from instrument."""
        self._check_is_open()
        self._check_cmd_exec_speed(time.monotonic())
        self._transport.discard_read()
        self._transport.write(cmd.encode("ascii") + self._TERMINATOR)
        resp = self._transport.read_until(message_terminator=self._TERMINATOR, timeout=self._RESPONSE_TIMEOUT_S)
        return resp.rstrip().decode("ascii")

    def _check_cmd_exec_speed(self, now: float) -> None:
        """Checks if command execution is higher than expected."""
        if (delay := now - self._prev_cmd_ts) < self.MINIMUM_EXEC_DELAY_S:
            _logger.warning(
                "Delay since previous command (%f) is shorter than recommended (%f)!", delay, self.MINIMUM_EXEC_DELAY_S
            )
        self._prev_cmd_ts = now

    def _check_range(self, range: Tuple[int, int], val: int) -> None:
        """Checks if value is in range."""
        if not range[0] <= val <= range[1]:
            raise ValueError(f"Value ({val}) is not in range {range}!")

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Get the device info in the `QMI_InstrumentIdentification` format."""
        dev_info = self.get_device_info()
        return QMI_InstrumentIdentification(
            vendor="TimeBase",
            model=f"DIM3000[{dev_info.dev}]",
            serial=dev_info.sn,
            version=f"{dev_info.hv}.{dev_info.fv}.{dev_info.fb}",
        )

    @rpc_method
    def get_device_info(self) -> DIM3000DevInfo:
        """Get the device info from the device."""
        return DIM3000DevInfo.from_string(self._ask("Gdev"))

    @rpc_method
    def get_init_data(self) -> DIM3000InitData:
        """Get initial data from the device."""
        return DIM3000InitData.from_string(self._ask("Ginit"))

    @rpc_method
    def get_parameters(self) -> DIM3000Parameters:
        """Get parameters from the device."""
        return DIM3000Parameters.from_string(self._ask("Gpar"))

    @rpc_method
    def set_output_frequency(self, freq_hz: int) -> None:
        """Set the output frequency in Hz."""
        self._check_range(self.FREQ_RANGE, freq_hz)
        self._write_par("freq", int(freq_hz))

    @rpc_method
    def set_output_amplitude(self, ampl_dbm: float) -> None:
        """Set the output amplitude in dBm."""
        self._write_par("ampl", int(ampl_dbm * 10.0))

    @rpc_method
    def set_sweep_mode(self, swpm: DIM3000SweepMode) -> None:
        """Set the sweep mode. See `DIM3000SweepMode`."""
        self._write_par("swpm", swpm.value)

    @rpc_method
    def set_sweep_start_frequency(self, swps_hz: int) -> None:
        """Set the sweep start frequency in Hz."""
        self._check_range(self.FREQ_RANGE, swps_hz)
        self._write_par("swps", int(swps_hz))

    @rpc_method
    def set_sweep_stop_frequency(self, swpp_hz: int) -> None:
        """Set the sweep stop frequency in Hz."""
        self._check_range(self.FREQ_RANGE, swpp_hz)
        self._write_par("swpp", int(swpp_hz))

    @rpc_method
    def set_sweep_step_frequency(self, swpf_hz: int) -> None:
        """Set the sweep step frequency in Hz."""
        self._check_range(self.FREQ_RANGE, swpf_hz)
        self._write_par("swpf", int(swpf_hz))

    @rpc_method
    def set_sweep_step_time(self, swpt_ns: int) -> None:
        """Set the sweep step time in nanoseconds."""
        self._check_range(self.TIME_RANGE, swpt_ns)
        self._write_par("swpt", int(swpt_ns))

    @rpc_method
    def set_fm_input(self, fmon: bool) -> None:
        """Set FM input."""
        self._write_par("fmon", int(fmon))

    @rpc_method
    def enable_fm_input(self) -> None:
        """Enable FM input."""
        self._write_par("fmon", int(True))

    @rpc_method
    def disable_fm_input(self) -> None:
        """Disable FM input."""
        self._write_par("fmon", int(False))

    @rpc_method
    def set_fm_deviation(self, fmdev: DIM3000FMDeviation) -> None:
        """Set FM deviation. See `DIM3000FMDeviation`."""
        self._write_par("fmdev", fmdev.value)

    @rpc_method
    def set_pulse_mode(self, plson: bool) -> None:
        """Set pulse mode."""
        self._write_par("plson", int(plson))

    @rpc_method
    def enable_pulse_mode(self) -> None:
        """Enable pulse mode."""
        self._write_par("plson", int(True))

    @rpc_method
    def disable_pulse_mode(self) -> None:
        """Disable pulse mode."""
        self._write_par("plson", int(False))

    @rpc_method
    def set_pulse_frequency(self, plsfr_hz: int) -> None:
        """Set the pulse frequency in Hz."""
        self._check_range(self.PULSE_FREQ_RANGE, plsfr_hz)
        self._write_par("plsfr", plsfr_hz)

    @rpc_method
    def set_pulse_duty_cycle(self, plsdt: int) -> None:
        """Set the pulse duty cycle [1-99]."""
        self._check_range(self.DUTY_CYCLE_RANGE, plsdt)
        self._write_par("plsdt", plsdt)

    @rpc_method
    def set_fsk_frequency(self, ffreq_hz: int) -> None:
        """Set the FSK frequency in Hz."""
        self._check_range(self.FREQ_RANGE, ffreq_hz)
        self._write_par("ffreq", ffreq_hz)

    @rpc_method
    def set_fsk_amplitude(self, fampl_dbm: float) -> None:
        """Set the FSK amplitude in dBm."""
        self._write_par("fampl", int(fampl_dbm * 10.0))

    @rpc_method
    def set_am_offset(self, amoffs: int) -> None:
        """Set the AM offset."""
        self._check_range(self.AM_OFFSET_RANGE, amoffs)
        self._write_par("amoffs", amoffs)
