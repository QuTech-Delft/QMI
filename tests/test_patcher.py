"""Unit tests for the `PatcherQmiContext` test helper."""
import threading
import unittest
from unittest.mock import patch

from qmi.core.context import QMI_Context
from tests.patcher import PatcherQmiContext


class TestPatcherQmiContext(unittest.TestCase):

    def test_start_stop_leaves_no_extra_threads(self):
        """A normal start()/stop() cycle must not leave any background thread running."""
        threads_before = set(threading.enumerate())

        patcher = PatcherQmiContext()
        patcher.start("patcher_test_context")
        patcher.stop()

        self.assertEqual(threads_before, set(threading.enumerate()))

    def test_stop_without_start_is_a_noop(self):
        """Calling stop() without a preceding start() must not raise and must not start any thread."""
        threads_before = set(threading.enumerate())

        patcher = PatcherQmiContext()
        patcher.stop()

        self.assertEqual(threads_before, set(threading.enumerate()))

    def test_stop_after_failed_start_leaves_no_extra_threads(self):
        """If `QMI_Context.start()` fails, the "$context" RPC thread created by `QMI_Context.__init__()`
        must still be cleaned up by stop()."""
        threads_before = set(threading.enumerate())

        patcher = PatcherQmiContext()
        with patch.object(QMI_Context, "start", side_effect=RuntimeError("Simulated start failure")):
            with self.assertRaises(RuntimeError):
                patcher.start("patcher_test_context")

        patcher.stop()

        self.assertEqual(threads_before, set(threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
