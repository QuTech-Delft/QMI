#! /usr/bin/env python3

"""Test qmi/tools/proc.py"""
import unittest
from unittest.mock import MagicMock, patch, call
import socket
import os, sys
import psutil
import subprocess
from argparse import Namespace, ArgumentError

import qmi
import qmi.tools.proc as proc

from qmi.core.config_defs import CfgQmi
from qmi.core.config_defs import CfgContext
from qmi.core.config_defs import CfgProcessManagement
from qmi.core.config_defs import CfgProcessHost

from qmi.core.context import QMI_Context

from qmi.core.exceptions import QMI_ApplicationException


class ProcessManagementClientTestCase(unittest.TestCase):
    def _start_qmi_context(self):
        """Start qmi and initialize the context with a configuration. Returns the configuration."""
        config = {
            "ip": "10.10.10.10",  # Local IP address
            "port": 512,
            "server_command": "test_config_server_command",
            "ssh_host": "test_config_ssh_host",
            "ssh_user": "test_config_ssh_user",
            "program_module": "test_program_module",
            "program_args": ["test_program_args"],
        }
        config0 = {
            "ip": "172.16.4.2",
            "port": 5005,
            "program_module": "test_local_module",
            "program_args": ["test_program_args"],
        }
        qmi.start("ContextName2", context_cfg={
                "ContextName2": {"tcp_server_port": 511},
                "ContextName1": {
                    "host": config["ip"],
                    "tcp_server_port": config["port"],
                    "program_module": config["program_module"],
                    "program_args": config["program_args"],
                    "enabled": True,
                },
                "ContextName0": {
                    "host": config0["ip"],
                    "tcp_server_port": config0["port"],
                    "program_module": config0["program_module"],
                    "program_args": config0["program_args"],
                    "connect_to_peers": ["ContextName1"],
                    "enabled": True,
                }
            },
        )
        return {"config": config, "config0": config0}

    def setUp(self):
        proc.subprocess = MagicMock(spec=subprocess)
        proc.subprocess.SubprocessError = subprocess.SubprocessError
        proc.open = MagicMock()
        self._config = self._start_qmi_context()
        proc.print = MagicMock()
        proc._logger = MagicMock()

    def tearDown(self):
        qmi.stop()

    def test_pmc_init(self):
        """Test ProcessManagementClient.__init__, happy flow, configuration parameters."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            context, _, _ = self._build_mock_config()
            context._config = CfgQmi(
                contexts={
                    "ContextName1": CfgContext(
                        host=self._config["config"]["ip"], tcp_server_port=0
                    ),
                },
                process_management=CfgProcessManagement(
                    hosts={
                        self._config["config"]["ip"]: CfgProcessHost(
                            server_command=self._config["config"]["server_command"],
                            ssh_host=self._config["config"]["ssh_host"],
                            ssh_user=self._config["config"]["ssh_user"],
                        )
                    }
                ),
            )
            context.get_config = MagicMock(return_value=context._config)
            proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
            proc.subprocess.Popen.assert_called_once_with(
                [
                    "ssh",
                    "-a",
                    "-x",
                    "-T",
                    "-q",
                    "-o",
                    "BatchMode yes",
                    "-l",
                    "test_config_ssh_user",
                    self._config["config"]["ssh_host"],
                    self._config["config"]["server_command"],
                ],
                stdin=proc.subprocess.PIPE,
                stdout=proc.subprocess.PIPE,
            )

    def test_pmc_init_default(self):
        """Test ProcessManagementClient.__init__, happy flow, default parameters."""
        proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
        proc.subprocess.Popen.assert_called_once_with(
            [
                "ssh",
                "-a",
                "-x",
                "-T",
                "-q",
                "-o",
                "BatchMode yes",
                self._config["config"]["ip"],
                proc.DEFAULT_SERVER_COMMAND,
            ],
            stdin=proc.subprocess.PIPE,
            stdout=proc.subprocess.PIPE,
        )

    def test_pmc_init_os_error(self):
        """Test ProcessManagementClient.__init__, os error on Popen."""
        with patch("qmi.tools.proc.subprocess.Popen", MagicMock(side_effect=OSError)):
            with self.assertRaises(proc.ProcessException):
                proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

    def test_pmc_close(self):
        """Test ProcessManagementClient.close, happy flow."""
        manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
        manager.close()
        manager._proc.stdin.close.assert_called_once_with()
        manager._proc.stdout.close.assert_called_once_with()
        manager._proc.wait.assert_called_once_with(timeout=2)

    def test_pmc_close_timeout(self):
        """Test whether ProcessManagementClient.close kills the process when a timeout happened."""
        manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch.object(
            manager._proc, "wait", side_effect=TimeoutError
        ):
            manager.close()

        manager._proc.kill.assert_called_once_with()

    def test_pmc_start_process(self):
        """Test ProcessManagementClient.start_process, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
            with patch.object(
                manager._proc.stdout, "readline", return_value="OK 123".encode("ascii")
            ):
                rt_val = manager.start_process()
                manager._proc.stdin.write.assert_called_once_with(
                    b"START ContextName1\n"
                )
                manager._proc.stdin.flush.assert_called_once_with()
                self.assertEqual(123, rt_val)

    def test_pmc_start_process_value_error(self):
        """Test whether ProcessManagementClient.start_process value error pid."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
            with patch.object(
                manager._proc.stdout,
                "readline",
                return_value="OK INVALID".encode("ascii"),
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.start_process()

    def test_pmc_start_process_err(self):
        """Test whether ProcessManagementClient.start_process raises an exception when a error response is received."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
            with patch.object(
                manager._proc.stdout, "readline", return_value="ERR 123".encode("ascii")
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.start_process()

    def test_pmc_start_process_dead_server(self):
        """Test whether ProcessManagementClient.start_process raises an exception when no response is received."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

            with patch.object(
                manager._proc.stdout, "readline", return_value="".encode("ascii")
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.start_process()

    def test_pmc_start_process_invalid_response(self):
        """Test whether ProcessManagementClient.start_process raises an exception when a invalid response is received."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

            with patch.object(
                manager._proc.stdout,
                "readline",
                return_value="invalidresponse".encode("ascii"),
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.start_process()

    def test_pmc_stop_process(self):
        """Test ProcessManagementClient.stop_process, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

            with patch.object(
                manager._proc.stdout, "readline", return_value="OK 1".encode("ascii")
            ):
                rt_val = manager.stop_process(123)
                manager._proc.stdin.write.assert_called_once_with(
                    b"STOP ContextName1 123\n"
                )
                manager._proc.stdin.flush.assert_called_once_with()
                self.assertTrue(rt_val)

    def test_pmc_stop_process_value_error(self):
        """Test whether ProcessManagementClient.stop_process value error pid."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")
            with patch.object(
                manager._proc.stdout,
                "readline",
                return_value="OK INVALID".encode("ascii"),
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.stop_process(123)

    def test_pmc_stop_process_dead_server(self):
        """Test whether ProcessManagementClient.stop_process raises an exception when no response is returned."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

            with patch.object(
                manager._proc.stdout, "readline", return_value="".encode("ascii")
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.stop_process(123)

    def test_pmc_stop_process_err(self):
        """Test whether ProcessManagementClient.stop_process raises an exception when an error is returned."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

            with patch.object(
                manager._proc.stdout, "readline", return_value="ERR 1".encode("ascii")
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.stop_process(123)

    def test_pmc_stop_process_invalid_response(self):
        """Test whether ProcessManagementClient.stop_process raises an exception when a invalid response is returned by a context."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            manager = proc.ProcessManagementClient(self._config["config"]["ip"], "ContextName1")

            with patch.object(
                manager._proc.stdout,
                "readline",
                return_value="invalidresponse".encode("ascii"),
            ):
                with self.assertRaises(proc.ProcessException):
                    manager.stop_process(123)

    def _build_mock_config(self):
        qmi.context = MagicMock(return_value=(context := MagicMock(spec=QMI_Context)))
        context.get_config = MagicMock(return_value=(config := MagicMock()))
        config.contexts = {
            "ContextName1": (ctxcfg := MagicMock()),
        }
        return context, config, ctxcfg

    def test_is_local_host(self):
        """Test is_local_host, happy flow."""
        self.assertFalse(proc.is_local_host("0.0.0.0"))
        self.assertTrue(proc.is_local_host("127.0.0.0"))
        self.assertTrue(proc.is_local_host("::1"))
        self.assertFalse(proc.is_local_host("INVALID"))

        # c0 = QMI_Context("ContextName0", CfgQmi(
        #     contexts={
        #         "ContextName0": CfgContext(host=self._config["config0"]["ip"], tcp_server_port=self._config["config0"]["port"], enabled=True)
        #     }
        # ))
        # c0.start()
        # c0.connect_to_peer("ContextName2", c0.discover_peer_contexts()[0][1])
        # Collect a local ip address that is not a loopback address.
        test_addr = None
        for addr in psutil.net_if_addrs().values():
            for a in addr:
                if a.family == socket.AF_INET and a.broadcast != None:
                    test_addr = a
                    break
            if test_addr:
                break

        if test_addr:
            self.assertTrue(proc.is_local_host(test_addr.address))

    def test_start_local_process(self):
        """Test start_local_process, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.open", MagicMock(return_value=(fopen := MagicMock()))
        ), patch(
            "qmi.tools.proc.subprocess.Popen",
            MagicMock(return_value=(popen := MagicMock())),
        ), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)
        ), patch(
            "sys.executable", (exec := MagicMock())
        ), patch(
            "os.environ.copy", MagicMock()
        ):
            _, _, ctxcfg = self._build_mock_config()
            popen.poll = MagicMock(return_value=None)
            rt_val = proc.start_local_process("ContextName1")
            self.assertEqual(rt_val, popen.pid)
            proc.subprocess.Popen.assert_called_once_with(
                [exec, "-m", ctxcfg.program_module] + ctxcfg.program_args,
                stdin=proc.subprocess.DEVNULL,
                stdout=fopen,
                stderr=proc.subprocess.STDOUT,
                start_new_session=True,
                env=os.environ.copy(),
            )

    def test_start_local_process_winenv(self):
        """Test start_local_process, happy flow, windows environment."""
        mock_pid_parent = MagicMock()
        mock_pid_parent.children = MagicMock(return_value=[(mock_pid:=MagicMock())])
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.open", MagicMock(return_value=(fopen := MagicMock()))
        ), patch(
            "qmi.tools.proc.subprocess.Popen",
            MagicMock(return_value=(popen := MagicMock())),
        ), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)
        ), patch(
            "sys.executable", (exec := MagicMock())
        ), patch(
            "os.environ.copy", MagicMock()
        ), patch("qmi.tools.proc.WINENV", True), patch('qmi.tools.proc.psutil.Process', MagicMock(return_value=mock_pid_parent)):
            _, _, ctxcfg = self._build_mock_config()
            popen.poll = MagicMock(return_value=None)
            rt_val = proc.start_local_process("ContextName1")
            self.assertEqual(rt_val, mock_pid.pid)

    def test_start_local_process_stopped(self):
        """Test whether start_local_process raises an exception when the process is not successfully started."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.subprocess.Popen",
            MagicMock(return_value=(popen := MagicMock())),
        ), patch("qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)):
            popen.poll = MagicMock(
                return_value=True
            )  # returns something when the process is not running.
            with self.assertRaises(proc.ProcessException):
                proc.start_local_process("ContextName1")

    def test_start_local_process_not_exist(self):
        """Test start_local_process whether an exception is raised when the context doesn't exist in the configuration."""
        with self.assertRaises(proc.ProcessException):
            proc.start_local_process("SomeContextNameThatDoesntExistInConfiguration")

    def test_start_local_process_no_program_module(self):
        """Test start_local_process whether an exception is raised when no program module is configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            ctxcfg.program_module = None
            with self.assertRaises(proc.ProcessException):
                proc.start_local_process("ContextName1")

    def test_start_local_process_python_path(self):
        """Test whether start_local_process PYTHONPATH configuration sets the PYTHONPATH in the environment."""
        env_copy = {"PYTHONPATH": "SOMEPATH"}
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.subprocess.Popen",
            MagicMock(return_value=(popen := MagicMock())),
        ), patch("qmi.tools.proc.os", MagicMock()), patch(
            "qmi.tools.proc.os.environ.copy", MagicMock(return_value=env_copy)
        ), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)
        ):
            _, _, ctxcfg = self._build_mock_config()
            popen.poll = MagicMock(return_value=None)
            ctxcfg.python_path = "SOMEOTHERPATH"
            proc.start_local_process("ContextName1")
            self.assertEqual(env_copy["PYTHONPATH"], "SOMEOTHERPATH")

    def test_start_local_process_invalid_python_path(self):
        """Test whether start_local_process raises an exception when a invalid PYTHONPATH is not configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=False)
        ):
            _, _, _ = self._build_mock_config()
            with self.assertRaises(proc.ProcessException):
                proc.start_local_process("ContextName1")

    def test_start_local_process_no_host(self):
        """Test whether start_local_process raises an exception when the host is not configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)
        ):
            _, _, ctxcfg = self._build_mock_config()
            ctxcfg.host = None
            with self.assertRaises(proc.ProcessException):
                proc.start_local_process("ContextName1")

    def test_start_local_process_output_file_with_cfg_output_dir(self):
        """Test whether start_local_process takes the configured output directory."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.subprocess.Popen",
            MagicMock(return_value=(popen := MagicMock())),
        ), patch(
            "qmi.tools.proc.time.strftime", MagicMock(return_value="strftime")
        ), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)
        ):
            context, _, ctxcfg = self._build_mock_config()
            ctxcfg.process_management.output_dir = "SomeOutputDir"
            popen.poll = MagicMock(return_value=None)
            context.resolve_file_name = MagicMock(return_value="ResolvedOutputDir")
            proc.start_local_process("ContextName1")
            proc.open.assert_called_once_with(
                os.path.join("ResolvedOutputDir", "ContextName1_strftime.out"), "a"
            )

    def test_start_local_process_output_file_open_oserror(self):
        """Test whether start_local_process raises an exception when the unable to open output folder."""
        with patch("qmi.tools.proc.open", MagicMock(side_effect=OSError)), patch(
            "qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)
        ):
            with self.assertRaises(proc.ProcessException):
                proc.start_local_process("ContextName1")

    def test_start_local_process_popen_oserror(self):
        """Test whether start_local_process raises an exception when the process raises an exception.."""
        with patch(
            "qmi.tools.proc.subprocess.Popen", MagicMock(side_effect=OSError)
        ), patch("qmi.tools.proc.os.path.isdir", MagicMock(return_value=True)):
            with self.assertRaises(proc.ProcessException):
                proc.start_local_process("ContextName1")

    def test_stop_local_process(self):
        """Test stop_local_process, happy flow."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(side_effect=[True, False])
            rt_val = proc.stop_local_process("ContextName1", 123)
            self.assertTrue(rt_val)
            proc.psutil.Process.assert_called_once_with(pid=123)

    def test_stop_local_process_no_process(self):
        """Test stop_local_process flow when no process is found."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(side_effect=psutil.NoSuchProcess(123)),
        ):
            rt_val = proc.stop_local_process("ContextName1", 123)
            self.assertFalse(rt_val)

    def test_stop_local_process_not_running(self):
        """Test stop_local_process flow when process is not running."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(return_value=False)
            rt_val = proc.stop_local_process("ContextName1", 123)
            self.assertFalse(rt_val)

    def test_stop_local_process_windows_permission_failure(self):
        """Test stop_local_process flow when unable to retrieve process status."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(side_effect=psutil.Error)
            with self.assertRaises(proc.ProcessException):
                proc.stop_local_process("ContextName1", 123)

    def test_stop_local_process_kill_no_process(self):
        """Test stop_local_process flow when kill occurs on a non running process."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(return_value=True)
            process.kill = MagicMock(side_effect=psutil.NoSuchProcess(123))
            rt_val = proc.stop_local_process("ContextName1", 123)
            self.assertFalse(rt_val)

    def test_stop_local_process_permision_error(self):
        """Test stop_local_process flow when kill results in an exception."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(return_value=True)
            process.kill = MagicMock(side_effect=psutil.Error)
            with self.assertRaises(proc.ProcessException):
                proc.stop_local_process("ContextName1", 123)

    def test_stop_local_process_not_killed(self):
        """Test stop_local_process flow unable to stop the process.."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(return_value=True)
            with self.assertRaises(proc.ProcessException):
                proc.stop_local_process("ContextName1", 123)

    def test_stop_local_process_wait_psutil_error(self):
        """Test stop_local_process flow when waiting results in an exception."""
        with patch(
            "qmi.tools.proc.psutil.Process",
            MagicMock(return_value=(process := MagicMock())),
        ):
            process.is_running = MagicMock(return_value=True)
            process.wait = MagicMock(side_effect=psutil.Error)
            with self.assertRaises(proc.ProcessException):
                proc.stop_local_process("ContextName1", 123)

    def _make_context_mock_peer(self):
        """Adapt the qmi context to use mocking for peer connections."""
        qmi.context().connect_to_peer = MagicMock()
        proxy = MagicMock()
        proxy.get_version = MagicMock(return_value="SomeVersion")
        proxy.get_pid = MagicMock(return_value=123)
        qmi.context().make_peer_context_proxy = MagicMock(return_value=proxy)
        return proxy

    def test_start_process_localhost(self):
        """Test start_process localhost, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.is_local_host", MagicMock(return_value=True)
        ), patch("qmi.tools.proc.start_local_process", MagicMock()):
            _, _, _ = self._build_mock_config()
            rt_val = proc.start_process("ContextName1")
            self.assertEqual(rt_val, proc.start_local_process("ContextName1"))

    def test_start_process_remote(self):
        """Test start_process remotehost, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.is_local_host", MagicMock(return_value=False)
        ), patch("qmi.tools.proc.ProcessManagementClient", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            rt_val = proc.start_process("ContextName1")
            self.assertEqual(
                rt_val,
                proc.ProcessManagementClient(
                    ctxcfg.host, "ContextName1"
                ).start_process(),
            )

    def test_start_no_ctxcfg(self):
        """Test start_process invalid configuration flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, config, _ = self._build_mock_config()
            config.contexts = {}
            with self.assertRaises(proc.ProcessException):
                proc.start_process("ContextName1")

    def test_start_no_host(self):
        """Test start_process invalid configuration flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            ctxcfg.host = None
            with self.assertRaises(proc.ProcessException):
                proc.start_process("ContextName1")

    def test_stop_process_localhost(self):
        """Test start_process localhost, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.is_local_host", MagicMock(return_value=True)
        ), patch("qmi.tools.proc.stop_local_process", MagicMock()):
            _, _, _ = self._build_mock_config()
            rt_val = proc.stop_process("ContextName1", 123)
            self.assertEqual(rt_val, proc.stop_local_process("ContextName1", 123))

    def test_stop_process_remote(self):
        """Test start_process remotehost, happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.is_local_host", MagicMock(return_value=False)
        ), patch("qmi.tools.proc.ProcessManagementClient", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            rt_val = proc.stop_process("ContextName1", 123)
            self.assertEqual(
                rt_val,
                proc.ProcessManagementClient(ctxcfg.host, "ContextName1").stop_process(
                    123
                ),
            )

    def test_stop_process_no_ctxcfg(self):
        """Test start_process invalid configuration flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, config, _ = self._build_mock_config()
            config.contexts = {}
            with self.assertRaises(proc.ProcessException):
                proc.stop_process("ContextName1", 123)

    def test_stop_process_no_host(self):
        """Test start_process invalid configuration flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            ctxcfg.host = None
            with self.assertRaises(proc.ProcessException):
                proc.stop_process("ContextName1", 123)

    def test_get_context_status(self):
        """Test get_context_status happy flow."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            self._make_context_mock_peer()
            rt_val = proc.get_context_status("ContextName1")
            self.assertEqual(rt_val, (123, "SomeVersion"))

    def test_get_context_status_no_tcp(self):
        """Test get_context_status flow when no host is configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            self._make_context_mock_peer()
            ctxcfg.host = None
            with self.assertRaises(proc.ProcessException):
                proc.get_context_status("ContextName1")

    def test_get_context_status_os_error(self):
        """Test get_context_status flow when connecting results in an operation error."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            context, _, _ = self._build_mock_config()
            self._make_context_mock_peer()
            context.connect_to_peer = MagicMock(side_effect=OSError)
            rt_val = proc.get_context_status("ContextName1")
            self.assertEqual(rt_val, (-1, ""))

    def test_get_context_status_connect_exception(self):
        """Test get_context_status flow when connecting results in an qmi error."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            context, _, _ = self._build_mock_config()
            self._make_context_mock_peer()
            context.connect_to_peer = MagicMock(side_effect=proc.QMI_Exception)
            with self.assertRaises(proc.ProcessException):
                proc.get_context_status("ContextName1")

    def test_get_context_status_get_pid_exception(self):
        """Test get_context_status flow when unable to collect the PID."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            self._build_mock_config()
            proxy = self._make_context_mock_peer()
            proxy.get_pid = MagicMock(side_effect=proc.QMI_Exception)
            with self.assertRaises(proc.ProcessException):
                proc.get_context_status("ContextName1")

    def test_get_context_status_disconnect_exception(self):
        """Test get_context_status flow when disconnect results into an exception."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            context, _, _ = self._build_mock_config()
            self._make_context_mock_peer()
            context.disconnect_from_peer = MagicMock(
                side_effect=proc.QMI_UnknownNameException
            )
            proc.get_context_status("ContextName1")  # exception is pass'ed.

    def test_shutdown_context_hard(self):
        """Test shutdown_context, happy flow, hard shutdown."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.time", MagicMock()
        ), patch("qmi.tools.proc.CONTEXT_SHUTDOWN_TIMEOUT", 0.5):
            context, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            future = MagicMock()
            future.wait = MagicMock()
            proxy.rpc_nonblocking.shutdown_context = MagicMock(return_value=future)
            context.has_peer_context = MagicMock(side_effect=[True, False])

            rt_val = proc.shutdown_context("ContextName1", cb := MagicMock())
            self.assertEqual(rt_val.responding, True)
            self.assertEqual(rt_val.pid, 123)
            self.assertEqual(rt_val.success, True)

            cb.assert_has_calls(
                [
                    call("soft shutdown"),
                    call(""),
                    call("hard shutdown"),
                    call(""),
                ]
            )

    def test_shutdown_context_soft(self):
        """Test shutdown_context, happy flow, soft shutdown."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.time", MagicMock()
        ), patch("qmi.tools.proc.CONTEXT_SHUTDOWN_TIMEOUT", 0.5):
            context, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            future = MagicMock()
            future.wait = MagicMock()
            proxy.rpc_nonblocking.shutdown_context = MagicMock(return_value=future)
            context.has_peer_context = MagicMock(return_value=False)

            rt_val = proc.shutdown_context("ContextName1", cb := MagicMock())
            self.assertEqual(rt_val.responding, True)
            self.assertEqual(rt_val.pid, 123)
            self.assertEqual(rt_val.success, True)

            cb.assert_has_calls(
                [
                    call("soft shutdown"),
                    call(""),
                ]
            )

    def test_shutdown_context_no_host(self):
        """Test shutdown_context flow when no host is configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, ctxcfg = self._build_mock_config()
            ctxcfg.host = None
            with self.assertRaises(proc.ProcessException):
                proc.shutdown_context("ContextName1", MagicMock())

    def test_shutdown_context_connect_oserror(self):
        """Test shutdown_context flow when connecting results in an os error."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            context, _, _ = self._build_mock_config()
            self._make_context_mock_peer()
            context.connect_to_peer = MagicMock(side_effect=OSError)
            rt_val = proc.shutdown_context("ContextName1", MagicMock())
            self.assertEqual(rt_val.responding, False)
            self.assertEqual(rt_val.pid, -1)
            self.assertEqual(rt_val.success, False)

    def test_shutdown_context_connect_exception(self):
        """Test shutdown_context flow when connecting results in an qmi error."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            context, _, _ = self._build_mock_config()
            self._make_context_mock_peer()
            context.connect_to_peer = MagicMock(side_effect=proc.QMI_Exception)
            with self.assertRaises(proc.ProcessException):
                proc.shutdown_context("ContextName1", MagicMock())

    def test_shutdown_context_pid_exception(self):
        """Test shutdown_context flow when get pid results in an exception."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            proxy.get_pid = MagicMock(side_effect=proc.QMI_Exception)
            with self.assertRaises(proc.ProcessException):
                proc.shutdown_context("ContextName1", MagicMock())

    def test_shutdown_context_soft_timeout(self):
        """Test shutdown_context flow when soft shutdown results in an timeout."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.time", MagicMock()
        ):
            context, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            future = MagicMock()
            future.wait = MagicMock(side_effect=proc.QMI_RpcTimeoutException)
            proxy.rpc_nonblocking.shutdown_context = MagicMock(return_value=future)
            context.has_peer_context = MagicMock(return_value=False)

            proc.shutdown_context("ContextName1", cb := MagicMock())

            cb.assert_has_calls(
                [
                    call("soft shutdown"),
                    call("timeout"),
                    call(""),
                ]
            )

    def test_shutdown_context_soft_exception(self):
        """Test shutdown_context flow when soft shutdown results in a connection error."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()):
            _, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            future = MagicMock()
            future.wait = MagicMock(side_effect=proc.QMI_Exception)
            proxy.rpc_nonblocking.shutdown_context = MagicMock(return_value=future)
            with self.assertRaises(proc.ProcessException):
                proc.shutdown_context("ContextName1", MagicMock())

    def test_shutdown_context_responding_failure(self):
        """Test shutdown_context flow when context is not responding."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.time", MagicMock()
        ), patch("qmi.tools.proc.CONTEXT_SHUTDOWN_TIMEOUT", 0.5):
            context, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            future = MagicMock()
            future.wait = MagicMock()
            proxy.rpc_nonblocking.shutdown_context = MagicMock(return_value=future)
            context.has_peer_context = MagicMock(side_effect=[True, True])

            rt_val = proc.shutdown_context("ContextName1", MagicMock())
            self.assertEqual(rt_val.responding, True)
            self.assertEqual(rt_val.pid, 123)
            self.assertEqual(rt_val.success, False)

    def test_shutdown_context_disconnect_exception(self):
        """Test shutdown_context flow when disconnect results in an error."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "qmi.tools.proc.time", MagicMock()
        ), patch("qmi.tools.proc.CONTEXT_SHUTDOWN_TIMEOUT", 0.5):
            context, _, _ = self._build_mock_config()
            proxy = self._make_context_mock_peer()
            future = MagicMock()
            future.wait = MagicMock()
            proxy.rpc_nonblocking.shutdown_context = MagicMock(return_value=future)
            context.has_peer_context = MagicMock(side_effect=[True, False])
            context.disconnect_from_peer = MagicMock(
                side_effect=proc.QMI_UnknownNameException
            )

            proc.shutdown_context("ContextName1", MagicMock())  # exception is passed.

    def test_select_contexts(self):
        """Test select_contexts, happy flow."""
        _, config, _ = self._build_mock_config()
        # Make the contexts "proper" contexts for the 'is_local_host' check.
        config.contexts["ContextName0"] = CfgContext()
        config.contexts["ContextName0"].host = "127.0.0.1"  # Local
        config.contexts["ContextName0"].enabled = True
        config.contexts["ContextName1"] = CfgContext()
        config.contexts["ContextName1"].host = "123.456.78.9"  # Not local
        config.contexts["ContextName1"].enabled = True
        # Select and assert
        contexts = proc.select_contexts(config)
        self.assertEqual(contexts[0], "ContextName1")
        # This patch we need for the 'is_local_host' check in the call.
        with patch(
                "qmi.tools.proc.get_context_status",
                MagicMock(
                    side_effect=[
                        (-1, "SomeVersion"),
                        (123, "SomeVersion"),
                    ]
                ),
        ):
            contexts = proc.select_local_contexts(config)
            self.assertEqual(contexts[0], "ContextName0")

    def test_select_contexts_not_in_config(self):
        """Test select_context_by_name when provided context is not configured."""
        with self.assertRaises(proc.QMI_ApplicationException):
            proc.select_context_by_name(MagicMock(), "InvalidContextName")

    def test_select_contexts_no_names(self):
        """Test select_contexts when no contexts are configured."""
        _, config, _ = self._build_mock_config()
        config.contexts = {}
        with self.assertRaises(proc.QMI_ApplicationException):
            proc.select_contexts(config)

    def test_select_contexts_invalid_name(self):
        """Test select_context_by_name when an invalid context name is configured."""
        _, config, _ = self._build_mock_config()
        config.contexts = {"!INVALID": MagicMock()}
        with self.assertRaises(proc.QMI_ApplicationException):
            proc.select_context_by_name(config, "!INVALID")

    def test_proc_server_start(self):
        """Test proc_server_start happy flow."""
        _, config, _ = self._build_mock_config()
        with patch(
            "qmi.tools.proc.start_local_process", MagicMock(return_value=123)
        ), patch("qmi.tools.proc.is_local_host", MagicMock(return_value=True)), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["START ContextName1", ""])
        ):
            rt_val = proc.proc_server(config)
            proc.start_local_process.assert_called_once_with("ContextName1")
            self.assertEqual(rt_val, 0)

    def test_proc_server_start_no_ctxcfg(self):
        """Test proc_server_start when contexts are not configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["START ContextName1", ""])
        ), patch(
            "qmi.tools.proc.print", MagicMock()
        ):
            _, config, _ = self._build_mock_config()
            config.contexts = {}
            proc.proc_server(config)
            proc.print.assert_called_with("ERR Unknown context")

    def test_proc_server_start_not_local_host(self):
        """Test proc_server_start when context is not localhost."""
        with patch(
            "qmi.tools.proc.start_local_process", MagicMock(return_value=123)
        ), patch("qmi.tools.proc.is_local_host", MagicMock(return_value=False)), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["START ContextName1", ""])
        ), patch(
            "qmi.tools.proc.print", MagicMock()
        ):
            _, config, _ = self._build_mock_config()
            proc.proc_server(config)
            proc.print.assert_called_with("ERR Context should not run on this host")
            # sadly the only valid way to test this.

    def test_proc_server_stop(self):
        """Test proc_server_stop, happy flow."""
        with patch(
            "qmi.tools.proc.stop_local_process", MagicMock(return_value=True)
        ), patch("qmi.tools.proc.is_local_host", MagicMock(return_value=True)), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["STOP ContextName1 123", ""])
        ), patch(
            "qmi.tools.proc.print", MagicMock()
        ):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_server(config)
            proc.stop_local_process.assert_called_once_with("ContextName1", 123)
            self.assertEqual(rt_val, 0)

    def test_proc_server_stop_invalid_pid(self):
        """Test proc_server_start when contexts are not configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["STOP ContextName1 0", ""])
        ):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_server(config)
            self.assertEqual(rt_val, 1)

    def test_proc_server_stop_no_ctxcfg(self):
        """Test proc_server_start when contexts are not configured."""
        with patch("qmi.tools.proc.qmi.context", MagicMock()), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["STOP ContextName1 123", ""])
        ), patch(
            "qmi.tools.proc.print", MagicMock()
        ):
            _, config, _ = self._build_mock_config()
            config.contexts = {"ContextName1": None}
            proc.proc_server(config)
            proc.print.assert_called_with("ERR Unknown context")

    def test_proc_server_stop_no_local_host(self):
        """Test proc_server_stop when context is not localhost."""
        with patch(
            "qmi.tools.proc.stop_local_process", MagicMock(return_value=True)
        ), patch("qmi.tools.proc.is_local_host", MagicMock(return_value=False)), patch(
            "sys.stdout.flush", MagicMock()
        ), patch(
            "sys.stdin.readline", MagicMock(side_effect=["STOP ContextName1 123", ""])
        ), patch(
            "qmi.tools.proc.print", MagicMock()
        ):
            _, config, _ = self._build_mock_config()
            proc.proc_server(config)
            proc.print.assert_called_with("ERR Context should not run on this host")

    def test_proc_server_value_error(self):
        """Test proc_server invalid input."""
        with patch("sys.stdout.flush", MagicMock()), patch(
            "sys.stdin.readline", MagicMock(side_effect="INVALID")
        ), patch("qmi.tools.proc.print", MagicMock()):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_server(config)
            self.assertEqual(rt_val, 1)

    def test_proc_start(self):
        """Test proc_start happy flow."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(
                side_effect=[
                    (-1, "SomeVersion"),
                    (123, "SomeVersion"),
                ]
            ),
        ), patch("qmi.tools.proc.start_process", MagicMock(return_value=123)):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_start(config, "ContextName1", False)
            self.assertEqual(rt_val, 0)

    def test_proc_start_already_running(self):
        """Test proc_start flow when invalid pid."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(
                return_value=(123, "SomeVersion"),
            ),
        ), patch("qmi.tools.proc.start_process", MagicMock(return_value=123)):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_start(config, "ContextName1", False)
            self.assertEqual(rt_val, 0)

    def test_proc_start_not_responding(self):
        """Test proc_start when context not responding."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(return_value=(-1, "SomeVersion")),
        ), patch("qmi.tools.proc.start_process", MagicMock(return_value=123)):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_start(config, "ContextName1", False)
            self.assertEqual(rt_val, 1)

    def test_proc_start_invalid_pid(self):
        """Test proc_start flow when invalid pid."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(
                side_effect=[
                    (-1, "SomeVersion"),
                    (456, "SomeVersion"),  # return a invalid pid
                ]
            ),
        ), patch("qmi.tools.proc.start_process", MagicMock(return_value=123)):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_start(config, "ContextName1", False)
            self.assertEqual(rt_val, 1)

    def test_proc_stop(self):
        """Test proc_stop happy flow."""
        _, config, _ = self._build_mock_config()
        with patch(
            "qmi.tools.proc.shutdown_context",
            MagicMock(return_value=proc.ShutdownResult(True, 123, True)),
        ):
            rt_val = proc.proc_stop(config, "ContextName1", False)
            self.assertEqual(rt_val, 0)

    def test_proc_stop_not_responding(self):
        """Test proc_stop context not responding."""
        _, config, _ = self._build_mock_config()
        with patch(
            "qmi.tools.proc.shutdown_context",
            MagicMock(return_value=proc.ShutdownResult(False, 123, False)),
        ):
            rt_val = proc.proc_stop(config, "ContextName1", False)
            self.assertEqual(rt_val, 0)

    def test_proc_stop_kill(self):
        """Test proc_stop kill has is killed."""
        _, config, _ = self._build_mock_config()
        with patch(
            "qmi.tools.proc.shutdown_context",
            MagicMock(return_value=proc.ShutdownResult(True, 123, False)),
        ), patch("qmi.tools.proc.stop_process", MagicMock(return_value=True)):
            rt_val = proc.proc_stop(config, "ContextName1", False)
            self.assertEqual(rt_val, 0)

    def test_proc_stop_failure_responding(self):
        """Test proc_stop when context is not responding."""
        with patch(
            "qmi.tools.proc.shutdown_context",
            MagicMock(return_value=proc.ShutdownResult(True, 123, False)),
        ), patch("qmi.tools.proc.stop_process", MagicMock(return_value=False)):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_stop(config, "ContextName1", False)
            self.assertEqual(rt_val, 0)

    def test_proc_stop_exception(self):
        """Test proc_stop when shutdown resulted in exception."""
        with patch(
            "qmi.tools.proc.shutdown_context",
            MagicMock(side_effect=proc.ProcessException),
        ):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_stop(config, "ContextName1", False)
            self.assertEqual(rt_val, 1)

    def test_proc_status(self):
        """Test proc_status happy flow."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(return_value=(123, "SomeVersion")),
        ):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_status(config, "ContextName1")
            self.assertEqual(rt_val, 0)

    def test_proc_status_offline(self):
        """Test proc_status process offline."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(return_value=(-1, "SomeVersion")),
        ):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_status(config, "ContextName1")
            self.assertEqual(rt_val, 0)

    def test_proc_status_exception(self):
        """Test proc_status exception."""
        with patch(
            "qmi.tools.proc.get_context_status",
            MagicMock(side_effect=proc.ProcessException),
        ):
            _, config, _ = self._build_mock_config()
            rt_val = proc.proc_status(config, "ContextName1")
            self.assertEqual(rt_val, 1)


class ArgParserTestCase(unittest.TestCase):

    def setUp(self) -> None:
        # suppress print-outs
        self._stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')  # redirect stderr to null device
        context_cfg = {
            "somectx": CfgContext(
                host="127.0.0.1",
                tcp_server_port=12345,
                program_module="test_program_module",
                enabled=True
            )
        }
        self.context_cfg = CfgQmi(contexts=context_cfg)
        ctx_patcher = patch("qmi.core.context.QMI_Context.get_config", return_value=self.context_cfg)
        self.addCleanup(ctx_patcher.stop)
        peer_patcher = patch("qmi.core.context.QMI_Context.connect_to_peer")
        self.addCleanup(peer_patcher.stop)
        ctx_patcher.start()
        peer_patcher.start()

    def tearDown(self) -> None:
        sys.stderr = self._stderr

    @patch("builtins.print")
    def test_start_server_mode_fails(self, print_patch):
        """Test that server mode start fails with incompatible commands."""
        fail_all = Namespace(command="server", all=True, locals=False, context_name=None, config=None)
        fail_local = Namespace(command="server", all=False, locals=True, context_name=None, config=None)
        fail_context_name = Namespace(command="server", all=False, locals=False, context_name="somectx", config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=fail_all):
            retval = proc.main()
            self.assertEqual(retval, 1)

        print_patch.assert_called_with("ERROR: Can not specify server mode together with other options")
        print_patch.reset()

        with patch("argparse.ArgumentParser.parse_args", return_value=fail_local):
            retval = proc.main()
            self.assertEqual(retval, 1)

        print_patch.assert_called_with("ERROR: Can not specify server mode together with other options")
        print_patch.reset()

        with patch("argparse.ArgumentParser.parse_args", return_value=fail_context_name):
            retval = proc.main()
            self.assertEqual(retval, 1)

        print_patch.assert_called_with("ERROR: Can not specify server mode together with other options")

    @patch("builtins.print")
    @patch("sys.stderr", return_value=None)
    def test_start_all_fails(self, sys_patch, print_patch):
        """Test that starting all contexts fails with incompatible commands."""
        fail_context_name = Namespace(command="start", all=True, locals=False, context_name="fail_ctx", config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=fail_context_name):
            retval = proc.main()
            self.assertEqual(retval, 1)

        print_patch.assert_called_with("ERROR: Can not specify a context_name together with --all", file=sys_patch)
        print_patch.reset()

        # We cannot test the same way the mutex as the argparse goes to sys.exit() at ArgumentError. Patch!
        sys.argv = ["command", "start", "--all", "--locals"]
        with patch("qmi.tools.proc.argparse.ArgumentParser.error", side_effect=[ArgumentError(MagicMock(), "Fail!")]):
            with self.assertRaises(ArgumentError) as arg_err:
                retval = proc.main()

        self.assertEqual(retval, 1)
        self.assertEqual("argument : Fail!", str(arg_err.exception))

        # But one true and one false should not raise ArgumentError, even if it fails otherwise!
        sys.argv = ["command", "start", "--all"]
        retval = proc.main()
        self.assertEqual(retval, 1)

        sys.argv = ["command", "start", "--locals"]
        retval = proc.main()
        self.assertEqual(retval, 1)

    @patch("builtins.print")
    @patch("sys.stderr", return_value=None)
    def test_start_locals_fails(self, sys_patch, print_patch):
        """Test that starting local contexts fails with incompatible context name."""
        fail_context_name = Namespace(command="start", all=False, locals=True, context_name="fail_ctx", config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=fail_context_name):
            retval = proc.main()
            self.assertEqual(retval, 1)

        print_patch.assert_called_with("ERROR: Can not specify a context_name together with --locals", file=sys_patch)

    @patch("builtins.print")
    @patch("sys.stderr", return_value=None)
    def test_start_stop_restart_fails(self, sys_patch, print_patch):
        """Test that 'start', 'stop' and 'restart' commands require extra arguments."""
        commands = ["start", "stop", "restart"]
        for command in commands:
            fail_command = Namespace(command=command, all=False, locals=False, context_name=None, config=None)
            with patch("argparse.ArgumentParser.parse_args", return_value=fail_command):
                retval = proc.main()
                self.assertEqual(retval, 1)

            print_patch.assert_called_with("ERROR: Specify either: a context_name, or --all, or --local", file=sys_patch)
            print_patch.reset()

    def test_start_server_mode(self):
        """Test that server mode is started with command 'server'."""
        return_value = Namespace(command="server", all=False, locals=False, context_name=None, config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=return_value):
            with patch("sys.stdin.readline", return_value=None) as sys_readline:
                retval = proc.main()
                sys_readline.assert_called_once()
                self.assertEqual(retval, 0)

    def test_start_context_name(self):
        """Test that select_(local_)context is called with command 'start'."""
        ctx = self.context_cfg
        ctx_name = list(ctx.contexts.keys())[0]
        local_ctx = None
        start_ctx = Namespace(command="start", all=False, locals=False, context_name=ctx_name, config=None)
        start_local_ctx = Namespace(command="start", all=False, locals=True, context_name=local_ctx, config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=start_ctx),\
             patch("qmi.tools.proc.select_context_by_name", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx, ctx_name)

        with patch("argparse.ArgumentParser.parse_args", return_value=start_local_ctx),\
             patch("qmi.tools.proc.select_local_contexts", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx)

    def test_stop_context_name(self):
        """Test that select_(local_)context is called with command 'stop'."""
        ctx = self.context_cfg
        ctx_name = list(ctx.contexts.keys())[0]
        local_ctx = None
        stop_ctx = Namespace(command="stop", all=False, locals=False, context_name=ctx_name, config=None)
        stop_local_ctx = Namespace(command="stop", all=False, locals=True, context_name=local_ctx, config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=stop_ctx),\
             patch("qmi.tools.proc.select_context_by_name", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx, ctx_name)

        with patch("argparse.ArgumentParser.parse_args", return_value=stop_local_ctx),\
             patch("qmi.tools.proc.select_local_contexts", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx)

    def test_restart_context_name(self):
        """Test that select_(local_)context is called with command 'restart'.
        Actually this will call only `proc_stop` as we set it to except. But the logic is then tested.
        """
        ctx = self.context_cfg
        ctx_name = list(ctx.contexts.keys())[0]
        local_ctx = None
        restart_ctx = Namespace(command="restart", all=False, locals=False, context_name=ctx_name, config=None)
        restart_local_ctx = Namespace(command="restart", all=False, locals=True, context_name=local_ctx, config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=restart_ctx),\
             patch("qmi.tools.proc.select_context_by_name", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx, ctx_name)

        with patch("argparse.ArgumentParser.parse_args", return_value=restart_local_ctx),\
             patch("qmi.tools.proc.select_local_contexts", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx)

    def test_status_context_name(self):
        """Test that select_(local_)context is called with command 'restart'.
        Actually this will call only `proc_stop` as we set it to except. But the logic is then tested.
        """
        ctx = self.context_cfg
        ctx_name = list(ctx.contexts.keys())[0]
        status_ctx = Namespace(command="status", all=False, locals=False, context_name=ctx_name, config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=status_ctx),\
             patch("qmi.tools.proc.select_context_by_name", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_called_once_with(ctx, ctx_name)

    def test_unknown_command(self):
        """Test that unknown command just returns without trying to select a context.
        This test is not fully exclusive, but should demonstrate w.r.t. previous tests that this is the case.
        """
        unknown_ctx = Namespace(command="unknown", all=True, locals=False, context_name=None, config=None)
        unknown_local_ctx = Namespace(command="unknown", all=True, locals=True, context_name=None, config=None)
        with patch("argparse.ArgumentParser.parse_args", return_value=unknown_ctx),\
             patch("qmi.tools.proc.select_contexts", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_not_called()

        with patch("argparse.ArgumentParser.parse_args", return_value=unknown_local_ctx),\
             patch("qmi.tools.proc.select_local_contexts", side_effect=[QMI_ApplicationException("wrong")]) as sel_ctx:
            retval = proc.main()
            self.assertEqual(retval, 1)
            sel_ctx.assert_not_called()
