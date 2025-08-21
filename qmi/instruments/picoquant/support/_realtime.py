from collections.abc import Callable
from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike

from qmi.instruments.picoquant.support._decoders import SYNC_TYPE

NUM_CHANNELS = 8


class RealTimeHistogram(NamedTuple):
    """Real-time histogram from MultiHarp T2 event data.

    Attributes:
        start_timestamp: MultiHarp timestamp of first SYNC event of the histogram.
        bin_resolution:  Histogram bin resolution as multiple of the instrument base resolution.
        num_sync:        Number of SYNC periods included in this histogram.
        channels:        List of channel numbers included in the histogram.
        histogram_data:  2D array of shape (num_channels, num_bins) containing counts for each bin.
    """
    start_timestamp: int
    bin_resolution: int
    num_sync: int
    channels: list[int]
    histogram_data: np.ndarray


class RealTimeCountRate(NamedTuple):
    """Real-time count rate from MultiHarp T2 event data.

    Attributes:
        start_timestamp: MultiHarp timestamp of the SYNC event that started the counters.
        num_sync:        Number of SYNC periods included in the counter values.
        counts:          1D array of counter value for each input channel.
    """
    start_timestamp: int
    num_sync: int
    counts: np.ndarray


class _RealTimeHistogramProcessor:
    """Extract real-time histograms and count rates from event data."""

    def __init__(self, publish_histogram_func: Callable, publish_countrate_func: Callable) -> None:
        """Initialize histogram processing.

        Parameters:
            publish_histogram_func: A call-back function for publishing the histogram.
            publish_countrate_func: A call-back function for publishing the count rate.
        """
        self._publish_histogram_func = publish_histogram_func
        self._publish_countrate_func = publish_countrate_func
        self._previous_sync_timestamp = -1

        self._histogram_channels: list[int] = []
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

    def set_histogram_config(self, channels: list[int], bin_resolution_ps: int, num_bins: int, num_sync: int) -> None:
        """Configure real-time histograms.

        Parameters:
            channels: Channel numbers to collect the histogram for.
            bin_resolution_ps: The bin resolution in picoseconds.
            num_sync: The number of synchronizations to collect the histogram data for.

        """

        assert bin_resolution_ps > 0
        self._histogram_channels = channels
        self._histogram_resolution = bin_resolution_ps
        self._histogram_num_bins = num_bins
        self._histogram_num_sync = num_sync

        # Clear data.
        self._histogram_data = np.zeros((len(channels), num_bins), dtype=np.uint32)
        self._histogram_sync_counter = -1

    def set_countrate_config(self, sync_aperture: tuple[int, int], num_sync: int) -> None:
        """Configure real-time count rate reporting.

        Parameters:
            sync_aperture: [min, max] aperture times respective to the synchronization moment per channel.
            num_sync: The number of synchronizations to collect the count rate for.
        """
        self._countrate_aperture = sync_aperture
        self._countrate_num_sync = num_sync

        # Clear data.
        self._countrate_data = np.zeros(NUM_CHANNELS, dtype=np.uint64)
        self._countrate_sync_counter = -1

    def process_events(self, event_records: np.ndarray) -> None:
        """Process event records and update histogram and count rates.

        Parameters:
            event_records: An array of (SYNC_TYPE, timestamp) event records.
        """

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


def _get_sync_deltas(event_records: np.ndarray, sync_events_idx: np.ndarray) -> np.ndarray:
    """For each event record, determine the time delta since the last SYNC event.

    Parameters:
        event_records:   Array of structured event records with "type" and "timestamp" fields.
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


class TttrHistogram:
    """Class to make histograms from Time Tagged Time Resolved (TTTR) T2-mode data."""

    def __init__(self, channel: int, numbins: int):
        """Initialization of histogram bins, counts and deltas. In T2 mode the default bin size is 1E-12 s.

        Parameters:
            channel: The channel number to collect TTTR histogram data for.
            numbins: The number of bins to divide the data for.
        """
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
        """Process events, and filter by aperture (if applicable).

        Parameters:
            events: An array of (SYNC_TYPE, timestamp) event records.
        """

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

    def get_plot_data(self, bin_resolution_s: float) -> tuple[ArrayLike, ArrayLike, int]:
        """Convenience function for plotting to return bin values and counts to the caller.

        Parameters:
            bin_resolution_s: bin resolution for the histogram. Unit is seconds.

        Returns:
            Tuple of (bin values data, self.counts, number of bins in self.bins)
        """
        return self.bins * bin_resolution_s / 1e-9, self.counts, len(self.bins)
