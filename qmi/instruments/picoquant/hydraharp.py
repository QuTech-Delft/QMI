""" QMI instrument driver for the PicoQuant HydraHarp 400 instrument.

The instrument driver makes use of the manufacturer provided software libraries, "hhlib.so" for Linux OS,
or "hhlib.dll" or "hhlib64.dll" for 32-bit and 64-bit Windows OS, respectively.
Please find the licence terms for these files in the dedicated software package for the HydraHarp instrument at
https://www.picoquant.com/dl_software/HydraHarp400/HydraHarp400_SW_and_DLL_v3_0_0_4.zip
"""
import ctypes
import enum
import logging
from typing import List, Tuple

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

    Unfortunately, their meanings are not fully documented in the HydraHarp documentation.
    """
    SINGLESHOT_CTC = 0
    """Default value."""
    C1_GATED = 1
    """(Undocumented)"""
    C1_START_CTC_STOP = 2
    """(Undocumented)"""
    C1_START_C2_STOP = 3
    """(Undocumented)"""
    WR_M2S = 4
    """(Undocumented)"""
    WR_S2M = 5
    """(Undocumented)"""


@enum.unique
class _FLAG(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~HydraHarpDevice.getFlags` function.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.

    Unfortunately, their meanings are not fully documented in the HydraHarp documentation.
    """
    OVERFLOW = 0x0001
    """Histogram mode only."""
    FIFOFULL = 0x0002
    """TTTR mode only."""
    SYNC_LOST = 0x0004
    """Synchronization lost."""
    REF_LOST = 0x0008
    """Reference lost."""
    SYSERROR = 0x0010
    """Hardware error, must contact support."""
    ACTIVE = 0x0020
    """Measurement is running."""
    CNTS_DROPPED = 0x0040
    """Counts were dropped."""


@enum.unique
class _WARNING(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~HydraHarpDevice.getWarnings` function.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.

    Unfortunately, their meanings are not fully documented in the HydraHarp documentation.
    """
    SYNC_RATE_ZERO = 0x0001
    """Sync rate zero."""
    SYNC_RATE_VERY_LOW = 0x0002
    """Sync rate very low."""
    SYNC_RATE_TOO_HIGH = 0x0004
    """Sync rate too high."""
    INPT_RATE_ZERO = 0x0010
    """Input rate zero."""
    INPT_RATE_TOO_HIGH = 0x0040
    """Input rate high."""
    INPT_RATE_RATIO = 0x0100
    """Input rate ratio."""
    DIVIDER_GREATER_ONE = 0x0200
    """Divider greater than one."""
    TIME_SPAN_TOO_SMALL = 0x0400
    """Time span too small."""
    OFFSET_UNNECESSARY = 0x0800
    """Offset unneccesary."""
    DIVIDER_TOO_SMALL = 0x1000
    """Divider too small."""
    COUNTS_DROPPED = 0x2000
    """Counts dropped."""


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

    @rpc_method
    def get_module_info(self) -> List[Tuple[int, int]]:
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
    def get_flags(self) -> List[str]:
        self._check_is_open()
        with self._device_lock:
            bitset = ctypes.c_int()
            self._lib.GetFlags(self._devidx, bitset)
            flags = _FLAG(bitset.value)
            return [flag.name for flag in _FLAG if flag in flags and flag.name is not None]

    @rpc_method
    def get_warnings(self) -> List[str]:
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
