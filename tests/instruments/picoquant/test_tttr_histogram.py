import unittest

import numpy as np

from qmi.instruments.picoquant.support._realtime import TttrHistogram


class PicoQuantSomeHarpOpenTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._tttr_histogram = TttrHistogram(0, 12500)  # register channel #0 events

    def tearDown(self) -> None:
        pass

    def test_process(self):
        """Test that process can collect data if sync is present"""
        # Events are returned as an array of event records.
        # Each event record contains two fields:
        # | `type` (uint8): The channel index where the event was recorded, or 64 for a SYNC event.
        # | `timestamp` (uint64): Event timestamp as a multiple of the instrument base resolution.
        channel_index = [0, 1, 64, 0, 1, 64, 0, 1]  # Two hits
        expected_counts = 2
        expected_deltas = [1, 1]
        timestamp = [2134567890, 2134567891, 2134567892, 2134567893, 2134567894, 2134567895, 2134567896, 2134567897]
        expected_previous = timestamp[5]
        events = np.array(list(zip(*[iter(channel_index)], *[iter(timestamp)])),
                 dtype=[("type", "uint8"), ("timestamp", "uint64")])
        self._tttr_histogram.process(events)

        self.assertEqual(sum(self._tttr_histogram.counts), expected_counts)
        self.assertListEqual(list(self._tttr_histogram.deltas), expected_deltas)
        self.assertEqual(self._tttr_histogram.previous, expected_previous)

    def test_process_no_sync_event(self):
        """Test that process does not collect data if no sync is present"""
        channel_index = [0, 1, 0, 1, 0, 1]  # zero syncs
        expected_counts = 0
        timestamp = [2134567890, 2134567891, 2134567892, 2134567893, 2134567894, 2134567895]
        events = np.array(list(zip(*[iter(channel_index)], *[iter(timestamp)])),
                 dtype=[("type", "uint8"), ("timestamp", "uint64")])
        self._tttr_histogram.process(events)

        self.assertEqual(sum(self._tttr_histogram.counts), expected_counts)
        self.assertIsNone(self._tttr_histogram.deltas)
        self.assertIsNone(self._tttr_histogram.previous)

    def test_process_append(self):
        """Test that process appends data at second call"""
        # Events are returned as an array of event records.
        # Each event record contains two fields:
        # | `type` (uint8): The channel index where the event was recorded, or 64 for a SYNC event.
        # | `timestamp` (uint64): Event timestamp as a multiple of the instrument base resolution.
        channel_index = [0, 1, 64, 0, 1, 64, 0, 1]  # Two hits for first, three for second
        expected_counts = 5
        expected_deltas = [3, 1, 1]
        timestamp = [2134567890, 2134567891, 2134567892, 2134567893, 2134567894, 2134567895, 2134567896, 2134567897]
        events = np.array(list(zip(*[iter(channel_index)], *[iter(timestamp)])),
                 dtype=[("type", "uint8"), ("timestamp", "uint64")])
        self._tttr_histogram.process(events)

        timestamp2 = [2134567898, 2134567899, 2134567900, 2134567901, 2134567902, 2134567903, 2134567904, 2134567905]
        expected_previous = timestamp2[5]
        events = np.array(list(zip(*[iter(channel_index)], *[iter(timestamp2)])),
                 dtype=[("type", "uint8"), ("timestamp", "uint64")])
        self._tttr_histogram.process(events)
        self.assertEqual(sum(self._tttr_histogram.counts), expected_counts)
        self.assertListEqual(list(self._tttr_histogram.deltas), expected_deltas)
        self.assertEqual(self._tttr_histogram.previous, expected_previous)

    def test_reset(self):
        """Test that reset indeed nullifies values."""
        channel_index = [0, 1, 64, 0, 1, 64, 0, 1]  # Two hits
        expected_counts = 0
        timestamp = [2134567890, 2134567891, 2134567892, 2134567893, 2134567894, 2134567895, 2134567896, 2134567897]
        events = np.array(list(zip(*[iter(channel_index)], *[iter(timestamp)])),
                 dtype=[("type", "uint8"), ("timestamp", "uint64")])
        self._tttr_histogram.process(events)

        self._tttr_histogram.reset()
        self.assertEqual(sum(self._tttr_histogram.counts), expected_counts)
        self.assertIsNone(self._tttr_histogram.deltas)


if __name__ == '__main__':
    unittest.main()
