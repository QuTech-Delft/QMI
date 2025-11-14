"""Convenience functions to handle the singleton-instance of QMI_Context.

Most QMI applications will create a single instance of `QMI_Context` and
use that context for all interactions with QMI. This module provides
functions to make this way of working more convenient.

The public functions defined in this module, are also imported into
the top-level `qmi` package. Applications can therefore call these
functions directly, for example::

    import qmi
    qmi.start("my_context")
    proxy = qmi.make_instrument("my_instrument", InstrumentClass, class_args)
    qmi.stop()
"""

import sys
import logging
import os
import os.path
import time

from typing import Any

import qmi.core.config
import qmi.core.logging_init
import qmi.core.thread

from qmi.core.config_struct import config_struct_from_dict
from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_UsageException, QMI_NoActiveContextException, QMI_ConfigurationException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import QMI_RpcObject
from qmi.core.task import QMI_Task, QMI_TaskRunner
from qmi.core.util import format_address_and_port


# Global variable holding the current QMI_Context instance.
_qmi_context = None

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# global constant holding environment variables
QMI_CONFIG = os.getenv("QMI_CONFIG")


def context() -> QMI_Context:
    """Return the current QMI_Context instance.

    This function may only be called when there is an active QMI context
    (i.e. after calling `qmi.start()`).

    Raises:
        QMI_NoActiveContextException: If there is no active context.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException("No active context")
    return _qmi_context


def start(
        context_name: str,
        config_file: str | None = None,
        init_logging: bool = True,
        console_loglevel: str | None = None,
        context_cfg: dict | None = None
) -> None:
    """Create and start a global QMI_Context instance.

    This function should be called exactly once by the top-level code of
    the application.

    This function performs a number of initialization steps:

    * read the QMI configuration file;
    * initialize logging;
    * create and start a global QMI context.

    The context name is a short string, without spaces or strange characters.
    This name will be used to refer to this context from other processes,
    as well as for displaying and logging.

    The context name should be unique within the workgroup (i.e. among all
    Python processes that work together via QMI.) If this context acts as
    a server for other contexts to connect to, its name *must* be unique.
    Otherwise, if this context only acts as a client, a duplicate context name
    is allowed but not recommended.

    If `config_file` is provided, it should be a path to a valid QMI
    configuration file. The referenced file will be used to load the
    configuration from.
    If `config_file` is ``None`` and the environment variable `QMI_CONFIG` is
    set, the configuration will be loaded from the file that the environment
    variable points to. If `QMI_CONFIG` is not set, an empty configuration is
    used.

    The configuration created can be edited by providing a dictionary as an
    optional input. See config_defs.CfgContext class for possible dict keys
    and respective values and types that are allowed. Wrong (type) of keys
    and/or values will raise an exception.

    Parameters:
        context_name:     Name of the QMI context.
        config_file:      Optional path to the QMI configuration file.
        init_logging:     Optional flag; set False to skip logging initialization.
        console_loglevel: Optionally override `console_loglevel` from config file.
        context_cfg:      Optionally insert or override context(s) in config.contexts.
    """

    global _qmi_context

    qmi.core.thread.check_in_main_thread()

    if _qmi_context is not None:
        raise QMI_UsageException("QMI context already started")

    config = create_config_from_file(config_file)  # this will raise FileNotFoundError if config_file == ""

    # Check for insert or override of context or contexts.
    if context_cfg is not None:
        for key in context_cfg.keys():
            config.contexts.update({key: config_struct_from_dict(context_cfg[key], CfgContext)})

    # Check for loglevel instructions
    if console_loglevel is not None:
        valid_levels = ["INFO", "WARNING", "DEBUG", "CRITICAL", "FATAL", "ERROR", "WARN", "NOTSET"]
        if console_loglevel not in valid_levels:
            raise QMI_ConfigurationException(
                f"Trying to use non-valid console loglevel {console_loglevel}. " +
                f"Valid values are {valid_levels}."
            )

        config.logging.console_loglevel = console_loglevel.upper()

    # Create QMI context.
    _qmi_context = QMI_Context(context_name, config)

    if init_logging:
        _init_logging()

    _logger.info(
        "QMI starting (prog=%r, context=%r, pid=%d, config=%r)",
        sys.argv[0], context_name, os.getpid(), config_file
    )

    # Start QMI context.
    _qmi_context.start()

    # Connect to peer contexts.
    _connect_to_peers()


def create_config_from_file(config_file: str | None) -> CfgQmi:
    """Create configuration from a file.

    Parameters:
        config_file: Path of configuration file or None.

    Returns:
        Top-level QMI configuration structure.
    """
    # Try first to see if input is given or QMI_CONFIG is set
    config_file = config_file if config_file is not None else QMI_CONFIG
    if config_file is None:
        # Failing that, use the default class
        return CfgQmi()

    else:
        _logger.debug("Reading QMI configuration file %s", config_file)
        cfgdict = qmi.core.config.load_config_file(config_file)
        cfgdict["config_file"] = os.path.abspath(config_file)

    return config_struct_from_dict(cfgdict, CfgQmi)


def _init_logging() -> None:
    """Initialize Python logging framework."""

    # Get logging configuration.
    assert _qmi_context is not None
    cfg = _qmi_context.get_config()
    loglevel = cfg.logging.loglevel
    console_loglevel = cfg.logging.console_loglevel
    logfile = cfg.logging.logfile

    # If QMI_DEBUG is set, override configured log level.
    if os.getenv("QMI_DEBUG"):
        loglevel = "DEBUG"
        console_loglevel = "DEBUG"

    if logfile:
        # Expand placeholders in logfile name.
        # For example "log_%(context)s_%(datetime)s.txt"
        gmtime = time.gmtime()
        attrs = {
            "context": _qmi_context.name,
            "date": time.strftime('%Y-%m-%d', gmtime),
            "datetime": time.strftime('%Y-%m-%dT%H-%M-%S', gmtime),
            }
        logfile = logfile % attrs

        # Make absolute file name.
        qmi_log_dir = _qmi_context.get_log_dir()
        qmi_log_dir = qmi_log_dir.replace("~", os.path.expanduser("~")) if qmi_log_dir.startswith("~") else qmi_log_dir
        if not os.path.isdir(qmi_log_dir):
            os.makedirs(qmi_log_dir, exist_ok=True)

        logfile = os.path.join(qmi_log_dir, logfile)

    # Initialize logging.
    qmi.core.logging_init.start_logging(
        loglevel=loglevel,
        console_loglevel=console_loglevel,
        logfile=logfile,
        loglevels=cfg.logging.loglevels,
        rate_limit=cfg.logging.rate_limit,
        burst_limit=cfg.logging.burst_limit,
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count
    )


def _connect_to_peers() -> None:
    """Helper function to connect to the pre-configured list of peers."""

    assert _qmi_context is not None

    # Get list of peer contexts.
    cfg = _qmi_context.get_config()
    ctxcfg = _qmi_context.get_context_config()

    # For each peer.
    for peername in ctxcfg.connect_to_peers:

        # Get host and port number of peer context.
        peercfg = cfg.contexts.get(peername)
        if not peercfg:
            raise QMI_ConfigurationException(f"Can not connect to unknown peer {peername!r}")
        peer_host = peercfg.host
        peer_port = peercfg.tcp_server_port
        if (not peer_host) or (not peer_port):
            raise QMI_ConfigurationException(f"Missing host/port for peer context {peername!r}")

        # Connect to peer.
        peer_address = format_address_and_port((peer_host, peer_port))
        _logger.info("Connecting to peer context %r on %s", peername, peer_address)
        _qmi_context.connect_to_peer(peername, peer_address)


def stop() -> None:
    """Stop and destroy the `QMI_Context` instance.

    This function should be called exactly once when the application exits.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """

    global _qmi_context

    qmi.core.thread.check_in_main_thread()

    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    _qmi_context.stop()
    _qmi_context = None


def info() -> str:
    """Return human-readable information about the context."""

    if _qmi_context is None:
        return "*** No active QMI context ***"
    else:
        return _qmi_context.info()


def make_rpc_object(
    rpc_object_name: str,
    rpc_object_class: type[QMI_RpcObject],
    *args: Any,
    **kwargs: Any
) -> Any:
    """Create an instance of a `QMI_RpcObject` subclass and make it accessible via RPC.

    The actual object instance will be created in a separate background thread.
    To access the object, you can call its methods via RPC. Note that using the returned proxy in
    a thread might require casting it first: proxy = cast(proxy, rpc_object_class)(qmi.context(), rpc_object_name).

    Parameters:
        rpc_object_name:  Unique name for the new object instance.
                          This name will also be used to access the object via RPC.
        rpc_object_class: Class that implements this object (must be a subclass of `QMI_RpcObject`).
        args:             Optional arguments for the object class constructor.
        kwargs:           Optional keyword arguments for the object class constructor.

    Returns:
        An RPC proxy that provides access to the new object instance.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.make_rpc_object(rpc_object_name, rpc_object_class, *args, **kwargs)


def make_instrument(
    instrument_name: str,
    instrument_class: type[QMI_Instrument],
    *args: Any,
    **kwargs: Any
) -> Any:
    """Create an instance of a `QMI_Instrument` subclass and make it accessible via RPC.

    The actual instrument instance will be created in a separate background thread.
    To access the instrument, you can call its methods via RPC.

    Parameters:
        instrument_name:  A unique name for the new instrument instance.
                          This name will also be used to access the instrument via RPC.
        instrument_class: Class that implements this instrument (must be a subclass of `QMI_Instrument`).
        args:             Optional arguments for the instrument class constructor.
        kwargs:           Optional keyword arguments for the instrument class constructor.

    Returns:
        An RPC proxy that provides access to the new instrument instance.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.make_instrument(instrument_name, instrument_class, *args, **kwargs)


def make_task(
    task_name: str,
    task_class: type[QMI_Task],
    *args: Any,
    task_runner: type[QMI_TaskRunner] = QMI_TaskRunner,
    **kwargs: Any
) -> Any:
    """Create an instance of a `QMI_Task` subclass and make it accessible via RPC.

    The actual task instance will be created in a separate thread.
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

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.make_task(task_name, task_class, *args, task_runner=task_runner, **kwargs)


def list_rpc_objects(rpc_object_baseclass=None) -> list:
    """Show a list of RPC objects in the local context and peer contexts."""

    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.list_rpc_objects(rpc_object_baseclass)


def show_rpc_objects(rpc_object_baseclass=None) -> None:
    """Show a list of RPC objects in the local context and peer contexts."""

    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.show_rpc_objects(rpc_object_baseclass)


def show_instruments() -> None:
    """Show a list of instruments in the local context and peer contexts."""
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.show_instruments()


def show_tasks() -> None:
    """Show a list of tasks in the local context and peer contexts."""
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.show_tasks()


def show_contexts() -> None:
    """Show a list of currently connected contexts (including the local context)."""
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.show_contexts()


def show_network_contexts() -> None:
    """Show a lists of context on the network (connected and not connected)."""
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.show_network_contexts()


def get_rpc_object(rpc_object_name: str, auto_connect: bool = False, host_port: str | None = None) -> Any:
    """Return a proxy for the specified object.

    The object may exist either in the local context, or in a peer context.

    Parameters:
        rpc_object_name: Object name, formatted as ``"<context_name>.<object_name>"``.
        auto_connect:    If True, connect automatically to the object peer.
        host_port:       Optional host:port string pattern to guide the auto_connect.

    Returns:
        A proxy for the specified object.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.get_rpc_object_by_name(rpc_object_name, auto_connect=auto_connect, host_port=host_port)


def get_instrument(instrument_name: str, auto_connect: bool = False, host_port: str | None = None) -> Any:
    """Return a proxy for the specified instrument.

    The instrument may exist either in the local context, or in a peer context.

    Parameters:
        instrument_name: Instrument name, formatted as ``"<context_name>.<instrument_name>"``.
        auto_connect:    If True, connect automatically to the instrument peer.
        host_port:       Optional host:port string pattern to guide the auto_connect.

    Returns:
        A proxy for the specified instrument.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.get_instrument(instrument_name, auto_connect, host_port)


def get_task(task_name: str, auto_connect: bool = False, host_port: str | None = None) -> Any:
    """Return a proxy for the specified task.

    The task may exist either in the local context, or in a peer context.

    Parameters:
        task_name: Task name, formatted as ``"<context_name>.<task_name>"``.
        auto_connect: if True, connect automatically to the task peer.
        host_port: Optional host:port string pattern to guide the auto_connect.

    Returns:
        A proxy for the specified task.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.get_task(task_name, auto_connect, host_port)


def get_configured_contexts() -> dict[str, CfgContext]:
    """Return a dictionary of active QMI contexts.

    Returns:
        An OrderedDict object of all active QMI contexts.

    Raises:
        QMI_NoActiveContextException: If there is no active QMI context present.
    """
    if _qmi_context is None:
        raise QMI_NoActiveContextException()

    return _qmi_context.get_configured_contexts()
