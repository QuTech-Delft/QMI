#! /usr/bin/env python3

"""Test QMI_Transport functionality."""
import os, sys
import socket
import threading
import time
import unittest.mock
import vxi11
import warnings

import qmi
import qmi.core.exceptions
import qmi.core.transport
from qmi.core.transport import QMI_TcpTransport, QMI_SerialTransport, QMI_Vxi11Transport, QMI_UsbTmcTransport
from qmi.core.transport import create_transport, list_usbtmc_transports
from qmi.core.instrument import QMI_Instrument
from qmi.core.context import QMI_Context
from qmi.core.rpc import rpc_method

from pyvisa_stub import ResourceManager, visa_str_1, visa_str_3


class Dummy_USBTMCInstrument(QMI_Instrument):
    """ Dummy Instrument driver using USBTMC transport.
    """

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
        # Create TCP server socket.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.server_sock.bind(("127.0.0.1", 0))
        (server_host, self.server_port) = self.server_sock.getsockname()
        self.server_sock.listen(5)

    def tearDown(self):
        self.server_sock.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_factory_serial(self, mock):
        trans = create_transport("serial:/dev/ttyS0:baudrate=9600")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="/dev/ttyS0",
                                     baudrate=9600)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_factory_serial_attributes(self, mock):
        trans = create_transport("serial:COM3:baudrate=115200:bytesize=7:parity=E:stopbits=2")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="COM3",
                                     baudrate=115200,
                                     bytesize=7,
                                     parity="E",
                                     stopbits=2)

    def test_factory_tcp(self):
        # Create TCP transport.
        trans = create_transport("tcp:localhost:%d" % self.server_port)
        trans.open()
        # Accept the connection on server side.
        (server_conn, peer_address) = self.server_sock.accept()
        server_conn.settimeout(1.0)

        # Send some bytes from server to transport.
        server_conn.sendall(b"aap noot\n")

        # Receive message through transport.
        data = trans.read_until(b"\n", timeout=1.0)
        self.assertEqual(data, b"aap noot\n")

        # Close transport.
        trans.close()

        # Check connection closed on server side.
        data = server_conn.recv(100)
        self.assertEqual(data, b"")
        server_conn.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_parse_serial_basic(self, mock):
        trans = create_transport("serial:/dev/ttyS0:baudrate=9600")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="/dev/ttyS0",
                                     baudrate=9600)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_parse_serial_attrs(self, mock):
        trans = create_transport("serial:COM3:baudrate=120:bytesize=7:parity=E:stopbits=1.5")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="COM3",
                                     baudrate=120,
                                     bytesize=7,
                                     parity="E",
                                     stopbits=1.5)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport")
    def test_parse_serial_defaults(self, mock):
        trans = create_transport("serial:/dev/ttyUSB0",
                                 {"baudrate": 115200,
                                  "bytesize": 8,
                                  "parity": "N",
                                  "stopbits": 1.0})
        self.assertIs(trans, mock.return_value)
        mock.assert_called_once_with(device="/dev/ttyUSB0",
                                     baudrate=115200,
                                     bytesize=8,
                                     parity="N",
                                     stopbits=1.0)

    def test_parse_serial_bad_attrtype(self):
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            create_transport("serial:/dev/ttyS0:baudrate=fast")

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
    """ Test various 'open' cases with a dummy instrument """
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
    """ Test QMI Transport parsing on different OS."""

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

    elif sys.platform.startswith("win") or "msys" in sys.platform:
        # Remove the possibility of import error of pyvisa
        import tests.core.pyvisa_stub
        sys.modules["pyvisa"] = tests.core.pyvisa_stub
        sys.modules["pyvisa.errors"] = tests.core.pyvisa_stub.errors

        def test_parse_usbtmc(self):
            serialnr = "XYZ"
            vendorid = 0x0699
            productid = 0x3000
            if os.getenv("LIBUSBPATH"):
                desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

        def test_parse_usbtmc_non_hex(self):
            serialnr = "XYZ"
            vendorid = 1689
            productid = 12288
            if os.getenv("LIBUSBPATH"):
                desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, productid)
            self.assertEqual(desc.vendorid, vendorid)

        def test_parse_usbtmc_defaults(self):
            serialnr = "XYZ"
            vendorid = 0xa1
            productid = 0xb2
            if os.getenv("LIBUSBPATH"):
                desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            else:
                with unittest.mock.patch("usb.core.find"):
                    desc = create_transport(f"usbtmc:vendorid={vendorid}:productid={productid}:serialnr={serialnr}")

            self.assertEqual(desc.serialnr, serialnr)
            self.assertEqual(desc.productid, int(productid))
            self.assertEqual(desc.vendorid, int(vendorid))

    @unittest.mock.patch("qmi.core.transport.QMI_Vxi11Transport")
    def test_parse_vxi11(self, mock):
        trans = create_transport("vxi11:localhost")
        self.assertIs(trans, mock.return_value)
        mock.assert_called_with(host="localhost")


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

        # Create TCP transport connected to local server.
        trans = QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)
        trans.open()

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

        # Close transport.
        trans.close()

        # Check upstream channel closed.
        data = server_conn.recv(100)
        self.assertEqual(data, b"")

        # Close server-side socket.
        server_conn.close()

    def test_remote_close(self):

        # Create TCP transport connected to local server.
        trans = QMI_TcpTransport("127.0.0.1", self.server_port, connect_timeout=1)
        trans.open()

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

        # Close transport.
        trans.close()

    def test_read_until_timeout(self):

        # Create TCP transport connected to local server.
        trans = QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)
        trans.open()

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

        # Close transport.
        trans.close()

    def test_connect_failure(self):

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

        # Create TCP transport connected to local server.
        trans = QMI_TcpTransport("localhost", self.server_port, connect_timeout=1)
        trans.open()

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

        # Close transport.
        trans.close()

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
        """ The init of the transport only saves the arguments, the instrument is created only at open. """
        QMI_Vxi11Transport("localhost")
        mock.assert_not_called()

    def test_init_invalid_host(self):
        """ The init will raise an exception due to invalid host. """
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            QMI_Vxi11Transport("-invalid-host")

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_open(self, mock: unittest.mock.Mock):
        """ Test open of device.

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
        """ Test open with VXI11 error.

        Expecting:
            QMI_InstrumentException has wrapped the internal error.
        """
        instr = QMI_Vxi11Transport("localhost")
        mock().open.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            instr.open()

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_close(self, mock: unittest.mock.Mock):
        """ Test close of the transport.

        Expecting:
            The underlying VXI11 instrument to be closed.
        """
        instr = QMI_Vxi11Transport("localhost")
        instr.open()
        instr.close()
        mock().close.assert_called_once()

    @unittest.mock.patch("qmi.core.transport.vxi11.Instrument")
    def test_close_vxi11_error(self, mock: unittest.mock.Mock):
        """ Test close with VXI11 error.

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

    # TEST write

    def test_write(self):
        """ Test writing to VXI11 instrument

        Expecting:
            Bytes has been passed untouched to vxi11 instrument.
        """
        self.instr.write(unittest.mock.sentinel.data)
        self.mock().write_raw.assert_called_once_with(unittest.mock.sentinel.data)

    def test_write_error(self):
        """ Test exception during writing. """
        self.mock().write_raw.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            self.instr.write(unittest.mock.sentinel.data)

    # TEST read

    def test_read(self):
        """ Test reading from VXI11 instrument

        Expecting:
            Timeout is set.
            Bytes read from VXI11 instrument has been passed untouched.
            Timeout is reverted
        """
        self.mock().timeout = 10.0  # default timeout
        self.mock().read_raw.return_value = unittest.mock.sentinel.data
        data = self.instr.read(8, 1.5)
        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.mock().read_raw.assert_called_once_with(8)
        self.assertEqual(data, unittest.mock.sentinel.data)

    def test_read_timeout(self):
        """ Test timeout exception during read.

        Expecting:
            QMI_TimeoutException is raised
        """
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            _ = self.instr.read(nbytes=8, timeout=0.5)

    def test_read_error(self):
        """ Test exception during read.

        Expecting:
            QMI_InstrumentException is raised
        """
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            _ = self.instr.read(8, 1.5)

    # TEST read_until

    def test_read_until(self):
        """ Test read_until message terminator command

        Expecting:
            Default timeout isn't changed after call
            VXI11 call to read data from instrument
            Data mocked is returned
        """
        self.mock().timeout = 10.0  # default timeout
        test_string = "test\n".encode("utf-8")
        self.mock().read_raw.return_value = test_string
        data = self.instr.read_until(message_terminator="\n".encode("utf-8"), timeout=1.5)
        self.assertAlmostEqual(self.mock().timeout, 10.0)
        self.mock().read_raw.assert_called_once_with()
        self.assertEqual(data, test_string)

    def test_read_until_invalid_term_char(self):
        """ Test if a too long terminator raises an error. """
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            _ = self.instr.read_until(message_terminator=bytes("error", "utf-8"), timeout=None)

    def test_read_until_error(self):
        """ Tests whether instrument error raises a QMI instrument exception. """
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            _ = self.instr.read_until(message_terminator=bytes("\n", "utf-8"), timeout=None)

    def test_read_until_timeout(self):
        """ Tests whether an instrument timeout raises a QMI timeout exception. """
        self.mock().read_raw.side_effect = vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            _ = self.instr.read_until(message_terminator=bytes("\n", "utf-8"), timeout=None)

    def test_read_until_missing_term_char(self):
        """ Tests whether the function catches a missing terminator from instrument. """
        self.mock().read_raw.side_effect = [b"test", vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")]
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException):
            _ = self.instr.read_until(message_terminator=bytes("\n", "utf-8"), timeout=0.001)

    def test_discard_read(self):
        """ Test discard_read command.

        Expecting:
            Data before timeout is discarded
            Timeout shouldn't raise exception
            Data after timeout is not lost
        """
        test_string = "test"
        self.mock().read_raw.side_effect = list(test_string) +\
            [vxi11.vxi11.Vxi11Exception(err=15, note="Test error!")] + [test_string]
        self.instr.discard_read()
        data = self.instr.read(len(test_string), 1.5)
        self.assertEqual(data, test_string)

    def test_discard_read_error(self):
        """ Test whether instrument exception raises a QMI exception. """
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
