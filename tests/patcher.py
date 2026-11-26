"""Generic patcher implementations."""
from unittest.mock import patch, Mock
import tempfile

import qmi
from qmi.core.context import QMI_Context, QMI_RpcProxy
from qmi.core.exceptions import QMI_UnknownNameException


class PatcherQmiRpcProxy:

    rpc_nonblocking = Mock()

    def __init__(self, context, descriptor):
        self._context = context
        self._descriptor = descriptor

    def get_pid(self):
        return 123

    @classmethod
    def get_version(cls):
        return "SomeVersion"


class PatcherQmiContext:
    """Patches the qmi_context global variable which results in an instanced qmi_context.
    Note that only within the context of this patcher the qmi_context is a singleton.
    """

    def __init__(self, name=None):
        self.name = name
        self.qmi_patcher = None
        self._patcher_started = False
        self._context: QMI_Context | None = None
        # Instruments made with `make_instrument`, as (owning context, proxy) pairs.
        self._instruments: list[tuple[QMI_Context, QMI_RpcProxy]] = []

    def start(self, context_name=None, config=None):
        """Start the qmi_context and patcher."""
        context_name = context_name or self.name
        self._context = QMI_Context(context_name, config)
        self.qmi_patcher = patch("qmi.core.context_singleton._qmi_context", self._context)
        self.qmi_patcher.start()
        self._patcher_started = True
        qmi.core.context_singleton._qmi_context.start()
        qmi.core.context_singleton._connect_to_peers()

    def stop(self):
        """Remove the instruments made with `make_instrument`, stop the real context, then stop the patcher.

        Like stopping a real QMI context, removing an instrument stops its RPC thread, which calls
        `release_rpc_object()` on the instrument.

        Safe to call even if `start()` was never called, or failed half-way, in which case it cleans up
        whatever was already created and otherwise does nothing.
        """
        while self._instruments:
            context, proxy = self._instruments.pop()
            try:
                context.remove_rpc_object(proxy)
            except QMI_UnknownNameException:
                pass  # Already removed by the test itself.

        if self._context is not None:
            if self._context._active:
                self._context.stop()
            self._context = None

        if self._patcher_started:
            self.qmi_patcher.stop()
            self._patcher_started = False

    def make_instrument(self, instrument_name, instrument_class, *args, **kwargs):
        """Make an instrument in the patched context and register it for removal on `stop()`."""
        context = qmi.core.context_singleton._qmi_context
        proxy = context.make_instrument(instrument_name, instrument_class, *args, **kwargs)
        self._instruments.append((context, proxy))
        return proxy

    def connect_to_peer(self, peer_context_name, peer_address):
        return None

    def make_peer_context_proxy(self, context_name):
        return PatcherQmiRpcProxy(self, None)

    def disconnect_from_peer(self, peer_context_name):
        return None

    def resolve_file_name(self, output_dir):
        temp_dir = tempfile.mkdtemp()
        return temp_dir

    def get_qmi_home_dir(self):
        temp_dir = tempfile.mkdtemp()
        return temp_dir

    def get_config(self):
        return qmi.core.context_singleton._qmi_context._config
