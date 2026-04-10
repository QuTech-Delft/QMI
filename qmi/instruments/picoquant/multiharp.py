""" QMI instrument driver for the PicoQuant MultiHarp 150 instrument.

The instrument driver makes use of the manufacturer provided software libraries, "mhlib.so" for Linux OS,
or "mhlib.dll" or "mhlib64.dll" for 32-bit and 64-bit Windows OS, respectively.
Please find the licence terms for these files in the dedicated software package for the MultiHarp instrument at
https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules/multiharp-150-high-throughput-multichannel-event-timer-tcspc-unit
--> "Software" tab --> download link in "Current software and developer's library version".
"""
import ctypes
import enum
import logging
from fractions import Fraction

import numpy as np

from qmi.core.exceptions import QMI_InvalidOperationException
from qmi.core.rpc import rpc_method
from qmi.instruments.picoquant.support._library_wrapper import _LibWrapper
from qmi.instruments.picoquant._picoquant import _str_to_enum, _PicoquantHarp, _EDGE
from qmi.instruments.picoquant.support._events import _MODE

_logger = logging.getLogger(__name__)


@enum.unique
class _REFSRC(enum.Enum):
    """Symbolic constants for the :func:`~MultiHarpDevice.initialize` method's `refsource` argument.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """
    INTERNAL = 0
    """Use internal clock."""
    EXTERNAL_10MHZ = 1
    """Use 10 MHz external clock."""
    WR_MASTER_GENERIC = 2
    """White Rabbit master with generic partner."""
    WR_SLAVE_GENERIC = 3
    """White Rabbit slave with generic partner."""
    WR_GRANDM_GENERIC = 4
    """White Rabbit grand master with generic partner."""
    EXTN_GPS_PPS = 5
    """Use 10 MHz + PPS from GPS."""
    EXTN_GPS_PPS_UART = 6
    """Use 10 MHz + PPS + time via UART from GPS."""
    WR_MASTER_MHARP = 7
    """White Rabbit master with MultiHarp as partner."""
    WR_SLAVE_MHARP = 8
    """White Rabbit slave with MultiHarp as partner."""
    WR_GRANDM_MHARP = 9
    """White Rabbit grand master with MultiHarp as partner."""


@enum.unique
class _MEASCTL(enum.Enum):
    """Symbolic constants for the :func:`~MultiHarpDevice.setMeasurementControl` `control` argument.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """
    SINGLESHOT_CTC = 0
    """Default value.
       Acquisition starts by software command and runs until CTC expires. 
       The duration is set by the ``tacq`` parameter passed to ``MH_StartMeas``.
    """
    C1_GATED = 1
    """Data is collected for the period where C1 is active. 
       This can be the logical high or low period dependent
       on the value supplied to the parameter ``startedge``.
    """
    C1_START_CTC_STOP = 2
    """Data collection is started by a transition on C1 and
       stopped by expiration of the internal CTC. 
       Which transition actually triggers the start is given
       by the value supplied to the parameter ``startedge``. 
       Theduration is set by the ``tacq``parameter passed to MH_StartMeas.
    """
    C1_START_C2_STOP = 3
    """Data collection is started by a transition on C1 and stopped
       by a transition on C2. Which transitions actually trigger
       start and stop is given by the values supplied to the parameters startedge and ``stopedge```
    """
    WR_M2S = 4
    """Sets measurement conrol for a pair of devices such that the master device
       not only starts its own measurement but also that of the slave.
       This setting must be applied identivcally for both devices and it requires
       that the two devices have established a white rabbit connection.
    """
    WR_S2M = 5
    """Sets measurement conrol for a pair of devices such that the master device
       not only starts its own measurement but also that of the slave.
       This setting must be applied identivcally for both devices and it requires
       that the two devices have established a white rabbit connection. 
    """
    SW_START_SW_STOP = 6  # new since v3.1
    """Sets measurement control such that the duration of a measurement is purely under software control,
       i.e. started by te call of ``MH_StartMeas`` and stopped by the call of ``MH_StartMeas``. 
       This overcomes the time limits of the hardware CTC and allows virtually unlimited measurement times.
       The resulting shortcoming is that the resulting duration is then less precise.
    """

@enum.unique
class _FLAG(enum.Enum):
    """Bitfield constants for the return value of the :func:`~MultiHarpDevice.getFlags` function.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """
    OVERFLOW = 0x0001
    """Histogram mode only. It indicates that a histogram measurement has reached the maximum count 
    as specified via MH_SetStopOverflow."""
    FIFOFULL = 0x0002
    """TTTR mode only. It indicates that the data FiFo has run full. The measurement will then have
    to be aborted as data integrity is no longer maintained."""
    SYNC_LOST = 0x0004
    """This flag may occur in T3 mode and in histo mode. It indicates that the sync signal has been lost
    which in this case is critical as the function of T3 mode and histo mode relies on an uninterrupted
    sync signal."""
    REF_LOST = 0x0008
    """This flag will occur when the MultiHarp is programmed to use an external reference clock and this
    reference clock is lost."""
    SYSERROR = 0x0010
    """Indicates an error of the hardware or internal software. The user should in this case
    call the library routine MH_GetDebugInfo and provide the result to PicoQuant support."""
    ACTIVE = 0x0020
    """Measurement is running."""
    CNTS_DROPPED = 0x0040
    """Indicates that counts were dropped at the first level FiFo directly following the TDC of an input channel.
    This occurs typically only at extremely high count rates. Dependent on the application scenario this may or
    may not be considered critical."""


@enum.unique
class _WARNING(enum.Enum):
    """Bitfield constants for the return value of the :func:`~MultiHarpDevice.getWarnings` function.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file. For full descriptions
    see the chapter '8.1. Warnings' from the MultiHarp MHLib Manual.
    """
    SYNC_RATE_ZERO = 0x0001
    """No pulses are detected at the sync input. In histogramming and T3 mode this is crucial and the
    measurement will not work without this signal."""
    SYNC_RATE_VERY_LOW = 0x0002
    """The detected pulse rate at the sync input is below 100 Hz and cannot be determined accurately.
    Other warnings may not be reliable under this condition."""
    SYNC_RATE_TOO_HIGH = 0x0004
    """The pulse rate at the sync input (after the divider) is higher than 75 MHz. This is close to 
    the TDC limit. Sync events will be lost above 78 MHz."""
    INPT_RATE_ZERO = 0x0010
    """No counts are detected at any of the input channels."""
    INPT_RATE_TOO_HIGH = 0x0040
    """The overall pulse rate at the input channels is higher than 80 MHz (USB 3.0 connection) or higher
    than 9 MHz (USB 2.0 connection). The measurement will likely lead to a FIFO overrun."""
    INPT_RATE_RATIO = 0x0100
    """This warning is issued in histogramming and T3 mode when the rate at any input channel is higher
    than 5% of the sync rate."""
    DIVIDER_GREATER_ONE = 0x0200
    """In T2 mode: The sync divider is set larger than 1. This is probably not intended.
    In histogramming and T3 mode: If the pulse rate at the sync input is below 75 MHz then a divider
    >1 is not needed."""
    TIME_SPAN_TOO_SMALL = 0x0400
    """This warning is issued in histogramming and T3 mode when the sync period (1/SyncRate) is longer
    than the start to stop time span that can be covered by the histogram or by the T3 mode records."""
    OFFSET_UNNECESSARY = 0x0800
    """This warning is issued in histogramming and T3 mode when an offset >0 is set even though the sync
    period (1/SyncRate) can be covered by the measurement time span without using an offset."""
    DIVIDER_TOO_SMALL = 0x1000
    """The pulse rate at the sync input (after the divider) is higher than 75 MHz."""
    COUNTS_DROPPED = 0x2000
    """This warning is issued when the front end of the data processing pipeline was not able to process
    all events that came in."""


class _WR_STATUS(enum.Enum):
    """ White Rabbit subsystem status bit-masks.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """

    # status_link_on       1 bit  : bit  0
    # status_link_up       1 bit  : bit  1
    # status_mode          2 bits : bits 3..2
    # status_locked_calibd 1 bit  : bit  4
    # status_ptp           3 bits : bits 7..5
    # status_servo         3 bits : bits 10..8
    # status_mac_set       1 bit  : bit  11
    # (reserved)          19 bits : bits 30..12
    # status_is_new        1 bit  : bit  31

    LINK_ON = 0x00000001
    """WR link is switched on."""
    LINK_UP = 0x00000002
    """WR link is established."""

    MODE_BITMASK = 0x0000000C
    """Mask for the mode bits."""
    MODE_OFF = 0x00000000
    """Mode is "off"."""
    MODE_SLAVE = 0x00000004
    """Mode is "slave"."""
    MODE_MASTER = 0x00000008
    """Mode is "master"."""
    MODE_GMASTER = 0x0000000C
    """Mode is "grandmaster"."""

    LOCKED_CALIBD = 0x00000010
    """Locked and calibrated."""

    PTP_BITMASK = 0x000000E0
    """Mask for the PTP bits."""
    PTP_LISTENING = 0x00000020
    """(Undocumented)"""
    PTP_UNCLWRSLCK = 0x00000040
    """(Undocumented)"""
    PTP_SLAVE = 0x00000060
    """(Undocumented)"""
    PTP_MSTRWRMLCK = 0x00000080
    """(Undocumented)"""
    PTP_MASTER = 0x000000A0
    """(Undocumented)"""

    SERVO_BITMASK = 0x00000700
    """Mask for the servo bits."""
    SERVO_UNINITLZD = 0x00000100
    """(Undocumented)"""
    SERVO_SYNC_SEC = 0x00000200
    """(Undocumented)"""
    SERVO_SYNC_NSEC = 0x00000300
    """(Undocumented)"""
    SERVO_SYNC_PHASE = 0x00000400
    """(Undocumented)"""
    SERVO_WAIT_OFFST = 0x00000500
    """(Undocumented)"""
    SERVO_TRCK_PHASE = 0x00000600
    """(Undocumented)"""

    MAC_SET = 0x00000800
    """User-defined MAC address is set."""
    IS_NEW = 0x80000000
    """Status updated since last check."""


class PicoQuant_MultiHarp150(_PicoquantHarp):
    """Instrument driver for the PicoQuant MultiHarp 150."""

    _MODEL = "MH"
    _MAXDEVNUM = 8
    _TTREADMAX = 1048576

    @property
    def _max_dev_num(self):
        return self._MAXDEVNUM

    @property
    def _ttreadmax(self):
        return self._TTREADMAX

    @property
    def _model(self):
        return self._MODEL

    @property
    def _lib(self) -> _LibWrapper:
        if self._lazy_lib is None:  # type: ignore
            self._lazy_lib = _LibWrapper('MH')
        return self._lazy_lib

    @rpc_method
    def initialize(self, mode_str: str, refsource_str: str) -> None:
        """Initialize the device.

        This routine must be called before any of the other methods, except OpenDevice, CloseDevice,
        GetErrorString and GetLibraryVersion can be used.

        See the manual for more information on measurement modes, external clock, and
        White Rabbit (WR) functionality.

        Selecting WR as a clock source requires that a WR connection has actually been established beforehand.
        Unless the WR connection is established by a WR startup script this will require a two stage process
        initially initializing with internal clock source, then setting up the WR connection by means of the WR
        routines described below, then initializing again with the desired WR clock model.

        Arguments:
            mode_str (str): Opening mode. Can be any of 'HIST', 'T2', 'T3'.
                            The latest driver version V3.0+ supports T2 and T3 modes.
            refsource_str (str): Reference source for time. Can be any of 'INTERNAL', 'EXTERNAL_10MHZ',
                'WR_MASTER_GENERIC', 'WR_SLAVE_GENERIC', 'WR_GRANDM_GENERIC', 'EXTN_GPS_PPS', 'EXTN_GPS_PPS_UART',
                'WR_MASTER_MHARP', 'WR_SLAVE_MHARP', 'WR_GRANDM_MHARP'.

        Raises:
            ValueError: if either argument is an unknown string value.
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()

        if self._measurement_running:
            raise QMI_InvalidOperationException("Measurement still active")
        mode = _str_to_enum(_MODE, mode_str)
        if mode not in (_MODE.HIST, _MODE.T2, _MODE.T3):
            raise ValueError("Unsupported measurement mode")

        if self._lib_version.startswith("2") and mode is _MODE.T3:
            raise ValueError("Unsupported measurement mode")

        refsource = _str_to_enum(_REFSRC, refsource_str)

        with self._device_lock:
            self._lib.Initialize(self._devidx, mode.value, refsource.value)
            self._mode = mode

        # Reset the event filter configuration.
        self.set_event_filter(reset_filter=True)
        self.set_block_events(False)
        _logger.info("[%s] Initialized device with mode %s and source %s", self._name, mode.value, refsource.value)

    @rpc_method
    def get_module_info(self) -> list[tuple[int, int]]:
        self._check_is_open()
        info = []
        with self._device_lock:
            nummod = ctypes.c_int()
            self._lib.GetNumOfModules(self._devidx, nummod)
            for modidx in range(nummod.value):
                modelcode = ctypes.c_int()
                versioncode = ctypes.c_int()
                self._lib.GetModuleInfo(self._devidx, modidx, modelcode, versioncode)
                info.append((modelcode.value, versioncode.value))
        return info

    @rpc_method
    def set_sync_channel_offset(self, value: int) -> None:
        self._check_is_open()
        with self._device_lock:
            self._lib.SetSyncChannelOffset(self._devidx, value)

    @rpc_method
    def set_sync_edge_trigger(self, level: int, edge_str: str) -> None:
        """Set SYNC trigger level and edge.

        Arguments:
            level: Trigger level, in mV. A value ranging from :-1200 mV to +1200 mV.
            edge_str: Either 'RISING' or 'FALLING'.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        edge = _str_to_enum(_EDGE, edge_str)
        with self._device_lock:
            self._lib.SetSyncEdgeTrg(self._devidx, level, edge.value)

    @rpc_method
    def set_sync_dead_time(self, on: int, deadtime: int) -> None:
        """Set sync channel dead-time.

        Arguments:
            on: 0 = set minimal dead-time, 1 = activate extended dead-time.
            deadtime: extended dead-time in ps. Valid range from `constants.EXTDEADMIN` (800 ps) to
                `constants.EXTDEADMAX` (160000 ps).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetSyncDeadTime(self._devidx, on, deadtime)

    @rpc_method
    def set_input_edge_trigger(self, channel: int, level: int, edge_str: str) -> None:
        """Set input channel trigger level and edge.

        Arguments:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            level: Trigger level, in mV. A value ranging from -1200 mV to +1200 mV.
            edge_str: 'RISING' or 'FALLING'.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            edge = _str_to_enum(_EDGE, edge_str)
            self._lib.SetInputEdgeTrg(self._devidx, channel, level, edge.value)

    @rpc_method
    def set_input_channel_dead_time(self, channel: int, on: int, deadtime: int) -> None:
        """Set input channel dead-time.

        Arguments:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            on: 0 = set minimal dead-time, 1 = activate extended dead-time.
            deadtime: extended dead-time in ps. Valid range from `constants.EXTDEADMIN` (800 ps) to
                `constants.EXTDEADMAX` (160000 ps).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetInputDeadTime(self._devidx, channel, on, deadtime)

    @rpc_method
    def set_measurement_control(self, meascontrol_str: str, startedge_str: str, stopedge_str: str) -> None:
        self._check_is_open()
        meascontrol = _str_to_enum(_MEASCTL, meascontrol_str)
        startedge = _str_to_enum(_EDGE, startedge_str)
        stopedge = _str_to_enum(_EDGE, stopedge_str)
        with self._device_lock:
            self._lib.SetMeasControl(self._devidx, meascontrol.value, startedge.value, stopedge.value)

    @rpc_method
    def set_trigger_output(self, period: int) -> None:
        self._check_is_open()
        with self._device_lock:
            self._lib.SetTriggerOutput(self._devidx, period)

    @rpc_method
    def get_flags(self) -> list[str]:
        self._check_is_open()
        with self._device_lock:
            bitset = ctypes.c_int()
            self._lib.GetFlags(self._devidx, bitset)

            return [flag.name for flag in _FLAG if bitset.value & flag.value]

    @rpc_method
    def get_start_time(self) -> Fraction:
        """Get start time of measurement.

        Retrieve the start time of a measurement with picosecond resolution. It relates always to the start of the
        most recent measurement, be it completed or only just started. The result is to be interpreted in the sense
        of a unix time, i.e. elapsed picoseconds since January 1st 1970 00:00:00 UTC (Universal Time).

        Note that the actual resolution is the device's base resolution. Actual accuracy depends on the chosen time
        base, e.g., a White Rabbit grandmaster can be very accurate.

        With less accurate clocks the high resolution result can still be meaningful in a relative sense,
        e.g. between two devices synchronized over White Rabbit. With internal clocking the accuracy only reflects
        that of the PC clock.

        Returns:
            Start time as a Fraction, to ensure that no precision is lost.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            timedw2 = ctypes.c_uint()
            timedw1 = ctypes.c_uint()
            timedw0 = ctypes.c_uint()
            self._lib.GetStartTime(self._devidx, timedw2, timedw1, timedw0)

        timedw2_int = timedw2.value
        timedw1_int = timedw1.value
        timedw0_int = timedw0.value
        picoseconds = (timedw2_int << 64) | (timedw1_int << 32) | timedw0_int
        starttime = Fraction(picoseconds, 1000000000000)
        _logger.debug("[%s] Measurement start-time fraction is %s", self._name, starttime)
        return starttime

    @rpc_method
    def get_warnings(self) -> list[str]:
        self._check_is_open()
        with self._device_lock:
            bitset = ctypes.c_int()
            self._lib.GetWarnings(self._devidx, bitset)
            return [warning.name for warning in _WARNING if bitset.value & warning.value]

    @rpc_method
    def get_all_count_rates(self) -> tuple[int, tuple[int, ...]]:
        """Get count rates of SYNC and INPUT channels.

        This can be used as a replacement of :func:`get_sync_rate()` and :func:`get_count_rate()`
        when all rates need to be retrieved in an efficient manner.

        Returns:
            A tuple (syncrate, inputrates), where syncrate is the sync channel rate (integer),
            and inputrate is a tuple of integers (one per channel).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        with self._device_lock:
            nchannels = ctypes.c_int()
            self._lib.GetNumOfInputChannels(self._devidx, nchannels)
            num_channels = nchannels.value
            syncrate = ctypes.c_int()
            inputrates = (ctypes.c_int * num_channels)()
            self._lib.GetAllCountRates(self._devidx, syncrate, inputrates)
            syncrate_int = syncrate.value
            inputrates_tuple = tuple((int(i) for i in inputrates))
            return syncrate_int, inputrates_tuple

    @rpc_method
    def get_all_histograms(self) -> np.ndarray:
        self._check_is_open()
        channels = self.get_number_of_input_channels()
        with self._device_lock:
            all_histdata = np.empty((channels, self._actuallen), dtype=np.uint32)
            ctypes_all_histdata = all_histdata.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32))
            self._lib.GetAllHistograms(self._devidx, ctypes_all_histdata)
            return all_histdata.copy()
