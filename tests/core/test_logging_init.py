import os
import unittest
import unittest.mock
import sys
import logging
from collections import namedtuple
from time import monotonic, sleep

import qmi.core.logging_init
from qmi.core.logging_init import start_logging, stop_logging, WatchedRotatingFileHandler, _RateLimitFilter, \
    _log_excepthook


class TestStartLoggingOptions(unittest.TestCase):

    def setUp(self):
        qmi.core.logging_init._file_handler = None
        qmi.core.logging_init._console_handler = None
        self.logfile = "log.file"
        self.log_dir = ""

    def tearDown(self):
        logging.shutdown()  # Close all log files
        path_1 = os.path.dirname(os.path.abspath(__file__))
        path_2 = os.getcwd()
        path_3 = self.log_dir
        # Delete all log files from all possible locations in these tests
        for p in [path_1, path_2, path_3]:
            files = os.listdir(p) if p else []
            for f in files:
                if f.startswith(self.logfile):
                    os.remove(os.path.join(p, f))

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_default(self, logging_patch):
        """Test that a logger is created with default options."""
        # Arrange
        qmi.core.logging_init._file_handler = unittest.mock.MagicMock()
        # Act
        start_logging()
        # Assert
        logging_patch.getLogger.assert_has_calls([unittest.mock.call().setLevel(logging.INFO)], any_order=True)
        # 3 calls: _remove_handlers() removeHandler on the old file handler, setLevel(), and addHandler()
        # for the new console handler.
        self.assertEqual(3, logging_patch.getLogger.call_count)

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        # basicConfig() is no longer used: the console handler is added explicitly instead.
        logging_patch.basicConfig.assert_not_called()
        logging_patch.getLogger().addHandler.assert_called_once_with(qmi.core.logging_init._console_handler)

        logging_patch.handlers.WatchedRotatingFileHandler.assert_not_called()

        logging_patch.captureWarnings.assert_called_with(True)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_logfile_loglevels_inputs(self, logging_patch):
        """Test that a logfile is created with loglevel input options."""
        # Arrange
        method_inputs = list(start_logging.__annotations__.keys())
        expected_max_bytes = start_logging.__defaults__[method_inputs.index("max_bytes")]
        expected_backup_count = start_logging.__defaults__[method_inputs.index("backup_count")]
        # Note that the logfile is supposed to be given as relative to the log_dir directory. In the absence
        # of that, it is relative to the `QMI_HOME` env directory, or as last option, the user's home directory.
        log_dir = os.path.expanduser("~")
        logfile = os.path.join(log_dir, self.logfile)
        loglevels = {
            "logger1": logging.CRITICAL,
            "logger2": logging.DEBUG
        }
        # Act
        start_logging(logfile=logfile, loglevels=loglevels)
        # Assert
        # 5 calls: setLevel(), addHandler() for the console handler, addHandler() for the file handler,
        # and setLevel() for each of the two loggers in `loglevels`.
        self.assertEqual(5, logging_patch.getLogger.call_count)
        logging_patch.getLogger.assert_has_calls([
            unittest.mock.call(), unittest.mock.call().setLevel(logging.INFO),
            unittest.mock.call("logger1"), unittest.mock.call("logger2"),
            unittest.mock.call("logger1").setLevel(logging.CRITICAL),
            unittest.mock.call("logger2").setLevel(logging.DEBUG),
        ], any_order=True)

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        # basicConfig() is no longer used: the console handler is added explicitly instead.
        logging_patch.basicConfig.assert_not_called()

        self.assertIsInstance(qmi.core.logging_init._file_handler, WatchedRotatingFileHandler)
        self.assertTrue(qmi.core.logging_init._file_handler.baseFilename.endswith(self.logfile))
        self.assertEqual(expected_max_bytes, qmi.core.logging_init._file_handler.maxBytes)
        self.assertEqual(expected_backup_count, qmi.core.logging_init._file_handler.backupCount)
        # Console handler and file handler are both added explicitly.
        logging_patch.getLogger().addHandler.assert_has_calls([
            unittest.mock.call(qmi.core.logging_init._console_handler),
            unittest.mock.call(qmi.core.logging_init._file_handler),
        ], any_order=True)
        self.assertEqual(2, logging_patch.getLogger().addHandler.call_count)

        logging_patch.captureWarnings.assert_called_with(True)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_rate_limit(self, logging_patch):
        """Test that a logger is created with default options."""
        # Arrange
        # Note that the logfile is supposed to be given as relative to the log_dir directory. In the absence
        # of that, it is relative to the `QMI_HOME` env directory, or as last option, the user's home directory.
        log_dir = os.path.expanduser("~")
        logfile = os.path.join(log_dir, self.logfile)
        rate_limit = 20
        burst_limit = 5
        # Act
        with unittest.mock.patch("qmi.core.logging_init.sys") as sys_patch, unittest.mock.patch(
            "qmi.core.logging_init._RateLimitFilter") as rlf_patch:
            sys_patch.excepthook = None
            sys_patch.warnoptions = False
            start_logging(logfile=logfile, rate_limit=rate_limit, burst_limit=burst_limit)

        # Assert
        # 3 calls: setLevel(), addHandler() for the console handler, and addHandler() for the file handler.
        self.assertEqual(3, logging_patch.getLogger.call_count)
        logging_patch.getLogger.assert_has_calls([unittest.mock.call(), unittest.mock.call().setLevel(logging.INFO)])

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        # basicConfig() is no longer used: the console handler is added explicitly instead.
        logging_patch.basicConfig.assert_not_called()

        self.assertIsInstance(qmi.core.logging_init._file_handler, WatchedRotatingFileHandler)
        self.assertEqual(2, logging_patch.getLogger().addHandler.call_count)

        rlf_patch.assert_called_once_with(rate_limit, burst_limit)

        logging_patch.captureWarnings.assert_called_with(True)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_max_bytes_backup_count(self, logging_patch):
        """Test that a logger is created with default options."""
        # Arrange
        # Note that the logfile is supposed to be given as relative to the log_dir directory. In the absence
        # of that, it is relative to the `QMI_HOME` env directory, or as last option, the user's home directory.
        log_dir = os.path.expanduser("~")
        logfile = os.path.join(log_dir, self.logfile)
        rate_limit = 5
        burst_limit = 20
        # Act
        with unittest.mock.patch("qmi.core.logging_init.sys") as sys_patch, unittest.mock.patch(
            "qmi.core.logging_init._RateLimitFilter") as rlf_patch:
            sys_patch.excepthook = None
            sys_patch.warnoptions = False
            start_logging(logfile=logfile, rate_limit=rate_limit, burst_limit=burst_limit)

        # Assert
        # 3 calls: setLevel(), addHandler() for the console handler, and addHandler() for the file handler.
        self.assertEqual(3, logging_patch.getLogger.call_count)
        logging_patch.getLogger.assert_has_calls([unittest.mock.call(), unittest.mock.call().setLevel(logging.INFO)])

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        # basicConfig() is no longer used: the console handler is added explicitly instead.
        logging_patch.basicConfig.assert_not_called()

        self.assertIsInstance(qmi.core.logging_init._file_handler, WatchedRotatingFileHandler)
        self.assertEqual(2, logging_patch.getLogger().addHandler.call_count)

        rlf_patch.assert_called_once_with(rate_limit, burst_limit)

        logging_patch.captureWarnings.assert_called_with(True)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    @unittest.mock.patch("qmi.core.logging_init.sys", autospec=sys)
    def test_log_excepthook(self, sys_patch, logging_patch):
        """Test that an excepthook is set and can be called with and exception."""
        # Arrange
        qmi.core.logging_init._saved_except_hook = None
        sys_patch.excepthook = None
        # set the excepthook
        start_logging()
        # Act
        self.assertEqual(_log_excepthook, sys_patch.excepthook)
        with self.assertRaises(TypeError) as terr:
            qmi.core.logging_init._saved_except_hook = unittest.mock.MagicMock()
            qmi.core.logging_init._file_handler = unittest.mock.MagicMock()
            # Cause exception.
            start_logging(1, 2, 3, 4, 5, 6, 7, 8, 9)

        # Test excepthook with the above exception
        sys_patch.excepthook(TypeError, terr.exception, terr)
        # Assert
        assert unittest.mock.call.Logger("exception") in logging_patch.method_calls
        logging_patch.assert_has_calls([unittest.mock.call.Logger("exception")])

    def test_log_rotation_small(self):
        """Test that log rotation works with given input values."""
        # Arrange
        max_log_size = 100  # bytes
        backups = 3
        # Note that the logfile is supposed to be given as relative to the log_dir directory. In the absence
        # of that, it is relative to the `QMI_HOME` env directory, or as last option, the user's home directory.
        log_dir = os.path.expanduser("~")
        logfile = os.path.join(log_dir, self.logfile)
        # clear the root logger (small log files seem to be an issue here) and set the logger
        logger = logging.getLogger()
        logger.handlers.clear()
        del logger
        start_logging(logfile=logfile, max_bytes=max_log_size, backup_count=backups)
        logger = logging.getLogger("qmi.core.logging_init")
        # The logging might be set to level NOTSET to avoid excess printouts, polluting the unit-test
        # view. "Force" the log level to be INFO for this logger.
        logger.setLevel(logging.INFO)
        logger.manager.disable = logging.DEBUG  # allows log levels above DEBUG
        self.log_dir = os.path.split(logger.root.handlers[1].baseFilename)[0]
        # Act
        logger.info("Start log")
        logger.info("Writing some stuff into log file.2.")
        logger.info("Writing some stuff into log file.1.")
        logger.info("Writing some stuff into log.")
        log_files = [l for l in os.listdir(
            self.log_dir
        ) if l.startswith(self.logfile)]
        logger.setLevel(logging.NOTSET)
        logger.manager.disable = logging.CRITICAL
        # Assert
        self.assertEqual(backups + 1, len(log_files))
        size_total = 0
        # See that the total file size stays contained
        # NOTE: It seems that the size limit is not strict: if a line is longer than the log size limit in bytes,
        # The file size can still be larger than the limit. The rotation then starts from next write.
        for lf in log_files:
            size_total += os.path.getsize(os.path.join(self.log_dir, lf))

        self.assertLessEqual(size_total, max_log_size * (backups + 1))

        # See also that writing more logs do not increase number of log files or total size.
        logger.info("Continue log")
        logger.info("Writing more stuff into log file.4.")
        logger.info("Writing more stuff into log file.5.")
        logger.info("Writing more stuff into log.")

        log_files = [l for l in os.listdir(
            self.log_dir
        ) if l.startswith(self.logfile)]
        self.assertEqual(backups + 1, len(log_files))
        size_total = 0
        # See that the total file size stays contained
        # NOTE: It seems that the size limit is not strict: if a line is longer than the log size limit in bytes,
        # The file size can still be larger than the limit. The rotation then starts from next write.
        for lf in log_files:
            size_total += os.path.getsize(os.path.join(self.log_dir, lf))

        self.assertLessEqual(size_total, max_log_size * (backups + 1))

    def test_log_rotation_big(self):
        """Test that log rotation works with given input values."""
        # Arrange
        max_log_size = 10000  # bytes
        backups = 3
        # Note that the logfile is supposed to be given as relative to the log_dir directory. In the absence
        # of that, it is relative to the `QMI_HOME` env directory, or as last option, the user's home directory.
        log_dir = os.path.expanduser("~")
        logfile = os.path.join(log_dir, self.logfile)
        # clear the root logger (small log files seem to be an issue here) and set the logger
        logger = logging.getLogger()
        logger.handlers.clear()
        del logger
        # set the logger
        start_logging(logfile=logfile, max_bytes=max_log_size, backup_count=backups)
        logger = logging.getLogger("qmi.core.logging_init")
        # The logging might be set to level NOTSET to avoid excess printouts, polluting the unit-test
        # view. "Force" the log level to be INFO for this logger.
        logger.setLevel(logging.INFO)
        logger.manager.disable = logging.DEBUG
        self.log_dir = os.path.split(logger.root.handlers[1].baseFilename)[0]
        # Act
        for i in range(100):
            logger.info(f"Start log {i}")
            logger.info(f"Writing some stuff into log file.{i+1}.")
            logger.info(f"Writing some stuff into log file.{i+2}.")
            logger.info(f"Writing some stuff into log {i}.")

        log_files = [l for l in os.listdir(
            self.log_dir
        ) if l.startswith(self.logfile)]
        logger.setLevel(logging.NOTSET)
        logger.manager.disable = logging.CRITICAL
        # Assert
        self.assertEqual(backups + 1, len(log_files))
        size_total = 0
        # See that the total file size stays contained
        # NOTE: It seems that the size limit is not strict: if a line is longer than the log size limit in bytes,
        # The file size can still be larger than the limit. The rotation then starts from next write.
        for lf in log_files:
            size_total += os.path.getsize(os.path.join(self.log_dir, lf))

        self.assertLessEqual(size_total, max_log_size * (backups + 1))


class TestStartStopLogging(unittest.TestCase):
    """Test start_logging()/stop_logging() against the real logging module, without mocking.

    These tests confirm the behaviour requested in issue #237: a second call to start_logging() must replace
    the console handler (and thus apply a new console_loglevel) instead of being silently ignored, and
    stop_logging() must undo everything start_logging() set up.
    """

    def setUp(self):
        qmi.core.logging_init._file_handler = None
        qmi.core.logging_init._console_handler = None
        self._original_except_hook = sys.excepthook

    def tearDown(self):
        stop_logging()
        logging.shutdown()
        sys.excepthook = self._original_except_hook
        qmi.core.logging_init._saved_except_hook = None

    def _qmi_console_handlers(self):
        return [
            hdlr for hdlr in logging.getLogger().handlers
            if hdlr is qmi.core.logging_init._console_handler
        ]

    def test_second_start_logging_replaces_console_handler(self):
        """A second call to start_logging() with a different console_loglevel must take effect."""
        # Act
        start_logging(console_loglevel=logging.WARNING)
        first_handler = qmi.core.logging_init._console_handler
        start_logging(console_loglevel=logging.DEBUG)
        second_handler = qmi.core.logging_init._console_handler

        # Assert: exactly one QMI console handler remains, and it is the newest one.
        self.assertIsNot(first_handler, second_handler)
        self.assertEqual([second_handler], self._qmi_console_handlers())
        self.assertEqual(logging.DEBUG, second_handler.level)

    def test_stop_logging_removes_handlers_and_restores_excepthook(self):
        """stop_logging() removes the QMI handlers and restores the original excepthook."""
        # Arrange
        logfile = os.path.join(os.path.expanduser("~"), "stop_logging_test.log")
        original_hook = sys.excepthook
        # Act
        start_logging(logfile=logfile)
        console_handler = qmi.core.logging_init._console_handler
        file_handler = qmi.core.logging_init._file_handler
        self.assertIn(console_handler, logging.getLogger().handlers)
        self.assertIn(file_handler, logging.getLogger().handlers)

        stop_logging()

        # Assert
        self.assertNotIn(console_handler, logging.getLogger().handlers)
        self.assertNotIn(file_handler, logging.getLogger().handlers)
        self.assertIsNone(qmi.core.logging_init._console_handler)
        self.assertIsNone(qmi.core.logging_init._file_handler)
        self.assertIs(original_hook, sys.excepthook)
        self.assertIsNone(qmi.core.logging_init._saved_except_hook)

        if os.path.isfile(logfile):  # The handler uses delay=True, so the file may not have been created.
            os.remove(logfile)

    def test_stop_logging_does_not_remove_user_handlers(self):
        """stop_logging() must only remove QMI's own handlers, not ones added by a user."""
        # Arrange
        user_handler = logging.StreamHandler()
        logging.getLogger().addHandler(user_handler)
        try:
            start_logging()
            # Act
            stop_logging()
            # Assert
            self.assertIn(user_handler, logging.getLogger().handlers)
        finally:
            logging.getLogger().removeHandler(user_handler)
            user_handler.close()


class Test_RateLimitFilter(unittest.TestCase):

    def _record(self, name, levelno):
        Record = namedtuple("Record", ["name", "levelno"])
        return Record(name, levelno)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_filter(self, logging_patch):
        """Test filter function and counter_data"""
        # Arrange
        rate_limit = 5
        burst_limit = 20
        name = "record_name"
        levelno = 5
        bucket_level = 0
        discarded_msgs = 1
        exp_bucket_level = float(bucket_level + rate_limit - 1)
        exp_disc_msgs = discarded_msgs + 1
        exp_record = {(name, levelno): (round(monotonic() + 1, 1), exp_bucket_level, exp_disc_msgs)}

        filter_obj = _RateLimitFilter(rate_limit, burst_limit)
        filter_obj._counters = {
            (name, levelno): (monotonic(), bucket_level, discarded_msgs)
        }
        # Act
        res1 = filter_obj.filter(self._record(name, levelno))
        sleep(1)  # sleep to make (time_now - last_time) larger
        res2 = filter_obj.filter(self._record(name, levelno))
        values = filter_obj._counters[(name, levelno)]
        rounded_filter_obj = {
            (name, levelno): (round(values[0], 1), round(values[1]), values[2])
        }

        # Assert
        self.assertFalse(res1)
        self.assertTrue(res2)
        self.assertDictEqual(exp_record, rounded_filter_obj)

    def test_filter_no_counter_data(self):
        """Test case where gotten counter_data is None."""
        # Arrange
        rate_limit = 5
        burst_limit = 20
        name = "record_name"
        levelno = 5
        exp_bucket_level = float(burst_limit - 1)
        exp_disc_msgs = 0
        round_up = (monotonic() + 1) * -10 // 1 * -1 / 10  # (-)10 for 1 decimal
        exp_record = {(name, levelno): (round_up, exp_bucket_level, exp_disc_msgs)}

        filter_obj = _RateLimitFilter(rate_limit, burst_limit)
        filter_obj._counters = {(name, levelno): None}
        # Act
        res1 = filter_obj.filter(self._record(name, levelno))
        sleep(1)  # sleep to make (time_now - last_time) larger
        res2 = filter_obj.filter(self._record(name, levelno))
        values = filter_obj._counters[(name, levelno)]
        rounded_filter_obj = {
            (name, levelno): (values[0] * -10 // 1 * -1 / 10, round(values[1]), values[2])
        }

        # Assert
        self.assertTrue(res1)
        self.assertTrue(res2)
        self.assertDictEqual(exp_record, rounded_filter_obj)


if __name__ == '__main__':
    unittest.main()
