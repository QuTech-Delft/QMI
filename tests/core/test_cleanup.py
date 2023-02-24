#! /usr/bin/env python3

"""Test cleanup behaviour of QMI framework."""

import logging
import unittest
import warnings
import weakref
from collections import namedtuple

import gc
import time

import qmi
import qmi.core.exceptions
from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.task import QMI_Task

# Global variables to inspect the fate of RPC objects.
_instrument_ref = [None]
_instrument_open = [False]
_task_ref = [None]
_task_running = [False]


class SimpleTestInstrument(QMI_Instrument):
    """Dummy instrument used for testing."""

    def __init__(self, context: QMI_Context, name: str) -> None:
        super().__init__(context, name)
        _instrument_ref[0] = weakref.ref(self)

    @rpc_method
    def open(self) -> None:
        super().open()
        _instrument_open[0] = True

    @rpc_method
    def close(self) -> None:
        super().close()
        _instrument_open[0] = False

    @rpc_method
    def hello(self) -> str:
        return "greetings"


class SimpleTestTask(QMI_Task):
    """Dummy task used for testing."""

    Settings = namedtuple("Settings", "x")

    def __init__(self, task_runner, name):
        super().__init__(task_runner, name)
        self.settings = SimpleTestTask.Settings(x=14)
        _task_ref[0] = weakref.ref(self)

    def run(self):
        """Run this task."""

        _task_running[0] = True
        try:

            i = 0
            while True:
                self.sleep(0.2)
                i += 1

        finally:
            _task_running[0] = False


class TestCleanup(unittest.TestCase):

    def setUp(self):
        # Suppress logging.
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)

    def tearDown(self):
        logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)

    def test_clean_stop(self):
        """Test shutdown with proper cleanup of all created objects."""

        # Start QMI.
        qmi.start("test_context")

        # Create an instrument as RPC object.
        inst = qmi.make_instrument("inst", SimpleTestInstrument)
        inst.open()
        inst.hello()

        # Create a task and start it.
        simple_task = qmi.make_task("simple_task", SimpleTestTask)
        simple_task.start()

        # Wait a bit.
        time.sleep(1.0)

        # Stop task and check that it stopped.
        self.assertTrue(_task_running[0])
        simple_task.stop()
        simple_task.join()
        self.assertFalse(_task_running[0])

        # Remove task and check that the object is destructed.
        self.assertIsInstance(_task_ref[0](), SimpleTestTask)
        qmi.context().remove_rpc_object(simple_task)
        gc.collect()
        self.assertIsNone(_task_ref[0]())

        # Close instrument and check that it got closed.
        inst.hello()
        self.assertTrue(_instrument_open[0])
        inst.close()
        self.assertFalse(_instrument_open[0])

        # Remove instrument and check that the object is destructed.
        self.assertIsInstance(_instrument_ref[0](), SimpleTestInstrument)
        qmi.context().remove_rpc_object(inst)
        gc.collect()
        self.assertIsNone(_instrument_ref[0]())

        # Stop QMI.
        qmi.stop()

    def test_fail_restart(self):
        """Test that a QMI context can not be started a second time."""

        # Create context and start it.
        ctx = QMI_Context("ctx")
        ctx.start()

        # Stop context.
        ctx.stop()

        # Try to restart the context. This should fail.
        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            ctx.start()

    def test_unclean_stop(self):
        """Test shutdown without proper cleanup."""

        # Start QMI.
        qmi.start("test_context")

        # Create an instrument as RPC object.
        inst = qmi.make_instrument("inst", SimpleTestInstrument)
        inst.open()
        inst.hello()

        # Create a task and start it.
        simple_task = qmi.make_task("simple_task", SimpleTestTask)
        simple_task.start()

        # Wait a bit.
        time.sleep(1.0)

        # Check references to instrument and task.
        self.assertIsInstance(_instrument_ref[0](), SimpleTestInstrument)
        self.assertIsInstance(_task_ref[0](), SimpleTestTask)
        self.assertTrue(_task_running[0])

        # Stop QMI. This should cleanly remove the remaining objects.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            qmi.stop()

        # Check that remaining objects are destructed.
        gc.collect()
        self.assertIsNone(_instrument_ref[0]())
        self.assertIsNone(_task_ref[0]())
        self.assertFalse(_task_running[0])

    def test_stop_handler(self):
        """Test that stop handlers are correctly called."""

        cb1_count = 0
        cb2_count = 0

        def cb1():
            nonlocal cb1_count
            cb1_count += 1

        def cb2():
            nonlocal cb2_count
            cb2_count += 1

        # Start QMI.
        qmi.start("test_context")

        # Setup stop handlers.
        qmi.context().register_stop_handler(cb1)
        qmi.context().register_stop_handler(cb2)

        self.assertEqual(cb1_count, 0)
        self.assertEqual(cb2_count, 0)

        # Stop QMI. This should trigger calls to the stop handlers.
        qmi.stop()

        # Check that the stop handlers were called.
        self.assertEqual(cb1_count, 1)
        self.assertEqual(cb2_count, 1)


if __name__ == "__main__":
    unittest.main()
