from enum import IntEnum

import numpy as np

SYNC_TYPE = 64  # Event type of SYNC events.
# Numpy record type used to represent event records.
# Event types 0 to 7 represent a normal event.
# Event type 64 represents a SYNC event.
# Event types 65 to 79 represent marker events.
EventDataType = np.dtype([
    ("type", np.uint8),
    ("timestamp", np.uint64)
])


class EventFilterMode(IntEnum):
    """The filter modes for channel filtering.

    0: NO_EVENTS - block all events from a channel.
    1: ALL_EVENTS - Do not filter events from this channel.
    2: APERTURE - filters events outside given 'aperture' time range (min-max) per sync event.
    """
    NO_EVENTS = 0
    ALL_EVENTS = 1
    APERTURE = 2


class EventDecoder:

    def __init__(self, sync_frequency_hz: float = 5E6, resolution_ps: float = 1.0) -> None:
        """EventDecoder base class for different mode event decoders.

        Parameters:
            sync_frequency_hz:     The sync signal frequency is Hz. Default 5MHz.
            resolution_ps:         The time tag resolution from 1 to 33 554 432 ps. Relevant only in T3 mode, as in T2
            mode this is always 1 (base resolution, default).
        """
        self._sync_period_ps = 1E12 / sync_frequency_hz  # From 1/s to 1/ps. Used only in T3 mode
        self._resolution_ps = resolution_ps
        self._overflow_counter = 0

    def process_data(self, fifo_data: np.ndarray) -> np.ndarray:
        """Decode event records from the Multi- or HydraHarp T2 or T3 data stream.

        This function decodes raw 32-bit TTTR event records and returns
        an array of structured event records.

        Overflow records in the TTTR stream are used to assign an unwrapped
        64-bit timestamp value to each event. The overflow records are removed
        from the event array returned by this function.

        The `EventDecoder` instance keeps track of the running overflow counter.
        The sequence of calls to this method must therefore correspond to
        a single TTTR data stream, processed in order, without gaps or data loss.

        Parameters:
            fifo_data: Numpy array of 32-bit raw event records in TTTR T2 or T3 format.

        Returns:
            Numpy array of `EventDataType` records.
        """
        raise NotImplementedError


class _T2EventDecoder(EventDecoder):
    """Decode the MultiHarp, HydraHarp TTTR data stream in T2 mode."""

    def process_data(self, fifo_data: np.ndarray) -> np.ndarray:

        #
        # MultiHarp T2 TTTR event record format:
        #   bit  31    = special_flag
        #   bits 30:25 = channel
        #   bits 24:0  = timetag
        #
        # The "timetag" value is a multiple of the instrument base resolution (80 ps for MultiHarp).
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

        # Extract the 25-bit "timetag" field. For overflow records, this is the overflow increment;
        # for event records, this is the time-tag (offset since last overflow).
        record_tags = (fifo_data & 0x01ffffff)  # 0x01ffffff = 2^25 - 1

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
        events["type"] = event_types  # type: ignore[call-overload]
        events["timestamp"] = event_timestamps  # type: ignore[call-overload]

        return events


class _T3EventDecoder(EventDecoder):
    """Decode the MultiHarp, HydraHarp TTTR data stream in T3 mode."""

    def process_data(self, fifo_data: np.ndarray) -> np.ndarray:

        # Multi/HydraHarp T3 TTTR event record format:
        #   bit  31    = special_flag
        #   bits 30:25 = channel
        #   bits 24:10 = d_time
        #   bits 9:0   = n_sync
        #
        # The "n_sync" and "d_time" values are multiples of the instrument base resolution (32 ps for HydraHarp).
        # Overflow of the 25-bit counter is marked via special overflow records.
        #
        # If special_flag == 0, the record represents a normal event record on the specified channel.
        # If special_flag == 1 And channel == 63, the record represents sync count overflow of the 25-bit time value.
        # The number of overflows can be read from the n_sync value.
        # If special_flag == 1 And 1 <= channel <= 15, the record represents an external marker event.
        #

        # Type code for overflow events.
        # Note that overflow channel is 63, but here also special flag is added, so 0x7f.
        overflow_type = 0x7f

        # Overflow period is the full range of the 10 bits sync counter times the period of the sync signal.
        overflow_period = (1 << 10) * self._sync_period_ps

        # Extract the 7-bit "type" field of each record by shifting 25 last bits out.
        # The "type" field consists of the 1-bit "special" flag together with the 6-bit "channel" field.
        record_types = (fifo_data >> 25).astype(np.uint8)

        # Extract the 15-bit "d_time" field by shifting 10 last bits out and taking 15 bits. Include resolution
        d_times = (fifo_data >> 10 & 0x07fff).astype(np.uint64) * self._resolution_ps  # 0x07fff = 2^15 - 1
        # Extract the 10-bit "n_sync" field. For overflow records, this is the overflow increment;
        # for event records, this is the time-tag (non-frequency corrected sync moment).
        n_syncs = (fifo_data & 0x03ff)  # 0x03ff = 2^10 - 1

        # Make a bool array marking the overflow records.
        overflow_records_bool = (record_types == overflow_type)

        # Make a bool array marking the normal (non-overflow) records.
        event_records_bool = ~overflow_records_bool

        # Prepare a running count of the number of overflows
        overflow_counts = np.cumsum(overflow_records_bool * n_syncs, dtype=np.uint64)
        overflow_counts += self._overflow_counter

        # Update the overflow counter to take this batch of events into account.
        if len(overflow_counts) > 0:
            self._overflow_counter = int(overflow_counts[-1])

        # Select the event types of the non-overflow records.
        event_types = record_types[event_records_bool]

        # Calculate the sync and event timestamps of the non-overflow records.
        sync_timestamps = overflow_counts[event_records_bool] * overflow_period +\
                          n_syncs[event_records_bool] * self._sync_period_ps
        event_timestamps = sync_timestamps + d_times[event_records_bool]

        # Remove duplicates from syncs
        sync_timestamps = np.unique(sync_timestamps)

        # Copy the non-overflow records to a result array.
        num_data_events = len(event_types)
        num_events = num_data_events + len(sync_timestamps)
        events = np.empty(num_events, dtype=EventDataType)
        events[:num_data_events]["type"] = event_types  # type: ignore[call-overload]
        events[:num_data_events]["timestamp"] = event_timestamps  # type: ignore[call-overload]
        events[num_data_events:]["type"] = 64  # type: ignore[call-overload]
        events[num_data_events:]["timestamp"] = sync_timestamps  # type: ignore[call-overload]
        # Events need to be sorted by timestamp, and by type number so that sync# 64 is before channel#.
        # NOTE: Since numpy 2.0 overflow of values is not allowed anymore. Therefore, for the means of the lexical sort
        # where we use the trick of setting the event types as their negatives to get the right order, now must be
        # retyped from unsigned 8-bit integer to signed 16-bit integer. The returned array by the lexsort does
        # re-conform to uint8 when placing it back to `events`, so no errors should be introduced.
        events = events[np.lexsort((-1 * events["type"].astype("int16"), events["timestamp"]))]

        return events
