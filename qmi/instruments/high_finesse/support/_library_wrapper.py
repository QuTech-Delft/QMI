"""" Wrapper for the external library component."""
from __future__ import annotations

import enum
import sys
from ctypes import CDLL

from qmi.instruments.high_finesse.support import wlmData, wlmConst

DLL_PATH_WINDOWS = "wlmData.dll"
DLL_PATH_LINUX = "libwlmData.so"
DLL_PATH_MACOS = "libwlmData.dylib"


@enum.unique
class WS8_ERR(enum.Enum):
    """Return error values of GetFrequency, GetWavelength, GetWLMVersion and GetOptionInfo."""
    NO_VALUE = wlmConst.ErrNoValue
    NO_SIGNAL = wlmConst.ErrNoSignal
    BAD_SIGNAL = wlmConst.ErrBadSignal
    LOW_SIGNAL = wlmConst.ErrLowSignal
    BIG_SIGNAL = wlmConst.ErrBigSignal
    WLM_MISSING = wlmConst.ErrWlmMissing
    NOT_AVAILABLE = wlmConst.ErrNotAvailable
    NOTHING_CHANGED = wlmConst.InfNothingChanged
    NO_PULSE = wlmConst.ErrNoPulse
    CHANNEL_NOT_AVAILABLE = wlmConst.ErrChannelNotAvailable
    DIV_ZERO = wlmConst.ErrDiv0
    OUT_OF_RANGE = wlmConst.ErrOutOfRange
    UNIT_NOT_AVAILABLE = wlmConst.ErrUnitNotAvailable


class _LibWrapper:

    def __init__(self) -> None:
        """ A Library wrapper that hides the (platform-specific) HighFinesse Wavemeter libraries.

        Raises:
            OSError: Trying to run on an unsupported platform, e.g. "cygwin" or file not found.
        """
        if sys.platform.startswith("win"):
            wlmData.LoadDLL(DLL_PATH_WINDOWS)
        elif sys.platform.startswith("linux"):
            wlmData.LoadDLL(DLL_PATH_LINUX)
        elif sys.platform.startswith("darwin"):
            wlmData.LoadDLL(DLL_PATH_MACOS)
        else:
            raise OSError("Unsupported platform")

        self._dll = wlmData.dll

    @property
    def dll(self) -> CDLL:
        """ A reference to the actual dll."""
        assert self._dll is not None
        return self._dll
