""" QMI instrument driver for the PicoQuant PicoHarp 300 instrument.

The instrument driver makes use of the manufacturer provided software libraries, "phlib.so" for Linux OS,
or "phlib.dll" or "phlib64.dll" for 32-bit and 64-bit Windows OS, respectively.
Please find the licence terms for these files in the dedicated software package for the PicoHarp instrument at
https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules/picoharp-300-stand-alone-tcspc-module-with-usb-interface
--> "Software" tab --> download link in "Current software and developer's library version".
"""
import ctypes
import enum
import logging

from qmi.core.exceptions import QMI_InvalidOperationException
from qmi.core.rpc import rpc_method
from qmi.instruments.picoquant.support._library_wrapper import _LibWrapper
from qmi.instruments.picoquant._picoquant import _str_to_enum, _PicoquantHarp
from qmi.instruments.picoquant.support._events import _MODE

_logger = logging.getLogger(__name__)


@enum.unique
class _FLAG(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~PicoHarpDevice.getFlags` function.

    These are defined as preprocessor symbols in the ``phdefin.h`` C header file.
    """
    OVERFLOW = 0x0040
    """Histogram mode only. It indicates that a histogram measurement has reached the maximum count 
    as specified via PH_SetStopOverflow."""
    FIFOFULL = 0x0003
    """TTTR mode only. It indicates that the data FiFo has run full. The measurement will then have
    to be aborted as data integrity is no longer maintained."""
    SYSERROR = 0x0100
    """Indicates an error of the hardware or internal software. The user should in this case
    call the library routine PH_GetHardwareDebugInfo and provide the result to PicoQuant support."""


@enum.unique
class _WARNING(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~PicoHarpDevice.getWarnings` function.

    These are defined as preprocessor symbols in the ``phdefin.h`` C header file. For full descriptions
    see the chapter '11. Warnings' from the PicoHarp PHLib Manual.
    """
    INP0_RATE_ZERO = 0x0001
    """No counts are detected at input channel 0."""
    INP0_RATE_TOO_LOW = 0x0002
    """The count rate at input channel 0 is below 1 kHz and the sync divider is >1."""
    INP0_RATE_TOO_HIGH = 0x0004
    """You have selected T2 mode and the count rate at input channel 0 is higher than 5 MHz.
    The measurement will inevitably lead to a FiFo overrun."""
    INP1_RATE_ZERO = 0x0010
    """No counts are detected at input channel 1."""
    INP1_RATE_TOO_HIGH = 0x0040
    """If you have selected T2 mode then this warning means the count rate at input channel 1 is higher than 5 MHz. 
    The measurement will inevitably lead to a FiFo overrun.
    In histogramming and T3 mode this warning is issued when the input rate is >10 MHz. This will probably lead to 
    deadtime artefacts."""
    INP_RATE_RATIO = 0x0100
    """This warning is issued in histogramming and T3 mode when the rate at input 1 is over 5% of the rate
    at input 0."""
    DIVIDER_GREATER_ONE = 0x0200
    """You have selected T2 mode and the sync divider is set larger than 1. This is probably not intended."""
    TIME_SPAN_TOO_SMALL = 0x0400
    """This warning is issued in histogramming and T3 mode when the sync period (1/Rate[ch0]) is longer than 
    the start to stop time span that can be covered by the histogram or by the T3 mode records."""
    OFFSET_UNNECESSARY = 0x0800
    """This warning is issued in histogramming and T3 mode when an offset >0 is set even though the sync period
    (1/Rate0) can be covered by the measurement time span without using an offset. The offset may lead to events
    getting discarded."""


class PicoQuant_PicoHarp300(_PicoquantHarp):
    """Instrument driver for the PicoQuant PicoHarp 300."""

    _MODEL = "PH"
    # From phdefin.h
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
            self._lazy_lib = _LibWrapper('PH')
        return self._lazy_lib

    @rpc_method
    def initialize(self, mode_str: str) -> None:
        """Initialize the device.

        This routine must be called before any of the other methods, except OpenDevice, CloseDevice,
        GetErrorString and GetLibraryVersion can be used.

        Arguments:
            mode_str (str): Opening mode. Can be any of 'HIST', 'T2', 'T3'.
                            The latest driver version V3.0+ supports T2 and T3 modes.

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

        with self._device_lock:
            self._lib.Initialize(self._devidx, mode.value)
            self._mode = mode

        # Reset the event filter configuration.
        self.set_event_filter(reset_filter=True)
        self.set_block_events(False)
        _logger.info("[%s] Initialized device with mode %s", self._name, mode.value)

    @rpc_method
    def set_sync_offset(self, sync_offset: int) -> None:
        self._check_is_open()
        with self._device_lock:
            self._lib.SetSyncOffset(self._devidx, sync_offset)

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
    def set_input_cfd(self, channel: int, level: int, zc: int) -> None:
        """Set Constant Fraction Discriminator (CFD) levels for input channel.

        Notes:
            This method can only be called on the TimeHarp 260 P model.

        Args:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            level: CFD discriminator level in millivolts (mV) range 0 to -1200 mV.
            zc: CFD zero cross level in millivolts (mV). range 0 to -40 mV.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetInputCFD(self._devidx, channel, level, zc)
