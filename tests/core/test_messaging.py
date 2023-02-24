#! /usr/bin/env python3

import logging
import time
import unittest
from unittest.mock import ANY

from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.context import QMI_Context
from qmi.core.messaging import QMI_Message, QMI_MessageHandler, QMI_MessageHandlerAddress
from qmi.core.exceptions import QMI_MessageDeliveryException


logging.getLogger().setLevel(logging.CRITICAL)


class TestMessage(QMI_Message):
    """Basic test message."""
    def __init__(self, source_address: QMI_MessageHandlerAddress, destination_address: QMI_MessageHandlerAddress, value):
        super().__init__(source_address, destination_address)
        self.value = value


class TestMessageHandler(QMI_MessageHandler):
    """Message handler mock for testing purposes."""
    def __init__(self, name):
        super().__init__(name)
        self.received = set()
        self.last_message = None

    def handle_message(self, message):
        assert message.value not in self.received
        self.received.add(message.value)
        self.last_message = message


class TestBasicMessaging(unittest.TestCase):
    """Test basic message sending and handling between contexts."""

    def setUp(self):
        # Start three contexts.

        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0),
                "c2": CfgContext(tcp_server_port=0),
                "c3": CfgContext(tcp_server_port=0)
            }
        )

        c1 = QMI_Context("c1", config)
        c1.start()
        c1_port = c1.get_tcp_server_port()

        c2 = QMI_Context("c2", config)
        c2.start()
        c2_port = c2.get_tcp_server_port()

        c3 = QMI_Context("c3", config)
        c3.start()
        c3_port = c3.get_tcp_server_port()

        # Note: Connecting to "localhost" on Windows can give 1 second delay
        # because IPv6 is attempted before IPv4.
        # This problem does not occur when connecting to "127.0.0.1".

        # Connect c1 to c2 and c3.
        c1.connect_to_peer("c2", "localhost:{}".format(c2_port))
        c1.connect_to_peer("c3", "127.0.0.1:{}".format(c3_port))

        # Connect c2 to c1.
        c2.connect_to_peer("c1", "127.0.0.1:{}".format(c1_port))

        self.c1 = c1
        self.c2 = c2
        self.c3 = c3

    def tearDown(self):
        self.c1.stop()
        self.c2.stop()
        self.c3.stop()

        self.c1 = None
        self.c2 = None
        self.c3 = None

    def test_delivery(self):
        """Basic message delivery."""
        mh1 = TestMessageHandler(QMI_MessageHandlerAddress("c1", "mh1"))
        mh2 = TestMessageHandler(QMI_MessageHandlerAddress("c2", "mh2"))
        mh3 = TestMessageHandler(QMI_MessageHandlerAddress("c3", "mh3"))

        self.c1.register_message_handler(mh1)
        self.c2.register_message_handler(mh2)
        self.c3.register_message_handler(mh3)

        expect_1 = set()
        expect_2 = set()
        expect_3 = set()

        for r in range(1, 4):
            if r == 1:
                sendctx = self.c2
                sender = mh2
                receiver = mh1
                expect_1.add(r)
            elif r == 2:
                sendctx = self.c1
                sender = mh1
                receiver = mh2
                expect_2.add(r)
            elif r == 3:
                sendctx = self.c1
                sender = mh1
                receiver = mh3
                expect_3.add(r)

            msg = TestMessage(sender.address, receiver.address, r)
            sendctx.send_message(msg)

        time.sleep(0.3)

        self.c1.unregister_message_handler(mh1)
        self.c2.unregister_message_handler(mh2)
        self.c3.unregister_message_handler(mh3)

        self.assertEqual(expect_1, mh1.received)
        self.assertEqual(expect_2, mh2.received)
        self.assertEqual(expect_3, mh3.received)

    def test_unroutable_message(self):
        """Undeliverable messages."""
        mh1 = TestMessageHandler(QMI_MessageHandlerAddress("c1", "mh1"))
        mh3 = TestMessageHandler(QMI_MessageHandlerAddress("c3", "mh3"))

        self.c1.register_message_handler(mh1)
        self.c3.register_message_handler(mh3)

        # c3 can not send messages directly to c1 (because it never connected to c1)
        msg = TestMessage(mh3.address, mh1.address, 1)
        with self.assertRaises(QMI_MessageDeliveryException):
            self.c3.send_message(msg)

        self.c1.unregister_message_handler(mh1)
        self.c3.unregister_message_handler(mh3)

    def test_local_alias(self):
        """Local aliases."""
        mh1 = TestMessageHandler(QMI_MessageHandlerAddress("c1", "mh1"))
        mh3 = TestMessageHandler(QMI_MessageHandlerAddress("c3", "mh3"))

        self.c1.register_message_handler(mh1)
        self.c3.register_message_handler(mh3)

        # c1 can send directly to c3
        msg = TestMessage(mh1.address, mh3.address, 1)
        self.c1.send_message(msg)

        time.sleep(0.1)

        # c3 will receive the message with source address renamed to its local alias for c1
        self.assertIsNotNone(mh3.last_message)
        self.assertTrue(mh3.last_message.source_address.context_id.startswith("$"))
        self.assertEqual(mh3.last_message.source_address.object_id, mh1.address.object_id)

        # c3 can send a message to its local alias for c1
        msg = TestMessage(mh3.address, mh3.last_message.source_address, 2)
        self.c3.send_message(msg)

        time.sleep(0.1)

        # c1 will receive the message
        self.assertIsNotNone(mh1.last_message)
        self.assertEqual(mh1.last_message.source_address, mh3.address)

        self.c1.unregister_message_handler(mh1)
        self.c3.unregister_message_handler(mh3)


class TestUdpMessaging(unittest.TestCase):
    """Test UDP message handling."""

    def setUp(self):
        # Create two contexts.
        configA = CfgQmi(
            workgroup="qmi_ut_wgA",
            contexts={
                "foo": CfgContext(tcp_server_port=60001),
                "bar": CfgContext(tcp_server_port=60002)
            }
        )

        configB = CfgQmi(
            workgroup="qmi_ut_wgB",
            contexts={
                "baz": CfgContext(tcp_server_port=60003)
            }
        )

        ctx_foo = QMI_Context("foo", configA)
        ctx_foo.start()

        ctx_bar = QMI_Context("ctx_bar", configA)
        ctx_bar.start()

        ctx_baz = QMI_Context("ctx_baz", configB)
        ctx_baz.start()

        self.ctx_foo = ctx_foo
        self.ctx_bar = ctx_bar
        self.ctx_baz = ctx_baz

    def tearDown(self):
        self.ctx_foo.stop()
        self.ctx_bar.stop()
        self.ctx_baz.stop()

        self.ctx_foo = None
        self.ctx_bar = None
        self.ctx_baz = None

    def test_discovery_default(self):
        """Basic discovery with default options. It should find only the contexts with the same workgroup name as
        ctx_foo itself has (the default workgroup name is its own context's workgroup name)."""
        peers = self.ctx_foo.discover_peer_contexts()
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertNotIn(("ctx_baz", ANY), peers)

    def test_discovery_all(self):
        """Discovery with setting key character '*' to find all workgroup names"""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter='*')
        self.assertNotIn(("ctx_foo", ANY), peers)  # That's me, not a peer
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertIn(("ctx_baz", ANY), peers)

    def test_discovery_workgroup_filter1(self):
        """Test workgroup filtering."""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter="qmi_ut_wg?")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertIn(("ctx_baz", ANY), peers)

    def test_discovery_workgroup_filter2(self):
        """Test workgroup filtering."""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter="qmi_ut_*")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertIn(("ctx_baz", ANY), peers)

    def test_discovery_workgroup_filter3(self):
        """Test workgroup filtering."""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter="qmi_ut_*A")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertNotIn(("ctx_baz", ANY), peers)

    def test_discovery_context_filter1(self):
        """Test context filtering."""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter='*', context_name_filter="ctx_ba?")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertIn(("ctx_baz", ANY), peers)

    def test_discovery_context_filter2(self):
        """Test context filtering."""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter='*', context_name_filter="ctx_b*")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertIn(("ctx_baz", ANY), peers)

    def test_discovery_context_filter3(self):
        """Test context filtering."""
        peers = self.ctx_baz.discover_peer_contexts(workgroup_name_filter='*', context_name_filter="ctx_b*")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertNotIn(("ctx_baz", ANY), peers)

    def test_discovery_context_filter4(self):
        """Test context filtering."""
        peers = self.ctx_foo.discover_peer_contexts(workgroup_name_filter='*', context_name_filter="ctx_bar")
        self.assertNotIn(("ctx_foo", ANY), peers)
        self.assertIn(("ctx_bar", ANY), peers)
        self.assertNotIn(("ctx_baz", ANY), peers)


if __name__ == "__main__":
    unittest.main()
