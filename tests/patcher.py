"""Generic patcher implementations."""
from unittest.mock import patch, Mock
import tempfile

import qmi
from qmi.core.context import QMI_Context, QMI_RpcProxy


class PatcherQmiRpcProxy:

    rpc_nonblocking = Mock()  # patch("qmi.core.rpc.QMI_RpcNonBlockingProxy")

    def __init__(self, context, descriptor):
        self._context = context
        self._descriptor = descriptor

    def get_pid(self):
        return 123

    def get_version(self):
        return "SomeVersion"


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
        return Mock()
