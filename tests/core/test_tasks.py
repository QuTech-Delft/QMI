#! /usr/bin/env python3

"""Test QMI task functionality."""

import logging
import random
import threading
import time
import unittest
from collections import namedtuple
from unittest.mock import sentinel

import qmi
import qmi.core.exceptions
from qmi.utils.context_managers import start_stop, start_stop_join
from qmi.core.pubsub import QMI_Signal, QMI_SignalReceiver
from qmi.core.rpc import QMI_RpcObject, rpc_method
from qmi.core.task import (
    QMI_Task,
    QMI_LoopTask,
    QMI_LoopTaskMissedLoopPolicy,
    QMI_TaskRunner,
)

from tests.patcher import PatcherQmiContext


class CustomTaskRunner(QMI_TaskRunner):
    @rpc_method
    def get_custom_taskrunner_attr(self):
        return sentinel.custom_taskrunner_attr


class SimpleTestTask(QMI_Task):
    """A simple test task.

    It waits for a configurable time, then emits a signal and stops.
    Alternatively, the task can be configured to raise an exception during initialization or while running.
    """

    Settings = namedtuple("Settings", "message value")

    my_signal = QMI_Signal([int])

    def __init__(
        self,
        task_runner,
        name,
        raise_exception_in_init,
        raise_exception_in_run,
        duration,
        value,
    ):
        super().__init__(task_runner, name)

        self.settings = SimpleTestTask.Settings(
            "Hello, world from within SimpleTestTask!", value
        )
        self.raise_exception_in_run = raise_exception_in_run
        self.duration = duration

        if raise_exception_in_init:
            raise ValueError(
                "This error originates from within SimpleTestTask's __init__() method."
            )

    def run(self):
        """Run this task."""

        if self.raise_exception_in_run:
            raise ValueError(
                "This error originates from within SimpleTestTask's run() method."
            )

        run_until = time.monotonic() + self.duration
        while time.monotonic() < run_until:
            self.update_settings()
            self.sleep(0.100)  # Wait for 100 ms.

        self.status = self.settings.value
        self.my_signal.publish(self.settings.value)


class SlowTestTask(SimpleTestTask):
    """A slow version of simple test task.

    It waits for a configurable time, then emits a signal and stops.
    The difference to the SimpleTestTask is that the settings update rate is much slower.
    """

    Settings = namedtuple("Settings", "message value")

    my_signal = QMI_Signal([int])

    def __init__(self, task_runner, name, duration, value, event):
        super().__init__(task_runner, name, False, False, duration, value)
        self.event = event

    def run(self):
        """Run this task."""

        run_until = time.monotonic() + self.duration
        while time.monotonic() < run_until:
            if self.event.is_set():
                self.update_settings()
                self.event.clear()

            self.sleep(0.1)

        self.status = self.settings.value
        self.my_signal.publish(self.settings.value)


class TestPublisher(QMI_RpcObject):
    """A simple RPC object which can publish a signal."""

    sig_test = QMI_Signal([int])

    @rpc_method
    def send_signal(self, value):
        self.sig_test.publish(value)


class SignalWaitingTask(QMI_Task):
    """A test task that waits for signals.

    This task subscribes to signals from another object.
    The task waits for a signal, then stops or continues depending on
    the contents of the signal.
    """

    def __init__(self, task_runner, name, wait_timeout, context_id):
        super().__init__(task_runner, name)
        self.wait_timeout = wait_timeout
        self.receiver = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{context_id}.test_publisher")
        publisher_proxy.sig_test.subscribe(self.receiver)
        self.status = None

    def run(self):
        while True:
            try:
                signal = self.receiver.get_next_signal(timeout=self.wait_timeout)
            except qmi.core.exceptions.QMI_TaskStopException:
                # This happens if the task is stopped while waiting for a signal.
                self.status = -100
                raise
            except qmi.core.exceptions.QMI_TimeoutException:
                # This happens if no signal arrives within `wait_timeout`.
                self.status = -101
                raise
            assert signal.signal_name == "sig_test"
            (value,) = signal.args
            if value == -1:
                break
            self.status = value


class LoopTestTask(QMI_LoopTask):
    """A loop test task.

    This task overrides the standard QMI_LoopTask methods and tests them. It also tests that the signals get
    published when changed, and that a loop time-outing its iteration period are handled as expected from the attribute
    set for `QMI_LoopTaskMissedLoopPolicy`.
    """

    Status = namedtuple("Status", "message value")
    Settings = namedtuple("Settings", "message value")

    my_signal = QMI_Signal([int])

    def __init__(
        self,
        task_runner,
        name,
        status_value,
        loop_period,
        policy,
        nr_of_loops,
        increase_loop,
        error=None,
    ):
        super().__init__(task_runner, name, loop_period, policy)
        # Initialize settings and status with some (default) values
        self.settings = LoopTestTask.Settings("Standard setting for LoopTestTask", 1)
        self.status = LoopTestTask.Status("LoopTestTask loop iteration status is", status_value)
        self._status_value = status_value
        self._nr_of_loops = nr_of_loops
        self._increase_loop = increase_loop
        self._error = error
        self._current_loop = 0

    def loop_prepare(self):
        # Initial settings and status value publishing
        self.sig_settings_updated.publish(self.settings.value)
        self.sig_status_updated.publish(self.status.value)
        # sleep until next monotonic period start. Makes sure we won't get random missed loops depending on which
        # monotonic moment we start our looping
        time_to_sleep = self._loop_period - (time.monotonic() % self._loop_period)
        if time_to_sleep > 0:
            self.sleep(time_to_sleep)

    def loop_iteration(self):
        # This follows settings update and processing step if settings are changed. Status is updated after this.
        self._current_loop += 1  # increase loop value
        # do some kind of "work"
        self._status_value += 1
        self.status = LoopTestTask.Status("LoopTestTask loop iteration status is", self._status_value)
        self.settings = LoopTestTask.Settings("Standard setting for LoopTestTask", self._current_loop)
        if self._current_loop >= self._nr_of_loops:
            time.sleep(self._loop_period)  # Make sure the latest loop finishes before stopping
            self._task_runner.stop()
            return

        if self._increase_loop:
            self._status_value += 1  # increase status value
            time.sleep(self._loop_period / 2.0)

        if self._error:
            time.sleep(self._loop_period * 1.1)  # Cause time-out in looping
            if self._error == "SKIP":
                self._current_loop += 1  # skip a loop

    def loop_finalize(self):
        # Clean up at the end of the loop task and set status and settings back to default (1)
        time.sleep(self._loop_period / 2.0)
        self.status = LoopTestTask.Status("LoopTestTask loop iteration status is", 1)
        self.settings = LoopTestTask.Settings("Standard setting for LoopTestTask", 1)
        self._task_runner.set_settings(self.settings)

    def update_status(self):
        # Try to obtain new status.
        if self._status_fifo:
            self.status = self._status_fifo.pop()
            return True

        return False

    def process_new_settings(self) -> None:
        # Update the settings
        self.settings = LoopTestTask.Settings(
            "Standard setting for LoopTestTask", self._current_loop
        )

    def publish_signals(self):
        # Publish something
        self.my_signal.publish(self.settings.value + self.status.value)
        self.sig_settings_updated.publish(self.settings.value)
        self.sig_status_updated.publish(self.status.value)


class TestQMITaskContextManager(unittest.TestCase):
    """Test the various context managers."""
    def test_with_context_manager(self):
        """Test the 'with' context manager run as QMI_TaskRunner."""
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)
        logging.getLogger("qmi.core.rpc").setLevel(logging.ERROR)
        qmi.start("test-taskrunner")
        with qmi.make_task(
            "taskrunner", SimpleTestTask, False, False, 1.0, 2.0
        ) as task:
            task.get_status()

        qmi.stop()
        logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)
        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_start_stop_context_manager(self):
        """Test the 'start_stop' context manager run as QMI_TaskRunner."""
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)
        logging.getLogger("qmi.core.rpc").setLevel(logging.ERROR)
        qmi.start("test-taskrunner")
        task: QMI_TaskRunner = qmi.make_task(
            "taskrunner", SimpleTestTask, False, False, 1.0, 2.0
        )
        with start_stop(task):
            task.get_status()

        task.join()
        qmi.stop()
        logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)
        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_start_stop_join_context_manager(self):
        """Test the 'start_stop_join' context manager run as QMI_TaskRunner."""
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)
        logging.getLogger("qmi.core.rpc").setLevel(logging.ERROR)
        qmi.start("test-taskrunner2")
        task: QMI_TaskRunner = qmi.make_task(
            "taskrunner2", SimpleTestTask, False, False, 1.0, 2.0
        )
        with start_stop_join(task):
            task.get_status()

        qmi.stop()
        logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)
        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)


class TestQMITasks(unittest.TestCase):
    def setUp(self):
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)
        logging.getLogger("qmi.core.rpc").setLevel(logging.ERROR)
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        self.qmi_patcher = PatcherQmiContext()
        self.qmi_patcher.start(self._ctx_qmi_id)

    def tearDown(self):
        self.qmi_patcher.stop()
        logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)
        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_context_manager(self):
        """Test the 'with' context manager does the same as start_stop_join context manager."""
        with qmi.make_task(
                "simple_task_init",
                SimpleTestTask,
                raise_exception_in_init=False,
                raise_exception_in_run=False,
                duration=1.0,
                value=5,
        ) as simple_task:
            self.assertTrue(simple_task.is_running())

        self.assertFalse(simple_task.is_running())

    def test_exception_double_start(self):
        """Test QMI_UsageException is raised if the task is started twice."""
        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            task_proxy = qmi.make_task(
                "simple_task_init",
                SimpleTestTask,
                raise_exception_in_init=False,
                raise_exception_in_run=False,
                duration=1.0,
                value=5,
            )
            task_proxy.start()
            task_proxy.start()

        # Remove task proxy and re-run within context manager.
        qmi.context().remove_rpc_object(task_proxy)

        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            with qmi.make_task(
                "simple_task_init",
                SimpleTestTask,
                raise_exception_in_init=False,
                raise_exception_in_run=False,
                duration=1.0,
                value=5,
            ) as task_proxy:
                task_proxy.start()

    def test_exception_duplicate_task(self):
        """Test QMI_UsageException is raised if the task is created twice."""
        task_proxy = qmi.make_task(
            "simple_task_init",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=1.0,
            value=5,
        )

        with self.assertRaises(qmi.core.exceptions.QMI_DuplicateNameException):
            with qmi.make_task(
                "simple_task_init",
                SimpleTestTask,
                raise_exception_in_init=False,
                raise_exception_in_run=False,
                duration=1.0,
                value=5,
            ) as task_proxy:
                pass

    def test_exception_during_init(self):
        """Test QMI_TaskInitException is raised."""
        with self.assertRaises(qmi.core.exceptions.QMI_TaskInitException):
            qmi.make_task(
                "simple_task_init",
                SimpleTestTask,
                raise_exception_in_init=True,
                raise_exception_in_run=False,
                duration=1.0,
                value=5,
            )

    def test_exception_during_run(self):
        """Test QMI_TaskRunException is raised."""
        task_proxy = qmi.make_task(
            "simple_task_run",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=True,
            duration=1.0,
            value=6,
        )
        task_proxy.start()
        time.sleep(2.0)
        with self.assertRaises(qmi.core.exceptions.QMI_TaskRunException):
            task_proxy.join()

    def test_exception_during_context_run(self):
        """Test QMI_TaskRunException is raised within context."""
        with self.assertRaises(qmi.core.exceptions.QMI_TaskRunException):
            with qmi.make_task(
                "simple_task_run",
                SimpleTestTask,
                raise_exception_in_init=False,
                raise_exception_in_run=True,
                duration=1.0,
                value=6,
            ) as task_proxy:
                time.sleep(2.0)

        self.assertFalse(task_proxy.is_running())

    def test_run_to_completion(self):
        """Test task stops running after completion of the task."""
        task_proxy = qmi.make_task(
            "simple_task_complete",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=1.0,
            value=7,
        )
        self.assertFalse(task_proxy.is_running())
        task_proxy.start()
        self.assertTrue(task_proxy.is_running())
        time.sleep(2.0)
        self.assertFalse(task_proxy.is_running())
        t1 = time.monotonic()
        task_proxy.join()
        t2 = time.monotonic()
        self.assertLess(t2 - t1, 0.1)
        status = task_proxy.get_status()
        self.assertEqual(status, 7)

    def test_run_to_stopped(self):
        """Test task stops running if it is called to stop."""
        task_proxy = qmi.make_task(
            "simple_task_stopped",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=2.0,
            value=8,
        )
        task_proxy.start()
        time.sleep(0.5)
        self.assertTrue(task_proxy.is_running())
        t1 = time.monotonic()
        task_proxy.stop()
        t2 = time.monotonic()
        self.assertLess(t2 - t1, 0.1)
        time.sleep(0.1)
        self.assertFalse(task_proxy.is_running())
        t1 = time.monotonic()
        task_proxy.join()
        t2 = time.monotonic()
        self.assertLess(t2 - t1, 0.1)
        status = task_proxy.get_status()
        self.assertIsNone(status)

    def test_context_run_to_completion(self):
        """Test task stops running after completion of the task within context manager."""
        with qmi.make_task(
            "simple_task_complete",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=1.0,
            value=7,
        ) as task_proxy:
            self.assertTrue(task_proxy.is_running())
            time.sleep(2.0)
            self.assertFalse(task_proxy.is_running())
            t1 = time.monotonic()

        t2 = time.monotonic()
        self.assertLess(t2 - t1, 0.1)
        status = task_proxy.get_status()
        self.assertEqual(status, 7)

    def test_context_run_to_stopped(self):
        """Test task stops running within context manager if it is called to stop."""
        with qmi.make_task(
            "simple_task_stopped",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=2.0,
            value=8,
        ) as task_proxy:
            time.sleep(0.5)
            self.assertTrue(task_proxy.is_running())
            t1 = time.monotonic()
            task_proxy.stop()
            t2 = time.monotonic()
            self.assertLess(t2 - t1, 0.1)
            time.sleep(0.1)
            self.assertFalse(task_proxy.is_running())
            t1 = time.monotonic()

        t2 = time.monotonic()
        self.assertLess(t2 - t1, 0.1)
        status = task_proxy.get_status()
        self.assertIsNone(status)

    def test_update_settings(self):
        """Test updating task settings."""
        task_proxy = qmi.make_task(
            "simple_task_update",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=2.0,
            value=9,
        )
        recv = QMI_SignalReceiver()
        task_proxy.sig_settings_updated.subscribe(recv)
        task_proxy.start()
        time.sleep(0.5)
        old_settings = task_proxy.get_settings()
        new_settings = SimpleTestTask.Settings("hello", 101)
        task_proxy.set_settings(new_settings)
        time.sleep(0.5)
        active_settings = task_proxy.get_settings()
        task_proxy.join()
        status = task_proxy.get_status()
        settings_received = recv.get_next_signal().args[0]

        self.assertNotEqual(old_settings, active_settings)
        self.assertEqual(active_settings, new_settings)
        self.assertEqual(status, 101)
        self.assertEqual(settings_received, new_settings)

    def test_update_settings_with_context(self):
        """Test updating task settings within a context manager."""
        recv = QMI_SignalReceiver()
        with qmi.make_task(
            "simple_task_update",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=2.0,
            value=9,
        ) as task_proxy:
            task_proxy.sig_settings_updated.subscribe(recv)
            time.sleep(0.5)
            old_settings = task_proxy.get_settings()
            new_settings = SimpleTestTask.Settings("hello", 101)
            task_proxy.set_settings(new_settings)
            time.sleep(0.5)
            active_settings = task_proxy.get_settings()
            task_proxy.join()
            status = task_proxy.get_status()
            settings_received = recv.get_next_signal().args[0]

        self.assertNotEqual(old_settings, active_settings)
        self.assertEqual(active_settings, new_settings)
        self.assertEqual(status, 101)
        self.assertEqual(settings_received, new_settings)

    def test_get_pending_settings(self):
        """A more complex test to obtain pending settings for slow cycle tasks, where the new settings are not updated
        frequently."""
        event = threading.Event()
        task_proxy = qmi.make_task(
            "slow_task", SlowTestTask, duration=2.0, value=9, event=event
        )
        recv = QMI_SignalReceiver()
        task_proxy.sig_settings_updated.subscribe(recv)
        task_proxy.start()
        pre_pending_settings = task_proxy.get_pending_settings()
        new_settings = SimpleTestTask.Settings("hello", 101)
        # When setting new settings with QMI_TaskRunner.set_settings the new settings are put into a FiFo queue.
        task_proxy.set_settings(new_settings)
        # The settings won't be updated in the proxy before update_settings() has been called in a LoopTask instance.
        # This triggers obtaining the next item in the FiFo queue.
        # In the run() of SlowTestTask class, update_settings() called only after the event is set.
        pending_settings = task_proxy.get_pending_settings()
        event.set()
        time.sleep(0.4)
        self.assertIsNone(task_proxy.get_pending_settings())
        event.set()
        time.sleep(0.4)
        post_pending_settings = task_proxy.get_pending_settings()
        task_proxy.join()

        self.assertIsNone(pre_pending_settings)
        self.assertEqual(pending_settings, new_settings)
        self.assertIsNone(post_pending_settings)

    def test_get_pending_settings_with_context(self):
        """A more complex test to obtain pending settings for slow cycle tasks, where the new settings are not updated
        frequently, within a context manager."""
        event = threading.Event()
        recv = QMI_SignalReceiver()
        with qmi.make_task(
            "slow_task", SlowTestTask, duration=2.0, value=9, event=event
        ) as task_proxy:
            task_proxy.sig_settings_updated.subscribe(recv)
            pre_pending_settings = task_proxy.get_pending_settings()
            new_settings = SimpleTestTask.Settings("hello", 101)
            # When setting new settings with QMI_TaskRunner.set_settings the new settings are put into a FiFo queue.
            task_proxy.set_settings(new_settings)
            # The settings won't be updated in the proxy before update_settings() has been called in a LoopTask
            # instance. This triggers obtaining the next item in the FiFo queue.
            # In the run() of SlowTestTask class, update_settings() called only after the event is set.
            pending_settings = task_proxy.get_pending_settings()
            event.set()
            time.sleep(0.4)
            self.assertIsNone(task_proxy.get_pending_settings())
            event.set()
            time.sleep(0.4)
            post_pending_settings = task_proxy.get_pending_settings()

        self.assertIsNone(pre_pending_settings)
        self.assertEqual(pending_settings, new_settings)
        self.assertIsNone(post_pending_settings)

    def test_signals(self):
        """Test the published signal in task gets added to the queue and received correctly."""
        task_proxy = qmi.make_task(
            "simple_task_signals",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=1.0,
            value=10,
        )
        recv = QMI_SignalReceiver()
        task_proxy.my_signal.subscribe(recv)
        task_proxy.start()
        time.sleep(0.5)
        task_proxy.join()
        self.assertTrue(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 1)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self._ctx_qmi_id)
        self.assertEqual(sig.publisher_name, "simple_task_signals")
        self.assertEqual(sig.signal_name, "my_signal")
        self.assertEqual(sig.args, (10,))

    def test_stop_before_start(self):
        """Test that just making a task doesn't start it, but also does not fail if `stop()` or `join()` is called."""
        task_proxy = qmi.make_task(
            "simple_task_stop",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=2.0,
            value=11,
        )
        time.sleep(0.5)
        self.assertFalse(task_proxy.is_running())
        task_proxy.stop()
        self.assertFalse(task_proxy.is_running())
        t1 = time.monotonic()
        task_proxy.join()
        t2 = time.monotonic()
        self.assertLess(t2 - t1, 0.1)
        status = task_proxy.get_status()
        self.assertIsNone(status)

    def test_receive_signals(self):
        """Test that signals are received one cycle (0.1s) after sending, and that the task stops at -1."""
        publisher_proxy = qmi.context().make_rpc_object("test_publisher", TestPublisher)
        task_proxy = qmi.make_task(
            "receiving_task",
            SignalWaitingTask,
            wait_timeout=None,
            context_id=self._ctx_qmi_id,
        )
        task_proxy.start()
        time.sleep(0.1)
        status = task_proxy.get_status()
        self.assertIsNone(status)
        publisher_proxy.send_signal(8)
        time.sleep(0.1)
        status = task_proxy.get_status()
        self.assertEqual(status, 8)
        publisher_proxy.send_signal(9)
        time.sleep(0.1)
        status = task_proxy.get_status()
        self.assertEqual(status, 9)
        publisher_proxy.send_signal(-1)
        time.sleep(0.1)
        self.assertFalse(task_proxy.is_running())
        task_proxy.join()

    def test_receive_signals_in_context(self):
        """Test that signals are received one cycle (0.1s) after sending within a context manager."""
        publisher_proxy = qmi.context().make_rpc_object("test_publisher", TestPublisher)
        with qmi.make_task(
            "receiving_task",
            SignalWaitingTask,
            wait_timeout=None,
            context_id=self._ctx_qmi_id,
        ) as task_proxy:
            self.assertTrue(task_proxy.is_running())
            time.sleep(0.1)
            status = task_proxy.get_status()
            self.assertIsNone(status)
            publisher_proxy.send_signal(8)
            time.sleep(0.1)
            status = task_proxy.get_status()
            self.assertEqual(status, 8)
            publisher_proxy.send_signal(9)
            time.sleep(0.1)
            status = task_proxy.get_status()
            self.assertEqual(status, 9)
            publisher_proxy.send_signal(-1)
            time.sleep(0.1)
            self.assertFalse(task_proxy.is_running())

    def test_timeout_while_waiting_for_signal(self):
        """Test when a wait times out, it raises an exception."""
        qmi.context().make_rpc_object("test_publisher", TestPublisher)
        task_proxy = qmi.make_task(
            "receiving_task",
            SignalWaitingTask,
            wait_timeout=1.0,
            context_id=self._ctx_qmi_id,
        )
        task_proxy.start()
        time.sleep(0.1)
        self.assertTrue(task_proxy.is_running())
        time.sleep(1.4)
        self.assertFalse(task_proxy.is_running())
        status = task_proxy.get_status()
        self.assertEqual(status, -101)  # indicates task got QMI_TimeoutException
        # task will have raised a QMI_TimeoutException while waiting for a signal
        with self.assertRaises(qmi.core.exceptions.QMI_TaskRunException):
            task_proxy.join()

    def test_timeout_while_waiting_for_signal_in_context(self):
        """Test when a wait times out, it raises an exception within a context manager."""
        qmi.context().make_rpc_object("test_publisher", TestPublisher)
        # task will have raised a QMI_TimeoutException while waiting for a signal
        with self.assertRaises(qmi.core.exceptions.QMI_TaskRunException):
            with qmi.make_task(
                "receiving_task",
                SignalWaitingTask,
                wait_timeout=1.0,
                context_id=self._ctx_qmi_id,
            ) as task_proxy:
                time.sleep(0.1)
                self.assertTrue(task_proxy.is_running())
                time.sleep(1.4)
                self.assertFalse(task_proxy.is_running())
                status = task_proxy.get_status()
                self.assertEqual(status, -101)  # indicates task got QMI_TimeoutException

    def test_stop_while_waiting_for_signal(self):
        qmi.context().make_rpc_object("test_publisher", TestPublisher)
        task_proxy = qmi.make_task(
            "receiving_task",
            SignalWaitingTask,
            wait_timeout=30.0,
            context_id=self._ctx_qmi_id,
        )
        task_proxy.start()
        time.sleep(0.1)
        self.assertTrue(task_proxy.is_running())
        task_proxy.stop()
        time.sleep(0.1)
        self.assertFalse(task_proxy.is_running())
        status = task_proxy.get_status()
        self.assertEqual(status, -100)  # indicates task got QMI_TaskStopException
        task_proxy.join()

    def test_run_to_loop_finish(self):
        """Test and assert that loop runs normally from start to finish if there are no glitches."""
        # Arrange
        status_signals_received = []
        settings_signals_received = []
        nr_of_loops = 3
        increase_loop = False
        initial_status_value = -1
        loop_period = 0.2
        policy = QMI_LoopTaskMissedLoopPolicy.IMMEDIATE
        status_signals_expected = list(range(initial_status_value, nr_of_loops, 1)) + [1]
        settings_signals_expected = [1] + list(range(1, 4))

        task_proxy = qmi.make_task(
            "loop_task_finish",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
        )
        receiver = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task_finish")
        publisher_proxy.sig_settings_updated.subscribe(receiver)

        # Act
        task_proxy.start()
        # Test that prepare has done its job
        status_signals_received.append(task_proxy.get_status().value)
        settings_signals_received.append(receiver.get_next_signal(timeout=loop_period).args[-1])
        # LoopTestTask does 3x 1 second loops --> should be finished after 3 seconds
        for n in range(nr_of_loops):
            while (status := task_proxy.get_status().value) == status_signals_received[-1]:
                pass  # Do as fast as possible

            status_signals_received.append(status)
            if not receiver.has_signal_ready():
                time.sleep(loop_period - (time.monotonic() % loop_period))  # synchronize

            # Test that the status changes at the end of each loop, after receiver signal increments
            settings_signals_received.append(receiver.get_next_signal(timeout=loop_period).args[-1])

        # Test that finalize_loop sets status back to 1
        time.sleep(loop_period)
        status_signals_received.append(task_proxy.get_status().value)
        task_proxy.join()  # Give time to finalize
        # Assert
        self.assertListEqual(status_signals_expected, status_signals_received)
        self.assertListEqual(settings_signals_expected, settings_signals_received)
        self.assertFalse(task_proxy.is_running())

    def test_run_to_loop_finish_in_context(self):
        """Test and assert that loop runs normally within context manager if there are no glitches."""
        # Arrange
        status_signals_received = []
        settings_signals_received = []
        nr_of_loops = 3
        increase_loop = False
        initial_status_value = -1
        loop_period = 0.2
        policy = QMI_LoopTaskMissedLoopPolicy.IMMEDIATE
        status_signals_expected = list(range(initial_status_value + 1, nr_of_loops, 1)) + [1]
        settings_signals_expected = list(range(1, 4))
        settings_receiver = QMI_SignalReceiver()
        status_receiver = QMI_SignalReceiver()

        with qmi.make_task(
            "loop_task_finish_with",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
        ) as task_proxy:
            # Act
            publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task_finish_with")
            publisher_proxy.sig_status_updated.subscribe(status_receiver)
            publisher_proxy.sig_settings_updated.subscribe(settings_receiver)
            # Test that prepare has done its job
            status_init = task_proxy.get_status().value
            # LoopTestTask does 3x 1 second loops --> should be finished after 3 seconds
            for n in range(nr_of_loops):
                # Test that the status changes at the end of each loop, after receiver signal increments
                while not status_receiver.has_signal_ready():
                    time.sleep(loop_period - (time.monotonic() % loop_period))  # Synchronize

                status = status_receiver.get_next_signal(timeout=loop_period).args[-1]
                if status == status_init:
                    time.sleep(loop_period - (time.monotonic() % loop_period))  # Synchronize
                    status = status_receiver.get_next_signal(timeout=loop_period).args[-1]

                while not settings_receiver.has_signal_ready():
                    time.sleep(loop_period - (time.monotonic() % loop_period))

                setting = settings_receiver.get_next_signal(timeout=loop_period).args[-1]
                if len(settings_signals_received) and setting == settings_signals_received[-1]:
                    setting = settings_receiver.get_next_signal(timeout=loop_period).args[-1]

                status_signals_received.append(status)
                settings_signals_received.append(setting)

            # Test that finalize_loop sets status back to 1
            time.sleep(loop_period)
            status_signals_received.append(task_proxy.get_status().value)

        # Assert
        self.assertEqual(initial_status_value, status_init)
        self.assertListEqual(status_signals_expected, status_signals_received)
        self.assertListEqual(settings_signals_expected, settings_signals_received)
        self.assertFalse(task_proxy.is_running())

    def test_my_signal(self):
        """See that my_signal also gets updated and sent in each loop with increasing step"""
        # Arrange
        increase_loop = True  # +1 extra status value / round
        nr_of_loops = 5
        initial_status_value = 5
        loop_period = 0.1
        policy = QMI_LoopTaskMissedLoopPolicy.IMMEDIATE
        my_signals_expected = list(range(
            initial_status_value + 2, initial_status_value + nr_of_loops * 2, 3)
        )  # my_signal sums up (increasing) status and settings values, starting after 1st round.
        my_signals_received = []

        task_proxy = qmi.make_task(
            "loop_task_my_signal",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
        )
        receiver = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task_my_signal")
        publisher_proxy.my_signal.subscribe(receiver)
        LoopTestTask.Settings("Standard setting for LoopTestTask", 1)

        # Act
        task_proxy.start()
        for n in range(len(my_signals_expected)):
            # Test that the my_signal is sent at each loop with increasing value
            while not receiver.has_signal_ready():
                time.sleep(loop_period - (time.monotonic() % loop_period))  # synchronize

            my_signals_received.append(receiver.get_next_signal(timeout=loop_period).args[-1])

        # Assert
        self.assertListEqual(my_signals_expected, my_signals_received)

    def test_my_signal_timeout(self):
        """See that my_signal raises timeout if trying to wait for more signals than the loops"""
        # Arrange
        increase_loop = True
        nr_of_loops = 2
        initial_status_value = 0
        loop_period = 0.1
        policy = QMI_LoopTaskMissedLoopPolicy.IMMEDIATE

        task_proxy = qmi.make_task(
            "loop_task",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
        )
        receiver = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task")
        publisher_proxy.my_signal.subscribe(receiver)
        LoopTestTask.Settings("Standard setting for LoopTestTask", 1)

        # Act
        task_proxy.start()

        # Assert
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            for n in range(3):
                # Test that the my_signal is sent at each loop with increasing loop jumps
                _ = receiver.get_next_signal(timeout=2 * loop_period).args[-1]

    def test_loop_timeout_policy_IMMEDIATE(self):
        """See that all loop iterations are obtained even if with some delay"""
        # Arrange
        nr_of_loops = 5
        increase_loop = False
        initial_status_value = -1
        loop_period = 0.1
        policy = QMI_LoopTaskMissedLoopPolicy.IMMEDIATE

        status_signals_expected = list(range(
            initial_status_value, initial_status_value + nr_of_loops + 1, 1)
        )
        settings_signals_expected = [1] + list(range(1, nr_of_loops + 1))
        status_got = []
        settings_got = []
        status_signals_received = []
        settings_signals_received = []

        # The `error=IMMEDIATE` in the task object creation makes each loop be 1.1 times longer than loop period.
        task_proxy = qmi.make_task(
            "loop_task_immediate",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
            error="IMMEDIATE",
        )
        receiver_sett = QMI_SignalReceiver()
        receiver_stat = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task_immediate")
        publisher_proxy.sig_settings_updated.subscribe(receiver_sett)
        publisher_proxy.sig_status_updated.subscribe(receiver_stat)

        # Act
        # Get initial values before start
        settings_got.append(task_proxy.get_settings().value)
        status_got.append(task_proxy.get_status().value)
        start = time.time()
        task_proxy.start()
        # Test that prepare has done its job
        settings_signals_received.append(
            receiver_sett.get_next_signal(timeout=2 * loop_period).args[-1]
        )
        status_signals_received.append(
            receiver_stat.get_next_signal(timeout=2 * loop_period).args[-1]
        )
        # LoopTestTask does 1.1x loop_period --> should be finished after nr_of_loops*loop_period
        for n in range(nr_of_loops):
            # Test that the status changes at the end of each loop, after receiver signal increments
            settings_got.append(task_proxy.get_settings().value)
            while task_proxy.get_status().value == status_got[-1]:
                time.sleep(0.1 * loop_period)

            status_got.append(task_proxy.get_status().value)
            settings_signals_received.append(
                receiver_sett.get_next_signal(timeout=2 * loop_period).args[-1]
            )
            status_signals_received.append(
                receiver_stat.get_next_signal(timeout=loop_period).args[-1]
            )

        time.sleep(loop_period * 2)  # Need to sleep once more for waiting the last loop `sleep`.
        # Test that finalize_loop sets settings and status back to 1
        settings_got.append(task_proxy.get_settings().value)
        status_got.append(task_proxy.get_status().value)
        end = time.time()
        # Assert
        self.assertFalse(task_proxy.is_running())
        self.assertGreater(end - start, 3 * loop_period)
        self.assertListEqual(settings_signals_received, settings_got[:-1])
        self.assertListEqual(status_signals_expected, status_got[:-1])
        self.assertEqual(1, settings_got[-1])  # loop_finalize should set the last value as 1
        self.assertEqual(1, status_got[-1])  # loop_finalize should set the last value as 1
        self.assertListEqual(status_signals_expected, status_signals_received)
        self.assertListEqual(settings_signals_expected, settings_signals_received)

    def test_loop_timeout_policy_SKIP(self):
        """See that setting policy to skip causes to skip loops"""
        # Arrange
        status_signals_received = []
        settings_signals_received = []
        increase_loop = False
        nr_of_loops = 5
        initial_status_value = -1
        loop_period = 0.1
        policy = QMI_LoopTaskMissedLoopPolicy.SKIP

        status_signals_expected = list(range(initial_status_value, round(nr_of_loops / 2 + 1e-15)))
        settings_signals_expected = [1] + [1, 3, 5]  # default value + skips loops 2 & 4

        task_proxy = qmi.make_task(
            "loop_task",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
            error="SKIP",
        )
        receiver_sett = QMI_SignalReceiver()
        receiver_stat = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task")
        publisher_proxy.sig_settings_updated.subscribe(receiver_sett)
        publisher_proxy.sig_status_updated.subscribe(receiver_stat)

        # Act
        status_got = task_proxy.get_status().value
        task_proxy.start()
        # Test that prepare has done its job
        settings_signals_received.append(
            receiver_sett.get_next_signal(timeout=loop_period).args[-1]
        )
        status_signals_received.append(
            receiver_stat.get_next_signal(timeout=loop_period).args[-1]
        )
        # LoopTestTask does 1.1x loop_period --> should be finished after half, rounded up, nr_of_loops has been done.
        for n in range(round(nr_of_loops / 2 + 1e-15)):  # + 1e-15 to cheat on "banker's rounding" to "always" round up
            # Test that the status changes at the end of each loop, after receiver signal increments
            while task_proxy.get_status().value == status_got:
                time.sleep(0.1 * loop_period)

            status_got = task_proxy.get_status().value
            status_signals_received.append(
                receiver_stat.get_next_signal(timeout=2 * loop_period).args[-1]
            )
            settings_signals_received.append(
                receiver_sett.get_next_signal(timeout=2 * loop_period).args[-1]
            )

        time.sleep(loop_period * 2)  # Make sure the loop has time to finalize
        # Assert
        # Test that finalize_loop sets status back to 1
        self.assertFalse(task_proxy.is_running())
        self.assertEqual(1, task_proxy.get_settings().value)
        self.assertEqual(1, task_proxy.get_status().value)
        self.assertListEqual(status_signals_expected, status_signals_received)
        self.assertListEqual(settings_signals_expected, settings_signals_received)

    def test_loop_timeout_policy_TERMINATE(self):
        """See that setting policy to terminate stops the task"""
        # Arrange
        status_signals_received = []
        settings_signals_received = []
        increase_loop = False
        nr_of_loops = 5
        initial_status_value = 3
        loop_period = 0.1
        policy = QMI_LoopTaskMissedLoopPolicy.TERMINATE

        status_signals_expected = list(range(
            initial_status_value, initial_status_value + 2, 1)
        ) + [1]  # Expected to skip a sample on 2nd step and terminate, last value defaults back to 1
        settings_signals_expected = [1, 1]  # initial value, 1st loop

        task_proxy = qmi.make_task(
            "loop_task_terminate",
            LoopTestTask,
            increase_loop=increase_loop,
            nr_of_loops=nr_of_loops,
            status_value=initial_status_value,
            loop_period=loop_period,
            policy=policy,
            error="TERMINATE",
        )
        receiver = QMI_SignalReceiver()
        publisher_proxy = qmi.get_task(f"{self._ctx_qmi_id}.loop_task_terminate")
        publisher_proxy.sig_settings_updated.subscribe(receiver)

        # Act
        # Test that initial status value is set as -1
        status_signals_received.append(task_proxy.get_status().value)
        task_proxy.start()
        # LoopTestTask does 5x 1 second loops, but we should miss every second loop --> should be finished after 2 loops
        for n in range(2):
            settings_signals_received.append(
                receiver.get_next_signal(timeout=2 * loop_period).args[-1]
            )
            # Test that the status changes at the end of each loop, after receiver signal increments
            while task_proxy.get_status().value == status_signals_received[-1]:
                time.sleep(0.1 * loop_period)

            status_signals_received.append(task_proxy.get_status().value)

        # 3rd loop should raise the timeout exception
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            settings_signals_received.append(
                receiver.get_next_signal(timeout=loop_period).args[-1]
            )

        time.sleep(loop_period)  # The loop should terminate with the timeout
        # Assert
        self.assertFalse(task_proxy.is_running())
        self.assertListEqual(status_signals_expected, status_signals_received)
        self.assertListEqual(settings_signals_expected, settings_signals_received)

    def test_get_task_class_name(self):
        task_proxy = qmi.make_task(
            "simple_task_name",
            SimpleTestTask,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=1.0,
            value=7,
        )
        task_class_name = task_proxy.get_task_class_name()
        expect_name = __name__ + ".SimpleTestTask"
        self.assertEqual(task_class_name, expect_name)

    def test_custom_task_runner(self):
        task_proxy = qmi.make_task(
            "simple_task_runner",
            SimpleTestTask,
            task_runner=CustomTaskRunner,
            raise_exception_in_init=False,
            raise_exception_in_run=False,
            duration=1.0,
            value=7,
        )
        actual = task_proxy.get_custom_taskrunner_attr()
        self.assertEqual(actual, sentinel.custom_taskrunner_attr)


if __name__ == "__main__":
    unittest.main()
