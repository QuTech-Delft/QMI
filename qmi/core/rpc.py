"""Remote Procedure Call mechanism for QMI.

This module provides support for Remote Procedure Calls: calling methods
on an object that exists in a different QMI context.

Defining RPC methods
####################

Only classes that inherit `QMI_RpcObject` can define RPC methods.
Within such a class, use the `@rpc_method` decorator to mark a method as
RPC-callable. Note that `QMI_Instrument` inherits `QMI_RpcObject`, therefore
instrument drivers are able to define RPC methods.

For example, the following fragment defines an RPC-callable method `MyClass.square`::

  class MyClass(QMI_RpcObject):

      def __init__(self, context, name, ...):
          super().__init__(context, name)

      @rpc_method
      def square(self, x):
          return x * x

Some restrictions apply to the types of data that can be passed in and out
of RPC methods: Parameters passed to an RPC method and return values or
exceptions produced by an RPC method must be `pickle-able`, i.e. the
Python `pickle` module must be able to serialize the data types used.

* Built-in types are generally pickle-able.
* Custom defined value-like types such as enums, named tuples and exceptions,
  are generally pickle-able provided that the type definition can be imported
  by the receiving program. This implies that such types must be defined
  in a Python module, not in a top-level Python script.
* Numpy arrays are pickle-able.
* Other kinds of custom defined classes are generally not pickle-able.

Calling RPC methods
###################

Classes that inherit `QMI_RpcObject` are instantiated via the QMI context.
The context then returns a `proxy` for the new object instance.

RPC methods can be called by simply invoking a method with the same name
on the proxy. The RPC mechanism translates this into a call to the real method
on the real object. The return value from the real method is passed back as
the return value from the proxy call.

For example::

    proxy = qmi.context().make_rpc_object("my_object", MyClass, ...)
    y = proxy.square(5)

It is also possible to create a proxy for an object in a different QMI context.
In this case, calling a method on the proxy will cause the method with the same
name to run in the remote context::

    proxy = qmi.context().get_rpc_object_by_name("other_context.my_object")
    y = proxy.square(5)

Locking RPC objects
###################

Class that inherit from `QMI_RpcObject` are lockable. This means that only the
proxy that owns the lock (i.e. that acquired it) can invoke RPC methods. Other
proxies will not be able to call any RPC method until the object is unlocked.
An example use case is where you have a script running to do some measurement
and you want to avoid that a GUI or automatic calibration interferes with that
measurement: in that case you can have the script lock the instruments.

Example::

    proxy = qmi.context().get_rpc_object_by_name("other_context.my_object")
    proxy.lock()  # object is now locked
    # do things ...
    proxy.unlock()

You can query if an object is locked via `is_locked()`. If for whatever reason
an object is locked and the proxy that owns the locked no longer exists, you
can force unlock the object via `force_unlock()`; use this with care!

The normal proxy locking is available only within the same context for the same proxy.
Since QMI V0.29.1 it is also possible to lock and unlock with a custom token from
other proxies as well, as long as the contexts for the other proxies have the same name.

Example 1::

    # Two proxies in same context.
    proxy1 = context.make_rpc_object("my_object", MyRpcTestClass)
    proxy2 = context.get_rpc_object_by_name("my_context.my_object")
    custom_token = "thisismineallmine"

    proxy1.lock(lock_token=custom_token)
    proxy2.is_locked()  # Returns True
    proxy2.unlock(lock_token=custom_token)
    proxy2.is_locked()  # Returns False

Example 2::

    # Three proxies in different contexts. The first one serves as an "object provider".
    c1 = QMI_Context("c1", config)
    c1.start()
    c1_port = c1.get_tcp_server_port()
    c1_address = "localhost:{}".format(c1_port)
    # Instantiate class in context c1 as object provider.
    proxy1 = c1.make_rpc_object("tc1", MyRpcTestClass)

    # Now make another context, and get a proxy to the object
    custom_token = "block"
    c2 = QMI_Context("c2", config)
    c2.start()
    c2.connect_to_peer("c1", c1_address)
    proxy2 = c2.get_rpc_object_by_name("c1.tc1")
    proxy2.is_locked()  # Returns False
    proxy2.lock(lock_token=custom_token)
    proxy2.is_locked()  # Returns True
    # And then close it
    c2.stop()

    # Then start third context with the same name as second context, obtain the object and unlock it.
    c3 = QMI_Context("c2", config)
    c3.start()
    c3.connect_to_peer("c1", c1_address)
    proxy3 = c3.get_rpc_object_by_name("c1.tc1")
    proxy3.is_locked()  # Returns True
    proxy3.unlock()  # Returns False as it fails without the correct token
    proxy3.unlock(lock_token=custom_token)  # Now succeeds and returns True
    proxy3.is_locked()  # Returns False
    # And then close it
    c3.stop()

    # Then finally stop the "object provider"
    c1.stop()

Reference
#########
"""

import inspect
import logging
import threading
import time
import enum
from abc import ABCMeta
from collections import deque
from collections.abc import Callable

from typing import Any, NamedTuple, Type, TypeVar, TYPE_CHECKING

from qmi.core.exceptions import (
    QMI_RuntimeException,
    QMI_UsageException,
    QMI_MessageDeliveryException,
    QMI_RpcTimeoutException,
    QMI_UnknownRpcException)
from qmi.core.messaging import (
    QMI_Message, QMI_RequestMessage, QMI_ReplyMessage, QMI_ErrorReplyMessage,
    QMI_MessageHandler, QMI_MessageHandlerAddress)
from qmi.core.pubsub import SignalDescription, QMI_Signal, QMI_RegisteredSignal, QMI_SignalSubscriber
from qmi.core.thread import QMI_Thread
from qmi.core.util import is_valid_object_name


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Unbound type variable for type annotations.
_T = TypeVar("_T")


class RpcConstantDescriptor(NamedTuple):
    """Description of an RPC constant.

    Attributes:
        name: Name of the constant.
        value: Value of the constant.
    """
    name: str
    value: Any


class RpcMethodDescriptor(NamedTuple):
    """Description of an RPC method.

    Attributes:
        name: Name of the RPC method.
        signature: String representation of the signature of the RPC method,
            including type annotations.
        docstring: Docstring of the RPC method.
    """
    name: str
    signature: str
    docstring: str


class RpcSignalDescriptor(NamedTuple):
    """Description of a QMI signal.

    Attributes:
        name: Name of the signal.
        arg_types: String representation of the list of argument types.
    """
    name: str
    arg_types: str


class RpcInterfaceDescriptor(NamedTuple):
    """Description of the subset of the interface of an RPC object class that
    can be accessed via RPC. This includes the methods marked using the
    `@rpc_method` decorator and the signals declared by the RPC object class or
    a delegate class.

    Attributes:
        rpc_class_module: Name of the module in which the RPC object class was
            defined.
        rpc_class_name: Name of the RPC object class.
        rpc_class_docstring: Docstring of the RPC object class.
        constants: A list of constant descriptors for the RPC constants declared
            by the RPC object class.
        methods: A list of method descriptors for the RPC methods declared by
            the RPC object class.
        signals: A list of signal descriptors for the signals declared by the
            RPC object class or a delegate class.
    """
    rpc_class_module: str
    rpc_class_name: str
    rpc_class_docstring: str | None
    constants: list[RpcConstantDescriptor]
    methods: list[RpcMethodDescriptor]
    signals: list[RpcSignalDescriptor]


class RpcObjectDescriptor(NamedTuple):
    """Description of an RPC object instance.

    Attributes:
        address: Unique address of the RPC object.
        category: Free-form name of the category of objects this RPC object
            belongs to.
        interface: Description of the subset of the interface of the RPC object
            that can be accessed via RPC, including signals.
    """
    address: QMI_MessageHandlerAddress
    category: str | None
    interface: RpcInterfaceDescriptor


class QMI_LockTokenDescriptor(NamedTuple):
    """Unique lock token that is used to lock/unlock RPC objects.

    Attributes:
        context_id: Name of the context that owns the RPC proxy that requested the lock.
        token:      Unique token.
    """
    context_id: str
    token: str


class QMI_RpcFutureState(enum.Enum):
    """Possible states of an QMI_RpcFuture instance."""
    NO_RESULT_YET = 1
    RESULT_IS_VALUE = 2
    RESULT_IS_EXCEPTION = 3
    OBJECT_IS_LOCKED = 4


class QMI_LockRpcAction(enum.Enum):
    """Actions that can be performed on a lock."""
    ACQUIRE = 1
    RELEASE = 2
    FORCE_RELEASE = 3
    QUERY = 4


# These "token" is returned when a lock is queried by a proxy that does not own the lock.
ACCESS_DENIED_TOKEN_PLACEHOLDER = "__ACCESS_DENIED__"
OBJECT_LOCKED_TOKEN_PLACEHOLDER = "__OBJECT_LOCKED__"


class QMI_LockRpcRequestMessage(QMI_RequestMessage):
    """Message sent by an RPC client to interact with the lock state of a remote object.

    See `QMI_LockRpcReplyMessage` for how to interpret the reply to a request.

    Attributes:
        lock_token:     The unique token to use for the lock.
        lock_action:    The action to be performed on the lock state.
    """
    __slots__ = ("lock_token", "lock_action")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 lock_token: QMI_LockTokenDescriptor | None,
                 lock_action: QMI_LockRpcAction
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.lock_token = lock_token
        self.lock_action = lock_action


class QMI_LockRpcReplyMessage(QMI_ReplyMessage):
    """Message sent back to an RPC client with the result of the action.

    The reply only contains a lock token (an actual token or a placeholder), indicating if the request was successful
    and what the state of the object lock is after the request.

    Specifically:
     - if you requested a lock and the returned token matches your token, you now own the lock;
     - if your requested to unlock and the returned token is None, the unlock was successful;
     - if your queried the lock status and the returned token is not None when the object is locked and None if the
       object is unlocked;
     - in all other cases, the request was denied.

    Attributes:
        lock_token: The unique token that locked the object.
    """
    __slots__ = ("lock_token",)

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 request_id: str,
                 lock_token: QMI_LockTokenDescriptor | None
                 ) -> None:
        super().__init__(source_address, destination_address, request_id)
        self.lock_token = lock_token


class QMI_MethodRpcRequestMessage(QMI_RequestMessage):
    """Message sent by an RPC client to invoke a remote method.

    Attributes:
        method_name:    Name of the method to invoke.
        method_args:    Tuple of positional arguments to the method.
        method_kwargs:  Dictionary of keyword arguments to the method.
        lock_token:     The unique token to use for the lock.
    """
    __slots__ = ("method_name", "method_args", "method_kwargs", "lock_token")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 method_name: str,
                 method_args: tuple,
                 method_kwargs: dict,
                 lock_token: QMI_LockTokenDescriptor | None = None
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.method_name = method_name
        self.method_args = method_args
        self.method_kwargs = method_kwargs
        self.lock_token = lock_token


class QMI_MethodRpcReplyMessage(QMI_ReplyMessage):
    """Message sent back to an RPC client with the result of a remote method invocation.

    Attributes:
        state: Either `RESULT_IS_VALUE`, `RESULT_IS_EXCEPTION` or `OBJECT_IS_LOCKED`.
        result: Return value from the method or exception raised by the method.
    """
    __slots__ = ("state", "result")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 request_id: str,
                 state: QMI_RpcFutureState,
                 result: Any
                 ) -> None:
        super().__init__(source_address, destination_address, request_id)
        self.state = state
        self.result = result


class QMI_RpcFuture(QMI_MessageHandler):
    """Representation of the future completion of a method invoked via RPC.

    An instance of `QMI_RpcFuture` is created when a call to an RPC method
    is dispatched. The future is completed when the RPC method finishes
    running. This happens asynchronously, because the real RPC method
    execution happens in a background thread.

    This class is used internally when the application invokes a method
    on an RPC proxy object. In this case the proxy method will block until
    the future is completed. Alternatively, when the application invokes
    a non-blocking RPC call, the proxy method returns an instance of this
    class without waiting for the real method call to end.
    """

    def __init__(self,
                 context: "qmi.core.context.QMI_Context",
                 rpc_object_address: QMI_MessageHandlerAddress,
                 lock_token: QMI_LockTokenDescriptor | None,
                 ) -> None:
        future_address = context.make_unique_address("$future_")
        super().__init__(future_address)

        self._result = None
        self._context = context  # The context that manages us.
        self._state = QMI_RpcFutureState.NO_RESULT_YET
        self._cv = threading.Condition(threading.Lock())
        self.rpc_object_address = rpc_object_address
        self.lock_token = lock_token

        context.register_message_handler(self)

    def send_method_rpc_request_message(self,
                                        rpc_method_name: str,
                                        rpc_method_args: tuple,
                                        rpc_method_kwargs: dict
                                        ) -> None:
        """Send a request message to the RPC object to invoke the specified method.

        Parameters:
            rpc_method_name: Name of the method to call.
            rpc_method_args: Tuple of positional arguments.
            rpc_method_kwargs: Dictionary of keyword arguments.
        """
        request = QMI_MethodRpcRequestMessage(
            self.address,
            self.rpc_object_address,
            rpc_method_name,
            rpc_method_args,
            rpc_method_kwargs,
            self.lock_token
        )

        try:
            self._context.send_message(request)
        except QMI_MessageDeliveryException as exc:
            self._set_result(QMI_RpcFutureState.RESULT_IS_EXCEPTION, exc)

    def send_lock_rpc_request_message(self, action: QMI_LockRpcAction) -> None:
        request = QMI_LockRpcRequestMessage(self.address, self.rpc_object_address, self.lock_token, action)
        try:
            self._context.send_message(request)
        except QMI_MessageDeliveryException as exc:
            self._set_result(QMI_RpcFutureState.RESULT_IS_EXCEPTION, exc)

    def handle_message(self, message: QMI_Message) -> None:
        """Called when a reply message is received."""

        if isinstance(message, QMI_MethodRpcReplyMessage):
            # Received result from RPC call.
            self._set_result(message.state, message.result)
        elif isinstance(message, QMI_LockRpcReplyMessage):
            # Response to lock request message.
            self._set_result(QMI_RpcFutureState.RESULT_IS_VALUE, message.lock_token)
        elif isinstance(message, QMI_ErrorReplyMessage):
            # Delivery of RPC request failed.
            self._set_result(QMI_RpcFutureState.RESULT_IS_EXCEPTION,
                             QMI_MessageDeliveryException(message.error_msg))
        else:
            _logger.error("Future for %s.%s received unexpected message type %r",
                          self.rpc_object_address.context_id,
                          self.rpc_object_address.object_id,
                          type(message))

    def _set_result(self, state: QMI_RpcFutureState, result: Any) -> None:
        """Store the result received from the RPC reply and wake up any task waiting for this result."""
        if state not in (QMI_RpcFutureState.RESULT_IS_EXCEPTION,
                         QMI_RpcFutureState.RESULT_IS_VALUE,
                         QMI_RpcFutureState.OBJECT_IS_LOCKED):
            _logger.error("Future for %s.%s received unexpected state %r",
                          self.rpc_object_address.context_id,
                          self.rpc_object_address.object_id,
                          state)
            return

        with self._cv:
            if self._state != QMI_RpcFutureState.NO_RESULT_YET:
                _logger.error("Future for %s.%s received duplicate reply message",
                              self.rpc_object_address.context_id,
                              self.rpc_object_address.object_id)
                return

            self._state = state
            self._result = result
            self._cv.notify_all()

    def wait(self, timeout: float | None = None) -> Any:
        """Wait until the RPC call completes.

        Parameters:
            timeout: Maximum wait time in seconds, or None to wait forever.

        Returns:
            The return value from the associated RPC method call.

        Raises:
            QMI_RpcTimeoutException: If the timeout expires before the RPC call completes.
            Exception: If the associated RPC method call raised an exception.
        """
        if timeout is not None:
            time_limit = time.monotonic() + timeout

        try:
            with self._cv:
                while True:
                    # Check state of the future.
                    if self._state == QMI_RpcFutureState.RESULT_IS_EXCEPTION:
                        if not isinstance(self._result, BaseException):
                            raise QMI_RuntimeException("Received invalid exception value from RPC call")
                        raise self._result

                    if self._state == QMI_RpcFutureState.RESULT_IS_VALUE:
                        return self._result
                    elif self._state == QMI_RpcFutureState.OBJECT_IS_LOCKED:
                        raise QMI_RuntimeException("The object is locked by another proxy")
                    else:
                        # No result yet.
                        pass

                    # No result yet, see if we are supposed to wait longer.
                    if timeout is None:
                        wait_result = self._cv.wait(timeout)
                    else:
                        wait_result = self._cv.wait(max(0.0, time_limit - time.monotonic()))

                    if not wait_result:
                        # Timeout expired!
                        raise QMI_RpcTimeoutException("Timeout in RPC call.")

        finally:
            # The QMI_RpcFuture has now become useless.
            self._context.unregister_message_handler(self)


def non_blocking_rpc_method_call(context: "qmi.core.context.QMI_Context",
                                 rpc_object_address: QMI_MessageHandlerAddress,
                                 method_name: str,
                                 rpc_lock_token: QMI_LockTokenDescriptor | None,
                                 *args: Any,
                                 **kwargs: Any
                                 ) -> Any:
    """Helper function that performs a non-blocking call to a specific method of the target RPC object."""
    if "rpc_timeout" in kwargs:
        raise RuntimeError("rpc_timeout parameter makes no sense for non-blocking invocation.")

    future = QMI_RpcFuture(context, rpc_object_address, rpc_lock_token)
    future.send_method_rpc_request_message(method_name, args, kwargs)
    return future


def blocking_rpc_method_call(context: "qmi.core.context.QMI_Context",
                             rpc_object_address: QMI_MessageHandlerAddress,
                             method_name: str,
                             rpc_lock_token: QMI_LockTokenDescriptor | None,
                             *args: Any,
                             rpc_timeout: float | None = None,
                             **kwargs: Any
                             ) -> Any:
    """Helper function that performs a blocking call to a specific method of the target RPC object."""
    future = QMI_RpcFuture(context, rpc_object_address, rpc_lock_token)
    future.send_method_rpc_request_message(method_name, args, kwargs)
    return future.wait(rpc_timeout)


class QMI_RpcNonBlockingProxy:
    """Proxy class for RPC objects that performs non-blocking calls. Direct instantiation is not recommended.

    This is always also instantiated in `QMI_RpcProxy` as `self.rpc_nonblocking` attribute. Typically, if user wants
    to use a non-blocking call with an RPC object `rpc_proxy`, they would do:
    ```python
    future = rpc_proxy.rpc_nonblocking.some_rpc_command(args)
    # Other stuff can be done here in the meanwhile, and the `proxy` is not blocked while waiting to return
    retval = future.wait()
    ```
    Instead of the usual
    ```python
    retval = rpc_proxy.some_rpc_commands(args)
    ```
    """

    def __init__(self, context: "qmi.core.context.QMI_Context", descriptor: RpcObjectDescriptor) -> None:

        self._context = context
        self._rpc_object_address = descriptor.address
        self._rpc_class_fqn = ".".join((descriptor.interface.rpc_class_module, descriptor.interface.rpc_class_name))
        self._lock_token: QMI_LockTokenDescriptor | None = None

        # Set docstring.
        setattr(self, "__doc__", descriptor.interface.rpc_class_docstring)

        # Helper function used to create a new scope such that each method created in the loop below uses the intended
        # method name.
        def make_rpc_forward_function(method_name: str):
            return lambda self, *args, **kwargs: \
                non_blocking_rpc_method_call(self._context, self._rpc_object_address, method_name,
                                             self._lock_token, *args, **kwargs)

        # Add methods.
        for method_descriptor in descriptor.interface.methods:
            # Generate a function that forward calls to itself to the corresponding RPC method of the peer context.
            method = make_rpc_forward_function(method_descriptor.name)

            # Update special attributes to make the forward function look like the method it is a proxy for.
            docstring = "rpc proxy for {}{} method of {} instance".format(method_descriptor.name,
                                                                          method_descriptor.signature,
                                                                          self._rpc_class_fqn)

            if method_descriptor.docstring:
                docstring = docstring + "\n\n" + method_descriptor.docstring

            setattr(method, "__name__", method_descriptor.name)
            setattr(method, "__qualname__", type(self).__name__ + "." + method_descriptor.name)
            setattr(method, "__doc__", docstring)

            # Invoke the __get__() descriptor function to create a bound method and attach it to the proxy instance
            # as an attribute.
            setattr(self, method_descriptor.name, method.__get__(self))

    def __repr__(self) -> str:
        return f"<non-blocking rpc proxy for {self._rpc_object_address} ({self._rpc_class_fqn})>"


class QMI_RpcProxy:
    """Proxy class for RPC objects that performs blocking calls. All RPC objects created return this proxy class to
    enable RPC communication between objects.

    Direct instantiation of this class is not meant to be done by users; internal use only!
    """

    def __init__(self, context: "qmi.core.context.QMI_Context", descriptor: RpcObjectDescriptor) -> None:

        self._context = context
        self._rpc_object_address = descriptor.address
        self._rpc_class_fqn = ".".join((descriptor.interface.rpc_class_module, descriptor.interface.rpc_class_name))
        self._lock_token: QMI_LockTokenDescriptor | None = None

        # Helper function used to create a new scope such that each method created in the loop below uses the intended
        # method name.
        def make_rpc_forward_function(method_name: str):
            return lambda self, *args, **kwargs: \
                blocking_rpc_method_call(self._context, self._rpc_object_address, method_name, self._lock_token,
                                         *args, **kwargs)

        # Set docstring.
        setattr(self, "__doc__", descriptor.interface.rpc_class_docstring)

        # Add constants.
        for constant_descriptor in descriptor.interface.constants:
            setattr(self, constant_descriptor.name, constant_descriptor.value)

        # Add methods.
        for method_descriptor in descriptor.interface.methods:
            # Generate a function that forward calls to itself to the corresponding RPC method of the peer context.
            method = make_rpc_forward_function(method_descriptor.name)

            # Update special attributes to make the forward function look like the method it is a proxy for.
            docstring = "rpc proxy for {}{} method of {} instance".format(method_descriptor.name,
                                                                          method_descriptor.signature,
                                                                          self._rpc_class_fqn)
            if method_descriptor.docstring:
                docstring = docstring + "\n\n" + method_descriptor.docstring

            setattr(method, "__name__", method_descriptor.name)
            setattr(method, "__qualname__", type(self).__name__ + "." + method_descriptor.name)
            setattr(method, "__doc__", docstring)

            # Invoke the __get__() descriptor function to create a bound method and attach it to the proxy instance
            # as an attribute.
            setattr(self, method_descriptor.name, method.__get__(self))

        # Add signals.
        for signal_descriptor in descriptor.interface.signals:
            subscriber = QMI_SignalSubscriber(
                self._context,
                self._rpc_object_address.context_id,
                self._rpc_object_address.object_id,
                signal_descriptor.name,
                signal_descriptor.arg_types
            )
            setattr(self, signal_descriptor.name, subscriber)

        # Add non-blocking proxy.
        self.rpc_nonblocking = QMI_RpcNonBlockingProxy(context, descriptor)

    def __enter__(self) -> "QMI_RpcProxy":
        """The context manager definition is needed for the proxy as it will always be returned from QMI contexts,
        instead of the actual RPC object instance. Trying to use context management directly on this class will
        cause recursion error, but for actual RPC objects not.

        The with keyword checks if the `QMI_RpcProxy` class (not instance) implements the context manager protocol,
        i.e. `__enter__` and `__exit__`, so they exist here as stubs. These stubs make an RPC to the actual `__enter__`
        and `__exit__` methods on the relevant RPC object. If in those classes `__enter__` and `__exit__` are
        decorated as `rpc_methods`, we do not see a recursion error. See for further details in:
        https://docs.python.org/3/reference/datamodel.html#special-method-lookup

        `rpc_method` decorated `__enter__` and `__exit__` methods are currently implemented in `QMI_Instrument` and
        `QMI_TaskRunner` classes.
        """
        self.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.__exit__()
        return

    def __repr__(self) -> str:
        return f"<rpc proxy for {self._rpc_object_address} ({self._rpc_class_fqn})>"

    @property
    def address(self) -> str:
        """Return the "address" of the proxy with context name and object name.

        Returns:
            String "{context name}.{name}".
        """
        return str(self._rpc_object_address)

    def lock(self, timeout: float = 0.0, lock_token: str | None = None) -> bool:
        """Substitutes the `lock` method stub of QMI_RpcObject."""
        # Create a lock token for this proxy and try to lock the object.
        their_lock_token = "None"
        if lock_token is not None:
            my_lock_token = QMI_LockTokenDescriptor(self._context.name, lock_token)

        else:
            my_lock_token = self._context.make_unique_token(prefix="$lock_")

        if timeout > 0.0:
            hardcoded_period = 0.1  # minimum time period for tries within timeout: timeout < 0.1 is practically 0.1.
            time_start = time.monotonic()
            while (time.monotonic() - time_start) < timeout:
                loop_start = time.monotonic()
                future = QMI_RpcFuture(self._context, self._rpc_object_address, my_lock_token)
                future.send_lock_rpc_request_message(QMI_LockRpcAction.ACQUIRE)

                # If the lock is granted, the returned lock token matches our lock token.
                their_lock_token = future.wait()
                if their_lock_token == my_lock_token:
                    _logger.debug("%s locked with %s", self._rpc_object_address, my_lock_token)
                    self._lock_token = my_lock_token
                    self.rpc_nonblocking._lock_token = my_lock_token
                    return True

                loop_end = time.monotonic()
                if (loop_end - loop_start) < hardcoded_period:
                    time.sleep(hardcoded_period - (loop_end - loop_start))

        else:
            # Just try once
            future = QMI_RpcFuture(self._context, self._rpc_object_address, my_lock_token)
            future.send_lock_rpc_request_message(QMI_LockRpcAction.ACQUIRE)

            # If the lock is granted, the returned lock token matches our lock token.
            their_lock_token = future.wait()
            if their_lock_token == my_lock_token:
                _logger.debug("%s locked with %s", self._rpc_object_address, my_lock_token)
                self._lock_token = my_lock_token
                self.rpc_nonblocking._lock_token = my_lock_token
                return True

        _logger.debug("%s lock denied, already locked with %s", self._rpc_object_address, their_lock_token)
        return False

    def unlock(self, lock_token: str | None = None) -> bool:
        """Substitutes the `unlock` method stub of QMI_RpcObject."""
        if lock_token is not None:
            # Try to unlock with the custom lock token.
            my_lock_token = QMI_LockTokenDescriptor(self._context.name, lock_token)
            future = QMI_RpcFuture(self._context, self._rpc_object_address, my_lock_token)

        else:
            # Try to unlock the object with this proxy's lock token.
            future = QMI_RpcFuture(self._context, self._rpc_object_address, self._lock_token)

        future.send_lock_rpc_request_message(QMI_LockRpcAction.RELEASE)

        # If the token was accepted, the returned lock token matches our lock token (or theirs is None if the object
        # was not even locked).
        their_lock_token = future.wait()
        if their_lock_token is None:
            _logger.debug("%s unlocked with %s", self._rpc_object_address, self._lock_token)
            self._lock_token = None  # do not reuse tokens
            self.rpc_nonblocking._lock_token = None
            return True
        else:
            _logger.debug("%s unlock with %s denied, locked with %s", self._rpc_object_address, self._lock_token,
                          their_lock_token)
            return False

    def force_unlock(self) -> None:
        """Substitutes the `force_unlock` method stub of QMI_RpcObject."""
        # Send force-release message.
        future = QMI_RpcFuture(self._context, self._rpc_object_address, self._lock_token)
        future.send_lock_rpc_request_message(QMI_LockRpcAction.FORCE_RELEASE)

        # Check that the lock was removed (token is None).
        their_lock_token = future.wait()
        if their_lock_token is None:
            _logger.debug("%s unlocked forcefully", self._rpc_object_address)
            self._lock_token = None
            self.rpc_nonblocking._lock_token = None
        else:
            _logger.warning("%s force unlock failed!", self._rpc_object_address)

    def is_locked(self) -> bool:
        """Substitutes the `is_locked` method stub of QMI_RpcObject."""
        # Send query.
        future = QMI_RpcFuture(self._context, self._rpc_object_address, self._lock_token)
        future.send_lock_rpc_request_message(QMI_LockRpcAction.QUERY)

        # If the object is lock, it will have a lock token set.
        lock_token = future.wait()
        return lock_token is not None


def rpc_method(method: _T) -> _T:
    """Decorator to indicate that a method can be called via RPC."""
    method._rpc_method = True  # type: ignore
    return method


def is_rpc_method(object: Any) -> bool:
    """Return True if the object is a method that can be called via RPC."""
    return inspect.isfunction(object) and getattr(object, "_rpc_method", False)


class _RpcObjectMetaClass(ABCMeta):
    """Meta-class used to create `QMI_RpcObject` and its subclasses.

    This meta-class extracts a list of signals published by the class.
    The list of signals is inserted as a class attribute named `_qmi_signals`.
    """

    def __init__(cls, name: str, bases: tuple, dct: dict) -> None:

        # Let "type" do its thing.
        super().__init__(name, bases, dct)

        # The original class must not yet have a _qmi_signals attribute.
        assert "_qmi_signals" not in dct

        # Scan the newly created QMI_RpcObject subclass for class attributes of type QMI_Signal.
        # These are markers to announce signals that the class may publish.
        signals = []
        for attr_name, attr_value in inspect.getmembers(cls, lambda member: isinstance(member, QMI_Signal)):
            if not is_valid_object_name(attr_name):
                raise QMI_UsageException(f"Invalid signal name {attr_name!r} in class {cls.__name__}")

            signals.append(SignalDescription(name=attr_name, arg_types=attr_value.arg_types))

        # Add the list of signals as an attribute of the newly created QMI_RpcObject subclass.
        cls._qmi_signals = tuple(signals)


class QMI_RpcObject(metaclass=_RpcObjectMetaClass):
    """Base class for classes which expose (a subset of) their methods via RPC.

    Each instance of `QMI_RpcObject` has a name, unique within its context.
    The context maintains a list of `QMI_RpcObject` instances.

    Subclasses of `QMI_RpcObject` apply the `@rpc_method` decorator to
    (a subset of) their methods to mark them as callable via RPC.

    Subclasses of `QMI_RpcObject` may choose to export (a subset of)
    their constant class attributes to be accessible directly via the proxy.
    This is done by creating a class attribute `_rpc_constants` holding
    a list of attribute names to be exported.

    Each instance of `QMI_RpcObject` runs in a separate thread. It is not allowed
    to invoke methods of the `QMI_RpcObject` directly from outside the class.
    Instead, the proper way to access an instance of `QMI_RpcObject` is to
    invoke a method on a special "proxy" object, which translates the call
    into an RPC request, which triggers an invocation of the real method of
    the `QMI_RpcObject` instance.

    Instances of `QMI_RpcObject` may publish QMI signals. Each instance may
    register a set of signals. Once registered, such signals can be published
    into the QMI network and routed to subscribed receivers.
    """

    @classmethod
    def get_category(cls) -> str | None:
        """Return the optional name of the category this object belongs to.

        A category name is a free-form string that has no special significance.
        Its purpose is to distinguish between groups of RPC objects that fulfill
        similar roles.
        """
        return None

    def __init__(self,
                 context: 'qmi.core.context.QMI_Context',
                 name: str,
                 signal_declaration_class: type | None = None
                 ) -> None:
        """Initialize the object.

        Instances of QMI_RpcObject are created and managed by the context.
        They should not normally be instantiated directly by the application.

        Parameters:
            context: Instance of `QMI_Context` that will manage this object.
            name: Unique name of this object instance.
            signal_declaration_class: Optional separate class which declares
                the signals published by this object.
        """
        self._context = context
        self._name = name

        # Create an RpcObjectDescriptor for this QMI_RpcObject instance.
        #
        # In the general case, the "signal_declaration_class" is identical to
        # the "rpc_object_class". This simply means that the class which
        # implements the RPC methods, is also the class which declares signals.
        # As an exception to this rule, QMI_TaskRunner will specify a different
        # signal declaration class.
        if signal_declaration_class is None:
            signal_declaration_class = type(self)

        self.rpc_object_descriptor = RpcObjectDescriptor(
            address=QMI_MessageHandlerAddress(context_id=context.name, object_id=name),
            category=self.get_category(),
            interface=make_interface_descriptor(type(self), signal_declaration_class)
        )

        # Create instances of QMI_RegisteredSignal for each signal type that this class may publish.
        # Insert these QMI_RegisteredSignal instances as attributes of the RpcObject instance.
        #
        # Note: The class attribute "_qmi_signals" will be created by the metaclass.
        declared_signals = self._qmi_signals  # type: ignore  # pylint: disable=no-member
        for sig_desc in declared_signals:
            sig = QMI_RegisteredSignal(context, name, sig_desc.name, sig_desc.arg_types)
            setattr(self, sig_desc.name, sig)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._name!r})"

    @rpc_method
    def __enter__(self):
        raise NotImplementedError(f"{type(self)} is not meant to be used with context manager.")

    def lock(self, timeout: float = 0.0, lock_token: str | None = None) -> bool:
        """Lock the remote object. If timeout is given, try every 0.1s within the given timeout value. The remote
        object can be locked with an optional custom lock token by giving a string into `lock_token` keyword argument.

        If successful, this proxy is the only proxy that can invoke RPC methods on the remote object; other proxies
        will receive an "object is locked" response. The return value indicates if the lock was granted; a denied lock
        means the object was already locked by another proxy.

        Do not override this stub method in subclasses. It has already been implemented in QMI_RpcProxy.
        """
        raise NotImplementedError("QMI_RpcObject.lock not implemented")

    def unlock(self, lock_token: str | None = None) -> bool:
        """Unlock the remote object.

        Without optional parameters, this is only allowed by the proxy that initially locked the object. By giving
        the lock token as an input parameter, the specific object locked by this token can be unlocked.
        The return value indicates if the unlocking was successful.

        Do not override this stub method in subclasses. It has already been implemented in QMI_RpcProxy.
        """
        raise NotImplementedError("QMI_RpcObject.unlock not implemented")

    def is_locked(self) -> bool:
        """Query if the remote object is locked.

        Do not override this stub method in subclasses. It has already been implemented in QMI_RpcProxy.
        """
        raise NotImplementedError("QMI_RpcObject.is_locked not implemented")

    def force_unlock(self) -> None:
        """Forcefully unlock the remote object.

        This unlocks the object, regardless of who owns the lock. This allows you to unlock an object if the locking
        proxy has been destroyed without unlocking.

        Use this with care.

        Do not override this stub method in subclasses. It has already been implemented in QMI_RpcProxy.
        """
        raise NotImplementedError("QMI_RpcObject.force_unlock not implemented")

    def release_rpc_object(self) -> None:
        """This method is called just before the RPC object is removed from the context.

        When an RPC object is removed from the context (via context.remove_rpc_object()),
        this method is invoked to release any resources used by the RPC object instance.

        Subclasses may override this method to release specific resources.
        The default implementation does nothing.
        """

    @rpc_method
    def get_name(self) -> str:
        """Return the name of this object.

        Returns:
            name attribute.
        """
        return self._name

    @rpc_method
    def get_signals(self) -> list[SignalDescription]:
        """Return a list of signals that can be published by this object.

        Returns:
            List consisting of qmi_signals attributes.
        """

        # Note: The class attribute "_qmi_signals" will be created by the metaclass.
        return list(self._qmi_signals)  # type: ignore  # pylint: disable=no-member


def make_interface_descriptor(rpc_object_class: Type[QMI_RpcObject],
                              signal_declaration_class: Type[QMI_RpcObject] | None = None
                              ) -> RpcInterfaceDescriptor:
    """Create a description of the (subset of the) interface of the specified
    `QMI_RpcObject` subclass that can be accessed via RPC. Signal declarations
    are taken from the specified signal declaration class, which may be a
    different class than that from which the RPC methods are extracted.
    """

    # Use the RPC object class as the class to extract signal declarations from if no signal declaration class was
    # provided by the caller.
    if signal_declaration_class is None:
        signal_declaration_class = rpc_object_class

    # Get the class docstring for updating it with info
    doc = rpc_object_class.__doc__ or ''
    doc += '\n\nRPC methods:\n'
    # Extract RPC method declarations.
    methods = []
    for name, member in inspect.getmembers(rpc_object_class, is_rpc_method):
        if name in ("lock", "unlock", "force_unlock", "is_locked"):
            raise QMI_UsageException(f"`{name}` is a protected method name")

        signature = str(inspect.signature(member))
        docstring = member.__doc__
        methods.append(RpcMethodDescriptor(name, signature, docstring))
        if not name.startswith("_"):
            signature_doc = signature.replace("(self, ", "(").replace("(self", "(")
            doc += f"  - {name}{signature_doc}\n"

    # Extract signal declarations.
    doc += '\nQMI signals:\n'
    signals = []
    for signal_description in signal_declaration_class._qmi_signals:
        name = signal_description.name
        arg_types = "(" + ", ".join(arg_type.__name__ for arg_type in signal_description.arg_types) + ")"
        signals.append(RpcSignalDescriptor(name, arg_types))
        doc += f"  - {name}{arg_types}\n"

    # Extract constant declarations.
    constant_names = set()
    for base in inspect.getmro(rpc_object_class):
        if hasattr(base, "_rpc_constants"):
            constant_names.update(getattr(base, "_rpc_constants"))

    # Extract constant values.
    doc += '\nRPC constants:\n'
    constants = []
    for constant_name in constant_names:
        assert hasattr(rpc_object_class, constant_name)
        constant_value = getattr(rpc_object_class, constant_name)
        assert not inspect.isfunction(constant_value)
        constants.append(RpcConstantDescriptor(constant_name, constant_value))
        doc += f"  - {constant_name}={constant_value}\n"

    # Create interface descriptor.
    return RpcInterfaceDescriptor(
        rpc_object_class.__module__, rpc_object_class.__name__, doc, constants, methods, signals
    )


class _RpcThread(QMI_Thread):
    """Dedicated thread for executing methods invoked via RPC.

    An instance of this class handles RPC invocations for a single instance
    of `QMI_RpcObject`. A separate instance of `RpcThread` is created for each
    RPC object instance.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.
    """

    def __init__(self,
                 context: 'qmi.core.context.QMI_Context',
                 rpc_object_maker: Callable[[], QMI_RpcObject]
                 ) -> None:
        super().__init__()
        self._context = context  # We need to know the context, to send replies to RPC requests.
        self._rpc_object_maker = rpc_object_maker
        self._locking_token: QMI_LockTokenDescriptor | None = None  # thread maintains lock token
        self._cv = threading.Condition(threading.Lock())
        self._fifo: deque = deque()
        self._rpc_object: QMI_RpcObject | None = None
        self._exception:  BaseException | None = None

    def _handle_lock_rpc_request(self, request: QMI_LockRpcRequestMessage) -> QMI_LockRpcReplyMessage:
        """Handle a lock message."""
        assert self._rpc_object is not None

        return_token: QMI_LockTokenDescriptor | None
        if request.lock_action == QMI_LockRpcAction.ACQUIRE and request.lock_token is not None:
            # Lock request; check if it is allowed.
            if self._locking_token is None:
                # Object was not locked, lock it by storing the provided token.
                self._locking_token = return_token = request.lock_token
                _logger.info("%s locked with %s!", self._rpc_object.get_name(), request.lock_token)
            elif self._locking_token != request.lock_token:
                # Object was already locked and lock token does not match.
                return_token = QMI_LockTokenDescriptor(self._context.name, ACCESS_DENIED_TOKEN_PLACEHOLDER)
                _logger.warning("Lock request (token=%s) for %s failed! Already locked with token=%s.",
                                request.lock_token,
                                self._rpc_object.get_name(),
                                self._locking_token)
            else:
                # Lock token matches, but object is already locked, nothing to do.
                return_token = self._locking_token

        elif request.lock_action == QMI_LockRpcAction.RELEASE:
            # Lock release request; check if it is allowed.
            if self._locking_token is None:
                # Object was not locked, nothing to do.
                return_token = self._locking_token
            elif self._locking_token == request.lock_token:
                # Lock token matches, unlock by clearing the locking token.
                self._locking_token = return_token = None
                _logger.info("%s unlocked with %s!", self._rpc_object.get_name(), request.lock_token)
            else:
                # Lock token does not match.
                return_token = QMI_LockTokenDescriptor(self._context.name, ACCESS_DENIED_TOKEN_PLACEHOLDER)
                _logger.warning("Unlocking request (token=%s) for %s failed! Locked with token=%s.",
                                request.lock_token,
                                self._rpc_object.get_name(),
                                self._locking_token)

        elif request.lock_action == QMI_LockRpcAction.FORCE_RELEASE:
            # Force release of lock irrespective of requesting proxy.
            if self._locking_token is not None:
                self._locking_token = return_token = None
                _logger.warning("%s forcefully unlocked!", self._rpc_object.get_name())

        elif request.lock_action == QMI_LockRpcAction.QUERY:
            # Nothing to do here; reply will contain the locking token (if any), is_locked() method of proxy
            # will check and return appropriate boolean value.
            if self._locking_token is None:
                return_token = None
            else:
                return_token = QMI_LockTokenDescriptor(self._context.name, OBJECT_LOCKED_TOKEN_PLACEHOLDER)

        else:
            raise ValueError(f"Unknown lock action: {request.lock_action!r}")

        reply = QMI_LockRpcReplyMessage(
            source_address=request.destination_address,
            destination_address=request.source_address,
            request_id=request.request_id,
            lock_token=return_token
        )
        return reply

    def _handle_method_rpc_request(self, request: QMI_MethodRpcRequestMessage) -> QMI_MethodRpcReplyMessage:
        """Handle RPC method request."""
        assert self._rpc_object is not None

        # RPC method call - need to check if the caller may invoke the RPC method: allowed if the object is not
        # locked (token is None) or if the provided lock token matches the locking token.
        if self._locking_token is None or self._locking_token == request.lock_token:
            # Invoke the method; this can raise an exception or return a result.
            try:
                method = self._check_and_get_method(request)
                result_type = QMI_RpcFutureState.RESULT_IS_VALUE
                result = method(*request.method_args, **request.method_kwargs)

            except BaseException as exception:
                _logger.debug("RPC method call failed", exc_info=True)
                result_type = QMI_RpcFutureState.RESULT_IS_EXCEPTION
                result = exception
        else:
            _logger.error("%s locked, method request without lock token is denied", self._rpc_object._name)
            result_type = QMI_RpcFutureState.OBJECT_IS_LOCKED
            result = None

        reply = QMI_MethodRpcReplyMessage(
            source_address=request.destination_address,
            destination_address=request.source_address,
            request_id=request.request_id,
            state=result_type,
            result=result
        )
        return reply

    def _check_and_get_method(self, request: QMI_MethodRpcRequestMessage):
        """Check if the object has the method requested and is RPC callable; if so, return it."""
        assert self._rpc_object is not None

        # Check that the method exists.
        if not hasattr(self._rpc_object, request.method_name):
            raise QMI_UnknownRpcException("Object {} of type {} does not have method {}"
                                          .format(request.destination_address.object_id,
                                                  type(self._rpc_object).__name__,
                                                  request.method_name))

        # Check that the method was marked as RPC-callable.
        method = getattr(self._rpc_object, request.method_name)
        is_rpc_callable = getattr(method, "_rpc_method", False)
        if not is_rpc_callable:
            raise QMI_UnknownRpcException(f"Method {request.method_name!r} is not RPC-callable!")

        return method

    def _reject_remaining_requests(self) -> None:
        """Reject any requests that are still in our queue when the RPC object shuts down."""

        while True:
            # Get next pending request.
            with self._cv:
                if not self._fifo:
                    break
                request = self._fifo.popleft()

            # Sanity check (this has already been checked by the RpcObjectManager).
            assert isinstance(request, (QMI_MethodRpcRequestMessage, QMI_LockRpcRequestMessage))

            # Send error reply for this request.
            reply = QMI_ErrorReplyMessage(source_address=request.destination_address,
                                          destination_address=request.source_address,
                                          request_id=request.request_id,
                                          error_msg="")
            try:
                self._context.send_message(reply)
            except QMI_MessageDeliveryException:
                # Ignore errors while sending the error reply.
                _logger.debug("Failed to send RPC error reply to %s.%s",
                              request.source_address.context_id,
                              request.source_address.object_id)

    def _request_shutdown(self) -> None:
        # Notify the thread so that it can end its request loop.
        assert self._shutdown_requested
        with self._cv:
            self._cv.notify_all()

    def rpc_object(self) -> QMI_RpcObject:
        """Return the actual RpcObject instance managed by this thread.

        Wait until initialization of the RpcObject instance is finished,
        if necessary. If initialization was successful, return the object
        instance. Otherwise, re-raise the exception that occurred during
        initialization.
        """
        with self._cv:
            while (self._rpc_object is None) and (self._exception is None):
                self._cv.wait()
            if self._exception is not None:
                raise self._exception

            assert isinstance(self._rpc_object, QMI_RpcObject)
            return self._rpc_object

    def run(self) -> None:
        """This method runs inside the RPC thread."""
        _logger.debug("Starting RPC thread")

        assert self._rpc_object is None
        assert self._exception is None

        try:
            # Construct and initialize RpcObject instance.
            rpc_object = self._rpc_object_maker()
            if not isinstance(rpc_object, QMI_RpcObject):
                raise TypeError(f"Expecting QMI_RpcObject but got {type(rpc_object)}")
        except BaseException as exception:
            # Initialization failed. Store the exception.
            _logger.warning("Initialization of RpcObject failed", exc_info=True)
            with self._cv:
                self._exception = exception
                self._cv.notify_all()

            # Stop thread.
            _logger.info("Stopping RPC thread (initialization failed)")
            return

        # Notify the outside world that initialization is finished.
        with self._cv:
            self._rpc_object = rpc_object
            self._cv.notify_all()

        # Request handling phase.
        while True:
            with self._cv:
                # Wait for RPC request or shutdown request.
                while (not self._shutdown_requested) and (not self._fifo):
                    self._cv.wait()

                # End the request loop if shutdown requested.
                if self._shutdown_requested:
                    break

                request = self._fifo.popleft()

            # Process request.
            reply: QMI_MethodRpcReplyMessage | QMI_LockRpcReplyMessage | None
            if isinstance(request, QMI_MethodRpcRequestMessage):
                reply = self._handle_method_rpc_request(request)
            elif isinstance(request, QMI_LockRpcRequestMessage):
                reply = self._handle_lock_rpc_request(request)
            else:
                raise ValueError(f"Unknown request type: {type(request)}")

            # Send reply.
            try:
                self._context.send_message(reply)
            except QMI_MessageDeliveryException:
                # Catch exceptions from sending message (avoid crashing the RPC thread on message delivery error).
                _logger.error(
                    "Failed to send RPC reply message from %s.%s to %s.%s",
                    request.destination_address.context_id,
                    request.destination_address.object_id,
                    request.source_address.context_id,
                    request.source_address.object_id
                )

            del request, reply

        # Reject any requests that are still in our queue.
        self._reject_remaining_requests()

        # Tell RPC object to release resources.
        try:
            rpc_object.release_rpc_object()
        except BaseException:
            # Log exceptions during resource release.
            _logger.exception("Failed to release RPC object")

        _logger.debug("Stopping RPC thread")

    def push_rpc_request(self, rpc_request: QMI_MethodRpcRequestMessage | QMI_LockRpcRequestMessage  | None) -> None:
        """Push an RPC request into the request queue and notify the thread."""
        with self._cv:
            self._fifo.append(rpc_request)
            self._cv.notify_all()


class RpcObjectManager(QMI_MessageHandler):
    """Manages a single instance of QMI_RpcObject.

    A dedicated `RpcObjectManager` is created by the context for each instance
    of `QMI_RpcObject`. The `RpcObjectManager` owns a single `RpcThread` instance
    (which, in turn, owns a single `QMI_RpcObject` instance).

    An `RpcObjectManager` receives RPC request messages on behalf of the
    RPC object. It pushes these messages into a queue, from where they are
    picked up and handled by the RpcThread.

    The message handler address of the RpcObjectManager is based on
    the name of the associated RPC object.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.
    """

    def __init__(self,
                 address: QMI_MessageHandlerAddress,
                 context: 'qmi.core.context.QMI_Context',
                 rpc_object_maker: Callable[[], QMI_RpcObject]
                 ) -> None:
        """Initialize the RPC object manager.

        Parameters:
            address: Address of the RPC object.
                This instance of `RpcObjectManager` will be registered as
                message handler for this address.
            context: QMI context in which this RPC object will exist.
            rpc_object_maker: Function which creates the actual RPC object instance.
        """
        super().__init__(address)
        self._context = context
        self._rpc_thread: _RpcThread | None = None
        self._rpc_object_maker = rpc_object_maker
        self._stop_lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        """Create a background thread and start handling RPC calls."""
        assert self._rpc_thread is None
        self._rpc_thread = _RpcThread(self._context, self._rpc_object_maker)
        self._rpc_thread.start()
        self._running = True

    def stop(self) -> None:
        """Stop the background thread and clean it up."""
        assert self._rpc_thread is not None
        with self._stop_lock:
            self._running = False
        self._rpc_thread.shutdown()
        self._rpc_thread.join()
        self._rpc_thread = None

    def make_proxy(self) -> QMI_RpcProxy:
        """Return a new instance of the RpcProxy class corresponding to the RPC object.

        Wait until initialization of the RPC object instance is finished,
        if necessary. If initialization was successful, create and return
        a RpcProxy instance for the RPC object.

        Otherwise re-raise the exception that occurred during initialization.
        """

        assert self._rpc_thread is not None

        # This may raise an exception!
        rpc_object = self._rpc_thread.rpc_object()
        return QMI_RpcProxy(self._context, rpc_object.rpc_object_descriptor)

    def handle_message(self, message: QMI_Message) -> None:
        """Called when a QMI message is delivered for our RPC object."""

        if not isinstance(message, (QMI_MethodRpcRequestMessage, QMI_LockRpcRequestMessage)):
            _logger.error("Received unknown message type %r from %s.%s",
                          type(message),
                          message.source_address.context_id,
                          message.source_address.object_id)
            return

        with self._stop_lock:
            # Reject message if the object is already stopped (or stopping).
            if not self._running:
                raise QMI_MessageDeliveryException("RPC object {}.{} already stopped"
                                                   .format(self.address.context_id, self.address.object_id))

            # The thread is still running, so we can safely push the message to the thread.
            assert self._rpc_thread is not None
            self._rpc_thread.push_rpc_request(message)

    def rpc_object(self) -> QMI_RpcObject:
        """Return the RPC object instanced managed by this `RpcObjectManager`."""
        assert self._rpc_thread is not None
        return self._rpc_thread.rpc_object()


# Imports needed only for static typing.
if TYPE_CHECKING:
    import qmi.core.context
