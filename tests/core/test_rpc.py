#! /usr/bin/env python

import inspect
import logging
import math
import time
from typing import NamedTuple
import unittest
from unittest.mock import Mock, MagicMock

from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.context import QMI_Context
from qmi.core.exceptions import (
    QMI_MessageDeliveryException, QMI_UsageException, QMI_InvalidOperationException, QMI_DuplicateNameException
)
from qmi.core.rpc import (
    QMI_RpcObject, QMI_RpcTimeoutException, QMI_RpcFuture, QMI_RpcProxy, QMI_RpcNonBlockingProxy,
    rpc_method, is_rpc_method
)
from threading import Timer


class MyRpcTestClass(QMI_RpcObject):
    """An RPC test class"""
    _rpc_constants = ["CONSTANT_NUMBER"]

    CONSTANT_NUMBER = 42
    CONSTANT_FLOAT = 3.1415

    def __init__(self, context, name):
        super().__init__(context, name)

    @rpc_method
    def remote_sqrt(self, x):
        """This is some_method."""

        if x < 0:
            raise ValueError("Bad value!")

        # Sleep. This will be used to test timeout behaviour.
        time.sleep(x / 1e3)

        return math.sqrt(x)

    @rpc_method
    def my_lock_method(self, lock_token):
        """Method with it's own lock token keyword argument."""
        pass


class MyRpcSubClass(MyRpcTestClass):
    """An RPC sub class"""
    _rpc_constants = ["CONSTANT_STRING"]

    CONSTANT_STRING = "testing"

    @rpc_method
    def remote_log(self, x):
        return math.log(x)


class ProxyInterface(NamedTuple):
    """For testing proxy descriptor."""
    rpc_class_module: str = "SomeClass"
    rpc_class_name: str = "ClassyName"
    rpc_class_docstring: str = """This is Some Classy docstring."""
    constants: list = []
    methods: list = []
    signals: list = []


class ProxyDescriptor(NamedTuple):
    """For testing proxy descriptor."""
    address: MagicMock = MagicMock()
    category: MagicMock = MagicMock()
    interface: ProxyInterface = ProxyInterface()


class TestRpcProxy(unittest.TestCase):
    """Test instantiating QMI_RpcProxy and QMI_RpcNonBlockingProxy classes."""

    def test_create_instance(self):
        """Test creating an instance of QMI_RpcProxy."""
        # Arrange
        proxy_interface = ProxyInterface()
        expected_class_fqn = ".".join([proxy_interface.rpc_class_module, proxy_interface.rpc_class_name])
        expected_docstring = proxy_interface.rpc_class_docstring
        # Act
        proxy = QMI_RpcProxy(QMI_Context("test_rpcproxy"), ProxyDescriptor())
        # Assert
        self.assertIsInstance(proxy, QMI_RpcProxy)
        self.assertEqual(expected_class_fqn, proxy._rpc_class_fqn)
        self.assertEqual(expected_docstring, proxy.__doc__)

    def test_context_manager_excepts(self):
        """Test creating an instance of QMI_RpcProxy with context manager excepts with RecursionError."""
        # Act
        with self.assertRaises(RecursionError):
            with QMI_RpcProxy(QMI_Context("test_rpcproxy"), ProxyDescriptor()):
                pass

    def test_create_nonblocking_instance(self):
        """Test creating an instance of QMI_RpcNonBlockingProxy."""
        # Arrange
        proxy_interface = ProxyInterface()
        expected_class_fqn = ".".join([proxy_interface.rpc_class_module, proxy_interface.rpc_class_name])
        expected_docstring = proxy_interface.rpc_class_docstring
        # Act
        proxy = QMI_RpcNonBlockingProxy(QMI_Context("test_rpcnonblockingproxy"), ProxyDescriptor())
        # Assert
        self.assertIsInstance(proxy, QMI_RpcNonBlockingProxy)
        self.assertEqual(expected_class_fqn, proxy._rpc_class_fqn)
        self.assertEqual(expected_docstring, proxy.__doc__)

    def test_nonblocking_context_manager_excepts(self):
        """Test creating an instance of QMI_RpcProxy with context manager excepts with TypeError."""
        # Act
        with self.assertRaises((AttributeError, TypeError)):  # TypeError as no __enter__ and __exit__ present
            with QMI_RpcNonBlockingProxy(QMI_Context("test_rpcproxy"), ProxyDescriptor()):
                pass


class TestRPC(unittest.TestCase):

    def _get_rpc_methods_signals_constants(self, rpc_object_class, signal_declaration_class):
        # Get the class docstring for updating it with info
        doc = ""
        doc += '\n\nRPC methods:\n'
        # Extract RPC method declarations.
        for name, member in inspect.getmembers(rpc_object_class, is_rpc_method):
            if name in ("lock", "unlock", "force_unlock", "is_locked"):
                continue

            signature = str(inspect.signature(member))
            if not name.startswith("_"):
                signature_doc = signature.replace("(self, ", "(").replace("(self", "(")
                doc += f"  - {name}{signature_doc}\n"

        # Extract signal declarations.
        doc += '\nQMI signals:\n'
        for signal_description in signal_declaration_class._qmi_signals:
            name = signal_description.name
            arg_types = "(" + ", ".join(arg_type.__name__ for arg_type in signal_description.arg_types) + ")"
            doc += f"  - {name}{arg_types}\n"

        # Extract constant declarations.
        constant_names = set()
        for base in inspect.getmro(rpc_object_class):
            if hasattr(base, "_rpc_constants"):
                constant_names.update(getattr(base, "_rpc_constants"))

        # Extract constant values.
        doc += '\nRPC constants:\n'
        for constant_name in constant_names:
            assert hasattr(rpc_object_class, constant_name)
            constant_value = getattr(rpc_object_class, constant_name)
            assert not inspect.isfunction(constant_value)
            doc += f"  - {constant_name}={constant_value}\n"

        return doc

    def setUp(self):

        # Suppress warnings.
        logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)
        logging.getLogger("qmi.core.messaging").setLevel(logging.ERROR)

        # Start two contexts.
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0),
                "c2": CfgContext(tcp_server_port=0)
            }
        )

        c1 = QMI_Context("c1", config)
        c1.start()
        c1_port = c1.get_tcp_server_port()

        c2 = QMI_Context("c2", config)
        c2.start()

        # Connect c2 to c1.
        c1_address = "localhost:{}".format(c1_port)
        c2.connect_to_peer("c1", c1_address)

        self.c1 = c1
        self.c2 = c2

    def tearDown(self):

        self.c1.stop()
        self.c2.stop()

        self.c1 = None
        self.c2 = None

        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)
        logging.getLogger("qmi.core.messaging").setLevel(logging.NOTSET)

    def test_blocking_rpc(self):
        """Test for blocking RPC calls."""
        # Get class documentation and update it with RPC methods, signals and constants listing
        orig_doc = MyRpcTestClass.__doc__
        orig_doc += self._get_rpc_methods_signals_constants(MyRpcTestClass, MyRpcTestClass)
        # Instantiate the class, as a thing to be serviced from context c1.
        # This gives us a proxy to the instance.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcTestClass)
        # Check nominal behavior.
        result = proxy1.remote_sqrt(256.0)
        self.assertEqual(result, 16.0)

        # Check exception behavior.
        with self.assertRaises(ValueError):
            proxy1.remote_sqrt(-1.0)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Check nominal behavior.
        result = proxy2.remote_sqrt(256.0)
        self.assertEqual(result, 16.0)
        # Assert also that docstring gets passed to proxy.
        self.assertEqual(orig_doc, proxy1.__doc__)
        self.assertEqual(proxy1.__doc__, proxy2.__doc__)

        # Check exception behavior.
        with self.assertRaises(ValueError):
            proxy2.remote_sqrt(-1.0)

    def test_blocking_rpc_timeout(self):
        """Test timeout for blocking RPC method calls."""
        # Instantiate class in context c1.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcTestClass)

        # Check local timeout behavior.
        with self.assertRaises(QMI_RpcTimeoutException):
            proxy1.remote_sqrt(1024, rpc_timeout=1.0)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Check remote timeout behavior.
        with self.assertRaises(QMI_RpcTimeoutException):
            proxy2.remote_sqrt(1024, rpc_timeout=1.0)

    def test_nonblocking_rpc(self):
        """Test for non-blocking RPC calls."""
        # Get class documentation and update it with RPC methods, signals and constants listing
        orig_doc = MyRpcTestClass.__doc__
        orig_doc += self._get_rpc_methods_signals_constants(MyRpcTestClass, MyRpcTestClass)
        # Instantiate the class, as a thing to be serviced from context c1.
        # This gives us a proxy to the instance.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcTestClass)

        # Check nominal behavior.
        future = proxy1.rpc_nonblocking.remote_sqrt(256.0)
        assert isinstance(future, QMI_RpcFuture)
        result = future.wait()
        self.assertEqual(result, 16.0)

        # Check exception behavior.
        with self.assertRaises(ValueError):
            future = proxy1.rpc_nonblocking.remote_sqrt(-1.0)
            assert isinstance(future, QMI_RpcFuture)
            future.wait()

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Check nominal behavior.
        future = proxy2.rpc_nonblocking.remote_sqrt(256.0)
        assert isinstance(future, QMI_RpcFuture)
        result = future.wait()
        self.assertEqual(result, 16.0)
        # Assert also that docstring gets passed to proxy.
        self.assertEqual(orig_doc, proxy1.__doc__)
        self.assertEqual(proxy1.__doc__, proxy2.__doc__)

        # Check exception behavior.
        with self.assertRaises(ValueError):
            future = proxy2.rpc_nonblocking.remote_sqrt(-1.0)
            assert isinstance(future, QMI_RpcFuture)
            future.wait()

    def test_nonblocking_rpc_queue(self):

        # Instantiate class in context c1.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcTestClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Send several slow requests.
        future1 = proxy1.rpc_nonblocking.remote_sqrt(128)
        future2 = proxy2.rpc_nonblocking.remote_sqrt(129)
        future3 = proxy1.rpc_nonblocking.remote_sqrt(130)
        future4 = proxy1.rpc_nonblocking.remote_sqrt(131)
        future5 = proxy1.rpc_nonblocking.remote_sqrt(132)
        future6 = proxy1.rpc_nonblocking.remote_sqrt(133)

        # Wait for answers.
        result = future1.wait()
        self.assertAlmostEqual(result, math.sqrt(128))
        result = future2.wait()
        self.assertAlmostEqual(result, math.sqrt(129))

        # Wait out-of-order.
        result = future5.wait()
        self.assertAlmostEqual(result, math.sqrt(132))
        result = future3.wait(timeout=0.001)
        self.assertAlmostEqual(result, math.sqrt(130))
        result = future4.wait(timeout=0.001)
        self.assertAlmostEqual(result, math.sqrt(131))
        result = future6.wait()
        self.assertAlmostEqual(result, math.sqrt(133))

    def test_nonblocking_rpc_timeout(self):

        # Instantiate class in context c1.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcTestClass)

        # Check timeout behavior.
        with self.assertRaises(QMI_RpcTimeoutException):
            future = proxy1.rpc_nonblocking.remote_sqrt(1024)
            assert isinstance(future, QMI_RpcFuture)
            _ = future.wait(timeout=1.0)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Check timeout behavior.
        with self.assertRaises(QMI_RpcTimeoutException):
            future = proxy2.rpc_nonblocking.remote_sqrt(1024)
            assert isinstance(future, QMI_RpcFuture)
            _ = future.wait(timeout=1.0)

    def test_force_unlock(self):
        """Test locking the object in one proxy and force unlocking from another proxy."""
        # Instantiate class in context c1.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcTestClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        proxy1.lock()
        # See that second proxy cannot unlock
        result = proxy2.unlock()
        self.assertFalse(result)
        self.assertTrue(proxy1.is_locked())

        # Then, using force_unlock, we do succeed
        proxy2.force_unlock()
        self.assertFalse(proxy1.is_locked())

    def test_subclass(self):

        # Get class documentation and update it with RPC methods, signals and constants listing
        orig_doc = MyRpcSubClass.__doc__
        orig_doc += self._get_rpc_methods_signals_constants(MyRpcSubClass, MyRpcSubClass)
        # Make instance of MyRpcSubClass in the first context.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Make an RPC call to a method defined by the subclass.
        result = proxy2.remote_log(10.0)
        self.assertAlmostEqual(result, 2.302585092994046)

        # Make an RPC call to a method defined by the base class.
        result = proxy2.remote_sqrt(100.0)
        self.assertAlmostEqual(result, 10.0)
        # Assert also that docstring gets passed to proxy.
        self.assertEqual(orig_doc, proxy1.__doc__)
        self.assertEqual(proxy1.__doc__, proxy2.__doc__)

    def test_constants(self):

        # Make instance of MyRpcSubClass in the first context.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Check that constants are accessible via both proxies.
        self.assertEqual(proxy1.CONSTANT_NUMBER, 42)
        self.assertEqual(proxy1.CONSTANT_STRING, "testing")
        self.assertEqual(proxy2.CONSTANT_NUMBER, 42)
        self.assertEqual(proxy2.CONSTANT_STRING, "testing")

        # Check that non-exported constants are not accessible.
        with self.assertRaises(AttributeError):
            print(proxy1.CONSTANT_FLOAT)

    def test_call_to_disconnected(self):

        # Make instance of MyRpcSubClass in the first context.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Force the contexts to disconnect.
        self.c2.disconnect_from_peer("c1")

        # Check that RPC call within context c1 still works.
        result = proxy1.remote_sqrt(64.0)
        self.assertAlmostEqual(result, 8.0)

        # Check that RPC call between contexts fails.
        with self.assertRaises(QMI_MessageDeliveryException):
            proxy2.remote_sqrt(32.0)

    def test_call_to_removed_object(self):

        # Make instance of MyRpcSubClass in the first context.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Remove the object.
        self.c1.remove_rpc_object(proxy1)

        # Check that RPC call to removed object fails within context c1.
        with self.assertRaises(QMI_MessageDeliveryException):
            proxy1.remote_sqrt(16.0)

        # Check that RPC call to removed object fails even from context c2.
        with self.assertRaises(QMI_MessageDeliveryException):
            proxy2.remote_sqrt(32.0)

        # Check that non-blocking calls deliver the exception when waited on.
        future1 = proxy1.rpc_nonblocking.remote_sqrt(16.0)
        future2 = proxy2.rpc_nonblocking.remote_sqrt(32.0)
        with self.assertRaises(QMI_MessageDeliveryException):
            future1.wait()
        with self.assertRaises(QMI_MessageDeliveryException):
            future2.wait()

    def test_disconnect_during_call(self):

        # Make instance of MyRpcSubClass in the first context.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Start a slow, remote RPC call from the second context.
        future = proxy2.rpc_nonblocking.remote_sqrt(512)

        # While the call is in progress, force the contexts to disconnect.
        time.sleep(0.05)
        self.c2.disconnect_from_peer("c1")

        # Check that the RPC call completes with an error.
        with self.assertRaises(QMI_MessageDeliveryException):
            future.wait()

    def test_remove_object_while_call_queued(self):

        # Make instance of MyRpcSubClass in the first context.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)

        # Make a proxy via the second context.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")

        # Start a slow RPC call.
        future1 = proxy1.rpc_nonblocking.remote_sqrt(512)

        # Start two more RPC calls, one from each context.
        # These will be queued while the first call is still in progress.
        future2 = proxy1.rpc_nonblocking.remote_sqrt(15)
        future3 = proxy2.rpc_nonblocking.remote_sqrt(17)

        # Remove the RPC object while the first call is still in progress.
        time.sleep(0.05)
        self.c1.remove_rpc_object(proxy1)

        # Check that the first call completed successfully.
        result = future1.wait()
        self.assertAlmostEqual(result, math.sqrt(512))

        # Check that the other two calls complete with an error.
        with self.assertRaises(QMI_MessageDeliveryException):
            future2.wait()
        with self.assertRaises(QMI_MessageDeliveryException):
            future3.wait()

    def test_get_name_of_RpcObject(self):
        """Test `get_name()` rpc method of the class."""
        expected = "tc1"
        # Make instance of MyRpcSubClass in the first context and get its name.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)
        name1 = proxy1.get_name()
        # Make a proxy via the second context and get its name.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")
        name2 = proxy2.get_name()
        # Assert the names are as expected
        self.assertEqual(expected, name1)
        self.assertEqual(expected, name2)

    def test_get_address_of_RpcObject(self):
        """Test `get_address()` rpc method of the class."""
        expected = "c1.tc1"
        # Make instance of MyRpcSubClass in the first context and get its name.
        proxy1 = self.c1.make_rpc_object("tc1", MyRpcSubClass)
        # address1 = proxy1.get_address()
        address1 = proxy1.address
        # Make a proxy via the second context and get its address.
        proxy2 = self.c2.get_rpc_object_by_name("c1.tc1")
        # address2 = proxy2.get_address()
        address2 = proxy2.address
        # Assert the addresses are as expected
        self.assertEqual(expected, address1)
        self.assertEqual(expected, address2)

    def test_no_context_manager_allowed(self):
        """Making an RPC object with context manager is not allowed."""
        with self.assertRaises(NotImplementedError):
            with self.c1.make_rpc_object("tc1", MyRpcSubClass):
                pass


class TestRpcMethodDecorator(unittest.TestCase):
    class ObjectWithGoodMethodName(QMI_RpcObject):
        @rpc_method
        def some_method(self): ...

    class ObjectWithBadMethodNameLock(QMI_RpcObject):
        @rpc_method
        def lock(self): ...

    class ObjectWithBadMethodNameUnlock(QMI_RpcObject):
        @rpc_method
        def unlock(self): ...

    class ObjectWithBadMethodNameForceUnlock(QMI_RpcObject):
        @rpc_method
        def force_unlock(self): ...

    class ObjectWithBadMethodNameIsLocked(QMI_RpcObject):
        @rpc_method
        def is_locked(self): ...

    def test_good_name(self):
        """Test acceptable method name."""
        obj = self.ObjectWithGoodMethodName(Mock(), "good_object")
        self.assertTrue(hasattr(obj, "some_method"))

    def test_bad_name_lock(self):
        """Test unacceptable method name."""
        with self.assertRaises(QMI_UsageException):
            self.ObjectWithBadMethodNameLock(Mock(), "bad_object")

    def test_bad_name_unlock(self):
        """Test unacceptable method name."""
        with self.assertRaises(QMI_UsageException):
            self.ObjectWithBadMethodNameUnlock(Mock(), "bad_object")

    def test_bad_name_force_unlock(self):
        """Test unacceptable method name."""
        with self.assertRaises(QMI_UsageException):
            self.ObjectWithBadMethodNameForceUnlock(Mock(), "bad_object")

    def test_bad_name_is_locked(self):
        """Test unacceptable method name."""
        with self.assertRaises(QMI_UsageException):
            self.ObjectWithBadMethodNameIsLocked(Mock(), "bad_object")


class TestRpcObjectLocking(unittest.TestCase):
    def setUp(self):

        # Suppress warnings.
        logging.getLogger("qmi.core.rpc").setLevel(logging.ERROR)

        config = CfgQmi(
            contexts={
                "my_context": CfgContext(tcp_server_port=0)
            }
        )

        self.context = QMI_Context("my_context", config)
        self.context.start()

    def tearDown(self):
        self.context.stop()
        self.context = None

        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_lock(self):
        """Test locking an object."""
        proxy = self.context.make_rpc_object("my_object", MyRpcTestClass)

        result = proxy.lock()
        self.assertTrue(result)
        self.assertTrue(proxy.is_locked())

    def test_lock_with_custom_token(self):
        """Test locking an object with a custom token."""
        proxy = self.context.make_rpc_object("my_object", MyRpcTestClass)

        result = proxy.lock(lock_token="thisismineallmine")
        self.assertTrue(result)
        self.assertTrue(proxy.is_locked())

    def test_lock_unlock(self):
        """Test unlocking an object that was locked within the same proxy."""
        proxy = self.context.make_rpc_object("my_object", MyRpcTestClass)

        result = proxy.lock()
        self.assertTrue(result)
        self.assertTrue(proxy.is_locked())

        result = proxy.unlock()
        self.assertTrue(result)
        self.assertFalse(proxy.is_locked())

    def test_lock_fail(self):
        """Test locking an object from another proxy fails when object is already locked."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")

        result = proxy1.lock()
        self.assertTrue(result)
        self.assertTrue(proxy1.is_locked())
        self.assertTrue(proxy2.is_locked())

        result = proxy2.lock()
        self.assertFalse(result)

    def test_unlock_fail(self):
        """Test unlocking a locked object from other proxy fails if the token is not known."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")

        result = proxy1.lock()
        self.assertTrue(result)
        self.assertTrue(proxy1.is_locked())
        self.assertTrue(proxy2.is_locked())

        result = proxy2.unlock()
        self.assertFalse(result)
        self.assertTrue(proxy1.is_locked())
        self.assertTrue(proxy2.is_locked())

    def test_force_unlock(self):
        """Test force unlocking an object unlocks even if object is locked by another proxy."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")

        result = proxy1.lock()
        self.assertTrue(result)
        self.assertTrue(proxy1.is_locked())
        self.assertTrue(proxy2.is_locked())

        proxy2.force_unlock()
        self.assertFalse(proxy1.is_locked())
        self.assertFalse(proxy2.is_locked())

    def test_lock_unlock_with_custom_token(self):
        """Test unlocking an object with a custom token."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")
        custom_token = "thisismineallmine"

        result = proxy1.lock(lock_token=custom_token)
        self.assertTrue(result)
        self.assertTrue(proxy1.is_locked())
        # Test that unlocking with some other custom token doesn't work
        result = proxy2.unlock(lock_token="precious")
        self.assertFalse(result)
        self.assertTrue(proxy1.is_locked())
        # Then unlock with the custom token
        result = proxy2.unlock(lock_token=custom_token)
        self.assertTrue(result)
        self.assertFalse(proxy2.is_locked())

    def test_lock_with_timeout(self):
        """Test that a proxy object that is locked, can be set pending by another proxy to be locked with a
        timeout. The second proxy achieves the lock when the first one releases it."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")

        result = proxy1.lock()
        self.assertTrue(result)
        # Call release after 0.5 sec
        unlock = Timer(0.5, proxy1.unlock)
        start = time.time()
        unlock.start()

        result = proxy2.lock(timeout=1.0)
        self.assertTrue(result)
        end = time.time()
        self.assertLess(end-start, 0.7)
        # As the context is locked by 2nd context, it should appear as locked for both
        self.assertTrue(proxy1.is_locked())
        self.assertTrue(proxy2.is_locked())

    def test_lock_with_timeout_2(self):
        """The same test as previous, but with the 'client' side now doing the locking."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")

        result = proxy2.lock()
        self.assertTrue(result)
        # Call release after 0.5 sec
        unlock = Timer(0.5, proxy2.unlock)
        start = time.time()
        unlock.start()

        result = proxy1.lock(timeout=1.0)
        self.assertTrue(result)
        end = time.time()
        self.assertLess(end-start, 0.7)
        # As the context is locked by 1st context, it should appear as locked for both
        self.assertTrue(proxy2.is_locked())
        self.assertTrue(proxy1.is_locked())

    def test_lock_with_timeout_fail(self):
        """Test that a proxy object that is locked, can be set pending by another proxy to be locked with a
        timeout. The second proxy time-outs before receiving the proxy."""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy2 = self.context.get_rpc_object_by_name("my_context.my_object")

        result = proxy1.lock()
        self.assertTrue(result)
        # Call release after 0.5 sec
        unlock = Timer(0.5, proxy1.unlock)
        start = time.time()
        unlock.start()

        result = proxy2.lock(timeout=0.4)
        self.assertFalse(result)
        end = time.time()
        self.assertLess(end - start, 0.5)
        time.sleep(0.6 - end + start)
        # The last call was to unlock, so neither should appear locked
        self.assertFalse(proxy1.is_locked())
        self.assertFalse(proxy2.is_locked())

    def test_my_lock_method(self):
        """Test shows that user is allowed to use the keyword argument `lock_token`"""
        proxy1 = self.context.make_rpc_object("my_object", MyRpcTestClass)
        proxy1.my_lock_method(lock_token='foo')

        self.assertTrue(proxy1.lock())
        self.assertTrue(proxy1.is_locked())

        proxy1.my_lock_method(lock_token='foo')

    def test_make_rpc_object_excepts(self):
        """Give an invalid name for a rpc object."""
        with self.assertRaises(QMI_UsageException):
            self.context.make_rpc_object("!@gr$%:(", MyRpcTestClass)


class TestRPCWithClosingService(unittest.TestCase):

    def test_making_object_in_inactive_context_excepts(self):
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0)
            }
        )
        c1 = QMI_Context("c1", config)
        c1.start()
        c1.make_rpc_object("duplicate", MyRpcTestClass)
        with self.assertRaises(QMI_DuplicateNameException):
            c1.make_rpc_object("duplicate", MyRpcTestClass)

    def test_making_duplicate_object_in_context_excepts(self):
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0)
            }
        )
        c1 = QMI_Context("c1", config)
        c1.start()
        c1.stop()
        with self.assertRaises(QMI_InvalidOperationException):
            c1.make_rpc_object("notactive", MyRpcTestClass)

    def test_lock_token_after_closed_context(self):
        """Test locking the object with a lock token and using it from another context with the same name."""
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0)
            }
        )

        c1 = QMI_Context("c1", config)
        c1.start()
        c1_port = c1.get_tcp_server_port()
        c1_address = "localhost:{}".format(c1_port)
        # Instantiate class in context c1 as "object provider".
        proxy1 = c1.make_rpc_object("tc1", MyRpcTestClass)
        self.assertFalse(proxy1.is_locked())

        # Now make another context with the same name, and get a proxy
        c2 = QMI_Context("c2", config)
        c2.start()
        c2.connect_to_peer("c1", c1_address)
        # Instantiate class in context 'c1'.
        proxy2 = c2.get_rpc_object_by_name("c1.tc1")
        self.assertFalse(proxy2.is_locked())
        result = proxy2.lock(lock_token="block")
        self.assertTrue(result)
        self.assertTrue(proxy2.is_locked())
        # And then close it
        c2.stop()

        # Then start third context with the same name, obtain the object and unlock it.
        c3 = QMI_Context("c2", config)
        c3.start()
        c3.connect_to_peer("c1", c1_address)
        # Instantiate class in context 'c1'.
        proxy3 = c3.get_rpc_object_by_name("c1.tc1")
        self.assertTrue(proxy3.is_locked())
        result = proxy3.unlock(lock_token="block")
        self.assertTrue(result)
        self.assertFalse(proxy3.is_locked())
        # And then close it
        c3.stop()

        # Then finally stop the "object provider"
        c1.stop()


if __name__ == "__main__":
    unittest.main()
