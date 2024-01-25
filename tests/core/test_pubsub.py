#! /usr/bin/env python3

"""Test publish/subscribe functionality."""
import random
import time
import unittest

import qmi
import qmi.core.exceptions
from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.context import QMI_Context
from qmi.core.rpc import QMI_RpcObject, rpc_method
from qmi.core.pubsub import SignalDescription, QMI_Signal, QMI_SignalReceiver


class MyPublisher(QMI_RpcObject):

    last_instance = None

    sig1 = QMI_Signal([])
    sig2 = QMI_Signal([int])
    sig3 = QMI_Signal([int, str])

    def __init__(self, context, name):
        super().__init__(context, name)
        MyPublisher.last_instance = self

    @rpc_method
    def send1(self):
        self.sig1.publish()

    @rpc_method
    def send2(self):
        self.sig2.publish(24)

    @rpc_method
    def send3(self, x, s):
        self.sig3.publish(x, s)

    @rpc_method
    def send_slow(self):
        for i in range(5):
            time.sleep(0.5)
            self.sig2.publish(i)


class TestLocalPubSub(unittest.TestCase):
    """Test publish/subscribe within the local context."""

    def setUp(self):
        self.context_name = "test_local_pubsub"
        qmi.start(self.context_name)

    def tearDown(self):
        qmi.stop()

    def test_register_signal(self):
        # Test registration of signals.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)
        pub2 = qmi.make_rpc_object("pub2", MyPublisher)

        # Check list of registered signals.
        sigs = pub1.get_signals()
        expect_sigs = {
            SignalDescription("sig1", ()),
            SignalDescription("sig2", (int,)),
            SignalDescription("sig3", (int, str))
        }
        self.assertEqual(set(sigs), expect_sigs)

        sigs = pub2.get_signals()
        self.assertEqual(set(sigs), expect_sigs)

    def test_subscribe(self):
        # Test subscribing to signals.

        qmi.make_rpc_object("pub1", MyPublisher)
        qmi.make_rpc_object("pub2", MyPublisher)

        # Create signal receiver queue.
        recv = QMI_SignalReceiver()
        recv2 = QMI_SignalReceiver()

        # Subscribe to signals.
        qmi.context().subscribe_signal(self.context_name, "pub1", "sig1", recv)
        qmi.context().subscribe_signal(self.context_name, "pub2", "sig2", recv)
        qmi.context().subscribe_signal(self.context_name, "pub1", "sig1", recv2)

        # Unsubscribe from signals.
        qmi.context().unsubscribe_signal(self.context_name, "pub1", "sig1", recv)
        qmi.context().unsubscribe_signal(self.context_name, "pub2", "sig2", recv)
        qmi.context().unsubscribe_signal(self.context_name, "pub1", "sig1", recv2)

        # Check that receiver queues are still empty.
        self.assertFalse(recv.has_signal_ready())
        self.assertFalse(recv2.has_signal_ready())

        # Try to unsubscribe from a non-subscribed signal - should be ignored.
        qmi.context().unsubscribe_signal(self.context_name, "pub1", "sig1", recv)

    def test_pubsub(self):
        # Publish and receive signals.

        qmi.make_rpc_object("pub1", MyPublisher)
        qmi.make_rpc_object("pub2", MyPublisher)

        # Create signal receiver queue.
        recv = QMI_SignalReceiver()

        # Subscribe to signals.
        qmi.context().subscribe_signal(self.context_name, "pub1", "sig1", recv)
        qmi.context().subscribe_signal(self.context_name, "pub1", "sig2", recv)
        qmi.context().subscribe_signal(self.context_name, "pub2", "sig1", recv)

        # Publish signals.
        qmi.context().publish_signal("pub1", "sig1", 111)
        qmi.context().publish_signal("pub1", "sig1", 112)
        qmi.context().publish_signal("pub1", "sig2", "aap", "noot")

        # Check that signals are received.
        self.assertTrue(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 3)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig1")
        self.assertEqual(sig.args, (111,))
        self.assertEqual(sig.receiver_seqnr, 0)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig1")
        self.assertEqual(sig.args, (112,))
        self.assertEqual(sig.receiver_seqnr, 1)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig2")
        self.assertEqual(sig.args, ("aap", "noot"))
        self.assertEqual(sig.receiver_seqnr, 2)

        # Check no more signals in queue.
        self.assertFalse(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 0)

        # Try to get signal from queue - should time out.
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            sig = recv.get_next_signal(timeout=1.0)

        # Publish a non-subscribed signal - should be fine.
        qmi.context().publish_signal("pub2", "sig2", 211)

        # Check no new signals received.
        self.assertFalse(recv.has_signal_ready())

        # Unsubscribe from one of the signals.
        qmi.context().unsubscribe_signal(self.context_name, "pub1", "sig1", recv)

        # Publish more signals.
        qmi.context().publish_signal("pub1", "sig1", 113)
        qmi.context().publish_signal("pub1", "sig2", "mies", "wim")

        # Check received as expected.
        self.assertTrue(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 1)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig2")
        self.assertEqual(sig.args, ("mies", "wim"))
        self.assertEqual(sig.receiver_seqnr, 3)

        # Unsubscribe from all signals.
        qmi.context().unsubscribe_signal(self.context_name, "pub1", "sig2", recv)
        qmi.context().unsubscribe_signal(self.context_name, "pub2", "sig1", recv)

        # Publish more signals.
        qmi.context().publish_signal("pub1", "sig1", 114)
        qmi.context().publish_signal("pub1", "sig2", "zus", "jet")
        qmi.context().publish_signal("pub2", "sig1", 3.14)

        # Check nothing received.
        self.assertFalse(recv.has_signal_ready())

    def test_subscribe_proxy(self):
        # Test subscribing to signals via RPC proxy.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)

        # Create signal receiver queue.
        recv = QMI_SignalReceiver()
        recv2 = QMI_SignalReceiver()

        # Subscribe to signals (registered and unregistered).
        pub1.sig1.subscribe(recv)
        pub1.sig2.subscribe(recv)
        pub1.sig1.subscribe(recv2)

        # Unsubscribe from signals.
        pub1.sig1.unsubscribe(recv)
        pub1.sig2.unsubscribe(recv)
        pub1.sig1.unsubscribe(recv2)

        # Check that receiver queues are still empty.
        self.assertFalse(recv.has_signal_ready())
        self.assertFalse(recv2.has_signal_ready())

        # Try to unsubscribe from a non-subscribed signal - should be ignored.
        pub1.sig2.unsubscribe(recv2)

    def test_pubsub_rpc(self):
        # Publish signals via RPC trigger and receive signals.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)
        pub2 = qmi.make_rpc_object("pub2", MyPublisher)

        # Create signal receiver queue.
        recv = QMI_SignalReceiver()

        # Subscribe to signals.
        pub1.sig1.subscribe(recv)
        pub1.sig2.subscribe(recv)
        pub2.sig1.subscribe(recv)

        # Publish signals.
        pub1.send1()
        pub1.send1()
        pub1.send2()
        pub2.send1()

        # Check that signals are received.
        self.assertTrue(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 4)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig1")
        self.assertEqual(sig.args, ())
        self.assertEqual(sig.receiver_seqnr, 0)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig1")
        self.assertEqual(sig.args, ())
        self.assertEqual(sig.receiver_seqnr, 1)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub1")
        self.assertEqual(sig.signal_name, "sig2")
        self.assertEqual(sig.args, (24,))
        self.assertEqual(sig.receiver_seqnr, 2)
        sig = recv.get_next_signal()
        self.assertEqual(sig.publisher_context, self.context_name)
        self.assertEqual(sig.publisher_name, "pub2")
        self.assertEqual(sig.signal_name, "sig1")
        self.assertEqual(sig.args, ())
        self.assertEqual(sig.receiver_seqnr, 3)

        # Check no more signals in queue.
        self.assertFalse(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 0)

    def test_multi_sub(self):
        # Multiple subscribers per signal.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)
        pub2 = qmi.make_rpc_object("pub2", MyPublisher)

        # Create signal receiver queues.
        recv1 = QMI_SignalReceiver()
        recv2 = QMI_SignalReceiver()
        recv3 = QMI_SignalReceiver()

        # Subscribe to signals.
        pub1.sig2.subscribe(recv1)
        pub1.sig3.subscribe(recv1)
        pub1.sig3.subscribe(recv2)
        pub2.sig2.subscribe(recv3)
        pub2.sig3.subscribe(recv1)
        pub2.sig3.subscribe(recv2)
        pub2.sig3.subscribe(recv3)

        # Publish signals.
        pub1.send2()
        pub1.send3(21, "one")
        pub2.send2()
        pub2.send3(41, "two")
        pub1.send2()
        pub1.send3(22, "")
        pub2.send2()
        pub2.send3(42, "")

        # Check that signals are received as expected.
        self.assertTrue(recv1.has_signal_ready())
        self.assertEqual(recv1.get_queue_length(), 6)
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (24,), 0))
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (21, "one"), 1))
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (41, "two"), 2))
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (24,), 3))
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (22, ""), 4))
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (42, ""), 5))

        self.assertTrue(recv2.has_signal_ready())
        self.assertEqual(recv2.get_queue_length(), 4)
        sig = recv2.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (21, "one"), 0))
        sig = recv2.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (41, "two"), 1))
        sig = recv2.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (22, ""), 2))
        sig = recv2.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (42, ""), 3))

        self.assertTrue(recv3.has_signal_ready())
        self.assertEqual(recv3.get_queue_length(), 4)
        sig = recv3.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig2", (24,), 0))
        sig = recv3.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (41, "two"), 1))
        sig = recv3.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig2", (24,), 2))
        sig = recv3.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (42, ""), 3))

        # Unsubscribe some receivers.
        pub1.sig3.unsubscribe(recv2)
        pub2.sig2.unsubscribe(recv3)
        pub2.sig3.unsubscribe(recv2)
        pub2.sig3.unsubscribe(recv3)

        # Publish more signals.
        qmi.context().publish_signal("pub2", "sig3", 43, "three")

        # Check that signals are received as expected.
        self.assertTrue(recv1.has_signal_ready())
        self.assertEqual(recv1.get_queue_length(), 1)
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub2", "sig3", (43, "three"), 6))

        # Check no further signals received.
        self.assertFalse(recv1.has_signal_ready())
        self.assertFalse(recv2.has_signal_ready())
        self.assertFalse(recv3.has_signal_ready())

    def test_queue_overflow(self):
        # Test receiver queue overflow behaviour.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)

        # Create signal receiver queue.
        recv = QMI_SignalReceiver(max_queue_length=5, discard_policy=QMI_SignalReceiver.DISCARD_OLD)

        # Subscribe to signal.
        pub1.sig3.subscribe(recv)

        # Publish signals.
        for i in range(10):
            pub1.send3(10 + i, "")

        # Check that only the last 5 signals remain in the queue.
        self.assertEqual(recv.get_queue_length(), 5)
        sig = recv.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (15, ""), 5))

        # Publish another signal - should fit in the queue without overflow.
        pub1.send3(20, "")

        # Check.
        self.assertEqual(recv.get_queue_length(), 5)
        sig = recv.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (16, ""), 6))

        # Publish more signals - should push old signals out of the queue.
        for i in range(3):
            pub1.send3(30 + i, "")

        # Check queue contents.
        self.assertEqual(recv.get_queue_length(), 5)
        sig = recv.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (19, ""), 9))
        sig = recv.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (20, ""), 10))
        for i in range(3):
            sig = recv.get_next_signal()
            self.assertEqual(sig, (self.context_name, "pub1", "sig3", (30 + i, ""), 11 + i))

        self.assertFalse(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 0)

        pub1.sig3.unsubscribe(recv)

        # Try again, this time with DISCARD_NEW policy.
        recv = QMI_SignalReceiver(max_queue_length=5, discard_policy=QMI_SignalReceiver.DISCARD_NEW)
        pub1.sig3.subscribe(recv)

        # Publish signals.
        for i in range(10):
            pub1.send3(10 + i, "")

        # Check that only the first 5 signals remain in the queue.
        self.assertEqual(recv.get_queue_length(), 5)
        sig = recv.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (10, ""), 0))

        # Publish more signals - only one of them can fit in the queue.
        for i in range(3):
            pub1.send3(30 + i, "")

        # Check queue contents.
        self.assertEqual(recv.get_queue_length(), 5)
        for i in range(4):
            sig = recv.get_next_signal()
            self.assertEqual(sig, (self.context_name, "pub1", "sig3", (11 + i, ""), 1 + i))
        sig = recv.get_next_signal()
        self.assertEqual(sig, (self.context_name, "pub1", "sig3", (30, ""), 10))

        self.assertFalse(recv.has_signal_ready())
        self.assertEqual(recv.get_queue_length(), 0)

    def test_async(self):
        # Test asynchronous delivery of signals.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)

        # Create receiver queue.
        recv = QMI_SignalReceiver()

        # Subscribe to signal.
        pub1.sig2.subscribe(recv)

        # Start a slow RPC command which publishes signals from the RPC thread.
        future = pub1.rpc_nonblocking.send_slow()

        # Check no signals received yet.
        self.assertFalse(recv.has_signal_ready())

        # Blocking wait for first signal.
        sig = recv.get_next_signal(timeout=2.0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (0,), 0))

        # Check no further signals received.
        self.assertFalse(recv.has_signal_ready())

        # Sleep until second signal received.
        time.sleep(0.75)
        self.assertEqual(recv.get_queue_length(), 1)

        # Check second signal.
        sig = recv.get_next_signal(timeout=0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (1,), 1))

        # Blocking wait for 3rd signal.
        sig = recv.get_next_signal(timeout=2.0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (2,), 2))

        # Check no further signals ready.
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            recv.get_next_signal(timeout=0.1)

        # Blocking wait for 4th signal.
        sig = recv.get_next_signal(timeout=2.0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (3,), 3))

        # Finish the RPC call.
        future.wait()

        # Check 5th signal.
        sig = recv.get_next_signal(timeout=0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig2", (4,), 4))

    def test_subscribe_unknown_object(self):
        # Subscribing to a non-existing object gives an error.

        pub1 = qmi.make_rpc_object("pub1", MyPublisher)
        recv = QMI_SignalReceiver()

        qmi.context().remove_rpc_object(pub1)

        with self.assertRaises(qmi.core.exceptions.QMI_SignalSubscriptionException):
            pub1.sig1.subscribe(recv)

    def test_remove_publisher(self):
        # Remove a publisher while a receiver is subscribed to its signal.

        # Create object and subscribe to its signal.
        pub1 = qmi.make_rpc_object("pub1", MyPublisher)

        recv = QMI_SignalReceiver()
        pub1.sig1.subscribe(recv)

        # Publish a signal and check that it is received.
        pub1.send1()
        sig = recv.get_next_signal(timeout=0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig1", (), 0))

        # Remove publisher.
        qmi.context().remove_rpc_object(pub1)

        # Create new object with the same name.
        pub1 = qmi.make_rpc_object("pub1", MyPublisher)

        # Publish a signal and check that it is not received.
        pub1.send1()
        self.assertFalse(recv.has_signal_ready())

        # Re-subscribe to the signal.
        pub1.sig1.subscribe(recv)

        # Publish a signal and check that it is received.
        pub1.send1()
        sig = recv.get_next_signal(timeout=0)
        self.assertEqual(sig, (self.context_name, "pub1", "sig1", (), 1))


class TestRemotePubSub(unittest.TestCase):
    """Test publish/subscribe between contexts."""

    def setUp(self):

        # Initialize two QMI contexts.
        config = CfgQmi(
            contexts={
                "context1": CfgContext(tcp_server_port=0),
                "context2": CfgContext()
            }
        )
        self.context1 = QMI_Context("context1", config)
        self.context2 = QMI_Context("context2", config)
        self.context1.start()
        self.context2.start()

        # Context2 connects to context1.
        context1_address = "localhost:{}".format(self.context1.get_tcp_server_port())
        self.context2.connect_to_peer("context1", context1_address)

    def tearDown(self):
        self.context1.stop()
        self.context2.stop()

    def test_pubsub_remote(self):
        # Publish and receive signals between contexts.

        # Create publisher in context1.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)

        # Create publisher in context2.
        pub2 = self.context2.make_rpc_object("pub2", MyPublisher)

        # Check that context2 can see the signals in context1.
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")
        sigs = proxy.get_signals()
        expect_sigs = {
            SignalDescription("sig1", ()),
            SignalDescription("sig2", (int,)),
            SignalDescription("sig3", (int, str))
        }
        self.assertEqual(set(sigs), expect_sigs)

        # Create signal receiver queue.
        recv1 = QMI_SignalReceiver()
        recv2 = QMI_SignalReceiver()

        # Subscribe to signals.
        # NOTE: context1 can not subscribe to signals from context2
        #       because context1 has not connected to context2.
        pub1.sig3.subscribe(recv1)
        pub2.sig3.subscribe(recv2)
        proxy.sig3.subscribe(recv2)

        # Publish signals.
        pub2.send3(21, "A")
        pub1.send3(11, "B")
        proxy.send2()

        # Wait until remote signals delivered.
        time.sleep(0.2)

        # Check that signals are received.
        self.assertTrue(recv1.has_signal_ready())
        self.assertEqual(recv1.get_queue_length(), 1)
        sig = recv1.get_next_signal()
        self.assertEqual(sig, ("context1", "pub1", "sig3", (11, "B"), 0))

        self.assertTrue(recv2.has_signal_ready())
        self.assertEqual(recv2.get_queue_length(), 2)
        sig = recv2.get_next_signal()
        self.assertEqual(sig, ("context2", "pub2", "sig3", (21, "A"), 0))
        sig = recv2.get_next_signal()
        self.assertEqual(sig, ("context1", "pub1", "sig3", (11, "B"), 1))

        # Unsubscribe from remote signal.
        proxy.sig3.unsubscribe(recv2)

        # Publish signals.
        pub1.send3(12, "C")
        pub2.send3(22, "D")

        # Wait until remote signals delivered (if any).
        time.sleep(0.2)

        # Check that local signals are received.
        self.assertTrue(recv1.has_signal_ready())
        self.assertEqual(recv1.get_queue_length(), 1)
        sig = recv1.get_next_signal()
        self.assertEqual(sig, ("context1", "pub1", "sig3", (12, "C"), 1))

        self.assertTrue(recv2.has_signal_ready())
        self.assertEqual(recv2.get_queue_length(), 1)
        sig = recv2.get_next_signal()
        self.assertEqual(sig, ("context2", "pub2", "sig3", (22, "D"), 2))

    def test_remote_async(self):
        # Test asynchronous delivery of signals between contexts.

        # Create publisher in context1 with proxy in context2.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")

        # Create receiver queue.
        recv = QMI_SignalReceiver()

        # Subscribe to signal.
        proxy.sig2.subscribe(recv)

        # Start a slow RPC command which publishes signals from the RPC thread.
        future = pub1.rpc_nonblocking.send_slow()

        # Check no signals received yet.
        self.assertFalse(recv.has_signal_ready())

        # Blocking wait for first signal.
        sig = recv.get_next_signal(timeout=2.0)
        self.assertEqual(sig, ("context1", "pub1", "sig2", (0,), 0))

        # Check no further signals received.
        self.assertFalse(recv.has_signal_ready())

        # Sleep until second signal received.
        time.sleep(0.75)
        self.assertEqual(recv.get_queue_length(), 1)

        # Check second signal.
        sig = recv.get_next_signal(timeout=0)
        self.assertEqual(sig, ("context1", "pub1", "sig2", (1,), 1))

        # Blocking wait for 3rd signal.
        sig = recv.get_next_signal(timeout=2.0)
        self.assertEqual(sig, ("context1", "pub1", "sig2", (2,), 2))

        # Check no further signals ready.
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            sig = recv.get_next_signal(timeout=0.1)

        # Blocking wait for 4th signal.
        sig = recv.get_next_signal(timeout=2.0)
        self.assertEqual(sig, ("context1", "pub1", "sig2", (3,), 3))

        # Finish the RPC call.
        future.wait()

        # Check 5th signal.
        sig = recv.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig2", (4,), 4))

    def test_subscribe_unknown_remote_object(self):
        # Subscribing to a non-existing object gives an error.

        # Create object in context1 with proxy in context2.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")

        # Remove the object in context1.
        self.context1.remove_rpc_object(pub1)

        # Try to subscribe in context2 to a signal from the removed object.
        recv = QMI_SignalReceiver()
        with self.assertRaises(qmi.core.exceptions.QMI_SignalSubscriptionException):
            proxy.sig1.subscribe(recv)

    def test_remove_remote_publisher(self):
        # Remove a publisher while a receiver is subscribed to its signal.

        # Create object in context1 with proxy in context2.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")

        # Subscribe in context2 to a signal published in context1.
        recv = QMI_SignalReceiver()
        proxy.sig1.subscribe(recv)

        # Publish a signal and check that it is received.
        pub1.send1()
        sig = recv.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig1", (), 0))

        # Remove publisher.
        self.context1.remove_rpc_object(pub1)

        # Create new object with the same name.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)

        # Publish a signal and check that it is not received.
        pub1.send1()
        time.sleep(0.2)
        self.assertFalse(recv.has_signal_ready())

        # Re-subscribe to the signal.
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")
        proxy.sig1.subscribe(recv)

        # Publish a signal and check that it is received.
        pub1.send1()
        sig = recv.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig1", (), 1))

    def test_disconnect_remote_publisher(self):
        # Subscribing to a signal in a disconnected context gives an error.

        # Create object in context1 with proxy in context2.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")

        # Subscribe in context2 to a signal published in context1.
        recv = QMI_SignalReceiver()
        proxy.sig1.subscribe(recv)

        # Publish a signal and check that it is received.
        pub1.send1()
        sig = recv.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig1", (), 0))

        # Close the connection between the contexts.
        self.context2.disconnect_from_peer("context1")
        time.sleep(0.2)

        # Publish a signal and check that it is not received.
        pub1.send1()
        time.sleep(0.2)
        self.assertFalse(recv.has_signal_ready())

        # Try to resubscribe to the signal in the disconnected context.
        with self.assertRaises(qmi.core.exceptions.QMI_SignalSubscriptionException):
            proxy.sig1.subscribe(recv)
        with self.assertRaises(qmi.core.exceptions.QMI_SignalSubscriptionException):
            proxy.sig2.subscribe(recv)

    def test_multiple_remote_subscriptions(self):
        # Test multiple subscriptions to the same remote signal.

        # Create object in context1 with proxy in context2.
        pub1 = self.context1.make_rpc_object("pub1", MyPublisher)
        proxy = self.context2.get_rpc_object_by_name("context1.pub1")

        # Subscribe two receivers in context2 to the same signal from context1.
        recv1 = QMI_SignalReceiver()
        recv2 = QMI_SignalReceiver()
        proxy.sig3.subscribe(recv1)
        proxy.sig3.subscribe(recv2)

        # Publish signal, check that both receivers get it.
        pub1.send3(11, "A")
        sig = recv1.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig3", (11, "A"), 0))
        sig = recv2.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig3", (11, "A"), 0))

        # Unsubscribe one receiver.
        proxy.sig3.unsubscribe(recv2)

        # Check that the other receiver still gets signals.
        time.sleep(0.2)
        pub1.send3(12, "B")
        sig = recv1.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig3", (12, "B"), 1))
        self.assertFalse(recv2.has_signal_ready())

        # Resubscribe, then unsubscribe the other receiver.
        proxy.sig3.subscribe(recv2)
        proxy.sig3.unsubscribe(recv1)

        # Check that signals are still correctly delivered.
        time.sleep(0.2)
        pub1.send3(13, "C")
        sig = recv2.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig3", (13, "C"), 1))
        self.assertFalse(recv1.has_signal_ready())

        # Unsubscribe the remaining receiver, then immediately resubscribe.
        proxy.sig3.unsubscribe(recv2)
        proxy.sig3.subscribe(recv1)

        # Check that signals are still correctly delivered.
        pub1.send3(14, "D")
        sig = recv1.get_next_signal(timeout=0.2)
        self.assertEqual(sig, ("context1", "pub1", "sig3", (14, "D"), 2))
        self.assertFalse(recv2.has_signal_ready())


class TestRemotePubSubQmi(unittest.TestCase):
    """Test publish/subscribe between contexts, created with qmi.start() instead of QMI_Context()."""

    def setUp(self):

        # Initialize two QMI contexts. Use random numbers to avoid conflicts on server between contexts.
        random_port = random.randint(10000, 30000)  # dynamic port numbers
        random_context = random.randint(3, 100)
        self.random_context_1 = f"context{random_context}"
        self.random_context_2 = f"context{random_context + 1}"
        context_config = {self.random_context_1: {"tcp_server_port": random_port},
                  self.random_context_2: {"tcp_server_port": random_port + 1}}
        config = CfgQmi(
            contexts={
                self.random_context_1: CfgContext(tcp_server_port=random_port),
                self.random_context_2: CfgContext()
            }
        )
        self.context3 = QMI_Context(self.random_context_1, config)
        self.context3.start()
        qmi.start(self.random_context_2, context_cfg=context_config)
        # Create publisher in context3.
        self.pub1 = self.context3.make_rpc_object("pub1", MyPublisher)

    def tearDown(self):
        self.context3.stop()
        qmi.stop()

    def test_pubsub_qmi_get(self):
        """Publish and receive signals between contexts."""
        # The "local" context started in setUp finds and connects to self.context3.
        context = qmi.context().discover_peer_contexts(context_name_filter="context*")
        for ctx in context:
            if ctx[0] == self.random_context_1:
                break

        proxy = qmi.get_rpc_object(f"{self.random_context_1}.pub1", auto_connect=True, host_port=ctx[1])
        # Check that context4 can see the signals from context3.
        sigs = proxy.get_signals()
        expect_sigs = {
            SignalDescription("sig1", ()),
            SignalDescription("sig2", (int,)),
            SignalDescription("sig3", (int, str))
        }
        self.assertEqual(set(sigs), expect_sigs)

        # Create signal receiver queue.
        recv1 = QMI_SignalReceiver()
        recv2 = QMI_SignalReceiver()
        recv3 = QMI_SignalReceiver()

        # Subscribe to signals.
        proxy.sig1.subscribe(recv1)
        proxy.sig2.subscribe(recv2)
        proxy.sig3.subscribe(recv3)

        self.pub1.send1()
        self.pub1.send2()
        self.pub1.send3(12, "C")

        # Wait until remote signals are delivered (if any).
        for _ in range(100):
            if not (recv1.has_signal_ready() and recv2.has_signal_ready() and recv3.has_signal_ready()):
                time.sleep(0.1)

            else:
                break

        # Check that signals are received.
        self.assertTrue(recv1.has_signal_ready())
        self.assertEqual(recv1.get_queue_length(), 1)
        sig = recv1.get_next_signal()
        self.assertEqual(sig, (self.random_context_1, "pub1", "sig1", (), 0))

        self.assertTrue(recv2.has_signal_ready())
        self.assertEqual(recv2.get_queue_length(), 1)
        sig = recv2.get_next_signal()
        self.assertEqual(sig, (self.random_context_1, "pub1", "sig2", (24,), 0))

        self.assertTrue(recv3.has_signal_ready())
        self.assertEqual(recv3.get_queue_length(), 1)
        sig = recv3.get_next_signal()
        self.assertEqual(sig, (self.random_context_1, "pub1", "sig3", (12, "C"), 0))

        # Unsubscribe from remote signal.
        proxy.sig1.unsubscribe(recv1)

        # Publish signals.
        self.pub1.send2()
        self.pub1.send3(22, "D")

        # Wait until remote signals are delivered (if any).
        for _ in range(100):
            if not (recv2.has_signal_ready() and recv3.has_signal_ready()):
                time.sleep(0.1)

            else:
                break

        # Check that local signals are received for receivers 2 and 3, but not for 1.
        self.assertFalse(recv1.has_signal_ready())
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            recv1.get_next_signal()

        self.assertTrue(recv2.has_signal_ready())
        self.assertEqual(recv2.get_queue_length(), 1)
        sig = recv2.get_next_signal()
        self.assertEqual(sig, (self.random_context_1, "pub1", "sig2", (24,), 1))

        self.assertTrue(recv3.has_signal_ready())
        self.assertEqual(recv3.get_queue_length(), 1)
        sig = recv3.get_next_signal()
        self.assertEqual(sig, (self.random_context_1, "pub1", "sig3", (22, "D"), 1))


if __name__ == "__main__":
    unittest.main()
