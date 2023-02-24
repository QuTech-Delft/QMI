#! /usr/bin/env python3

"""Test basic start/stop functionality of QMI framework.
"""
import os
import unittest
from collections import OrderedDict

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
        "console_loglevel": "WARNING"
    },

    "contexts": {
        # Testing remote instrument access.
        "instr_server": {
            "host": "127.0.0.1",
            "tcp_server_port": 40001
        }
    }
}"""


class TestContextConfigFileInputs(unittest.TestCase):

    def tearDown(self):
        # Set these back to None to avoid false leads for later unit-tests
        qmi.core.context_singleton.QMI_CONFIG = None

    def test_01_context_name_in_config_file(self):
        # Check that the context name matches with a config file context name.
        # First create a temporary qmi.conf file.
        qmi_config_path = os.path.dirname(os.path.abspath(__file__))
        qmi_config_file = os.path.join(qmi_config_path, "qmi.conf")
        with open(qmi_config_file, 'w') as qmi_conf:
            qmi_conf.write(CONFIG_FILE_CONTEXT)

        context_name = "instr_server"

        try:
            qmi.start(context_name, qmi_config_file)
            contexts = qmi.get_configured_contexts()
            self.assertIsInstance(contexts, OrderedDict)
            self.assertTrue(context_name in contexts.keys())

        finally:
            qmi.stop()
            os.remove(qmi_config_file)

    def test_02_context_name_not_in_config_file(self):
        # Check that, when context name is not in the config file, an exception is raised when checking the configured
        # contexts.
        # First create a temporary qmi.conf file.
        qmi_config_path = os.path.dirname(os.path.abspath(__file__))
        qmi_config_file = os.path.join(qmi_config_path, "qmi.conf")
        with open(qmi_config_file, 'w') as qmi_conf:
            qmi_conf.write(CONFIG_FILE_CONTEXT)

        context_name = "hello_world"

        qmi.start(context_name, qmi_config_file)
        try:
            contexts = qmi.get_configured_contexts()
            self.assertIsInstance(contexts, OrderedDict)
            self.assertTrue(context_name not in contexts.keys())

        finally:
            qmi.stop()
            os.remove(qmi_config_file)

    def test_03_no_config_file(self):
        # Check that, when no config file is defined, an exception is raised when checking the configured contexts.
        context_name = "instr_server"

        try:
            qmi.start(context_name)
            contexts = qmi.get_configured_contexts()
            self.assertIsInstance(contexts, OrderedDict)
            self.assertTrue(context_name not in contexts.keys())

        finally:
            qmi.stop()


if __name__ == "__main__":
    unittest.main()
    os.environ["QMI_CONFIG"] = ORIGINAL_QMI_CONFIG
