"""Initialization of the Python logging framework for QMI.

Logging framework can be configured using the "logging" and "log_dir" sections of the QMI configuration file, e.g.:

```json
{
    # Log level for messages to the console.
    "logging": {
        "console_loglevel": "DEBUG",
        "logfile": "debug.log",
        "loglevels": {
            "qmi.core.rpc": "ERROR",
            "qmi.core.task": "ERROR"
        },
        "max_bytes": 1000000,
        "backup_count": 2
    },
    # Directory to write various log files.
    "log_dir": "${qmi_home}/log_dir",

    "contexts": ...
}
```
to show DEBUG info on the console, and to write into max three log files (the latest log and two backups) of max size
of 1MB. The location of the log file named 'debug.log' is in 'log_dir' folder of the QMI home directory.  The loglevel
setting is overridden with module-specific settings, for modules `qmi.core.rpc` and `qmi.core.task`, to be "ERROR".

The default [`log levels`](https://docs.python.org/3/library/logging.html#logging-levels) for QMI are "INFO" for the
log file and "WARNING" for the console. The standard log file name is 'qmi.log'.
"""
import os.path
import sys
import logging
import logging.handlers
import threading
import time
import warnings

from collections.abc import Callable, Mapping
from types import TracebackType


# Global variable holding the file log handler (if any).
_file_handler: logging.FileHandler | None = None

# Global variable holding the saved exception hook.
_saved_except_hook: Callable | None = None


class _RateLimitFilter(logging.Filter):
    """Rate limiting of log messages.

    Rate limiting can be used to prevent excessive amounts of repeated log messages filling up the disk.

    The rate limits are tracked separately per logger and per log level.
    Conceptually, each combination of logger and log level has an associated `token bucket`.
    When a message is logged, one token is taken out of the bucket.
    The bucket then gets refilled at a steady rate until it is full again.
    When the bucket becomes empty, log messages are dropped until the bucket is sufficiently refilled.
    """

    def __init__(self, rate_limit: float, burst_limit: int = 1) -> None:
        """Initialize a rate limiting log filter.

        Parameters:
            rate_limit:  Maximum number of log messages per second.
            burst_limit: Maximum number of messages that can be "saved up" for a short burst of messages.
                         This must be at least 1.
        """
        super().__init__("")
        self._rate_limit = rate_limit
        self._burst_limit = burst_limit
        self._lock = threading.Lock()

        # _counters is used to track the token bucket state for each
        # combination of logger and log level:
        #    self._counters[(logger_name, log_level)] returns a tuple
        #      (last_update_time, bucket_level, nr_discarded_messages)
        self._counters: dict[tuple[str, int], tuple[float, float, int]] = {}

    def filter(self, record: logging.LogRecord) -> bool:

        time_now = time.monotonic()

        with self._lock:
            # Get counter record for this combination of logger and log level.
            key = (record.name, record.levelno)
            counter_data = self._counters.get(key)

            if counter_data is not None:
                # Update the bucket level.
                # Refill the bucket by (rate_limit * elapsed_time) tokens,
                # but never more than the burst limit.
                (last_time, bucket_level, messages_discarded) = counter_data
                bucket_level += self._rate_limit * (time_now - last_time)
                bucket_level = min(bucket_level, self._burst_limit)
            else:
                # First use. Initialize the bucket level to the to burst limit.
                bucket_level = self._burst_limit
                messages_discarded = 0

            if bucket_level < 1:
                # Discard this message.
                messages_discarded += 1
                ret = False
            else:
                # Allow this message.
                bucket_level -= 1.0
                ret = True

            # Store updated counter record.
            self._counters[key] = (time_now, bucket_level, messages_discarded)

        return ret


class WatchedRotatingFileHandler(logging.handlers.RotatingFileHandler, logging.handlers.WatchedFileHandler):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        self.dev, self.ino = -1, -1
        self._statstream()
        self._basedir = os.path.split(self.baseFilename)[0]

    def emit(self, record):
        self.reopenIfNeeded()  # WatchedFileHandler, makes sure the log file will be present.
        if not os.path.isdir(self._basedir):  # Prevents errors if directory is also removed by chance.
            os.makedirs(self._basedir)

        super().emit(record)  # RotatingFileHandler, handles the log file rotation if log file full.


def _makeLogFormatter(log_process: bool) -> logging.Formatter:
    """Create and return a log formatter instance."""

    if log_process:
        format_spec = "%(asctime)-23s | %(process)5d | %(levelname)-8s | %(name)-22s | %(message)s"
    else:
        format_spec = "%(asctime)-23s | %(levelname)-8s | %(name)-22s | %(message)s"

    fmt = logging.Formatter(format_spec)

    # Override default timezone and time format.
    fmt.converter = time.gmtime  # type: ignore
    fmt.default_msec_format = "%s.%03d"

    return fmt


def start_logging(
    loglevel: int | str = logging.INFO,
    console_loglevel: int | str = logging.WARNING,
    logfile: str | None = None,
    loglevels: Mapping[str, int | str] | None = None,
    rate_limit: float | None = None,
    burst_limit: int = 1,
    max_bytes: int = 10 * 2**30,
    backup_count: int = 5
) -> None:
    """Initialize the Python logging framework for use by QMI.

    This function sets up logging to `stderr` and optional logging to a file. The maximum size
    of a logfile can be given, and the number of rotating logfile count as well. The maximum total
    logfile disk space usage will be max_bytes * backup_count.
    Logging of Python *warnings* is enabled.
    Unhandled exceptions are logged to file.

    This function is normally called automatically by ``qmi.start()``.

    Parameters:
        loglevel:         Default log level (level of the root logger).
                          Only log messages with at least this priority will be processed.
        console_loglevel: Log level for logging to console.
                          Only log messages with at least this priority will be logged to screen.
        logfile:          Optional file name of the log file.
                          When omitted, logging to file will be disabled.
        loglevels:        Optional initial log levels for specific loggers.
                          When specified, this is a dictionary mapping logger names to their initial log levels.
        rate_limit:       Maximum number of log messages per second per logger.
        burst_limit:      Maximum number of messages that can be "saved up" for a short burst of messages.
        max_bytes:        Maximum size of a log file in bytes. Default is 10GB = 10 * 2**30.
        backup_count:     Number of backup files to be used. Default is 5.
    """

    global _file_handler
    global _saved_except_hook

    # If there is still an old file log handler, remove it.
    if _file_handler is not None:
        logging.getLogger().removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None

    # Set log level of the root logger.
    logging.getLogger().setLevel(loglevel)

    # Set basic configuration: logging to stderr.
    hdlr = logging.StreamHandler()
    fmt = _makeLogFormatter(log_process=False)
    hdlr.setFormatter(fmt)
    hdlr.setLevel(console_loglevel)
    logging.basicConfig(handlers=[hdlr])

    # Create log file handler.
    # This must be done as a separate step (separate from basicConfig())
    # because basicConfig() ignores subsequent calls once logging is configured.
    # However, we must support the case where logging is configured during
    # early initialization via QMI_DEBUG, then later re-configured to add
    # a log file after the configuration is processed.
    if logfile:
        # Use the custom WatchedRotatingFileHandler class for logging to file[s].
        # This handler will automatically create or re-open the log file if the underlying
        # file is removed, renamed or reached its maximum size, for example as part of log rotation.
        _file_handler = WatchedRotatingFileHandler(logfile, delay=True, maxBytes=max_bytes, backupCount=backup_count)
        fmt = _makeLogFormatter(log_process=True)
        _file_handler.setFormatter(fmt)
        # Configure rate limiting.
        if rate_limit is not None:
            _file_handler.addFilter(_RateLimitFilter(rate_limit, burst_limit))
        logging.getLogger().addHandler(_file_handler)

    # Set log levels of specific loggers.
    if loglevels:
        for (k, v) in loglevels.items():
            logging.getLogger(k).setLevel(v)

    # Set hook to log uncaught exceptions.
    if _saved_except_hook is None:
        _saved_except_hook = sys.excepthook
        sys.excepthook = _log_excepthook

    # Redirect warnings through the logging system.
    logging.captureWarnings(True)

    # By default, the Python interpreter disables many types of warnings.
    # We change that here, unless explicit warning options have been specified via "python -W ...".
    if not sys.warnoptions:
        # Enable all warnings but log only the first occurrence.
        warnings.simplefilter("default")


def _log_excepthook(
    type_: type[BaseException],
    value: BaseException,
    traceback: TracebackType | None = None
) -> None:
    """Called when an uncaught exception occurs.

    This function logs the exception to the QMI log file (if any),
    then calls the original exception hook to display the exception
    on screen.
    """

    assert traceback is not None
    # Call the original excepthook to display the exception on screen.
    assert _saved_except_hook is not None
    _saved_except_hook(type_, value, traceback)

    # Log the exception to file.
    hdlr = _file_handler
    if hdlr is not None:
        # Create temporary logger which logs only to file (not to screen).
        logger = logging.Logger("exception")
        logger.addHandler(hdlr)
        # Log the exception.
        logger.error("%s: %s", type_.__name__, value, exc_info=(type_, value, traceback))
