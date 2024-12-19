"""" Wrapper for the external library component."""
import enum
import sys
from ctypes import CDLL

from qmi.instruments.high_finesse.support import wlmData, wlmConst

DLL_PATH_WINDOWS = "wlmData.dll"
DLL_PATH_LINUX = "libwlmData.so"
DLL_PATH_MACOS = "libwlmData.dylib"


@enum.unique
class WlmGetErr(enum.Enum):
    """Return error values of GetFrequency, GetWavelength, GetWLMVersion, GetPowerNum and GetOptionInfo."""
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


@enum.unique
class WlmTempErr(enum.Enum):
    """Return error values of GetTemperature and GetPressure."""
    TEMP_NOT_MEASURED = wlmConst.ErrTempNotMeasured
    TEMP_NOT_AVAILABLE = wlmConst.ErrTempNotAvailable
    TEMP_WLM_MISSING = wlmConst.ErrTempWlmMissing


@enum.unique
class WlmGainErr(enum.Enum):
    """Return error values of GetGain."""
    GAIN_NOT_AVAILABLE = wlmConst.ErrGainNotAvailable
    GAIN_WLM_MISSING = wlmConst.ErrGainWlmMissing
    GAIN_CHANNEL_NOT_AVAILABLE = wlmConst.ErrGainChannelNotAvailable
    GAIN_OUT_OF_RANGE = wlmConst.ErrGainOutOfRange
    GAIN_PARAMETER_OUT_OF_RANGE = wlmConst.ErrGainParameterOutOfRange


@enum.unique
class WlmMmiErr(enum.Enum):
    """Return error values of GetMultimodeInfo."""
    MMI_NOT_AVAILABLE = wlmConst.ErrMMINotAvailable
    MMI_WLM_MISSING = wlmConst.ErrMMIWlmMissing
    MMI_CHANNEL_NOT_AVAILABLE = wlmConst.ErrMMIChannelNotAvailable
    MMI_OUT_OF_RANGE = wlmConst.ErrMMIOutOfRange
    MMI_PARAMETER_OUT_OF_RANGE = wlmConst.ErrMMIParameterOutOfRange


@enum.unique
class WlmDistanceErr(enum.Enum):
    """Return error values of GetDistance."""
    DISTANCE_NOT_AVAILABLE = wlmConst.ErrDistanceNotAvailable
    DISTANCE_WLM_MISSING = wlmConst.ErrDistanceWlmMissing


class _LibWrapper:

    def __init__(self) -> None:
        """ A Library wrapper that hides the (platform-specific) HighFinesse Wavemeter libraries.

        Raises:
            OSError: Trying to run on an unsupported platform, e.g. "cygwin", or file not found.
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
