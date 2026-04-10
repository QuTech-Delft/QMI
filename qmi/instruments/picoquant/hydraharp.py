""" QMI instrument driver for the PicoQuant HydraHarp 400 instrument.

The instrument driver makes use of the manufacturer provided software libraries, "hhlib.so" for Linux OS,
or "hhlib.dll" or "hhlib64.dll" for 32-bit and 64-bit Windows OS, respectively.
Please find the licence terms for these files in the dedicated software package for the HydraHarp instrument at
https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules/hydraharp-400-multichannel-picosecond-event-timer-tcspc-module
--> "Software" tab --> download link in "Current software and developer's library version".
"""
import ctypes
import enum
import logging

from qmi.core.exceptions import QMI_InvalidOperationException
from qmi.core.rpc import rpc_method
from qmi.instruments.picoquant.support._library_wrapper import _LibWrapper
from qmi.instruments.picoquant._picoquant import _str_to_enum, _PicoquantHarp, _EDGE
from qmi.instruments.picoquant.support._events import _MODE

_logger = logging.getLogger(__name__)


@enum.unique
class _REFSRC(enum.Enum):
    """Symbolic constants for the :func:`~HydraHarpDevice.initialize` method's `refsource` argument.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.
    """
    INTERNAL = 0
    """Use internal clock."""

    EXTERNAL = 1
    """Use external clock."""


@enum.unique
class _MEASCTL(enum.Enum):
    """Symbolic constants for the :func:`~HydraHarpDevice.setMeasurementControl` `control` argument.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.
    """
    SINGLESHOT_CTC = 0
    """Default value. Acquisition starts by software command and runs until CTC expires. The duration
    is set by the tacq parameter passed to HH_StartMeas."""
    C1_GATED = 1
    """Histograms are collected for the period where C1 is active. This can be the logical high or
    low period dependent on the value supplied to the parameter startedge."""
    C1_START_CTC_STOP = 2
    """Data collection is started by a transition on C1 and stopped by expiration of the internal CTC. 
    Which transition actually triggers the start is given by the value supplied to the parameter startedge. 
    The duration is set by the tacq parameter passed to HH_StartMeas."""
    C1_START_C2_STOP = 3
    """Data collection is started by a transition on C1 and stopped by by a transition on C2. Which transitions
    actually trigger start and stop is given by the values supplied to the parameters startedge and stopedge."""
    CONT_C1_GATED = 4
    """Histograms are collected for each period where C1 is active. This can be the logical high or low periods
    dependent on the value supplied to the parameter startedge."""
    CONT_C1_START_CTC_STOP = 5
    """Histogram collection is started by a transition on C1 and stopped by expiration of the internal CTC.
    Which transition actually triggers the start is given by the value supplied to the parameter startedge.
    Histogram duration is set by the tacq parameter passed to HH_StartMeas. The current histogram
    ends if a new trigger occurs before the CTC has expired."""
    CONT_CTC_RESTART = 6
    """Histogram collection is started and stopped exclusively by the internal CTC. Consecutive histograms will
    line up without gaps. Histogram duration is set by the tacq parameter passed to HH_StartMeas."""


@enum.unique
class _FLAG(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~HydraHarpDevice.getFlags` function.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.
    """
    OVERFLOW = 0x0001
    """Histogram mode only. It indicates that a histogram measurement has reached the maximum count 
    as specified via HH_SetStopOverflow."""
    FIFOFULL = 0x0002
    """TTTR mode only.  It indicates that the data FiFo has run full. The measurement will then have
    to be aborted as data integrity is no longer maintained."""
    SYNC_LOST = 0x0004
    """This flag may occur in T3 mode and in histo mode. It indicates that the sync signal has been lost
    which in this case is critical as the function of T3 mode and histo mode relies on an uninterrupted
    sync signal."""
    REF_LOST = 0x0008
    """This flag will occur when the HydraHarp is programmed to use an external reference clock and this
    reference clock is lost."""
    SYSERROR = 0x0010
    """Indicates an error of the hardware or internal software. The user should in this case
    call the library routine HH_GetHardwareDebugInfo and provide the result to PicoQuant support."""
    ACTIVE = 0x0020
    """Measurement is running."""
    CNTS_DROPPED = 0x0040
    """Indicates that counts were dropped at the first level FiFo directly following the TDC of an input channel.
    This occurs typically only at extremely high count rates. Dependent on the application scenario this may or
    may not be considered critical."""


@enum.unique
class _WARNING(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~HydraHarpDevice.getWarnings` function.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file. For full descriptions
    see the chapter '8.1. Warnings' from the HydraHarp HHLib Manual.
    """
    SYNC_RATE_ZERO = 0x0001
    """No pulses are detected at the sync input. In histogramming and T3 mode this is crucial and the
    measurement will not work without this signal."""
    SYNC_RATE_TOO_LOW = 0x0002
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


class PicoQuant_HydraHarp400(_PicoquantHarp):
    """Instrument driver for the PicoQuant HydraHarp 400."""

    _MODEL = "HH"
    _MAXDEVNUM = 8
    _TTREADMAX = 131072

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
            self._lazy_lib = _LibWrapper('HH')
        return self._lazy_lib

    @rpc_method
    def initialize(self, mode_str: str, refsource_str: str) -> None:
        """Initialize the device.

        This routine must be called before any of the other methods, except OpenDevice, CloseDevice,
        GetErrorString and GetLibraryVersion can be used.

        Arguments:
            mode_str (str): Opening mode. Can be any of 'HIST', 'T2', 'T3', 'CONT'.
                            The latest driver version V3.0+ supports T2, T3 and CONT modes.
            refsource_str (str): Reference source for time. Can be any of 'INTERNAL', 'EXTERNAL'.

        Raises:
            ValueError: if either argument is an unknown string value.
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()

        if self._measurement_running:
            raise QMI_InvalidOperationException("Measurement still active")
        mode = _str_to_enum(_MODE, mode_str)
        if mode not in (_MODE.HIST, _MODE.T2, _MODE.T3, _MODE.CONT):
            raise ValueError("Unsupported measurement mode")

        if self._lib_version.startswith("2") and mode in (_MODE.T3, _MODE.CONT):
            raise ValueError(f"Unsupported measurement in mode library version {self._lib_version}")

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
    def set_measurement_control(self, meascontrol_str: str, startedge_str: str, stopedge_str: str) -> None:
        self._check_is_open()
        meascontrol = _str_to_enum(_MEASCTL, meascontrol_str)
        startedge = _str_to_enum(_EDGE, startedge_str)
        stopedge = _str_to_enum(_EDGE, stopedge_str)
        with self._device_lock:
            self._lib.SetMeasControl(self._devidx, meascontrol.value, startedge.value, stopedge.value)

    @rpc_method
    def get_flags(self) -> list[str]:
        self._check_is_open()
        with self._device_lock:
            bitset = ctypes.c_int()
            self._lib.GetFlags(self._devidx, bitset)
            flags = _FLAG(bitset.value)
            return [flag.name for flag in _FLAG if flag in flags and flag.name is not None]

    @rpc_method
    def get_warnings(self) -> list[str]:
        self._check_is_open()
        with self._device_lock:
            bitset = ctypes.c_int()
            self._lib.GetWarnings(self._devidx, bitset)
            warnings = _WARNING(bitset.value)
            return [warning.name for warning in _WARNING if warning in warnings and warning.name is not None]

    @rpc_method
    def calibrate(self) -> None:
        self._check_is_open()
        with self._device_lock:
            self._lib.Calibrate(self._devidx)

    @rpc_method
    def set_sync_cfd(self, level: int, zc: int) -> None:
        self._check_is_open()
        with self._device_lock:
            self._lib.SetSyncCFD(self._devidx, level, zc)

    @rpc_method
    def set_input_cfd(self, channel: int, level: int, zc: int) -> None:
        self._check_is_open()
        with self._device_lock:
            self._lib.SetInputCFD(self._devidx, channel, level, zc)
