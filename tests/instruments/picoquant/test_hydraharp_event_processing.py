#! /usr/bin/env python3

"""Unit test for T3 mode event processing in HydraHarp driver."""

import ctypes
import threading
import unittest
from unittest.mock import patch, PropertyMock

import numpy as np

from qmi.core.exceptions import QMI_RuntimeException
from qmi.core.pubsub import QMI_SignalReceiver
from qmi.instruments.picoquant.support._hhlib_function_signatures import _hhlib_function_signatures
from qmi.instruments.picoquant.support._events import EventDataType, EventFilterMode
from qmi.instruments.picoquant import PicoQuant_HydraHarp400

from tests.patcher import PatcherQmiContext as QMI_Context


def gen_events(max_events, sync_period):
    events_in = np.empty(max_events, dtype=EventDataType)
    events_in["type"] = 0
    events_in["timestamp"] = np.cumsum(np.random.randint(1, sync_period, max_events))
    # At each passing of a sync moment we need to add a sync signal
    (inds,) = np.where((
            events_in["timestamp"] // sync_period > np.insert(events_in["timestamp"], 0, 0)[:-1] // sync_period
    ))
    # And then insert the sync signals and cap the length
    events_in["type"] = np.insert(events_in["type"], inds - 1, np.array([64] * len(inds)))[:max_events]
    events_in["timestamp"] = np.insert(
        events_in["timestamp"], inds - 1,
                                (events_in["timestamp"] // sync_period)[inds - 1] * sync_period
    )[:max_events]
    events_in = events_in[np.lexsort((-1 * events_in["type"].astype("int16"), events_in["timestamp"]))]
    # This can leave the last index wrong. Check.
    last_sync_index = -(events_in["type"][::-1].tolist().index(64) + 1)
    if (events_in["timestamp"][-1] - events_in["timestamp"][last_sync_index]) > sync_period:
        # we replace the last input with a sync
        events_in["type"][-1] = 64
        events_in["timestamp"][-1] = events_in["timestamp"][last_sync_index] + sync_period
        events_in = events_in[np.lexsort((-1 * events_in["type"].astype("int16"), events_in["timestamp"]))]

    return events_in


def gen_random_events(num_events, event_rate, sync_rate, resolution, channels, seed=None):
    rng = np.random.default_rng(seed)

    mean_event_interval = event_rate // num_events // resolution
    delta_times = rng.exponential(scale=mean_event_interval, size=num_events)
    delta_times = delta_times.astype(np.uint64)
    event_timestamps = np.cumsum(delta_times)

    sync_period = 1e12 / sync_rate
    syncs_in_events = int(event_timestamps.max() // sync_period)
    sync_timestamps = np.linspace(0, sync_period * syncs_in_events, num=(syncs_in_events + 1))
    # Filter out only those syncs that have an event within sync range
    inds = [i for i in range(0, len(sync_timestamps) - 2) if np.any(
        (event_timestamps > sync_timestamps[i]) & (sync_timestamps[i + 1] > event_timestamps)
    )]
    sync_timestamps = sync_timestamps[np.array(inds)]
    sync_timestamps = sync_timestamps.astype(np.uint64)

    events = np.empty(num_events + len(sync_timestamps), dtype=EventDataType)
    events[:num_events]["type"] = rng.choice(channels, size=num_events)
    events[:num_events]["timestamp"] = event_timestamps
    events[num_events:]["type"] = 64
    events[num_events:]["timestamp"] = sync_timestamps
    events = np.unique(events)  # Remove any duplicates
    events = events[np.lexsort((-1 * events["type"].astype("int16"), events["timestamp"]))]

    return events[:num_events]


def events_to_fifo(events, sync_period, resolution):
    """Convert array of events to the corresponding HydraHarp T3 FIFO data words."""

    # Convert events to array (if necessary).
    evt_array = np.array([_ for _ in events if _[0] != 64], dtype=EventDataType)

    # Check monotonic timestamps.
    assert np.all(evt_array["timestamp"][1:] >= evt_array["timestamp"][:-1])

    tmp_types = evt_array["type"]
    tmp_timestamps = evt_array["timestamp"]

    # count "timestamp" residuals over sync moments for nsync.
    nsync_counts = (tmp_timestamps // sync_period - np.insert(tmp_timestamps, 0, 0)[:-1] // sync_period)
    # In bits 10:25 will be added the dtime.
    dtime_counts = (tmp_timestamps % sync_period).astype(np.uint64) // int(resolution)
    # Filter out timestamps outside sync period range.
    relative_timestamp = tmp_timestamps - np.cumsum(nsync_counts) * sync_period
    valid_ndx = relative_timestamp < sync_period
    # We have to remove any entries that are larger than the 2^15 - 1 (32767 * R) range
    valid_ndx = valid_ndx & (dtime_counts < (2 ** 15 - 1) / resolution)
    # Filter out invalid indexes for d_time and also for time stamps.
    nsync_counts = nsync_counts[valid_ndx]
    dtime_counts = dtime_counts[valid_ndx]
    tmp_timestamps = tmp_timestamps[valid_ndx]

    # Insert overflow records at positions where the MSB part of the timestamp changes.
    overflows = (
            tmp_timestamps // sync_period // 1024
            - np.insert(tmp_timestamps, 0, 0)[:-1] // sync_period // 1024
    )
    (overflow_idx,) = np.where(overflows > 0)
    overflow_counts = overflows[overflow_idx]
    # Have to set counts, special bit (31 from this side) for overflow, and the channel number (63 for overflow)
    overflow_words = overflow_counts.astype(np.uint64) & 0x01ffffff | ((1 << 31) | (63 << 25))
    # Convert events to FIFO words. Include "type" for channel number.  This has to be all done in one go.
    fifo_words = (
            (tmp_types[valid_ndx].astype(np.uint64) << 25) |  # Shift the channel numbers to bits 25:30
            (dtime_counts.astype(np.uint64) << 10) |  # dtimes at bits 10:24
            np.cumsum(nsync_counts).astype(np.uint64) & 0x03ff  # nsync at bits 0:9
    )
    # And then insert the overflow_words into it:
    fifo_words = np.insert(fifo_words, overflow_idx, overflow_words)

    return fifo_words


def make_patched_read_fifo(fifo_words, done_event):
    """Return a function to be used in place of the actual readFifo() method in the HydraHarp API."""

    fifo_pos = [0]

    def patched_read_fifo(_, fifo_data, ttreadmax, nactual):
        pos = fifo_pos[0]
        n_fifo_words = len(fifo_words)
        npos = min(n_fifo_words, pos + ttreadmax)  # read 131072 words. Resets timestamp after npos words.
        fifo_pos[0] = npos
        for i, val in enumerate(fifo_words[pos:npos]):
            fifo_data[i] = val
        nactual.value = npos - pos
        if (done_event is not None) and (pos == n_fifo_words):
            done_event.set()
        return 0

    return patched_read_fifo


class TestHydraHarpEventFilter(unittest.TestCase):

    # Reduced limit on maximum pending events to make it easier to test.
    PATCHED_MAX_PENDING_EVENTS = 1024
    PATCHED_MAX_EVENTS_PER_CALL = 100000  # Should be less than TTREADMAX
    SYNC_FREQUENCY_32MHz = 32e6  # Use 32MHz sync frequency.
    SYNC_FREQUENCY_5MHz = 5e6  # Use 5MHz sync frequency.
    RESOLUTION_LIMIT = 2**15 - 1   # Limit for 32768*R resolution limit

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Generate random event sets to be used in test cases.
        self.events_in_resolution_1 = gen_random_events(
            num_events=1000,
            event_rate=2.0e6,
            sync_rate=self.SYNC_FREQUENCY_32MHz,  # creates a sync period of 31250 < 2**15 - 1
            resolution=1,
            channels=[0, 1],
            seed=2345,
        )

        self.events_in_4chan_resolution_1 = gen_random_events(
            num_events=50000,
            event_rate=1.0e9,
            sync_rate=self.SYNC_FREQUENCY_32MHz,
            resolution=1,
            channels=[0, 1, 2, 3],
            seed=1234,
        )

    def setUp(self) -> None:
        patcher = patch('qmi.instruments.picoquant.PicoQuant_HydraHarp400._lib', new_callable=PropertyMock)
        self._library_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

        function_names, _, _ = zip(*_hhlib_function_signatures)
        stripped_names = [name.split("_")[1] for name in function_names]
        self._library_mock.mock_add_spec(stripped_names, spec_set=True)

        # Create QMI context.
        self._ctx = QMI_Context("hydraharp_eventfilter_test")

        # Create instrument instance. Limit MAX calls to avoid problems.
        PicoQuant_HydraHarp400.MAX_EVENTS_PER_CALL = self.PATCHED_MAX_EVENTS_PER_CALL
        if self._testMethodName == "test_pending_events_limit":
            self._hydraharp: PicoQuant_HydraHarp400 = PicoQuant_HydraHarp400(
                self._ctx,
                "hydraharp",
                "1111111",
                max_pending_events=self.PATCHED_MAX_PENDING_EVENTS
            )
        else:
            self._hydraharp: PicoQuant_HydraHarp400 = PicoQuant_HydraHarp400(
                self._ctx,
                "hydraharp",
                "1111111"
            )

        self._library_mock.GetLibraryVersion.return_value = 0
        self._library_mock.OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b"1111111")
        with patch("sys.platform", "linux1"), patch(
            "ctypes.create_string_buffer", return_value=string_buffer
        ):
            self._hydraharp.open()

        self._hydraharp.initialize("T3", "EXTERNAL")

    def tearDown(self):
        # Close instrument instance.
        self._hydraharp.close()
        self._ctx = None

    def test_simple(self):
        """Simple test with default fixed sync frequency and resolution being 1ps."""
        # Events to use during this test. In T3 mode there is in principle one sync event per channel.
        # There are thus 1 sync event per sync period, which is 1/self.SYNC_FREQUENCY * 1E12 (2E5 ps at 5MHz)
        sync_period = 1e12 / self.SYNC_FREQUENCY_5MHz
        events_in = [
            (64, 0),
            (0, int(self.RESOLUTION_LIMIT // 3)),
            (1, int(self.RESOLUTION_LIMIT // 2)),
            (64, int(sync_period * 5000)),
            (0, int(sync_period * 5000 + self.RESOLUTION_LIMIT // 3)),
            (0, int(sync_period * 5000 + self.RESOLUTION_LIMIT // 2)),
            (64, int(sync_period * 6025)),
            (1, int(sync_period * 6025 + self.RESOLUTION_LIMIT // 4)),
            (1, int(sync_period * 6025 + self.RESOLUTION_LIMIT // 2)),
        ]

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, 1.0)  # resolution = 1
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_5MHz))
        resolution = ctypes.c_double(1.0)
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Check events.
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertTrue(np.all(events == np.array(events_in, dtype=EventDataType)))

    def test_resolution_simple(self):
        """Simple test with default fixed sync frequency and resolution being 1ps."""
        # Events to use during this test. In T3 mode there is in principle one sync event per channel.
        # There are thus 1 sync event per sync period, which is 1/self.SYNC_FREQUENCY * 1E12 (2E5 ps at 5MHz)
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_5MHz))
        sync_period = 1e12 / sync_rate.value
        resolution = ctypes.c_double(2.0)
        events_in = [
            (64, 0),
            (0, int(self.RESOLUTION_LIMIT // 4)),
            (1, int(self.RESOLUTION_LIMIT // 3)),
            (64, int(sync_period * 5000)),
            (0, int(sync_period * 5000 + self.RESOLUTION_LIMIT // 4)),
            (0, int(sync_period * 5000 + self.RESOLUTION_LIMIT // 3)),
            (64, int(sync_period * 6025)),
            (1, int(sync_period * 6025 + self.RESOLUTION_LIMIT // 5)),
            (1, int(sync_period * 6025 + self.RESOLUTION_LIMIT // 3)),
        ]
        expected_events = np.array(events_in, dtype=EventDataType)
        for e in (1, 4, 7):
            expected_events[e][1] -= 1

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Check events.
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertTrue(np.all(events == expected_events))

    def test_simple_clip_resolution(self):
        """Simple test with default fixed sync frequency and resolution being 4ps.
        Most of the sample events need to be modified to be a multiple of 4 to get exact same numbers out.
        """
        # Events to use during this test. In T3 mode there is in principle one sync event per channel.
        # There are thus 1 sync event per sync period, which is 1/self.SYNC_FREQUENCY * 1E12 (2E5 ps at 5MHz)
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_5MHz))
        sync_period = 1e12 / sync_rate.value
        resolution = ctypes.c_double(4.0)
        events_in = [
            (64, 0),
            (1, int(self.RESOLUTION_LIMIT // 3 + 2)),
            (0, int(self.RESOLUTION_LIMIT // 2 + 1)),
            (1, int(self.RESOLUTION_LIMIT + 1)),  # should be clipped
            (64, int(sync_period * 5000)),
            (0,  int(sync_period * 5000 + self.RESOLUTION_LIMIT // 3 + 2)),
            (0,  int(sync_period * 5000 + self.RESOLUTION_LIMIT // 2 + 1)),
            (0,  int(sync_period * 5000 + self.RESOLUTION_LIMIT + 1)),  # should be clipped
            (64, int(sync_period * 6025)),
            (0,  int(sync_period * 6025 + self.RESOLUTION_LIMIT // 4 + 1)),
            (1,  int(sync_period * 6025 + self.RESOLUTION_LIMIT // 2 + 1)),
            (1,  int(sync_period * 6025 + self.RESOLUTION_LIMIT))  # Cannot add, edit later
        ]
        expected_events = np.delete(np.array(events_in, dtype=EventDataType), [3, 7])
        expected_events[-1][1] -= 3  # rounds down to closest multiple of 4
        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)  # resolution = 1
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Check events.
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertTrue(np.all(events == expected_events))

    def test_channel_filter(self):
        """Test filtering by setting channels 1 and 2 to be filtered out."""
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_32MHz))
        resolution = ctypes.c_double(1.0)
        sync_period = 1e12 / sync_rate.value
        # Generate a random set of events.
        events_in = self.events_in_4chan_resolution_1

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Configure event filter: block events form channels 1 and 2.
        self._hydraharp.set_event_filter(
            channel_filter={1: EventFilterMode.NO_EVENTS, 2: EventFilterMode.NO_EVENTS}
        )

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Expect only events on SYNC and channels 0 and 1. Also sort.
        events_expected = events_in[
            (events_in["type"] == 64)
            | (events_in["type"] == 0)
            | (events_in["type"] == 3)
        ]
        events_expected = events_expected[
            np.lexsort((-1 * events_expected["type"].astype("int16"), events_expected["timestamp"]))
        ]
        # Check events.
        self.assertTrue(np.all(events == events_expected))

    def test_aperture_filter_events(self):
        """Filter out events that do not fall withing a specific 'aperture' time per channel."""
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_32MHz))
        resolution = ctypes.c_double(1.0)
        sync_period = 1e12 / sync_rate.value
        num_events = 50000
        event_rate = 2.0e9
        # Generate a random set of events.
        events_in = gen_random_events(
            num_events=num_events,
            event_rate=event_rate,
            sync_rate=sync_rate.value,
            resolution=resolution.value,
            channels=[0, 1],
            seed=2345,
        )

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Configure event filter: setup aperture filtering for channels 0 and 1.
        delta_min = int(25000 // resolution.value)
        delta_max = int(75000 // resolution.value)
        self._hydraharp.set_event_filter(
            channel_filter={0: EventFilterMode.APERTURE, 1: EventFilterMode.APERTURE},
            sync_aperture=(delta_min, delta_max),
        )

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Expect only events on SYNC and events that fall in the aperture.
        events_expected = []
        last_sync = -1
        for evt_type, evt_timestamp in events_in:
            if evt_type == 64:
                last_sync = evt_timestamp
                events_expected.append((evt_type, evt_timestamp))
            else:
                if (last_sync >= 0) and (delta_min <= (evt_timestamp - last_sync) <= delta_max):
                    events_expected.append((evt_type, evt_timestamp))

        # Check events.
        self.assertTrue(np.all(events == np.array(events_expected, dtype=EventDataType)))

    def test_aperture_filter_sync(self):
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_32MHz))
        resolution = ctypes.c_double(1.0)
        sync_period = 1e12 / sync_rate.value
        # Generate a random set of events.
        events_in = self.events_in_resolution_1

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Configure event filter: setup aperture filtering for channels 0 and 1 and SYNC.
        delta_min = 25000
        delta_max = 75000
        self._hydraharp.set_event_filter(
            channel_filter={
                0: EventFilterMode.APERTURE,
                1: EventFilterMode.APERTURE,
                64: EventFilterMode.APERTURE,
            },
            sync_aperture=(delta_min, delta_max),
        )

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Expect only events on SYNC and events that fall in the aperture.
        events_expected = []
        last_sync = -1
        last_is_sync = False
        for evt_type, evt_timestamp in events_in:
            if evt_type == 64:
                if last_is_sync:
                    events_expected.pop()

                last_sync = evt_timestamp
                last_is_sync = True
                events_expected.append((evt_type, evt_timestamp))

            else:
                if (last_sync >= 0) and (delta_min <= evt_timestamp - last_sync <= delta_max):
                    events_expected.append((evt_type, evt_timestamp))
                    last_is_sync = False

        if last_is_sync:
            events_expected.pop()

        # Check events.
        self.assertTrue(np.all(events == np.array(events_expected, dtype=EventDataType)))

    def test_get_events_limit(self):
        """Test that the `get_events()` function returns at most MAX_EVENTS_PER_CALL events."""
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_32MHz))
        resolution = ctypes.c_double(4.0)
        sync_period = 1e12 / sync_rate.value
        # Generate random events.
        final_block_events = 10101
        events_per_call = PicoQuant_HydraHarp400.MAX_EVENTS_PER_CALL
        num_events = 2 * events_per_call + final_block_events
        events_in = np.empty(num_events, dtype=EventDataType)
        events_in["type"] = 0
        events_in["timestamp"] = np.cumsum(np.random.randint(1, 1000, num_events) * int(resolution.value))
        # The events will be passed to the driver in smaller series, in blocks of TTREADMAX.
        # Calculate the sync moments and add into the expected events that should come out
        expected_events = np.array(events_in, dtype=EventDataType)
        sync_counts = (
            expected_events["timestamp"] // sync_period
            - np.insert(expected_events["timestamp"], 0, 0)[:-1] // sync_period
        )
        sync_idx = np.where(sync_counts > 0)[0]
        # The above does not take into account the first possible sync timestamp at 0. Check.
        if sync_idx[0] > 0 and expected_events["timestamp"][0] < sync_period:
            sync_idx = np.insert(sync_idx, 0, 0)

        cum_counts = np.cumsum(sync_counts, dtype=np.uint64)
        # Problem: with resolution of 4, every second sync moment falls on "2".
        # So, every second block of timestamp data is shifted by 2. We need to take this into account.
        timestamp_shift = 2 * (cum_counts % 2)
        expected_events["timestamp"] -= timestamp_shift

        sync_events = np.empty(len(sync_idx), dtype=EventDataType)
        sync_events["type"] = 64
        sync_events["timestamp"] = cum_counts[sync_idx] * sync_period
        expected_events = np.insert(expected_events, sync_idx, sync_events)
        expected_events = expected_events[
            np.lexsort((-1 * expected_events["type"].astype("int16"), expected_events["timestamp"]))
        ]

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()
        done_event.clear()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        # It should return only the first MAX_EVENTS_PER_CALL events.
        events = self._hydraharp.get_events()

        # Check events.
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertEqual(len(events), events_per_call)
        self.assertTrue(np.all(events == expected_events[:events_per_call]))

        # Now get the next MAX_EVENTS_PER_CALL events.
        (_ts, events) = self._hydraharp.get_timestamped_events()
        # Find and remove any duplicates (possibly a bug of the test, but also possibly of the event fetching thread)
        vals, inverse, count = np.unique(events, return_inverse=True, return_counts=True)
        idx_vals_repeated = np.where(count > 1)[0]
        if idx_vals_repeated.shape[0] > 0:
            # duplicates[0] is an enumeration of duplicate values found and [1] the indices of the duplicates
            duplicates = np.where(inverse == idx_vals_repeated[:, np.newaxis])
            # As the enum repeats the same number as many times as value is found, and we want also to make sure we take
            # into account also the cases where there are more than one duplicate, we find with np.where how many same
            # values are present; with `+ 1` to shift the indices to remove other than the 1st (i.e. the original first)
            # value's duplicate(s).
            deletion_array = duplicates[1][np.where((duplicates[0][1:] - duplicates[0][:-1]) == 0)[0] + 1]
            events = np.delete(events, deletion_array)

        len_events = len(events)
        self.assertAlmostEqual(len_events, events_per_call, delta=1)  # delta takes into account that possibly one entry
        delta = events_per_call - len_events  # is removed.
        self.assertTrue(np.all(events == expected_events[events_per_call:2*events_per_call-delta]))

        # Get the final batch of events. Reduce the added sync events from total count
        events = self._hydraharp.get_events()
        self.assertEqual(len(events) - np.count_nonzero(expected_events["type"] == 64), final_block_events + 1)
        self.assertTrue(np.all(events == expected_events[2*events_per_call-delta:]))

        # Check no further events.
        events = self._hydraharp.get_events()
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(len(events), 0)

    def test_pending_events_limit(self):
        """Test that the driver correctly handles overflow of the pending event buffer. Resolution is 1"""
        sync_period = int(1e12 // self.SYNC_FREQUENCY_32MHz)
        # Generate a bunch of events that just barely fit into the pending event buffer.
        max_events = self.PATCHED_MAX_PENDING_EVENTS - 1
        events_in = gen_events(max_events, sync_period)

        # Patch the readFifo() function.
        # This fill feed the first part of the events to the driver (not enough to overflow the buffer).
        resolution = ctypes.c_double(1.0)
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_32MHz))
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all queued events are processed.
        done_event.wait()
        done_event.clear()

        # Fetch the events queued so far.
        events = self._hydraharp.get_events()
        # Check events.
        # if len(events) < len(events_in):
        # The `get_events` cannot give a sync signal as the last entry. If that is the case for events_in, remove it
        if events_in["type"][-1] == 64:
            events_in = events_in[:-1]

        self.assertEqual(len(events), len(events_in))
        self.assertTrue(np.all(events == events_in))

        # Generate more events than can fit into the pending event buffer.
        more_events = self.PATCHED_MAX_PENDING_EVENTS + 2
        more_events_in = gen_events(more_events, sync_period)

        # Repatch the readFifo() function to feed the new events into the running measurement.
        # This should/will cause the pending event buffer to overflow.
        more_fifo_words_in = events_to_fifo(more_events_in, sync_period, resolution.value)
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(more_fifo_words_in, done_event)
        # Wait to make sure all queued events are processed.
        done_event.wait()

        # Try to fetch events. This should raise an exception as a result of the overflow.
        with self.assertRaises(QMI_RuntimeException):
            _ = self._hydraharp.get_events()

        # Stop the measurement.
        done_event.clear()
        self._hydraharp.stop_measurement()

        # Generate new events to check that a subsequent measurement runs cleanly after overflow.
        events_in = gen_events(max_events, sync_period)

        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_32MHz))  # Redefine this as otherwise it gets corrupted
        with patch("ctypes.c_double", return_value=resolution), patch("ctypes.c_int", return_value=sync_rate):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all queued events are processed.
        done_event.wait()

        # Fetch the events queued so far.
        events = self._hydraharp.get_events()

        # Check events.
        # if len(events) < len(events_in):
        # The `get_events` cannot give a sync signal as the last entry. If that is the case for events_in, remove it
        if events_in["type"][-1] == 64:
            events_in = events_in[:-1]

        self.assertEqual(len(events), len(events_in))
        self.assertTrue(np.all(events == events_in))

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Check no further events.
        events = self._hydraharp.get_events()
        self.assertEqual(len(events), 0)


class TestHydraHarpRealtime(unittest.TestCase):
    """Test class to test real-time functionalities of event processing. This requires a running QMI context.
    """
    # Reduced limit on maximum pending events to make it easier to test.
    PATCHED_MAX_PENDING_EVENTS = 1024
    PATCHED_MAX_EVENTS_PER_CALL = 100000  # Should be less than TTREADMAX
    SYNC_FREQUENCY_32MHz = 32e6  # Use 32MHz sync frequency.
    SYNC_FREQUENCY_5MHz = 5e6  # Use 5MHz sync frequency.
    RESOLUTION_LIMIT = 2 ** 15 - 1  # Limit for 32768*R resolution limit

    def setUp(self) -> None:
        patcher = patch('qmi.instruments.picoquant.PicoQuant_HydraHarp400._lib', new_callable=PropertyMock)
        self._library_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

        function_names, _, _ = zip(*_hhlib_function_signatures)
        stripped_names = [name.split("_")[1] for name in function_names]
        self._library_mock.mock_add_spec(stripped_names, spec_set=True)

        # Start QMI context.
        self._ctx = QMI_Context("hydraharp_realtime_test")
        self._ctx.start()

        # Create instrument instance. Limit MAX calls to avoid problems.
        PicoQuant_HydraHarp400.MAX_EVENTS_PER_CALL = self.PATCHED_MAX_EVENTS_PER_CALL
        if self._testMethodName == "test_pending_events_limit":
            self._hydraharp = self._ctx.make_instrument(
                "hydraharp",
                PicoQuant_HydraHarp400,
                "1111111",
                max_pending_events=self.PATCHED_MAX_PENDING_EVENTS,
            )
        else:
            self._hydraharp = self._ctx.make_instrument(
                "hydraharp",
                PicoQuant_HydraHarp400,
                "1111111"
            )

        self._library_mock.GetLibraryVersion.return_value = 0
        self._library_mock.OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b"1111111")
        with patch("sys.platform", "linux1"), patch(
                "ctypes.create_string_buffer", return_value=string_buffer
        ):
            self._hydraharp.open()

        self._hydraharp.initialize("T3", "EXTERNAL")

    def tearDown(self):
        # Close instrument instance.
        self._hydraharp.close()
        # Stop QMI context.
        self._ctx.stop()
        self._ctx = None

    def test_realtime_histogram(self):
        """Test that real-time histogram updates even if event filter is used. Low resolution test."""
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_5MHz))
        resolution = ctypes.c_double(25.0)
        sync_period = 1e12 / sync_rate.value
        num_events = 50000
        event_rate = 2.0e9
        # Generate a random set of events.
        events_in = gen_random_events(
            num_events=num_events,
            event_rate=event_rate,
            sync_rate=sync_rate.value,
            resolution=resolution.value,
            channels=[0, 1],
            seed=2345,
        )

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Subscribe to real-time histograms.
        recv = QMI_SignalReceiver()
        self._hydraharp.sig_histogram.subscribe(recv)

        # Configure event filter to reject events on both channels.
        # This should not affect the histograms.
        self._hydraharp.set_event_filter(
            channel_filter={0: EventFilterMode.NO_EVENTS, 1: EventFilterMode.NO_EVENTS}
        )

        # Configure real-time histograms.
        bin_resolution = int(resolution.value)
        histogram_bins = 2**15 // bin_resolution  # Max resolution in T3 mode
        histogram_num_sync = int(
            event_rate // num_events // resolution.value
        )  # Important to be correct!
        self._hydraharp.set_realtime_histogram(
            channels=[0, 1],
            bin_resolution=bin_resolution,
            num_bins=histogram_bins,
            num_sync=histogram_num_sync,
        )

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Expect only SYNC events.
        events_expected = events_in[(events_in["type"] == 64)]
        self.assertTrue(np.all(events == events_expected))

        # Check histograms.
        sync_count = 0
        last_sync = -1
        start_timestamp = 0
        for evt_type, evt_timestamp in events_in:
            if evt_type == 64:
                if sync_count % histogram_num_sync == 0:
                    if sync_count > 0:
                        # Check against published histogram.
                        sig = recv.get_next_signal()
                        (hist,) = sig.args
                        self.assertEqual(hist.start_timestamp, start_timestamp)
                        self.assertEqual(hist.bin_resolution, bin_resolution)
                        self.assertEqual(hist.num_sync, histogram_num_sync)
                        self.assertEqual(hist.channels, [0, 1])
                        self.assertTrue(np.all(hist.histogram_data == expect_histogram))

                    expect_histogram = np.zeros((2, histogram_bins), dtype=np.uint32)
                    start_timestamp = evt_timestamp

                sync_count += 1
                last_sync = int(evt_timestamp)

            elif sync_count > 0:
                # Count event in expected histogram.
                bin_index = min((int(evt_timestamp) - last_sync) // bin_resolution, histogram_bins - 1)
                expect_histogram[evt_type, bin_index] += 1

        # Check that there are no further published histograms.
        self.assertFalse(recv.has_signal_ready())

        self._hydraharp.sig_histogram.unsubscribe(recv)

    def test_realtime_countrate(self):
        """Test the countrate is correct despite of event block"""
        sync_rate = ctypes.c_int(int(self.SYNC_FREQUENCY_5MHz))
        resolution = ctypes.c_double(2.0)
        sync_period = 1e12 / sync_rate.value
        num_events = 50000
        event_rate = 2.0e9
        # Generate a random set of events.
        events_in = gen_random_events(
            num_events=num_events,
            event_rate=event_rate,
            sync_rate=sync_rate.value,
            resolution=resolution.value,
            channels=[0, 1],
            seed=2345,
        )

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in, sync_period, resolution.value)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Subscribe to real-time count rate.
        recv = QMI_SignalReceiver()
        self._hydraharp.sig_countrate.subscribe(recv)

        # Block all events.
        # This should not affect the count rate reports.
        self._hydraharp.set_block_events(True)

        # Configure real-time count rates.
        delta_min = 25000
        delta_max = 75000
        countrate_num_sync = int(event_rate // num_events // resolution.value)  # Important to be correct!

        self._hydraharp.set_realtime_countrate(sync_aperture=(delta_min, delta_max), num_sync=countrate_num_sync)

        # Start the measurement.
        with patch("ctypes.c_double", return_value=resolution), patch(
            "ctypes.c_int", return_value=sync_rate
        ):
            self._hydraharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._hydraharp.stop_measurement()

        # Fetch events.
        events = self._hydraharp.get_events()

        # Expect no events (all events blocked).
        self.assertEqual(len(events), 0)

        # Check count rates.
        sync_count = 0
        last_sync = -1
        start_timestamp = 0
        for evt_type, evt_timestamp in events_in:
            if evt_type == 64:
                if sync_count % countrate_num_sync == 0:
                    if sync_count > 0:
                        # Check against published count rate.
                        sig = recv.get_next_signal()
                        (counts,) = sig.args
                        self.assertEqual(counts.start_timestamp, start_timestamp)
                        self.assertEqual(counts.num_sync, countrate_num_sync)
                        self.assertTrue(np.all(counts.counts == expect_counts))

                    expect_counts = np.zeros(8, dtype=np.uint64)
                    start_timestamp = evt_timestamp

                sync_count += 1
                last_sync = int(evt_timestamp)

            elif sync_count > 0:
                # Check aperture filter.
                if delta_min <= int(evt_timestamp) - last_sync <= delta_max:
                    # Count this event.
                    expect_counts[evt_type] += 1

        # Check that there are no further published count rates.
        self.assertFalse(recv.has_signal_ready())

        self._hydraharp.sig_histogram.unsubscribe(recv)


if __name__ == "__main__":
    unittest.main()
