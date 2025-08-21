"""Publish/subscribe messaging mechanism for QMI.

The publish/subscribe mechanism is suitable for situations where data
is spontaneously produced (i.e. not in response to a request). Such data
may be sent to other QMI objects by `publishing a signal`.

Tasks which want to act on signals may create a signal receiver and
`subscribe` it to the corresponding publisher.

Declaring signals
#################

Any subclass of ``QMI_RpcObject`` (such as instruments and tasks) can publish signals.
In order to publish a signal, the signal must be declared in the RPC object class definition.
This is done by creating a `class attribute` and initializing it with an instance of ``QMI_Signal``.

For example::

    class MyTask(QMI_Task):

        # Declare a signal with name "sig_alice" which takes two parameters, both integers.
        sig_alice = QMI_Signal([int, int])

        # Declare a signal with name "sig_bob" which takes one string parameter.
        sig_bob = QMI_Signal([str])

        # ... rest of class definition

Publishing a signal
###################

An RPC object can publish any of the signals it has declared.
Publishing a signal means broadcasting a message through the QMI network.
This message is automatically received by all signal receivers that are subscribed to the signal.

For example, the task `MyTask` could publish its signals as follows::

    class MyTask(QMI_Task):
        sig_alice = QMI_Signal([int, int])
        sig_bob = QMI_Signal([str])

        def run(self):

            # Publish "sig_alice"
            self.sig_alice.publish(11, 105)

            # Publish "sig_bob"
            self.sig_bob.publish("hello receiver")

            # Publish "sig_alice" again with different parameters.
            self.sig_alice.publish(5, 6)

Subscribing to signals
######################

Any Python script, task or function can subscribe to signals.
Subscribing to a signal requires a `proxy` for the object that publishes the signal,
and a `signal receiver`.

For example, the following code creates an instance of `MyTask`.
It then uses the proxy to subscribe a receiver to the signal `sig_alice`::

    # Create task (and get a proxy to the new task).
    my_task_proxy = qmi.make_task("my_task", MyTask)

    # Create signal receiver.
    receiver = QMI_SignalReceiver()

    # Subscribe receiver to the signal "sig_alice".
    my_task_proxy.sig_alice.subscribe(receiver)

You can always subscribe to signals that are published in the same QMI context
(i.e. the same Python program).
It is also possible to subscribe to signals that are published by
another Python program, provided that this program is a peer context in
the QMI network, and a connection to this peer context has been established.

A receiver can be subscribed to multiple signals, and multiple
receivers can be subscribed to the same signal.

Receiving signals
#################

A signal receiver keeps received signals in an internal queue.
Each time a signal gets published to which the receiver is currently subscribed,
it adds a `ReceivedSignal` record to its queue.

In order to process a received signal, you can call `get_next_signal()` to
get a `ReceivedSignal` record from the receive queue.
If there are received signals in the queue, this function returns the oldest
received signal.
Otherwise, if the queue is empty, the function will either wait until
the next signal is received, or raise a `QMI_TimeoutException`.

For example::

    # Let's assume that "receiver" is already subscribed to "sig_alice"
    # and the signal has been published via "sig_alice.publish(11, 105)".
    try:
        sig = receiver.get_next_signal(timeout=1.0)
        print("Received signal", sig.signal_name, "with arguments", sig.args[0], sig.args[1])
          # will print something like "Received signal sig_alice with arguments 11 105"
    except QMI_TimeoutException:
        print("No signal was received within 1 second")

Reference
#########
"""

import logging
import threading
from collections import deque
from collections.abc import Callable

from typing import Any, NamedTuple, Type, TYPE_CHECKING

from qmi.core.exceptions import (
    QMI_TimeoutException, QMI_MessageDeliveryException,
    QMI_RuntimeException, QMI_SignalSubscriptionException, QMI_UsageException)
from qmi.core.messaging import (
    QMI_Message, QMI_RequestMessage, QMI_ReplyMessage, QMI_ErrorReplyMessage,
    QMI_MessageHandler, QMI_MessageHandlerAddress)
from qmi.core.util import is_valid_object_name


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class SignalDescription(NamedTuple):
    """Description of signal type, specifying its name and arguments.

    Attributes:
        name: Signal name.
        arg_types: Tuple of Python types (e.g. `int` or `str`), describing
            the parameters that will be passed in each published instance of
            this signal type.
    """
    name: str
    arg_types: tuple[Type, ...]


class ReceivedSignal(NamedTuple):
    """Signal instance received by a `QMI_SignalReceiver`.

    When a `QMI_SignalReceiver` receives a signal, it stores an instance
    of `ReceivedSignal` in its receive queue. The application can retrieve
    this instance and handle it.

    Attributes:
        publisher_context: Name of the context that published the signal.
        publisher_name: Name of the object that published the signal.
        signal_name: Name of the signal.
        args: List of signal arguments.
        receiver_seqnr: Sequence number assigned by the `QMI_SignalReceiver`.
            This sequence number can be used to detect dropped signals in
            case of overflow of the receive queue.
    """
    publisher_context:  str
    publisher_name: str
    signal_name: str
    args: tuple
    receiver_seqnr: int


class QMI_Signal:
    """Marker for signal declarations in an RpcObject or Task.

    An RpcObject or Task that wants to publish a signal, creates
    a class attribute with the name of the signal and initializes
    it with an instance of `QMI_Signal`.

    For example::

        class MyObject(QMI_RpcObject):
            my_signal = QMI_Signal([int, str])
    """
    __slots__ = ("arg_types",)

    def __init__(self, arg_types: list[Type]) -> None:
        """Declare a new signal type.

        Parameters:
            arg_types: List of Python types, describing the parameters that
                will be passed in each published instance of this signal type.
        """
        self.arg_types = tuple(arg_types)

    def publish(self, *args: Any) -> None:
        """Publish this signal.

        This method will be implemented by `QMI_RegisteredSignal`.
        It is declared here for static type checking.
        """
        raise QMI_RuntimeException("QMI_Signal has not been registered and converted to QMI_RegisteredSignal.")


class QMI_RegisteredSignal:
    """Represents a named signal, bound to a specific `QMI_RpcObject` instance.

    When an instance of an RPC class (task or instrument) is created,
    QMI automatically detects any `QMI_Signal` declarations in the RPC class
    and converts them to `QMI_RegisteredSignal` instances in the RPC object instance.

    An instance of `QMI_RegisteredSignal` may be used to publish signals.
    """

    __slots__ = ("context",
                 "publisher_name",
                 "signal_name",
                 "arg_types")

    def __init__(self,
                 context: "qmi.core.context.QMI_Context",
                 publisher_name: str,
                 signal_name: str,
                 arg_types: tuple[Type, ...]
                 ) -> None:
        """Initialize the `QMI_RegisteredSignal` instance.

        This is used internally by QMI.

        Do not create your own instances of `QMI_RegisteredSignal`.
        Instead, use the signal attributes of your QMI_RpcObject instance.
        """
        self.context = context
        self.publisher_name = publisher_name
        self.signal_name = signal_name
        self.arg_types = arg_types

    def __repr__(self) -> str:
        arg_types = ", ".join(arg_type.__name__ for arg_type in self.arg_types)
        return f"<registered signal {self.publisher_name}.{self.signal_name} ({arg_types})>"

    def publish(self, *args: Any) -> None:
        """Publish this signal.

        Arguments may be passed when publishing the signal. These must
        correspond to the argument types registered for this signal.

        The published signal will be received by all receivers currently
        subscribed to this signal type.

        This method is thread-safe: it may be called from any thread.
        """
        self.context.publish_signal(self.publisher_name, self.signal_name, *args)


class QMI_SignalSubscriber:
    """Represents a named signal, bound to a specific RPC proxy instance.

    When a proxy for an RPC class (task or instrument) is created,
    QMI automatically detects any `QMI_Signal` declarations in the RPC class
    and converts them to `QMI_SignalSubscriber` instances in the RPC proxy.

    An instance of `QMI_SignalSubscriber` may be used to subscribe to signals
    or unsubscribe from signals.
    """

    __slots__ = ("context",
                 "publisher_context",
                 "publisher_name",
                 "signal_name",
                 "signal_arg_types")

    def __init__(self,
                 context: "qmi.core.context.QMI_Context",
                 publisher_context: str,
                 publisher_name: str,
                 signal_name: str,
                 signal_arg_types: str
                 ) -> None:
        """Initialize the QMI_SignalSubscriber instance.

        This is used internally by QMI.

        Do not create your own instances of QMI_SignalSubscriber.
        Instead, use the signal attributes of an RPC proxy instance.
        """
        self.context = context
        self.publisher_context = publisher_context
        self.publisher_name = publisher_name
        self.signal_name = signal_name
        self.signal_arg_types = signal_arg_types

    def __repr__(self) -> str:
        return "<subscriber for signal {}.{}.{} {}>".format(self.publisher_context, self.publisher_name,
                                                            self.signal_name, self.signal_arg_types)

    def subscribe(self, receiver: "QMI_SignalReceiver") -> None:
        """Subscribe the specified receiver to this signal type.

        While subscribed, the `QMI_SignalReceiver` instance will receive and
        queue all published signals that match this subscription.

        A `QMI_SignalReceiver` instance can be simultaneously subscribed to
        multiple signals (either from the same publisher or from different publishers).
        Similarly, multiple receivers can be simultaneously subscribed to the
        same signal. However it is an error to try to subscribe a receiver to
        a signal to which it is already subscribed.

        Parameters:
            receiver: A `QMI_SignalReceiver` instance which will receive the published signals.
        """
        self.context.subscribe_signal(self.publisher_context, self.publisher_name, self.signal_name, receiver)

    def unsubscribe(self, receiver: "QMI_SignalReceiver") -> None:
        """Unsubscribe the specified receiver from this signal type.

        Parameters:
            receiver: The `QMI_SignalReceiver` instance to unsubscribe.
        """
        self.context.unsubscribe_signal(self.publisher_context, self.publisher_name, self.signal_name, receiver)


def _wait_for_condition(cond: threading.Condition, predicate: Callable[[], bool], timeout: float | None) -> bool:
    """Helper function to wait for a condition.

    When called from the main thread, this function is equivalent to::

      cond.wait_for(predicate, timeout)

    When called from a task thread, this function uses a special method
    of waiting which stops waiting when the task is requested to stop.
    """
    import qmi.core.task
    thread = threading.current_thread()
    if isinstance(thread, qmi.core.task._TaskThread):
        # We are called from a task thread.
        # Use a special method to wait on the condition variable
        # which wakes up if the thread is requested to stop.
        return thread.wait_for_condition(cond, predicate, timeout)
    else:
        # Not called from a QMI_Thread.
        # We can use a normal wait on the condition variable.
        return cond.wait_for(predicate, timeout)


class QMI_SignalReceiver:
    """An instance of `QMI_SignalReceiver` contains a queue of received signals.

    A `QMI_SignalReceiver` instance can be subscribed to a specific set of
    signals. When any such signal gets published, the published signal is
    automatically added to the receive queue of the `QMI_SignalReceiver`.

    A task or script which creates a `QMI_SignalReceiver`, should periodically
    check to see if new signals have arrived and handle them.

    When an instance of `QMI_SignalReceiver` is no longer needed, it **must**
    be explicitly unsubscribed from all signals.
    """

    DISCARD_OLD = 1
    DISCARD_NEW = 2

    def __init__(self, max_queue_length: int = 10000, discard_policy: int = DISCARD_OLD) -> None:
        """Create a `QMI_SignalReceiver`, containing a signal receive queue.

        Parameters:
            max_queue_length: Maximum number of signals to keep in the receive queue.
            discard_policy: Policy in case the receive queue becomes full.
                If discard_policy == `QMI_SignalReceiver.DISCARD_OLD`, the oldest pending
                signal will be discarded to make room for a new publised signal.
                If discard_policy == `QMI_SignalReceiver.DISCARD_NEW`, newly received
                signals will be dropped when they do not fit in the queue.
        """
        assert max_queue_length > 0
        assert discard_policy in (self.DISCARD_OLD, self.DISCARD_NEW)
        self._max_queue_length = max_queue_length
        self._discard_policy = discard_policy
        self._queue = deque(maxlen=max_queue_length)  # type: deque
        self._queue_cond = threading.Condition()
        self._receiver_seqnr = 0

    def discard_all(self) -> None:
        """Discard all pending signals currently waiting in the receive queue.

        This method is thread-safe.
        """
        with self._queue_cond:
            self._queue.clear()

    def has_signal_ready(self) -> bool:
        """Return `True` if at least one received signal is waiting in the receive queue.

        This method is thread-safe.
        """
        with self._queue_cond:
            return len(self._queue) != 0

    def get_queue_length(self) -> int:
        """Return the number of signals currently in the receive queue.

        This method is thread-safe. Note however that the queue length can
        change at any time due to actions of other threads.
        """
        with self._queue_cond:
            return len(self._queue)

    def get_next_signal(self, timeout: float | None = 0) -> ReceivedSignal:
        """Return the oldest published signal waiting in the receive queue.

        If there is no signal waiting in the queue, optionally wait until
        a new signal is received, subject to the specified timeout.

        This method is thread-safe.

        Parameters:
            timeout: Maximum time (in seconds) to wait for a new signal
                if the queue is empty, or None to wait indefinitely.

        Returns:
            `ReceivedSignal` tuple describing the received signal.

        Raises:
            QMI_TimeoutException: If the timeout expires before a signal is received.
            QMI_TaskStopException: If the calling task receives a stop request before a signal is received.
        """
        with self._queue_cond:
            if len(self._queue) == 0:
                predicate = lambda: (len(self._queue) > 0)
                if not _wait_for_condition(self._queue_cond, predicate, timeout):
                    raise QMI_TimeoutException("Timeout while waiting for signal")

            return self._queue.popleft()

    def _receive_signal(self, message: "QMI_SignalMessage") -> None:
        """Internal method to add a new received signal to the queue."""

        with self._queue_cond:
            sig = ReceivedSignal(
                publisher_context=message.source_address.context_id,
                publisher_name=message.source_address.object_id,
                signal_name=message.signal_name,
                args=message.args,
                receiver_seqnr=self._receiver_seqnr
            )
            self._receiver_seqnr += 1

            if len(self._queue) == self._max_queue_length:
                if self._discard_policy == self.DISCARD_NEW:
                    # Queue is full; ignore new signals.
                    return

            # Append new signal to queue.
            # If the queue is full, it will automatically discard the oldest signal.
            self._queue.append(sig)

            # Notify any thread waiting for a signal.
            self._queue_cond.notify_all()


class QMI_SignalMessage(QMI_Message):
    """Message sent to broadcast a signal between contexts.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.

    Attributes:
        signal_name: Name of the published signal.
            (The identity of the publisher follows from the `source_address` attribute.)
        args: Tuple of parameter values passed when publishing this signal.
    """

    __slots__ = ("signal_name", "args")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 signal_name: str,
                 args: tuple
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.signal_name = signal_name
        self.args = args


class QMI_SignalSubscriptionRequest(QMI_RequestMessage):
    """Message sent to subscribe or unsubscribe to a remote publisher.

    This message is sent to a remote `SignalManager` to subscribe or
    unsubscribe to the specified type of signal. The remote `SignalManager`
    will typically answer by sending a `QMI_SignalSubscriptionReply`.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.

    Attributes:
        publisher_name: Name of the RPC object that publishes the signal.
        signal_name: Signal name.
        subscribe: `True` to subscribe, `False` to unsubscribe.
    """

    __slots__ = ("publisher_name", "signal_name", "subscribe")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 publisher_name: str,
                 signal_name: str,
                 subscribe: bool
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.publisher_name = publisher_name
        self.signal_name = signal_name
        self.subscribe = subscribe


class QMI_SignalSubscriptionReply(QMI_ReplyMessage):
    """Message sent in response to a subscribe/unsubscribe request.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.

    Attributes:
        success: `True` if the request was processed successfully, `False` to indicate failure.
        error_msg: Short message describing the error, if `success` == `False`.
    """

    __slots__ = ("success", "error_msg")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 request_id: str,
                 success: bool,
                 error_msg: str
                 ) -> None:
        super().__init__(source_address, destination_address, request_id)
        self.success = success
        self.error_msg = error_msg


class QMI_SignalRemovedMessage(QMI_Message):
    """Message sent to remote subscribers when an object stops publishing a signal.

    This message is currently sent only when the RPC object that was publishing
    the signal is removed from QMI. In this case, multiple instances of
    `QMI_SignalRemovedMessage` may be sent, one for each signal type that was
    published by the removed object.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.

    Attributes:
        publisher_name: Name of the RPC object name that was publishing the signal.
        signal_name: Name of the signal that is no longer published.
    """

    __slots__ = ("publisher_name", "signal_name")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 publisher_name: str,
                 signal_name: str
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.publisher_name = publisher_name
        self.signal_name = signal_name


class _PendingSubscriptionRequest:
    """Helper object representing a pending subscription request sent to a remote context."""

    def __init__(self,
                 publisher_context: str,
                 publisher_name: str,
                 signal_name: str,
                 subscribe: bool
                 ) -> None:
        """Initialize a new pending subscription request.

        Parameters:
            publisher_context:  Context ID of the remote context containing the publisher.
            publisher_name:     Object ID of the remote publisher.
            signal_name:        Signal name of the signal to subscribe to.
            subscribe:          True when subscribing, False when unsubscribing.
        """
        self.publisher_context = publisher_context
        self.publisher_name = publisher_name
        self.signal_name = signal_name
        self.subscribe = subscribe
        self.receivers: set[QMI_SignalReceiver] = set()
        self._completed = threading.Event()
        self._success = False
        self._error_msg = ""

    def add_receiver(self, receiver: QMI_SignalReceiver) -> None:
        """Add a signal receiver to be added as local subscriber when the
        remote subscription request completes."""
        self.receivers.add(receiver)

    def set_reply(self, success: bool, error_msg: str) -> None:
        """Called when the reply is received.

        This will cause all current and future calls to the "wait()" method
        to complete and return the specified values.
        """
        assert not self._completed.is_set()
        self._success = success
        self._error_msg = error_msg
        self._completed.set()

    def wait(self) -> tuple[bool, str]:
        """Wait until a reply is received, then return (success, error_msg)."""
        self._completed.wait()
        return (self._success, self._error_msg)


class SignalManager(QMI_MessageHandler):
    """Keeps track of signal subscriptions and handles signal publishing.

    Each context owns exactly one SignalManager.

    The SignalManager registers itself as a MessageHandler to receive messages
    sent to the ``"$pubsub"`` object of the local context.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.
    """

    PUBSUB_OBJECT_ID = "$pubsub"

    def __init__(self, context: "qmi.core.context.QMI_Context"):
        """Initialize the signal manager and register as message handler."""

        address = QMI_MessageHandlerAddress(context.name, self.PUBSUB_OBJECT_ID)
        super().__init__(address)

        _logger.debug("SignalManager initializing")

        self._context = context

        # Mutex to guard manipulation of internal data structures.
        self._lock = threading.Lock()

        # Register of subscribers in the local context.
        # Map "<context>.<publisher>.<signal>" to a set of SignalReceiver objects.
        self._local_subscriptions: dict[str, set[QMI_SignalReceiver]] = {}

        # Register of remote subscribers to locally published signals.
        # Type: { "publisher_name": { "signal_name": set_of_context_names } }
        # Map "<publisher>.<signal>" to a set of remote context names.
        self._remote_subscriptions: dict[str, set[str]] = {}

        # Register of pending subscription requests by request ID.
        # Each pending subscription request is stored in this dictionary,
        # as well as in "_pending_subscription_request_by_signal_name".
        self._pending_subscription_request_by_request_id: dict[str, _PendingSubscriptionRequest] = {}

        # Register of pending subscription requests by signal name.
        # This is a mapping from "<context>.<publisher>.<signal>" to
        # a corresponding PendingSubscriptionRequest, if one exists.
        # Each pending subscription request is stored in this dictionary,
        # as well as in "_pending_subscription_request_by_request_id".
        self._pending_subscription_request_by_signal_name: dict[str, _PendingSubscriptionRequest] = {}

        context.register_message_handler(self)

    def subscribe_signal(self,
                         publisher_context: str,
                         publisher_name: str,
                         signal_name: str,
                         receiver: QMI_SignalReceiver) -> None:
        """Subscribe a SignalReceiver to a specified signal.

        This method blocks until the subscription is established.
        This method is thread-safe and may safely be called from any thread.

        Raises:
            QMI_UnknownNameException: When the specified publisher does not exist.
            QMI_MessageDeliveryException: When the subscription request can not be routed to a remote context.
        """

        if publisher_context == "":
            publisher_context = self._context.name
        if not is_valid_object_name(publisher_context):
            raise QMI_UsageException(f"Invalid context name {publisher_context!r}")
        if not is_valid_object_name(publisher_name):
            raise QMI_UsageException(f"Invalid publisher name {publisher_name!r}")
        if not is_valid_object_name(signal_name):
            raise QMI_UsageException(f"Invalid signal name {signal_name!r}")

        _logger.debug("Subscribing to signal %s.%s.%s", publisher_context, publisher_name, signal_name)

        if publisher_context == self._context.name:
            self._subscribe_local(publisher_context, publisher_name, signal_name, receiver)
        else:
            self._subscribe_remote(publisher_context, publisher_name, signal_name, receiver)

    def unsubscribe_signal(self,
                           publisher_context: str,
                           publisher_name: str,
                           signal_name: str,
                           receiver: QMI_SignalReceiver) -> None:
        """Unsubscribe a SignalReceiver from a specified signal.

        If the receiver is not currently subscribed to the specified signal,
        this function will do nothing.

        This method is thread-safe and may safely be called from any thread.
        """

        if publisher_context == "":
            publisher_context = self._context.name
        if not is_valid_object_name(publisher_context):
            raise QMI_UsageException(f"Invalid context name {publisher_context!r}")
        if not is_valid_object_name(publisher_name):
            raise QMI_UsageException(f"Invalid publisher name {publisher_name!r}")
        if not is_valid_object_name(signal_name):
            raise QMI_UsageException(f"Invalid signal name {signal_name!r}")

        _logger.debug("Unsubscribing from signal %s.%s.%s", publisher_context, publisher_name, signal_name)

        if publisher_context == self._context.name:
            self._remove_local_subscriber(publisher_context, publisher_name, signal_name, receiver)
        else:
            self._unsubscribe_remote(publisher_context, publisher_name, signal_name, receiver)

    def _add_local_subscriber(self,
                              publisher_context: str,
                              publisher_name: str,
                              signal_name: str,
                              receiver: QMI_SignalReceiver) -> None:
        """Add the receiver to the list of local subscribers."""
        full_name = publisher_context + "." + publisher_name + "." + signal_name
        with self._lock:
            lsubs = self._local_subscriptions.get(full_name)
            if lsubs is None:
                lsubs = set()
                self._local_subscriptions[full_name] = lsubs
            lsubs.add(receiver)

    def _remove_local_subscriber(self,
                                 publisher_context: str,
                                 publisher_name: str,
                                 signal_name: str,
                                 receiver: QMI_SignalReceiver) -> None:
        """Remove the receiver from the list of local subscribers."""
        full_name = publisher_context + "." + publisher_name + "." + signal_name
        with self._lock:
            lsubs = self._local_subscriptions.get(full_name)
            if lsubs is not None:
                lsubs.discard(receiver)
                if len(lsubs) == 0:
                    self._local_subscriptions.pop(full_name)

    def _add_remote_subscriber(self, publisher_name: str, signal_name: str, subscriber_context: str) -> None:
        full_name = publisher_name + "." + signal_name
        with self._lock:
            rsubs = self._remote_subscriptions.get(full_name)
            if rsubs is None:
                rsubs = set()
                self._remote_subscriptions[full_name] = rsubs
            rsubs.add(subscriber_context)

    def _remove_remote_subscriber(self, publisher_name: str, signal_name: str, subscriber_context: str) -> None:
        full_name = publisher_name + "." + signal_name
        with self._lock:
            rsubs = self._remote_subscriptions.get(full_name)
            if rsubs is not None:
                rsubs.discard(subscriber_context)
                if len(rsubs) == 0:
                    self._remote_subscriptions.pop(full_name)

    def _subscribe_local(self,
                         publisher_context: str,
                         publisher_name: str,
                         signal_name: str,
                         receiver: QMI_SignalReceiver
                         ) -> None:
        """Subscribe to a signal from a local publisher."""

        assert publisher_context == self._context.name

        # Check that the publisher exists as an RPC object.
        if self._context.get_rpc_object_descriptor(publisher_name) is None:
            raise QMI_SignalSubscriptionException(f"Unknown RPC object {publisher_context}.{publisher_name}")

        # Add the receiver to the list of local subscribers.
        self._add_local_subscriber(publisher_context, publisher_name, signal_name, receiver)

        # Check that the publisher still exists.
        if self._context.get_rpc_object_descriptor(publisher_name) is None:
            # Publisher vanished just before or after we subscribed. Undo the subscription.
            self._remove_local_subscriber(publisher_context, publisher_name, signal_name, receiver)

    def _send_subscription_request(self, request_message: QMI_SignalSubscriptionRequest) -> None:
        """Send a subscription request message to the remote context."""
        _logger.debug("Sending %s request for %s.%s.%s",
                      ("subscribe" if request_message.subscribe else "unsubscribe"),
                      request_message.destination_address.context_id,
                      request_message.publisher_name,
                      request_message.signal_name)
        try:
            self._context.send_message(request_message)
        except QMI_MessageDeliveryException as exc:
            # Failed to send the subscription request.
            # Handle this as if we received an error reply.
            self._handle_subscription_reply(request_message.request_id, False, str(exc))

    def _subscribe_remote(self,
                         publisher_context: str,
                         publisher_name: str,
                         signal_name: str,
                         receiver: QMI_SignalReceiver
                         ) -> None:
        """Subscribe to a signal from a remote publisher."""

        full_name = publisher_context + "." + publisher_name + "." + signal_name
        request_message = None

        with self._lock:

            # Check if there are other local subscribers for the same signal.
            lsubs = self._local_subscriptions.get(full_name)
            if lsubs:
                # There already are some local subscribers.
                # Just add this receiver to the list and we are subscribed.
                lsubs.add(receiver)
                return

            # Otherwise, check if there is a pending subscription request for this signal.
            pending_request = self._pending_subscription_request_by_signal_name.get(full_name)
            if pending_request is None:
                # Create a subscription request message.
                request_message = QMI_SignalSubscriptionRequest(
                    source_address=QMI_MessageHandlerAddress(self._context.name, self.PUBSUB_OBJECT_ID),
                    destination_address=QMI_MessageHandlerAddress(publisher_context, self.PUBSUB_OBJECT_ID),
                    publisher_name=publisher_name,
                    signal_name=signal_name,
                    subscribe=True)
                # Add the new request to the pending subscription table.
                pending_request = _PendingSubscriptionRequest(publisher_context, publisher_name, signal_name, True)
                self._pending_subscription_request_by_signal_name[full_name] = pending_request
                self._pending_subscription_request_by_request_id[request_message.request_id] = pending_request

            # Add this receiver to the pending subscription request.
            pending_request.add_receiver(receiver)

        # Send the remote subscription request, if needed.
        if request_message is not None:
            self._send_subscription_request(request_message)

        # Wait until the pending subscription request completes.
        (success, error_msg) = pending_request.wait()
        if not success:
            raise QMI_SignalSubscriptionException(error_msg)

    def _unsubscribe_remote(self,
                            publisher_context: str,
                            publisher_name: str,
                            signal_name: str,
                            receiver: QMI_SignalReceiver) -> None:
        """Unsubscribe a receiver from a signal published by a remote object."""

        full_name = publisher_context + "." + publisher_name + "." + signal_name
        request_message = None

        with self._lock:

            # Remove the local subscription on the specified signal.
            last_subscriber = False
            lsubs = self._local_subscriptions.get(full_name)
            if lsubs is not None:
                lsubs.discard(receiver)
                if len(lsubs) == 0:
                    self._local_subscriptions.pop(full_name)
                    last_subscriber = True

            if last_subscriber:
                # We have just removed the last remaining local subscriber.
                # Create a remote unsubscribe request (unless there is already
                # a remote subscription request in progress.)
                pending_request = self._pending_subscription_request_by_signal_name.get(full_name)
                if pending_request is None:
                    # Create an unsubscribe request message.
                    request_message = QMI_SignalSubscriptionRequest(
                        source_address=QMI_MessageHandlerAddress(self._context.name, self.PUBSUB_OBJECT_ID),
                        destination_address=QMI_MessageHandlerAddress(publisher_context, self.PUBSUB_OBJECT_ID),
                        publisher_name=publisher_name,
                        signal_name=signal_name,
                        subscribe=False)

                    # Add the new request to the pending subscription table.
                    pending_request = _PendingSubscriptionRequest(publisher_context,
                                                                  publisher_name,
                                                                  signal_name,
                                                                  False)
                    self._pending_subscription_request_by_signal_name[full_name] = pending_request
                    self._pending_subscription_request_by_request_id[request_message.request_id] = pending_request

        # Send the remote unsubscribe request, if needed.
        if request_message is not None:
            self._send_subscription_request(request_message)

    def _deliver_local(self, message: "QMI_SignalMessage") -> None:
        """Deliver a published message to local subscribers."""

        assert message.destination_address.context_id == self._context.name
        assert message.destination_address.object_id == self.PUBSUB_OBJECT_ID

        full_name = (message.source_address.context_id
                     + "." + message.source_address.object_id
                     + "." + message.signal_name)

        with self._lock:
            receiver_set = self._local_subscriptions.get(full_name)
            if receiver_set is None:
                receiver_list: list[QMI_SignalReceiver] = []
            else:
                receiver_list = list(receiver_set)

        for receiver in receiver_list:
            receiver._receive_signal(message)

    def publish_signal(self, publisher_name: str, signal_name: str, args: tuple) -> None:
        """Publish the specified signal to the QMI network."""

        if not is_valid_object_name(publisher_name):
            raise QMI_UsageException(f"Invalid publisher name {publisher_name!r}")
        if not is_valid_object_name(signal_name):
            raise QMI_UsageException(f"Invalid signal name {signal_name!r}")

        source_address = QMI_MessageHandlerAddress(self._context.name, publisher_name)

        # Local delivery of locally published signal.
        msg = QMI_SignalMessage(
            source_address=source_address,
            destination_address=QMI_MessageHandlerAddress(self._context.name, self.PUBSUB_OBJECT_ID),
            signal_name=signal_name,
            args=args
        )
        self._deliver_local(msg)

        # Remote delivery of locally published signal.
        full_name = publisher_name + "." + signal_name

        with self._lock:
            rsubs = self._remote_subscriptions.get(full_name)
            if rsubs is None:
                rsubs_list: list[str] = []
            else:
                # Copy list of subscribers to avoid race conditions.
                rsubs_list = list(rsubs)

        for sub in rsubs_list:
            msg = QMI_SignalMessage(
                source_address=source_address,
                destination_address=QMI_MessageHandlerAddress(sub, self.PUBSUB_OBJECT_ID),
                signal_name=signal_name,
                args=args
            )
            try:
                self._context.send_message(msg)
            except QMI_MessageDeliveryException:
                # Signal could not be delivered to remote context - ignore.
                _logger.debug("Can not send signal to remote context %s", sub, exc_info=True)

    def _handle_subscription_request(self, request_message: QMI_SignalSubscriptionRequest) -> None:
        """Called when we receive a subscribe/unsubscribe request from a remote subscriber.

        This function creates or removes an entry in the table of remote subscribers,
        then sends a reply message.
        """
        if request_message.source_address.object_id != self.PUBSUB_OBJECT_ID:
            raise QMI_RuntimeException("Unexpected SignalSubscriptionRequest from {}.{}"
                                       .format(request_message.source_address.context_id,
                                               request_message.source_address.object_id))

        publisher_name = request_message.publisher_name
        signal_name = request_message.signal_name
        subscriber_context = request_message.source_address.context_id

        _logger.debug("Got %s request from %s for %s.%s",
                      ("subscribe" if request_message.subscribe else "unsubscribe"),
                      subscriber_context, publisher_name, signal_name)

        if request_message.subscribe:
            # Check that the publisher exists as a local RPC object.
            if self._context.get_rpc_object_descriptor(publisher_name) is None:
                success = False
                error_msg = f"Unknown RPC object {self._context.name}.{publisher_name}"
            else:
                # Add the remote context to the table of remote subscribers.
                self._add_remote_subscriber(publisher_name, signal_name, subscriber_context)

                # Double-check that the publisher still exists.
                if self._context.get_rpc_object_descriptor(publisher_name) is None:
                    self._remove_remote_subscriber(publisher_name, signal_name, subscriber_context)
                    success = False
                    error_msg = f"Unknown RPC object {self._context.name}.{publisher_name}"
                else:
                    success = True
                    error_msg = ""
        else:
            # Unsubscribe. This is always successful.
            self._remove_remote_subscriber(publisher_name, signal_name, subscriber_context)
            success = True
            error_msg = ""

        # Send reply message.
        reply_message = QMI_SignalSubscriptionReply(
            source_address=request_message.destination_address,
            destination_address=request_message.source_address,
            request_id=request_message.request_id,
            success=success,
            error_msg=error_msg)
        try:
            self._context.send_message(reply_message)
        except QMI_MessageDeliveryException:
            # Ignore errors during reply delivery.
            pass

    def _handle_subscription_reply(self, request_id: str, success: bool, error_msg: str) -> None:
        """Called when we receive a reply to a pending subscribe/unsubscribe request.

        This function clears the pending subscription request and notifies any
        waiting threads that the subscription has completed.

        A special case occurs when an unsubscribe request has completed while
        there are already new subscribers waiting for the same signal. This
        is handled by immediately sending a new subscribe request.
        """
        with self._lock:
            # Find the pending subscription request and remove it from the table.
            pending_request = self._pending_subscription_request_by_request_id.pop(request_id)
            full_name = (pending_request.publisher_context
                         + "." + pending_request.publisher_name
                         + "." + pending_request.signal_name)
            self._pending_subscription_request_by_signal_name.pop(full_name)

            _logger.debug("Got reply to %s request for %s, status %s",
                          ("subscribe" if pending_request.subscribe else "unsubscribe"),
                          full_name, success)

            # On successful completion of a subscribe request, move the waiting
            # subscribers to the list of local subscribers for this signal.
            if pending_request.subscribe and success:
                lsubs = self._local_subscriptions.get(full_name)
                if lsubs:
                    lsubs.update(pending_request.receivers)
                else:
                    self._local_subscriptions[full_name] = pending_request.receivers

            # When a subscribe request completes, notify all waiting subscribers.
            if pending_request.subscribe:
                pending_request.set_reply(success, error_msg)

            request_message = None
            if (not pending_request.subscribe) and pending_request.receivers:
                # An unsubscribe request just completed, but there are already
                # new subscribers waiting for the same signal.
                # Immediately send a new subscription request.
                request_message = QMI_SignalSubscriptionRequest(
                    source_address=QMI_MessageHandlerAddress(self._context.name, self.PUBSUB_OBJECT_ID),
                    destination_address=QMI_MessageHandlerAddress(pending_request.publisher_context,
                                                                  self.PUBSUB_OBJECT_ID),
                    publisher_name=pending_request.publisher_name,
                    signal_name=pending_request.signal_name,
                    subscribe=True)
                # Add the new request to the pending subscription table.
                pending_request.subscribe = True
                self._pending_subscription_request_by_signal_name[full_name] = pending_request
                self._pending_subscription_request_by_request_id[request_message.request_id] = pending_request

        # Send the remote subscription request, if needed.
        if request_message is not None:
            self._send_subscription_request(request_message)

    def _handle_remote_signal_removed(self, message: QMI_SignalRemovedMessage) -> None:
        """Called when we receive a notification that a remote publisher has been removed.

        This function removes all local subscriptions on the removed signal.
        """
        publisher_context = message.source_address.context_id
        publisher_name = message.publisher_name
        signal_name = message.signal_name
        full_name = publisher_context + "." + publisher_name + "." + signal_name
        with self._lock:
            if full_name in self._local_subscriptions:
                self._local_subscriptions.pop(full_name)

    def handle_message(self, message: QMI_Message) -> None:
        """Handle messages sent to the signal manager object."""

        assert message.destination_address.context_id == self._context.name
        assert message.destination_address.object_id == self.PUBSUB_OBJECT_ID

        if ((not isinstance(message, QMI_SignalMessage))
                and (message.source_address.object_id != self.PUBSUB_OBJECT_ID)):
            raise QMI_RuntimeException("Unexpected message {} from {}.{}"
                                       .format(type(message).__name__,
                                               message.source_address.context_id,
                                               message.source_address.object_id))

        if isinstance(message, QMI_SignalMessage):
            self._deliver_local(message)
        elif isinstance(message, QMI_SignalSubscriptionRequest):
            self._handle_subscription_request(message)
        elif isinstance(message, QMI_SignalSubscriptionReply):
            self._handle_subscription_reply(message.request_id, message.success, message.error_msg)
        elif isinstance(message, QMI_ErrorReplyMessage):
            self._handle_subscription_reply(message.request_id, False, message.error_msg)
        elif isinstance(message, QMI_SignalRemovedMessage):
            self._handle_remote_signal_removed(message)
        else:
            raise QMI_RuntimeException(f"Unexpected message type {type(message).__name__}")

    def handle_object_removed(self, rpc_object_name: str) -> None:
        """Called when a local RPC object is removed.

        This function drops any local subscriptions on signals published by
        the removed object. This function also drops any remote subscribers
        on signals published by the removed object, and notifies the remote
        subscribers that the signal has been removed.
        """
        with self._lock:
            # Drop any local subscriptions on signals published by the removed object.
            # This is potentially slow.
            pattern = self._context.name + "." + rpc_object_name + "."
            remove_entries = []
            for full_name in self._local_subscriptions:
                if full_name.startswith(pattern):
                    remove_entries.append(full_name)
            for full_name in remove_entries:
                self._local_subscriptions.pop(full_name)

            # Drop any remote subscribers in the removed peer context.
            # This is potentially slow.
            pattern = rpc_object_name + "."
            remove_entries = []
            notify_subscribers = []
            for full_name in self._remote_subscriptions:
                if full_name.startswith(pattern):
                    remove_entries.append(full_name)
            for full_name in remove_entries:
                rsubs = self._remote_subscriptions.pop(full_name)
                (_publisher_name, signal_name) = full_name.split(".")
                for subscriber_context in rsubs:
                    notify_subscribers.append((signal_name, subscriber_context))

        # Notify remote subscribers that these signals have been removed.
        for (signal_name, subscriber_context) in notify_subscribers:
            _logger.debug("Sending signal removed notification to %s for %s.%s",
                          subscriber_context, rpc_object_name, signal_name)
            message = QMI_SignalRemovedMessage(
                source_address=QMI_MessageHandlerAddress(self._context.name, self.PUBSUB_OBJECT_ID),
                destination_address=QMI_MessageHandlerAddress(subscriber_context, self.PUBSUB_OBJECT_ID),
                publisher_name=rpc_object_name,
                signal_name=signal_name)
            try:
                self._context.send_message(message)
            except QMI_MessageDeliveryException as exc:
                # Ignore errors during message delivery.
                pass

    def handle_peer_context_removed(self, context_name: str) -> None:
        """Update remote signal administration after disconnecting a peer context.

        This method is called by the socket manager when a peer connection
        (outgoing or incoming) is closed. This method drops any remote subscribers
        in the removed context. This method also drops any local subscriptions
        on signals published by the removed context.
        """
        with self._lock:
            # Drop any remote subscribers in the removed peer context.
            # This is potentially slow, but disconnecting from a peer context should not occur very frequently.
            remove_entries = []
            for (full_name, rsubs) in self._remote_subscriptions.items():
                if context_name in rsubs:
                    rsubs.remove(context_name)
                    if len(rsubs) == 0:
                        remove_entries.append(full_name)
            for full_name in remove_entries:
                self._remote_subscriptions.pop(full_name)

            # Drop any local subscriptions on signals published by the remote context.
            # This is potentially slow.
            pattern = context_name + "."
            remove_entries = []
            for full_name in self._local_subscriptions:
                if full_name.startswith(pattern):
                    remove_entries.append(full_name)
            for full_name in remove_entries:
                self._local_subscriptions.pop(full_name)


# Imports needed only for static typing.
if TYPE_CHECKING:
    import qmi.core.context
