#! /usr/bin/env python

"""
Integration test for QMI proc.py --config argument default value behavior.

This test patches argparse.ArgumentParser to test proc.run() with:
1. default=None: Should FAIL - QMI_CONFIG is ignored, config not found
2. default="": Should SUCCEED - QMI_CONFIG is used, config found
"""

from argparse import ArgumentParser
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch, call

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


class ProcRunConfigDefaultTestCase(unittest.TestCase):
    """
    Integration test for proc.run() with different --config default values.

    This test patches argparse.ArgumentParser to intercept the add_argument calls
    and modify the --config default value for testing.
    """

    def setUp(self):
        """Set up a temporary config file and backup QMI_CONFIG env variable."""
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

        self._config = CfgQmi()
        for key, config_dict in CONTEXT_CFG.items():
            self._config.contexts.update({key: config_struct_from_dict(config_dict, CfgContext)})

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
        - User runs: qmi_proc status CONTEXT_NAME (without explicit --config)

        Expected behavior:
        - args.config becomes None (default=None, not provided by user)
        - qmi.start(config_file=None) is called
        - qmi.start() does NOT check QMI_CONFIG
        - Config file is NOT found (or uses system default location)
        - Context "CONTEXT_NAME" is NOT found in any loaded configuration
        - Result of run must be a fail (1)
        """
        # Arrange
        expected_exception = call('ERROR:', QMI_ApplicationException("Unknown context name 'ContextName1'"))
        # Set QMI_CONFIG to our test config (but it won't be used with default=None)
        os.environ["QMI_CONFIG"] = self.config_path

        # Patch ArgumentParser.add_argument to use default=None for --config
        original_add_argument = ArgumentParser.add_argument

        def patched_add_argument(self, *args, **kwargs):
            # When adding the --config argument, override its default to None
            if '--config' in args:
                kwargs['default'] = None
            return original_add_argument(self, *args, **kwargs)

        with patch("builtins.print") as print_out:
            with patch.object(ArgumentParser, "add_argument", patched_add_argument):
                proc.sys.argv = ["qmi_proc", "status", CONTEXT_NAME]
                result = proc.run()

        self.assertTrue(str(print_out.mock_calls[0]).startswith(expected_exception))
        self.assertTrue(result)

    def test_proc_run_with_default_empty_string_succeeds_with_env_var(self):
        """
        Test that when --config default="", proc.run() SUCCEEDS if QMI_CONFIG is set.

        Setup:
        - --config default is "" (empty string)
        - QMI_CONFIG environment variable is set to our test config
        - User runs: qmi_proc status CONTEXT_NAME (without explicit --config)

        Expected behavior:
        - args.config is "" (default="", not provided by user)
        - qmi.start(config_file="") is called
        - qmi.start() checks/uses QMI_CONFIG because config_file is empty
        - Config file IS found via QMI_CONFIG
        - Context "CONTEXT_NAME" IS found in the loaded configuration
        - Run succeeds (returns 0)
        """
        # Set QMI_CONFIG to our test config
        os.environ["QMI_CONFIG"] = self.config_path

        with redirect_stdout(StringIO()) as print_out:
            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "start", CONTEXT_NAME]):
                result = proc.run()

            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "stop", CONTEXT_NAME]):
                result_2 = proc.run()

        self.assertIn("STARTED", print_out.getvalue())
        self.assertIn("STOPPED", print_out.getvalue())
        # The status command should return 0 (success)
        self.assertFalse(result)
        self.assertFalse(result_2)

    def test_proc_run_explicit_config_works_regardless_of_default(self):
        """
        Test that explicit --config parameter works regardless of default value.

        Setup:
        - --config default is set to None
        - User runs: qmi_proc status CONTEXT_NAME --config /path/to/qmi.conf

        Expected behavior:
        - args.config becomes /path/to/qmi.conf (explicitly provided)
        - Config file IS found via explicit path
        - Context "CONTEXT_NAME" IS found in the loaded configuration
        - Status check succeeds
        """
        # Test with default=None first
        original_add_argument = ArgumentParser.add_argument

        def patched_add_argument_none(self, *args, **kwargs):
            if '--config' in args:
                kwargs['default'] = None
            return original_add_argument(self, *args, **kwargs)

        with patch.object(ArgumentParser, 'add_argument', patched_add_argument_none):
            # Set command line arguments with explicit --config
            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "status", CONTEXT_NAME, "--config", self.config_path]):
                result = proc.run()

        self.assertFalse(result)


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

        with redirect_stdout(StringIO()) as print_out:
            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "start", self.context_name]):
                test_start = proc.run()

            with patch("qmi.tools.proc.sys.argv", ["qmi_proc", "stop", self.context_name]):
                test_stop = proc.run()

            with patch.object(ArgumentParser, 'add_argument', patched_add_argument_none), patch(  # , \
                "qmi.tools.proc.sys.argv", ["qmi_proc", "status", self.context_name]
            ):
                test_fail = proc.run()

        self.assertIn("STARTED", print_out.getvalue())
        self.assertIn("STOPPED", print_out.getvalue())

        # Assertions showing the difference
        self.assertFalse(test_start)
        self.assertFalse(test_stop)
        self.assertTrue(test_fail)


if __name__ == "__main__":
    unittest.main()
