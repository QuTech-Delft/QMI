import unittest
import unittest.mock
import sys
import logging
from collections import namedtuple
from time import monotonic, sleep

import qmi.core.logging_init
from qmi.core.logging_init import start_logging, _RateLimitFilter, _log_excepthook


class TestStartLoggingOptions(unittest.TestCase):

    def setUp(self):
        qmi.core.logging_init._file_handler = None

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_default(self, logging_patch):
        """Test that a logger is created with default options."""
        # Arrange
        qmi.core.logging_init._file_handler = unittest.mock.MagicMock()
        # Act
        start_logging()
        # Assert
        logging_patch.getLogger.assert_has_calls([unittest.mock.call().setLevel(logging.INFO)], any_order=True)
        self.assertEqual(2, logging_patch.getLogger.call_count)

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        logging_patch.basicConfig.assert_called_once()

        logging_patch.handlers.WatchedFileHandler.assert_not_called()
        logging_patch.getLogger().addHandler.assert_not_called()

        logging_patch.captureWarnings.assert_called_with(True)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_logfile_loglevels_inputs(self, logging_patch):
        """Test that a logfile is created with loglevel input options."""
        # Arrange
        logfile = "log.file"
        loglevels = {
            "logger1": logging.CRITICAL,
            "logger2": logging.DEBUG
        }
        # Act
        start_logging(logfile=logfile, loglevels=loglevels)
        # Assert
        self.assertEqual(4, logging_patch.getLogger.call_count)
        logging_patch.getLogger.assert_has_calls([
            unittest.mock.call(), unittest.mock.call().setLevel(logging.INFO),
            unittest.mock.call("logger1"), unittest.mock.call("logger2"),
            unittest.mock.call("logger1").setLevel(logging.CRITICAL),
            unittest.mock.call("logger2").setLevel(logging.DEBUG),

        ], any_order=True)

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        logging_patch.basicConfig.assert_called_once()

        logging_patch.handlers.WatchedFileHandler.assert_called_once_with(logfile)
        logging_patch.getLogger().addHandler.assert_called_once()

        logging_patch.captureWarnings.assert_called_with(True)

    @unittest.mock.patch("qmi.core.logging_init.logging")
    def test_logging_rate_limit(self, logging_patch):
        """Test that a logger is created with default options."""
        # Arrange
        logfile = "log.file"
        rate_limit = 5
        burst_limit = 20
        # Act
        with unittest.mock.patch("qmi.core.logging_init.sys") as sys_patch, unittest.mock.patch(
            "qmi.core.logging_init._RateLimitFilter") as rlf_patch:
            sys_patch.excepthook = None
            sys_patch.warnoptions = False
            start_logging(logfile=logfile, rate_limit=rate_limit, burst_limit=burst_limit)

        # Assert
        self.assertEqual(2, logging_patch.getLogger.call_count)
        logging_patch.getLogger.assert_has_calls([unittest.mock.call(), unittest.mock.call().setLevel(logging.INFO)])

        logging_patch.StreamHandler.assert_called_once()
        logging_patch.StreamHandler.assert_has_calls([unittest.mock.call().setLevel(logging.WARNING)])

        logging_patch.basicConfig.assert_called_once()

        logging_patch.handlers.WatchedFileHandler.assert_called_once_with(logfile)
        logging_patch.getLogger().addHandler.assert_called_once()

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
            start_logging(1, 2, 3, 4, 5, 6, 7)

        # Test excepthook with the above exception
        sys_patch.excepthook(TypeError, terr.exception, terr)
        # Assert
        assert unittest.mock.call.Logger("exception") in logging_patch.method_calls
        logging_patch.assert_has_calls([unittest.mock.call.Logger("exception")])


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
        exp_record = {(name, levelno): (round(monotonic() + 1, 1), exp_bucket_level, exp_disc_msgs)}

        filter_obj = _RateLimitFilter(rate_limit, burst_limit)
        filter_obj._counters = {(name, levelno): None}
        # Act
        res1 = filter_obj.filter(self._record(name, levelno))
        sleep(1)  # sleep to make (time_now - last_time) larger
        res2 = filter_obj.filter(self._record(name, levelno))
        values = filter_obj._counters[(name, levelno)]
        rounded_filter_obj = {
            (name, levelno): (round(values[0], 1), round(values[1]), values[2])
        }

        # Assert
        self.assertTrue(res1)
        self.assertTrue(res2)
        self.assertDictEqual(exp_record, rounded_filter_obj)


if __name__ == '__main__':
    unittest.main()
