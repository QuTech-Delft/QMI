"""Toplevel package of the QMI framework.
"""

import sys
import logging
import os
import atexit


__version__ = "0.51.1"


# Check Python version.
if sys.version_info.major != 3:
    raise RuntimeError("QMI depends on Python 3. Your version: {}".format(sys.version_info))

# Set up basic logging functionality.
# This is done only when requested via the QMI_DEBUG environment variable.
# Normal logging setup is done during qmi.start().
if os.getenv("QMI_DEBUG"):
    import qmi.core.logging_init
    qmi.core.logging_init.start_logging(loglevel=logging.DEBUG,
                                        console_loglevel=logging.DEBUG)

# Direct call through .getLogger() to avoid making a package global variable.
logging.getLogger(__name__).debug("MODULE INIT: %s (enter)", __name__)

# Import symbols from specific QMI modules.
# This makes it more convenient to access these symbols from applications
# since they appear directly inside the qmi module.
from qmi.core.context_singleton import (
        context, start, stop, info, make_rpc_object, make_task, make_instrument, list_rpc_objects,
        show_rpc_objects, show_instruments, show_tasks, show_contexts, show_network_contexts,
        get_rpc_object, get_instrument, get_task, get_configured_contexts
    )

from qmi.core.object_registry import ObjectRegistry as _ObjectRegistry

object_registry = _ObjectRegistry()

atexit.register(lambda: object_registry.report(os.getenv("QMI_DEBUG") is not None))

logging.getLogger(__name__).debug("MODULE INIT: %s (leave)", __name__)
