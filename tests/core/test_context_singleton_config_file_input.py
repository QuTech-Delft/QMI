#! /usr/bin/env python3

"""Test start/stop functionality of QMI framework with config files and optional inputs.
"""
import logging
import os
from shutil import rmtree
import unittest

ORIGINAL_QMI_CONFIG = os.getenv("QMI_CONFIG")
qmi_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qmi.conf")
os.environ["QMI_CONFIG"] = qmi_config_path

import qmi
import qmi.core.context_singleton
import qmi.core.exceptions

QMI_ENV_CONFIG_FILE_PRESENT = False
QMI_ENV_CONFIG_FILE = os.path.join(str(os.getenv("QMI_CONFIG")), "qmi.conf")
if os.path.isfile(QMI_ENV_CONFIG_FILE):
    QMI_ENV_CONFIG_FILE_PRESENT = True

CONFIG_FILE_CONTEXT = """{
    # Log level for messages to the console.
    "logging": {
        "console_loglevel": "INFO",
        "max_bytes": 100,
        "backup_count": 2
    },
    # Directory to write various log files.
    "log_dir": "${qmi_home}/log_dir",

    "contexts": {
        # Testing remote instrument access.
        "instr_server": {
            "host": "127.0.0.1",
            "tcp_server_port": 40001
        },
        "instr_client": {
            "connect_to_peers": ["instr_server"]
        }
    }
}"""

CONTEXT_CFG = {"instr_server": {
        "host": 'localhost',
        "tcp_server_port": 10004,
        "connect_to_peers": [],
        "enabled": True,
        "program_module": "some_module",
        "program_args": [],
        "python_path": "SOMEPATH",
        "virtualenv_path": None
    },
    "instr_client": {
        "host": None,
        "tcp_server_port": None,
        "connect_to_peers": ["instr_server"],
        "enabled": False,
        "program_module": None,
        "program_args": ["arg1", "arg2"],
        "python_path": None,
        "virtualenv_path": "MOSEPATH"
        }
    }

BAD_OPTIONAL_CONTEXT_1 = {"instr_server": {
        "tcp_server_port": "10004"
    }}
BAD_OPTIONAL_CONTEXT_2 = {"instr_client": {
        "connect_to_peers": "instr_server"
        }
    }
BAD_OPTIONAL_CONTEXT_3 = {"instr_server": {
        "enabled": "True"
    }}


class TestContextConfigFileInputs(unittest.TestCase):

    def setUp(self) -> None:
        self.ctx_name = "hello_world"

    def tearDown(self):
        # Stop context if present.
        if self.ctx_name in qmi.info():
            log_dir = qmi.context().get_log_dir()
            qmi.stop()
            # Careful here not to remove accidentally QMI_HOME... Which could be your home directory!
            if log_dir.endswith("log_dir"):
                logging.shutdown()  # Forces log file to close.
                rmtree(log_dir)

        # Set these back to None to avoid false leads for later unit-tests
        qmi.core.context_singleton.QMI_CONFIG = None

    def test_01_no_input_no_environment(self):
        # Check that not giving an input file leads to use of default context.
        qmi.core.context_singleton.QMI_CONFIG = None

        qmi.start(self.ctx_name, None)
        ctx = qmi.context()

        self.assertEqual(self.ctx_name, ctx.name)
        self.assertTrue(ctx.get_config().config_file is None)
        self.assertTrue(ctx.get_config().qmi_home is None)

    def test_02_no_input_QMI_CONFIG_environment_set(self):
        # Check that, when QMI_CONFIG environment variable is "set", it is used if no input file given.
        # Add extra check that we do not accidentally overwrite/delete a real QMI_CONFIG qmi.conf file
        qmi_config_path = os.path.dirname(os.path.abspath(__file__))
        qmi_config_file = os.path.join(qmi_config_path, "qmi.conf")
        qmi_log_path = os.path.join(os.path.expanduser("~"), "log_dir")
        qmi_log_file = os.path.join(qmi_log_path, "qmi.log")
        delete_later = False
        if not os.path.isfile(qmi_config_file):
            # First create a temporary qmi.conf file.
            delete_later = True
            with open(qmi_config_file, 'w') as qmi_conf:
                qmi_conf.write(CONFIG_FILE_CONTEXT)

        qmi.core.context_singleton.QMI_CONFIG = qmi_config_file

        qmi.start(self.ctx_name)
        ctx = qmi.context()
        self.assertEqual(self.ctx_name, ctx.name)
        self.assertEqual(qmi_config_file, ctx.get_config().config_file)
        self.assertIsNone(ctx.get_config().qmi_home)
        self.assertEqual(qmi_log_path, ctx.get_log_dir())
        self.assertEqual(qmi_log_file, os.path.join(ctx.get_log_dir(), "qmi.log"))

        if delete_later:
            os.remove(qmi_config_file)

    def test_03_input_config_file(self):
        # Check that context creation works with an input for input file.
        # First create a temporary qmi.conf file.
        qmi_config_path = os.path.dirname(os.path.abspath(__file__))
        qmi_config_file = os.path.join(qmi_config_path, "qmi.conf")
        with open(qmi_config_file, 'w') as qmi_conf:
            qmi_conf.write(CONFIG_FILE_CONTEXT)

        qmi.start(self.ctx_name, qmi_config_file)
        ctx = qmi.context()
        qmi.core.context_singleton._init_logging()  # Run again to see that it does not crash on already existing log

        self.assertEqual(ctx.name, self.ctx_name)
        self.assertEqual(ctx.get_config().config_file, qmi_config_file)
        self.assertTrue(ctx.get_config().qmi_home is None)

        os.remove(qmi_config_file)

    def test_04_input_config_file_error(self):
        # Check that an error is raised when there is a mistake in the input file name/path
        qmi_config_path = os.path.dirname(os.path.abspath(__file__))
        qmi_config_file = os.path.join(qmi_config_path, "qmi.conf")

        with self.assertRaises(FileNotFoundError):
            qmi.start(self.ctx_name, qmi_config_file)

    def test_05_no_input_override_default_loglevel(self):
        # Check that we can override default loglevel.
        loglevel = "WARN"
        qmi.core.context_singleton.QMI_CONFIG = None

        qmi.start(self.ctx_name, console_loglevel=loglevel)
        ctx = qmi.context()

        self.assertEqual(ctx.get_config().logging.console_loglevel, loglevel.upper())

    def test_06_no_input_invalid_override_loglevel(self):
        # Check that we raise an error with an invalid loglevel.
        loglevel = "SILENT"
        qmi.core.context_singleton.QMI_CONFIG = None
        with self.assertRaises(qmi.core.exceptions.QMI_ConfigurationException):
            qmi.start(self.ctx_name, console_loglevel=loglevel)


class TestContextOptionalConfigInputs(unittest.TestCase):

    def setUp(self):
        self.log_dir = ""

    def tearDown(self):
        # Careful here not to remove accidentally QMI_HOME... Which could be your home directory!
        if self.log_dir.endswith("log_dir"):
            logging.shutdown()  # Forces log file to close.
            rmtree(self.log_dir)

    def test_01_no_conf_file_only_optional_cfg_input(self):
        # Check that not giving an input config file, but giving optional cfg input leads to use of optional context.
        context_name = "instr_server"
        second_context = "instr_client"
        qmi.core.context_singleton.QMI_CONFIG = None

        qmi.start(context_name, context_cfg=CONTEXT_CFG)

        try:
            contexts = qmi.get_configured_contexts()
            # Check first the server context values are correct
            context_server = contexts[context_name]
            input_server_context = CONTEXT_CFG[context_name]
            self.assertTrue(context_server.host is input_server_context["host"])
            self.assertTrue(context_server.tcp_server_port is input_server_context["tcp_server_port"])
            self.assertTrue(context_server.connect_to_peers == input_server_context["connect_to_peers"])
            self.assertTrue(context_server.enabled is input_server_context["enabled"])
            self.assertTrue(context_server.program_module is input_server_context["program_module"])
            self.assertTrue(context_server.program_args == input_server_context["program_args"])
            self.assertTrue(context_server.python_path is input_server_context["python_path"])
            self.assertTrue(context_server.virtualenv_path is input_server_context["virtualenv_path"])
            # Then check the client context values are correct
            context_client = contexts[second_context]
            input_client_context = CONTEXT_CFG[second_context]
            self.assertTrue(context_client.host is input_client_context["host"])
            self.assertTrue(context_client.tcp_server_port is input_client_context["tcp_server_port"])
            self.assertTrue(context_client.connect_to_peers == input_client_context["connect_to_peers"])
            self.assertTrue(context_client.enabled is input_client_context["enabled"])
            self.assertTrue(context_client.program_module is input_client_context["program_module"])
            self.assertTrue(context_client.program_args == input_client_context["program_args"])
            self.assertTrue(context_client.python_path is input_client_context["python_path"])
            self.assertTrue(context_client.virtualenv_path is input_client_context["virtualenv_path"])

        finally:
            qmi.stop()

    def test_02_conf_file_context_overridden_by_optional_cfg_input(self):
        # Check that the initial config values read from config file get overridden with optional config input
        # First create a temporary qmi.conf file.
        qmi_config_path = os.path.dirname(os.path.abspath(__file__))
        qmi_config_file = os.path.join(qmi_config_path, "qmi.conf")
        with open(qmi_config_file, 'w') as qmi_conf:
            qmi_conf.write(CONFIG_FILE_CONTEXT)

        context_name = "instr_server"
        second_context = "instr_client"

        qmi.start(context_name, qmi_config_file, context_cfg=CONTEXT_CFG)
        try:
            contexts = qmi.get_configured_contexts()
            # Check first the server context values are correct
            context_server = contexts[context_name]
            input_server_context = CONTEXT_CFG[context_name]
            self.assertTrue(context_server.host is input_server_context["host"])
            self.assertTrue(context_server.tcp_server_port is input_server_context["tcp_server_port"])
            self.assertTrue(context_server.connect_to_peers == input_server_context["connect_to_peers"])
            self.assertTrue(context_server.enabled is input_server_context["enabled"])
            self.assertTrue(context_server.program_module is input_server_context["program_module"])
            self.assertTrue(context_server.program_args == input_server_context["program_args"])
            self.assertTrue(context_server.python_path is input_server_context["python_path"])
            self.assertTrue(context_server.virtualenv_path is input_server_context["virtualenv_path"])
            # Then check the client context values are correct
            context_client = contexts[second_context]
            input_client_context = CONTEXT_CFG[second_context]
            self.assertTrue(context_client.host is input_client_context["host"])
            self.assertTrue(context_client.tcp_server_port is input_client_context["tcp_server_port"])
            self.assertTrue(context_client.connect_to_peers == input_client_context["connect_to_peers"])
            self.assertTrue(context_client.enabled is input_client_context["enabled"])
            self.assertTrue(context_client.program_module is input_client_context["program_module"])
            self.assertTrue(context_client.program_args == input_client_context["program_args"])
            self.assertTrue(context_client.python_path is input_client_context["python_path"])
            self.assertTrue(context_client.virtualenv_path is input_client_context["virtualenv_path"])

        finally:
            self.log_dir = qmi.context().get_log_dir()
            qmi.stop()
            os.remove(qmi_config_file)

    def test_03_see_that_typecheck_catches_wrong_input_types(self):
        # Check that the type checking in context_singleton catches wrong types on inputs in optional config
        context_name = "instr_server"
        second_context = "instr_client"
        qmi.core.context_singleton.QMI_CONFIG = None

        with self.assertRaises(qmi.core.exceptions.QMI_ConfigurationException):
            qmi.start(context_name, context_cfg=BAD_OPTIONAL_CONTEXT_1)

        with self.assertRaises(qmi.core.exceptions.QMI_ConfigurationException):
            qmi.start(second_context, context_cfg=BAD_OPTIONAL_CONTEXT_2)

        with self.assertRaises(qmi.core.exceptions.QMI_ConfigurationException):
            qmi.start(context_name, context_cfg=BAD_OPTIONAL_CONTEXT_3)

    def test_04_no_context_started_raises_QMI_NoActiveContextException(self):
        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.make_rpc_object("fail", object)

        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.make_instrument("fail", object)

        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.make_task("fail", object)

        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.get_rpc_object("fail")

        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.get_instrument("fail")

        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.get_task("fail")


if __name__ == "__main__":
    unittest.main()
    os.environ["QMI_CONFIG"] = ORIGINAL_QMI_CONFIG
