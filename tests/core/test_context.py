import unittest
import os
import time

from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_ConfigurationException, QMI_UsageException


class TestQMIContext(unittest.TestCase):

    def setUp(self):
        # Start two contexts.
        self.log_dir = os.path.join("~", "log_dir")
        self.datastore_dir = os.path.join("~","datastore")
        self.config_file = os.path.join("~", "config", "qmi.conf")
        self.qmi_home = os.path.join("~", "home")
        config1 = CfgQmi(
            contexts={"c1": CfgContext(tcp_server_port=0)},
            log_dir=self.log_dir,
            qmi_home=self.qmi_home,
            datastore=self.datastore_dir,
            config_file=self.config_file
            )
        config2 = CfgQmi(
            contexts={"c2": CfgContext(tcp_server_port=0)}
            )

        self.c1 = QMI_Context("c1", config1)
        self.c2 = QMI_Context("c2", config2)

        self.c1.start()
        self.c2.start()

    def tearDown(self):
        # Stop the contexts
        if self.c1._active:
            self.c1.stop()

        self.c1 = None
        if self.c2._active:
            self.c2.stop()

        self.c2 = None

    def test_version_mismatch_warnings(self):
        """Test that we can set and get version mismatch warnings"""
        suppress = self.c1.suppress_version_mismatch_warnings
        self.assertFalse(suppress)
        self.c1.suppress_version_mismatch_warnings = True
        suppress = self.c1.suppress_version_mismatch_warnings
        self.assertTrue(suppress)
        self.c1.suppress_version_mismatch_warnings = False

    def test_get_config(self):
        """Test that we get config object CfgQmi correctly."""
        # Arrange
        expected_config_file = self.config_file
        expected_log_dir = self.log_dir
        expected_home_dir = self.qmi_home
        expected_workgroup = "default"
        expected_context = {"c1": CfgContext(tcp_server_port=0)}
        expected_datastore = self.datastore_dir
        # Act
        config = self.c1.get_config()
        # Assert
        self.assertEqual(expected_config_file, config.config_file)
        self.assertEqual(expected_log_dir, config.log_dir)
        self.assertEqual(expected_home_dir, config.qmi_home)
        self.assertEqual(expected_workgroup, config.workgroup)
        self.assertEqual(expected_context, config.contexts)
        self.assertEqual(expected_datastore, config.datastore)

    def test_get_context_config(self):
        """Test that we get config context object CfgContext correctly."""
        # Arrange
        expected_context = CfgContext(tcp_server_port=0)
        # Act
        context = self.c2.get_context_config()
        # Assert
        self.assertEqual(expected_context, context)

    def test_get_qmi_home_dir(self):
        """Get the QMI home directory set in config and assert it is correct."""
        # Arrange
        expected_home = self.qmi_home
        # Act
        qmi_home = self.c1.get_qmi_home_dir()
        # Assert
        self.assertEqual(expected_home, qmi_home)

    def test_get_qmi_home_dir_default(self):
        """Get the QMI home directory reading it from environment variable 'QMI_HOME'."""
        # Arrange
        expected_home = os.path.expanduser("~")
        # Act
        qmi_home = self.c2.get_qmi_home_dir()
        # Assert
        self.assertEqual(expected_home, qmi_home)

    def test_get_log_dir(self):
        """Get the log directory set in config and assert it is correct."""
        # Arrange
        expected_log_dir = self.log_dir
        # Act
        log_dir = self.c1.get_log_dir()
        # Assert
        self.assertEqual(expected_log_dir, log_dir)

    def test_get_log_dir_default(self):
        """Get the log directory reading it from environment variable 'QMI_HOME'."""
        # Arrange
        expected_log_dir = os.path.expanduser("~")
        # Act
        log_dir = self.c2.get_log_dir()
        # Assert
        self.assertEqual(expected_log_dir, log_dir)

    def test_get_datastore_dir(self):
        """Try to get datastore directory from the config."""
        # Arrange
        expected_dir = self.datastore_dir
        # Act
        datastore_dir = self.c1.get_datastore_dir()
        # Assert
        self.assertEqual(expected_dir, datastore_dir)

    def test_get_datastore_dir_raises_exception(self):
        """Try to get datastore directory from the config, but it is not defined there, raising exception."""
        with self.assertRaises(QMI_ConfigurationException):
            self.c2.get_datastore_dir()

    def test_resolve_file_name(self):
        """Test that file name substitutions work for all configured file names. Names to be substituted are:
          $$            -> "$"
          ${context}    -> context name
          ${qmi_home}   -> QMI home directory
          ${datastore}  -> QMI datastore directory
          ${config_dir} -> directory of QMI configuration file
          ${date}       -> date of program start, UTC, formatted as YYYY-mm-dd
          ${datetime}   -> time of program start, UTC, formatted as YYYY-mm-ddTHH-MM-SS
        """
        # Test 1. File name not in substitutions list -> returns the input name as-is.
        expected_conf_file = "qmi.conf"
        resolved_name = self.c1.resolve_file_name("qmi.conf")
        self.assertEqual(expected_conf_file, resolved_name)
        # Test 2. Double dollar into one
        expected_name = "$"
        resolved_name = self.c1.resolve_file_name("$$")
        self.assertEqual(expected_name, resolved_name)
        # Test 3. Context name
        expected_context = "c1"
        resolved_name = self.c1.resolve_file_name("$context")
        self.assertEqual(expected_context, resolved_name)
        # Test 4. QMI home directory
        expected_directory = self.qmi_home
        resolved_name = self.c1.resolve_file_name("$qmi_home")
        self.assertEqual(expected_directory, resolved_name)
        # Test 5. Datastore directory
        expected_directory = self.datastore_dir
        resolved_name = self.c1.resolve_file_name("$datastore")
        self.assertEqual(expected_directory, resolved_name)
        # Test 6. Configuration file directory
        expected_directory = os.path.split(self.config_file)[0]
        resolved_name = self.c1.resolve_file_name("$config_dir")
        self.assertEqual(expected_directory, resolved_name)
        # Test 7. Date of program start
        gmtime = time.gmtime(self.c1._start_time)
        date = time.strftime("%Y-%m-%d", gmtime)
        resolved_name = self.c1.resolve_file_name("$date")
        self.assertEqual(date, resolved_name)
        # Test 8. Time of program start
        datetime = time.strftime("%Y-%m-%dT%H-%M-%S", gmtime)
        resolved_name = self.c1.resolve_file_name("$datetime")
        self.assertEqual(datetime, resolved_name)

    def test_resolve_without_datastore(self):
        """Test file name substitution when no datastore is configured."""

        resolved_name = self.c2.resolve_file_name("qmi.conf")
        self.assertEqual(resolved_name, "qmi.conf")

        resolved_name = self.c2.resolve_file_name("$context")
        self.assertEqual(resolved_name, "c2")

        with self.assertRaises(QMI_ConfigurationException):
            resolved_name = self.c2.resolve_file_name("$datastore")

    def test_resolve_datastore(self):
        """Test resolving file name substitution in the datastore path."""

        cfg = CfgQmi(
            contexts={"ctx_tmp": CfgContext(tcp_server_port=0)},
            log_dir=self.log_dir,
            qmi_home=self.qmi_home,
            datastore="${qmi_home}/datastore",
            config_file=self.config_file)

        ctx_tmp = QMI_Context("ctx_tmp", cfg)
        ctx_tmp.start()
        datastore_dir = ctx_tmp.get_datastore_dir()
        ctx_tmp.stop()
        self.assertEqual(datastore_dir, os.path.join(self.qmi_home, "datastore"))

    def test_resolve_recursive_datastore(self):
        """Test an attempt to recursively define the datastore path."""
        cfg = CfgQmi(
            contexts={"ctx_tmp": CfgContext(tcp_server_port=0)},
            log_dir=self.log_dir,
            qmi_home=self.qmi_home,
            datastore="${datastore}/datastore",
            config_file=self.config_file)

        ctx_tmp = QMI_Context("ctx_tmp", cfg)
        ctx_tmp.start()
        with self.assertRaises(QMI_ConfigurationException):
            datastore_dir = ctx_tmp.get_datastore_dir()
        ctx_tmp.stop()

    def test_list_rpc_objects(self):
        # Arrange
        expected_list_rpc_objects = [('c1.$context', '_ContextRpcObject'), ('c2.$context', '_ContextRpcObject')]
        # Act
        list_rpc_objects1 = self.c1.list_rpc_objects()
        list_rpc_objects2 = self.c2.list_rpc_objects()
        # Assert
        self.assertListEqual(expected_list_rpc_objects, list_rpc_objects1 + list_rpc_objects2)

    def test_shutdown_requested(self):
        requested = self.c1.shutdown_requested()
        self.assertFalse(requested)

    def test_wait_until_shutdown(self):
        shutdown = self.c1.wait_until_shutdown(0.01)
        self.assertFalse(shutdown)

    def test_double_start_excepts(self):
        with self.assertRaises(QMI_UsageException) as exc:
            self.c1.start()

        self.assertEqual("QMI_Context already started", str(exc.exception))

    def test_double_stop_excepts(self):
        self.c1.stop()
        with self.assertRaises(QMI_UsageException) as exc:
            self.c1.stop()

        self.assertEqual("QMI_Context already inactive", str(exc.exception))


if __name__ == '__main__':
    unittest.main()
