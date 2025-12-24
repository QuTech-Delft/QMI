"""
# QMI Process Manager

This tool can start, stop and query background QMI processes. Processes are identified by their context name,
as specified in the QMI configuration file. Processes can run either on the local computer or on a remote,
network-connected computer.

When installing QMI with `pip`, also an executable `qmi_proc[.exe]` is created and can be used from command line.
Run on command line `qmi_proc --help` to see usage options for `qmi_proc`.
"""

import builtins
import sys
import argparse
import logging
import os
import os.path
import socket
import subprocess
from subprocess import Popen
import time

from collections.abc import Callable
from typing import NamedTuple

import colorama
import psutil

import qmi
from qmi.core.config_defs import CfgQmi
from qmi.core.exceptions import (
    QMI_Exception, QMI_ApplicationException, QMI_UnknownNameException,
    QMI_RpcTimeoutException
)
from qmi.core.util import format_address_and_port, is_valid_object_name


# Am I running in a windows virtual environment?
# sys.prefix and sys.base_prefix are not equal within a virtual environment.
# This is the documented way of validation: https://docs.python.org/3/library/venv.html#how-venvs-work.
WINENV = (sys.prefix != sys.base_prefix and os.name == 'nt')  # type: ignore

# Time in seconds to wait until a context shuts down after a request.
CONTEXT_SHUTDOWN_TIMEOUT = 8

# Default command to run on remote computer to start a process management server.
DEFAULT_SERVER_COMMAND = "python -m qmi.tools.proc server"

# Global variable holding the logger for this module.
if __name__ == "__main__":
    _logger = logging.getLogger("qmi_proc")

else:
    _logger = logging.getLogger(__name__)

# psutil version info
V, R, _ = map(int, psutil.__version__.split("."))

# Result from shutdown_context().
ShutdownResult = NamedTuple("ShutdownResult", [
    ("responding", bool),   # True if the context was initially responding.
    ("pid", int),           # Process ID (if context responded).
    ("success", bool),      # True if shutdown was successful.
])


class ProcessException(Exception):
    """Raised when a process management operation fails."""


class ProcessManagementClient:
    """Client side of a remote process management server."""

    def __init__(self, host: str, context_name: str) -> None:
        """Connect to a remote computer via SSH and start a remote process management server.

        Parameters:
            host:           Host to connect to.
            context_name:   Name of context to manage.

        Raises:
            ProcessException: If connecting to the remote computer fails.
        """
        # Context name to manage with this instance.
        self._context_name = context_name

        # Get QMI configuration.
        cfg = qmi.context().get_config()

        # Get SSH host, user, command from configuration.
        server_command = None
        ssh_host = None
        ssh_user = None
        hostcfg = cfg.process_management.hosts.get(host)
        if hostcfg is not None:
            server_command = hostcfg.server_command
            ssh_host = hostcfg.ssh_host
            ssh_user = hostcfg.ssh_user

        # Fill in defaults
        if not server_command:
            server_command = DEFAULT_SERVER_COMMAND
        if not ssh_host:
            ssh_host = host

        # Check if we need to activate a virtual environment on the remote.
        assert context_name in cfg.contexts.keys()
        ctxcfg = cfg.contexts[context_name]
        venv_path = ctxcfg.virtualenv_path
        if venv_path is not None:
            if sys.platform.startswith("win"):
                executable_path = os.path.join(venv_path, "Scripts", "")
            else:
                executable_path = os.path.join(venv_path, "bin", "")

            server_command = executable_path + server_command

        # Prepare command to invoke SSH.
        cmdline = [
            "ssh",                  # run SSH
            "-a",                   # disable agent forwarding
            "-x",                   # disable X11 forwarding
            "-T",                   # disable TTY allocation
            "-q",                   # suppress warnings
            "-o", "BatchMode yes"   # suppress password prompts
        ]
        if ssh_user:
            cmdline += ["-l", ssh_user]
        cmdline += [ssh_host, server_command]

        # Invoke SSH.
        _logger.debug("Running %s", cmdline)
        try:
            self._proc: Popen = subprocess.Popen(
                cmdline,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _logger.debug("Can not start SSH (%s: %s)", type(exc).__name__, str(exc))
            raise ProcessException(f"Can not start SSH ({type(exc).__name__}: {str(exc)})")

        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

    def close(self) -> None:
        """Close the remote server process."""

        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        # Close input stream to remote process.
        self._proc.stdin.close()

        # Wait until SSH process ends.
        try:
            self._proc.wait(timeout=2)
        except TimeoutError:
            _logger.debug("SSH client keeps running after stdin closed")
            self._proc.kill()

        self._proc.stdout.close()

    def start_process(self) -> int:
        """Request that the remote process management server start a new process."""

        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        # Send command to remote process management server.
        cmd = f"START {self._context_name}"
        self._proc.stdin.write(cmd.encode("ascii") + b"\n")
        self._proc.stdin.flush()

        # Receive response from server.
        resp = self._proc.stdout.readline()
        decoded_resp = resp.decode("ascii", errors="replace")

        # Handle response.
        if not decoded_resp:
            # Process server died.
            raise ProcessException("Remote process management failed")
        if decoded_resp.startswith("OK "):
            # Got result from process server.
            try:
                pid = int(decoded_resp[3:].strip())
            except ValueError:
                raise ProcessException("Remote process management protocol error")
            return pid
        elif decoded_resp.startswith("ERR "):
            # Got error from process server.
            msg = decoded_resp[4:].strip()
            raise ProcessException(msg)
        else:
            raise ProcessException(f"Invalid response from remote process manager ({decoded_resp!r})")

    def stop_process(self, pid: int) -> bool:
        """Request that the remote process management server stop a running process."""

        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        # Send command to remote process management server.
        cmd = f"STOP {self._context_name} {pid}"
        self._proc.stdin.write(cmd.encode("ascii") + b"\n")
        self._proc.stdin.flush()

        # Receive response from server.
        resp = self._proc.stdout.readline()
        decoded_resp = resp.decode("ascii", errors="replace")

        # Handle response.
        if not decoded_resp:
            # Process server died.
            raise ProcessException("Remote process management failed")
        if decoded_resp.startswith("OK "):
            # Got result from process server.
            try:
                success = int(decoded_resp[3:].strip())
            except ValueError:
                raise ProcessException("Remote process management protocol error")
            return success != 0
        elif decoded_resp.startswith("ERR "):
            # Got error from process server.
            msg = decoded_resp[4:].strip()
            raise ProcessException(msg)
        else:
            raise ProcessException(f"Invalid response from remote process manager ({decoded_resp!r})")


def is_local_host(host: str) -> bool:
    """Return True if the host specification refers to the local computer."""

    # Resolve host.
    try:
        addrs = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)  # type: ignore
    except OSError:
        _logger.debug("Invalid host name '%s'", host)
        return False

    # Get list of IP addresses for the specified host.
    host_ips: set[str] = set()
    for addr in addrs:
        host_ips.add(str(addr[4][0]))

    # Return True if the specified host refers to a loopback address.
    for ip_address in host_ips:
        assert isinstance(ip_address, builtins.str), "'ip_address' unexpectedly not a string!"
        if ip_address.startswith("127.") or ip_address == "::1":
            return True

    # Get list of IP addresses matching the local computer.
    if_addrs = psutil.net_if_addrs()

    # Return True if a local IP address matches the specified host.
    for addrs in if_addrs.values():
        for addr in addrs:
            if (V == 7 and R >= 2) or V > 7:
                assert isinstance(addr, psutil._ntuples.snicaddr)
            else:
                assert isinstance(addr, psutil._common.snicaddr)

            if addr.address in host_ips:
                return True

    # Specified host does not refer to the local computer.
    return False


def start_local_process(context_name: str) -> int:
    """Start the specified process on the local computer.

    Parameters:
        context_name: Context to be started.

    Returns:
        Process ID of the newly started process.

    Raises:
        ProcessException: If the process can not be started.
    """

    _logger.debug("Starting local process for context %s", context_name)

    # Get context info from QMI configuration.
    cfg = qmi.context().get_config()
    ctxcfg = cfg.contexts.get(context_name)

    # Check that the context exists in the configuration.
    if ctxcfg is None:
        raise ProcessException(f"Unknown context '{context_name}'")

    # Get program module and arguments from configuration.
    program_module = ctxcfg.program_module
    program_args = ctxcfg.program_args
    if not program_module:
        raise ProcessException(f"No program module configured for context '{context_name}'")

    # Extend PYTHONPATH if needed.
    environment = os.environ.copy()
    python_path = ctxcfg.python_path
    if python_path is not None:
        if not os.path.isdir(python_path):
            raise ProcessException(f"PYTHONPATH is not a valid path for context '{context_name}'")
        environment["PYTHONPATH"] = python_path

    # Check if a virtual environment needs to be activated.
    venv_path = ctxcfg.virtualenv_path
    if venv_path is not None:
        if sys.platform.startswith("win"):
            executable = os.path.join(venv_path, "Scripts", "python.exe")
        else:
            executable = os.path.join(venv_path, "bin", "python")

    else:
        executable = sys.executable

    # Check that a host is configured for this context.
    if not ctxcfg.host:
        raise ProcessException(f"No host configured for context '{context_name}'")

    # Find the directory where output logs will be written.
    output_dir = cfg.process_management.output_dir
    if output_dir:
        output_dir = qmi.context().resolve_file_name(output_dir)
    else:
        output_dir = qmi.context().get_qmi_home_dir()

    # Create output log file.
    datetime = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    output_file_name = os.path.join(output_dir, context_name + "_" + datetime + ".out")
    try:
        output_file = open(output_file_name, "a")
    except OSError as exc:
        raise ProcessException(f"Can not create output log file '{output_file_name}' ({str(exc)})")

    # Start a new Python process to run the specified program.
    # Close standard input.
    # Redirect standard output and stderr to the output log file.
    cmdline = [executable, "-m", program_module] + program_args
    try:
        proc = subprocess.Popen(cmdline,
                                stdin=subprocess.DEVNULL,
                                stdout=output_file,
                                stderr=subprocess.STDOUT,
                                start_new_session=True,
                                env=environment)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcessException(f"Can not start program ({type(exc).__name__}: {str(exc)})")

    finally:
        # Close output log file in parent process.
        output_file.close()

    # Wait and check if managed process is running.
    time.sleep(1)
    ret = proc.poll()
    if ret is not None:
        raise ProcessException(f"Program started but already stopped (status={ret})")

    # Workaround for a limitation in the Python subprocess module.
    # The subprocess module does not allow a Popen object to be destroyed
    # while the child process is still running. By setting the "returncode"
    # attribute, we can make the subprocess module believe that the child
    # process has completed while it is actually still running.
    # See https://bugs.python.org/issue26741 which introduces this limitation.
    proc.returncode = 0

    pid = proc.pid
    if WINENV:
        parent = psutil.Process(pid)
        # always the only child, due to the nature in which this process is spawned.
        pid = parent.children()[0].pid

    # Return PID of managed process.
    return pid


def stop_local_process(context_name: str, pid: int) -> bool:
    """Stop the specified process on the local computer.

    Parameters:
        context_name: Context to be stopped.
        pid:          Process ID.

    Returns:
        True:  If the process was stopped;
        False: If the process was not running.

    Raises:
         ProcessException: If the process can not be stopped.
    """

    _logger.debug("Stopping local process for context %s (PID=%d)", context_name, pid)

    # Search for process with specified process ID.
    try:
        proc = psutil.Process(pid=pid)
    except psutil.NoSuchProcess:
        # Process not running.
        _logger.debug("No process found with PID=%d", pid)
        return False

    # Check that process is running.
    try:
        if not proc.is_running():
            _logger.debug("Process with PID=%d is not running", pid)
            return False
    except psutil.Error as exc:
        # May happen in case of permission errors on Windows.
        raise ProcessException(f"Can not check process status ({type(exc).__name__})")

    # Kill process.
    try:
        proc.kill()
    except psutil.NoSuchProcess:
        # Program disappeared before we could kill it.
        _logger.debug("Process with PID=%d disappeared before kill", pid)
        return False
    except psutil.Error as exc:
        # May happen in case of permission error.
        raise ProcessException(f"Can not kill process ({type(exc).__name__})")

    # Wait until process ends.
    try:
        proc.wait(timeout=2)
        if proc.is_running():
            raise ProcessException(f"Process killed but still running (pid={proc.pid})")
    except psutil.Error as exc:
        raise ProcessException(f"Can not check process status ({type(exc).__name__})")

    # Process successfully stopped.
    return True


def start_process(context_name: str) -> int:
    """Start the specified process on a local or remote computer.

    Parameters:
        context_name: Context to be started.

    Returns:
        pid: Process ID of the newly started process.

    Raises:
         ProcessException: If the process can not be started.
    """

    # Get context info from QMI configuration.
    cfg = qmi.context().get_config()
    ctxcfg = cfg.contexts.get(context_name)

    # Check that the context exists in the configuration.
    if ctxcfg is None:
        raise ProcessException(f"Unknown context '{context_name}'")

    # Check that a host is configured for this context.
    if not ctxcfg.host:
        raise ProcessException(f"No host configured for context '{context_name}'")

    if is_local_host(ctxcfg.host):
        # Apply local process management.
        return start_local_process(context_name)
    else:
        # Apply remote process management.
        client = ProcessManagementClient(ctxcfg.host, context_name)
        try:
            return client.start_process()
        finally:
            client.close()


def stop_process(context_name: str, pid: int) -> bool:
    """Stop the specified process on a local or remote computer.

    Parameters:
        context_name: Context to be stopped.
        pid:          Process ID.

    Returns:
        True:  If the process was stopped;
        False: If the process was not running.

    Raises:
         ProcessException: If the process can not be stopped.
    """

    # Get context info from QMI configuration.
    cfg = qmi.context().get_config()
    ctxcfg = cfg.contexts.get(context_name)

    # Check that the context exists in the configuration.
    if ctxcfg is None:
        raise ProcessException(f"Unknown context '{context_name}'")

    # Check that a host is configured for this context.
    if not ctxcfg.host:
        raise ProcessException(f"No host configured for context '{context_name}'")

    if is_local_host(ctxcfg.host):
        # Apply local process management.
        return stop_local_process(context_name, pid)
    else:
        # Apply remote process management.
        client = ProcessManagementClient(ctxcfg.host, context_name)
        try:
            return client.stop_process(pid)
        finally:
            client.close()


def get_context_status(context_name: str) -> tuple[int, str]:
    """Check whether context is responding via TCP.

    Parameters:
         context_name: Name of the context to be tested.

    Returns:
        (pip, ver): A tuple containing the process ID of the Python program containing the context, or -1 if the
                    context is not responding via TCP. And the QMI version number of the newly created context.

    Raises:
        ProcessException: If an error occurs.
    """

    # Get context info from QMI configuration.
    cfg = qmi.context().get_config()
    ctxcfg = cfg.contexts[context_name]

    # Check that the context is configured to support TCP connections.
    if (not ctxcfg.host) or (not ctxcfg.tcp_server_port):
        # Context does not support TCP connections.
        raise ProcessException(f"Context {context_name} does not support TCP connections")

    # Try to connect to the context.
    peer_addr = format_address_and_port((ctxcfg.host, ctxcfg.tcp_server_port))
    try:
        qmi.context().suppress_version_mismatch_warnings = True
        qmi.context().connect_to_peer(context_name, peer_addr)

    except OSError as exc:
        # Can not connect to context; mark it as not responding.
        _logger.debug("Can not connect to context %r (%s: %s)",
                      context_name, type(exc).__name__, str(exc))
        return -1, ""

    except QMI_Exception as exc:
        # Unexpected error while connecting to context (bad handshake, etc.).
        _logger.debug("Protocol error from context %r (%s: %s)", context_name, type(exc).__name__, str(exc))
        raise ProcessException(f"Protocol error from context '{context_name}'")

    # Successfully connected to peer context.
    # Get a proxy for the remote ContextInfo object.
    proxy = qmi.context().make_peer_context_proxy(context_name)

    # Get peer process ID.
    try:
        pid = proxy.get_pid()
    except QMI_Exception as exc:
        # Unexpected error
        _logger.debug("Error in get_pid() call to context %r (%s: %s)",
                      context_name, type(exc).__name__, str(exc))
        raise ProcessException(f"Can not get PID of context '{context_name}'")

    # Get peer QMI version
    ver = proxy.get_version()

    # Disconnect from the peer context.
    try:
        qmi.context().disconnect_from_peer(context_name)
    except QMI_UnknownNameException:
        pass  # apparently already disconnected

    # Mark context as responding.
    return pid, ver


def shutdown_context(context_name: str, progressfn: Callable[[str], None]) -> ShutdownResult:
    """Send a shutdown request to the specified context.

    Send a soft shutdown request and wait until the context goes away.
    If that does not work, send a hard shutdown request and wait until
    the context goes away. If that does not work, give up and report failure.

    Parameters:
        context_name: Context to shut down.
        progressfn:   Callback function to report progress message.

    Returns:
        ShutdownResult: Instance with values responding, pid, success.

    Raises:
         ProcessException: If an error occurs.
    """
    def wait_disappear() -> bool:
        """Wait for a context to disappear.

        Returns:
             Boolean to tell if context disappeared (True) or not (False).
        """
        t = 0.0
        while t < CONTEXT_SHUTDOWN_TIMEOUT:
            time.sleep(0.5)
            t += 0.5
            progressfn("")
            if not qmi.context().has_peer_context(context_name):
                # Peer context disappeared.
                return True

        return False

    # Get context info from QMI configuration.
    cfg = qmi.context().get_config()
    ctxcfg = cfg.contexts[context_name]

    # Check that the context is configured to support TCP connections.
    if (not ctxcfg.host) or (not ctxcfg.tcp_server_port):
        raise ProcessException(f"Context '{context_name}' does not support TCP connections")

    # Supress warning for shutdown
    qmi.context().suppress_version_mismatch_warnings = True

    # Try to connect to the context.
    peer_addr = format_address_and_port((ctxcfg.host, ctxcfg.tcp_server_port))
    try:
        qmi.context().connect_to_peer(context_name, peer_addr)
    except OSError as exc:
        # Can not connect to context; mark it as not responding.
        _logger.debug("Can not connect to context %r (%s: %s)",
                      context_name, type(exc).__name__, str(exc))
        return ShutdownResult(responding=False, pid=-1, success=False)
    except QMI_Exception as exc:
        # Unexpected error while connecting to context (bad handshake, etc.).
        _logger.debug("Protocol error from context %r (%s: %s)", context_name, type(exc).__name__, str(exc))
        raise ProcessException(f"Protocol error from context '{context_name}'")

    try:
        # Successfully connected to peer context and received handshake.
        # Get a proxy for the remote ContextInfo object.
        proxy = qmi.context().make_peer_context_proxy(context_name)

        # Get peer process ID.
        try:
            pid = proxy.get_pid()
        except QMI_Exception as exc:
            # Unexpected error
            _logger.debug("Error in get_pid() call to context %r (%s: %s)",
                          context_name, type(exc).__name__, str(exc))
            raise ProcessException(f"Can not get PID of context '{context_name}'")

        # Send soft shutdown request.
        progressfn("soft shutdown")
        future = proxy.rpc_nonblocking.shutdown_context(hard=False)

        # Wait for answer from RPC call, but recover when no answer is received.
        try:
            future.wait(timeout=2)
        except QMI_RpcTimeoutException:
            _logger.debug("RPC timeout in soft shutdown to context %r", context_name)
            progressfn("timeout")
        except QMI_Exception as exc:
            # Unexpected error
            _logger.debug("Error in soft shutdown to context %r (%s: %s)",
                          context_name, type(exc).__name__, str(exc))
            raise ProcessException(f"Error in soft shutdown to context '{context_name}'")

        # Wait until context disappears.
        if wait_disappear():
            return ShutdownResult(responding=True, pid=pid, success=True)

        # Soft shutdown failed.
        # Send hard shutdown request.
        progressfn("hard shutdown")
        future = proxy.rpc_nonblocking.shutdown_context(hard=True)

        # We don't expect an answer from the RPC call.
        # Clean up the future.
        try:
            future.wait(timeout=0)
        except QMI_RpcTimeoutException:
            pass  # ignore timeout

        # Wait until context disappears.
        if wait_disappear():
            return ShutdownResult(responding=True, pid=pid, success=True)

        # Hard shutdown failed.
        return ShutdownResult(responding=True, pid=pid, success=False)

    finally:
        # Disconnect from peer context.
        try:
            qmi.context().disconnect_from_peer(context_name)
        except QMI_UnknownNameException:
            pass  # apparently already disconnected


def select_context_by_name(cfg: CfgQmi, context_name: str) -> list[str]:
    """Return input the context name in a list if it is valid.

    Parameters:
        cfg:          The current QMI configuration.
        context_name: The name of the context to validate.

    Raises:
        QMI_ApplicationException: If context name is not within known contexts or name is invalid.

    Returns:
        list: The input context name in a list.
    """
    # Return only the specified context.
    if context_name not in cfg.contexts:
        raise QMI_ApplicationException(f"Unknown context name '{context_name}'")

    if not is_valid_object_name(context_name):
        raise QMI_ApplicationException(f"Invalid context name '{context_name}'")

    return [context_name]


def select_contexts(cfg: CfgQmi) -> list[str]:
    """Return a list of all applicable context names.

    Parameters:
        cfg: The current QMI configuration.

    Raises:
        QMI_ApplicationException: If no contexts are enabled in the configuration, or name is invalid.

    Returns:
        context_names: All context names as a list.
    """
    context_names = []

    # Return all enabled contexts.
    for (ctxname, ctxcfg) in cfg.contexts.items():
        if ctxcfg.enabled:
            context_names.append(ctxname)
    if not context_names:
        raise QMI_ApplicationException("There are no enabled contexts in the configuration")

    # Sanity check on context names.
    # Note that our remote process management protocol does not correctly
    # handle context names containing whitespace or non-ASCII characters.
    for ctxname in context_names:
        if not is_valid_object_name(ctxname):
            raise QMI_ApplicationException(f"Invalid context name '{ctxname}'")

    return context_names


def select_local_contexts(cfg: CfgQmi) -> list[str]:
    """Return a list of all applicable local context names.

    Parameters:
        cfg: The current QMI configuration.

    Raises:
        QMI_ApplicationException: If no local contexts are enabled in the configuration, or name is invalid.

    Returns:
        Local context names as a list.
    """
    context_names = []

    # Return all enabled local contexts.
    for (ctxname, ctxcfg) in cfg.contexts.items():
        if ctxcfg.enabled and ctxcfg.host and is_local_host(ctxcfg.host):
            context_names.append(ctxname)

    if not context_names:
        raise QMI_ApplicationException("There are no enabled local contexts in the configuration")

    # Sanity check on context names.
    # Note that our remote process management protocol does not correctly
    # handle context names containing whitespace or non-ASCII characters.
    for ctxname in context_names:
        if not is_valid_object_name(ctxname):
            raise QMI_ApplicationException(f"Invalid context name '{ctxname}'")

    return context_names


def show_progress_msg(msg: str) -> None:
    """Print short progress message on screen."""
    if msg:
        print("(" + msg + ")", end=" ")
    else:
        print(".", end=" ")
    sys.stdout.flush()


def proc_server(cfg: CfgQmi) -> int:
    """Run the process manager in server mode.

    Parameters:
        cfg: The current QMI configuration.

    Raises:
        ProcessException: If process is unknown or should not run on this host.
        ValueError:       By invalid command.

    Returns:
        Exit status: (0 = success).
    """

    _logger.debug("Running qmi_proc in server mode")

    ret = 0

    # Serve remote requests via stdin/stdout until EOF on stdin.
    while True:
        # Get next request via stdin.
        sys.stdout.flush()
        req = sys.stdin.readline()

        # Stop when EOF is seen on stdin.
        if not req:
            break

        try:
            # Parse request.
            words = req.strip().split()

            if len(words) == 2 and words[0] == "START":
                # Received command to start a new process.
                context_name = words[1]

                # Get context info from QMI configuration.
                ctxcfg = cfg.contexts.get(context_name)
                if ctxcfg is None:
                    raise ProcessException("Unknown context")

                # Check that context is configured to run on the local host.
                if (not ctxcfg.host) or (not is_local_host(ctxcfg.host)):
                    raise ProcessException("Context should not run on this host")

                # Start process.
                pid = start_local_process(context_name)

                # Report result.
                print(f"OK {pid}")
                sys.stdout.flush()

            elif len(words) == 3 and words[0] == "STOP":
                # Received command to stop a running process.
                context_name = words[1]
                pid = int(words[2])

                # Sanity check on PID.
                if pid < 1:
                    raise ValueError("Invalid request")

                # Get context info from QMI configuration.
                ctxcfg = cfg.contexts[context_name]
                if ctxcfg is None:
                    raise ProcessException("Unknown context")

                # Check that context is configured to run on the local host.
                if (not ctxcfg.host) or (not is_local_host(ctxcfg.host)):
                    raise ProcessException("Context should not run on this host")

                # Stop process.
                result = stop_local_process(context_name, pid)

                # Report result.
                print(f"OK {int(result)}")
                sys.stdout.flush()

            else:
                raise ValueError("Invalid request")

        except ProcessException as exc:
            # Error occurred while processing command.
            # Report error and continue to next command.
            print(f"ERR {exc}")
            sys.stdout.flush()

        except ValueError:
            # Invalid command received from client.
            # Report error and abort server.
            _logger.debug("Invalid request %r", req)
            print("ERR Invalid request")
            sys.stdout.flush()
            ret = 1
            break

    return ret


def proc_start(cfg: CfgQmi, context_name: str | None, local: bool) -> int:
    """Start one or more processes.

    Parameters:
        cfg:          The current QMI configuration.
        context_name: Process to start, or None to start all configured processes.
        local:        Boolean flag to indicate if we only look at local processes (True) or all processes (False).

    Raises:
        ProcessException: By unexpected PID number in check.

    Returns:
        Exit status (0 = success).
    """
    colorama.init()
    started_str = "[" + colorama.Fore.GREEN + "STARTED" + colorama.Fore.RESET + "]"
    failed_str = "[" + colorama.Fore.RED + "FAILED" + colorama.Fore.RESET + "]"

    ret = 0

    # Select applicable contexts.
    if context_name:
        context_names = select_context_by_name(cfg, context_name)
    elif local:
        context_names = select_local_contexts(cfg)
    else:
        context_names = select_contexts(cfg)

    print("Starting QMI processes:")

    # Process each applicable context.
    for context_name in context_names:
        # Show process name.
        print(f"    {context_name:30s}:", end=" ")
        sys.stdout.flush()

        try:
            # Perhaps the process is already running.
            # Check if the peer context responds via TCP.
            pid, ver = get_context_status(context_name)
            if pid >= 0:
                print(f"already running (PID={pid}, QMI={ver})")

            else:
                # Context not responding via TCP.
                # Note that the program may still be running but just not responding.
                # We can not really do anything about that, so just try to start it and hope for the best.
                show_progress_msg("starting")
                pid = start_process(context_name)
                show_progress_msg(f"started PID={pid}")

                # Check that newly started process responds via TCP.
                time.sleep(0.5)
                status_pid, _ = get_context_status(context_name)
                if status_pid < 0:
                    show_progress_msg("")
                    time.sleep(1.5)
                    status_pid, _ = get_context_status(context_name)

                if status_pid == pid:
                    # New process responds via TCP; everything OK.
                    show_progress_msg("responding")
                    print(started_str)
                elif status_pid < 0:
                    # New process does not respond via TCP.
                    print("not responding via TCP", failed_str)
                    ret = 1
                else:
                    raise ProcessException(
                        f"New process (PID={pid}) for context {context_name} reports unexpected PID={status_pid}"
                    )

        except ProcessException as exc:
            print(failed_str)
            print(f"ERROR: {exc}", file=sys.stderr)
            ret = 1

    print()
    colorama.deinit()

    return ret


def proc_stop(cfg: CfgQmi, context_name: str | None, local: bool) -> int:
    """Stop one or more running processes.

    Parameters:
        cfg:          The current QMI configuration.
        context_name: Process to start, or None to stop all configured processes.
        local:        Boolean flag to indicate if we only look at local processes (True) or all processes (False).

    Raises:
        ProcessException: By unexpected error in stopping the process.

    Returns:
        Exit status (0 = success).
    """
    colorama.init()
    stopped_str = "[" + colorama.Fore.GREEN + "STOPPED" + colorama.Fore.RESET + "]"
    failed_str = "[" + colorama.Fore.RED + "FAILED" + colorama.Fore.RESET + "]"

    ret = 0

    # Select applicable contexts.
    if context_name:
        context_names = select_context_by_name(cfg, context_name)
    elif local:
        context_names = select_local_contexts(cfg)
    else:
        context_names = select_contexts(cfg)

    print("Stopping QMI processes:")

    # Process each applicable context. Stop should happen in inverse order to start, in case of dependencies.
    for context_name in reversed(context_names):
        # Show process name.
        print(f"    {context_name:30s}:", end=" ")
        sys.stdout.flush()

        try:
            # Try to shut down context via TCP.
            result = shutdown_context(context_name, show_progress_msg)
            if result.success:
                print(stopped_str)
            elif not result.responding:
                print("not responding via TCP")
            else:
                print(failed_str)
                # Failed to stop via TCP.
                # Try to stop process via local process management.
                print(f"    {'':30s} ", end=" ")
                show_progress_msg("kill")
                sys.stdout.flush()
                if stop_process(context_name, result.pid):
                    print(stopped_str)
                else:
                    print("not running")

        except ProcessException as exc:
            print(failed_str)
            print(f"ERROR: {exc}", file=sys.stderr)
            ret = 1

    print()
    colorama.deinit()

    return ret


def proc_status(cfg: CfgQmi, context_name: str | None) -> int:
    """Show the status of one or more processes.

    Parameters:
        cfg:          The current QMI configuration.
        context_name: Process to get status for, or None to get all configured processes.

    Raises:
        ProcessException: By unexpected error when checking the status.

    Returns:
        Exit status (0 = success).
    """

    colorama.init()
    running_str = "[" + colorama.Fore.GREEN + "RUNNING" + colorama.Fore.RESET + "]"
    offline_str = "[" + colorama.Fore.RED + "OFFLINE" + colorama.Fore.RESET + "]"

    ret = 0

    # Select applicable contexts.
    if context_name:
        context_names = select_context_by_name(cfg, context_name)
    else:
        context_names = select_contexts(cfg)

    max_len_context_name = len(max(context_names, key=len))

    print("QMI process status:")

    # Process each applicable context.
    for context_name in context_names:
        print("    {:{max}s}:".format(context_name, max=max_len_context_name), end=" ")
        sys.stdout.flush()

        # Check if the peer context responds via TCP.
        try:
            pid, ver = get_context_status(context_name)
            # Print process status
            if pid >= 0:
                print(running_str, f"responding via TCP (PID={pid}, QMI={ver})")
            else:
                print(offline_str, "not responding via TCP")
        except ProcessException as exc:
            print()
            print(f"ERROR: {exc}", file=sys.stderr)
            ret = 1

    print()
    colorama.deinit()

    return ret


def run() -> int:
    """Main routine of QMI process manager.

    Returns:
         0 in case of success; exit status in case of error.
    """
    parser = argparse.ArgumentParser()
    parser.description = """This tool starts or stops background QMI processes.
        Processes are identified by their context name, as specified in
        the QMI configuration file. Processes can run either on the local computer
        or on a remote, network-connected computer."""
    parser.add_argument("--config", action="store", type=str,
                        help="specify the QMI configuration file")
    mutex_group = parser.add_mutually_exclusive_group()
    mutex_group.add_argument("--all", action="store_true", help="start or stop all configured processes")
    mutex_group.add_argument("--locals", action="store_true", help="start or stop local configured processes")
    parser.add_argument("command", action="store", choices=["start", "stop", "restart", "status", "server"],
                        help="'start' to start the specified process; 'stop' to stop a running process;"
                             + " 'restart' to restart the running process; 'status' to show the process status")
    parser.add_argument("context_name", action="store", type=str, nargs="?",
                        help="context name of the process to start or stop")
    args = parser.parse_args()

    if args.command == "server" and (args.all or args.context_name or args.locals):
        print("ERROR: Can not specify server mode together with other options")
        return 1

    if args.all and args.context_name:
        print("ERROR: Can not specify a context_name together with --all", file=sys.stderr)
        return 1

    if args.locals and args.context_name:
        print("ERROR: Can not specify a context_name together with --locals", file=sys.stderr)
        return 1

    if (args.command in ("start", "stop", "restart")) and (not args.all) and (not args.locals) and \
            (not args.context_name):
        print("ERROR: Specify either: a context_name, or --all, or --local", file=sys.stderr)
        return 1

    qmi.start("proc_mgr", config_file=args.config, console_loglevel="WARNING")
    # Get the QMI configuration.
    cfg = qmi.context().get_config()
    try:

        if args.command == "server":
            return proc_server(cfg=cfg)

        if args.command == "start":
            return proc_start(cfg=cfg, context_name=args.context_name, local=args.locals)

        elif args.command == "stop":
            return proc_stop(cfg=cfg, context_name=args.context_name, local=args.locals)

        elif args.command == "restart":
            proc_stop(cfg=cfg, context_name=args.context_name, local=args.locals)
            return proc_start(cfg=cfg, context_name=args.context_name, local=args.locals)

        elif args.command == "status":
            return proc_status(cfg=cfg, context_name=args.context_name)

        else:
            print(f"ERROR: Unknown command {args.command!r}", file=sys.stderr)
            return 1

    except QMI_ApplicationException as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

    finally:
        qmi.stop()


if __name__ == "__main__":
    sys.exit(run())
