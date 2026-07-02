"""
Integration test for QMI proc.py --config argument default value behavior.

This test patches argparse.ArgumentParser to test proc.run() with:
1. default=None: Should FAIL - QMI_CONFIG is ignored, config not found
2. default="": Should SUCCEED - QMI_CONFIG is used, config found
"""

from argparse import ArgumentParser, Namespace
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from typing import Callable
from unittest.mock import MagicMock, patch

import qmi
from qmi.core.config import dump_config_file
from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.config_struct import config_struct_from_dict
from qmi.core.exceptions import QMI_ApplicationException
from qmi.tools import proc

CONTEXT_NAME = "ContextName1"
CONTEXT_CFG = {
    CONTEXT_NAME: {
        "host": "127.0.0.1",
        "tcp_server_port": 10340,
        "program_module": "tests.core.some_proc_service",
        "enabled": True,
    }
}
# CONFIG = {
#     "ip": "10.10.10.10",  # Local IP address
#     "port": 10320,
#     "server_command": "test_config_server_command",
#     "ssh_host": "test_config_ssh_host",
#     "ssh_user": "test_config_ssh_user",
#     "program_module": "test_program_module",
#     "program_args": ["test_program_arg1", "--test program_arg2"],
# }
#
#
# class ThreadWithReturnValue(threading.Thread):
#
#     def __init__(self, group=None, target=None, name=None, args=(), kwargs={}, Verbose=None):
#         self._return = None
#         super().__init__(group, target, name, args, kwargs)
#
#     def run(self):
#         try:
#             self._return = self._target(*self._args, **self._kwargs)
#         finally:
#             # Avoid a refcycle if the thread is running a function with
#             # an argument that has a member that points to the thread.
#             del self._target, self._args, self._kwargs
#
#     def join(self, timeout = None) -> Callable:
#         super().join(timeout)
#         print(type(self._return))
#         return self._return
#
#
# class QmiProcRealStartStatusStopTestCase(unittest.TestCase):
#
#     def setUp(self):
#         proc.qmi.context = context
#         proc.qmi.start = start
#         proc.qmi.stop = stop
#         proc.qmi.make_rpc_object = make_rpc_object
#         proc.qmi.make_task = make_task
#         proc.qmi.make_instrument = make_instrument
#         proc.qmi.get_rpc_object = get_rpc_object
#         proc.qmi.get_instrument = get_instrument
#         proc.qmi.get_task = get_task
#         proc.qmi.get_configured_contexts = get_configured_contexts
#         self.context_name = "ContextName1"
#         self.service_module = "some_proc_service"
#         qmi_conf = "qmi.conf"
#         self.path_to_conf = os.path.join(os.path.dirname(__file__), qmi_conf)
#         # set QMI_CONFIG
#         os.environ["QMI_CONFIG"] = self.path_to_conf
#         CONTEXT_CFG[self.context_name]["program_module"] = self.service_module
#         CONTEXT_CFG[self.context_name]["host"] = "127.0.0.1"
#         dump_config_file({"contexts": CONTEXT_CFG, "logging": {"loglevel": "CRITICAL"}}, self.path_to_conf)
#
#     def tearDown(self):
#         del os.environ["QMI_CONFIG"]
#         CONTEXT_CFG[self.context_name]["program_module"] = CONFIG["program_module"]
#         os.remove(self.path_to_conf)
#         try:
#             qmi.stop()
#         except:
#             pass
#
#     def test_start_local_service_and_check(self):
#         """Test starting a local service, with creating and specifying a virtual environment location,
#         and check that the process is running."""
#         with patch("qmi.tools.proc.sys.stdout", new = StringIO()) as print_out:
#             with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "start", self.context_name]):
#                 self.assertFalse(proc.run())
#
#             with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "status", self.context_name]):
#                 self.assertFalse(proc.run())
#
#             with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "stop", self.context_name]):
#                 self.assertFalse(proc.run())
#
#             print(f"{print_out.getvalue()=}")
#
#         print(f"{print_out.getvalue()=}")
#

class ProcRunConfigDefaultTestCase(unittest.TestCase):
    """
    Integration test for proc.run() with different --config default values.

    This test patches argparse.ArgumentParser to intercept the add_argument calls
    and modify the --config default value for testing.
    """

    def setUp(self):
        """Set up a temporary config file and QMI_CONFIG env variable."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "qmi.conf")

        # Create a valid config file
        config_dict = {
            "contexts": CONTEXT_CFG,
            "logging": {"loglevel": "CRITICAL"}
        }
        dump_config_file(config_dict, self.config_path)

        # Save original values
        self.original_qmi_config = os.environ.get("QMI_CONFIG")

        # patch colorama
        # colopatch = patch("qmi.tools.proc.colorama")
        # colopatch.start()
        # self.addCleanup(colopatch.stop)

        # patch sys
        # self.sys_patch = patch("qmi.tools.proc.sys", autospec=sys)
        # self.sys_patch.start()
        # self.addCleanup(self.sys_patch.stop)

        self._config = CfgQmi()
        for key, config_dict in CONTEXT_CFG.items():
            self._config.contexts.update({key: config_struct_from_dict(config_dict, CfgContext)})

        # QMI_Context.get_config = MagicMock(return_value=self._config)

    def tearDown(self):
        """Clean up temporary files and restore the environment."""
        try:
            qmi.stop()
        except:
            pass

        if os.path.exists(self.config_path):
            os.remove(self.config_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

        # Restore environment
        if self.original_qmi_config is not None:
            os.environ["QMI_CONFIG"] = self.original_qmi_config
        elif "QMI_CONFIG" in os.environ:
            del os.environ["QMI_CONFIG"]

    def test_proc_run_with_default_none_fails_without_config_file(self):
        """
        Test that when --config default=None, proc.run() FAILS if QMI_CONFIG is not used.

        Setup:
        - --config default is None
        - QMI_CONFIG environment variable is set
        - User runs: qmi_proc status TestContext (without explicit --config)

        Expected behavior:
        - args.config becomes None (default=None, not provided by user)
        - qmi.start(config_file=None) is called
        - qmi.start() does NOT check QMI_CONFIG
        - Config file is NOT found (or uses system default location)
        - Context "TestContext" is NOT found in any loaded configuration
        - QMI_ApplicationException is raised with "Unknown context" or similar
        """
        # Set QMI_CONFIG to our test config (but it won't be used with default=None)
        os.environ["QMI_CONFIG"] = self.config_path

        # Patch ArgumentParser.add_argument to use default=None for --config
        original_add_argument = ArgumentParser.add_argument

        def patched_add_argument(self, *args, **kwargs):
            # When adding the --config argument, override its default to None
            if '--config' in args:
                kwargs['default'] = None
            return original_add_argument(self, *args, **kwargs)

        # with redirect_stdout(StringIO()) as print_out:
        with patch("qmi.tools.proc.sys.stdout", new = StringIO()) as print_out:
            with patch.object(ArgumentParser, "add_argument", patched_add_argument):
                proc.sys.argv = ["qmi_proc", "status", CONTEXT_NAME]
                proc.run()

        print(f"{print_out.getvalue()=}")

    def test_proc_run_with_default_empty_string_succeeds_with_env_var(self):
        """
        Test that when --config default="", proc.run() SUCCEEDS if QMI_CONFIG is set.

        Setup:
        - --config default is "" (empty string)
        - QMI_CONFIG environment variable is set to our test config
        - User runs: qmi_proc status TestContext (without explicit --config)

        Expected behavior:
        - args.config becomes "" (default="", not provided by user)
        - qmi.start(config_file="") is called
        - qmi.start() checks/uses QMI_CONFIG because config_file is empty
        - Config file IS found via QMI_CONFIG
        - Context "TestContext" IS found in the loaded configuration
        - Status check succeeds (returns 0 or raises expected error from missing TCP)
        """
        # Set QMI_CONFIG to our test config
        os.environ["QMI_CONFIG"] = self.config_path

        # Patch ArgumentParser.add_argument to use default="" for --config
        original_add_argument = ArgumentParser.add_argument

        def patched_add_argument(self, *args, **kwargs):
            # When adding the --config argument, override its default to ""
            if '--config' in args:
                kwargs['default'] = ""
            return original_add_argument(self, *args, **kwargs)

        with patch.object(ArgumentParser, "add_argument", patched_add_argument), patch(
            "qmi.tools.proc.sys.argv", ["qmi_proc", "start", CONTEXT_NAME]
        ):
            result = proc.run()

        with patch.object(ArgumentParser, "add_argument", patched_add_argument), patch(
            "qmi.tools.proc.sys.argv", ["qmi_proc", "stop", CONTEXT_NAME]
        ):
            result_2 = proc.run()

        # The status command should return 0 (success)
        self.assertFalse(result)
        self.assertFalse(result_2)

    def test_proc_run_explicit_config_works_regardless_of_default(self):
        """
        Test that explicit --config parameter works regardless of default value.

        Setup:
        - --config default can be None or ""
        - User runs: qmi_proc status TestContext --config /path/to/qmi.conf

        Expected behavior:
        - args.config becomes /path/to/qmi.conf (explicitly provided)
        - Config file IS found via explicit path
        - Context "TestContext" IS found in the loaded configuration
        - Status check succeeds
        """
        # Test with default=None first
        original_add_argument = ArgumentParser.add_argument

        def patched_add_argument_none(self, *args, **kwargs):
            if '--config' in args:
                kwargs['default'] = None
            return original_add_argument(self, *args, **kwargs)

        with patch.object(ArgumentParser, 'add_argument', patched_add_argument_none):  # , \
            # Set command line arguments with explicit --config
            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "status", CONTEXT_NAME, "--config", self.config_path]):
                result = proc.run()

        self.assertEqual(result, 0)


class ProcRunConfigDefaultComparisonTestCase(unittest.TestCase):
    """
    Direct comparison test showing the behavior difference between default=None and default="".
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "qmi.conf")

        self.context_name = CONTEXT_NAME

        config_dict = {
            "contexts": CONTEXT_CFG,
            "logging": {"loglevel": "CRITICAL"}
        }
        dump_config_file(config_dict, self.config_path)

        self.original_qmi_config = os.environ.get("QMI_CONFIG")
        self.original_argv = sys.argv.copy()

        self._config = CfgQmi()
        for key, config_dict in CONTEXT_CFG.items():
            self._config.contexts.update({key: config_struct_from_dict(config_dict, CfgContext)})

    def tearDown(self):
        try:
            qmi.stop()
        except:
            pass

        if os.path.exists(self.config_path):
            os.remove(self.config_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

        if self.original_qmi_config is not None:
            os.environ["QMI_CONFIG"] = self.original_qmi_config
        elif "QMI_CONFIG" in os.environ:
            del os.environ["QMI_CONFIG"]

        sys.argv = self.original_argv

    def test_default_none_vs_empty_string_side_by_side(self):
        """
        Side-by-side comparison of behavior with default=None vs default="".

        This test demonstrates the key difference by running proc.run() twice
        with different parser configurations.
        """
        os.environ["QMI_CONFIG"] = self.config_path
        original_add_argument = ArgumentParser.add_argument

        def patched_add_argument_none(self, *args, **kwargs):
            if '--config' in args:
                kwargs['default'] = None
            return original_add_argument(self, *args, **kwargs)

        # with patch("qmi.tools.proc.sys.stdout", new = StringIO()) as print_out:
        with redirect_stdout(StringIO()) as print_out:
            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "start", self.context_name]):
                test_start = proc.run()

            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "stop", self.context_name]):
                test_stop = proc.run()

            with patch.object(ArgumentParser, 'add_argument', patched_add_argument_none), patch(  # , \
                "qmi.tools.proc.sys.argv", ["qmi_proc", "status", self.context_name]
            ):
                test_fail = proc.run()

        print(f"{print_out.getvalue()=}")
        # self.assertIn("STARTED", print_out.getvalue())
        # self.assertIn("STOPPED", print_out.getvalue())

        # Assertions showing the difference
        self.assertFalse(test_start)
        self.assertFalse(test_stop)
        self.assertTrue(test_fail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
