#! /usr/bin/env python3

"""Test QMI_Transport functionality."""
import os, sys
import socket
import asyncio
import threading
import time
import unittest.mock
import warnings
import random
import string

import vxi11

import qmi
import qmi.core.exceptions
import qmi.core.transport
from qmi.core.transport import (
    QMI_SocketTransport,
    QMI_UdpTransport,
    QMI_TcpTransport,
    QMI_SerialTransport,
    QMI_Vxi11Transport,
    QMI_UsbTmcTransport
)
from qmi.core.transport import create_transport, list_usbtmc_transports
from qmi.core.instrument import QMI_Instrument
from qmi.core.context import QMI_Context
from qmi.core.rpc import rpc_method
from qmi.utils.context_managers import open_close

from tests.core.pyvisa_stub import ResourceManager, visa_str_1, visa_str_3


class Dummy_USBTMCInstrument(QMI_Instrument):
    """Dummy Instrument driver using USBTMC transport."""

    USB_VENDOR_ID = 0x1313
    USB_PRODUCT_ID = 0x8076

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        with unittest.mock.patch("usb.core.find"):
            self._transport = create_transport(transport)

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def get_idn(self) -> None:
        return


class TestQmiTransportFactory(unittest.TestCase):
    """Test QMI Transport factory."""

    def setUp(self):
        # Create UDP server socket.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        self.server_sock.settimeout(10)
        self.server_host, self.server_port = "localhost", 65000
        self.server_sock.bind((self.server_host, self.server_port))

        # Create TCP client socket.
        self.client_sock = socket.socket()
        self.client_sock.settimeout(10)
        self.client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.client_sock.bind(("", 0))
        self.client_sock.listen(5)
        (self.client_host, self.client_port) = self.client_sock.getsockname()

    def tearDown(self):
        try:
            self.server_sock.close()
        finally:
            self.client_sock.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_factory_serial(self, mock):
        trans = create_transport("serial:/dev/ttyS0:baudrate=9600")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="/dev/ttyS0",
                                     baudrate=9600)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_factory_serial_attributes(self, mock):
        trans = create_transport("serial:COM3:baudrate=115200:bytesize=7:parity=E:stopbits=2:rtscts=True")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="COM3",
                                     baudrate=115200,
                                     bytesize=7,
                                     parity="E",
                                     rtscts=True,
                                     stopbits=2)

    def test_factory_udp(self):
        async def the_call():
            # Async function for not sending the message "too early" so that it won't get lost
            time.sleep(0.1)
            self.server_sock.settimeout(None)
            self.server_sock.sendto(b"aap noot\n", trans._address)
            l = asyncio.get_running_loop()
            l.stop()

        # Create UDP transport.
        with open_close(QMI_UdpTransport("localhost", int(self.server_port) - 1)) as trans:

            # Send some bytes from server to transport.
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                asyncio.set_event_loop(loop)

            loop.run_until_complete(the_call())
            # Receive message through transport.
            data = trans.read_until(b"\n", timeout=1.0)
            self.assertEqual(data, b"aap noot\n")

            if loop.is_running():
                loop.close()

            w_data = b"aap noot\n"
            trans.write(w_data)
            data = trans.read(len(w_data))
            self.assertEqual(data, w_data)

        self.server_sock.close()

    def test_factory_tcp(self):
        # Create TCP transport.
        with open_close(create_transport(f"tcp:localhost:{self.client_port}")) as trans:
            # Accept the connection on client side.
            (client_conn, peer_address) = self.client_sock.accept()
            client_conn.settimeout(1.0)

            # Send some bytes from client to transport.
            client_conn.sendall(b"aap noot\n")

            # Receive message through transport.
            data = trans.read_until(b"\n", timeout=1.0)
            self.assertEqual(data, b"aap noot\n")

        # Check connection closed on server side.
        data = client_conn.recv(100)
        self.assertEqual(data, b"")
        client_conn.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_parse_serial_basic(self, mock):
        trans = create_transport("serial:/dev/ttyS0:baudrate=9600")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="/dev/ttyS0",
                                     baudrate=9600)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_parse_serial_attrs(self, mock):
        trans = create_transport("serial:COM3:baudrate=120:bytesize=7:parity=E:stopbits=1.5:rtscts=True")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="COM3",
                                     baudrate=120,
                                     bytesize=7,
                                     parity="E",
                                     stopbits=1.5,
                                     rtscts=True)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_parse_serial_defaults(self, mock):
        trans = create_transport("serial:/dev/ttyUSB0",
                                 {"baudrate": 115200,
                                  "bytesize": 8,
                                  "parity": "N",
                                  "stopbits": 1.0,
                                  "rtscts": False})
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="/dev/ttyUSB0",
                                     baudrate=115200,
                                     bytesize=8,
                                     parity="N",
                                     stopbits=1.0,
                                     rtscts=False)

    def test_parse_serial_bad_attrtype(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("serial:/dev/ttyS0:baudrate=fast")

    def test_parse_serial_bad_booltype(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("serial:/dev/ttyS0:baudrate=115200:rtscts=0")

    def test_parse_serial_bad_attrname(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("serial:/dev/ttyS0:spin=up")

    def test_parse_serial_missing_device(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("serial")

    def test_parse_bad_type(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("digital:/dev/ttyS0")

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_basic(self, mock):
        trans = create_transport("tcp:localhost:1234")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host="localhost", port=1234)

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_ipv4(self, mock):
        trans = create_transport("tcp:192.168.1.222:5000")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host="192.168.1.222", port=5000)

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_ipv6(self, mock):
        trans = create_transport("tcp:[2620:0:2d0:200::8]:5000")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host="2620:0:2d0:200::8", port=5000)

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_ipv6_range(self, mock):
        trans = create_transport("tcp:[ 2001:db8:1234::/48]:5000")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host=" 2001:db8:1234::/48", port=5000)

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_attrs(self, mock):
        trans = create_transport("tcp:localhost:1234:connect_timeout=1")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host="localhost", port=1234, connect_timeout=1.0)

    def test_parse_tcp_missing_port(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("tcp:localhost")

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_default_port(self, mock):
        trans = create_transport("tcp:localhost", {"port": 5000})
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host="localhost", port=5000)

    @unittest.mock.patch("qmi.core.transport.QMI_TcpTransport")
    def test_parse_tcp_default_port_override(self, mock):
        trans = create_transport("tcp:localhost:21", {"port": 5000})
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(host="localhost", port=21)

    @unittest.mock.patch("qmi.core.transport.QMI_Vxi11Transport")
    def test_parse_vxi11(self, mock):
        trans = create_transport("vxi11:localhost")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_with(host="localhost")


class TestTransportOpenWithDummyInstrument(unittest.TestCase):
    """Test various 'open' cases with a dummy instrument """
    def setUp(self) -> None:
        # Create TCP server socket.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.server_sock.bind(("127.0.0.1", 0))
        (server_host, self.server_port) = self.server_sock.getsockname()
        self.server_sock.listen(5)
        # Create TCP transport.
        self.trans = create_transport("tcp:localhost:%d" % self.server_port)

    def tearDown(self) -> None:
        self.server_sock.close()
        if self.trans._is_open:
            self.trans.close()

    def test_trying_to_open_prototype_directly(self):
        transport = qmi.core.transport.QMI_Transport()
        with self.assertRaises(NotImplementedError):
            transport.open()

        with self.assertRaises(NotImplementedError):
            transport._open_transport()

    def test_trying_to_open_transport_via_private(self):
        expected = None
        res = self.trans._open_transport()
        self.assertEqual(res, expected)
        with self.assertRaises(qmi.core.exceptions.QMI_InvalidOperationException):
            self.trans.discard_read()

    def test_trying_to_open_already_opened_transport(self):
        self.trans.open()
        with self.assertRaises(qmi.core.exceptions.QMI_InvalidOperationException):
            self.trans.open()

    def test_trying_to_act_on_closed_instrument(self):
        with self.assertRaises(qmi.core.exceptions.QMI_InvalidOperationException):
            self.trans.discard_read()


class TestQmiTransportParsing(unittest.TestCase):
    """Test QMI Transport parsing on different OS."""

    def setUp(self):
        # Create TCP server socket.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.server_sock.bind(("127.0.0.1", 0))
        (server_host, self.server_port) = self.server_sock.getsockname()
        self.server_sock.listen(5)

    def tearDown(self):
        self.server_sock.close()

    if "linux" in sys.platform or "darwin" in sys.platform:
        def test_parse_usbtmc(self):
            serialnr = "XYZ"
            vendorid = 0x0699
            productid = 0x3000
            desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

        def test_parse_usbtmc_non_hex(self):
            serialnr = "XYZ"
            vendorid = 1689
            productid = 12288
            desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

        def test_parse_usbtmc_defaults(self):
            serialnr = "XYZ"
            vendorid = 0xa1
            productid = 0xb2
            desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

        def test_parse_gpib_not_for_linux(self):
            primary_addr = 1
            expected_text = "Gpib transport descriptor is for NI GPIB-USB-HS device and Windows-only."

            with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException) as exc:
                create_transport(f"gpib:{primary_addr}")

            self.assertEqual(expected_text, str(exc.exception))

    elif sys.platform.startswith("win") or "msys" in sys.platform:
        # Remove the possibility of import error of pyvisa
        import tests.core.pyvisa_stub
        sys.modules["pyvisa"] = tests.core.pyvisa_stub
        sys.modules["pyvisa.errors"] = tests.core.pyvisa_stub.errors

        def test_parse_usbtmc(self):
            serialnr = "XYZ"
            vendorid = 0x0699
            productid = 0x3000
            transport_str = f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}"
            if os.getenv("LIBUSBPATH"):
                desc = create_transport(transport_str)

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(transport_str)

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

        def test_parse_usbtmc_non_hex(self):
            serialnr = "XYZ"
            vendorid = 1689
            productid = 12288
            transport_str = f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}"
            if os.getenv("LIBUSBPATH"):
                desc = create_transport(transport_str)

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(transport_str)

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, productid)
            self.assertEqual(desc.vendorid, vendorid)

        def test_parse_usbtmc_defaults(self):
            serialnr = "XYZ"
            vendorid = 0xa1
            productid = 0xb2
            transport_str = f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}"
            if os.getenv("LIBUSBPATH"):
                desc = create_transport(transport_str)

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(transport_str)

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

        def test_parse_gpib(self):
            board = 0
            primary_addr = 1
            secondary_addr = 2
            timeout = 3.0
            transport_str = f"gpib:board={board}:{primary_addr}:secondary_addr={secondary_addr}:connect_timeout={timeout}"

            if os.getenv("LIBUSBPATH"):
                desc = create_transport(transport_str)

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(transport_str)

            self.assertEqual(desc._board, board)
            self.assertEqual(desc._primary_addr, primary_addr)
            self.assertEqual(desc._secondary_addr, secondary_addr)
            self.assertEqual(desc._connect_timeout, timeout)

        def test_parse_gpib_defaults(self):
            primary_addr = 1
            transport_str = f"gpib:{primary_addr}"
            default_timeout = 30.0

            if os.getenv("LIBUSBPATH"):
                desc = create_transport(transport_str)

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(transport_str)

            self.assertIsNone(desc._board)
            self.assertEqual(primary_addr, desc._primary_addr)
            self.assertIsNone(desc._secondary_addr)
            self.assertEqual(default_timeout, desc._connect_timeout)

    @unittest.mock.patch("qmi.core.transport.QMI_Vxi11Transport")
    def test_parse_vxi11(self, mock):
        trans = create_transport("vxi11:localhost")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_with(host="localhost")


class TestQmiSocketTransportBase(unittest.TestCase):
    """Test QMI_SocketTransportBase class."""

    def setUp(self):
        # Filter out warnings about unclosed sockets
        warnings.filterwarnings("ignore", "unclosed", ResourceWarning)

    def test_host_validation(self):
        """Try to create a base transport with invalid hosts. See that exceptions are raised."""
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SocketTransport("invalid_hostname", 22)

        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SocketTransport("192.168.1.300", 22)

    def test_port_validation(self):
        """Try to create a base transport with invalid port numbers. See that exceptions are raised."""
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SocketTransport("localhost", 0)

        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SocketTransport("localhost", 100000)

    def test_write_not_implemented_error(self):
        """Test QMI_SocketTransportBase.write() is not implemented in the base class."""
        # Create UDP transport connected to local server.
        trans = QMI_SocketTransport("localhost", 64500)
        trans.open()

        # Try to send something through the transport.
        with self.assertRaises(NotImplementedError):
            trans.write(b"")


class TestQmiUdpTransport(unittest.TestCase):
    """Test QMI_UdpTransport class."""

    def setUp(self):
        # Filter out warnings about unclosed sockets
        warnings.filterwarnings("ignore", "unclosed", ResourceWarning)

        # Create UDP server socket.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_host, self.server_port = "localhost", 65000
        self.server_sock.bind((self.server_host, self.server_port))

    def tearDown(self):
        self.server_sock.close()

    def test_cannot_use_qmi_transmission_udp_port(self):
        # Test that port number 35999 is reserved for QMI packets.
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_UdpTransport("localhost", QMI_Context.DEFAULT_UDP_RESPONDER_PORT)

    def test_udp_basic(self):
        """Test basic functionalities of the UDP transport."""
        address = "127.0.0.1" + ':' + str(self.server_port - 1)
        expected_transport_string = f"QMI_UdpTransport(remote={address})"
        # Create UDP transport bound to local server.
        with open_close(QMI_UdpTransport("localhost", int(self.server_port) - 1)) as trans:
            # Check the string name of the instance
            self.assertEqual(expected_transport_string, str(trans))

            # Send some bytes back from server to transport.
            testmsg = b"answer"
            self.server_sock.sendto(testmsg, trans._address)

            # Receive bytes through the transport.
            data = trans.read(len(testmsg), timeout=1.0)
            self.assertEqual(testmsg, data)

            # Try to receive more bytes; wait for timeout.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(10, timeout=1.0)

            # Send more bytes back from server to transport.
            self.server_sock.sendto(b"more bytes", trans._address)

            # Receive the first bunch of bytes.
            data = trans.read(5, timeout=1.0)
            self.assertEqual(data, b"more ")

            # Receive the remaining bytes in a separate call.
            # Try to receive more bytes than are available to hit timeout.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(10, timeout=1.0)

            # Remaining bytes are still in buffer after failed read above.
            # Receive some of them.
            data = trans.read(3, timeout=1.0)
            self.assertEqual(data, b"byt")

            # Send more bytes from server to transport.
            self.server_sock.sendto(b"first line\nsecond line", trans._address)

            # Receive the first line.
            # It starts with remaining bytes from the previous send.
            data = trans.read_until(b"\n", timeout=1.0)
            self.assertEqual(data, b"esfirst line\n")

            # Receive first word of the second line.
            data = trans.read(7, timeout=None)
            self.assertEqual(data, b"second ")

            # Try to receive a second line; this should hit the timeout.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read_until(b"\n", timeout=1.0)

            # Send message terminator for the second line.
            self.server_sock.sendto(b"\n", trans._address)

            # Receive second line (note first word was already received).
            data = trans.read_until(b"\n", timeout=1.0)
            self.assertEqual(data, b"line\n")

            # Test with a 2-character terminator.
            self.server_sock.sendto(b"the;last\nline;\n", trans._address)
            data = trans.read_until(b";\n", timeout=1.0)
            self.assertEqual(data, b"the;last\nline;\n")

            # Send some bytes through the transport.
            testmsg = b"aap noot"
            trans.write(testmsg)

            # Receive bytes one-by-one.
            buf = bytearray()
            while len(buf) < len(testmsg):
                data = trans.read_until_timeout(1, timeout=1.0)
                self.assertNotEqual(data, b"")
                buf.extend(data)

            self.assertEqual(buf, testmsg)

    def test_udp_large_packages(self):
        """Test for large package sizes > 4096 bytes, which is regular UDP limit."""
        # Create UDP transport connected to local server.
        with open_close(QMI_UdpTransport("127.0.0.1", self.server_port - 1)) as trans:
            # The transport should fail if sent package is > 4kB, as UDP is not set to handle larger packages.
            bs_size = 5000  # Normal max 2**12 bytes (- headers)
            s = ''.join(random.choices(string.ascii_uppercase + string.digits, k=bs_size))

            # Send some bytes from server to transport.
            self.server_sock.sendto(s.encode(), trans._address)

            try:
                # Try to receive only a part of the bytes (triggers exception).
                with self.assertRaises(qmi.core.exceptions.QMI_RuntimeException):
                    read = trans.read(100, timeout=1.0)  # The `read` will set the size to 4096 in any case

            except AssertionError as ass:
                # Catch this as some servers apparently fragment the message to be max of 4096 bytes, so it does not crash
                if len(read) != 100:
                    raise AssertionError from ass

                trans.discard_read()

            async def the_call():
                # Async function for not sending the message "too early" so that it won't get lost
                time.sleep(0.1)
                self.server_sock.sendto(s.encode(), trans._address)
                l = asyncio.get_running_loop()
                l.stop()

            # Send some bytes from server to transport.
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                asyncio.set_event_loop(loop)

            loop.run_until_complete(the_call())
            try:
                # The same should happen with read_until (triggers exception).
                with self.assertRaises(qmi.core.exceptions.QMI_RuntimeException):
                    trans.read_until(b"\n", timeout=1.0)

            except qmi.core.exceptions.QMI_TimeoutException as tim:
                # Catch this as some servers apparently fragment the message to be max of 4096 bytes, so it does not crash
                if len(trans._read_buffer) != 4096:
                    raise AssertionError from tim

                trans.discard_read()

            if loop.is_running():
                loop.close()

            # Send some bytes from server to transport.
            self.server_sock.sendto(s.encode(), trans._address)

            # With 'read' it is possible to set to read even larger packets. See that it works.
            # The caller does need to know the exact packet size in this case, though.
            data = trans.read(bs_size, timeout=1.0)
            self.assertEqual(data.decode(), s)

    def test_remote_close(self):
        """Test the data is received even after remote is closed."""
        # Create UDP transport connected to local server.
        with open_close(QMI_UdpTransport("127.0.0.1", self.server_port - 1)) as trans:
            # Send some bytes from server to transport.
            self.server_sock.sendto(b"some bytes", trans._address)

            # Close connection on server side.
            self.server_sock.close()

            # Receive bytes through transport.
            data = trans.read(4, timeout=1.0)
            self.assertEqual(data, b"some")

            # Try to receive more bytes than are available (triggers exception).
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(100, timeout=1.0)

            # Try to receive a line (also triggers exception).
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read_until(b"\n", timeout=0)

            # Receive the remaining bytes.
            data = trans.read(6, timeout=None)
            self.assertEqual(data, b" bytes")

            # Try to read another byte. Should raise exception.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(1, timeout=0.0)

    def test_read_until_buffer_already_filled(self):
        """Test that `read_until()` returns immediately if message terminator is already in read buffer."""
        # Create UDP transport bound to local server.
        with open_close(QMI_UdpTransport("localhost", self.server_port - 1)) as trans:
            # Set some bytes with message terminator into read buffer.
            testmsg = b"hello\n"
            trans._read_buffer = testmsg
            # Read and assert
            data = trans.read_until(b"\n", timeout=0.2)
            self.assertEqual(testmsg, data)

    def test_read_until_exceptions(self):
        """Test for exceptions raised with `read_until()` with missing terminal character and too large packet."""
        # Create UDP transport bound to local server.
        with open_close(QMI_UdpTransport("localhost", self.server_port - 1)) as trans:
            # Send some bytes from server to transport.
            testmsg = b"hello there"
            self.server_sock.sendto(testmsg, trans._address)

            # Receive bytes through the transport. But no end character inputted -> get timeout error.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read_until(b"\n", timeout=0.2)

            # See that the data read until timeout remains in the read buffer.
            self.assertEqual(testmsg, trans._read_buffer)

            # The transport should fail if sent package is > 4kB, as UDP is not set to handle larger packages.
            bs_size = 5000  # Normal max 2**12 bytes (- headers)
            s = ''.join(random.choices(string.ascii_uppercase + string.digits, k=bs_size))

            # Send some bytes from server to transport.
            self.server_sock.sendto(s.encode(), trans._address)

            try:
                # Receive bytes through the transport. But packet too large.
                with self.assertRaises(qmi.core.exceptions.QMI_RuntimeException):
                    trans.read_until(b"\n", timeout=0.2)

            except qmi.core.exceptions.QMI_TimeoutException as tim:
                # Catch this as some servers apparently fragment the message to be max of 4096 bytes, so it does not crash
                if len(trans._read_buffer) != 4107:
                    raise AssertionError from tim

    def test_read_until_timeout(self):
        """Test `read_until_timeout` until timeout."""
        # Create UDP transport connected to local server.
        with open_close(QMI_UdpTransport("localhost", self.server_port - 1)) as trans:
            # Send some bytes from server to transport.
            testmsg = b"hello there"
            self.server_sock.sendto(testmsg, trans._address)

            # Receive bytes through the transport.
            data = trans.read_until_timeout(len(testmsg), timeout=1.0)
            self.assertEqual(data, testmsg)

            # Try to receive more bytes; wait for timeout.
            data = trans.read_until_timeout(10, timeout=1.0)
            self.assertEqual(data, b"")

            # Send more bytes back from server to transport.
            self.server_sock.sendto(b"more bytes", trans._address)

            # Receive the first bunch of bytes.
            data = trans.read_until_timeout(5, timeout=1.0)
            self.assertEqual(data, b"more ")

            # Try to receive more bytes than are available to get partial data
            # after timeout.
            data = trans.read_until_timeout(10, timeout=1.0)
            self.assertEqual(data, b"bytes")

            # Send more bytes from server to transport.
            self.server_sock.sendto(b"last data", trans._address)

            # Close connection on server side.
            self.server_sock.close()

            # Receive bytes through transport.
            data = trans.read_until_timeout(4, timeout=1.0)
            self.assertEqual(data, b"last")

            # Receive remaining bytes (results in partial answer).
            data = trans.read_until_timeout(100, timeout=1.0)
            self.assertEqual(data, b" data")

            # Try to read more bytes. Should raise timeout exception in UDP.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(100, timeout=1.0)

    def test_discard_read(self):
        """Test discarding read data."""
        # Create UDP transport connected to local server.
        with open_close(QMI_UdpTransport("localhost", self.server_port + 1)) as trans:
            # Send some bytes from server to transport.
            testmsg = b"hello there"
            self.server_sock.sendto(testmsg, trans._address)

            # Discard bytes through the transport.
            trans.discard_read()
            # Try to read, which should now except as the input buffer was discarded
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(1, 0.0)

            # The transport should fail if sent package is > 4kB, as UDP is not set to handle larger packages.
            bs_size = 5000  # Normal max 2**12 bytes (- headers)
            s = ''.join(random.choices(string.ascii_uppercase + string.digits, k=bs_size))

            # Send some bytes from server to transport.
            self.server_sock.sendto(s.encode(), trans._address)

            # Try to discard. This should activate the OSError except catch.
            trans.discard_read()

            # Try to read, which should now except as the input buffer was discarded
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(1, 0.0)

    def test_client_non_existing(self):
        """Test that non-existing UDP client raises an error."""
        # Try to create a server for non-existing client host name.
        trans = QMI_UdpTransport("imaginary-host", 5123)
        with self.assertRaises(OSError):
            trans.open()

    def test_opening_twice_error(self):
        """The same UDP host and port should not be possible to open twice."""
        # Create UDP transport connected to local server.
        with open_close(QMI_UdpTransport("localhost", self.server_port - 2)):
            # Try to create a second one with same number. Should raise an error.
            trans2 = QMI_UdpTransport("localhost", self.server_port - 2)
            with self.assertRaises((OSError, PermissionError)):
                trans2.open()

    def test_udp_async(self):
        """Test asynchronous data sending and receiving works, also with partial reads."""
        # Create UDP transport connected to local server.
        with open_close(QMI_UdpTransport("localhost", self.server_port - 1)) as trans:
            # Create a separate thread which sends data from the server side.
            def thread_main():
                for i in range(4):
                    time.sleep(0.5)
                    self.server_sock.sendto("tick {}".format(i).encode("ascii"), trans._address)
                    time.sleep(0.5)
                    self.server_sock.sendto("tock {}\n".format(i).encode("ascii"), trans._address)

            thread = threading.Thread(target=thread_main, name="test_transport_thread")
            thread.start()

            try:
                # Receive data through the transport (after ~ 0.5 second delay).
                data = trans.read(6, timeout=1.0)
                self.assertEqual(data, b"tick 0")

                # Receive terminated message through the transport (after delay).
                data = trans.read_until(b"\n", timeout=1.0)
                self.assertEqual(data, b"tock 0\n")

                # Receive data which arrives in 3 chunks.
                data = trans.read(15, timeout=2.0)
                self.assertEqual(data, b"tick 1tock 1\nti")

                # Receive terminated message which arrives in chunks.
                data = trans.read_until(b"\n", timeout=1.0)
                self.assertEqual(data, b"ck 2tock 2\n")

                # Receive partial data after timeout.
                data = trans.read_until_timeout(100, timeout=0.6)
                self.assertEqual(data, b"tick 3")

                # Check no further data available yet.
                with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                    trans.read_until(b"\n", timeout=0)

                # Wait until data arrives.
                data = trans.read_until(b"\n", timeout=1.0)
                self.assertEqual(data, b"tock 3\n")

                # Check no further data available.
                data = trans.read_until_timeout(1, timeout=0)
                self.assertEqual(data, b"")

            finally:
                # Clean up background thread.
                thread.join()
                # Close server side.
                self.server_sock.close()


class TestQmiTcpTransport(unittest.TestCase):
    """Test QMI_TcpTransport class."""

    def setUp(self):
        # Filter out warnings about unclosed sockets
        warnings.filterwarnings("ignore", "unclosed", ResourceWarning)
        # Create dummy non-listening TCP port.
        self.dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.dummy_sock.bind(("127.0.0.1", 0))
        (dummy_host, self.dummy_port) = self.dummy_sock.getsockname()

        # Create TCP server socket.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.server_sock.bind(("127.0.0.1", 0))
        (server_host, self.server_port) = self.server_sock.getsockname()
        self.server_sock.listen(5)

    def tearDown(self):
        self.dummy_sock.close()
        self.server_sock.close()

    def test_tcp_basic(self):
        """Test basic functionalities of TCP transport work."""
        address = "127.0.0.1" + ':' + str(self.server_port)
        expected_transport_string = f"QMI_TcpTransport(remote={address})"
        # Create TCP transport connected to local server.
        with open_close(QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)) as trans:
            # Check the string name of the instance
            self.assertEqual(expected_transport_string, str(trans))

            # Accept the connection on server side.
            (server_conn, peer_address) = self.server_sock.accept()
            server_conn.settimeout(1.0)

            # Send some bytes through the transport.
            testmsg = b"aap noot"
            trans.write(testmsg)

            # Receive bytes at the server side.
            buf = bytearray()
            while len(buf) < len(testmsg):
                data = server_conn.recv(100)
                self.assertNotEqual(data, b"")
                buf.extend(data)
            self.assertEqual(buf, testmsg)

            # Send some bytes back from server to transport.
            testmsg = b"answer"
            server_conn.sendall(testmsg)

            # Receive bytes through the transport.
            data = trans.read(len(testmsg), timeout=1.0)
            self.assertEqual(data, testmsg)

            # Try to receive more bytes; wait for timeout.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(10, timeout=1.0)

            # Send more bytes back from server to transport.
            server_conn.sendall(b"more bytes")

            # Receive the first bunch of bytes.
            data = trans.read(5, timeout=1.0)
            self.assertEqual(data, b"more ")

            # Receive the remaining bytes in a separate call.
            # Try to receive more bytes than are available to hit timeout.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read(10, timeout=1.0)

            # Remaining bytes are still in buffer after failed read above.
            # Receive some of them.
            data = trans.read(3, timeout=1.0)
            self.assertEqual(data, b"byt")

            # Send more bytes from server to transport.
            server_conn.sendall(b"first line\nsecond line")

            # Receive the first line.
            # It starts with remaining bytes from the previous send.
            data = trans.read_until(b"\n", timeout=1.0)
            self.assertEqual(data, b"esfirst line\n")

            # Receive first word of the second line.
            data = trans.read(7, timeout=None)
            self.assertEqual(data, b"second ")

            # Try to receive a second line; this should hit the timeout.
            with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                trans.read_until(b"\n", timeout=1.0)

            # Send message terminator for the second line.
            server_conn.sendall(b"\n")

            # Receive second line (note first word was already received).
            data = trans.read_until(b"\n", timeout=1.0)
            self.assertEqual(data, b"line\n")

            # Test with a 2-character terminator.
            server_conn.sendall(b"the;last\nline;\n")
            data = trans.read_until(b";\n", timeout=1.0)
            self.assertEqual(data, b"the;last\nline;\n")

        # Check upstream channel closed.
        data = server_conn.recv(100)
        self.assertEqual(data, b"")

        # Close server-side socket.
        server_conn.close()

    def test_remote_close(self):
        """Test data is received also after remote is closed"""
        # Create TCP transport connected to local server.
        with open_close(QMI_TcpTransport("127.0.0.1", self.server_port, connect_timeout=1)) as trans:
            # Accept the connection on server side.
            (server_conn, peer_address) = self.server_sock.accept()
            server_conn.settimeout(1.0)

            # Send some bytes from server to transport.
            server_conn.sendall(b"some bytes")

            # Close connection on server side.
            server_conn.close()

            # Receive bytes through transport.
            data = trans.read(4, timeout=1.0)
            self.assertEqual(data, b"some")

            # Try to receive more bytes than are available (triggers exception).
            with self.assertRaises(qmi.core.exceptions.QMI_EndOfInputException):
                trans.read(100, timeout=1.0)

            # Try to receive a line (also triggers exception).
            with self.assertRaises(qmi.core.exceptions.QMI_EndOfInputException):
                trans.read_until(b"\n", timeout=None)

            # Receive the remaining bytes.
            data = trans.read(6, timeout=None)
            self.assertEqual(data, b" bytes")

            # Try to read another byte. Should raise exception.
            with self.assertRaises(qmi.core.exceptions.QMI_EndOfInputException):
                trans.read(1, timeout=None)

    def test_read_until_buffer_already_filled(self):
        """Test that `read_until()` returns immediately if message terminator is already in read buffer."""
        # Create TCP transport connected to local server.
        with open_close(QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)) as trans:
            # Set some bytes with message terminator into read buffer.
            testmsg = b"hello\n"
            trans._read_buffer = testmsg
            # Read and assert
            data = trans.read_until(b"\n", timeout=0.2)
            self.assertEqual(testmsg, data)

    def test_read_until_timeout(self):
        """Test `read_until_timeout` until timeout."""
        # Create TCP transport connected to local server.
        with open_close(QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)) as trans:
            # Accept the connection on server side.
            (server_conn, peer_address) = self.server_sock.accept()
            server_conn.settimeout(1.0)

            # Send some bytes from server to transport.
            testmsg = b"hello there"
            server_conn.sendall(testmsg)

            # Receive bytes through the transport.
            data = trans.read_until_timeout(len(testmsg), timeout=1.0)
            self.assertEqual(data, testmsg)

            # Try to receive more bytes; wait for timeout.
            data = trans.read_until_timeout(10, timeout=1.0)
            self.assertEqual(data, b"")

            # Send more bytes back from server to transport.
            server_conn.sendall(b"more bytes")

            # Receive the first bunch of bytes.
            data = trans.read_until_timeout(5, timeout=1.0)
            self.assertEqual(data, b"more ")

            # Try to receive more bytes than are available to get partial data
            # after timeout.
            data = trans.read_until_timeout(10, timeout=1.0)
            self.assertEqual(data, b"bytes")

            # Send more bytes from server to transport.
            server_conn.sendall(b"last data")

            # Close connection on server side.
            server_conn.close()

            # Receive bytes through transport.
            data = trans.read_until_timeout(4, timeout=1.0)
            self.assertEqual(data, b"last")

            # Receive remaining bytes (results in partial answer).
            data = trans.read_until_timeout(100, timeout=1.0)
            self.assertEqual(data, b" data")

            # Try to read more bytes. Should raise exception.
            with self.assertRaises(qmi.core.exceptions.QMI_EndOfInputException):
                trans.read(100, timeout=1.0)

    def test_connect_failure(self):
        """Test connecting to non-existing or closed or unroutable host fails."""
        # Try to connect to non-existing host name.
        with self.assertRaises(OSError):
            trans = QMI_TcpTransport("imaginary-host", 5123, connect_timeout=1)
            trans.open()

        # Try to connect to closed TCP port.
        # This may trigger connection refused, or timeout if the port is firewalled.
        with self.assertRaises((OSError, qmi.core.exceptions.QMI_TimeoutException)):
            trans = QMI_TcpTransport("localhost", self.dummy_port, connect_timeout=1)
            trans.open()

        # Try to connect to unroutable IP address.
        with self.assertRaises(Exception):
            trans = QMI_TcpTransport("192.168.231.11", 5123, connect_timeout=1)
            trans.open()

    def test_tcp_async(self):
        """Test asynchronous sending and receiving data works, with partial data."""
        # Create TCP transport connected to local server.
        with open_close(QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)) as trans:
            # Accept the connection on server side.
            (server_conn, peer_address) = self.server_sock.accept()
            server_conn.settimeout(1.0)

            # Create a separate thread which sends data from the server side.
            def thread_main():
                for i in range(4):
                    time.sleep(0.5)
                    server_conn.sendall("tick {}".format(i).encode("ascii"))
                    time.sleep(0.5)
                    server_conn.sendall("tock {}\n".format(i).encode("ascii"))

            thread = threading.Thread(target=thread_main, name="test_transport_thread")
            thread.start()

            try:

                # Receive data through the transport (after ~ 0.5 second delay).
                data = trans.read(6, timeout=1.0)
                self.assertEqual(data, b"tick 0")

                # Receive terminated message through the transport (after delay).
                data = trans.read_until(b"\n", timeout=1.0)
                self.assertEqual(data, b"tock 0\n")

                # Receive data which arrives in 3 chunks.
                data = trans.read(15, timeout=2.0)
                self.assertEqual(data, b"tick 1tock 1\nti")

                # Receive terminated message which arrives in chunks.
                data = trans.read_until(b"\n", timeout=1.0)
                self.assertEqual(data, b"ck 2tock 2\n")

                # Receive partial data after timeout.
                data = trans.read_until_timeout(100, timeout=0.6)
                self.assertEqual(data, b"tick 3")

                # Check no further data available yet.
                with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
                    trans.read_until(b"\n", timeout=0)

                # Wait until data arrives.
                data = trans.read_until(b"\n", timeout=1.0)
                self.assertEqual(data, b"tock 3\n")

                # Check no further data available.
                data = trans.read_until_timeout(1, timeout=0)
                self.assertEqual(data, b"")

            finally:
                # Clean up background thread.
                thread.join()
                # Close server side.
                server_conn.close()

    def test_invalid_host(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_TcpTransport("invalid_hostname", 22)
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_TcpTransport("192.168.1.300", 22)


class TestQmiSerialTransportInit(unittest.TestCase):

    def test_correct_construction(self):
        QMI_SerialTransport("COM1", 9600)
        QMI_SerialTransport("/valid/path", 9600)
        QMI_SerialTransport("COM3", 120, bytesize=7, parity="E", stopbits=1.5)
        QMI_SerialTransport("/dev/ttyUSB0", 115200, bytesize=8, parity="N", stopbits=1.0)
        QMI_SerialTransport("/dev/ttyUSB0", 115200, bytesize=8, parity="N", stopbits=1.0, rtscts=True)

    def test_invalid_device_description(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("invalid", 9600)

    def test_invalid_baudrate(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 0)

    def test_invalid_bytesize(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 9600, bytesize=4)
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 9600, bytesize=9)

    def test_invalid_parity(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 9600, parity="X")
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 9600, parity="FOO")

    def test_invalid_stopbits(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 9600, stopbits=1.4)

    def test_invalid_rtscts(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_SerialTransport("/valid/path", 9600, rtscts=3.14)

    @unittest.mock.patch("qmi.core.transport.serial.Serial", autospec=True)
    def test_correct_open_close(self, mocked_serial):
        device = "/dev/mydevice"
        baudrate = 9600
        transport = QMI_SerialTransport(device, baudrate)  # use defaults for other arguments
        transport.open()
        transport.close()

        mocked_serial.assert_called_once_with(
            device, baudrate=baudrate,
            bytesize=8, parity="N", stopbits=1.0, rtscts=False,
            timeout=QMI_SerialTransport.SERIAL_READ_TIMEOUT
        )
        mocked_serial.return_value.close.assert_called_once()


class TestQmiSerialTransportMethods(unittest.TestCase):

    def setUp(self):
        patcher = unittest.mock.patch("qmi.core.transport.serial.Serial", autospec=True)
        self.serial = patcher.start().return_value
        self.addCleanup(patcher.stop)

        self.transport = QMI_SerialTransport("/dev/mydevice", 9600)
        self.transport.open()

    def tearDown(self):
        self.transport.close()
        self.serial.close.assert_called_once()

    def test_write(self):
        data = b"hello, world!"
        self.transport.write(data)
        self.serial.write.assert_called_once_with(data)

    def test_read_blocking_immediate(self):
        data = b"hello, world!"
        nbytes = len(data)
        self.serial.read.return_value = data

        recv = self.transport.read(nbytes, timeout=None)

        self.assertEqual(recv, data)
        self.serial.read.assert_called_once_with(nbytes)

    def test_read_blocking_sequential(self):
        data = b"hello, world!"
        nbytes = len(data)
        self.serial.read.side_effect = [bytearray([d]) for d in data]

        recv = self.transport.read(nbytes, timeout=None)

        self.assertEqual(recv, data)

    def test_read_blocking_timeout(self):
        self.serial.read.return_value = bytearray([])

        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            self.transport.read(1, timeout=0.1)

    def test_read_nonblocking(self):
        data = b"hello, world!"
        nbytes = len(data)
        self.serial.in_waiting = nbytes
        self.serial.read.return_value = data

        recv = self.transport.read(nbytes, timeout=0)

        self.assertEqual(recv, data)
        self.serial.read.assert_called_once_with(nbytes)

    def test_read_timeout_retry(self):
        data = b"hello, world!"
        nbytes = len(data)
        nbytes_partial = 5

        # Helper function that only returns part of the data array on the first call and then stalls.
        def _read(n):
            _read.calls += 1
            if _read.calls == 1:
                return data[:nbytes_partial]
            else:
                return bytearray([])

        _read.calls = 0
        self.serial.read.side_effect = _read

        try:
            self.transport.read(nbytes, timeout=0.1)
        except qmi.core.exceptions.QMI_TimeoutException:
            pass  # deliberately timeout

        # The partial read should be in the buffer (no more calls to read())
        self.serial.read.reset_mock()
        recv = self.transport.read(nbytes_partial, None)
        self.assertEqual(recv, data[:nbytes_partial])
        self.serial.read.assert_not_called()

    def test_read_until_immediate(self):
        data = b"hello, world!"

        self.serial.in_waiting = len(data)
        self.serial.read.return_value = data

        recv = self.transport.read_until(b',', timeout=None)
        self.assertEqual(recv, b"hello,")

    def test_read_until_sequential(self):
        data = b"hello, world!"
        nbytes_partial = 3

        self.serial.in_waiting = nbytes_partial
        self.serial.read.side_effect = [data[:nbytes_partial]] + [bytearray([d]) for d in data[nbytes_partial:]]

        recv = self.transport.read_until(b',', timeout=None)
        self.assertEqual(recv, b"hello,")

    def test_read_until_with_timeout(self):
        self.serial.in_waiting = 1
        self.serial.read.return_value = b'a'

        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            self.transport.read_until(b',', timeout=0.1)

    def test_read_until_timeout(self):
        data = b"hello, world!"
        nbytes = len(data)
        nbytes_partial = 5

        # Helper function that only returns part of the data array on the first call and then stalls.
        def _read(n):
            _read.calls += 1
            if _read.calls == 1:
                return data[:nbytes_partial]
            else:
                return bytearray([])

        _read.calls = 0
        self.serial.read.side_effect = _read

        recv = self.transport.read_until_timeout(nbytes, timeout=0.1)
        self.assertEqual(recv, data[:nbytes_partial])

    def test_read_until_multiple(self):
        data = b"hello;world;"
        nbytes = len(data)
        self.serial.in_waiting = nbytes
        self.serial.read.return_value = data

        # Read from serial.
        recv1 = self.transport.read_until(b';', timeout=None)
        self.assertEqual(recv1, b"hello;")

        # Read from buffer.
        recv2 = self.transport.read_until(b';', timeout=None)
        self.assertEqual(recv2, b"world;")

        self.serial.read.assert_called_once_with(nbytes)

    def test_discard_read(self):
        self.transport.discard_read()
        self.serial.reset_input_buffer.assert_called_once()

    def test_read_with_discard(self):
        data = b"hello;world;"
        nbytes = len(data)
        self.serial.in_waiting = nbytes
        self.serial.read.return_value = data

        # Read from serial.
        recv1 = self.transport.read_until(b';', timeout=None)
        self.assertEqual(recv1, b"hello;")

        # Discard buffer.
        self.transport.discard_read()

        # Read will again go via serial, because buffer is empty.
        recv2 = self.transport.read_until(b';', timeout=None)
        self.assertEqual(recv2, b"hello;")

        self.serial.read.assert_has_calls([unittest.mock.call(nbytes), unittest.mock.call(nbytes)])
        self.serial.reset_input_buffer.assert_called_once()


class TestQmiUsbTmcTransport(unittest.TestCase):

    def test_correct_construction(self):
        vendorid = 0x0699
        productid = 0x3000
        serialnr = "XYZ"
        exp_trnsprt = f"QMI_UsbTmcTransport 0x{vendorid:04x}:0x{productid:04x} ({serialnr})"
        # Make two transports, one with hex input and other with int input
        trnsprt_1 = QMI_UsbTmcTransport(vendorid, productid, "XYZ")
        trnsprt_2 = QMI_UsbTmcTransport(1689, 12288, "XYZ")  # Same values but in int
        # Assert that transport string should be always formatted with hex numbers
        self.assertEqual(exp_trnsprt, str(trnsprt_1))
        self.assertEqual(exp_trnsprt, str(trnsprt_2))

    def test_invalid_vendor_id(self):
        """Test _validate_vendor_id method."""
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_UsbTmcTransport(0xfcafe, 0xbebe, "bar")

        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_UsbTmcTransport(-1, 0xbebe, "foo")

    def test_invalid_product_id(self):
        """Test _validate_product_id method."""
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_UsbTmcTransport(0xbebe, 0xfcafe, "bar")

        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_UsbTmcTransport(0xbebe, -1, "foo")

    def test_not_implemented_methods(self):
        """Test not implemented functions raise NotImplementedError"""
        transport = QMI_UsbTmcTransport(1689, 12288, "XYZ")
        with self.assertRaises(NotImplementedError):
            transport.write(b"no_data")

        with self.assertRaises(NotImplementedError):
            transport._read_message(None)

        with self.assertRaises(NotImplementedError):
            transport.list_resources()


class TestQmiVxi11TransportInit(unittest.TestCase):

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_init(self, mock: unittest.mock.Mock):
        """The init of the transport only saves the arguments, the instrument is created only at open. """
        QMI_Vxi11Transport("localhost")
        mock.assert_not_called()

    def test_init_invalid_host(self):
        """The init will raise an exception due to invalid host. """
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_Vxi11Transport("-invalid-host")

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_open(self, mock: unittest.mock.Mock):
        """Test open of device.

        Expecting:
            The instrument to be made with host.
            The instrument to be opened.
        """
        host = "localhost"
        instr = QMI_Vxi11Transport(host)
        instr.open()
        mock.assert_called_once_with(host)
        mock().open.assert_called_once()

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_open_vxi11_error(self, mock: unittest.mock.Mock):
        """Test open with VXI11 error.

        Expecting:
            QMI_InstrumentException has wrapped the internal error.
        """
        instr = QMI_Vxi11Transport("localhost")
        mock().open.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            instr.open()

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_close(self, mock: unittest.mock.Mock):
        """Test close of the transport.

        Expecting:
            The underlying VXI11 instrument to be closed.
        """
        instr = QMI_Vxi11Transport("localhost")
        instr.open()
        instr.close()
        mock().close.assert_called_once()

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_close_vxi11_error(self, mock: unittest.mock.Mock):
        """Test close with VXI11 error.

        Expecting:
            QMI_InstrumentException has wrapped the internal error.
        """
        instr = QMI_Vxi11Transport("localhost")
        instr.open()
        mock().close.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            instr.close()


class TestQmiVxi11TransportMethods(unittest.TestCase):

    def setUp(self):
        patcher = unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
        self.mock = patcher.start()
        self.addCleanup(patcher.stop)

        self.instr = QMI_Vxi11Transport("localhost")
        self.instr.open()

    def test_write(self):
        """Test writing to VXI11 instrument

        Expecting:
            Bytes has been passed untouched to vxi11 instrument.
        """
        self.instr.write(unittest.mock.sentinel.data)
        self.mock().write_raw.assert_called_once_with(unittest.mock.sentinel.data)

    def test_write_error(self):
        """Test exception during writing. """
        self.mock().write_raw.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            self.instr.write(unittest.mock.sentinel.data)

    def test_read(self):
        """Test reading from VXI11 instrument.

        Expecting:
            Bytes read from VXI11 instrument has been passed untouched.
        """
        # Arrange
        expected_read = b"a1b2c3d4"
        nbytes = len(expected_read)
        # Making data to be a bytearray, it gets all read in one go, not byte-per-byte.
        self.mock().read_raw.side_effect = [bytearray(expected_read)]
        # Act
        data = self.instr.read(nbytes)
        # Assert
        self.assertEqual(expected_read, data)
        self.mock().read_raw.assert_called_once_with(self.instr._instr.max_recv_size)

    def test_read_buffer_already_filled(self):
        """Test reading from VXI11 instrument with already filled buffer.

        Expecting:
            Data is returned from the already filled buffer.
            read_raw() is not called.
        """
        expected_read = b"a1b2c3d4"
        nbytes = len(expected_read)
        self.instr._read_buffer = expected_read + b"\n"
        data = self.instr.read(nbytes)
        # Assert
        self.mock().read_raw.assert_not_called()
        self.assertEqual(expected_read, data)

    def test_read_timeout(self):
        """Test timeout exception during read.

        Expecting:
            Timeout is set.
            QMI_TimeoutException is raised.
            Timeout is reverted to default.
        """
        self.mock().timeout = 10.0  # default timeout
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            self.instr.read(nbytes=8, timeout=0.5)

        # Assert that the timeout is restored
        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.mock().read_raw.assert_called_once_with(self.instr._instr.max_recv_size)

    def test_read_error(self):
        """Test exception during read. See that the _read_buffer contains data until exception.

        Expecting:
            A few bytes are read.
            QMI_EndOfInputException is raised.
            The read bytes remain in the buffer and are not discarded.
        """
        # Arrange
        test_string = b"test"
        self.mock().read_raw.side_effect = [bytearray(test_string)] +\
           [vxi11.vxi11.Vxi11Exception(note="Test error!")]
        with self.assertRaises(qmi.core.exceptions.QMI_EndOfInputException):
            self.instr.read(8, 0.1)  # Try to read 8 bytes

        self.assertEqual(test_string, self.instr._read_buffer)
        self.assertEqual(2, self.mock().read_raw.call_count)

    def test_read_until(self):
        """Test read_until message terminator command.

        Expecting:
            Default timeout isn't changed after call
            VXI11 call to read data from instrument
            Data mocked is returned
        """
        self.mock().timeout = 10.0  # default timeout
        test_string = "test\n".encode("utf-8")
        self.mock().read_raw.side_effect = [chr(c).encode() for c in test_string]
        data = self.instr.read_until(message_terminator="\n".encode("utf-8"), timeout=1.5)
        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.assertEqual(len(test_string), self.mock().read_raw.call_count)
        self.assertEqual(test_string, data)

    def test_read_until_buffer_already_filled(self):
        """Test read_until with buffer already filled.

        Expecting:
            Data is returned from buffer.
            read_raw() is not called.
        """
        test_string = "test\n".encode("utf-8")
        self.instr._read_buffer = test_string
        data = self.instr.read_until(message_terminator="\n".encode("utf-8"))
        # Assert
        self.mock().read_raw.assert_not_called()
        self.assertEqual(test_string.strip(), data)

    def test_read_until_invalid_term_char(self):
        """Test that a too long terminator raises an error. """
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            _ = self.instr.read_until(message_terminator=bytes("error", "utf-8"), timeout=None)

    def test_read_until_error(self):
        """Tests whether instrument error raises a QMI instrument exception. """
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            _ = self.instr.read_until(message_terminator=bytes("\n", "utf-8"), timeout=None)

    def test_read_until_timeout_exception(self):
        """Tests whether an instrument timeout raises a QMI timeout exception. """
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            _ = self.instr.read_until(message_terminator=bytes("\n", "utf-8"), timeout=None)

    def test_read_until_missing_term_char(self):
        """Tests whether the function catches a missing terminator from instrument. """
        self.mock().read_raw.side_effect = [b"test", vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")]
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            _ = self.instr.read_until(message_terminator=bytes("\n", "utf-8"), timeout=0.001)

    def test_read_until_timeout(self):
        """Test read_until_timeout works exactly like read if data is available.

        Expecting:
            Timeout is set.
            Bytes read from VXI11 instrument has been passed untouched.
            Timeout is reverted.
        """
        self.mock().timeout = 10.0  # default timeout
        expected_read = b"a1b2c3d4"
        nbytes = len(expected_read)
        self.mock().read_raw.side_effect = [chr(c).encode() for c in expected_read]
        data = self.instr.read_until_timeout(nbytes, 1.5)
        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.assertEqual(nbytes, self.mock().read_raw.call_count)
        self.assertEqual(expected_read, data)

    def test_read_until_timeout_partial_read_with_timeout_exception(self):
        """Test read_until_timeout catches timeout exception and returns partial read from buffer.

        Expecting:
            Timeout is set.
            Read times out with QMI_TimeoutException.
            Bytes read from VXI11 instrument has been passed partially until the timeout.
            Second read can read the remaining bytes.
            Timeout is reverted.
        """
        self.mock().timeout = 10.0  # default timeout
        expected_read = b"a1b2c3d4"
        nbytes = len(expected_read)
        first_read_len = nbytes // 2
        second_read_len = nbytes - first_read_len
        self.mock().read_raw.side_effect = [chr(c).encode() for c in expected_read[:first_read_len]] +\
                                           [vxi11.vxi11.Vxi11Exception(err=15, note="Timeout!")] +\
                                           [chr(c).encode() for c in expected_read[first_read_len:]]
        # The first read should catch the timeout and return whatever was read until the timeout
        data_first_read = self.instr.read_until_timeout(nbytes, 1.5)
        data_second_read = self.instr.read_until_timeout(second_read_len, 1.5)
        data = data_first_read + data_second_read

        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.assertEqual(nbytes + 1, self.mock().read_raw.call_count)  # + 1 as exception also happens at read
        self.assertEqual(first_read_len, len(data_first_read))
        self.assertEqual(second_read_len, len(data_second_read))
        self.assertEqual(expected_read, data)

    def test_read_until_timeout_partial_read_with_endofinput_exception(self):
        """Test read_until_timeout excepts with QMI_EndOfInputException and read buffer remains as is.

        Expecting:
            Timeout is set.
            Read excepts with QMI_EndOfInputException.
            Bytes read from VXI11 instrument until exception remain in read buffer.
            Timeout is reverted.
        """
        self.mock().timeout = 10.0  # default timeout
        expected_read = b"a1b2c3d4"
        nbytes = len(expected_read)
        first_read_len = nbytes // 2
        self.mock().read_raw.side_effect = [chr(c).encode() for c in expected_read[:first_read_len]] +\
                                           [vxi11.vxi11.Vxi11Exception(note="End of input!")]
        # The read should except and return nothing.
        with self.assertRaises(qmi.core.exceptions.QMI_EndOfInputException):
            self.instr.read_until_timeout(nbytes, 1.5)

        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.assertEqual(first_read_len + 1, self.mock().read_raw.call_count)   # + 1 as exception also happens at read
        self.assertEqual(first_read_len, len(self.instr._read_buffer))

    def test_discard_read_vxi11exception(self):
        """Test discard_read command.

        Expecting:
            Data before timeout is discarded.
            Vxi11Exception number 15 only breaks the while loop.
            Data after timeout is not lost.
        """
        # Arrange
        discard_string = b"discard\r\n"
        test_string = b"test"
        self.mock().read_raw.side_effect = [bytearray(discard_string)] +\
            [vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")] +\
            [test_string]
        # Act
        self.instr.discard_read()
        data = self.instr.read(len(test_string))
        # Assert
        self.assertEqual(test_string, data)

    def test_discard_read_timeouterror(self):
        """Test discard_read command.

        Expecting:
            Data before timeout is discarded.
            TimeoutError only breaks the while loop.
            Data after timeout is not lost.
        """
        # Arrange
        discard_string = b"discard\r\n"
        test_string = b"test"
        self.mock().read_raw.side_effect = [bytearray(discard_string)] +\
            [TimeoutError("Timeout!")] +\
            [test_string]
        # Act
        self.instr.discard_read()
        data = self.instr.read(len(test_string))
        # Assert
        self.assertEqual(test_string, data)

    def test_discard_read_exception(self):
        """Test discard_read raises a QMI_InstrumentException for Vxi11Exception != 15."""
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            self.instr.discard_read()


class ListUsbtmcTransportsTestCase(unittest.TestCase):
    """Test the list_usbtmc_transports function."""
    @unittest.mock.patch('sys.platform', 'win32')
    def test_list_usbtmc_transports_win(self):
        # Expected resources found
        vendor_ids = [0x0699, 0xbebe]
        product_ids = [0x3000, 0xcafe]
        serial_nrs = ["XYZ", "ABC"]
        transport_str_1 = f"usbtmc:vendorid=0x{vendor_ids[0]:04x}:productid=0x{product_ids[0]:04x}:serialnr={serial_nrs[0]}"
        transport_str_2 = f"usbtmc:vendorid=0x{vendor_ids[1]:04x}:productid=0x{product_ids[1]:04x}:serialnr={serial_nrs[1]}"
        expected_resources = [transport_str_1, transport_str_2]
        # Act
        with unittest.mock.patch(
                "qmi.core.transport_usbtmc_visa.pyvisa.ResourceManager",
                return_value=ResourceManager()
        ):
            resources = list_usbtmc_transports()

        # Assert
        self.assertListEqual(expected_resources, resources)

    @unittest.mock.patch('sys.platform', 'linux1')
    def test_list_usbtmc_transports_lin(self):
        # Expected resources found
        vendor_ids = [0x0699, 0xbebe]
        product_ids = [0x3000, 0xcafe]
        serial_nrs = ["XYZ", "ABC"]
        transport_str_1 = f"usbtmc:vendorid=0x{vendor_ids[0]:04x}:productid=0x{product_ids[0]:04x}:serialnr={serial_nrs[0]}"
        transport_str_2 = f"usbtmc:vendorid=0x{vendor_ids[1]:04x}:productid=0x{product_ids[1]:04x}:serialnr={serial_nrs[1]}"
        expected_resources = [transport_str_1, transport_str_2]
        # Act
        with unittest.mock.patch(
                "qmi.core.transport_usbtmc_pyusb.usbtmc.list_resources",
                return_value=[visa_str_1, visa_str_3]
        ):
            resources = list_usbtmc_transports()

        # Assert
        self.assertListEqual(expected_resources, resources)


if __name__ == "__main__":
    unittest.main()
