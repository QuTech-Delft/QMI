#! /usr/bin/env python3

"""Unit test for T2 mode event processing in MultiHarp driver."""

import ctypes
import threading
import unittest
from unittest.mock import patch, PropertyMock

import numpy as np

from qmi.core.exceptions import QMI_RuntimeException
from qmi.core.pubsub import QMI_SignalReceiver
from qmi.instruments.picoquant.support._mhlib_function_signatures import _mhlib_function_signatures
from qmi.instruments.picoquant.support._events import EventDataType, EventFilterMode
from qmi.instruments.picoquant import PicoQuant_MultiHarp150

from tests.patcher import PatcherQmiContext as QMI_Context


def gen_random_events(num_events, event_rate, sync_rate, channels, seed=None):
    rng = np.random.default_rng(seed)

    mean_event_interval = 12.5e9 / event_rate
    delta_times = rng.exponential(scale=mean_event_interval, size=num_events)
    delta_times += 1.0
    delta_times = delta_times.astype(np.uint64)
    event_timestamps = np.cumsum(delta_times)

    mean_sync_interval = 12.5e9 / sync_rate
    sync_timestamps = mean_sync_interval * np.arange(1, num_events + 1)
    sync_timestamps += rng.normal(loc=0.0, scale=12.5, size=num_events)
    sync_timestamps = sync_timestamps.astype(np.uint64)

    events = np.empty(2 * num_events, dtype=EventDataType)
    events[:num_events]["type"] = rng.choice(channels, size=num_events)
    events[:num_events]["timestamp"] = event_timestamps
    events[num_events:]["type"] = 64
    events[num_events:]["timestamp"] = sync_timestamps
    events.sort(order="timestamp")

    return events[:num_events]


def events_to_fifo(events):
    """Convert array of events to the corresponding MultiHarp T2 FIFO data words."""

    # Convert events to array (if necessary).
    evt_array = np.array(events, dtype=EventDataType)

    # Check monotonic timestamps.
    assert np.all(evt_array["timestamp"][1:] >= evt_array["timestamp"][:-1])

    # Convert events to FIFO words. "type" for channel numbers and "timestamp" for time tags
    fifo_words = ((evt_array["type"].astype(np.uint32) << 25)
                  | (evt_array["timestamp"].astype(np.uint32) & 0x1ffffff))

    # Insert overflow records at positions where the MSB part of the timestamp changes.
    tmp_timestamps = np.insert(evt_array["timestamp"], 0, 0)
    (overflow_idx,) = np.where((tmp_timestamps[:-1] >> 25) != (tmp_timestamps[1:] >> 25))
    overflow_counts = (tmp_timestamps[overflow_idx + 1] >> 25) - (tmp_timestamps[overflow_idx] >> 25)
    # have to set special bit (31 from this side) for overflow
    overflow_words = overflow_counts.astype(np.uint32) | ((1 << 31) | (63 << 25))
    fifo_words = np.insert(fifo_words, overflow_idx, overflow_words)

    return fifo_words


def make_patched_read_fifo(fifo_words, done_event):
    """Return a function to be used in place of the actual readFifo() method in the MultiHarp API."""

    fifo_pos = [0]

    def patched_read_fifo(_, fifo_data, nactual):
        n_fifo_words = len(fifo_words)
        pos = fifo_pos[0]
        npos = min(n_fifo_words, pos + 10240)  # read 10240 words = 655360 bits (1.6x < 1048576). Resets timestamp.
        fifo_pos[0] = npos
        for i, val in enumerate(fifo_words[pos:npos]):
            fifo_data[i] = val
        nactual.value = npos - pos
        if (done_event is not None) and (pos == n_fifo_words):
            done_event.set()
        return 0

    return patched_read_fifo


class TestMultiHarpEventFilter(unittest.TestCase):

    # Reduced limit on maximum pending events to make it easier to test.
    PATCHED_MAX_PENDING_EVENTS = 100000
    PATCHED_MAX_EVENTS_PER_CALL = 500000  # Should be less than TTREADMAX

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Generate random event sets to be used in test cases.
        self.events_in_slow = gen_random_events(
            num_events=100000,
            event_rate=0.1e6,
            sync_rate=100.0e3,
            channels=[0, 1],
            seed=2345)

        self.events_in_fast = gen_random_events(
            num_events=500000,
            event_rate=2.0e6,
            sync_rate=100.0e3,
            channels=[0, 1],
            seed=2345)

        self.events_in_4chan = gen_random_events(
            num_events=500000,
            event_rate=1.0e6,
            sync_rate=100.0e3,
            channels=[0, 1, 2, 3],
            seed=1234)

    def setUp(self) -> None:
        patcher = patch('qmi.instruments.picoquant.PicoQuant_MultiHarp150._lib', new_callable=PropertyMock)
        self._library_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

        function_names, _, _ = zip(*_mhlib_function_signatures)
        stripped_names = [name.split('_')[1] for name in function_names]
        self._library_mock.mock_add_spec(stripped_names, spec_set=True)

        # Start QMI context.
        self._ctx = QMI_Context("multiharp_eventfilter_test")

        # Create instrument instance. Limit MAX calls to avoid problems.
        PicoQuant_MultiHarp150.MAX_EVENTS_PER_CALL = self.PATCHED_MAX_EVENTS_PER_CALL
        if self._testMethodName == "test_pending_events_limit":
            self._multiharp: PicoQuant_MultiHarp150 = PicoQuant_MultiHarp150(
                self._ctx, "multiharp", "1111111", max_pending_events=self.PATCHED_MAX_PENDING_EVENTS
            )
        else:
            self._multiharp: PicoQuant_MultiHarp150 = PicoQuant_MultiHarp150(self._ctx, "multiharp", "1111111")

        self._library_mock.GetLibraryVersion.return_value = 0
        self._library_mock.OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'1111111')
        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', return_value=string_buffer):
            self._multiharp.open()

        self._multiharp.initialize("T2", "EXTERNAL_10MHZ")

    def tearDown(self):
        # Close instrument instance.
        self._multiharp.close()
        self._ctx = None

    def test_simple(self):

        # Events to use during this test.
        events_in = [(64, 100),
                     (0, 101),
                     (1, 102),
                     (64, 1000000000),
                     (0,  1000000001),
                     (1,  1000000002),
                     (0,  1010000001),
                     (1,  1010000002),
                     (64, 1020000000)]

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        self._library_mock.StartMeas.return_value = 0
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        events = self._multiharp.get_events()

        # Check events.
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertTrue(np.all(events == np.array(events_in, dtype=EventDataType)))

    def test_channel_filter(self):

        # Generate a random set of events.
        events_in = self.events_in_4chan

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Configure event filter: block events form channels 1 and 2.
        self._multiharp.set_event_filter(channel_filter={1: EventFilterMode.NO_EVENTS,
                                                         2: EventFilterMode.NO_EVENTS})

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        events = self._multiharp.get_events()

        # Expect only events on SYNC and channels 0 and 1.
        events_expected = events_in[(events_in["type"] == 64)
                                    | (events_in["type"] == 0)
                                    | (events_in["type"] == 3)]

        # Check events.
        self.assertTrue(np.all(events == events_expected))

    def test_aperture_filter_events(self):

        # Generate a random set of events.
        events_in = self.events_in_fast

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Configure event filter: setup aperture filtering for channels 0 and 1.
        delta_min = 25000
        delta_max = 75000
        self._multiharp.set_event_filter(channel_filter={0: EventFilterMode.APERTURE,
                                                         1: EventFilterMode.APERTURE},
                                         sync_aperture=(delta_min, delta_max))

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        events = self._multiharp.get_events()

        # Expect only events on SYNC and events that fall in the aperture.
        events_expected = []
        last_sync = -1
        for (evt_type, evt_timestamp) in events_in:
            if evt_type == 64:
                last_sync = evt_timestamp
                events_expected.append((evt_type, evt_timestamp))
            else:
                if (last_sync >= 0) and (delta_min <= evt_timestamp - last_sync <= delta_max):
                    events_expected.append((evt_type, evt_timestamp))

        # Check events.
        self.assertTrue(np.all(events == np.array(events_expected, dtype=EventDataType)))

    def test_aperture_filter_sync(self):

        # Generate a random set of events.
        events_in = self.events_in_slow

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Configure event filter: setup aperture filtering for channels 0 and 1 and SYNC.
        delta_min = 25000
        delta_max = 75000
        self._multiharp.set_event_filter(channel_filter={0: EventFilterMode.APERTURE,
                                                         1: EventFilterMode.APERTURE,
                                                         64: EventFilterMode.APERTURE},
                                         sync_aperture=(delta_min, delta_max))

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        events = self._multiharp.get_events()

        # Expect only events on SYNC and events that fall in the aperture.
        events_expected = []
        last_sync = -1
        last_is_sync = False
        for (evt_type, evt_timestamp) in events_in:
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
        # Test that the `get_events()` function returns at most MAX_EVENTS_PER_CALL events.

        # Generate random events.
        events_per_call = PicoQuant_MultiHarp150.MAX_EVENTS_PER_CALL
        num_events = 2 * events_per_call + 10101
        events_in = np.empty(num_events, dtype=EventDataType)
        events_in["type"] = 0
        events_in["timestamp"] = np.cumsum(np.random.randint(1, 200, len(events_in)))

        # Patch the readFifo() function.
        # The events will be passed to the driver in smaller series.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        # It should return only the first MAX_EVENTS_PER_CALL events.
        events = self._multiharp.get_events()

        # Check events.
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertEqual(len(events), events_per_call)
        self.assertTrue(np.all(events == events_in[:events_per_call]))

        # Now get the next MAX_EVENTS_PER_CALL events.
        (_ts, events) = self._multiharp.get_timestamped_events()
        self.assertEqual(len(events), events_per_call)
        self.assertTrue(np.all(events == events_in[events_per_call:2*events_per_call]))

        # Get the final batch of events.
        events = self._multiharp.get_events()
        self.assertEqual(len(events), 10101)
        self.assertTrue(np.all(events == events_in[2*events_per_call:]))

        # Check no further events.
        events = self._multiharp.get_events()
        self.assertIsInstance(events, np.ndarray)
        self.assertEqual(events.dtype, EventDataType)
        self.assertEqual(len(events), 0)

    def test_pending_events_limit(self):
        # Test that the driver correctly handles overflow of the pending event buffer.

        # Generate a bunch of events that just barely fit into the pending event buffer.
        events_in = np.empty(self.PATCHED_MAX_PENDING_EVENTS - 1, dtype=EventDataType)
        events_in["type"] = 0
        events_in["timestamp"] = np.cumsum(np.random.randint(1, 1000, len(events_in)))

        # Patch the readFifo() function.
        # This fill feed the first part of the events to the driver (not enough to overflow the buffer).
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all queued events are processed.
        done_event.wait()

        # Fetch the events queued so far.
        events = self._multiharp.get_events()

        # Check events.
        self.assertEqual(len(events), len(events_in))
        self.assertTrue(np.all(events == events_in))

        # Generate more events than can fit into the pending event buffer.
        events_in = np.empty(self.PATCHED_MAX_PENDING_EVENTS + 1, dtype=EventDataType)
        events_in["type"] = 0
        events_in["timestamp"] = np.cumsum(np.random.randint(1, 1000, len(events_in)))

        # Repatch the readFifo() function to feed the new events into the running measurement.
        # This should/will cause the pending event buffer to overflow.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)
        done_event.wait()

        # Try to fetch events. This should raise an exception as a result of the overflow.
        with self.assertRaises(QMI_RuntimeException):
            _ = self._multiharp.get_events()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Generate new events to check that a subsequent measurement runs cleanly after overflow.
        events_in = np.empty(self.PATCHED_MAX_PENDING_EVENTS - 1, dtype=EventDataType)
        events_in["type"] = 0
        events_in["timestamp"] = np.cumsum(np.random.randint(1, 1000, len(events_in)))

        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all queued events are processed.
        done_event.wait()

        # Fetch the events queued so far.
        events = self._multiharp.get_events()

        # Check events.
        self.assertEqual(len(events), len(events_in))
        self.assertTrue(np.all(events == events_in))

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Check no further events.
        events = self._multiharp.get_events()
        self.assertEqual(len(events), 0)


class TestMultiHarpRealtime(unittest.TestCase):
    """Test class to test real-time functionalities of event processing. This requires a running QMI context.
    """
    # Reduced limit on maximum pending events to make it easier to test.
    PATCHED_MAX_PENDING_EVENTS = 100000
    PATCHED_MAX_EVENTS_PER_CALL = 500000  # Should be less than TTREADMAX

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Generate random event sets to be used in test cases.
        self.events_in_fast = gen_random_events(
            num_events=500000,
            event_rate=2.0e6,
            sync_rate=100.0e3,
            channels=[0, 1],
            seed=2345)

    def setUp(self) -> None:
        patcher = patch('qmi.instruments.picoquant.PicoQuant_MultiHarp150._lib', new_callable=PropertyMock)
        self._library_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

        function_names, _, _ = zip(*_mhlib_function_signatures)
        stripped_names = [name.split('_')[1] for name in function_names]
        self._library_mock.mock_add_spec(stripped_names, spec_set=True)

        # Start QMI context.
        self._ctx = QMI_Context("multiharp_realtime_test")
        self._ctx.start()

        # Create instrument instance. Limit MAX calls to avoid problems.
        PicoQuant_MultiHarp150.MAX_EVENTS_PER_CALL = self.PATCHED_MAX_EVENTS_PER_CALL
        if self._testMethodName == "test_pending_events_limit":
            self._multiharp = self._ctx.make_instrument(
                "multiharp", PicoQuant_MultiHarp150, "1111111", max_pending_events=self.PATCHED_MAX_PENDING_EVENTS
            )
        else:
            self._multiharp = self._ctx.make_instrument("multiharp", PicoQuant_MultiHarp150, "1111111")

        self._library_mock.GetLibraryVersion.return_value = 0
        self._library_mock.OpenDevice.return_value = 0

        string_buffer = ctypes.create_string_buffer(b'1111111')
        with patch('sys.platform', 'linux1'), patch('ctypes.create_string_buffer', return_value=string_buffer):
            self._multiharp.open()

        self._multiharp.initialize("T2", "EXTERNAL_10MHZ")

    def tearDown(self):
        # Close instrument instance.
        self._multiharp.close()
        # Stop QMI context.
        self._ctx.stop()
        self._ctx = None

    def test_realtime_histogram(self):

        # Generate a random set of events.
        events_in = self.events_in_fast

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Subscribe to real-time histograms.
        recv = QMI_SignalReceiver()
        self._multiharp.sig_histogram.subscribe(recv)

        # Configure event filter to reject events on both channels.
        # This should not affect the histograms.
        self._multiharp.set_event_filter(channel_filter={0: EventFilterMode.NO_EVENTS,
                                                         1: EventFilterMode.NO_EVENTS})

        # Configure real-time histograms.
        bin_resolution = 25
        histogram_bins = 5000
        histogram_num_sync = 100
        self._multiharp.set_realtime_histogram(
            channels=[0, 1],
            bin_resolution=bin_resolution,
            num_bins=histogram_bins,
            num_sync=histogram_num_sync)

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        events = self._multiharp.get_events()

        # Expect only SYNC events.
        events_expected = events_in[(events_in["type"] == 64)]
        self.assertTrue(np.all(events == events_expected))

        # Check histograms.
        sync_count = 0
        last_sync = -1
        start_timestamp = 0
        for (evt_type, evt_timestamp) in events_in:
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

        self._multiharp.sig_histogram.unsubscribe(recv)

    def test_realtime_countrate(self):

        # Generate a random set of events.
        events_in = self.events_in_fast

        # Patch the readFifo() function.
        fifo_words_in = events_to_fifo(events_in)
        done_event = threading.Event()
        self._library_mock.ReadFiFo.side_effect = make_patched_read_fifo(fifo_words_in, done_event)

        # Subscribe to real-time count rate.
        recv = QMI_SignalReceiver()
        self._multiharp.sig_countrate.subscribe(recv)

        # Block all events.
        # This should not affect the count rate reports.
        self._multiharp.set_block_events(True)

        # Configure real-time count rates.
        delta_min = 25000
        delta_max = 75000
        countrate_num_sync = 80
        self._multiharp.set_realtime_countrate(sync_aperture=(delta_min, delta_max), num_sync=countrate_num_sync)

        # Start the measurement.
        self._multiharp.start_measurement(1000)

        # Wait to make sure all events are processed.
        done_event.wait()

        # Stop the measurement.
        self._multiharp.stop_measurement()

        # Fetch events.
        events = self._multiharp.get_events()

        # Expect no events (all events blocked).
        self.assertEqual(len(events), 0)

        # Check count rates.
        sync_count = 0
        last_sync = -1
        start_timestamp = 0
        for (evt_type, evt_timestamp) in events_in:
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

        self._multiharp.sig_histogram.unsubscribe(recv)


if __name__ == "__main__":
    unittest.main()
