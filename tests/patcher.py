"""Generic patcher implementations."""
import qmi


from unittest.mock import patch

from qmi.core.context import QMI_Context


class PatcherQmiContext:
    """Patches the qmi_context global variable which results in an instanced qmi_context.
    Note that only within the context of this patcher the qmi_context is a singleton.
    """

    def __init__(self, name=None):
        self.name = name
        self.qmi_patcher = None

    def start(self, context_name=None, config=None):
        """Start the qmi_context and patcher."""
        context_name = context_name or self.name
        self.qmi_patcher = patch("qmi.core.context_singleton._qmi_context", QMI_Context(context_name, config))
        self.qmi_patcher.start()
        qmi.core.context_singleton._qmi_context.start()
        qmi.core.context_singleton._connect_to_peers()

    def stop(self):
        """Stop the qmi_context and patcher."""
        qmi.stop()
        self.qmi_patcher.stop()

    def make_instrument(self, instrument_name, instrument_class, *args, **kwargs):
        return qmi.core.context_singleton._qmi_context.make_instrument(
            instrument_name, instrument_class, *args, **kwargs
        )
