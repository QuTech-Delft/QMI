"""Background tasks for QMI.

This module provides support for tasks which run asynchronously in the background.

Defining tasks
##############

To define a new background task, create a subclass of `QMI_Task`.
The new class must define a `run()` method, containing the main code of the task.
It may also be helpful to redefine the `__init__()` method in order
to accept arguments and initialize the task.

A task may define two types of special variables:

- **settings**: data that affects the behaviour of the task.
  Settings can be modified by other tasks or scripts while the task
  is still running.

- **status**: data that represents the current activity of the task.
  The task can change its own status while it runs, but other tasks or
  scripts can not change this task's status.

Declare two custom named tuple types to contain the settings resp. the status
of your task. Instances of these named tuples will be used to store the
current settings in ``self.settings`` and the current status in ``self.status``.

Example of a custom task definition::

    MySettings = namedtuple("MySettings", "param other_param")
    MyStatus = namedtuple("MyStatus", "field other_field")

    class MyTask(QMI_Task):
        def __init__(self, task_runner, name, my_arg, my_other_arg):
            super().__init__(task_runner, name)
            self.settings = MySettings(...)
            self.status = MyStatus(...)
            ...
        def run(self):
            while not self.stop_requested():
                self.update_settings()
                ...

Running tasks
#############

Tasks are created via the QMI context.
The context then returns a `proxy` for the new task instance.
A newly created task must be explicitly started by calling the `start()`
method through the proxy.

A task stops when its `run()` method returns.
Alternatively, the `stop()` method may be called through the proxy to request
that the task stops itself as soon as possible.
Even in this case, the task will still continue to run until its `run()` method
honours the stop request by returning.

To clean up a stopped task, call the `join()` method through the proxy.
The `join()` method will wait until the task has stopped, if necessary,
then clean up the background thread.

Example of starting and stopping a task::

    proxy = qmi.make_task("my_task", MyTask, "arg1", "arg2")
    proxy.start()
    ...
    new_settings = MySettings(...)
    proxy.set_settings(new_settings)
    ...
    status = proxy.get_status()
    print("Status:", status)
    ...
    proxy.stop()
    proxy.join()

Custom Task Runner
##################

It's possible to define a custom task runner and have qmi use _it_ instead of a
default `QMI_TaskRunner` instance. This will allow custom RPC methods and state
to be added to the runner, which can be useful in some cases.

Example of a custom task runner::

    class MyTaskRunner(QMI_TaskRunner):
        @rpc_method
        def set_param(self, param):
            settings = self.get_pending_settings()
            settings._replace(param=param)
            self.set_settings(settings)

    proxy = qmi.make_task("my_task", MyTask, "arg1", "arg2", task_runner=MyTaskRunner)
    proxy.start()
    ...
    proxy.set_param(...)
    ...
    proxy.stop()
    proxy.join()

Reference
#########
"""

import collections
import enum
import inspect
import logging
import threading
import time
from typing import Any, Generic, Type, TypeVar, TYPE_CHECKING
from collections.abc import Callable

from qmi.core.rpc import QMI_RpcObject, rpc_method
from qmi.core.pubsub import SignalDescription, QMI_Signal, QMI_RegisteredSignal
from qmi.core.thread import QMI_Thread
from qmi.core.exceptions import (
    QMI_TaskInitException, QMI_TaskRunException, QMI_TaskStopException,
    QMI_UsageException, QMI_WrongThreadException)
from qmi.core.util import is_valid_object_name

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Global definitions for type variables used in this module
_SET = TypeVar("_SET")  # task settings
_STS = TypeVar("_STS")  # task status


class QMI_LoopTaskMissedLoopPolicy(enum.Enum):
    """Possible policies of QMI_LoopTask instance missing a loop period."""
    IMMEDIATE = 1  # Do actions as quickly as possible
    SKIP = 2  # Skip actions and try again at the next period
    TERMINATE = 3  # Not acceptable to miss periodical loop instances -> terminate QMI_LoopTask


class _TaskMetaClass(type):
    """Meta-class used to create QMI_Task and its subclasses.

    This meta-class extracts a list of signals published by the class.
    The list of signals is inserted as a class attribute named `_qmi_signals`.
    """

    def __init__(cls, name: str, bases: tuple, dct: dict) -> None:

        # Let "type" do its thing.
        super().__init__(name, bases, dct)

        # The original class must not yet have a _qmi_signals attribute.
        assert "_qmi_signals" not in dct

        # Scan the newly created QMI_Task subclass for class attributes of type QMI_Signal.
        # These are markers to announce signals that the class may publish.
        signals = []
        for attr_name, attr_value in inspect.getmembers(cls, lambda member: isinstance(member, QMI_Signal)):
            if not is_valid_object_name(attr_name):
                raise QMI_UsageException(f"Invalid signal name {attr_name!r} in class {cls.__name__}")
            signals.append(SignalDescription(name=attr_name, arg_types=attr_value.arg_types))

        # Add the list of signals as an attribute of the newly created QMI_Task subclass.
        cls._qmi_signals = tuple(signals)


class QMI_Task(Generic[_SET, _STS], metaclass=_TaskMetaClass):
    """Base class for all background tasks.

    Each instance of `QMI_Task` runs in a separate thread where it performs
    background activities without blocking the rest of the application.

    Subclasses of `QMI_Task` implement specific background tasks.
    Each subclass must implement a special method `run()`, containing
    the code which runs in the background.

    Tasks may publish QMI signals.

    Attributes:
        sig_settings_updated: Signal used to publish the latest settings when updated. Can be used by clients who need
                              to know when the settings might have changed by another client. Users need to re-define
                              this signal with appropriate type, if necessary.
    """

    sig_settings_updated = QMI_Signal([type(None)])

    def __init__(self, task_runner: 'QMI_TaskRunner', name: str) -> None:
        """Initialize the task.

        Subclasses of QMI_Task may override this method. The `__init__()`
        function of the subclass must also take `task_runner` and `name`
        as its first two parameters. These parameters are provided by
        the QMI context. The subclass `__init__()` must call the base class
        method via ``super().__init__(task_runner, name)``.

        The subclass `__init__()` may take additional parameters. These
        additional parameters can be passed to `context.make_task()`.

        Parameters:
            task_runner: The `QMI_TaskRunner` instance which manages this task.
            name: The RPC object name of this task instance.
        """

        # Check that task is initialized inside the task thread.
        if task_runner._thread is not threading.current_thread():
            raise QMI_WrongThreadException()

        _logger.debug("Initializing task %s", name)

        self._context = task_runner._context
        self._task_runner = task_runner
        self._name = name
        self._stop_requested = threading.Event()
        self._settings_fifo: collections.deque = collections.deque(maxlen=1)
        self.settings: _SET | None = None
        self.status: _STS | None = None

        # Create instances of QMI_RegisteredSignal for each signal type that this class may publish.
        # Insert these QMI_RegisteredSignal instances as attributes of the RpcObject instance.
        #
        # Note: The class attribute "_qmi_signals" will be created by the metaclass.
        declared_signals = self._qmi_signals  # type: ignore  # pylint: disable=no-member
        for sig_desc in declared_signals:
            if sig_desc.name == "sig_settings_updated":
                # specifically remap settings because this is only typed in the inherited task
                sig = QMI_RegisteredSignal(self._context, name, sig_desc.name, tuple([type(self.settings)]))
            else:
                sig = QMI_RegisteredSignal(self._context, name, sig_desc.name, sig_desc.arg_types)
            setattr(self, sig_desc.name, sig)

    def stop_requested(self) -> bool:
        """Return True if the task should stop.

        A long running background task should regularly call this function
        to check whether a stop request has been sent to the task.

        If this function returns True, the task should stop as
        soon as possible (by returning from its run() function).
        """
        return self._stop_requested.is_set()

    def sleep(self, duration: float) -> None:
        """Sleep for the specified duration (in seconds).

        This should be used by the task code instead of `time.sleep()`.
        If the task receives a stop request while sleeping,
        this method ends immediately and raises `QMI_TaskStopException`.

        Parameters:
            duration: Sleep duration in seconds.

        Raises:
            ~qmi.core.exceptions.QMI_TaskStopException: If the task received a stop request.
        """

        # Check that this method is called only from within the task thread.
        if self._task_runner._thread is not threading.current_thread():
            raise QMI_WrongThreadException()

        if self._stop_requested.wait(duration):
            raise QMI_TaskStopException()

    def update_settings(self) -> bool:
        """Update to the latest settings that were sent to the task.

        If another routine called `set_settings()` to send new settings
        to this task, this method copies the new settings to `self.settings`
        and returns True.

        Otherwise, the settings remain the same and this method returns False.

        Returns:
            True if there are new settings, False if the settings are unchanged.
        """

        # Check that this method is called only from within the task thread.
        if self._task_runner._thread is not threading.current_thread():
            raise QMI_WrongThreadException()

        # Try to obtain new settings.
        if self._settings_fifo:
            self.settings = self._settings_fifo.pop()
            self.sig_settings_updated.publish(self.settings)
            return True

        return False

    def run(self) -> None:
        """Main function of the task.

        This function runs in the background as long as the task is active.
        Subclasses must provide their own implementation.
        """
        raise NotImplementedError()


class _TaskThread(QMI_Thread):
    """A TaskThread is a dedicated thread which runs a QMI task.

    This is an internal QMI class, used exclusively by the QMI_TaskRunner.
    This class should never be used or accessed directly in application code.
    """

    class State(enum.Enum):
        """State of the task thread."""
        INITIAL = 100
        EXCEPTION_WHILE_INSTANTIATING_TASK = 101
        READY_TO_RUN = 102
        RUNNING = 103
        EXCEPTION_WHILE_RUNNING_TASK = 104
        TASK_COMPLETED_NORMALLY = 105
        TASK_STOPPED_BEFORE_START = 106

    def __init__(self,
                 task_runner: 'QMI_TaskRunner',
                 task_name: str,
                 task_class: Type[QMI_Task],
                 task_args: tuple,
                 task_kwargs: dict
                 ) -> None:
        super().__init__()
        self._task_runner = task_runner
        self._task_name = task_name
        self._task_class = task_class
        self._task_args = task_args
        self._task_kwargs = task_kwargs
        self.task: QMI_Task | None = None
        self._exception: BaseException | None = None
        self._state = _TaskThread.State.INITIAL
        self._state_cond = threading.Condition()
        self._wait_cond_lock = threading.Lock()
        self._wait_cond: threading.Condition | None = None

    def run(self) -> None:
        """Main function inside the thread."""

        try:
            # Create the task instance.
            self.task = self._task_class(self._task_runner,  # type: ignore
                                         self._task_name,
                                         *self._task_args,
                                         **self._task_kwargs)
        except BaseException as exception:
            # Initialization failed. Report exception and stop the thread.
            with self._state_cond:
                _logger.warning("Initialization of task %s failed", self._task_name, exc_info=True)
                self._exception = exception
                self._state = _TaskThread.State.EXCEPTION_WHILE_INSTANTIATING_TASK
                self._state_cond.notify_all()
                return

        # Notify the outside world that the task was initialized.
        with self._state_cond:
            assert self._state in (_TaskThread.State.INITIAL, _TaskThread.State.TASK_STOPPED_BEFORE_START)
            if self._state == _TaskThread.State.INITIAL:
                self._state = _TaskThread.State.READY_TO_RUN
                self._state_cond.notify_all()

        _logger.debug("Task thread %s ready to run", self._task_name)

        # Wait until the outside world tells us to continue.
        with self._state_cond:
            while self._state == _TaskThread.State.READY_TO_RUN:
                self._state_cond.wait()
            if self._state != _TaskThread.State.RUNNING:
                # The task was stopped before it was even started.
                # Do not call the task run() method, just stop the thread.
                _logger.debug("Task thread %s stopped before start", self._task_name)
                return

        _logger.debug("Task thread %s starts running", self._task_name)

        try:
            # Invoke the task main function.
            self.task.run()
        except QMI_TaskStopException:
            # The task was stopped via QMI_TaskStopException.
            # Log this, but don't re-raise the exception.
            _logger.warning("Task %s stopped on QMI_TaskStopException", self._task_name, exc_info=True)
        except BaseException as exception:
            # The task main function raised an exception.
            # Report the exception and stop the thread.
            with self._state_cond:
                _logger.warning("Exception in task %s", self._task_name, exc_info=True)
                self._exception = exception
                self._state = _TaskThread.State.EXCEPTION_WHILE_RUNNING_TASK
                self._state_cond.notify_all()
                return

        # Notify the outside world that the task is finished.
        with self._state_cond:
            self._state = _TaskThread.State.TASK_COMPLETED_NORMALLY
            self._state_cond.notify_all()

        _logger.debug("Task thread %s completed normally", self._task_name)

    def get_state(self) -> tuple[State, BaseException | None]:
        """Return task state and any exception that occurred in the task."""
        with self._state_cond:
            return (self._state, self._exception)

    def wait_until_initialized(self) -> None:
        """Block until initialization of the task is finished."""
        with self._state_cond:
            while self._state == _TaskThread.State.INITIAL:
                self._state_cond.wait()

    def start_task(self) -> None:
        """Start the task.

        This causes invocation of the `QMI_Task.run()` method inside
        the dedicated thread.

        This function may be called only once per task.
        """
        with self._state_cond:
            # Wait until initialization finished.
            while self._state == _TaskThread.State.INITIAL:
                self._state_cond.wait()
            # Sanity check on task state.
            assert self._state == _TaskThread.State.READY_TO_RUN
            # Kick task to RUNNING state.
            self._state = _TaskThread.State.RUNNING
            self._state_cond.notify_all()

    def stop_task(self) -> None:
        """Tell the task to stop.

        This function signals the task to stop, then returns immediately.
        It may take some time until the task actually stops, depending on
        the code inside the task.

        If necessary, call `wait_until_complete()` to wait for actual
        completion of the task.
        """

        with self._state_cond:

            if self._state == _TaskThread.State.EXCEPTION_WHILE_INSTANTIATING_TASK:
                # Task already stopped.
                return

            if self._state in (_TaskThread.State.INITIAL, _TaskThread.State.READY_TO_RUN):
                # Task is still waiting to start. Stop it now.
                self._state = _TaskThread.State.TASK_STOPPED_BEFORE_START
                self._state_cond.notify_all()
                return

            # Sanity check on task state.
            assert self._state in (_TaskThread.State.RUNNING,
                                   _TaskThread.State.TASK_COMPLETED_NORMALLY,
                                   _TaskThread.State.EXCEPTION_WHILE_RUNNING_TASK,
                                   _TaskThread.State.TASK_STOPPED_BEFORE_START)
            assert self.task is not None

        # Set flag to make task code stop.
        self.task._stop_requested.set()

        # If the task is waiting on a condition, force it to wake up.
        with self._wait_cond_lock:
            # DO NOT hold self._wait_cond_lock while locking the condition lock.
            # Doing so could cause deadlock since] wait_for_condition() holds
            # the condition lock while locking self._wait_cond_lock.
            wait_cond = self._wait_cond

        if wait_cond is not None:
            with wait_cond:
                wait_cond.notify_all()

    def _request_shutdown(self) -> None:
        # Stop the task during Python shutdown.
        _logger.warning("Stopping task %s during shutdown", self._task_name)
        self.stop_task()

    def wait_for_condition(self,
                           cond: threading.Condition,
                           predicate: Callable[[], bool],
                           timeout: float | None
                           ) -> bool:
        """Wait until a condition becomes true, or until the task is stopped.

        This method provides a way for QMI code to wait on a condition variable,
        but stop waiting if the running task receives a stop request.
        This is done by internally notifying the condition variable when a stop
        request is received.

        This function may only be called from the thread that is represented
        by this instance of `_TaskThread`.

        Parameters:
            cond:       Condition variable to wait on. The calling thread
                        must hold the lock associated with the condition
                        variable before calling this function.
            predicate:  Callable function which returns a boolean.
                        The predicate will be evaluated before waiting,
                        and evaluated again each time the condition variable
                        is notified. Waiting ends when the predicate
                        returns True.
            timeout:    Timeout in seconds, or None to wait indefinitely.

        Returns:
            True if the condition becomes true, False if timeout occurs.

        Raises:
            QMI_TaskStopException: If the thread receives a stop request before
                the condition becomes true.
        """

        # Check that this method is called from within this thread.
        assert threading.current_thread() is self
        assert self.task is not None

        # Register the condition variable on which we are going to wait.
        # This will be used to stop waiting if the task receives a stop request.
        with self._wait_cond_lock:
            assert self._wait_cond is None
            self._wait_cond = cond

        try:
            # Wait until either the predicate becomes true or the task receives a stop request.
            stop_requested = self.task._stop_requested
            ret = cond.wait_for(lambda: (predicate() or stop_requested.is_set()), timeout)

            # Raise QMI_TaskStopException if the task has received a stop request.
            if self.task._stop_requested.is_set():
                raise QMI_TaskStopException()

            # Otherwise return True if the predicate became True, False if waiting timed out.
            return ret

        finally:
            # Unregister the condition variable on which we waited.
            with self._wait_cond_lock:
                self._wait_cond = None


class QMI_TaskRunner(QMI_RpcObject):
    """Manager for a single task.

    A `QMI_TaskRunner` manages a single instance of `QMI_Task`.

    A dedicated `QMI_TaskRunner` is created by the context for each instance
    of `QMI_Task`. The `QMI_TaskRunner` creates a background thread to run
    the actual `QMI_Task` instance.

    The `QMI_TaskRunner` supports a fixed set of RPC methods.
    To interact with the task, other tasks or routines call these methods.

    A `QMI_TaskRunner` instance is created by the context when the
    application calls `context.make_task()`. Application code should
    not explicitly call the `QMI_TaskRunner()` constructor.
    """

    @classmethod
    def get_category(cls) -> str | None:
        return "task"

    def __init__(self,
                 context: 'qmi.core.context.QMI_Context',
                 name: str,
                 task_class: Type[QMI_Task],
                 task_args: tuple,
                 task_kwargs: dict
                 ) -> None:
        """Initialize the task runner and create the task instance.

        If the task raises an exception during initialization,
        the task will be cleaned up and the exception re-raised from this method.

        Parameters:
            context: The QMI context.
            name: RPC object name of the task.
            task_class: Specific subclass of `QMI_Task` to be instantiated.
            task_args: Positional arguments for the `QMI_Task` constructor.
            task_kwargs: Keyword arguments for the `QMI_Task` constructor.
        """

        _logger.debug("Creating task %s", name)

        # An instance of QMI_TaskRunner publishes signals which are declared
        # in another class, namely in the specific subclass of QMI_Task
        # which is managed by the task runner. We therefore specify the
        # task class as the "signal_declaration_class".
        super().__init__(context, name, signal_declaration_class=task_class)

        self._task_class = task_class
        self._new_settings = None
        self._joined = False
        self._policy = None

        # Create thread and start it.
        self._thread = _TaskThread(self, name, task_class, task_args, task_kwargs)
        self._thread.start()

        # The thread will create an instance of the QMI_Task subclass.
        # Wait until the instance is initialized.
        self._thread.wait_until_initialized()
        (state, exception) = self._thread.get_state()

        if state == _TaskThread.State.EXCEPTION_WHILE_INSTANTIATING_TASK:
            # An exception occurred during initialization.
            # Clean up task and re-raise the exception here.
            self._thread.join()
            assert isinstance(exception, BaseException)
            raise QMI_TaskInitException(f"Failed to initialize task {self._name}") from exception

        assert state == _TaskThread.State.READY_TO_RUN
        assert self._thread.task is not None

    @rpc_method
    def __enter__(self):
        """The `__enter__` methods is decorated as `rpc_method` so that `QMI_RpcProxy` can call it when using the
        proxy with a `with` context manager. This method also calls to start the task thread."""
        return self.start()

    @rpc_method
    def __exit__(self, *args, **kwargs):
        """The `__exit__` methods is decorated as `rpc_method` so that `QMI_RpcProxy` can call it when using the
        proxy with a `with` context manager. This method also calls to stop and join the task thread."""
        self.stop()
        self.join()

    def release_rpc_object(self) -> None:
        """Ensure the task is joined before it is removed from the context."""
        if not self._joined:
            _logger.warning("Task %s removed but not joined; stopping it now", self._name)
            self.stop()
            self.join()

    @rpc_method
    def start(self) -> None:
        """Start the task.

        This function triggers a call to the `run()` method of the task.
        Note that the task runs in a separate thread.
        This function returns as soon as the task is started, while the
        task continues to run in the background.

        This function may be called only once per task.
        """

        # Check that task was not yet started.
        (state, dummy_exception) = self._thread.get_state()
        if state != _TaskThread.State.READY_TO_RUN:
            raise QMI_UsageException(f"Task {self._name} can not be started more than once")

        _logger.debug("Starting task %s", self._name)
        self._thread.start_task()

    @rpc_method
    def stop(self) -> None:
        """Stop the task.

        This function tells the task to stop. From this point on, if the
        task calls `stop_requested()` it will return True and if the task
        sleeps it will be stopped via `QMI_TaskStopException`.

        This function returns immediately without waiting until the task
        is stopped. The task may continue to run in the background for
        some time, depending on the code inside the task.
        """
        _logger.debug("Stopping task %s", self._name)
        self._thread.stop_task()

    @rpc_method
    def join(self) -> None:
        """Wait until the task is fully stopped.

        This function blocks until the task is fully stopped.
        This may take some time, depending on the code inside the task.
        If the task does not stop spontaneously and `stop()` has not been
        called, this function may never return.

        If the task code raised an exception, the exception will
        be re-raised from this method.

        Each task must be joined before it can be removed from the context.
        Joining the task will also stop the associated thread and release its
        resources.
        """

        _logger.debug("Joining task %s", self._name)

        # Wait until the task thread ends.
        self._thread.join()

        # Get the task state.
        (state, exception) = self._thread.get_state()
        assert state in (_TaskThread.State.TASK_COMPLETED_NORMALLY,
                         _TaskThread.State.EXCEPTION_WHILE_RUNNING_TASK,
                         _TaskThread.State.TASK_STOPPED_BEFORE_START)

        # Break the reference cycle between QMI_TaskRunner and QMI_Task.
        assert self._thread.task is not None
        self._thread.task._task_runner = None  # type: ignore

        # Mark the task as joined (safe to be released).
        self._joined = True

        if state == _TaskThread.State.EXCEPTION_WHILE_RUNNING_TASK:
            # An exception occurred while running the task.
            # Re-raise the exception to report it to the application.
            assert isinstance(exception, BaseException)
            raise QMI_TaskRunException(f"Task {self._name} failed") from exception

    @rpc_method
    def is_running(self) -> bool:
        """Return True if the task is currently running.

        This method returns True if the task has been started, has not yet
        stopped and has not raised an exception.
        """
        (state, dummy_exception) = self._thread.get_state()
        return state == _TaskThread.State.RUNNING

    @rpc_method
    def set_settings(self, new_settings: Any) -> None:
        """Send new settings to the task.

        Other parts of the software may call this method to change the settings
        used by the task.

        Note that the task may not immediately use the new settings. The task
        continues to use its current settings until it explicitly updates the
        settings by calling `update_settings()`.
        """
        assert self._thread.task is not None
        self._thread.task._settings_fifo.append(new_settings)

    @rpc_method
    def get_settings(self) -> Any:
        """Return the current value of the task's `self.settings` variable.

        The task can receive settings from other parts of the software.
        This method returns a snapshot of the settings that are currently
        in effect.

        Note that calling `get_settings()` immediately after `set_settings()`
        may still return the old settings until the task explicitly updates
        its settings by calling `update_settings()`.
        """
        assert self._thread.task is not None
        return self._thread.task.settings

    @rpc_method
    def get_pending_settings(self) -> Any:
        """Return pending settings stored in the task runner's fifo.

        Only once the internal task calls `update_settings()`, is the pending
        settings from the fifo assigned to the task's actual settings.
        """
        assert self._thread.task is not None
        pending_settings = list(self._thread.task._settings_fifo)
        return pending_settings[0] if pending_settings else None

    @rpc_method
    def get_status(self) -> Any:
        """Return the current value of the task's `self.status` variable.

        The task code can update its `self.status` variable at any time
        to expose its current status to other parts of the software.
        This method returns a current snapshot of the status variable.
        """
        assert self._thread.task is not None
        return self._thread.task.status

    @rpc_method
    def get_task_class_name(self) -> str:
        """Return the name of the QMI_Task class managed by this task runner."""
        module_name = self._task_class.__module__
        class_name = self._task_class.__name__
        return module_name + "." + class_name


class QMI_LoopTask(QMI_Task):
    """
    QMI_LoopTask is a subclass of `QMI_Task`, implementing specific background loop task.
    It has its own special `run()` method, containing a sequence of actions that apply to most `QMI_Task`
    implementations that will be used.

    Attributes:
        sig_status_updated: Signal used to publish the latest status when updated. Can be used by clients who need
                              to know when the status might have changed by another client. Users need to re-define
                              this signal with appropriate type, if necessary.
    """
    sig_status_updated = QMI_Signal([type(None)])

    def __init__(self, task_runner, name, loop_period: float = 1.0,
                 policy: QMI_LoopTaskMissedLoopPolicy = QMI_LoopTaskMissedLoopPolicy.IMMEDIATE) -> None:
        """
        Initialize the loop task.

        A QMI_Task subclass, overriding the base class. The `__init__()` function takes `task_runner` and `name`,
        which are provided by QMI context. The subclass `__init__()` calls the base class method via
        ``super().__init__(task_runner, name)``.

        The subclass `__init__()` takes additional parameters `loop_period` and `policy`. These additional parameters
        can be passed to `context.make_task()`.

        Parameters:
            task_runner: QMI_TaskRunner - object instance which manages this task.
            name: string - The RPC object name of this task instance.
            loop_period: float - The loop task repeat period in (fractions of) seconds.
            policy: QMI_LoopTaskMissedLoopPolicy - The policy for handling missed loop periods
        """
        super().__init__(task_runner, name)
        self._loop_period = loop_period
        self._policy = policy
        self._status_fifo: collections.deque = collections.deque(maxlen=1)

        declared_signals = self._qmi_signals  # type: ignore  # pylint: disable=no-member
        # Create an instance of QMI_RegisteredSignal for sig_status_updated, published by this class.
        # Insert this QMI_RegisteredSignal instance as an attribute of the RpcObject instance.
        for sig_desc in declared_signals:
            if sig_desc.name == "sig_status_updated":
                # specifically remap settings because this is only typed in the inherited task
                sig = QMI_RegisteredSignal(self._context, name, sig_desc.name, tuple([type(self.status)]))
                setattr(self, sig_desc.name, sig)

    def run(self) -> None:
        """
        Main function inside the task thread. This overrides the base class implementation.

        The default implementation creates a skeleton of actions that a task loop will take. The clients using this
        QMI_LoopTask will have to override the implementations of `loop_prepare()`, `loop_iteration()`,
        `loop_finalize()`, `process_new_settings()`, `update_status()`, and `publish_signals()`.

        The behaviour of handling missed loop iterations depend on the `QMI_LoopTaskMissedLoopPolicy` attribute set.
        """

        _logger.info("[%s] Starting...", self._name)

        self.loop_prepare()
        next_time = time.monotonic() + self._loop_period
        try:
            while not self.stop_requested():

                # Check for updated settings. If updated, process them
                if self.update_settings():
                    self.process_new_settings()

                # Do work.
                self.loop_iteration()

                # Check for updates status. If updated, publish new status.
                if self.update_status():
                    self.sig_status_updated.publish(self.status)

                # Update other signals (if present).
                self.publish_signals()

                # Sleep until next iteration.
                time_to_sleep = next_time - time.monotonic()
                if time_to_sleep > 0:
                    self.sleep(time_to_sleep)
                    next_time += self._loop_period

                else:
                    _logger.warning("[%s] Missed loop time: %.3f seconds late", self._name, -time_to_sleep)
                    if self._policy == QMI_LoopTaskMissedLoopPolicy.IMMEDIATE:
                        # Try to do the next one as soon as possible, but do not miss any steps
                        next_time = time.monotonic() + self._loop_period

                    elif self._policy == QMI_LoopTaskMissedLoopPolicy.SKIP:
                        # Check how many loop periods were missed and set the next one after those
                        periods_missed = int((self._loop_period - time_to_sleep) / self._loop_period)
                        next_time += self._loop_period * periods_missed

                    elif self._policy == QMI_LoopTaskMissedLoopPolicy.TERMINATE:
                        # Stop loop
                        self._task_runner.stop()

        except QMI_TaskStopException:
            pass  # not an error

        finally:
            self.loop_finalize()

        _logger.info("[%s] Stopped", self._name)

    def loop_prepare(self) -> None:
        """Method to prepare the task loop.

        Subclasses may override this method to prepare the task loop.
        The default implementation does nothing.
        """
        pass

    def process_new_settings(self) -> None:
        """Method for processing new settings.

        Subclasses may override this method to new task settings.
        The default implementation does nothing.
        """
        pass

    def loop_iteration(self) -> None:
        """Define work to be done in the task loop.

        Subclasses may override this method to define work done in a loop iteration.
        The default implementation does nothing.
        """
        pass

    def update_status(self) -> bool:
        """Update to the latest status that were set to the task.

        If another routine called `set_status()` to set a new status to this task, this method should copy the new
        status to `self.status` and return True. Otherwise the status remains the same and this method returns False.

        Subclasses may override this method to set specific status.
        The default implementation does nothing (returns False).

        Returns:
             bool - True if there is a new status, False if the status is unchanged.
        """
        return False

    def publish_signals(self) -> None:
        """Method for publishing other signals described by the client for the loop task.

        Subclasses may override this method to publish specific signals.
        The default implementation does nothing.
        """
        pass

    def loop_finalize(self) -> None:
        """The loop should return the task to a specific state and settings at the end.

        Subclasses may override this method to specify finalizing actions.
        The default implementation does nothing.
        """
        pass


# Imports needed only for static typing.
if TYPE_CHECKING:
    import qmi.core.context
