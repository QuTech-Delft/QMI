"""
Instrument driver for the PicoTech PicoScope 4000A series oscilloscopes.

This driver depends on the PicoSDK libraries from PicoTech and on
the PicoSDK Python wrappers from
https://github.com/picotech/picosdk-python-wrappers .
"""

import ctypes
import logging
from typing import TYPE_CHECKING

from qmi.core.context import QMI_Context
from qmi.core.rpc import rpc_method

from qmi.instruments.picotech._picoscope import PicoTech_PicoScope, _check_error

# Lazy import of the "picosdk" module. See the function _import_modules() in _picoscope.py.
if TYPE_CHECKING:
    from picosdk.ps4000a import ps4000a as _ps
else:
    _ps = None


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class PicoTech_PicoScope4824(PicoTech_PicoScope):
    """Instrument driver for the PicoTech PicoScope 4824 USB oscilloscope.

    Attributes:
        NUM_CHANNELS:     Number of oscilloscope channels.
        NUM_INPUT_RANGES: Number of supported input ranges. Range '0' is not supported.
    """
    NUM_CHANNELS = 8
    NUM_INPUT_RANGES = 12

    def __init__(self, context: QMI_Context, name: str, serial_number: str) -> None:
        """Initialize the instrument driver.

        Arguments:
            name: Name for this instrument instance.
            serial_number: Serial number of the Picoscope.
        """
        super().__init__(context, name, serial_number)
        self._library = "4000a"

    @rpc_method
    def run_block(self, num_pretrig_samples: int, num_posttrig_samples: int, time_base: int) -> None:
        """Start acquisition in block mode.

        If the trigger is enabled (see `set_trigger()`), the oscilloscope will
        until the trigger condition occurs, then acquire a single block of data.
        If the trigger is disabled, the oscilloscope will immediately acquire
        a single block of data.

        This function returns immediately while the acquisition is in progress.
        Call `is_block_ready()` or `wait_block_ready()` to check whether the acquisition has finished.
        Optionally call `stop()` to end the acquisition before it completes.

        Parameters:
            num_pretrig_samples:    Number of pre-trigger samples.
            num_posttrig_samples:   Number of post-trigger samples.
            time_base:              Timebase selector (range 0 ... 2**32-1).
                                    The effective timebase is `(timebase+1) * 12.5 ns`.
                                    Depending on the enabled channels, a minimum value of 1 may be required
                                    (minimum timebase 25 ns).
        """
        self._check_is_open()

        num_samples = num_pretrig_samples + num_posttrig_samples
        par_interval_ns = ctypes.c_float()
        err = _ps.ps4000aGetTimebase2(
            self._handle,
            time_base,
            num_samples,
            ctypes.byref(par_interval_ns),
            None,  # maxSamples
            0,  # segmentIndex
        )
        _check_error(err)

        err = _ps.ps4000aRunBlock(
            self._handle,
            num_pretrig_samples,
            num_posttrig_samples,
            time_base,
            None,  # timeIndisposedMs
            0,     # segmentIndex
            None,  # lpReady
            None,  # pParameter
        )
        _check_error(err)

        self._num_samples = num_samples
        self._timebase_interval_ns = par_interval_ns.value

    @rpc_method
    def get_sampling_interval(self, time_base: int) -> float:
        """Returns the scope's time resolution in nanoseconds depending on the time_base selector.

        Parameters:
            time_base:   Timebase selector (range 0 ... 2^32-1).
                         The effective time resolution is 12.5 ns * (time_base + 1).

        Returns:
            resolution:  Scope's time resolution in nanoseconds.
                         0 is returned for invalid time_base.
        """
        if 0 <= time_base < 2 ** 32:
            return 12.5 * (time_base + 1)

        else:
            return 0
