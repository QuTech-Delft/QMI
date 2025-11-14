"""Sending and receiving messages between QMI objects and between QMI contexts.

The classes defined in this module are for the most part used internally by QMI.
Application programs should typically not interact with these classes directly.
"""

import sys
import asyncio
import copy
import fnmatch
import functools
import logging
import os
import pickle
import random
import socket
import threading
import time
from collections.abc import Callable
from typing import Generic, NamedTuple, TypeVar

import qmi

from qmi.core.thread import QMI_Thread
from qmi.core.exceptions import (
    QMI_Exception, QMI_RuntimeException, QMI_TimeoutException, QMI_InvalidOperationException,
    QMI_MessageDeliveryException, QMI_UsageException,
    QMI_DuplicateNameException, QMI_UnknownNameException
    )

from qmi.core.udp_responder_packets import (
        unpack_qmi_udp_packet,
        QMI_UdpResponderContextInfoRequestPacket,
        QMI_UdpResponderContextInfoResponsePacket,
        QMI_UdpResponderKillRequestPacket,
    )

from qmi.core.util import format_address_and_port, parse_address_and_port


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


# Full address of a message handler, including its context name.
class QMI_MessageHandlerAddress(NamedTuple):
    """Unique address associated with a specific message handler.

    Attributes:
        context_id: Name of the context that contains the message handler.
        object_id: Unique name for the message handler within the context.
            In many cases, this is simply the RPC object name.
    """

    context_id: str
    object_id: str

    def __str__(self) -> str:
        return self.context_id + "." + self.object_id


class QMI_Message:
    """Base class for all messages sent via QMI.

    Attributes:
        source_address: Address of the object which sent this message.
        destination_address: Address of the object which should receive this message.
    """

    __slots__ = ("source_address", "destination_address")

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress
                 ) -> None:
        self.source_address = source_address
        self.destination_address = destination_address


class QMI_RequestMessage(QMI_Message):
    """Base class for request messages in QMI.

    Request messages are used when a reply is expected.
    When an object sends a request message, it expects to receive exactly
    one corresponding reply message.

    The association between request messages and reply messages is tracked
    explicitly via the `request_id` attribute.

    Attributes:
        request_id: Unique ID for this message.
            Automatically initialized to a random 64-bit integer.
    """

    __slots__ = ("request_id",)

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.request_id = f"{random.getrandbits(64):016x}"


class QMI_ReplyMessage(QMI_Message):
    """Base class for reply messages in QMI.

    A reply message is a response to a request message.
    When an object receives a request message, it is expected to send
    exactly one corresponding reply message.

    The destination of the reply message is taken from the source
    of the corresponding request message. The `request_id` attribute
    of the reply message must be equal to the `request_id` of the
    corresponding request message.

    Attributes:
        request_id: Request ID of the `QMI_RequestMessage` to which this message is a reply.
    """

    __slots__ = ("request_id",)

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 request_id: str
                 ) -> None:
        super().__init__(source_address, destination_address)
        self.request_id = request_id


class QMI_ErrorReplyMessage(QMI_ReplyMessage):
    """Special reply message, sent when a request can not be processed.

    An instance of `QMI_ErrorReplyMessage` is generated when a request message
    can not be delivered, or when the associated connection is lost before
    a reply is received. This message will then be delivered in place of
    the actual reply to the pending request.

    Attributes:
        error_msg: Short string, describing the reason why the request could not be processed.
    """

    __slots__ = ("error_msg",)

    def __init__(self,
                 source_address: QMI_MessageHandlerAddress,
                 destination_address: QMI_MessageHandlerAddress,
                 request_id: str,
                 error_msg: str
                 ) -> None:
        super().__init__(source_address, destination_address, request_id)
        self.error_msg = error_msg


class QMI_InitialHandshakeMessage(QMI_Message):
    """Initial handshake message exchanged for a new TCP connection."""

    __slots__ = ("version", "is_server_handshake")

    def __init__(self, context_name: str, version: str, is_server_handshake: bool) -> None:
        source_address = QMI_MessageHandlerAddress(context_name, "$router")
        # QMI_InitialHandshakeMessage does not use a destination address.
        destination_address = QMI_MessageHandlerAddress("", "")
        super().__init__(source_address, destination_address)
        self.version = version
        self.is_server_handshake = is_server_handshake


class QMI_MessageHandler:
    """Base class for QMI classes which can receive messages.

    A message handler instance has a unique address and is registered
    with the QMI context.
    """

    def __init__(self, address: QMI_MessageHandlerAddress) -> None:
        self.address = address

    def handle_message(self, message: QMI_Message) -> None:
        """Called by the QMI message router when a message for this object is received.

        This method is responsible for handling the received message.
        This method should not raise exceptions other than `QMI_MessageDeliveryException`.

        Subclasses must implement this method.

        Raises:
            QMI_MessageDeliveryException: If the message can not be accepted.
        """
        raise NotImplementedError()

    def shutdown(self) -> None:
        """Called by the QMI message router during unregistering of the handler.

        After this call, no more messages will be received.

        Subclasses can implement this method to free resources they are using.
        The default implementation does nothing.

        Do not call this method explicitly. It will be called automatically
        during unregistering of the message handler.
        """
        pass


_T = TypeVar('_T')


class _EventDrivenThread(QMI_Thread):
    """An EventDrivenThread executes an Asyncio event loop."""

    class Future(Generic[_T]):
        """Representation of the future completion of a procedure running in an `EventDrivenThread`."""

        def __init__(self, thread: '_EventDrivenThread') -> None:
            self._thread = thread
            self._finished = False
            self._value = None  # type: _T | None
            self._exception = None  # type: Exception | None

        def set_value(self, value: _T) -> None:
            with self._thread._cv:
                assert not self._finished
                self._value = value
                self._finished = True
                self._thread._cv.notify_all()

        def set_exception(self, exc: Exception) -> None:
            with self._thread._cv:
                assert not self._finished
                self._exception = exc
                self._finished = True
                self._thread._cv.notify_all()

        def wait(self, timeout: float | None = None) -> _T:
            with self._thread._cv:
                ok = self._thread._cv.wait_for(lambda: (self._thread._thread_finished or self._finished),
                                               timeout=timeout)
            if not ok:
                raise QMI_TimeoutException()
            if not self._finished:
                raise QMI_InvalidOperationException("Thread stopped before operation completed")
            if self._exception is not None:
                raise self._exception
            return self._value  # type: ignore

    def __init__(self) -> None:
        super().__init__()
        self._cv = threading.Condition()
        self._thread_initialized = False
        self._thread_finished = False

        # self.event_loop holds this thread's Asyncio event loop.
        # This variable is only valid while the thread runs
        # (i.e. _thread_initialized and not _thread_finished) and may only
        # be accessed by code running inside the thread.
        self.event_loop = None  # type: asyncio.AbstractEventLoop | None

    def run(self) -> None:

        _logger.debug("EventDrivenThread starting")

        # Create Asyncio event loop for this thread.
        # It has to be of type SelectorEventLoop.
        # The default event loop type on Windows is ProactorEventLoop,
        # but that does not support the socket notifier mechanism we use.
        self.event_loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(self.event_loop)

        # Mark thread as initialized.
        with self._cv:
            self._thread_initialized = True
            self._cv.notify_all()

        try:
            # Run event loop until event_loop.stop() is called.
            self.event_loop.run_forever()

        finally:
            # Mark thread as finished.
            with self._cv:
                self._thread_finished = True
                self._cv.notify_all()

            # Clean up event loop.
            self.event_loop.close()
            self.event_loop = None

        _logger.debug("EventDrivenThread finished")

    def _request_shutdown(self) -> None:
        """Initiate termination of the thread.

        This is called once during `shutdown()` of the thread.
        """

        assert self._shutdown_requested

        # Check that thread was started (i.e. self.start() was called).
        # If the thread is not currently running and has not completed
        # its initialization, it means start() was never called and
        # this is an invalid use case (calling shutdown() before start()).
        assert self.is_alive() or self._thread_initialized

        with self._cv:

            # Wait until thread is initialized.
            while not self._thread_initialized:
                self._cv.wait()

            # Tell the event loop to stop, unless the thread is already finished.
            if not self._thread_finished:
                assert self.event_loop is not None
                self.event_loop.call_soon_threadsafe(self.event_loop.stop)

    def run_in_thread_arg(self, func: Callable[[_T], None], arg: _T) -> None:
        """Run the specified function inside the thread.

        This method returns immediately. The specified function will run
        inside the thread after some short but indeterminate delay.

        The thread must be started before calling this method.
        If the thread is stopped before the specified function gets a chance
        to run, nothing happens.

        Parameters:
            func: Function to run in the thread.
            arg: A single argument to be passed to the function.
        """

        # Check that thread was started (i.e. self.start() was called).
        assert self.is_alive() or self._thread_initialized

        with self._cv:

            # Wait until thread is initialized.
            while not self._thread_initialized:
                self._cv.wait()

            # Tell the event loop to run the specified function.
            if not self._thread_finished:
                assert self.event_loop is not None
                self.event_loop.call_soon_threadsafe(func, arg)

    @staticmethod
    def _call_no_arg_helper(func: Callable[[], None]) -> None:
        func()

    def run_in_thread(self, func: Callable[[], None]) -> None:
        """Run the specified function inside the thread.

        This method returns immediately. The specified function will run
        inside the thread after some short but indeterminate delay.

        The thread must be started before calling this method.
        If the thread is stopped before the specified function gets a chance
        to run, nothing happens.

        Parameters:
            func: Function to run in the thread.
        """
        self.run_in_thread_arg(self._call_no_arg_helper, func)

    def make_future(self) -> '_EventDrivenThread.Future':
        return _EventDrivenThread.Future(self)

    @staticmethod
    def _call_wait_helper(func: Callable[[], _T], future: Future[_T]) -> None:
        try:
            ret = func()
            future.set_value(ret)
        except Exception as exc:
            future.set_exception(exc)

    def run_in_thread_wait(self, func: Callable[[], _T]) -> _T:
        """Run the specified function inside the thread and wait until it completes.

        This method waits while the specified function runs in the thread,
        then returns the value returned by the specified function.

        The thread must already be started before calling this method.
        If the thread is stopped before the specified function gets a chance
        to run, QMI_InvalidOperationException is raised.

        Parameters:
            func: Function to run in the thread.

        Returns:
            Value returned by the specified function.

        Raises:
            QMI_InvalidOperationException: If the thread stops before the function runs.
            Exception: If the specified function raises the same exception.
        """

        # Check that thread was started (i.e. self.start() was called).
        assert self.is_alive() or self._thread_initialized

        with self._cv:

            # Wait until thread is initialized.
            while not self._thread_initialized:
                self._cv.wait()

            # Check that the thread is still running.
            if self._thread_finished:
                raise QMI_InvalidOperationException("EventDrivenThread already stopped before run_in_thread_wait()")

            # Tell the event loop to run the specified function.
            assert self.event_loop is not None
            future = self.make_future()  # type: _EventDrivenThread.Future[_T]
            self.event_loop.call_soon_threadsafe(self._call_wait_helper, func, future)

            # Wait until the function completes and return its result.
            return future.wait()


class _SocketWrapper:
    """Base class for socket wrappers.

    A SocketWrapper encapsulates a socket object and handles read events on the socket.

    This is an abstract base class. Subclasses implement actual behavior for specific use cases.
    """

    def close(self) -> None:
        """Close the wrapped socket object and release resources.

        Subclasses must override this method.
        """
        raise NotImplementedError()


class _UdpResponder(_SocketWrapper):
    """Handles requests received via a dedicated UDP socket.

    The UdpResponder runs in an Asyncio event loop to respond to asynchronous
    events on the UDP socket.

    Instances of `UdpResponder` are managed by the `SocketManager`.
    """

    def __init__(self,
                 event_loop: asyncio.AbstractEventLoop,
                 message_router: 'MessageRouter',
                 sock: socket.socket
                 ) -> None:
        """Initialize a UdpResponder instance.

        Parameters:
            event_loop: Asyncio event loop to which the socket should attach itself.
            message_router: `MessageRouter` instance that manages this UDP responder.
            sock: UDP server socket, already bound and listening.
        """

        super().__init__()
        self._event_loop = event_loop
        self._message_router = message_router
        self._sock = sock

        # POSIX sockets should not block on recv_from(), when select() returns True. However,
        # in Linux, this is not always true. We make the socket non-blocking and
        # and explicitly handle recv() failure to make up for this.
        self._sock.setblocking(False)

        # Register callback to be invoked when the socket is ready for reading.
        self._event_loop.add_reader(self._sock.fileno(), self._handle_read)

        _logger.debug("UDP responder ready on %s", format_address_and_port(self._sock.getsockname()))

    def close(self) -> None:
        """Detach from the event loop and close the wrapped socket."""
        _logger.debug("Closing UDP responder")
        self._event_loop.remove_reader(self._sock.fileno())
        self._sock.close()

    def _handle_read(self) -> None:
        """Called through the event loop when the socket may be ready for reading."""

        try:
            (request_data, incoming_address) = self._sock.recvfrom(4096)
        except BlockingIOError:
            # No UDP message available. Continue.
            _logger.error("UdpResponder got handle_read but no packet available")
            return

        # Try to interpret it as a QMI packet.
        # If that fails, discard the packet.
        try:
            request_packet = unpack_qmi_udp_packet(request_data)
        except QMI_Exception:
            _logger.exception("Discarded bad UDP packet.")
            return

        # Handle the different kinds of incoming packets.
        if isinstance(request_packet, QMI_UdpResponderContextInfoRequestPacket):
            self._handle_context_info_request_packet(incoming_address, request_packet)
        elif isinstance(request_packet, QMI_UdpResponderKillRequestPacket):
            self._handle_kill_request_packet()
        else:
            _logger.warning("Received UDP packet of type %s, discarded.", type(request_packet).__name__)

    def _handle_context_info_request_packet(self,
                                            incoming_address: tuple[str, int],
                                            request_packet: QMI_UdpResponderContextInfoRequestPacket
                                            ) -> None:
        """Called when a `QMI_UdpResponderContextInfoRequestPacket` is received."""

        # First, we check if we want to respond, by checking the request's
        # "workgroup_name_filter" and "context_name_filter" to the corresponding values of the Context.

        workgroup_name_filter = request_packet.workgroup_name_filter.decode()
        workgroup_name_match = fnmatch.fnmatchcase(self._message_router.workgroup_name, workgroup_name_filter)

        if not workgroup_name_match:
            # Don't respond.
            return

        context_name_filter = request_packet.context_name_filter.decode()
        context_name_match = fnmatch.fnmatchcase(self._message_router.context_name, context_name_filter)

        if not context_name_match:
            # Don't respond.
            return

        # Send response.

        response_msg_id = random.randint(1, 2 ** 64 - 1)  # Positive 64-bit integer.

        response_packet = QMI_UdpResponderContextInfoResponsePacket.create(
            response_msg_id,  # Unique message ID.
            time.time(),  # POSIX timestamp.
            request_packet.pkt_id,
            request_packet.pkt_timestamp,
            os.getpid(),
            self._message_router.context_name.encode(),
            self._message_router.workgroup_name.encode(),
            self._message_router.tcp_server_port
        )
        outgoing_address = incoming_address
        self._sock.sendto(bytes(response_packet), outgoing_address)

    def _handle_kill_request_packet(self) -> None:
        """Called when a `QMI_UdpResponderKillRequestPacket` is received."""
        print("Answering external hard-kill request, exiting with exitcode 1.")
        os._exit(1)


class _PeerTcpConnection(_SocketWrapper):
    """Encapsulates a TCP connection to a peer context.

    The TCP connection can either be an outgoing (client-side) connection to a
    remote server, or an incoming (server-side) connection from a remote client.

    The `PeerTcpConnection` is initially a passive object. It will later be attached
    to an Asyncio event loop to enable background processing of received data.

    Instances of `PeerTcpConnection` are managed by the `SocketManager`.
    """

    # Maximum size of serialized message is 10 MB.
    MAX_MESSAGE_SIZE = 10000000

    def __init__(self,
                 message_router: 'MessageRouter',
                 sock: socket.socket,
                 peer_context_alias: str,
                 is_incoming: bool
                 ) -> None:
        """Initialize a PeerTcpConnection instance.

        Parameters:
            message_router: `MessageRouter` instance that manages this TCP connection.
            sock: TCP socket, already connected to a remote TCP socket.
            peer_context_alias: Local name for the peer context. This is either the actual name
                of the remote context (for outgoing connections) or a local unique identifier
                (for incoming connections).
            is_incoming: True if this is an incoming connection from a remote client;
                False if this is an outgoing connection to a remote server.
        """
        self._message_router = message_router
        self._sock = sock
        self.peer_context_alias = peer_context_alias
        self._is_incoming = is_incoming
        self._event_loop = None  # type: asyncio.AbstractEventLoop | None
        self._socket_manager = None  # type: _SocketManager | None
        self._recv_buf = bytearray()

        # Actual peer context name initially unknown (until handshake).
        self.peer_context_name = None  # type: str | None

        # Actual peer context version initially unknown (until handshake).
        self.peer_context_version = None  # type: str | None

        # Table of pending outgoing request messages, by request ID.
        self._pending_requests: dict[str, tuple[QMI_MessageHandlerAddress, QMI_MessageHandlerAddress]] = {}

        # NOTE: Do not make TCP socket non-blocking (in contrast to UDP socket)
        # because sending to the TCP socket should be a blocking operation.

        self.local_address = sock.getsockname()
        self.peer_address = None  # type: tuple[str, int] | None
        self._peer_address_str = "[unknown]"
        try:
            self.peer_address = sock.getpeername()
            self._peer_address_str = format_address_and_port(self.peer_address)
        except OSError:
            # Maybe connection already broke - then we don't know the peer address.
            pass

    def attach_to_socket_manager(self,
                                 event_loop: asyncio.AbstractEventLoop,
                                 socket_manager: '_SocketManager'
                                 ) -> None:
        """Attach this PeerTcpConnection to the socket manager and start
        event-driven processing of received data.
        """
        assert self._event_loop is None
        assert self._socket_manager is None

        self._event_loop = event_loop
        self._socket_manager = socket_manager

        # Register callback to be invoked when the socket is ready for reading.
        self._event_loop.add_reader(self._sock.fileno(), self._handle_read)

    def close(self) -> None:
        """Detach from the event loop and close the wrapped socket."""
        _logger.debug("Closing TCP connection to %s (%r)",
                      self._peer_address_str,
                      self.peer_context_name)
        if self._event_loop is not None:
            self._event_loop.remove_reader(self._sock.fileno())
        self._sock.close()
        self._clear_pending_requests()

    def _clear_pending_requests(self) -> None:
        """Send failure replies for any pending requests on this socket.

        This function is called when the connection is closed.
        There may be tasks in the local context that are still waiting
        for replies to requests that were sent out via this connection.
        Because the socket is now closed, these replies will never be received.

        For each such pending request, we generate an error reply to notify
        the waiting task that the request will not be answered.
        """
        for (request_id, (source_address, destination_address)) in self._pending_requests.items():
            reply = QMI_ErrorReplyMessage(
                source_address=destination_address,
                destination_address=source_address,
                request_id=request_id,
                error_msg=f"Connection to {self.peer_context_name} closed while waiting for reply")
            try:
                self._message_router.deliver_message(reply)
            except QMI_MessageDeliveryException:
                _logger.debug("Failed to deliver error reply to %r while closing socket", source_address)
        self._pending_requests.clear()

    def _handle_read(self) -> None:
        """Called through the event loop when the socket is ready for reading."""

        assert self._socket_manager is not None

        # If this function raises an exception, it will kill the Asyncio event
        # loop (and thus the whole SocketManager). DO NOT WANT!
        # Catch any such exceptions here and close the connection.
        try:
            self._receive_data()
        except Exception as exc:
            _logger.info("Error on connection to %s (%s) - closing",
                         self._peer_address_str,
                         self.peer_context_name,
                         exc_info=True)
            # Close connection.
            self._socket_manager.remove_peer_connection(self)
            self.close()

    def _receive_data(self) -> None:
        """Called when the socket is ready for reading."""

        assert self._socket_manager is not None

        incoming_data = self._sock.recv(4096)
        if len(incoming_data) == 0:
            # Connection closed by other side.
            _logger.debug("Connection to %s (%s) closed by peer", self._peer_address_str, self.peer_context_name)

            # Close our side as well and remove from the socket manager.
            self._socket_manager.remove_peer_connection(self)
            self.close()
            return

        # Add received data to buffer.
        self._recv_buf.extend(incoming_data)

        # Consume any complete messages from the receive buffer.
        while True:

            if len(self._recv_buf) < 1:
                break

            if self._recv_buf[0] != ord(b'P'):
                raise QMI_RuntimeException("Protocol violation (got {!r} while expecting 'P')"
                                           .format(self._recv_buf[0:1]))

            if len(self._recv_buf) < 9:
                break

            pickled_message_size = int.from_bytes(self._recv_buf[1:9], byteorder='little')

            if pickled_message_size > self.MAX_MESSAGE_SIZE:
                # Protocol violation.
                raise QMI_RuntimeException(f'Protocol packet too big ({pickled_message_size})')

            if len(self._recv_buf) < 9 + pickled_message_size:
                break

            packed_message = self._recv_buf[9:9 + pickled_message_size]
            self._recv_buf = self._recv_buf[9 + pickled_message_size:]

            self._process_message(packed_message)

    def _process_message(self, packed_message: bytearray) -> None:
        """Called when a message has been received from the socket."""

        # This may fail.
        message = pickle.loads(packed_message)
        if not isinstance(message, QMI_Message):
            raise ValueError("Expected QMI_Message")

        if self.peer_context_name is None:

            # The first message from the peer must be a handshake message.
            if not isinstance(message, QMI_InitialHandshakeMessage):
                raise QMI_RuntimeException("Expecting handshake message but got {}"
                                           .format(type(message).__name__))

            # Process handshake message.
            self.peer_context_name = message.source_address.context_id
            self.peer_context_version = message.version
            if message.is_server_handshake and self._is_incoming:
                raise QMI_RuntimeException("Received server handshake from connecting client")
            if (not message.is_server_handshake) and (not self._is_incoming):
                raise QMI_RuntimeException("Received client handshake while connecting as client")
            _logger.debug("Received handshake from %r", message.source_address.context_id)

        else:
            if isinstance(message, QMI_InitialHandshakeMessage):
                raise QMI_RuntimeException("Unexpected handshake message from peer")

            # Check destination context name.
            if message.destination_address.context_id != self._message_router.context_name:
                raise QMI_MessageDeliveryException(
                    "Unexpected destination context {} in message from {}"
                    .format(message.destination_address.context_id, self.peer_context_name))

            # Check source context name and rewrite to local alias.
            if message.source_address.context_id != self.peer_context_name:
                raise QMI_MessageDeliveryException("Unexpected source context {} in message from {}"
                                                   .format(message.source_address.context_id, self.peer_context_name))
            message.source_address = QMI_MessageHandlerAddress(
                self.peer_context_alias,
                message.source_address.object_id
            )

            # In case of a reply message, remove the corresponding request from the table.
            if isinstance(message, QMI_ReplyMessage):
                if message.request_id in self._pending_requests:
                    self._pending_requests.pop(message.request_id)
                else:
                    _logger.warning("Received reply message for unknown request_id %r", message.request_id)

            # Push message to router for local delivery.
            try:
                self._message_router.deliver_message(message)
            except QMI_MessageDeliveryException as exc:
                # Message delivery failed.
                # If this is a request message, send back and error reply.
                _logger.warning("%s", str(exc))
                if isinstance(message, QMI_RequestMessage):
                    self.send_error_reply(message, str(exc))
            except Exception:
                # This happens if a "handle_message()" method raises an unexpected exception.
                _logger.exception("Unexpected exception while delivering message to %r", message.destination_address)

    def send_message(self, message: QMI_Message) -> None:
        """Send a message to the peer context via this TCP connection.

        This function serializes the message and sends it through TCP.
        An exception is raised if serialization or transmission fails.

        When this function sends a request message, the request is added
        to the pending request table, to be cleared when a reply is received.
        """

        # Replace local name of destination context by actual context name.
        # Skip this step only for QMI_InitialHandshakeMessage, which does not have a destination.
        message = copy.copy(message)
        if not isinstance(message, QMI_InitialHandshakeMessage):
            assert message.destination_address.context_id == self.peer_context_alias
            assert self.peer_context_name is not None
            message.destination_address = QMI_MessageHandlerAddress(
                self.peer_context_name,
                message.destination_address.object_id
            )

        # Serialize the message.
        pickled_message = pickle.dumps(message)

        pickled_message_size = len(pickled_message)
        if pickled_message_size > self.MAX_MESSAGE_SIZE:
            raise ValueError("Message exceeds maximum size")

        # Prepend the header.
        pickled_message = b'P' + pickled_message_size.to_bytes(8, byteorder='little') + pickled_message

        # Send the message via TCP.
        self._sock.sendall(pickled_message)

        # In case of a request message, add the message to the pending request table.
        if isinstance(message, QMI_RequestMessage):
            if message.request_id in self._pending_requests:
                _logger.warning("Duplicate request_id %r in message to %r",
                                message.request_id,
                                message.destination_address)
            else:
                self._pending_requests[message.request_id] = (message.source_address, message.destination_address)

    def send_handshake(self) -> None:
        """Send an initial handshake message to the remote side."""
        message = QMI_InitialHandshakeMessage(
            self._message_router.context_name,
            qmi.__version__,
            self._is_incoming
        )
        self.send_message(message)

    def send_error_reply(self, message: QMI_RequestMessage, error_msg: str) -> None:
        """Send an error reply message back to the peer context via this TCP connection."""
        reply = QMI_ErrorReplyMessage(
            source_address=message.destination_address,
            destination_address=message.source_address,
            request_id=message.request_id,
            error_msg=error_msg)
        try:
            self.send_message(reply)
        except (ValueError, OSError):
            _logger.warning("Error while sending error reply to %s", message.destination_address.context_id)

    def receive_handshake(self, timeout: float | None) -> None:
        """Wait (blocking) until the socket receives a handshake message.

        This function is used when creating a client-side connection,
        to verify the handshake in the main thread.
        """

        assert self._event_loop is None
        assert self.peer_context_name is None

        if timeout is None:
            endtime = None
        else:
            endtime = time.monotonic() + timeout

        while True:

            # Check message header.
            if (len(self._recv_buf) > 0) and (self._recv_buf[0] != ord(b'P')):
                raise QMI_RuntimeException("Protocol violation (got {!r} while expecting 'P')"
                                           .format(self._recv_buf[0:1]))

            # Decode message length.
            if len(self._recv_buf) < 9:
                need_len = 9
            else:
                pickled_message_size = int.from_bytes(self._recv_buf[1:9], byteorder='little')
                if pickled_message_size > self.MAX_MESSAGE_SIZE:
                    raise QMI_RuntimeException(f'Protocol packet too big ({pickled_message_size})')
                need_len = 9 + pickled_message_size

            # Stop when message complete.
            if len(self._recv_buf) >= need_len:
                break

            # Receive additional bytes.
            if endtime is not None:
                tmo = max(0, endtime - time.monotonic())
                self._sock.settimeout(tmo)
            incoming_data = self._sock.recv(need_len - len(self._recv_buf))
            if len(incoming_data) == 0:
                # Connection closed by other side.
                raise QMI_RuntimeException("Connection to {} closed by peer before handshake"
                                           .format(self._peer_address_str))

            self._recv_buf.extend(incoming_data)

        if endtime is not None:
            # Put socket back in unconditional blocking mode.
            self._sock.settimeout(None)

        packed_message = self._recv_buf[9:9 + pickled_message_size]
        self._recv_buf = self._recv_buf[9 + pickled_message_size:]

        # This must be the handshake (since we had not receive a handshake yet).
        self._process_message(packed_message)

        # We must now know the remote peer name (from the handshake).
        assert self.peer_context_name is not None


class _TcpServer(_SocketWrapper):
    """Encapsulates a TCP server socket.

    A TcpServer runs in an Asyncio event loop to respond to asynchronous
    connection events on the TCP server socket.

    Instances of `TcpServer` are managed by the `SocketManager`.
    """

    def __init__(self,
                 event_loop: asyncio.AbstractEventLoop,
                 socket_manager: '_SocketManager',
                 sock: socket.socket
                 ) -> None:
        """Initialize a TcpServer instance.

        Parameters:
            event_loop: Asyncio event loop to which the socket should attach itself.
            message_router: `MessageRouter` instance that manages this UDP responder.
            sock: TCP server socket, already bound and listening.
        """

        self._event_loop = event_loop
        self._socket_manager = socket_manager
        self._sock = sock

        # Make the socket non-blocking.
        self._sock.setblocking(False)

        # Register callback to be invoked when the socket is ready for reading.
        self._event_loop.add_reader(self._sock.fileno(), self._handle_read)

        _logger.debug("TCP server ready on %s", format_address_and_port(self._sock.getsockname()))

    def close(self) -> None:
        """Detach from the event loop and close the wrapped socket."""
        _logger.debug("TCP server on %s closing", format_address_and_port(self._sock.getsockname()))
        self._event_loop.remove_reader(self._sock.fileno())
        self._sock.close()

    def _handle_read(self) -> None:
        """Called through the event loop when a new TCP connection is established."""

        # Accept new connection.
        try:
            (incoming_connection_socket, incoming_connection_address) = self._sock.accept()
        except OSError as exc:
            # Accept can fail in case of early TCP protocol error.
            _logger.exception("Accepting new TCP connection failed")
            return

        _logger.debug("Incoming TCP connection from %s", format_address_and_port(incoming_connection_address))

        # Disable TCP small packet delay (Nagle algorithm).
        try:
            incoming_connection_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            _logger.exception("Setting TCP_NODELAY failed on incoming TCP connection")
            # Continue normal flow; we can in principle work correctly without TCP_NODELAY.

        # Add new connection to socket manager.
        self._socket_manager.add_incoming_connection(incoming_connection_socket)


class _SocketManager:
    """The `SocketManager` manages the UDP and TCP sockets of a context.

    The `SocketManager` manages one UDP responder socket, an optional TCP
    server socket, and possibly multiple TCP peer connection sockets.

    The `SocketManager` runs in a separate thread in an event-driven fashion.
    Unless stated otherwise, the public methods of the `SocketManager` may only
    be called in the socket manager thread.
    """

    def __init__(self, event_loop: asyncio.AbstractEventLoop, message_router: 'MessageRouter') -> None:
        _logger.debug("SocketManager initializing")
        self._event_loop = event_loop
        self._message_router = message_router
        self._lock = threading.Lock()
        self._socket_wrappers = []  # type: list[_SocketWrapper]
        self._peer_context_map = {}  # type: dict[str, _PeerTcpConnection]
        self._peer_name_counter = 0

    def close_all(self) -> None:
        """Close all sockets managed by the SocketManager."""
        _logger.debug("SocketManager closing all sockets")
        with self._lock:
            self._peer_context_map.clear()
        for sock in self._socket_wrappers:
            sock.close()
        self._socket_wrappers.clear()

    def add_tcp_server(self, sock: socket.socket) -> None:
        """Add a TCP server socket."""
        tcp_server = _TcpServer(self._event_loop, self, sock)
        self._socket_wrappers.append(tcp_server)

    def add_udp_responder(self, sock: socket.socket) -> None:
        """Add an UDP responder socket."""
        udp_responder = _UdpResponder(self._event_loop, self._message_router, sock)
        self._socket_wrappers.append(udp_responder)

    def add_incoming_connection(self, sock: socket.socket) -> None:
        """Add an incoming TCP connection from a remote client context.

        The TCP connection is already accepted.
        A handshake with the client still needs to be performed.
        """

        # Assign unique "anonymous" name for the remote side of this connection.
        self._peer_name_counter += 1
        peer_context_alias = f"$client_{self._peer_name_counter}"

        # Wrap socket in PeerTcpConnection object.
        conn = _PeerTcpConnection(self._message_router,
                                  sock,
                                  peer_context_alias,
                                  is_incoming=True)

        # Send handshake and attach to event loop.
        try:
            conn.attach_to_socket_manager(self._event_loop, self)
            conn.send_handshake()
        except Exception as exc:
            _logger.exception("Error on new incoming connection")
            conn.close()
            return

        # Add connection to index of managed sockets.
        self._socket_wrappers.append(conn)
        with self._lock:
            self._peer_context_map[conn.peer_context_alias] = conn

    def add_outgoing_connection(self, conn: _PeerTcpConnection) -> None:
        """Add an outgoing TCP connection to a remote TCP server.

        The TCP connection is already established and the handshake has been completed.
        There must not be an existing connection to a remote peer context with the same name.
        """

        # Check against duplicate peer context name (the MessageRouter already prevents it, but we double-check).
        assert conn.peer_context_alias not in self._peer_context_map

        # Check that the handshake is complete.
        assert conn.peer_context_name is not None

        # Attach connection to the event loop.
        conn.attach_to_socket_manager(self._event_loop, self)

        # Add connection to index of managed sockets.
        self._socket_wrappers.append(conn)
        with self._lock:
            self._peer_context_map[conn.peer_context_alias] = conn

        # Notify MessageRouter that a new peer context was connected.
        self._message_router.notify_peer_context_added(conn.peer_context_alias)

    def remove_peer_connection(self, conn: _PeerTcpConnection) -> None:
        """Remove the specified peer connection from the socket manager.

        This method is called by _PeerTcpConnectionSocket when it detects
        that its connection to the peer context is no longer valid.
        """
        with self._lock:
            peer_context_alias = conn.peer_context_alias
            assert self._peer_context_map[peer_context_alias] is conn
            self._peer_context_map.pop(peer_context_alias)
        self._socket_wrappers.remove(conn)

        # Notify MessageRouter that peer context became disconnected.
        self._message_router.notify_peer_context_removed(peer_context_alias)

    def disconnect_from_peer(self, peer_context_name: str) -> None:
        """Disconnect from the specified peer context."""
        conn = self._peer_context_map.get(peer_context_name)
        if conn is None:
            raise QMI_UnknownNameException(f"Unknown peer context {peer_context_name}")
        self.remove_peer_connection(conn)
        conn.close()

    def send_message(self, message: QMI_Message) -> None:
        """Send the specified message to the right peer context.

        If the destination context is not one of the currently connected
        peer contexts, the message will be dropped. If this happens with
        a request message, a corresponding error reply message will be
        generated.
        """

        # NOTE: This function must not raise exceptions, because any exceptions
        #   raised here would end up in the top level Asyncio event loop.

        assert message.source_address.context_id == self._message_router.context_name

        error_msg: str | None = None

        # Determine which connection to use to send this message.
        destination_context_name = message.destination_address.context_id
        conn = self._peer_context_map.get(destination_context_name)

        if conn is not None:
            try:
                conn.send_message(message)
            except (ValueError, OSError) as exc:
                # TODO qmi#379 - It sometimes happens that a background service
                #     logs 1000s of BrokenPipeError exceptions within 1 second.
                #     To be investigated why this happens.
                _logger.exception(
                    "Error while sending message from %s.%s to %s.%s type %s",
                    message.source_address.context_id,
                    message.source_address.object_id,
                    message.destination_address.context_id,
                    message.destination_address.object_id,
                    type(message))
                error_msg = f"{type(exc).__name__}: {exc!s}"
        else:
            _logger.warning("Unknown message destination context %r", destination_context_name)
            error_msg = f"Unknown message destination context {destination_context_name}"

        # Generate an error reply if we fail to route a request message.
        if (error_msg is not None) and isinstance(message, QMI_RequestMessage):
            reply = QMI_ErrorReplyMessage(source_address=message.destination_address,
                                          destination_address=message.source_address,
                                          request_id=message.request_id,
                                          error_msg=error_msg)
            try:
                self._message_router.deliver_message(reply)
            except QMI_MessageDeliveryException:
                _logger.debug("Failed to deliver error reply to %r", message.source_address)
            except Exception:
                _logger.exception("Unexpected exception while delivering error reply to %r", message.source_address)

    def get_peer_context_names(self) -> list[str]:
        """Return a list of peer context names.

        Note that this method returns context names for outgoing connections,
        as well as local aliases for incoming connections.

        This method is thread-safe and may safely be called from any thread.
        """
        with self._lock:
            peer_context_names = list(self._peer_context_map.keys())
        return peer_context_names

    def has_peer_context(self, peer_context_name: str) -> bool:
        """Return True if a context with specified name is currently connected as a peer.

        This method is thread-safe and may safely be called from any thread.
        Note however that the result of this method may become invalid at any time
        as the set of connected contexts may change asynchronously.
        """
        with self._lock:
            return peer_context_name in self._peer_context_map


class MessageRouter:
    """Sends and delivers messages within a QMI context and between contexts.

    Each QMI context owns one `MessageRouter` instance to handle messaging.
    The `MessageRouter` provides methods to send messages and to register
    QMI objects as message receivers.

    The `MessageRouter` will create a background thread to handle network
    connections.

    This class is intended for internal use within QMI. Application programs
    should not interact with this class directly.
    """

    # Timeout (in seconds) for connecting to a peer context via TCP.
    # This can be quite short since we are working on a LAN.
    # This should be quite short, otherwise context status checking will become too slow.
    CONNECT_TIMEOUT = 2

    # Timeout (in seconds) for initial handshake on outgoing peer connections.
    HANDSHAKE_TIMEOUT = 30

    def __init__(self, context_name: str, workgroup_name: str) -> None:
        self.context_name = context_name
        self.workgroup_name = workgroup_name
        self.tcp_server_port = 0
        self._thread = None  # type: _EventDrivenThread | None
        self._socket_manager = None  # type: _SocketManager | None
        self._address_to_messagehandler_map = {}  # type: dict[str, QMI_MessageHandler]
        self._address_to_messagehandler_map_lock = threading.Lock()
        self._cb_peer_context_added = None    # type: Callable[[str], None] | None
        self._cb_peer_context_removed = None  # type: Callable[[str], None] | None
        self._suppress_version_mismatch_warnings = False

    @property
    def suppress_version_mismatch_warnings(self) -> bool:
        """If set to `True`, no warnings will be issued when connecting to a
        peer that runs a different version of QMI.
        """

        return self._suppress_version_mismatch_warnings

    @suppress_version_mismatch_warnings.setter
    def suppress_version_mismatch_warnings(self, value: bool) -> None:

        self._suppress_version_mismatch_warnings = value

    def set_peer_context_callbacks(self,
                                   cb_peer_context_added: Callable[[str], None] | None,
                                   cb_peer_context_removed: Callable[[str], None] | None) -> None:
        """Register callback functions to be invoked when a peer context is added or removed.

        `cb_peer_context_added(peer_context_name)` is invoked when a new outgoing
        connection to a peer context is established. This callback is not
        invoked for new incoming peer connections.

        `cb_peer_context_removed(peer_context_name)` is invoked when a peer
        connection (outgoing or incoming) is removed.

        The callbacks run in the socket manager thread. These callbacks
        are typically handled by the `SignalManager` to manage its remote
        signal subscriptions.

        This function must not be called after starting the message router.
        """
        assert self._thread is None
        self._cb_peer_context_added = cb_peer_context_added
        self._cb_peer_context_removed = cb_peer_context_removed

    def start(self) -> None:
        """Start the socket manager thread."""

        assert self._thread is None

        # Create event-driven thread for the socket manager.
        self._thread = _EventDrivenThread()
        self._thread.start()

        # Create socket manager inside the thread.
        def make_socket_manager() -> _SocketManager:
            assert self._thread is not None
            assert self._thread.event_loop is not None
            return _SocketManager(self._thread.event_loop, self)
        self._socket_manager = self._thread.run_in_thread_wait(make_socket_manager)
        assert isinstance(self._socket_manager, _SocketManager)

    def stop(self) -> None:
        """Disconnect all peer connections, stop servers and stop the socket manager thread."""

        assert self._thread is not None
        assert self._socket_manager is not None

        # Tell the socket manager to close all sockets.
        self._thread.run_in_thread(self._socket_manager.close_all)
        self._socket_manager = None

        # Stop the thread.
        self._thread.shutdown()
        self._thread.join()
        self._thread = None

    def register_message_handler(self, message_handler: QMI_MessageHandler) -> None:
        """Register a local message handler."""
        assert message_handler.address.context_id == self.context_name
        object_id = message_handler.address.object_id
        with self._address_to_messagehandler_map_lock:
            if object_id in self._address_to_messagehandler_map:
                raise QMI_DuplicateNameException("Can not register duplicate message handler address {}"
                                                 .format(message_handler.address))
            self._address_to_messagehandler_map[object_id] = message_handler

    def unregister_message_handler(self, message_handler: QMI_MessageHandler) -> None:
        """Unregister a previously registered message handler."""
        assert message_handler.address.context_id == self.context_name
        object_id = message_handler.address.object_id
        with self._address_to_messagehandler_map_lock:
            if self._address_to_messagehandler_map.get(object_id) is not message_handler:
                raise QMI_UnknownNameException(f"Unknown message handler {message_handler.address}")
            del self._address_to_messagehandler_map[object_id]

    def start_tcp_server(self, tcp_server_port: int) -> None:
        """Start TCP server for incoming connections from remote contexts.

        Parameters:
            tcp_server_port: TCP server port, or 0 to assign a free port.
        """

        assert self._thread is not None
        assert self._socket_manager is not None
        assert self.tcp_server_port == 0

        _logger.info("Starting TCP server on port %d ...", tcp_server_port)

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind the port so we can be reached from the outside.
        address = ('', tcp_server_port)  # The empty string represents 'INADDR_ANY'.
        sock.bind(address)

        # Start listening for inbound connection requests.
        # Allow for 5 pending connection requests.
        sock.listen(5)

        # Get the actual TCP port number (in case it was automatically assigned).
        (sock_host, self.tcp_server_port) = sock.getsockname()

        # Hand the server socket over to the socket manager.
        self._thread.run_in_thread_arg(self._socket_manager.add_tcp_server, sock)

    def start_udp_responder(self, udp_server_port: int) -> None:
        """Start UDP responder on the specified UDP port."""

        assert self._thread is not None
        assert self._socket_manager is not None
        assert udp_server_port != 0

        _logger.info("Starting UDP responder on port %d ...", udp_server_port)

        sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        # Make sure that the same port can be re-used by multiple QMI_Contexts on the same host.
        #
        # There is a lot of similarity between the older 'SO_REUSEADDR' socket option (already present
        # in BSD before other systems copied its networking stack) and the newer 'SO_REUSEPORT'socket option.
        #
        # See https://stackoverflow.com/questions/14388706 for a deep explanation of their differences.
        #
        # Bottom line:
        #
        # - On Windows there's no choice; only SO_REUSEADDR is available;
        # - On OSX both options are available but SO_REUSEADDR doesn't work for our use-case.
        #        (we get an 'Address already in use' error).
        # - On Linux, both options are available and seem to do what we want.
        #       We default to SO_REUSEADDR.
        #
        if sys.platform in ['darwin']:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)  # type: ignore
        elif sys.platform in ['linux', 'win32']:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        else:
            sock.close()
            raise QMI_RuntimeException(f"Unexpected value for sys.platform ({sys.platform!r})")

        # Bind the port so we can be reached from the outside.
        address = ('', udp_server_port)  # The empty string represents 'INADDR_ANY'.
        sock.bind(address)

        # Hand the UDP server socket over to the socket manager.
        self._thread.run_in_thread_arg(self._socket_manager.add_udp_responder, sock)

    def connect_to_peer(self, peer_context_name: str, peer_address: str) -> None:
        """Connect as a client to a remote QMI context at the specified peer address."""

        assert self._thread is not None
        assert self._socket_manager is not None

        # Check that the peer context name is valid (not anonymous) and not yet connected.
        if peer_context_name.startswith("$"):
            raise QMI_UsageException(f"Invalid peer context name {peer_context_name}")
        if self._socket_manager.has_peer_context(peer_context_name):
            raise QMI_UsageException(f"Duplicate connection to context {peer_context_name} not allowed")

        peer_addr_parsed = parse_address_and_port(peer_address)
        _logger.info("Connecting to peer context %s at %s",
                     peer_context_name,
                     format_address_and_port(peer_addr_parsed))

        # Connect to TCP server at remote context.
        outgoing_connection_socket = socket.create_connection(peer_addr_parsed, timeout=self.CONNECT_TIMEOUT)

        # Now that the connection is established, increase timeout to infinite
        # to get normal blocking semantics.
        outgoing_connection_socket.settimeout(None)

        # Disable delaying of small TCP segments.
        outgoing_connection_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # Wrap socket in PeerTcpConnection object.
        conn = _PeerTcpConnection(self,
                                  outgoing_connection_socket,
                                  peer_context_name,
                                  is_incoming=False)

        # Send handshake and wait for answer.
        try:
            conn.send_handshake()
            conn.receive_handshake(self.HANDSHAKE_TIMEOUT)
        except Exception:
            conn.close()
            raise

        # Verify the name of the peer context.
        if conn.peer_context_name != peer_context_name:
            got_name = conn.peer_context_name
            conn.close()
            raise QMI_RuntimeException("Got handshake from context {} while expecting {}"
                                       .format(got_name, peer_context_name))

        # Verify the version of the peer context.
        if conn.peer_context_version != qmi.__version__ and not self._suppress_version_mismatch_warnings:
            _logger.warning("Version mismatch detected; peer context %s at %s runs version %s (local version is %s)",
                            peer_context_name, format_address_and_port(peer_addr_parsed), conn.peer_context_version,
                            qmi.__version__)

        # Hand the TCP socket over to the socket manager.
        # Note that this transfers the PeerTcpConnection object to the socket manager thread.
        self._thread.run_in_thread_wait(functools.partial(self._socket_manager.add_outgoing_connection, conn))

    def disconnect_from_peer(self, peer_context_name: str) -> None:
        """Disconnect from the specified remote QMI context.

        Raises:
            ~qmi.core.exceptions.QMI_UnknownNameException: If the specified context is not connected.
        """

        assert self._thread is not None
        assert self._socket_manager is not None

        _logger.info("Disconnecting from peer context %s", peer_context_name)
        self._thread.run_in_thread_wait(
            functools.partial(self._socket_manager.disconnect_from_peer, peer_context_name))

    def notify_peer_context_added(self, context_name: str) -> None:
        """Called by the SocketManager when an outgoing peer connection is added.

        This method runs in the socket manager thread.
        """
        if self._cb_peer_context_added is not None:
            self._cb_peer_context_added(context_name)

    def notify_peer_context_removed(self, context_name: str) -> None:
        """Called by the SocketManager when a peer connection is removed.

        This method runs in the socket manager thread.
        """
        if self._cb_peer_context_removed is not None:
            self._cb_peer_context_removed(context_name)

    def deliver_message(self, message: QMI_Message) -> None:
        """Deliver a message to a local message handler.

        This function may be called via `send_message()` for direct local
        delivery of locally originated messages.
        Alternatively, this function may be called by the socket manager
        when a message is received from a peer connection.

        This method is thread-safe. It can be called from any thread.

        Raises:
            QMI_MessageDeliveryException: If the message can not be delivered.
        """
        if message.destination_address.context_id != self.context_name:
            raise QMI_MessageDeliveryException("Can not deliver message to non-local destination {}"
                                               .format(message.destination_address))
        with self._address_to_messagehandler_map_lock:
            message_handler = self._address_to_messagehandler_map.get(message.destination_address.object_id)
        if message_handler is None:
            raise QMI_MessageDeliveryException("Can not deliver message to unknown destination {}"
                                               .format(message.destination_address))
        else:
            message_handler.handle_message(message)

    def send_message(self, message: QMI_Message) -> None:
        """Send the message to its destination.

        If the destination is within the local context, this function delivers
        the message to the local message handler. Otherwise, this function
        sends the message to the correct peer context.

        This method is thread-safe. It can be called from any thread.

        Raises:
            QMI_MessageDeliveryException: If the message can not be routed.
        """

        destination_context_name = message.destination_address.context_id
        if destination_context_name == self.context_name:

            # The destination_address is our context; perform local delivery of the message.
            self.deliver_message(message)

        else:

            # We never forward messages from remote context to remote context.
            if message.source_address.context_id != self.context_name:
                raise QMI_MessageDeliveryException(
                    "Can not send message from remote context {} to remote context {}"
                    .format(message.source_address.context_id, destination_context_name))

            # Check that the socket manager is running (message router started).
            socket_thread = self._thread
            socket_manager = self._socket_manager
            if (socket_thread is None) or (socket_manager is None):
                raise QMI_MessageDeliveryException("Can not send message to {!r} - message router inactive"
                                                   .format(message.destination_address))

            # Let the socket manager handle remote message delivery.
            if not socket_manager.has_peer_context(destination_context_name):
                raise QMI_MessageDeliveryException("Can not send message to unknown context {!r}"
                                                   .format(destination_context_name))
            socket_thread.run_in_thread_arg(socket_manager.send_message, message)

    def get_peer_context_names(self) -> list[str]:
        """Return a list of currently connected peer context names."""
        socket_manager = self._socket_manager
        if socket_manager is not None:
            return socket_manager.get_peer_context_names()
        else:
            return []
