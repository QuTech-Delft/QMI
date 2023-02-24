"""
Definitions of data structures for QMI configuration data.
"""

from collections import OrderedDict
from dataclasses import field
from typing import Dict, List, Optional, Type

from qmi.core.config_struct import configstruct


@configstruct
class CfgLogging:
    """Configuration of QMI logging policy.

    Attributes:
        loglevel: Log level.
        console_loglevel: Log level for logging to console.
        logfile: Name of QMI log file, relative to QMI home directory.
        loglevels: Optional {<logger>, <level>} mapping from logger name to specific log level for that logger.
        rate_limit: Maximum number of log messages per second when logging to file.
        burst_limit: Maximum number of log messages than can be logged to file in a short burst.
    """
    loglevel:           str             = "INFO"
    console_loglevel:   str             = "WARNING"
    logfile:            str             = "qmi.log"
    loglevels:          Dict[str, str]  = field(default_factory=OrderedDict)
    rate_limit:         Optional[float] = None
    burst_limit:        int             = 1


@configstruct
class CfgContext:
    """Configuration of a QMI context.

    Attributes:
        host: IP address where the context runs (required if the context accepts peer connections).
        tcp_server_port: TCP port for incoming peer connections (or None, to disable incoming connections).
        connect_to_peers: List of peer contexts to connect to.
        enabled: True to start this context via QMI process management.
        program_module: Python module to invoke as main script.
        program_args: Optional arguments passed when starting this context.
        python_path: Optional Python search path (overrides $PYTHONPATH).
        virtualenv_path: Optional path to virtual environment to activate.
    """
    host:               Optional[str]   = None
    tcp_server_port:    Optional[int]   = None
    connect_to_peers:   List[str]       = field(default_factory=list)
    enabled:            bool            = False
    program_module:     Optional[str]   = None
    program_args:       List[str]       = field(default_factory=list)
    python_path:        Optional[str]   = None
    virtualenv_path:    Optional[str]   = None


@configstruct
class CfgProcessHost:
    """Configuration of process management for a specific host.

    Attributes:
        logdir: Directory for output logs from managed processes.
        server_command: Command to run on the host for remote process management.
        ssh_host: Optional host name to pass to SSH to access this host (default: host address).
        ssh_user: Optional user name to pass to SSH to access this host (default: current user).
    """
    server_command:     Optional[str]   = None
    ssh_host:           Optional[str]   = None
    ssh_user:           Optional[str]   = None


@configstruct
class CfgProcessManagement:
    """Configuration of process management.

    Attributes:
        output_dir: Directory for output logs from managed processes.
        hosts: Mapping from host address to process management configuration for that host.
    """
    output_dir:         Optional[str]   = None
    hosts:              Dict[str, CfgProcessHost] = field(default_factory=OrderedDict)


@configstruct
class CfgQmi:
    """Top-level QMI configuration structure.

    Attributes:
        config_file:    Absolute path name of the configuration file.
        workgroup:      Name of the QMI workgroup.
        qmi_home:       QMI home directory (or None to derive the home directory from environment settings).
        log_dir:        Directory to write various log files (or None to use the QMI home directory).
        datastore:      Location of the DataStore repository.
        logging:        Logging configuration.
        contexts:       Mapping from context name to configuration for that context.
        process_management: Process management configuration.
    """
    config_file:        Optional[str]   = None
    workgroup:          str             = "default"
    qmi_home:           Optional[str]   = None
    log_dir:            Optional[str]   = None
    datastore:          Optional[str]   = None
    logging:            CfgLogging      = field(default_factory=CfgLogging)
    contexts:           Dict[str, CfgContext] = field(default_factory=OrderedDict)
    process_management: CfgProcessManagement = field(default_factory=CfgProcessManagement)
