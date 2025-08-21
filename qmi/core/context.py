"""Implementation of the QMI_Context class.
"""

import logging
import os
import pathlib
import random
import re
import selectors
import socket
import string
import threading
import time
import warnings
import atexit

from collections.abc import Callable
from typing import Any, NamedTuple

import qmi

from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.exceptions import QMI_UsageException, QMI_DuplicateNameException, QMI_UnknownNameException, \
                                QMI_ConfigurationException, QMI_InvalidOperationException, QMI_WrongThreadException
from qmi.core.messaging import MessageRouter, QMI_Message, QMI_MessageHandlerAddress, QMI_MessageHandler
from qmi.core.rpc import QMI_RpcObject, QMI_RpcProxy, RpcObjectManager, rpc_method, RpcObjectDescriptor, \
                         make_interface_descriptor, QMI_LockTokenDescriptor
from qmi.core.pubsub import SignalManager, QMI_SignalReceiver
from qmi.core.instrument import QMI_Instrument
from qmi.core.task import QMI_Task, QMI_TaskRunner
from qmi.core.udp_responder_packets import unpack_qmi_udp_packet, QMI_UdpResponderContextInfoRequestPacket, \
                                           QMI_UdpResponderContextInfoResponsePacket
from qmi.core.util import is_valid_object_name, format_address_and_port, AtomicCounter


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


# Global variable counting the number of active contexts.
_active_context_counter = AtomicCounter()


@atexit.register
def _check_active_contexts() -> None:
    """Check that there are no active QMI contexts when the program exits.

    This function runs just before the Python program exits.
    It emits a warning if there are still active QMI contexts.

    Programs that use QMI should always stop their QMI context before
    the program ends, to ensure that resources such as network connections
    and background threads are properly cleaned up.
    """

    count = _active_context_counter.value()
    if count:
        # Note: ResourceWarning is by default not displayed in Python.
        warnings.warn(f"Still {count} active QMI contexts at program exit", ResourceWarning)


class _UdpPingResponse(NamedTuple):
    """Ping response descriptor."""
    received_timestamp: float
    incoming_address: tuple[str, int]
    response_packet: QMI_UdpResponderContextInfoResponsePacket


def ping_qmi_contexts(
    workgroup_name_filter: str,
    context_name_filter: str = "*",
    timeout: float = 0.1
) -> list[_UdpPingResponse]:
    """Broadcast an info request message to discover all QMI contexts on the network.

    Parameters:
        workgroup_name_filter: Filter on workgroup name.
        context_name_filter:   Filter on context name (default: "*").
        timeout:               Time to wait for answers (default: 0.1).
    """
    responses = []

    # Prepare a socket.
    udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    try:
        # Configure the socket.
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        address_in = ("", 0)  # the empty string represents INADDR_ANY; port 0 means: give me any port
        udp_socket.bind(address_in)

        # Prepare the outgoing packet.
        request_pkt_id = random.randint(1, 2**64 - 1)
        request_packet = QMI_UdpResponderContextInfoRequestPacket.create(
            request_pkt_id,
            time.time(),
            workgroup_name_filter.encode(),
            context_name_filter.encode()
        )
        address_out = ("<broadcast>", QMI_Context.DEFAULT_UDP_RESPONDER_PORT)
        udp_socket.sendto(request_packet, address_out)  # type: ignore

        # Collect answers.
        wait_until = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            key_udp_packet_received = selector.register(udp_socket, selectors.EVENT_READ)

            while True:
                t_now = time.monotonic()
                if t_now >= wait_until:
                    break

                for key, _ in selector.select(wait_until - t_now):
                    if key is key_udp_packet_received:

                        # A packet is received, determine if it is a response packet/
                        response_packet, incoming_address = udp_socket.recvfrom(4096)
                        response_received_timestamp = time.time()

                        try:
                            unpacked_response_packet = unpack_qmi_udp_packet(response_packet)
                        except BaseException:
                            continue  # ignore unpack failure; probably not a QMI packet

                        if not isinstance(unpacked_response_packet, QMI_UdpResponderContextInfoResponsePacket):
                            continue  # not a response

                        if unpacked_response_packet.request_pkt_id != request_pkt_id:
                            continue  # not a response to our request

                        # The packet is a response to our broadcast.
                        response = _UdpPingResponse(
                            received_timestamp=response_received_timestamp,
                            incoming_address=incoming_address,
                            response_packet=unpacked_response_packet
                        )
                        responses.append(response)

    finally:
        udp_socket.close()

    return responses


class _ContextRpcObject(QMI_RpcObject):
    """Internal class, used to provide information about the local context via RPC."""

    @classmethod
    def get_category(cls) -> str | None:
        return "context"

    @rpc_method
    def get_version(self) -> str:
        """Return the QMI version used by this context."""
        return self._context.get_version()

    @rpc_method
    def get_rpc_object_descriptors(self) -> list[RpcObjectDescriptor]:
        """Get a list RPC descriptors of the objects in this context."""
        return self._context.get_rpc_object_descriptors()

    @rpc_method
    def get_rpc_object_descriptor(self, rpc_object_name: str) -> RpcObjectDescriptor | None:
        """Get an RPC descriptor for the object with the given name."""
        return self._context.get_rpc_object_descriptor(rpc_object_name)

    @rpc_method
    def get_pid(self) -> int:
        """Return process ID of Python program."""
        return os.getpid()

    @rpc_method
    def shutdown_context(self, hard: bool) -> None:
        """Tell the context to shut down.

        A normal (soft) shutdown requires active cooperation from the main
        program. It sets a flag to indicate that a shutdown request was received.
        The main program should actively monitor this flag to perform cleanup
        and exit as soon as the flag is set.

        A hard shutdown will almost always succeed but may leave instruments
        and data files in an unclean state.

        Parameters:
            hard: Set to True if process should be exited immediately. Otherwise, normal shutdown.
        """

        if hard:
            # Exit the process now (this also exits all threads).
            _logger.info("Received hard shutdown request")
            print("Answering external hard-kill request, exiting with exitcode 1.")
            os._exit(1)

        else:
            # Set the shutdown request flag.
            _logger.info("Received soft shutdown request")
            self._context._context_shutdown_requested.set()


class QMI_Context:
    """Represents an application or script within the QMI system.

    The `QMI_Context` is the main entry point to QMI functionality.
    It keeps track of *instruments*, *tasks*, *signals*, *RPC objects*
    and *connections* to other contexts. It provides functionality to create
    and access these objects, and to interact with objects in other contexts.

    Internally, the QMI context will create Python threads to perform certain
    tasks in the background.

    Unless stated otherwise, methods of the `QMI_Context` instance may only
    be called from the thread that created the context. A few specific methods
    may safely be called from any thread; this is explicitly stated in the
    documentation of the method when it applies.

    In most Python programs that use the QMI framework, there is exactly
    one instance of QMI_Context. This instance is created when the application
    calls ``qmi.start(...)`` and destroyed when the application calls ``qmi.stop()``.

    Attributes:
        DEFAULT_UDP_RESPONDER_PORT: Default port number for UDP responses.
    """

    DEFAULT_UDP_RESPONDER_PORT = 35999

    def __init__(self, name: str, config: CfgQmi | None = None) -> None:
        """Create a new `QMI_Context` instance.

        This is normally done automatically by ``qmi.start(...)``.
        Most applications should not explicitly create a `QMI_Context` instance.

        The class attribute workgroup_name contains the name of the QMI workgroup (read-only).

        Parameters:
            name:   Name of the context.
                    This must be a short string without spaces or strange characters.
                    If other contexts will connect to this context, its name must
                    be unique within the workgroup (i.e. among all Python processes
                    that work together via QMI).
            config: QMI configuration data.
        """

        _logger.debug("Initializing context %r", name)

        # The "active" variable indicates if the context is currently active.
        self._active = False

        # The "used" variable prevents restarting the context after it was previously stopped.
        self._used = False

        # Event which is set to true when the context receives a shutdown request via RPC.
        self._context_shutdown_requested = threading.Event()

        # Program start time (can be used to create log file names etc.).
        self._start_time = time.time()

        if not is_valid_object_name(name):
            raise QMI_UsageException(f"Invalid context name {name!r}")

        self.name = name
        self._unique_counters: dict[str, int] = {}
        self._unique_counters_lock = threading.Lock()
        self._rpc_object_map: dict[str, RpcObjectManager | None] = {}
        self._rpc_object_map_lock = threading.Lock()

        # Remember in which thread this context was created.
        self._creation_thread = threading.current_thread()

        if config is None:
            # Initialize to an empty configuration.
            config = CfgQmi()

        self._config = config

        # Determine workgroup name from configuration.
        self._workgroup_name = self._config.workgroup

        # Create message router.
        self._message_router = MessageRouter(self.name, self._workgroup_name)

        # Create signal manager.
        self._signal_manager = SignalManager(self)
        self._message_router.set_peer_context_callbacks(None, self._signal_manager.handle_peer_context_removed)

        # Create RPC object to answer queries about this context.
        self._internal_make_rpc_object("$context", _ContextRpcObject)

        # List of callback function to be invoked when the context stops.
        self._stop_handlers: list[Callable[[], None]] = []

        # Set object ID.
        self._oid = qmi.object_registry.register(self)

    @property
    def suppress_version_mismatch_warnings(self) -> bool:
        """If set to `True`, no warnings will be issued when connecting to a
        peer that runs a different version of QMI.
        """

        return self._message_router.suppress_version_mismatch_warnings

    @suppress_version_mismatch_warnings.setter
    def suppress_version_mismatch_warnings(self, value: bool) -> None:

        self._message_router.suppress_version_mismatch_warnings = value

    @property
    def workgroup_name(self) -> str:
        """Make '_workgroup_name' as read-only property."""
        return self._workgroup_name

    def __repr__(self) -> str:
        return f"QMI_Context(name={self.name!r})"

    def _check_in_context_thread(self) -> None:
        """Check that this function is called in the same thread that created the context.

        Raises:
            QMI_WrongThreadException: If the function is called from any
                thread other than the thread that created this context.
        """
        if threading.current_thread() is not self._creation_thread:
            raise QMI_WrongThreadException("Not in context main thread")

    def get_config(self) -> CfgQmi:
        """Return the QMI configuration.

        The QMI configuration is a hierarchical data structure consisting
        of Python dataclass instances. The QMI configuration is typically
        initialized by reading the QMI configuration file during program startup.

        It is not allowed to modify the configuration data structure
        returned by this function.

        Returns:
            self._config: The QMI configuration data.
        """
        return self._config

    def get_context_config(self) -> CfgContext:
        """Return the subset of the QMI configuration specific for this context.

        The QMI configuration contains a mapping that applies to this context.

        Returns:
            ctxcfg: The QMI configuration subset specific for this context.
        """
        ctxcfg = self._config.contexts.get(self.name)
        if ctxcfg is None:
            ctxcfg = CfgContext()
        return ctxcfg

    def get_qmi_home_dir(self) -> str:
        """Return the QMI home directory.

        The QMI home directory is the location where QMI expects to find
        configuration files and data.

        The QMI home directory may be specified in the QMI configuration file.
        Otherwise, if the environment variable `QMI_HOME` is set, it contains
        the path of the QMI home directory.
        Otherwise, the user home directory will be used as QMI home directory.

        Returns:
            qmi_home: The QMI home directory.
        """

        # Try to get home directory from configuration.
        cfg = self.get_config()
        qmi_home = cfg.qmi_home

        # Try to get home directory from environment.
        if not qmi_home:
            qmi_home = os.getenv("QMI_HOME")

        # Take user home directory as fall-back.
        if not qmi_home:
            qmi_home = str(pathlib.Path.home())

        return qmi_home

    def get_log_dir(self) -> str:
        """Return the directory where log files should be written."""
        cfg = self.get_config()
        if cfg.log_dir:
            return self.resolve_file_name(cfg.log_dir)
        else:
            # No log_dir configured; use the QMI home directory.
            return self.get_qmi_home_dir()

    @staticmethod
    def _file_name_resolves_keyword(file_name: str, keyword: str) -> bool:
        """Return True if the specified file name uses a specific "${keyword}" substitution."""
        for m in re.finditer(r"\$(?:\$|([_a-z][_a-z0-9]*)|{([_a-z][_a-z0-9]*)})", file_name, re.IGNORECASE):
            refname = m.group(1) or m.group(2)
            if refname == keyword:
                return True
        return False

    def get_datastore_dir(self) -> str:
        """Return the base directory of the DataStore repository."""

        cfg = self.get_config()
        datastore_dir = cfg.datastore
        if not datastore_dir:
            raise QMI_ConfigurationException("Missing field 'datastore' in QMI configuration")

        # Avoid recursive calls to get_datastore_dir().
        if self._file_name_resolves_keyword(datastore_dir, "datastore"):
            raise QMI_ConfigurationException("Recursive reference to 'datastore' directory")

        return self.resolve_file_name(datastore_dir)

    def resolve_file_name(self, file_name: str) -> str:
        """Apply substitutions to a configured file name.

        The following substitutions are supported::

          $$            -> "$"
          ${context}    -> context name
          ${qmi_home}   -> QMI home directory
          ${datastore}  -> QMI datastore directory
          ${config_dir} -> directory of QMI configuration file
          ${date}       -> date of program start, UTC, formatted as YYYY-mm-dd
          ${datetime}   -> time of program start, UTC, formatted as YYYY-mm-ddTHH-MM-SS

        Returns:
            The substituted file name if any of the supported substitutions were present. Else, the file name.
        """

        # Fast path.
        if "$" not in file_name:
            return file_name

        qmi_home = self.get_qmi_home_dir()

        # Determine configuration directory.
        config_file = self._config.config_file
        if config_file:
            config_dir = os.path.dirname(config_file)
        else:
            config_dir = qmi_home

        # Format date and time.
        gmtime = time.gmtime(self._start_time)
        date = time.strftime("%Y-%m-%d", gmtime)
        datetime = time.strftime("%Y-%m-%dT%H-%M-%S", gmtime)

        mapping = {
            "context": self.name,
            "qmi_home": qmi_home,
            "config_dir": config_dir,
            "date": date,
            "datetime": datetime
        }

        # Avoid unnecessary calls to get_datastore_dir() because
        # - such calls fail if the datastore path is not configured;
        # - such calls lead to infinite recursion when resolving the datastore path.
        if self._file_name_resolves_keyword(file_name, "datastore"):
            mapping["datastore"] = self.get_datastore_dir()

        return os.path.normpath(string.Template(file_name).substitute(mapping))

    def start(self) -> None:
        """Start the context.

        A `QMI_Context` instance must be started before creating any tasks
        or sending any messages. This happens automatically when the
        application calls ``qmi.start(...)``.
        """

        self._check_in_context_thread()

        _logger.info("Starting QMI context %r", self.name)
        if self._active:
            raise QMI_UsageException("QMI_Context already started")

        # Check that this context has never been started yet.
        if self._used:
            raise QMI_UsageException("Can not start QMI_Context a second time")

        # Start message router.
        self._message_router.start()

        # Start TCP server if a TCP server port is specified in the configuration.
        ctxcfg = self.get_context_config()
        if ctxcfg.tcp_server_port is not None:
            self._message_router.start_tcp_server(ctxcfg.tcp_server_port)

        # The UDP responder is mandatory.
        self._message_router.start_udp_responder(self.DEFAULT_UDP_RESPONDER_PORT)

        # Mark that we're now active.
        self._active = True
        self._used = True
        _active_context_counter.inc()
        _logger.info("QMI context %r now active", self.name)

    def stop(self) -> None:
        """Stop the context.

        After the context is stopped, it must not be used anymore.
        A stopped context may not be started a second time.
        """

        self._check_in_context_thread()

        _logger.info("Stopping QMI context %r", self.name)
        if not self._active:
            raise QMI_UsageException("QMI_Context already inactive")

        # Invoke callback functions to allow subsystems to stop.
        for stop_handler in self._stop_handlers:
            try:
                stop_handler()
            except Exception as exc:
                # The callback function failed, but we still want to
                # continue shutting down QMI. Report the exception and ignore.
                _logger.exception("QMI stop handler failed: %s", str(exc))
            del stop_handler

        self._message_router.stop()

        with self._rpc_object_map_lock:

            # Mark that we're now inactive.
            # No new RPC objects can be created after this point.
            self._active = False

            # Find remaining RPC objects managed by this context.
            managers = []
            for (rpc_object_name, manager) in list(self._rpc_object_map.items()):
                if manager is not None:
                    managers.append(manager)
                    del self._rpc_object_map[rpc_object_name]

        # Stop remaining RPC objects.
        for manager in managers:
            self.unregister_message_handler(manager)
            manager.stop()

        # Update number of active contexts.
        _active_context_counter.dec()

        qmi.object_registry.unregister(self._oid)

    def shutdown_requested(self) -> bool:
        """Return True if the context has received a shutdown request via RPC.

        A background program may call this function to check whether a shutdown
        request has been received. If this function returns True, the program
        should clean up and exit.
        """
        return self._context_shutdown_requested.is_set()

    def wait_until_shutdown(self, duration: float) -> bool:
        """Wait until a shutdown request is received.

        Parameters:
            duration: Maximum wait time in seconds.

        Returns:
            True:  If a shutdown request is received.
            False: If the wait duration expires before a shutdown request is received.
        """
        return self._context_shutdown_requested.wait(duration)

    def register_stop_handler(self, handler: Callable[[], None]) -> None:
        """Register a callback function to be invoked when this context stops.

        Parameters:
            handler: Function to be called (without arguments) when the context stops.
        """
        self._check_in_context_thread()
        self._stop_handlers.append(handler)

    def send_message(self, message: QMI_Message) -> None:
        """Send a message to its destination.

        If the destination is within the local context, this function delivers
        the message to the local message handler. Otherwise, this function
        sends the message to the correct peer context.

        This method is thread-safe. It can be called from any thread.

        Raises:
            ~qmi.core.exceptions.QMI_MessageDeliveryException: If the message can not be routed.
        """
        self._message_router.send_message(message)

    def connect_to_peer(
        self,
        peer_context_name: str,
        peer_address: str | None = None,
        ignore_duplicate: bool = False
    ) -> None:
        """Connect to the specified peer context.

        Parameters:
            peer_context_name: Name of the peer context to connect to.
            peer_address:      IP address and TCP port of the peer context, formatted as ``"<addr>:<port>"``.
                               When not specified, the peer address will be taken from the QMI configuration.
            ignore_duplicate:  When True, nothing will happen if a connection
                               to the specified context already exists.
        """
        self._check_in_context_thread()
        if not self._active:
            raise QMI_InvalidOperationException("Inactive context can not connect to peer")

        if ignore_duplicate:
            # Do nothing if we are already connected to this peer context.
            if self.has_peer_context(peer_context_name):
                return

        if not peer_address:
            # Get remote context configuration.
            cfg = self.get_config()
            peer_cfg = cfg.contexts.get(peer_context_name)
            if peer_cfg is None:
                raise QMI_UnknownNameException(f"Unknown remote context {peer_context_name}")
            if (not peer_cfg.host) or (not peer_cfg.tcp_server_port):
                raise QMI_ConfigurationException(f"Missing host/port for peer context {peer_context_name}")
            peer_address = format_address_and_port((peer_cfg.host, int(peer_cfg.tcp_server_port)))

        # Make new peer connection.
        self._message_router.connect_to_peer(peer_context_name, peer_address)

    def disconnect_from_peer(self, peer_context_name: str) -> None:
        """Disconnect from the specified remote QMI context.

        Raises:
            ~qmi.core.exceptions.QMI_UnknownNameException: If the specified context is not connected.
        """
        self._check_in_context_thread()
        if not self._active:
            raise QMI_InvalidOperationException("Inactive context can not have peers")
        self._message_router.disconnect_from_peer(peer_context_name)

    def has_peer_context(self, peer_context_name: str) -> bool:
        """Return True if a context with specified name is currently connected as a peer.

        Note that the result of this method may become invalid at any time
        as the set of connected contexts may change asynchronously.
        """
        context_names = self._message_router.get_peer_context_names()
        return peer_context_name in context_names

    def discover_peer_contexts(
        self,
        workgroup_name_filter: str | None = None,
        context_name_filter: str = "*"
    ) -> list[tuple[str, str]]:
        """Discover QMI contexts on the network.

        You can filter on workgroup name and/or context name via the optional arguments. Use a "*" to match any
        sequence of characters (e.g. "ba*" matches "bar", "baz" and "ball") and a "?" to match a single character (e.g.
        "ba?" matches "bar" and "baz", but not "ball"). Filters are case-sensitive.

        Parameters:
            workgroup_name_filter: Filter on workgroup name (None: use the workgroup name of this context's config).
            context_name_filter:   Filter on context name (default: "*").

        Returns:
             contexts: A list of (context_name, address:port)-pairs that can be passed to `connect_to_peer`.
        """
        if workgroup_name_filter is None:
            workgroup_name_filter = self._config.workgroup

        responses = ping_qmi_contexts(
            workgroup_name_filter=workgroup_name_filter,
            context_name_filter=context_name_filter
        )
        contexts: list[tuple[str, str]] = []
        for resp in responses:
            address = resp.incoming_address[0]
            port = resp.response_packet.context.port
            context_name = resp.response_packet.context.name.decode()

            if context_name != self.name:
                contexts.append((context_name, f"{address}:{port}"))

        return contexts

    def register_message_handler(self, message_handler: QMI_MessageHandler) -> None:
        """Register a new message handler.

        The message handler must be a local object (in the same context)
        and it must have a unique object ID within the context.

        This function is intended for internal use within QMI.
        Application programs should not need to call this function.

        Parameters:
            message_handler: New message handler to be registered.
        """
        self._message_router.register_message_handler(message_handler)

    def unregister_message_handler(self, message_handler: QMI_MessageHandler) -> None:
        """Unregister an existing message handler.

        This function removes a message handler from the context.
        After this function returns, no further messages will be delivered
        to the specified handler.
        The specified object must currently be registered as a message handler.

        This function is intended for internal use within QMI.
        Application programs should not need to call this function.

        Parameters:
            message_handler: The message handler to be unregistered.
        """
        self._message_router.unregister_message_handler(message_handler)

    def info(self) -> str:
        """Return information about the context."""
        ret: list[str] = [
            "*** QMI_Context info: name={!r}, workgroup={!r}, pid={!r} ***".format(
                self.name, self.workgroup_name, os.getpid()
            ), "", "*** end of QMI_Context info ***"
        ]
        return "\n".join(ret)

    def get_version(self) -> str:
        """Return the QMI version used by this context."""
        return qmi.__version__

    def get_tcp_server_port(self) -> int:
        """Return the TCP server port for this context, or return 0 if this context does not have a TCP server."""
        if self._active:
            return self._message_router.tcp_server_port
        else:
            return 0

    def get_rpc_object_descriptors(self) -> list[RpcObjectDescriptor]:
        """Return a list of descriptors for all local RPC objects."""
        ret = []
        with self._rpc_object_map_lock:
            for manager in self._rpc_object_map.values():
                if manager is not None:
                    rpc_object = manager.rpc_object()
                    ret.append(rpc_object.rpc_object_descriptor)
        return ret

    def get_rpc_object_descriptor(self, rpc_object_name: str) -> RpcObjectDescriptor | None:
        """Return a descriptor for the specified local RPC object if object is managed, else None."""
        with self._rpc_object_map_lock:
            manager = self._rpc_object_map.get(rpc_object_name)
            if manager is not None:
                rpc_object = manager.rpc_object()
                return rpc_object.rpc_object_descriptor
        return None

    def make_unique_address(self, prefix: str) -> QMI_MessageHandlerAddress:
        """Generate a unique message handler address with a specified prefix."""
        with self._unique_counters_lock:
            nr = self._unique_counters.get(prefix, 0) + 1
            self._unique_counters[prefix] = nr
        return QMI_MessageHandlerAddress(self.name, prefix + str(nr))

    def make_unique_token(self, prefix: str = "$lock_") -> QMI_LockTokenDescriptor:
        """Generate and return a unique token descriptor."""
        with self._unique_counters_lock:
            nr = self._unique_counters.get(prefix, 0) + 1
            self._unique_counters[prefix] = nr
        return QMI_LockTokenDescriptor(self.name, prefix + str(nr))

    def make_rpc_object(
        self,
        rpc_object_name: str,
        rpc_object_class: type[QMI_RpcObject],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Create an instance of a `QMI_RpcObject` and return a proxy for the new object instance.

        The actual object instance will be created in a separate background thread.
        You can call its methods via RPC, using the proxy object returned by this function.

        The return type of the make_XXX() methods is not annotated.
        It is not possible to provide a precise annotation, because the actual return type is "rpc_object_class.Proxy"
        which is a programmatically constructed class and thus not available for static type checking.

        Parameters:
            rpc_object_name:  Name for the new object instance, unique within the local context.
            rpc_object_class: Class that implements this object (must be a subclass of `QMI_RpcObject`).
            args:             Optional arguments for the class constructor.
            kwargs:           Optional keyword arguments for the class constructor.

        Returns:
            An RPC proxy that provides access to the new object instance.
        """
        if not is_valid_object_name(rpc_object_name):
            raise QMI_UsageException(f"Invalid object name {rpc_object_name!r}")

        return self._internal_make_rpc_object(rpc_object_name, rpc_object_class, *args, **kwargs)

    def _internal_make_rpc_object(
        self,
        rpc_object_name: str,
        rpc_object_class: type[QMI_RpcObject],
        *args: Any,
        **kwargs: Any,
    ) -> QMI_RpcProxy:
        """Helper function to create the actual RPC object instance."""
        def rpc_object_maker() -> QMI_RpcObject:
            return rpc_object_class(self, rpc_object_name, *args, **kwargs)

        manager = None
        proxy = None

        with self._rpc_object_map_lock:
            # Check that context is active.
            # Only internal RPC objects may be created when the context is not active.
            if (not self._active) and (not rpc_object_name.startswith("$")):
                raise QMI_InvalidOperationException("Can not create RPC object in inactive context")

            # Check unique name.
            if rpc_object_name in self._rpc_object_map:
                raise QMI_DuplicateNameException(f"Duplicate object name {rpc_object_name}")

            # Reserve name.
            self._rpc_object_map[rpc_object_name] = None

        try:
            # Create RPC object manager and start it.
            address = QMI_MessageHandlerAddress(self.name, rpc_object_name)
            manager = RpcObjectManager(address, self, rpc_object_maker)
            manager.start()

            try:
                # Make a proxy for the RPC object.
                # This blocks until the RPC object is initialized,
                # and may raise an exception if initialization fails.
                proxy = manager.make_proxy()

                with self._rpc_object_map_lock:

                    # Check that context is still active.
                    if (not self._active) and (not rpc_object_name.startswith("$")):
                        proxy = None
                        raise QMI_InvalidOperationException("Can not create RPC object in inactive context")

                    # Register the object manager under the claimed name.
                    self._rpc_object_map[rpc_object_name] = manager

                # Register the object manager as message handler.
                self.register_message_handler(manager)

            finally:
                if proxy is None:
                    # Initialization failed. Shut down the object manager.
                    manager.stop()
                    manager = None

        finally:
            if manager is None:
                # RPC object creation failed. Release the claimed name.
                with self._rpc_object_map_lock:
                    del self._rpc_object_map[rpc_object_name]

        return proxy

    def remove_rpc_object(self, proxy: QMI_RpcProxy) -> None:
        """Stop the specified RPC object and release its resources.

        This can only be used for RPC objects running in the local context.

        Parameters:
            proxy: Proxy for the RPC object to be removed.
        """

        # Check that the proxy refers to a local object.
        if proxy._rpc_object_address.context_id != self.name:
            raise QMI_UsageException(f"Can not remove remote RPC object {proxy._rpc_object_address}")

        rpc_object_name = proxy._rpc_object_address.object_id

        with self._rpc_object_map_lock:

            # Find the RPC object manager.
            manager = self._rpc_object_map.get(rpc_object_name)
            if manager is None:
                raise QMI_UnknownNameException(f"Can not remove unknown RPC object {rpc_object_name}")

            # Mark the object as being removed.
            self._rpc_object_map[rpc_object_name] = None

        # Unregister the manager as message handler.
        self.unregister_message_handler(manager)

        # Drop subscriptions on signals published by this object.
        self._signal_manager.handle_object_removed(rpc_object_name)

        # Release the claimed object name.
        with self._rpc_object_map_lock:
            del self._rpc_object_map[rpc_object_name]

        # Shut down the object manager.
        manager.stop()

    def make_instrument(
        self,
        instrument_name: str,
        instrument_class: type[QMI_Instrument],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Create an instance of a `QMI_Instrument` subclass and make it accessible via RPC.

        The actual instrument instance will be created in a separate background thread.
        To access the instrument, you can call its methods via RPC.

        Parameters:
            instrument_name:  Unique name for the new instrument instance.
                              This name will also be used to access the instrument via RPC.
            instrument_class: Class that implements this instrument (must be a subclass of `QMI_Instrument`).
            args:             Optional arguments for the instrument class constructor.
            kwargs:           Optional keyword arguments for the instrument class constructor.

        Returns:
            An RPC proxy that provides access to the new instrument instance.
        """
        return self.make_rpc_object(instrument_name, instrument_class, *args, **kwargs)

    def make_task(
        self,
        task_name: str,
        task_class: type[QMI_Task],
        *args: Any,
        task_runner: type[QMI_TaskRunner] = QMI_TaskRunner,
        **kwargs: Any
    ) -> Any:
        """Create an instance of a `QMI_Task` subclass and make it accessible via RPC.

        The task instance will be created in a separate thread.
        A `QMI_TaskRunner` will be created to manage the task thread.
        The task can be accessed by calling the methods of the task runner via RPC.

        Note that the task is not yet started.
        To start the task, perform an explicit call to the `start()` method of the returned task.

        Parameters:
            task_name:   Unique name for the new task instance.
                         This name will also be used to access the task runner via RPC.
            task_class:  Class that implements this task (must be a subclass of `QMI_Task`).
            args:        Optional arguments for the task class constructor.
            task_runner: Class that implements the managing of the task (must be a subclass of `QMI_Taskrunner`)
            kwargs:      Optional keyword arguments for the task class constructor.

        Returns:
            An RPC proxy that provides access to the new task.
        """
        return self.make_rpc_object(task_name, task_runner, task_class, args, kwargs)

    def make_proxy(self, rpc_object_descriptor: RpcObjectDescriptor) -> Any:
        """Return a proxy for the specified object descriptor.

        This function is intended for internal use within QMI. Application programs
        should not call this function directly.

        Parameters:
            rpc_object_descriptor: `RpcObjectDescriptor` uniquely identifying an RPC object.

        Returns:
            Proxy for the specified RPC object.
        """
        assert isinstance(rpc_object_descriptor, RpcObjectDescriptor)
        return QMI_RpcProxy(self, rpc_object_descriptor)

    def _make_peer_context_descriptor(self, context_name: str) -> RpcObjectDescriptor:
        address = QMI_MessageHandlerAddress(context_id=context_name, object_id="$context")
        category = _ContextRpcObject.get_category()
        interface = make_interface_descriptor(_ContextRpcObject)
        return RpcObjectDescriptor(address=address, category=category, interface=interface)

    def make_peer_context_proxy(self, context_name: str) -> Any:
        """Return a proxy for the internal `$context` object of the specified peer context.

        This function is intended for internal use within QMI. Application programs
        should not call this function directly.

        Parameters:
            context_name: Name of the peer context.

        Returns:
            A proxy for the internal context RPC object of the specified peer context.
        """
        descriptor = self._make_peer_context_descriptor(context_name)
        return self.make_proxy(descriptor)

    def _get_context_descriptors(self, include_self: bool = True) -> list[RpcObjectDescriptor]:
        context_names = []
        if include_self:
            context_names.append(self.name)
        context_names.extend(self._message_router.get_peer_context_names())

        return [
            self._make_peer_context_descriptor(context_name) for context_name in context_names
            if not context_name.startswith("$")
        ]

    def show_network_contexts(self):
        """Show a list of contexts that are on the network."""
        contexts = self.discover_peer_contexts()

        print()
        if len(contexts) == 0:
            print("No contexts found.")
        else:
            all_names, all_addresses = zip(*contexts)
            max_name_length = max(len(name) for name in all_names)
            max_addr_length = max(len(addr) for addr in all_addresses)

            name_hdr = "name"
            addr_hdr = "address"
            conn_hdr = "connected"

            name_wdt = max(len(name_hdr), max_name_length)
            addr_wdt = max(len(addr_hdr), max_addr_length)
            conn_wdt = len(conn_hdr)

            print(f"{name_hdr.ljust(name_wdt)} {addr_hdr.ljust(addr_wdt)} {conn_hdr}")
            print(f"{'-' * name_wdt} {'-' * addr_wdt} {'-' * conn_wdt}")
            for context_name, context_address in contexts:
                if self.has_peer_context(context_name):
                    connected = "yes"
                else:
                    connected = "no"

                print(f"{context_name.ljust(name_wdt)} {context_address.ljust(addr_wdt)} {connected}")

            print(f"{'-' * name_wdt} {'-' * addr_wdt} {'-' * conn_wdt}")

    def list_rpc_objects(self, category: str | None = None) -> list[tuple[str, str]]:
        """Returns a list of tuple strings of RPC objects addresses in the local context and in peer context."""
        rpc_objects = []
        for peer_context_descriptor in self._get_context_descriptors():
            peer_context_proxy = self.make_proxy(peer_context_descriptor)
            rpc_object_descriptors = peer_context_proxy.get_rpc_object_descriptors()
            for rpc_object_descriptor in rpc_object_descriptors:
                if category is not None and rpc_object_descriptor.category != category:
                    continue

                rpc_object = (str(rpc_object_descriptor.address), str(rpc_object_descriptor.interface.rpc_class_name))
                rpc_objects.append(rpc_object)

        rpc_objects.sort()
        return rpc_objects

    def show_rpc_objects(self, category: str | None = None) -> None:
        """Show a list of RPC objects in the local context and peer contexts."""

        rpc_objects = self.list_rpc_objects(category)

        print()
        if len(rpc_objects) == 0:
            print("No objects found.")

        else:
            max_address_length = max(max(len(address) for address, _ in rpc_objects), 7)
            max_class_name_length = max(max(len(class_name) for _, class_name in rpc_objects), 4)

            print(f"{'address'.ljust(max_address_length)}  type")
            print(f"{'-' * max_address_length}  {'-' * max_class_name_length}")
            for address, class_name in rpc_objects:
                print(f"{address.ljust(max_address_length)}  {class_name}")
            print(f"{'-' * max_address_length}  {'-' * max_class_name_length}")

    def show_tasks(self) -> None:
        """Show a list of tasks in the local context and peer contexts."""
        self.show_rpc_objects(QMI_TaskRunner.get_category())

    def show_instruments(self) -> None:
        """Show a list of instruments in the local context and peer contexts."""
        self.show_rpc_objects(QMI_Instrument.get_category())

    def show_contexts(self) -> None:
        """Show a list of currently connected contexts (including the local context)."""
        self.show_rpc_objects(_ContextRpcObject.get_category())

    def get_rpc_object_by_name(
        self,
        rpc_object_name: str,
        auto_connect: bool = False,
        host_port: str | None = None
    ) -> Any:
        """Return a proxy for the specified RPC object.

        The object may exist either in the local context, or in a peer context. Note that when using auto_connect
        keyword parameter, in Windows environment the peer might not be found without giving the exact host:port
        address for `connect_to_peer` command.

        Parameters:
            rpc_object_name: Object name, formatted as ``"<context_name>.<object_id>"``.
            auto_connect:    If True, connect automatically to the RPC object peer.
            host_port:       Optional host:port string pattern to guide the auto_connect.

        Returns:
            A proxy for the specified object.

        Raises:
            ValueError: If the given RPC object descriptor was not found.
        """
        if auto_connect:
            self.connect_to_peer(rpc_object_name.split(".")[0], peer_address=host_port, ignore_duplicate=True)

        (context_id, object_id) = rpc_object_name.split(".", 1)
        context_proxy = self.make_peer_context_proxy(context_id)
        rpc_object_descriptor = context_proxy.get_rpc_object_descriptor(object_id)
        if rpc_object_descriptor is not None:
            assert (rpc_object_descriptor.address.context_id == context_id) and \
                   (rpc_object_descriptor.address.object_id == object_id)
            return self.make_proxy(rpc_object_descriptor)

        raise ValueError(f"Unknown RPC object '{rpc_object_name}'.")

    def get_instrument(self, instrument_name: str, auto_connect: bool = False, host_port: str | None = None) -> Any:
        """Return a proxy for the specified instrument.

        The instrument may exist either in the local context, or in a peer context.

        Parameters:
            instrument_name: Instrument name, formatted as ``"<context_name>.<instrument_name>"``.
            auto_connect:    If True, connect automatically to the instrument peer.
            host_port:       Optional host:port string pattern to guide the auto_connect.

        Returns:
            A proxy for the specified instrument.
        """
        return self.get_rpc_object_by_name(instrument_name, auto_connect=auto_connect, host_port=host_port)

    def get_task(self, task_name: str, auto_connect: bool = False, host_port: str | None = None) -> Any:
        """Return a proxy for the specified task.

        The task may exist either in the local context, or in a peer context.

        Parameters:
            task_name:    Task name, formatted as ``"<context_name>.<task_name>"``.
            auto_connect: If True, connect automatically to the task peer.
            host_port:    Optional host:port string pattern to guide the auto_connect.

        Returns:
            A proxy for the specified task.
        """
        return self.get_rpc_object_by_name(task_name, auto_connect=auto_connect, host_port=host_port)

    def get_configured_contexts(self) -> dict[str, CfgContext]:
        """ Get active QMI contexts.

        Returns:
            An OrderedDict object of contexts in the config file.
        """
        return self._config.contexts

    def subscribe_signal(
        self,
        publisher_context: str,
        publisher_name: str,
        signal_name: str,
        receiver: QMI_SignalReceiver
    ) -> None:
        """Subscribe to a specified signal.

        While subscribed, the SignalReceiver object will receive and queue
        all published signals of the specified type.

        A SignalReceiver object can be simultaneously subscribed to multiple
        signals (from different publishers). Similarly, multiple receivers
        can be simultaneously subscribed to the same signal. However, it
        is an error to try to subscribe a receiver to a signal to which it
        is already subscribed.

        This method may safely be called from any thread.

        Parameters:
            publisher_context: Name of the context that publishes the signal.
                               An empty string may be used to refer to the local context.
            publisher_name:    Name of the publisher of the signal (e.g. instrument name).
            signal_name:       Name of the signal to subscribe to.
            receiver:          A SignalReceiver object which will receive the published signals.
        """
        self._signal_manager.subscribe_signal(publisher_context, publisher_name, signal_name, receiver)

    def unsubscribe_signal(
        self,
        publisher_context: str,
        publisher_name: str,
        signal_name: str,
        receiver: QMI_SignalReceiver
    ) -> None:
        """Unsubscribe from a specified signal.

        It is an error to unsubscribe a receiver from a signal to which is not currently subscribed.

        This method may safely be called from any thread.

        Parameters:
            publisher_context: Name of the context that publishes the signal, or empty string for local context.
            publisher_name:    Name of the publisher of the signal.
            signal_name:       Name of the signal to unsubscribe from.
            receiver:          The SignalReceiver object to unsubscribe from the signal.
        """
        self._signal_manager.unsubscribe_signal(publisher_context, publisher_name, signal_name, receiver)

    def publish_signal(self, publisher_name: str, signal_name: str, *args: Any) -> None:
        """Publish the specified signal to the QMI network.

        The published signal will be received by any SignalReceivers that are
        currently subscribed to the specified signal from the specified publisher.

        Parameters:
            publisher_name: Name of the publisher of the signal.
            signal_name:    Name of the signal.
            args:           Additional data to send along with the signal.
        """
        self._signal_manager.publish_signal(publisher_name, signal_name, args)
