""" This module contains the base class for QMI instrument driver for the Picoquant 'Harp instruments.
Further, it has some utility functions on how to extract real-time histograms and count rates from T2 event data
and how to filter these T2 event records.
"""

import ctypes
import enum
import logging
import time
from enum import IntEnum, Enum
from threading import Condition, Lock
from typing import Callable, Optional, Dict, List, Tuple, NamedTuple, TypeVar, Type

import numpy as np
from numpy.typing import ArrayLike

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_RuntimeException, QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.pubsub import QMI_Signal
from qmi.core.rpc import rpc_method
from qmi.core.thread import QMI_Thread
from qmi.instruments.picoquant._library_wrapper import _LibWrapper

_logger = logging.getLogger(__name__)

NUM_CHANNELS = 8

# Event type of SYNC events.
SYNC_TYPE = 64


# Numpy record type used to represent event records.
# Event types 0 to 7 represent a normal event.
# Event type 64 represents a SYNC event.
# Event types 65 to 79 represent marker events.
EventDataType = np.dtype([
    ("type", np.uint8),
    ("timestamp", np.uint64)
])


class RealTimeHistogram(NamedTuple):
    """Real-time histogram from T2 event data.

    Attributes:
        start_timestamp: timestamp of first SYNC event of the histogram.
        bin_resolution: Histogram bin resolution as multiple of the instrument base resolution.
        num_sync:       Number of SYNC periods included in this histogram.
        channels:       List of channel numbers included in the histogram.
        histogram_data: 2D array of shape (num_channels, num_bins) containing counts for each bin.
    """
    start_timestamp: int
    bin_resolution: int
    num_sync: int
    channels: List[int]
    histogram_data: np.ndarray


class RealTimeCountRate(NamedTuple):
    """Real-time count rate from T2 event data.

    Attributes:
        start_timestamp: timestamp of the SYNC event that started the counters.
        num_sync:       Number of SYNC periods included in the counter values.
        counts:         1D array of counter value for each input channel.
    """
    start_timestamp: int
    num_sync: int
    counts: np.ndarray


class EventFilterMode(IntEnum):
    NO_EVENTS = 0
    ALL_EVENTS = 1
    APERTURE = 2


class _FetchEventsThread(QMI_Thread):
    """This thread continuously fetches event data from the via USB."""

    _LOOP_SLEEP_DURATION = 0.01

    def __init__(self,
                 read_fifo_func: Callable[[], np.ndarray],
                 publish_histogram_func: Callable,
                 publish_countrate_func: Callable,
                 max_pending_events: int = 10**8
                 ) -> None:
        """Initialize background event fetching thread.

        Args:
            read_fifo_func: Callable that can be used to obtain the fifo ndarray.
            publish_histogram_func: Callable used to publish histogram data.
            publish_countrate_func: callable used to countrate histogram data.
            max_pending_events: The purpose of this limit is to avoid consuming an excessive amount of memory.
                By default allow at most 10**8 events in the queue (~ 900 MByte). It is not expected that this limit
                will be exceeded in a properly working setup.

        """
        super().__init__()
        self._read_fifo_func = read_fifo_func
        self._publish_histogram_func = publish_histogram_func
        self._publish_countrate_func = publish_countrate_func
        self._condition = Condition(Lock())
        self._t2_decoder: Optional[_T2EventDecoder] = None
        self._event_filter: Optional[_EventFilter] = None
        self._histogram_processor: Optional[_RealTimeHistogramProcessor] = None
        self._event_filter_channels: Dict[int, EventFilterMode] = {}
        self._event_filter_aperture = (0, 0)
        self._histogram_channels: List[int] = []
        self._histogram_resolution = 1
        self._histogram_num_bins = 0
        self._histogram_num_sync = 0
        self._countrate_aperture = (0, 0)
        self._countrate_num_sync = 0
        self._active = False
        self._count_read_fifo = 0
        self._block_events = False
        self._data: List[np.ndarray] = []
        self._data_timestamp = 0.0
        self._num_pending_events = 0
        self._pending_events_overflow = False
        self._max_pending_events = max_pending_events

    def _process_fifo_data(self, fifo_data: np.ndarray, fifo_data_timestamp: float) -> None:
        """Process new received raw event records from the multiharp, hydraharp.

        This function will be called in the background thread while holding the "self._condition" lock.
        """
        assert self._t2_decoder is not None
        assert self._histogram_processor is not None
        assert self._event_filter is not None

        # Decode event records.
        event_records = self._t2_decoder.process_data(fifo_data)

        # Process real-time histograms and counters.
        self._histogram_processor.process_events(event_records)

        if not self._block_events:

            # Filter events.
            event_records = self._event_filter.process_events(event_records)

            # Store filtered events.
            num_events = len(event_records)
            if num_events > 0:
                if self._num_pending_events + num_events > self._max_pending_events:
                    # Too many pending events.
                    self._pending_events_overflow = True
                else:
                    self._data.append(event_records)
                    self._num_pending_events += num_events
                    self._data_timestamp = fifo_data_timestamp

    def run(self) -> None:
        """Main function running in the background thread."""
        with self._condition:
            while not self._shutdown_requested:
                if self._active:
                    # Read data from HydraHarp, if any.
                    fifo_data = self._read_fifo_func()
                    fifo_data_timestamp = time.time()
                    if len(fifo_data) > 0:
                        # Process received event records.
                        self._process_fifo_data(fifo_data, fifo_data_timestamp)
                    self._count_read_fifo += 1
                    # Sleep and wake up again in 10ms.
                    self._condition.wait(self._LOOP_SLEEP_DURATION)
                else:
                    # Wait until we are activated.
                    self._condition.wait()

    def activate(self) -> None:
        """Activate background event fetching.

        This method is called immediately after starting a measurement in TTTR mode.
        It activates continuous event fetching in the background thread.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            if self._active:
                raise QMI_InvalidOperationException("Already active")
            self._t2_decoder = _T2EventDecoder()
            self._event_filter = _EventFilter()
            self._event_filter.set_event_filter_config(self._event_filter_channels,
                                                       self._event_filter_aperture)
            self._histogram_processor = _RealTimeHistogramProcessor(self._publish_histogram_func,
                                                                    self._publish_countrate_func)
            self._histogram_processor.set_histogram_config(self._histogram_channels,
                                                           self._histogram_resolution,
                                                           self._histogram_num_bins,
                                                           self._histogram_num_sync)
            self._histogram_processor.set_countrate_config(self._countrate_aperture,
                                                           self._countrate_num_sync)
            self._count_read_fifo = 0
            self._active = True
            self._data = []
            self._num_pending_events = 0
            self._pending_events_overflow = False
            self._condition.notify_all()

    def deactivate(self) -> None:
        """Deactivate background event fetching.

        This method is called after stopping a measurement in TTTR mode.
        Note that the instrument typically continues to produce events for a
        short time after stopping a measurement.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            self._active = False
            self._condition.notify_all()

    def set_block_events(self, blocked: bool) -> None:
        """Enable or disable blocking of events.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            self._block_events = blocked

    def set_event_filter_config(self,
                                channel_filter: Dict[int, EventFilterMode],
                                sync_aperture: Tuple[int, int]
                                ) -> None:
        """Update event filter parameters.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            self._event_filter_channels = channel_filter
            self._event_filter_aperture = sync_aperture
            if self._event_filter is not None:
                self._event_filter.set_event_filter_config(channel_filter, sync_aperture)

    def set_histogram_config(self, channels: List[int], bin_resolution: int, num_bins: int, num_sync: int) -> None:
        """Configure real-time histograms.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            self._histogram_channels = channels
            self._histogram_resolution = bin_resolution
            self._histogram_num_bins = num_bins
            self._histogram_num_sync = num_sync
            if self._histogram_processor is not None:
                self._histogram_processor.set_histogram_config(channels, bin_resolution, num_bins, num_sync)

    def set_countrate_config(self, sync_aperture: Tuple[int, int], num_sync: int) -> None:
        """Configure real-time count rate reporting.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            self._countrate_aperture = sync_aperture
            self._countrate_num_sync = num_sync
            if self._histogram_processor:
                self._histogram_processor.set_countrate_config(sync_aperture, num_sync)

    def _request_shutdown(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def get_events(self, max_events: int) -> Tuple[float, np.ndarray]:
        """Return events fetched by the background thread.

        Parameters:
            max_events: Maximum number of events to return.

        Returns:
            Tuple (timestamp, event_data).

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_HydraHarp400` instance.
        """

        # Accept at most `max_events` pending event records.
        # This must be done under the condition variable lock.
        with self._condition:

            data_timestamp = self._data_timestamp

            if self._pending_events_overflow:
                # Events got dropped because there were too many pending events.
                # Discard all pending events and clear the overflow flag, then raise an exception.
                self._data = []
                self._num_pending_events = 0
                self._pending_events_overflow = False
                raise QMI_RuntimeException("Too many pending events from time tagger, pending events discarded.")

            if self._num_pending_events <= max_events:
                # Accept all pending events.
                data = self._data
                self._data = []
                self._num_pending_events = 0

            else:
                # Split the set of pending events.
                room_left = max_events
                split_pos = 0
                while True:
                    num_events = len(self._data[split_pos])
                    if num_events > room_left:
                        break
                    room_left -= num_events
                    split_pos += 1
                data = self._data[:split_pos]
                self._data = self._data[split_pos:]
                if room_left > 0:
                    data.append(self._data[0][:room_left])
                    self._data[0] = self._data[0][room_left:]
                self._num_pending_events -= max_events

        # Concatenate the event arrays to be returned.
        if len(data) == 0:
            event_data = np.empty(0, dtype=EventDataType)
        else:
            event_data = np.concatenate(data)

        return data_timestamp, event_data


class _RealTimeHistogramProcessor:
    """Extract real-time histograms and count rates from T2 event data."""

    def __init__(self, publish_histogram_func: Callable, publish_countrate_func: Callable) -> None:
        """Initialize histogram processing."""
        self._publish_histogram_func = publish_histogram_func
        self._publish_countrate_func = publish_countrate_func
        self._previous_sync_timestamp = -1

        self._histogram_channels: List[int] = []
        self._histogram_resolution = 1
        self._histogram_num_bins = 0
        self._histogram_num_sync = 0
        self._histogram_data = np.zeros((0, 0), dtype=np.uint32)
        self._histogram_sync_counter = -1
        self._histogram_start_timestamp = 0

        self._countrate_aperture = (0, 0)
        self._countrate_num_sync = 0
        self._countrate_data = np.zeros(NUM_CHANNELS, dtype=np.uint64)
        self._countrate_sync_counter = -1
        self._countrate_start_timestamp = 0

    def set_histogram_config(self, channels: List[int], bin_resolution: int, num_bins: int, num_sync: int) -> None:
        """Configure real-time histograms."""

        assert bin_resolution > 0
        self._histogram_channels = channels
        self._histogram_resolution = bin_resolution
        self._histogram_num_bins = num_bins
        self._histogram_num_sync = num_sync

        # Clear data.
        self._histogram_data = np.zeros((len(channels), num_bins), dtype=np.uint32)
        self._histogram_sync_counter = -1

    def set_countrate_config(self, sync_aperture: Tuple[int, int], num_sync: int) -> None:
        """Configure real-time count rate reporting."""
        self._countrate_aperture = sync_aperture
        self._countrate_num_sync = num_sync

        # Clear data.
        self._countrate_data = np.zeros(NUM_CHANNELS, dtype=np.uint64)
        self._countrate_sync_counter = -1

    def process_events(self, event_records: np.ndarray) -> None:
        """Process T2 event records and update histogram and count rates."""

        # Do nothing if histogram and count rate features are both disabled.
        if (self._histogram_num_sync == 0) and (self._countrate_num_sync == 0):
            return

        # Prepend the previous SYNC event, if there is any.
        # This simplifies calculation of time deltas since last SYNC.
        previous_sync_inserted = False
        if self._previous_sync_timestamp >= 0:
            event_records = np.insert(event_records, 0, (SYNC_TYPE, self._previous_sync_timestamp))
            previous_sync_inserted = True

        # Find the indexes of SYNC events.
        (sync_events_idx,) = np.where(event_records["type"] == SYNC_TYPE)

        # Do nothing before we get the first SYNC event.
        if len(sync_events_idx) == 0:
            return

        # Update the timestamp of the last SYNC event.
        self._previous_sync_timestamp = event_records[sync_events_idx[-1]]["timestamp"]

        # For each event, determine time delta since the last SYNC event.
        # The result is only valid for event past the first SYNC.
        first_sync_idx = sync_events_idx[0]
        sync_deltas = _get_sync_deltas(event_records, sync_events_idx)

        # Discard all events before the first SYNC.
        # Also discard the previous SYNC, if we prepended it to the current dataset.
        if previous_sync_inserted:
            first_sync_idx += 1
            sync_events_idx = sync_events_idx[1:]
        event_records = event_records[first_sync_idx:]
        sync_deltas = sync_deltas[first_sync_idx:]
        sync_events_idx -= first_sync_idx

        # Update real-time histograms.
        if self._histogram_num_sync > 0:
            self._update_histogram(event_records, sync_events_idx, sync_deltas)

        # Update real-time count rates.
        if self._countrate_num_sync > 0:
            self._update_countrate(event_records, sync_events_idx, sync_deltas)

    def _update_histogram(self,
                          event_records: np.ndarray,
                          sync_events_idx: np.ndarray,
                          sync_deltas: np.ndarray
                          ) -> None:
        """Update real-time histograms."""

        channels = self._histogram_channels
        num_bins = self._histogram_num_bins
        num_sync = self._histogram_num_sync

        # Do nothing if histogram processing is disabled.
        if (num_sync < 1) or (num_bins < 1) or (len(channels) < 1):
            return

        # Convert delta time to histogram bin index.
        # Clip to maximum bin index.
        event_bins = sync_deltas // self._histogram_resolution
        event_bins = np.minimum(event_bins, num_bins - 1)

        # Skip events before the first SYNC.
        next_idx = 0
        if self._histogram_sync_counter < 0:
            if len(sync_events_idx) == 0:
                return
            next_idx = sync_events_idx[0]
            self._histogram_start_timestamp = event_records[next_idx]["timestamp"]

        # Visit each SYNC record which ends a histogram integration interval.
        event_types = event_records["type"]
        for sync_idx in sync_events_idx[num_sync-self._histogram_sync_counter-1::num_sync]:

            # Update histogram up to the end of the current integration interval.
            # Process each channel separately.
            for (chan_pos, chan) in enumerate(channels):
                chan_bool = (event_types[next_idx:sync_idx] == chan)
                chan_bins = event_bins[next_idx:sync_idx][chan_bool]
                # Note: input to bincount MUST be dtype int64
                #       output from bincount will be dtype int64
                self._histogram_data[chan_pos] += np.bincount(chan_bins.astype(np.int64),
                                                              minlength=num_bins
                                                              ).astype(np.uint32)

            # Publish completed histogram.
            self._publish_histogram_func(RealTimeHistogram(
                start_timestamp=self._histogram_start_timestamp,
                bin_resolution=self._histogram_resolution,
                num_sync=num_sync,
                channels=channels,
                histogram_data=self._histogram_data))

            # Reset histogram for new integration interval.
            self._histogram_data = np.zeros((len(channels), num_bins), dtype=np.uint32)
            self._histogram_start_timestamp = event_records[sync_idx]["timestamp"]
            next_idx = sync_idx

        # Update the SYNC counter.
        self._histogram_sync_counter = (self._histogram_sync_counter + len(sync_events_idx)) % num_sync

        # Update histogram for remaining events.
        # Process each channel separately.
        for (chan_pos, chan) in enumerate(channels):
            chan_bool = (event_types[next_idx:] == chan)
            chan_bins = event_bins[next_idx:][chan_bool]
            self._histogram_data[chan_pos] += np.bincount(chan_bins.astype(np.int64),
                                                          minlength=num_bins
                                                          ).astype(np.uint32)

    def _update_countrate(self,
                          event_records: np.ndarray,
                          sync_events_idx: np.ndarray,
                          sync_deltas: np.ndarray
                          ) -> None:
        """Update real-time count rates."""

        # Do nothing if count rate processing is disabled.
        num_sync = self._countrate_num_sync
        if num_sync < 1:
            return

        # Select events that pass the aperture filter.
        (delta_min, delta_max) = self._countrate_aperture
        events_selected_bool = ((sync_deltas >= delta_min) & (sync_deltas <= delta_max))

        # Narrow down to events on the normal input channels.
        event_types = event_records["type"]
        events_selected_bool &= (event_types < NUM_CHANNELS)

        # Skip events before the first SYNC.
        next_idx = 0
        if self._countrate_sync_counter < 0:
            if len(sync_events_idx) == 0:
                return
            next_idx = sync_events_idx[0]
            self._countrate_start_timestamp = event_records[next_idx]["timestamp"]

        # Visit each SYNC record which ends an integration interval.
        for sync_idx in sync_events_idx[num_sync-self._countrate_sync_counter-1::num_sync]:

            # Update counters up to the end of the current integration interval.
            event_chan = event_types[next_idx:sync_idx][events_selected_bool[next_idx:sync_idx]]
            # Note: input to bincount MUST be dtype int64
            #       output from bincount will be dtype int64
            self._countrate_data += np.bincount(event_chan.astype(np.int64),
                                                minlength=NUM_CHANNELS
                                                ).astype(np.uint64)

            # Publish integrated counter values.
            self._publish_countrate_func(RealTimeCountRate(
                start_timestamp=self._countrate_start_timestamp,
                num_sync=num_sync,
                counts=self._countrate_data))

            # Reset counters for new integration interval.
            self._countrate_data = np.zeros(NUM_CHANNELS, dtype=np.uint64)
            self._countrate_start_timestamp = event_records[sync_idx]["timestamp"]
            next_idx = sync_idx

        # Update the SYNC counter.
        self._countrate_sync_counter = (self._countrate_sync_counter + len(sync_events_idx)) % num_sync

        # Update counters for the remaining events.
        event_chan = event_types[next_idx:][events_selected_bool[next_idx:]]
        self._countrate_data += np.bincount(event_chan.astype(np.int64),
                                            minlength=NUM_CHANNELS
                                            ).astype(np.uint64)


class _EventFilter:
    """Filter T2 event records."""

    def __init__(self) -> None:
        """Initialize the event filter."""
        self._previous_sync_timestamp = -1
        self._previous_sync_reported = False
        self._sync_aperture = (0, 0)
        self._channel_filter_map = np.zeros(128, dtype=np.uint8)
        self._aperture_filter_enabled = False

    def set_event_filter_config(self,
                                channel_filter: Dict[int, EventFilterMode],
                                sync_aperture: Tuple[int, int]
                                ) -> None:
        """Set event filter parameters.

        Parameters:
            channel_filter: Mapping from event type (input channel) to the event filter mode for that event type.
            sync_aperture:  Tuple (delta_min, delta_max) in multiples of the instrument base resolution,
                            defining a time window following each SYNC event.
                            For event types that use `EventFilterMode.APERTURE`, only events that fall inside
                            this time window will pass the filter.
        """
        self._sync_aperture = sync_aperture
        self._channel_filter_map[:] = 0
        self._aperture_filter_enabled = False

        # Construct a map from event type code to channel filter mode.
        for (event_type, filter_mode) in channel_filter.items():
            self._channel_filter_map[event_type] = int(filter_mode)
            if filter_mode == EventFilterMode.APERTURE:
                self._aperture_filter_enabled = True

    def process_events(self, event_records: np.ndarray) -> np.ndarray:
        """Filter event records.

        This function filters a sequence of event records and returns only
        the events that are considered to be interesting according to the
        configured filter rules.

        The `_EventFilter` instance keeps track of the most recent SYNC event.
        The sequence of calls to this method must therefore correspond to
        a single TTTR event stream, processed in order, without missing events.

        Parameters:
            event_records: Numpy array of EventDataType records.

        Returns:
            Numpy array of event records that pass the filter.
        """

        # Do not waste time processing an empty array.
        if len(event_records) == 0:
            return event_records

        # Prepend the previous SYNC event, if there is any.
        # This simplifies processing of the aperture filter.
        previous_sync_inserted = False
        if self._aperture_filter_enabled and (self._previous_sync_timestamp >= 0):
            event_records = np.insert(event_records, 0, (SYNC_TYPE, self._previous_sync_timestamp))
            previous_sync_inserted = True

        # Map event type of each record to the corresponding filter mode.
        record_filter_modes = self._channel_filter_map[event_records["type"]]

        # Select events on channels that are unconditionally enabled.
        events_selected_bool = (record_filter_modes == EventFilterMode.ALL_EVENTS)

        # Find the indexes of SYNC events.
        (sync_events_idx,) = np.where(event_records["type"] == SYNC_TYPE)

        # Handle aperture filter, if necessary.
        if self._aperture_filter_enabled and (len(sync_events_idx) > 0):

            # For each event, determine time delta since the last SYNC event.
            # The result is only valid for event past the first SYNC.
            first_sync_idx = sync_events_idx[0]
            sync_deltas = _get_sync_deltas(event_records, sync_events_idx)

            # Mark all events on channels that are configured to use aperture filtering.
            events_aperture_bool = (record_filter_modes == EventFilterMode.APERTURE)

            # Reject events that do not pass the SYNC aperture.
            (delta_min, delta_max) = self._sync_aperture
            events_aperture_bool[:first_sync_idx] = False
            events_aperture_bool &= (sync_deltas >= delta_min)
            events_aperture_bool &= (sync_deltas <= delta_max)

            # Select events that pass the aperture filter.
            events_selected_bool |= events_aperture_bool

            # If aperture filtering is enabled on the SYNC channel, temporarily select all SYNC events.
            if self._channel_filter_map[SYNC_TYPE] == EventFilterMode.APERTURE:
                events_selected_bool[sync_events_idx] = True

        # If we prepended a previous, already reported SYNC event,
        # drop that event now to avoid reporting it a second time.
        if previous_sync_inserted and self._previous_sync_reported:
            events_selected_bool[0] = False

        # Update the timestamp of the last SYNC event.
        if len(sync_events_idx) > 0:
            self._previous_sync_timestamp = event_records[sync_events_idx[-1]]["timestamp"]
            self._previous_sync_reported = True

        # Discard rejected events.
        event_records = event_records[events_selected_bool]

        # If aperture filtering is enabled on the SYNC channel,
        # reject SYNC events unless they are followed by a non-SYNC event.
        if self._channel_filter_map[SYNC_TYPE] == EventFilterMode.APERTURE:

            # Select non-SYNC events.
            events_selected_bool = (event_records["type"] != SYNC_TYPE)

            # Also select all events that are followed by a non-SYNC event.
            events_selected_bool[np.where(events_selected_bool[1:])] = True

            # Remember whether the last SYNC event is dropped, so it can
            # be reported later if it becomes relevant again.
            if (len(event_records) > 0) and (event_records[-1]["type"] == SYNC_TYPE):
                self._previous_sync_reported = False

            # Discard rejected events.
            event_records = event_records[events_selected_bool]

        # Return the events that pass the filter.
        return event_records


class _T2EventDecoder:
    """Decode the TTTR data stream in T2 mode."""

    def __init__(self) -> None:
        self._overflow_counter = 0

    def process_data(self, fifo_data: np.ndarray) -> np.ndarray:
        """Decode event records from the T2 data stream.

        This function decodes raw 32-bit TTTR event records and returns
        an array of structured event records.

        Overflow records in the TTTR stream are used to assign an unwrapped
        64-bit timestamp value to each event. The overflow records are removed
        from the event array returned by this function.

        The `_T2EventDecoder` instance keeps track of the running overflow counter.
        The sequence of calls to this method must therefore correspond to
        a single TTTR data stream, processed in order, without gaps or data loss.

        Parameters:
            fifo_data: Numpy array of 32-bit raw event records in TTTR T2 format.

        Returns:
            Numpy array of `EventDataType` records.
        """

        #
        # T2 TTTR event record format:
        #   bit  31    = special_flag
        #   bits 30:25 = channel
        #   bits 24:0  = timetag
        #
        # The "timetag" value is a multiple of the instrument base resolution.
        # Overflow of the 25-bit counter is marked via special overflow records.
        #
        # If special_flag == 0, the record represents a normal event on the specified channel.
        # If special_flag == 1 And channel == 63, the record represents overflow of the 25-bit time value.
        # If special_flag == 1 And channel == 0, the record represents a SYNC event.
        # If special_flag == 1 And 1 <= channel <= 15, the record represents a marker event.
        #

        # Type code for overflow events.
        # Note that overflow channel is 63, but here also special flag is added, so 0x7f.
        overflow_type = 0x7f

        # Overflow period is the full range of the 25 bits time tag.
        overflow_period = (1 << 25)

        # Extract the 7-bit "type" field of each record.
        # The "type" field consists of the 1-bit "special" flag together with the 6-bit "channel" field.
        record_types = (fifo_data >> 25).astype(np.uint8)

        # Extract the 25-bit "timetag" field.
        # For overflow records, this is the overflow increment;
        # for event records, this is the time-tag (offset since last overflow).
        record_tags = (fifo_data & 0x01ffffff)

        # Make a bool array marking the overflow records.
        overflow_records_bool = (record_types == overflow_type)

        # Make a bool array marking the normal (non-overflow) records.
        event_records_bool = ~overflow_records_bool

        # Prepare a running count of the number of overflows
        overflow_counts = np.cumsum(overflow_records_bool * record_tags, dtype=np.uint64)
        overflow_counts += self._overflow_counter

        # Update the overflow counter to take this batch of events into account.
        if len(overflow_counts) > 0:
            self._overflow_counter = int(overflow_counts[-1])

        # Select the event types of the non-overflow records.
        event_types = record_types[event_records_bool]

        # Calculate the event timestamps of the non-overflow records.
        event_timestamps = overflow_counts[event_records_bool] * overflow_period + record_tags[event_records_bool]

        # Copy the non-overflow records to a result array.
        events = np.empty(len(event_types), dtype=EventDataType)
        events["type"] = event_types
        events["timestamp"] = event_timestamps

        return events


def _get_sync_deltas(event_records: np.ndarray, sync_events_idx: np.ndarray) -> np.ndarray:
    """For each event record, determine the time delta since the last SYNC event.

    Parameters:
        event_records: Array of structured event records with "type" and "timestamp" fields.
        sync_events_idx: Array of indexes into `event_records` corresponding to SYNC events.

    Returns:
        Array of time deltas since SYNC event for each event record.
        This array has the same length as `event_records`.
        The returned values for records occurring before the first SYNC record will be invalid.
    """

    # Extract timestamps of SYNC events.
    event_timestamps = event_records["timestamp"]
    sync_timestamps = event_timestamps[sync_events_idx]

    # If there is no SYNC record, return dummy invalid data.
    if len(sync_events_idx) == 0:
        return np.zeros_like(event_timestamps)

    # Find index of the first SYNC event.
    first_sync_idx = sync_events_idx[0]

    # Prepare an array holding, for each event record, the timestamp of the most recent SYNC event.
    most_recent_sync_timestamp = np.zeros_like(event_timestamps)
    most_recent_sync_timestamp[first_sync_idx] = sync_timestamps[0]
    most_recent_sync_timestamp[sync_events_idx[1:]] = np.diff(sync_timestamps)
    most_recent_sync_timestamp = np.cumsum(most_recent_sync_timestamp)

    # Prepare an array holding, for each event record, the elapsed time since the most recent SYNC event.
    sync_deltas = event_timestamps - most_recent_sync_timestamp

    return sync_deltas


_ENUM_T = TypeVar('_ENUM_T', bound=Enum)


def _str_to_enum(enum_type: Type[_ENUM_T], str_value: str) -> _ENUM_T:
    """Convert a string value to an Enum-type value, by comparing it to the enum value names."""
    try:
        return enum_type[str_value]
    except KeyError:
        allowed_values = tuple(ev.name for ev in enum_type)
        raise ValueError("Bad value {!r}, expected one of {!r}".format(str_value, allowed_values))


class TttrHistogram:
    """Class to make histograms from Time Tagged Time Resolved (TTTR) T2-mode data."""

    def __init__(self, channel: int, numbins: int):

        self.channel = channel
        self.bins = np.arange(numbins)
        self.bin_edges = np.arange(numbins + 1)

        self.counts = np.zeros(numbins, dtype=np.uint64)
        self.deltas = None
        self.previous = None  # No timestamp carried from previous events.

    def reset(self) -> None:
        """Reset counts, deltas and previous timestamp."""
        self.counts.fill(0)
        self.deltas = None
        self.previous = None  # No timestamp carried from previous events.

    def process(self, events: np.ndarray) -> None:
        """Process events, and filter by aperture (if applicable)."""

        sync_type = 64  # The type of SYNC events.

        # If we have a previously recorded SYNC timestamp, we prepend it to the EVENTS array.
        if self.previous is not None:
            events = np.insert(events, 0, (sync_type, self.previous))

        # Find the first SYNC event.
        first_sync_index, = np.where(events["type"] == sync_type)
        if len(first_sync_index) == 0:
            # No sync event found. Discard these events.
            return

        # Discard all events before the first SYNC event.
        first_sync_index = first_sync_index[0]
        if first_sync_index != 0:
            events = events[first_sync_index:]  # type: ignore

        # At this point, the first event is guaranteed to be a SYNC,
        #   which simplifies matters significantly.

        assert events["type"][0] == sync_type

        idx = np.where(events["type"] == sync_type)  # This includes the first event.
        timestamps = events["timestamp"][idx]  # The timestamps of the SYNC events.

        increments = np.insert(np.diff(timestamps), 0, events["timestamp"][0])

        most_recent_synctime = np.zeros_like(events["timestamp"])
        most_recent_synctime[idx] = increments
        most_recent_synctime = np.cumsum(most_recent_synctime)

        deltas = events["timestamp"] - most_recent_synctime

        deltas = deltas[events["type"] == self.channel]
        deltas = deltas[deltas < len(self.counts)]

        self.deltas = deltas

        hist, _ = np.histogram(deltas, self.bin_edges)

        hist = hist.astype(np.uint64)

        self.counts += hist

        self.previous = most_recent_synctime[-1]

    def get_plot_data(self, bin_resolution: float) -> Tuple[ArrayLike, ArrayLike, int]:
        """Convenience function to return bin values and counts for plotting to the caller.

        Parameters:
            bin_resolution: bin resolution for the histogram. Unit is probably seconds

        Returns:
            Tuple of (bin values data, self.counts, number of bins in self.bins)
        """
        return self.bins * bin_resolution / 1e-9, self.counts, len(self.bins)


@enum.unique
class _MODE(enum.Enum):
    """Symbolic constants for the :func:`~HydraHarpDevice.initialize` method's `mode` argument.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.
    """
    HIST = 0
    """Histogram mode."""
    T2 = 2
    """T2 mode."""
    T3 = 3
    """T3 mode."""
    CONT = 8
    """Continuous Mode"""


@enum.unique
class _EDGE(enum.Enum):
    """Symbolic constants for routines that take an `edge` argument:

    * Function :func:`~HydraHarpDevice.setMeasurementControl`, `startedge` and `stopedge` arguments;
    * Function :func:`~HydraHarpDevice.setSyncEdgeTrigger`, `edge` argument;
    * Function :func:`~HydraHarpDevice.setInputEdgeTrigger`, `edge` argument.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.
    """
    RISING = 1
    """Rising edge."""
    FALLING = 0
    """Falling edge."""


@enum.unique
class _FEATURE(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~HydraHarpDevice.getFeatures` function.

    These are defined as preprocessor symbols in the ``hhdefin.h`` C header file.

    Unfortunately, their meanings are not fully documented in the documentation.
    """
    DLL = 0x0001
    """DLL License available."""
    TTTR = 0x0002
    """TTTR mode available."""
    MARKERS = 0x0004
    """Markers available."""
    LOWRES = 0x0008
    """Long range mode available"""
    TRIGOUT = 0x0010
    """Trigger output available."""
    PROG_TD = 0x0020
    """Programmable deadtime available."""


class _PicoquantHarp(QMI_Instrument):

    # Some functions have model-dependent variable/string differences. Use this to distinguish
    _MODEL: str = ""

    # The QMI RPC mechanism can not handle messages larger than 10 MB.
    # To avoid RPC errors, we limit the number of events returned per call
    # to 10**6 such that the RPC message will be at most 9 MB plus some overhead.
    MAX_EVENTS_PER_CALL = 10 ** 6

    # Signal published to report real-time histograms based on T2 event data.
    sig_histogram = QMI_Signal([RealTimeHistogram])

    # Signal published to report real-time count rates based on T2 event data.
    sig_countrate = QMI_Signal([RealTimeCountRate])

    def __init__(self, context: QMI_Context, name: str, serial_number: str, max_pending_events: int = 10 ** 8) -> None:
        """Instantiate the instrument driver. This is the base class for all *Harp instruments.

        Arguments
            context: the QMI_Context that manages us
            name: the name of the instrument instance
            serial_number: the serial number of the instrument to be opened.
            max_pending_events: Only Relevant for T2 capturing. Defaults to 10e8 events.
        """
        super().__init__(context, name)
        self._serial_number = serial_number
        self._max_pending_events = max_pending_events
        self._lazy_lib: Optional[_LibWrapper] = None
        self._devidx = -1
        self._lib_version: str = ""
        self._fetch_events_thread: Optional[_FetchEventsThread] = None
        self._mode: Optional[_MODE] = None
        self._measurement_running = False
        self._measurement_start_time = 0.0
        self._event_filter_channels: Dict[int, EventFilterMode] = {}
        self._event_filter_aperture = (0, 0)
        self._actuallen = 65536  # Actual histogram length value

        # The instrument may be accessed concurrently by two threads:
        #  - public API functions are called through the RPC thread that manages this instrument instance
        #  - the function _read_fifo() is called by the background event fetching thread.
        # For this reason, interaction with the instrument must be protected with an explicit mutex.
        self._device_lock = Lock()

    @property
    def _max_dev_num(self):
        raise NotImplementedError()

    @property
    def _ttreadmax(self):
        raise NotImplementedError()

    @property
    def _model(self):
        raise NotImplementedError()

    @property
    def _lib(self) -> _LibWrapper:
        raise NotImplementedError

    def _read_fifo(self) -> np.ndarray:
        """Read event FIFO data.

        This is an internal method. It gets called by the background thread when measuring in T2 mode.

        CPU time during wait for completion will be yielded to other processes/threads. The call will return after a
        timeout period of approximately 1 ms if no more data could be fetched. The actual time to return may vary
        towards 2..3 ms due to USB overhead and operating system latencies.

        Returns:
            Raw FIFO data as a 1-dimensional array of 32-bit unsigned integers.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            fifo_data = np.empty(self._ttreadmax, dtype=np.uint32)
            buffer = fifo_data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32))
            n_actual = ctypes.c_int()
            if self._model == "MH":
                self._lib.ReadFiFo(self._devidx, buffer, n_actual)

            else:
                self._lib.ReadFiFo(self._devidx, buffer, self._ttreadmax, n_actual)

            n_actual_int = n_actual.value
            return fifo_data[:n_actual_int].copy()

    @rpc_method
    def open(self) -> None:
        """Open the device.

        This method also starts a background thread which will be responsible
        for fetching event data from the instrument.
        """

        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        vers = ctypes.create_string_buffer(8)
        self._lib.GetLibraryVersion(vers)
        self._lib_version = vers.value.decode()
        _logger.debug("Library version = %s", self._lib_version)

        with self._device_lock:
            for devidx in range(self._max_dev_num):
                try:
                    serial = ctypes.create_string_buffer(8)
                    self._lib.OpenDevice(devidx, serial)
                    decoded_serial = serial.value.decode()
                    if not decoded_serial:
                        try:
                            if self._model in ["HH"]:
                                self._lib.Initialize(devidx, 0, 0)  # HydraHarp

                            else:
                                raise NotImplementedError(f"Model {self._model} is not implemented!")

                        except QMI_InstrumentException:
                            continue

                        serial = ctypes.create_string_buffer(8)
                        self._lib.GetSerialNumber(devidx, serial)
                        decoded_serial = serial.value.decode()

                    if decoded_serial == self._serial_number:
                        self._devidx = devidx
                        break

                    self._lib.CloseDevice(devidx)

                except QMI_InstrumentException:
                    continue

            if self._devidx == -1:
                raise QMI_InstrumentException(f"No device with serial number {self._serial_number!r} found.")

        self._fetch_events_thread = _FetchEventsThread(self._read_fifo,
                                                       self.sig_histogram.publish,  # type: ignore
                                                       self.sig_countrate.publish,  # type: ignore
                                                       self._max_pending_events)
        self._fetch_events_thread.start()

        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the device.

        Stops the background event fetching thread and closes the underlying device.
        """

        self._check_is_open()

        assert (self._fetch_events_thread is not None)
        self._fetch_events_thread.shutdown()
        self._fetch_events_thread.join()
        self._fetch_events_thread = None

        _logger.info("[%s] Closing connection to instrument", self._name)
        with self._device_lock:
            self._devidx = -1
        self._mode = None
        super().close()

    @rpc_method
    def get_error_string(self, error_code: int) -> str:
        """ Get the error string for an error code number.

        Inputs:
            error_code: The error code number to be translated

        Returns:
            Error code's description string.
        """
        self._check_is_open()
        with self._device_lock:
            error_string = ctypes.create_string_buffer(40)
            self._lib.GetErrorString(error_string, error_code)
            return error_string.value.decode()

    @rpc_method
    def get_hardware_info(self) -> Tuple[str, str, str]:
        """Get model, part nr, and version of the device.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            A 3-tuple of consisting of (model, partno, version) strings.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            model = ctypes.create_string_buffer(24)
            partno = ctypes.create_string_buffer(8)
            version = ctypes.create_string_buffer(8)
            self._lib.GetHardwareInfo(self._devidx, model, partno, version)
            decoded_model = model.value.decode()
            decoded_partno = partno.value.decode()
            decoded_version = version.value.decode()
            return decoded_model, decoded_partno, decoded_version

    @rpc_method
    def get_serial_number(self) -> str:
        """Get the device serial number.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            The serial number for example '1035683'.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            serial = ctypes.create_string_buffer(8)
            self._lib.GetSerialNumber(self._devidx, serial)
            return serial.value.decode()

    @rpc_method
    def get_features(self) -> List[str]:
        """Get device features.

        This function is usually not needed by the user. It is mainly for integration in PicoQuant system software
        such as SymPhoTime in order to figure out in a standardized way the capabilities the device has.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            A list of strings, each describing a feature of the device.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            features_bitset = ctypes.c_int()
            self._lib.GetFeatures(self._devidx, features_bitset)
            features = _FEATURE(features_bitset.value)
            return [feature.name for feature in _FEATURE if feature in features and feature.name is not None]

    @rpc_method
    def get_base_resolution(self) -> Tuple[float, int]:
        """Get the resolution and binsteps of the device.

        Returns:
            A tuple `(resolution, binsteps)` where resolution (float) is the base resolution in
            picoseconds binsteps (int) is the number of allowed binning steps.
        """
        self._check_is_open()
        with self._device_lock:
            resolution = ctypes.c_double()
            binsteps = ctypes.c_int()
            self._lib.GetBaseResolution(self._devidx, resolution, binsteps)
            return resolution.value, binsteps.value

    @rpc_method
    def get_debug_info(self) -> str:
        """Get debugging info of the device.

        Call this immediately after receiving an error from any library call or after detecting a `SYSERROR` from
        `get_flags`. In case of `SYSERROR`, please provide this information to support.

        Returns:
            A debug info string (65,655 characters, max).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            debuginfo = ctypes.create_string_buffer(65536)
            if self._model == "MH":
                self._lib.GetDebugInfo(self._devidx, debuginfo)

            else:
                self._lib.GetHardwareDebugInfo(self._devidx, debuginfo)

            return debuginfo.value.decode()

    @rpc_method
    def get_number_of_input_channels(self) -> int:
        """Get number of input channels of the device.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            Number of input channels.
            When a channel index is passed to another method of this driver, the valid range
            of channel index is from 0 to `number_of_channels` - 1.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            nchannels = ctypes.c_int()
            self._lib.GetNumOfInputChannels(self._devidx, nchannels)
            return nchannels.value

    @rpc_method
    def calibrate(self) -> None:
        """Calibrate the <xxx>Harp instrument. <xxx> = Hydra, Pico

        This method should be called before starting a measurement.

        Calibrates the time measurement circuits. This is necessary whenever temperature changes > 5 K occurred.
        Calibrate after warming up of the instrument before starting serious measurements. Warming up takes about 20
        to 30 minutes dependent on the lab temperature. It is completed when the cooling fan starts to run for the first
        time. Calibration takes only a few seconds. Calibration is only important for serious measurements.
        You can use the instrument during the warming-up period for set–up and preliminary measurements. For very long
        measurements, allow some more time for thermal stabilization, calibrate immediately before the measurement
        commences and try to maintain a stable room temperature during the measurement. The permissible ambient
        temperature is 15°C to 35 °C. Do not obstruct the cooling fan at the back and the air inlets at the bottom of
        the housing.
        """
        raise NotImplementedError()

    @rpc_method
    def set_marker_edges(self, me0_str: str, me1_str: str, me2_str: str, me3_str: str) -> None:
        """Set marker edges.

        Change the active edge on which the external TTL signals connected to the marker inputs are triggering.
        Only meaningful in TTTR mode.

        Arguments:
            me0_str (str): edge of marker signal 0.
            me1_str (str): edge of marker signal 1.
            me2_str (str): edge of marker signal 2.
            me3_str (str): edge of marker signal 3.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        me0 = _str_to_enum(_EDGE, me0_str)
        me1 = _str_to_enum(_EDGE, me1_str)
        me2 = _str_to_enum(_EDGE, me2_str)
        me3 = _str_to_enum(_EDGE, me3_str)
        with self._device_lock:
            self._lib.SetMarkerEdges(self._devidx, me0.value, me1.value, me2.value, me3.value)

    @rpc_method
    def set_marker_enable(self, en0: bool, en1: bool, en2: bool, en3: bool) -> None:
        """Set marker enable.

        Used to enable or disable the external TTL marker inputs.
        Only meaningful in TTTR mode.

        Arguments:
            en0: edge of marker signal 0.
            en1: edge of marker signal 1.
            en2: edge of marker signal 2.
            en3: edge of marker signal 3.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetMarkerEnable(self._devidx, int(en0), int(en1), int(en2), int(en3))

    @rpc_method
    def set_marker_holdoff_time(self, holdofftime: int) -> None:
        """Set marker hold-off time.

        Arguments:
            holdofftime: hold-off time in [ns]. Ranges from 0 ns 25500 ns.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetMarkerHoldoffTime(self._devidx, holdofftime)

    @rpc_method
    def start_measurement(self, tacq: int) -> None:
        """Start a measurement.

        Arguments:
            tacq: acquisition time, in [ms], ranging from 1 to 360000000; corresponding to 100 hours)

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        if self._measurement_running:
            raise QMI_InvalidOperationException("Measurement still active")
        assert self._fetch_events_thread is not None
        with self._device_lock:
            self._lib.StartMeas(self._devidx, tacq)
            self._measurement_start_time = time.time()
        self._measurement_running = True
        if self._mode == _MODE.T2:
            # Start collecting data in the background thread.
            self._fetch_events_thread.activate()

    @rpc_method
    def stop_measurement(self) -> None:
        """Stop a running measurement.

        This call can be used to force a stop before the acquisition time expires.

        Important:
            For cleanup purposes, this must be called after a measurement, even if the measurement has expired on its
            own!

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        with self._device_lock:
            self._lib.StopMeas(self._devidx)
        if self._mode == _MODE.T2:
            # Stop collecting data in the background thread.
            self._fetch_events_thread.deactivate()
        self._measurement_running = False

    @rpc_method
    def get_measurement_active(self) -> bool:
        """Check if measurement is active.

        This method will return False if a measurement has expired on its own, even if
        the method `stop_measurement()` has not yet been called.

        Returns:
            | True - acquisition time still running.
            | False - acquisition time has ended.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            ctcstatus = ctypes.c_int()
            self._lib.CTCStatus(self._devidx, ctcstatus)
            ctcstatus_int = ctcstatus.value
        return ctcstatus_int == 0

    @rpc_method
    def get_measurement_start_time(self) -> float:
        """Return the approximate POSIX timestamp of the start of the current measurement.

        The returned timestamp is based on the computer system clock.
        Its accuracy depends on the latency of USB communication with the instrument,
        process scheduling delay and the accuracy of the system clock.

        Returns:
            POSIX timestamp as a floating point number
        """
        self._check_is_open()
        return self._measurement_start_time

    @rpc_method
    def get_events(self) -> np.ndarray:
        """Return events recorded by the instrument in T2 mode.

        While a measurement is active, a background thread continuously reads
        event records from the instrument and stores the events in a buffer.
        This method takes all pending events, removes them from the buffer and returns them.

        Events are returned as an array of event records.
        Each event record contains two fields:
        | `type` (uint8): The channel index where the event was recorded, or 64 for a SYNC event.
        | `timestamp` (uint64): Event timestamp as a multiple of the instrument base resolution.

        This method may only be used in T2 mode.

        Returns:
            Numpy array containing event records.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        (_timestamp, events) = self._fetch_events_thread.get_events(self.MAX_EVENTS_PER_CALL)
        return events

    @rpc_method
    def get_timestamped_events(self) -> Tuple[float, np.ndarray]:
        """Return events recorded by the instrument in T2 mode.

        While a measurement is active, a background thread continuously reads
        event records from the instrument and stores the events in a buffer.
        This method takes all pending events, removes them from the buffer and returns them.

        Events are returned as an array of event records.
        Each event record contains two fields:
        | `type` (uint8): The channel index where the event was recorded, or 64 for a SYNC event.
        | `timestamp` (uint64): Event timestamp as a multiple of the instrument base resolution.

        This method may only be used in T2 mode.

        Returns:
            Tuple `(timestamp, events)`
            where `timestamp` is the approximate wall-clock time where the last event record was received,
            and `events` is a Numpy array containing the event records.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        return self._fetch_events_thread.get_events(self.MAX_EVENTS_PER_CALL)

    @rpc_method
    def get_resolution(self) -> float:
        """Get time resolution.

        Returns:
            The resolution at the current binning (histogram bin width) as a float, in [ps]. Not meaningful in T2 mode.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            resolution = ctypes.c_double()
            self._lib.GetResolution(self._devidx, resolution)
            return resolution.value

    @rpc_method
    def get_sync_rate(self) -> int:
        """Return SYNC rate in events per second (determined every 100 ms).

        Allow at least 100 ms after :func:`initialize` or :func:`setSyncDivider` to get a stable rate meter reading.
        Similarly, wait at least 100 ms to get a new reading (100 ms is the gate time of the counter).

        Returns:
            Sync event rate in events per second.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            syncrate = ctypes.c_int()
            self._lib.GetSyncRate(self._devidx, syncrate)
            return syncrate.value

    @rpc_method
    def get_count_rate(self, channel: int) -> int:
        """Return input channel rate in events per second (determined every 100 ms).

        Allow at least 100 ms after :func:`initialize` to get a stable rate meter reading.
        Similarly, wait at least 100 ms to get a new reading (100 ms is the gate time of the counter).

        Arguments:
            channel: Channel index (range from 0 to `number_of_channels` - 1).

        Returns:
            Channel event rate in events per second.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            cntrate = ctypes.c_int()
            self._lib.GetCountRate(self._devidx, channel, cntrate)
            return cntrate.value

    @rpc_method
    def get_elapsed_measurement_time(self) -> float:
        """Get elapsed measurement time.

        Obtain the elapsed measurement time of a measurement. This relates to the current measurement when
        still running or to the previous measurement when already finished.

        Returns:
            The elapsed measurement time, in [ms].

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            elapsed = ctypes.c_double()
            self._lib.GetElapsedMeasTime(self._devidx, elapsed)
            return float(elapsed.value)

    @rpc_method
    def get_sync_period(self) -> float:
        """Get the sync period.

        This method only gives meaningful results while a measurement is running and after two sync periods have
        elapsed. The return value is undefined in all other cases. Resolution is that of the device's base
        resolution. Accuracy is determined by single shot jitter and clock stability.

        Returns:
            The sync period in [s].

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            period = ctypes.c_double()
            self._lib.GetSyncPeriod(self._devidx, period)
            return period.value

    @rpc_method
    def set_block_events(self, blocked: bool) -> None:
        """Enable or disable blocking event data.

        This feature can be used to "pause" the event data stream.
        The instrument will continue measuring and tagging events, but all
        event records will be discarded by the QMI driver.

        While events are blocked, the instrument will maintain its time base
        such that time intervals between events before and after the pause
        will be correctly represented.

        If real-time histograms are enabled, these will still be updated
        while events are blocked.

        This function only affects measurements in T2 mode.

        Parameter:
            block: True to block all event data, False to resume reporting event data.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        self._fetch_events_thread.set_block_events(blocked)

    @rpc_method
    def set_event_filter(self,
                         reset_filter: bool = False,
                         channel_filter: Optional[Dict[int, EventFilterMode]] = None,
                         sync_aperture: Optional[Tuple[int, int]] = None,
                         ) -> None:
        """Configure the event filter.

        When measuring in T2 mode, incoming events are passed through a filter
        to reject uninteresting events. This event filter is implemented in
        the QMI driver software (not inside the instrument).

        The filter is configured separately for each event type.
        Event types 0 to 7 correspond to the normal input channels.
        Event type 64 represents SYNC events.

        Each event type can be configured either to reject all events (`EventFilterMode.NO_EVENTS`),
        or to accept all events (`EventFilterMode.ALL_EVENTS`) or to accept only events that occur
        within a specific time window after a SYNC event (`EventFilterMode.APERTURE`).

        If `EventFilterMode.APERTURE` is selected for the SYNC channel, the filter accepts
        only the SYNC events that are eithr preceded or followed by a non-SYNC events.
        This mode can be used to discard redundant SYNCs when nothing interesting is happening.

        Parameters:
            reset_filter:   Configure the filter so that all normal events and SYNC events are accepted.
            channel_filter: Mapping from event type to the new event filter mode to be configured.
                            Any event types not specified in the mapping are left in their current setting.
            sync_aperture:  Tuple (delta_min, delta_max) in multiples of the instrument base resolution,
                            defining a time window following each SYNC event.
                            If unspecified or None, the current aperture setting is left unchanged.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None

        if reset_filter:
            # Reset filter so that all event types are accepted (normal input channels, SYNC).
            self._event_filter_channels.clear()
            for event_type in range(NUM_CHANNELS):
                self._event_filter_channels[event_type] = EventFilterMode.ALL_EVENTS
            self._event_filter_channels[SYNC_TYPE] = EventFilterMode.ALL_EVENTS

        if channel_filter is not None:
            self._event_filter_channels.update(channel_filter)

        if sync_aperture is not None:
            self._event_filter_aperture = sync_aperture

        self._fetch_events_thread.set_event_filter_config(self._event_filter_channels, self._event_filter_aperture)

    @rpc_method
    def set_realtime_histogram(self, channels: List[int], bin_resolution: int, num_bins: int, num_sync: int) -> None:
        """Configure real-time histograms.

        When measuring in T2 mode, the driver can optionally report real-time histograms.
        Each received event is assigned to a histogram bin based on the time interval between
        the last SYNC and the event. The histogram is integrated during several SYNC periods.
        After a configurable number of SYNC events, the integrated histogram is published
        via `sig_histogram`.

        Parameters:
            channels:       List of channels to include in the histogram (range 0 to 7).
            bin_resolution: Resolution of each histogram bin as a multiple of the instrument base resolution.
            num_bins:       Number of bins in the histogram (determines the maximum time interval after SYNC).
            num_sync:       Number of SYNC periods to integrate before publishing the histogram.
                            Specify 0 to disable real-time histograms.
        """
        if bin_resolution < 1:
            raise ValueError("Invalid bin_resolution")
        self._check_is_open()
        assert self._fetch_events_thread is not None
        self._fetch_events_thread.set_histogram_config(channels, bin_resolution, num_bins, num_sync)

    @rpc_method
    def set_realtime_countrate(self, sync_aperture: Tuple[int, int], num_sync: int) -> None:
        """Configure real-time count rate reporting.

        When measuring in T2 mode, the driver can optionally report real-time count rates.
        Events that fall in a specific time window after the SYNC pulse are counted.
        This counter is integrated during several SYNC periods.
        After a configurable number of SYNC events, the integrated counter values are
        published via `sig_countrate`.

        Parameters:
            sync_aperture:  Tuple (delta_min, delta_max) as a multiple of the instrument base resolution,
                            defining a time window after each SYNC pulse.
            num_sync:       Number of SYNC periods to integrate before publishing the counter value.
                            Specify 0 to disable the real-time countrate monitoring.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        self._fetch_events_thread.set_countrate_config(sync_aperture, num_sync)

    @rpc_method
    def set_histogram_length(self, lencode: int) -> int:
        """Set the length of the histogram.

        Set the number of bins of the collected histograms. The histogram length is 65536 which is also the
        default after initialization if `set_histogram_length` is not called.

        Arguments:
            lencode: The histogram length code requesting a histogram of (1024 * 2**`lencode`) bins.
                     Valid range is from 0 to 6.

        Returns:
            The current length (time bin count) of histograms calculated as (1024 * 2**`lencode`).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            actuallen = ctypes.c_int()
            self._lib.SetHistoLen(self._devidx, lencode, actuallen)
            self._actuallen = actuallen.value  # Update actual histogram buffer size
            return actuallen.value  # returns the actual length

    @rpc_method
    def set_measurement_control(self, meascontrol_str: str, startedge_str: str, stopedge_str: str) -> None:
        """Set the measurement control mode.

        This must be called before starting a measurement. The default after initialization (if this function is not
        called) is 0, i.e., software controlled acquisition time. The other modes 1..5 allow hardware triggered
        measurements through TTL signals at the control port or through White Rabbit. Note that this needs custom
        software.

        Arguments:
            meascontrol_str: Measurement control code. Any of 'SINGLESHOT_CTC', 'C1_GATED', 'C1_START_CTC_STOP',
                'C1_START_C2_STOP', 'WR_M2S', 'WR_S2M'.
            startedge_str : Start edge selection. Either 'RISING' or 'FALLING'.
            stopedge_str: Stop edge selection. Either 'RISING' or 'FALLING'.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def clear_histogram_memory(self) -> None:
        """Reset the histogram state to all-zeros.

        Clear the histogram memory of all channels. Only meaningful in histogramming mode.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.ClearHistMem(self._devidx)

    @rpc_method
    def set_offset(self, offset: int) -> None:
        """Set time offset.

        This offset only applies in histogramming and T3 mode. It affects only the difference between stop and start
        before it is put into the T3 record or is used to increment the corresponding histogram bin.

        It is intended for situations where the range of the histogram is not long enough to look at "late" data. By
        means of the offset the "window of view" is shifted to a later range.

        This is not the same as changing or compensating cable delays. If the latter is desired,
        use :func:`setSyncChannelOffset` and/or :func:`setInputChannelOffset`.

        Arguments:
            offset: time offset in [ns], ranging from 0 ns to 100000000 ns.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetOffset(self._devidx, offset)

    @rpc_method
    def set_binning(self, binning: int) -> None:
        """Set time binning.

        Arguments:
            binning: the following values can be used:

                     | 0 = 1× base resolution,
                     | 1 = 2× base resolution,
                     | 2 = 4× base resolution,
                     | 3 = 8× base resolution, and so on.

                     Range is 0 to (`BINSTEPSMAX` - 1).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetBinning(self._devidx, binning)

    @rpc_method
    def set_stop_overflow(self, stop_ovfl: bool, stopcount: int) -> None:
        """Set stop overflow count value.

        This setting determines if a measurement run will stop if any channel reaches the maximum set by the
        `stopcount` parameter.

        If `stop_ovfl` is False, the measurement will continue but counts above `STOPCNTMAX` in any bin will be clipped.

        Arguments:
            stop_ovfl: If true, the measurement will stop once the limit is reached. If not, the measurement will
                continue.
            stopcount: 1 to 4294967295.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            stop_ovfl_int = 1 if stop_ovfl else 0
            self._lib.SetStopOverflow(self._devidx, stop_ovfl_int, stopcount)

    @rpc_method
    def set_sync_divider(self, divider: int) -> None:
        """Set the SYNC divider value.

        The sync divider must be used to keep the effective sync rate at values < 78 MHz.
        It should only be used with sync sources of stable period.

        Using a larger divider than strictly necessary does not do great harm but it may result in slightly larger
        timing jitter.

        The readings obtained with :func:`get_count_rate` are internally corrected for the divider setting and
        deliver the external (undivided) rate. The sync divider should not be changed while a measurement is running.

        Arguments:
            divider: value ranging from 1 to 16.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetSyncDiv(self._devidx, divider)

    @rpc_method
    def set_sync_cfd(self, level: int, zc: int) -> None:
        """Set Constant Fraction Discriminator (CFD) levels for SYNC input.

        Notes:
            The values are given as a positive numbers although the electrical signals are actually negative.

        Args:
            level: CFD discriminator level in millivolts (mV) range 0 to 1000 representing 0 to -1000 mV.
            zc: CFD zero cross level in millivolts (mV). range 0 to 40 mV representing 0 to 40 mV.
        """
        raise NotImplementedError()

    @rpc_method
    def set_input_cfd(self, channel: int, level: int, zc: int) -> None:
        """Set Constant Fraction Discriminator (CFD) levels for input channel.

        Args:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            level: CFD discriminator level in millivolts (mV) range 0 to 1000 representing 0 to -1000 mV.
            zc: CFD zero cross level in millivolts (mV). range 0 to 40 mV representing 0 to 40 mV.
        """
        raise NotImplementedError()

    @rpc_method
    def set_sync_offset(self, sync_offset: int) -> None:
        """Set SYNC offset.

        This function can replace an adjustable cable delay. A positive offset corresponds to inserting a cable in
        the sync input.

        Arguments:
            sync_offset: SYNC offset, in [ps]. A value ranging from -99999 ps to +99999 ps.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def set_sync_channel_offset(self, value: int) -> None:
        """Set SYNC channel offset.

        This is equivalent to changing the cable delay on the sync input. Actual resolution is the device's base
        resolution.

        Arguments:
            value: SYNC channel offset, in [ps]. A value ranging from -99999 ps to +99999 ps.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def set_input_channel_offset(self, channel: int, value: int) -> None:
        """Set input channel offset.

        This is equivalent to changing the cable delay on the chosen input. Actual resolution is the device's base
        resolution.

        Arguments:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            value: channel offset, in [ps]. A value ranging from -99999 ps to +99999 ps.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetInputChannelOffset(self._devidx, channel, value)

    @rpc_method
    def set_input_channel_enable(self, channel: int, enable: bool) -> None:
        """Enable or disable the input channel.

        Arguments:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            enable: True to enable the channel, False to disable.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            enable_int = 1 if enable else 0
            self._lib.SetInputChannelEnable(self._devidx, channel, enable_int)

    @rpc_method
    def get_flags(self) -> List[str]:
        """Get flags.

        Returns:
            A list of active flags, represented as short strings.
            See the definition of the :class:`~qmi.instruments.picoquant.<xxx>harp_wrapper.FLAG`
            type for possible values. <xxx> = multi, hydra, pico or time.
            The meaning of these flags is not fully documented.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_histogram(self, channel: int, clear: Optional[int] = None) -> np.ndarray:
        """Get histogram data array from a specific channel. Note that MH_GetHistogram cannot be used with the
        shortest two histogram lengths of 1024 and 2048 bins. You need to use MH_GetAllHistograms in this case.

        Arguments:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            clear: Optional input for HydraHarp only: 0 = keep histogram in buffer, 1 = clear buffer

        Returns:
              Histogram data array for given input channel.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            # The histogram buffer size must correspond to the default or the value obtained through MH_SetHistoLen().
            hist_data = np.empty(self._actuallen, dtype=np.uint32)
            ctypes_hist_data = hist_data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32))
            if clear is not None:
                self._lib.GetHistogram(self._devidx, ctypes_hist_data, channel, clear)

            else:
                self._lib.GetHistogram(self._devidx, ctypes_hist_data, channel)

            return hist_data.copy()

    @rpc_method
    def get_all_histograms(self) -> np.ndarray:
        """Get histogram data array from a specific channel. The multidimensional array receiving the data must be
         shaped according to the number of input channels of the device and the chosen histogram length.

        Returns:
              Histogram data arrays of all channels.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_warnings(self) -> List[str]:
        """Get a list of warnings.

        Returns:
            A list of strings. See the definition of the :class:`~qmi.instruments.picoquant.<xxx>harp_wrapper.WARNING`
            type for possible values. <xxx> = multi, hydra, pico or time.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_warnings_text(self, warnings: int) -> str:
        """Translates warnings into human-readable text.

        Arguments:
            warnings: integer bitfield obtained from MH_GetWarnings

        Returns:
            The warning text string.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            text = ctypes.create_string_buffer(16384)
            self._lib.GetWarningsText(self._devidx, text, warnings)
            return text.value.decode()

    @rpc_method
    def set_trigger_output(self, period: int) -> None:
        """Set trigger output.

        Set the period of the programmable trigger output. The period 0 switches it off.

        Arguments:
            period: Period in units of 100 ns range is 0 to 16777215.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_module_info(self) -> List[Tuple[int, int]]:
        """Get the model and version codes of all modules of the device.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            List of tuples (modelcode, versioncode).
            This information may be needed for support queries.
            The meaning of these numbers is not documented.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()
