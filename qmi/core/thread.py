"""Implementation of the QMI_Thread class.
"""

import threading

from qmi.core.exceptions import QMI_WrongThreadException


def check_in_main_thread() -> None:
    """Check that this function is called in the main thread.

    Raises:
        ~qmi.core.exceptions.QMI_WrongThreadException: If the function is called from any
            thread other than the main thread.
    """
    if threading.current_thread() is not threading.main_thread():
        raise QMI_WrongThreadException("Not in main thread")


class QMI_Thread(threading.Thread):
    """A QMI_Thread is an abstract base class for all threads used within QMI.

    The added value compared to Python's `threading.Thread` class is that it provides a
    way to request thread shutdown (via the `shutdown` method).

    QMI_Thread instances are initialized to be Python 'daemon' threads. This is done to prevent
    a deadlock when the Python process terminates; the Python interpreter effectively performs a
    'join()' on non-daemon threads at shutdown, prior even to running atexit handlers.

    Unfortunately, the shutdown process cannot be reliably hooked. By making the QMI_Threads
    daemonic, we ensure that we get to the execution of the at-exit handlers, which will properly
    tear down any remaining QMI_Contexts; This will shut down all active QMI_Threads in an orderly way.

    The QMI_Thread class currently has three specializations:

    - _EventDrivenThread in qmi.core.messaging;
    - _RpcThread in qmi.core.rpc;
    - _TaskThread in qmi.core.task.

    Important:
        QMI_Threads are part of the core QMI machinery.
        They should not be instantiated directly by QMI users.
        QMI users should use QMI_Tasks instead.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._shutdown_requested = False  # Indicates if thread shutdown has been requested.

    def run(self) -> None:
        """The run() method must be overridden by derived classes."""
        raise NotImplementedError()

    def shutdown(self) -> None:
        """Command the thread to terminate orderly, as soon as possible.

        After calling shutdown(), the usual thing to do is call join() to join up with the thread.

        The shutdown() function can also be called during Python cleanup, see the documentation of the join()
        method above.
        """

        # We check '_shutdown_requested', thereby guaranteeing that the _request_shutdown() method won't be called
        # more than once.
        if not self._shutdown_requested:
            self._shutdown_requested = True
            self._request_shutdown()

    def _request_shutdown(self) -> None:
        """Command the thread to terminate cleanly, as soon as possible.

        The _request_shutdown() method may be overridden by derived classes, so
        they can optionally take action to terminate their run() loop beyond polling
        the '_shutdown_requested' member variable.

        The way to initiate termination of the run() loop can differ between sub-classes.
        For example, it may involve waking up a running select() or wait().

        Simple implementations can just poll the '_shutdown_requested' member variable,
        which is fine for many use cases.

        The _request_shutdown() implementation _must_ be thread-safe, i.e., it
        should be possible to call the function from any thread.

        For a given QMI_Thread, the _request_shutdown() method will never be called
        more than once. This is guarded by the '_shutdown_requested' member variable.

        This function must only be called from the shutdown() method!
        """
        pass
