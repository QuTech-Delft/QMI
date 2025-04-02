"""Initialization of the Python logging framework for QMI."""

import sys
import logging
import logging.handlers
import threading
import time
import warnings

from types import TracebackType
from typing import Dict, Callable, Mapping, Optional, Tuple, Type, Union


# Global variable holding the file log handler (if any).
_file_handler: Optional[logging.FileHandler] = None

# Global variable holding the saved exception hook.
_saved_except_hook: Optional[Callable] = None


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
            rate_limit: Maximum number of log messages per second.
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
        self._counters: Dict[Tuple[str, int], Tuple[float, float, int]] = {}

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


def _makeLogFormatter(log_process: bool) -> logging.Formatter:
    """Create a log formatter instance."""

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
    loglevel: Union[int, str] = logging.INFO,
    console_loglevel: Union[int, str] = logging.WARNING,
    logfile: Optional[str] = None,
    loglevels: Optional[Mapping[str, Union[int, str]]] = None,
    rate_limit: Optional[float] = None,
    burst_limit: int = 1
) -> None:
    """Initialize the Python logging framework for use by QMI.

    This function sets up logging to `stderr` and optional logging to a file.
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
    # However we must support the case where logging is configured during
    # early initialization via QMI_DEBUG, then later re-configured to add
    # a log file after the configuration is processed.
    if logfile:
        # Use the WatchedFileHandler class for logging to file.
        # This handler will automatically re-open the log file if the underlying
        # file is removed or renamed, for example as part of log rotation.
        _file_handler = logging.handlers.WatchedFileHandler(logfile)
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

    # By default the Python interpreter disables many types of warnings.
    # We change that here, unless explicit warning options have been specified via "python -W ...".
    if not sys.warnoptions:
        # Enable all warnings but log only the first occurrence.
        warnings.simplefilter("default")


def _log_excepthook(type_: Type[BaseException],
                    value: BaseException,
                    traceback: Optional[TracebackType] = None
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
