import enum
import time
from threading import Condition, Lock
from collections.abc import Callable

import numpy as np

from qmi.core.exceptions import QMI_InvalidOperationException, QMI_RuntimeException, QMI_UsageException
from qmi.core.thread import QMI_Thread
from qmi.instruments.picoquant.support._decoders import (
    EventDataType, EventDecoder, EventFilterMode, SYNC_TYPE, _T2EventDecoder, _T3EventDecoder
)
from qmi.instruments.picoquant.support._realtime import _RealTimeHistogramProcessor, _get_sync_deltas


@enum.unique
class _MODE(enum.Enum):
    """Symbolic constants for the :func:`~MultiHarpDevice.initialize` method's `mode` argument.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """
    HIST = 0
    """Histogram mode."""
    T2 = 2
    """T2 mode."""
    T3 = 3
    """T3 mode."""
    CONT = 8
    """Continuous Mode"""


class _FetchEventsThread(QMI_Thread):
    """This thread continuously fetches event data from the MultiHarp via USB."""

    _LOOP_SLEEP_DURATION = 0.01

    def __init__(self,
                 read_fifo_func: Callable[[], np.ndarray],
                 publish_histogram_func: Callable,
                 publish_countrate_func: Callable,
                 max_pending_events: int = 10**8
                 ) -> None:
        """Initialize background event fetching thread.

        Parameters:
            read_fifo_func: Callable that can be used to obtain an ndarray of FIFO data.
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
        self._mode = _MODE.HIST  # Start up _mode class variable in HIST mode to give a value. Will be T2 or T3 later.
        self._condition = Condition(Lock())
        self._decoder = EventDecoder()
        self._event_filter = _EventFilter()
        self._histogram_processor = _RealTimeHistogramProcessor(publish_histogram_func, publish_countrate_func)
        self._event_filter_channels: dict[int, EventFilterMode] = {}
        self._event_filter_aperture = (0, 0)
        self._histogram_channels: list[int] = []
        self._histogram_resolution = 1
        self._histogram_num_bins = 0
        self._histogram_num_sync = 0
        self._countrate_aperture = (0, 0)
        self._countrate_num_sync = 0
        self._active = False
        self._count_read_fifo = 0
        self._block_events = False
        self._data: list[np.ndarray] = []
        self._data_timestamp = 0.0
        self._num_pending_events = 0
        self._pending_events_overflow = False
        self._max_pending_events = max_pending_events

    def _process_fifo_data(self, fifo_data: np.ndarray, fifo_data_timestamp: float) -> None:
        """Process new received raw event records from the multiharp, hydraharp.

        This function will be called in the background 'run' thread while holding the "self._condition" lock.
        """
        # Decode event records.
        event_records = self._decoder.process_data(fifo_data)
        # Update real-time histogram
        self._histogram_processor.process_events(event_records)

        if not self._block_events:

            event_records = self._event_filter.process_events(event_records)

            # Store filtered events.
            num_events = len(event_records)
            if num_events > 0:
                if self._num_pending_events + num_events > self._max_pending_events:
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
                    # Read data from a Harp, if any.
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

    def activate(self, mode: _MODE = _MODE.T2, sync_frequency_hz: float = 5E6, resolution_ps: float = 1.0) -> None:
        """Activate background event fetching.

        This method is called immediately after starting a measurement in TTTR mode.
        It activates continuous event fetching in the background thread.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.

        Parameters:
            mode: The mode to activate the event fetching in. Can be _MODE.T2 (default) or _MODE.T3.
            sync_frequency_hz: The synchronization signal frequency (in Hz). Applicable only in T3 mode. Default 5 MHz.
            resolution_ps: The resolution of a 15-bit d_time bit in picoseconds. Default is 1.0 ps.
        """
        self._mode = mode
        with self._condition:
            if self._active:
                raise QMI_InvalidOperationException("Already active")

            if self._mode == _MODE.T2:
                self._decoder = _T2EventDecoder()

            elif self._mode == _MODE.T3:
                self._decoder = _T3EventDecoder(sync_frequency_hz, resolution_ps)

            else:
                raise QMI_UsageException(f"No event processing decoder for mode {self._mode}")

            self._event_filter.set_event_filter_config(self._event_filter_channels,
                                                       self._event_filter_aperture)
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
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.
        """
        with self._condition:
            self._active = False
            self._condition.notify_all()

    def set_block_events(self, blocked: bool) -> None:
        """Enable or disable blocking of events.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.

        Parameters:
            blocked: A boolean flag to enable or disable event block.

        """
        with self._condition:
            self._block_events = blocked

    def set_event_filter_config(self,
                                channel_filter: dict[int, EventFilterMode],
                                sync_aperture: tuple[int, int]
                                ) -> None:
        """Update event filter parameters.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.

        Parameters:
            channel_filter: A dictionary of channel number with their respective event filter modes.
            sync_aperture: [min, max] aperture times respective to the synchronization moment per channel.
        """
        with self._condition:
            self._event_filter_channels = channel_filter
            self._event_filter_aperture = sync_aperture
            self._event_filter.set_event_filter_config(channel_filter, sync_aperture)

    def set_histogram_config(self, channels: list[int], bin_resolution_ps: int, num_bins: int, num_sync: int) -> None:
        """Configure real-time histograms.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.

        Parameters:
            channels: Channel numbers to collect the histogram for.
            bin_resolution_ps: The bin resolution in picoseconds.
            num_bins: The number of bins in the histogram.
            num_sync: The number of synchronizations to collect the histogram data for.
        """
        with self._condition:
            self._histogram_channels = channels
            self._histogram_resolution = bin_resolution_ps
            self._histogram_num_bins = num_bins
            self._histogram_num_sync = num_sync
            self._histogram_processor.set_histogram_config(channels, bin_resolution_ps, num_bins, num_sync)

    def set_countrate_config(self, sync_aperture: tuple[int, int], num_sync: int) -> None:
        """Configure real-time count rate reporting.

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.

        Parameters:
            sync_aperture: [min, max] aperture times respective to the synchronization moment per channel.
            num_sync: The number of synchronizations to collect the count rate for.
        """
        with self._condition:
            self._countrate_aperture = sync_aperture
            self._countrate_num_sync = num_sync
            self._histogram_processor.set_countrate_config(sync_aperture, num_sync)

    def _request_shutdown(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def get_events(self, max_events: int) -> tuple[float, np.ndarray]:
        """Return events fetched by the background thread.

        Parameters:
            max_events: Maximum number of events to return.

        Returns:
            Tuple (timestamp, event_data).

        This method is thread-safe.
        It will be called in the thread that owns the `PicoQuant_MultiHarp150`, `PicoQuant_HydraHarp400` instance.
        """

        # Accept at most `max_events` pending event records.
        # This must be done under the condition variable lock.
        with self._condition:

            data_timestamp = self._data_timestamp

            if self._pending_events_overflow:
                # Events got dropped because there were too many pending events.
                # Discard all pending events and clear the overflow flag, then raise an exception.
                # TODO: Handle the events up to 'max' anyhow first and only then discard the rest?
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
                                channel_filter: dict[int, EventFilterMode],
                                sync_aperture: tuple[int, int]
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
        """Filter MultiHarp event records.

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
