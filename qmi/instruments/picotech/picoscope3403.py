"""
Instrument driver for the PicoTech PicoScope 3000A series oscilloscopes.

This driver depends on the PicoSDK libraries from PicoTech and on
the PicoSDK Python wrappers from
https://github.com/picotech/picosdk-python-wrappers.
"""

import ctypes
import logging
from typing import TYPE_CHECKING
import warnings

import numpy as np
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_UsageException
from qmi.core.rpc import rpc_method

from qmi.instruments.picotech._picoscope import ChannelCoupling, PicoTech_PicoScope, TriggerEdge, _check_error

# Lazy import of the "picosdk" module. See the function _import_modules() _picoscope.py.
if TYPE_CHECKING:
    from picosdk.ps3000a import ps3000a as _ps
else:
    _ps = None

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class PicoTech_PicoScope3403(PicoTech_PicoScope):
    """Instrument driver for the PicoTech PicoScope 3403 USB oscilloscope.

    Attributes:
        NUM_CHANNELS:     Number of oscilloscope channels.
        NUM_INPUT_RANGES: Number of supported input ranges. Range '0' is not supported.
    """
    NUM_CHANNELS = 4
    NUM_INPUT_RANGES = 11

    def __init__(self, context: QMI_Context, name: str, serial_number: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:          Name for this instrument instance.
            serial_number: Serial number of the Picoscope.
        """
        super().__init__(context, name, serial_number)
        self._library = "3000a"

    def _get_time_base(self, sampling_interval: int) -> int:
        """Returns the time base selector for a given sampling interval.
        For invalid sampling intervals, an exception is raised.

        Parameters:
            sampling_interval: Sampling interval in nanoseconds. Must be 1, 2, 4 or a multiple of 8 ns.

        Returns:
            time_base:         The respective time-base value for the sampling interval.
        """
        if sampling_interval in (1, 2, 4):
            return int(np.log2(sampling_interval))

        if sampling_interval > 4 and sampling_interval % 8 == 0:
            return int(round((sampling_interval / 8) + 2, 0))

        raise QMI_UsageException("Sampling interval must be 1, 2, 4 or a multiple of 8 ns")

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
            time_base:              Time base selector (range 0 ... 2**32-1). The effective time base is
                                    (timebase - 2) * 8 ns for timebase > 2, else 2^timebase.
                                    For one enabled channel, values from 0 are allowed (time-base >= 1 ns).
                                    For two enabled channels, values from 1 are allowed (time-base >= 2 ns).
                                    From three enabled channels, values from 2 are allowed (time-base >= 4 ns).
        """
        self._check_is_open()

        num_samples = num_pretrig_samples + num_posttrig_samples
        par_interval_ns = ctypes.c_float()
        err = _ps.ps3000aGetTimebase2(
            self._handle,
            time_base,
            num_samples,
            ctypes.byref(par_interval_ns),
            0,  # oversamples
            None,  # maxSamples
            0,  # segmentIndex
        )
        _check_error(err)

        err = _ps.ps3000aRunBlock(
            self._handle,
            num_pretrig_samples,
            num_posttrig_samples,
            time_base,
            0,  # oversamples
            None,  # timeIndisposedMs
            0,  # segmentIndex
            None,  # lpReady
            None,
            )  # pParameter
        _check_error(err)

        self._num_samples = num_samples
        self._timebase_interval_ns = par_interval_ns.value

    @rpc_method
    def acquire_by_trigger_and_get_data(
        self,
        channels: list[int],
        max_val: list[float],
        couplings: list[ChannelCoupling],
        trigger_channel: int | None,
        trigger_level: float,
        sampling_interval: int,
        time_span: int,
    ) -> object:
        """Acquires data from a specific channel, which is triggered, and returns the data.

        It is assumed that the trigger level is set to (almost) the highest point of
        the measured waveform. This is used to select the appropriate input range.
        The scope waits 1 second to get triggered.
        Default measurement values are: DC coupling and triggering on the rising edge.
        The number of samples is determined from the sampling interval and time span and set
        relative to the trigger point.
        If no trigger channel number is given, trigger is disabled and sampling is done from
        the number of samples before the current moment of `run_block` call.
        The data is then sent back as real voltages.

        Parameters:
            channels:          List of used channels [0...NUM_CHANNELS-1] for readout.
            max_val:           Maximum expected values for ALL channels [0, 1, ... NUM_CHANNELS-1] to set an
                               appropriate input range.
            couplings:         Coupling of channels for readout for ALL channels [0, 1, ... NUM_CHANNELS-1].
                               ChannelCoupling.DC or ChannelCoupling.AC.
            trigger_channel:   Channel to set the trigger on. If it is 'None', triggers will be disabled on
                               all channels.
            trigger_level:     Threshold in Volts for the trigger.
            sampling_interval: Sampling interval in nanoseconds. Must be 1, 2, 4 or a multiple of 8 ns.
            time_span:         Time span of data acquiring in nanoseconds.

        Returns:
            times:    A 1D Numpy array containing the sampling times in ns.
            voltages: A 1D Numpy array containing the measured voltages in V.
        """
        warnings.warn(
            f"{self.acquire_by_trigger_and_get_data.__name__} will be deprecated in the future as it is not a base "
            "functionality of the driver. Please implement it as a custom method in your code.")

        if min(channels) < 0 or max(channels) >= self.NUM_CHANNELS:
            raise ValueError("Invalid channel index")

        if trigger_channel is not None:
            if (trigger_channel < 0) or (trigger_channel >= self.NUM_CHANNELS) or trigger_channel not in channels:
                raise ValueError("Invalid trigger channel index")

        time_base = self._get_time_base(sampling_interval)
        if time_base < 2 and len(channels) > 2 ** time_base:
            raise QMI_UsageException(f"Time-base of {time_base} is not supported for {len(channels)} channels")

        # Give maximum voltage range per expected maximum value per enabled channel.
        max_volts = []
        for chan in range(self.NUM_CHANNELS):
            if chan not in channels:
                # Disable all channels that are not used and skip to next one.
                self.set_channel(chan, False, ChannelCoupling.DC, 0, 0)
                continue

            if np.abs(max_val[chan]) <= 0.02:
                ranges = 1
                max_volts.append(0.02)
            elif np.abs(max_val[chan]) <= 0.05:
                ranges = 2
                max_volts.append(0.05)
            elif np.abs(max_val[chan]) <= 0.1:
                ranges = 3
                max_volts.append(0.1)
            elif np.abs(max_val[chan]) <= 0.2:
                ranges = 4
                max_volts.append(0.2)
            elif np.abs(max_val[chan]) <= 0.5:
                ranges = 5
                max_volts.append(0.5)
            elif np.abs(max_val[chan]) <= 1:
                ranges = 6
                max_volts.append(1)
            elif np.abs(max_val[chan]) <= 2:
                ranges = 7
                max_volts.append(2)
            elif np.abs(max_val[chan]) <= 5:
                ranges = 8
                max_volts.append(5)
            elif np.abs(max_val[chan]) <= 10:
                ranges = 9
                max_volts.append(10)
            else:
                ranges = 10
                max_volts.append(20)

            self.set_channel(chan, True, couplings[chan], ranges, 0)

        # Calculate the total number of samples in the time span.
        number_samples = time_span // sampling_interval
        _logger.info("Timespan = %i Num samples = %i", time_span, number_samples)

        if trigger_channel is not None:
            self.stop()
            trig_int = int(self.MAX_SAMPLE_VALUE / max_volts[channels.index(trigger_channel)] * trigger_level)
            self.set_trigger(True, trigger_channel, trig_int, TriggerEdge.RISING)
            self.run_block(number_samples // 2, number_samples - number_samples // 2, time_base)

        else:
            self.disable_trigger()
            self.stop()
            self.run_block(number_samples, 0, time_base)

        self.wait_block_ready(timeout=1.5)
        data = self.get_block_data(channels)
        times = np.arange(0, number_samples, 1) * sampling_interval
        voltages = []
        for i in channels:
            voltages.append(data[0][channels.index(i)] * (max_volts[channels.index(i)] / self.MAX_SAMPLE_VALUE))

        return times, voltages

    @rpc_method
    def get_sampling_interval(self, time_base: int) -> float:
        """Returns the scope's time resolution in nanoseconds depending on the time_base selector.

        Parameters:
            time_base:   Timebase selector (range 0 ... 2^32-1).
                         The effective time resolution is 2^time_base ns for timebase <= 2.
                         The effective time resolution is (timebase-2)/(125000000) for timebase > 2.

        Returns:
            resolution:  Scope's time resolution in nanoseconds. 0 is returned for invalid time_base.
        """
        if 0 <= time_base <= 2:
            return 2.0 ** time_base

        elif 2 < time_base < 2 ** 32:
            # We can round here to 0 decimals as this model has always a resolution of multiple of 8.
            return round(((time_base - 2) / 125e6) * 1e9, 0)

        else:
            return 0
