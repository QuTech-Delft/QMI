"""Implementation of the QMI_Transport class."""

import logging
import re
import socket
import sys
import time
from collections.abc import Mapping
from typing import Any, Type

import serial
import vxi11  # type: ignore

from qmi.core.context import QMI_Context
from qmi.core.exceptions import (
    QMI_InvalidOperationException, QMI_TimeoutException, QMI_EndOfInputException,
    QMI_TransportDescriptorException, QMI_InstrumentException, QMI_RuntimeException
)
from qmi.core.util import format_address_and_port

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class QMI_Transport:
    """QMI_Transport is the base class for bidirectional byte stream transport implementations,
    typically used to talk to instruments.

    An instance of QMI_Transport represents a channel that admits reading and writing of arbitrary
    byte sequences. Message boundaries are not preserved. Subclasses of QMI_Transport implement the
    transport API for specific types of communication channels.

    Once created, a QMI_Transport needs to be opened via the open() method before reading and writing.
    When the application has finished using the transport, it must call the close() method to close
    the underlying channel and release system resources.
    """

    def __init__(self) -> None:
        """Initialize the transport.

        Subclasses must extend this method and set self._is_open to True
        when the transport is successfully initialized.
        """
        self._is_open = False

    def _check_is_open(self) -> None:
        """Verify that the transport is open, otherwise raise exception."""
        if not self._is_open:
            raise QMI_InvalidOperationException(
                f"Operation not allowed on closed transport {type(self).__name__}")

    def _open_transport(self) -> None:
        """Subclasses must override this method to open specific resources."""
        raise NotImplementedError("This is prototype function that has to be implemented by the inheriting sub-class")

    def open(self) -> None:
        """Open the transport and claim associated resources."""
        if self._is_open:
            raise QMI_InvalidOperationException(
                f"Operation not allowed on opened transport {type(self).__name__}")

        self._open_transport()
        self._is_open = True

    def close(self) -> None:
        """Close the transport and release associated resources.

        This transport instance can never be used again after it has been closed.

        Subclasses must override this method to close specific resources. When overriding this method, the subclass
        should make a call to this method before all resources are closed.
        """
        self._check_is_open()
        self._is_open = False

    def write(self, data: bytes) -> None:
        """Write a sequence of bytes to the transport.

        When this method returns, all bytes are written to the transport
        or queued to be written to the transport.

        An exception is raised if the transport is closed from the remote
        side before all bytes could be written.

        Subclasses must override this method, if applicable.
        """
        raise NotImplementedError("QMI_Transport.write not implemented")

    def read(self, nbytes: int, timeout: float | None) -> bytes:
        """Read a specified number of bytes from the transport.

        This method blocks until the specified number of bytes are available,
        then returns the received bytes.

        If "timeout" is not None and the timeout expires before the requested
        number of bytes are available, QMI_TimeoutException is raised and
        any available bytes remain in the input buffer. If "timeout" is None,
        this method waits until the requested number of bytes are received.

        Subclasses must override this method, if applicable.

        Parameters:
            nbytes: Number of bytes to read.
            timeout: Maximum time to wait (in seconds), or None to wait indefinitely.

        Returns:
            Received bytes.

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the timeout expires before the
                requested number of bytes are available.
            ~qmi.core.exceptions.QMI_EndOfInputException: If the transport has been closed on
                the remote side before the requested number of bytes are available.
        """
        raise NotImplementedError("QMI_Transport.read not implemented")

    def read_until(self, message_terminator: bytes, timeout: float | None) -> bytes:
        """Read a sequence of bytes ending in "message_terminator".

        This method blocks until the specified message terminator sequence
        is found, then returns the received bytes including the message
        terminator.

        If "timeout" is not None and the timeout expires before the message
        terminator is received, QMI_TimeoutException is raised and any
        available bytes remain in the input buffer. If "timeout" is None,
        this method waits until the message terminator is received.

        Subclasses must override this method, if applicable.

        Parameters:
            message_terminator: Byte sequence terminating a message.
            timeout: Maximum time to wait (in seconds), or None to wait indefinitely.

        Returns:
            Received bytes, including the terminator.

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the timeout expires before the
                requested number of bytes are available.
            ~qmi.core.exceptions.QMI_EndOfInputException: If the transport has been closed on
                the remote side and the end of the input is reached before the
                message terminator is found.
        """
        raise NotImplementedError("QMI_Transport.read_until not implemented")

    def read_until_timeout(self, nbytes: int, timeout: float) -> bytes:
        """Read a sequence of bytes from the transport.

        This method blocks until either the specified number of bytes
        are available or the timeout (in seconds) expires, whichever occurs
        sooner.

        If timeout occurs, the partial sequence of available bytes is returned.
        This sequence may be empty if timeout occurs before any byte was available.

        If the transport has been closed on the remote side, any remaining
        input bytes are returned (up to the maximum number of bytes requested).
        If there are no more bytes to read, QMI_EndOfInputException is raised.

        Subclasses must override this method, if applicable.

        Parameters:
            nbytes: Maximum number of bytes to read.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.

        Raises:
            ~qmi.core.exceptions.QMI_EndOfInputException: If the transport has been closed on
                the remote side and there are no more bytes to read.
        """
        raise NotImplementedError("QMI_Transport.read_until_timeout not implemented")

    def discard_read(self) -> None:
        """Discard all bytes that are immediately available for reading."""
        raise NotImplementedError("QMI_Transport.discard_read not implemented")


class TransportDescriptorParser:
    """This class is for creating a transport-specific parser classes and has (static) methods that are
    used for parsing transport strings.
    """
    def __init__(self,
                 interface: str,
                 positionals: list[tuple[str, tuple[Type, bool]]],
                 keywords: Mapping[str, tuple[Type, bool]]
    ) -> None:
        self.interface = interface
        self._positionals = positionals
        self._keywords = keywords

    def parse_parameter_strings(
            self, transport_descriptor: str, default_parameters: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Method for parsing transport descriptor strings.

        Parameters:
            transport_descriptor: The string to parse.
            default_parameters:   Dictionary of default parameters to be used if not present in the string.

        Returns:
            parameters:           A dictionary object of the parsed parameters.
        """
        if default_parameters is None:
            parameters = {}
        else:
            parameters = dict(default_parameters)

        # Drop unexpected default parameters.
        # These may be intended for a different transport interface.
        positional_names = {name for (name, _) in self._positionals}
        for attr in list(parameters.keys()):
            if (attr not in positional_names) and (attr not in self._keywords):
                parameters.pop(attr)

        interface = self._parse_interface(transport_descriptor)

        if self.interface != interface.lower():
            raise QMI_TransportDescriptorException(
                f'Unexpected interface: {interface} expected {self.interface}')

        parts = self._parse_parts(transport_descriptor)

        parameters.update(self._parse_positional_parameters(parts[1:]))
        parameters.update(self._parse_keyword_parameters(parts[1:]))

        self._check_missing_parameters(parameters)
        return parameters

    @staticmethod
    def _parse_parts(transport_descriptor: str) -> list[str]:
        regex = re.compile(
            r"((?:^([^:]+))|"  # transport interface: i.e. serial:...
            r"(?::\[(.+)[\]$])|"  # enclosed parameter (for example used in ipv6): i.e. ...:[param]:... or ...:[param]
            r"(?::([^:]+)))")  # regular parameter: i.e. ...:param:... or ...:param
        parts = []
        for match in re.finditer(regex, transport_descriptor):
            if match[2]:  # transport interface
                parts.append(match[2])
            elif match[3]:  # enclosed parameter
                parts.append(match[3])
            elif match[4]:  # regular parameter
                parts.append(match[4])
            else:
                raise QMI_TransportDescriptorException(
                    f"Invalid transport descriptor {transport_descriptor!r}")
        if len(parts) < 2:
            raise QMI_TransportDescriptorException(f"Invalid transport descriptor {transport_descriptor!r}")
        return parts

    @staticmethod
    def _parse_interface(transport_descriptor: str) -> str:
        parts = TransportDescriptorParser._parse_parts(transport_descriptor)
        return parts[0]

    def match_interface(self, transport_descriptor: str) -> bool:
        """A method to check the transport descriptor is used with the correct parser class."""
        interface = self._parse_interface(transport_descriptor).lower()
        return self.interface == interface

    def _check_missing_parameters(self, parameters: dict[str, Any]):
        req_params = self._get_required_parameters()
        missing_parameters = req_params.difference(parameters.keys())
        if len(missing_parameters) > 0:
            raise QMI_TransportDescriptorException(f'Missing required parameter(s): {missing_parameters}')

    def _parse_positional_parameters(self, params: list[str]) -> dict[str, Any]:
        positional_params = [param for param in params if not self._is_keyword_param(param)]
        d = dict()
        for (name, (ty, _)), param in zip(self._positionals, positional_params):
            try:
                d[name] = ty(param)
            except ValueError:
                raise QMI_TransportDescriptorException("Cannot parse keyword {} expected type {} but got {}", name,
                                                       ty, param)
        return d

    def _parse_keyword_parameters(self, strings: list[str]) -> dict[str, Any]:
        keyword_strings = [param for param in strings if self._is_keyword_param(param)]
        parameters = dict()
        for keyword_string in keyword_strings:
            q = keyword_string.split('=', maxsplit=2)
            if len(q) < 2:
                raise QMI_TransportDescriptorException('Keyword parameter is not in form of foo=bar')
            k, v = q
            if k in self._keywords.keys():
                try:
                    ty = self._keywords[k][0]
                    if ty is int and v.startswith('0x'):
                        parameters[k] = int(v, 16)
                    elif ty == bool:
                        if v not in ("True", "False"):
                            raise ValueError()
                        parameters[k] = (v == "True")
                    else:
                        parameters[k] = ty(v)
                except ValueError:
                    raise QMI_TransportDescriptorException("Cannot parse keyword {} expected type {} but got {}", k,
                                                           self._keywords[k][0], v)
            else:
                raise QMI_TransportDescriptorException("Unexpected keyword {}", k)
        return parameters

    def _get_required_parameters(self):
        required_positional = set(name for name, (_, required) in self._positionals if required)
        required_keyword = set(name for name, (_, required) in self._keywords.items() if required)
        req_params = required_positional | required_keyword
        return req_params

    @staticmethod
    def _is_keyword_param(param):
        return '=' in param


SerialTransportDescriptorParser = TransportDescriptorParser(
    "serial",
    [("device", (str, True))],
    {'baudrate': (int, False), 'bytesize': (int, False),
     'parity': (str, False),
     'stopbits': (float, False),
     'rtscts': (bool, False)}
)

TcpTransportDescriptorParser = TransportDescriptorParser(
    "tcp",
    [("host", (str, True)),
     ('port', (int, True))],
    {'connect_timeout': (float, False)}
)

UdpTransportDescriptorParser = TransportDescriptorParser(
    "udp",
    [("host", (str, True)),
     ('port', (int, True))],
    {'connect_timeout': (float, False)}
)

UsbTmcTransportDescriptorParser = TransportDescriptorParser(
    "usbtmc",
    [],
    {'vendorid': (int, False),
     'productid': (int, False),
     'serialnr': (str, True)}
)

GpibTransportDescriptorParser = TransportDescriptorParser(
    "gpib",
    [('primary_addr', (int, True))],
    {'board': (int, False),
     'secondary_addr': (int, False),
     'connect_timeout': (float, False)}
)

Vxi11TransportDescriptorParser = TransportDescriptorParser(
    "vxi11",
    [("host", (str, True))],
    {}
)


class QMI_SerialTransport(QMI_Transport):
    """Byte stream transport via serial port.

    This class can also be used for "virtual" serial ports via USB.

    Attributes:
        SERIAL_READ_TIMEOUT: Set a fixed read timeout on the serial port device. The actual specified timeout
                             for read() and read_until() calls will be rounded up to a multiple of this fixed
                             timeout. The timeout parameter of the serial port device must be fixed because
                             changing the timeout causes reprogramming of the serial port parameters,
                             which is a slow operation and can even cause data loss (with an FTDI
                             device under Windows).
    """
    SERIAL_READ_TIMEOUT = 0.040  # 40 ms

    def __init__(self,
                 device: str,
                 baudrate: int,
                 bytesize: int = 8,
                 parity: str = 'N',
                 stopbits: float = 1.0,
                 rtscts: bool = False,
                 ) -> None:
        """Create a bidirectional byte stream via a serial port.

        Parameters:
            device:   The device name, e.g. COM3 on Windows or /dev/ttyS1 or /dev/ttyUSB1 on Linux.
            baudrate: The baud rate in bits per second.
            bytesize: The number of bits per character (5, 6, 7 or 8).
            parity:   The parity mode (valid values are 'N','E','O').
            stopbits: The number of stop bits (1.0, 1.5 or 2.0).
            rtscts:   True to enable RTS/CTS flow control.
        """
        super().__init__()
        _logger.debug("Opening serial port %r baud=%d", device, baudrate)

        self._validate_device_name(device)
        self._validate_baudrate(baudrate)
        self._validate_bytesize(bytesize)
        self._validate_parity(parity)
        self._validate_stopbits(stopbits)
        self._validate_rstcts(rtscts)

        self.device = device
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._rtscts = rtscts
        self._read_buffer = bytearray()
        self._serial: serial.Serial | None = None

    @staticmethod
    def _validate_stopbits(stopbits: float) -> None:
        if stopbits not in (1.0, 1.5, 2.0):
            raise QMI_TransportDescriptorException(f"Invalid value for stopbits ({stopbits})")

    @staticmethod
    def _validate_parity(parity: str) -> None:
        if parity not in ('N', 'E', 'O'):
            raise QMI_TransportDescriptorException(f"Invalid parity specification ({parity})")

    @staticmethod
    def _validate_bytesize(bytesize: int) -> None:
        if bytesize < 5 or bytesize > 8:
            raise QMI_TransportDescriptorException(f"Invalid value for bytesize ({bytesize})")

    @staticmethod
    def _validate_baudrate(baudrate: int) -> None:
        if baudrate < 1:
            raise QMI_TransportDescriptorException(f"Invalid baud rate ({baudrate})")

    @staticmethod
    def _validate_device_name(device: str) -> None:
        if not (device.upper().startswith("COM") or device.startswith("/")):
            raise QMI_TransportDescriptorException(f"Unknown serial port device path ({device})")

    @staticmethod
    def _validate_rstcts(rtscts: bool) -> None:
        if rtscts not in (True, False):
            raise QMI_TransportDescriptorException(f"Invalid rtscts ({rtscts})")

    @property
    def _safe_serial(self) -> serial.Serial:
        """ The _safe_serial property should be used inside the QMI_Transport code if-and-only-if we are 100% sure that
        the _serial attribute is not None.

        This aids in static typechecking, since whereas the type of _serial is Optional[T], the result of this method
        is guaranteed to be of type T. It is a QMI-internal bug if this property is used in case _serial is None. In
        that case, we raise an AssertionError, and we hope the users will complain to us so we can fix the bug in the
        library.

        Raises: AssertionError: in case the property is used when the underlying value of _serial is None.

        Returns: The value of _serial, if it is not None. """
        assert self._serial is not None
        return self._serial

    def __str__(self) -> str:
        return f"QMI_SerialTransport {self.device!r}"

    def _open_transport(self) -> None:
        _logger.debug("Opening serial port %r", self.device)
        self._serial = serial.Serial(self.device,
                                     baudrate=self._baudrate,
                                     bytesize=self._bytesize,
                                     parity=self._parity,
                                     stopbits=self._stopbits,
                                     rtscts=self._rtscts,
                                     timeout=self.SERIAL_READ_TIMEOUT)

    def close(self) -> None:
        _logger.debug("Closing serial port %r", self.device)
        super().close()
        if self._serial is not None:
            self._serial.close()

    def write(self, data: bytes) -> None:
        self._check_is_open()
        self._safe_serial.write(data)

    def read(self, nbytes: int, timeout: float | None) -> bytes:
        self._check_is_open()

        nbuf = len(self._read_buffer)
        if nbuf >= nbytes:
            # The requested number of bytes are already in the buffer.
            # Return them immediately.
            ret = bytes(self._read_buffer[:nbytes])
            self._read_buffer = self._read_buffer[nbytes:]
            return ret

        if (timeout is not None) and (timeout <= 0):
            # Non-blocking read requested.
            # Do not try to read from the serial port, unless we know that
            # the requested number of bytes is already available.
            if self._safe_serial.in_waiting >= nbytes - nbuf:
                self._read_buffer.extend(self._safe_serial.read(nbytes - nbuf))
        else:
            # Loop until timeout or sufficient number of bytes received.
            tstart = time.monotonic()
            while True:
                # Try to read from the serial port. This call returns when
                # the requested number of bytes are received, or when the
                # fixed serial port timeout expires.
                self._read_buffer.extend(self._safe_serial.read(nbytes - nbuf))
                nbuf = len(self._read_buffer)
                if nbuf >= nbytes:
                    break
                if timeout is not None:
                    tremain = tstart + timeout - time.monotonic()
                    if tremain <= 0:
                        break

        # Timeout before requested number of bytes received.
        # Raise exception and leave all data in the buffer.
        nbuf = len(self._read_buffer)
        if nbuf < nbytes:
            raise QMI_TimeoutException(f"Timeout after {nbuf} bytes while expecting {nbytes}")

        # Return the received data.
        assert nbuf == nbytes
        ret = bytes(self._read_buffer)
        self._read_buffer = bytearray()
        return ret

    def read_until(self, message_terminator: bytes, timeout: float | None) -> bytes:
        self._check_is_open()

        # Check if a message terminator is already present in the buffer.
        p = self._read_buffer.find(message_terminator)
        if p < 0:
            # No message terminator in the buffer.
            # Read all bytes from the serial port that are available without waiting.
            navail = self._safe_serial.in_waiting
            self._read_buffer.extend(self._safe_serial.read(navail))

        # Check if a message terminator is already present in the buffer.
        p = self._read_buffer.find(message_terminator)
        if p >= 0:
            # Complete message already in the buffer. Return it immediately.
            nbytes = p + len(message_terminator)
            ret = bytes(self._read_buffer[:nbytes])
            self._read_buffer = self._read_buffer[nbytes:]
            return ret

        # Loop until timeout or message terminator received.
        # Do not block if a zero timeout was specified.
        tstart = time.monotonic()
        tremain = timeout
        while (tremain is None) or (tremain > 0):
            # Read a single character from the serial port.
            # This call returns when a character is received, or when
            # the fixed serial port timeout expires.
            b = self._safe_serial.read(1)
            self._read_buffer.extend(b)

            # Check if a message terminator was received.
            if self._read_buffer.endswith(message_terminator):
                # Return the complete message.
                ret = bytes(self._read_buffer)
                self._read_buffer = bytearray()
                return ret

            # Update remaining wait time.
            if timeout is not None:
                tremain = tstart + timeout - time.monotonic()

        nbuf = len(self._read_buffer)
        raise QMI_TimeoutException(f"Timeout after {nbuf} bytes without message terminator")

    def read_until_timeout(self, nbytes: int, timeout: float) -> bytes:
        try:
            ret = self.read(nbytes, timeout)
        except QMI_TimeoutException:
            ret = bytes(self._read_buffer)
            self._read_buffer = bytearray()
        return ret

    def discard_read(self) -> None:
        self._check_is_open()
        self._safe_serial.reset_input_buffer()
        self._read_buffer = bytearray()


def _is_valid_hostname(hostname: str) -> bool:
    """Return True if the specified host name has valid syntax."""
    # source: https://stackoverflow.com/questions/2532053/validate-a-hostname-string
    if len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]  # strip exactly one dot from the right, if present
    parts = hostname.split(".")
    if re.match(r"^[0-9]+$", parts[-1]):
        return False  # numeric TLD, not a domain name
    allowed = re.compile(r"(?!-)[A-Z0-9-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in parts)


def _is_valid_ipaddress(address: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, address)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, address)
        return True
    except OSError:
        pass
    return False


class QMI_SocketTransport(QMI_Transport):
    """Base class for bidirectional data streams via socket network connection.

    Attributes:
        MIN_PACKET_SIZE: The minimum packet size to read with `read_until` method.
        MAX_PACKET_SIZE: The maximum packet size to read with `read` method.
    """
    MIN_PACKET_SIZE: int
    MAX_PACKET_SIZE: int

    def __init__(self, host: str, port: int) -> None:
        """Initialize the UDP or TCP transport with validation of host and port.

        Parameters:
            host:   The server/client IP address.
            port:   The port for the address.
        """
        super().__init__()

        # As 'localhost' does not necessarily resolve to '127.0.0.1', it is good to resolve it just-in-case.
        host = socket.gethostbyname(host) if host == "localhost" else host
        self._validate_host(host)
        self._validate_port(port)
        self._address = (host, port)
        self._socket: socket.socket | None = None
        self._read_buffer = bytearray()

    @staticmethod
    def _validate_host(host):
        if (not _is_valid_hostname(host)) and (not _is_valid_ipaddress(host)):
            raise QMI_TransportDescriptorException(f"Invalid host name {host}")

    @staticmethod
    def _validate_port(port):
        if port < 1 or port > 65535:
            raise QMI_TransportDescriptorException(f"Invalid port number {port}")

    @property
    def _safe_socket(self) -> socket.socket:
        """ The _safe_socket property should be used inside the QMI_Transport code if-and-only-if we are 100% sure that
        the _socket attribute is not None.

        This aids in static typechecking, since whereas the type of _socket is Optional[T], the result of this method
        is guaranteed to be of type T. It is a QMI-internal bug if this property is used in case _socket is None. In
        that case, we raise an AssertionError, and we hope the users will complain to us so we can fix the bug in the
        library.

        Raises: AssertionError: in case the property is used when the underlying value of _socket is None.

        Returns: The value of _socket, if it is not None. """
        assert self._socket is not None
        return self._socket

    def _open_transport(self) -> None:
        _logger.debug("Opening %s with address %s", self, self._address)
        self._read_buffer = bytearray()

    def _read_from_socket(self, packet_size: int) -> tuple[bytes, Any]:
        """Helper function to read from a socket with specific packet size.
        Exact amount does not matter but a small power of 2 is recommended, e.g. 4096
        by socket.recv() documentation.

        Parameters:
            packet_size: The packet size to read.
        """
        try:
            b, addr = self._safe_socket.recvfrom(packet_size)
        except (BlockingIOError, socket.timeout) as err:
            raise err  # Re-raise this for handling in the upper try-except.
        except OSError as err:
            raise QMI_RuntimeException(
                f"UDP packet size was larger than {packet_size}. Data is lost."
            ) from err

        if not b:
            raise QMI_EndOfInputException(
                f"Reached end of input from socket {format_address_and_port(self._address)}"
            )
        return b, addr

    def close(self) -> None:
        super().close()
        self._safe_socket.close()

    def write(self, data: bytes) -> None:
        raise NotImplementedError("QMI_SocketTransportBase.write not implemented")

    def read(self, nbytes: int, timeout: float | None = None) -> bytes:
        self._check_is_open()
        tstart = time.monotonic()
        tremain = timeout
        nbuf = len(self._read_buffer)
        while nbuf < nbytes:
            self._safe_socket.settimeout(tremain)
            try:
                b, addr = self._read_from_socket(max(nbytes - nbuf, self.MIN_PACKET_SIZE))

            except (BlockingIOError, socket.timeout) as err:
                raise QMI_TimeoutException(
                    f"Timeout after {nbuf} bytes while expecting {nbytes}"
                ) from err
            self._read_buffer.extend(b)
            nbuf = len(self._read_buffer)
            if timeout is not None:
                tremain = tstart + timeout - time.monotonic()
                if tremain < 0:
                    raise QMI_TimeoutException(f"Timeout after {nbuf} bytes while expecting {nbytes}")

        ret = bytes(self._read_buffer[:nbytes])
        self._read_buffer = self._read_buffer[nbytes:]
        return ret

    def read_until(self, message_terminator: bytes, timeout: float | None = None) -> bytes:
        # Check if message terminator already received. To be further handled in subclass implementation.
        p = self._read_buffer.find(message_terminator)
        if p >= 0:
            # Found "message_terminator" - return data.
            nbytes = p + len(message_terminator)
            ret = bytes(self._read_buffer[:nbytes])
            self._read_buffer = self._read_buffer[nbytes:]
            return ret

        self._check_is_open()
        tstart = time.monotonic()
        tremain = timeout
        while True:
            self._safe_socket.settimeout(tremain)
            try:
                # Read from socket.
                b, addr = self._read_from_socket(self.MAX_PACKET_SIZE)
                self._read_buffer.extend(b)
            except (BlockingIOError, socket.timeout, TimeoutError) as err:
                nbuf = len(self._read_buffer)
                raise QMI_TimeoutException(
                    f"Socket timeout after {nbuf} bytes without message terminator"
                ) from err

            # Check if message terminator received.
            p = self._read_buffer.find(message_terminator)
            if p >= 0:
                # Found "message_terminator" - return data.
                nbytes = p + len(message_terminator)
                ret = bytes(self._read_buffer[:nbytes])
                self._read_buffer = self._read_buffer[nbytes:]
                return ret

            # Determine remaining time if message terminator is not yet received.
            if timeout is not None:
                # Calculate remaining time.
                tremain = tstart + timeout - time.monotonic()
                if tremain < 0:
                    nbuf = len(self._read_buffer)
                    raise QMI_TimeoutException(f"Function timeout after {nbuf} bytes without message terminator.")

    def read_until_timeout(self, nbytes: int, timeout: float) -> bytes:
        try:
            ret = self.read(nbytes, timeout)
        except QMI_TimeoutException:
            ret = bytes(self._read_buffer)
            self._read_buffer = bytearray()
        except QMI_EndOfInputException:
            if not self._read_buffer:
                raise
            ret = bytes(self._read_buffer)
            self._read_buffer = bytearray()
        return ret

    def discard_read(self) -> None:
        self._check_is_open()
        self._read_buffer = bytearray()
        self._safe_socket.settimeout(0)
        while True:
            try:
                b = self._safe_socket.recv(self.MAX_PACKET_SIZE)
            except (BlockingIOError, socket.timeout):
                # no more bytes available
                break
            except OSError:
                # UDP protocol was used and > 4096 bytes in socket buffer. This discards also the rest of the packet.
                break

            if not b:
                # end of stream
                break


class QMI_UdpTransport(QMI_SocketTransport):
    """
    An instance of QMI_UdpTransport represents a server-side UDP connection with
    a listening port to an instrument. Client-side UDP connections are not supported.

    The maximum UDP packet size is 64KB (including headers). For `write` and `read` functions,
    this means limitations. The write function we can check the data size to send and split into
    multiple messages. For `read` functions this is not possible and the client must limit the
    data size as necessary. If for `read` functions the receivable data size is larger than
    the size defined in `recvfrom(<size>)`, an exception is raised.

    Attributes:
        MIN_PACKET_SIZE: The minimum packet size to read with `read` method.
        MAX_PACKET_SIZE: The maximum packet size to read with `read_until` method.
    """
    MIN_PACKET_SIZE = 4096
    MAX_PACKET_SIZE = 4096

    def __init__(self, host: str, port: int) -> None:
        """Initialize the UDP transport by validating the UDP host and port.

        Parameters:
            host: The server IP address.
            port: The port for the address.
        """
        super().__init__(host, port)

    def _validate_port(self, port):
        super()._validate_port(port)
        if port == QMI_Context.DEFAULT_UDP_RESPONDER_PORT:
            raise QMI_TransportDescriptorException(f"UDP port number {port} not allowed")

    def __str__(self) -> str:
        remote_addr = format_address_and_port(self._address)
        return f"QMI_UdpTransport(remote={remote_addr})"

    def _open_transport(self) -> None:
        super()._open_transport()
        # Validate the host exists before trying to create a socket
        socket.gethostbyname(self._address[0])
        # Create socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # To set the local address to point to our client, we need to bind it.
        self._socket.bind(("", self._address[1]))

    def close(self) -> None:
        _logger.debug("Closing UDP transport %s", self)
        super().close()

    def write(self, data: bytes) -> None:
        self._check_is_open()
        # NOTE: We explicitly adjust the socket timeout before each send/recv call.
        self._safe_socket.settimeout(None)
        self._safe_socket.sendto(data, self._address)


class QMI_TcpTransport(QMI_SocketTransport):
    """Bidirectional byte stream via TCP network connection.

    An instance of QMI_TcpTransport represents a client-side TCP connection
    to an instrument. Server-side TCP connections are not supported.

    Attributes:
        DEFAULT_CONNECT_TIMEOUT: A default timeout period for connecting to TCP client. Default is 10 seconds.
        MIN_PACKET_SIZE: The minimum packet size to read with `read` method.
        MAX_PACKET_SIZE: The maximum packet size to read with `read_until` method.
    """

    DEFAULT_CONNECT_TIMEOUT = 10
    MIN_PACKET_SIZE = 0
    MAX_PACKET_SIZE = 512

    def __init__(self, host: str, port: int, connect_timeout: float | None = DEFAULT_CONNECT_TIMEOUT) -> None:
        """Initialize the TCP transport by connecting to the specified address.

        Parameters:
            connect_timeout: Maximum time to connect in seconds.

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If connecting takes longer than the specified connection
            timeout.
        """
        super().__init__(host, port)
        self._connect_timeout = connect_timeout

    def __str__(self) -> str:
        remote_addr = format_address_and_port(self._address)
        return f"QMI_TcpTransport(remote={remote_addr})"

    def _open_transport(self) -> None:
        super()._open_transport()
        # Create socket and connect.
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self._connect_timeout)
        # Set TCP_NODELAY socket option.
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            self._socket.connect(self._address)
        except socket.timeout as e:
            self._socket.close()
            raise QMI_TimeoutException(f"Timeout while connecting to {self._address}") from e

    def close(self) -> None:
        _logger.debug("Closing TCP transport %s", self)
        super().close()

    def write(self, data: bytes) -> None:
        self._check_is_open()
        # NOTE: We explicitly adjust the socket timeout before each send/recv call.
        self._safe_socket.settimeout(None)
        self._safe_socket.sendall(data)


class QMI_UsbTmcTransport(QMI_Transport):
    """Transport SCPI commands via USBTMC device class.

    When running under Windows, this class depends on VISA for the actual
    USBTMC implementation.

    When running under Linux, this class depends on python-usbtmc (and libusb)
    for the actual USBTMC implementation.

    This class does not implement the full functionality of QMI_Transport.
    The issue is that USBTMC is fundamentally a message-oriented protocol,
    while QMI_Transport assumes a byte stream without message delimiters.

    Only the following operations are supported:
      * write() writes the specified bytes as a single USBTMC message.
      * read_until() reads a single USBTMC message (until the device indicates
        end-of-message) and returns the fetched bytes.

    Attributes:
        DEFAULT_READ_TIMEOUT: Default timeout in seconds for USBTMC read transactions.
        WRITE_TIMEOUT:        Timeout in seconds for USBTMC write transactions.
    """

    DEFAULT_READ_TIMEOUT = 60
    WRITE_TIMEOUT = 5

    def __init__(self, vendorid: int, productid: int, serialnr: str) -> None:
        """Initialize te specified USB device as USBTMC instrument.

        The first USBTMC-compatible interface of the USB device will be used.

        Parameters:
            vendorid: USB vendor ID.
            productid: USB product ID.
            serialnr: USB device serial number.
        """
        _logger.debug("Opening USBTMC device 0x%04x:0x%04x (%s)", vendorid, productid, serialnr)
        super().__init__()

        self._validate_vendor_id(vendorid)
        self._validate_product_id(productid)

        self.vendorid = vendorid
        self.productid = productid
        self.serialnr = serialnr

    @staticmethod
    def _validate_product_id(productid):
        if (productid < 0) or (productid > 65535):
            raise QMI_TransportDescriptorException(f"Missing/bad USB product ID {productid}")

    @staticmethod
    def _validate_vendor_id(vendorid):
        if (vendorid < 0) or (vendorid > 65535):
            raise QMI_TransportDescriptorException(f"Missing/bad USB vendor ID {vendorid}")

    def __str__(self) -> str:
        return f"QMI_UsbTmcTransport 0x{self.vendorid:04x}:0x{self.productid:04x} ({self.serialnr})"

    def close(self) -> None:
        _logger.debug("Closing USBTMC device 0x%04x:0x%04x (%s)", self.vendorid, self.productid, self.serialnr)
        super().close()

    def write(self, data: bytes) -> None:
        """Send the specified data to the instrument as a single USBTMC message. A fixed timeout of 5 seconds
        is applied. If timeout occurs, the transfer is aborted and an exception is raised.

        Parameters:
            data: The data to write in a byte string.
        """
        raise NotImplementedError("QMI_UsbTmcTransport.write not implemented")

    def read(self, nbytes: int, timeout: float | None) -> bytes:
        """Read a specified number of bytes from the transport.

        All bytes must belong to the same USBTMC message.

        This method blocks until the specified number of bytes are available,
        then returns the received bytes. If timeout occurs, any partial read
        data is discarded and QMI_TimeoutException is raised.

        Parameters:
            nbytes: Expected number of bytes to read.
            timeout: Maximum time to wait in seconds (default: 60 seconds).

        Returns:
            Received bytes.

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the timeout expires before the
                requested number of bytes are available.
            ~qmi.core.exceptions.QMI_EndOfInputException: If an end-of-message indicator
                is received before the requested number of bytes is reached.
        """
        self._check_is_open()
        # USB requires a timeout
        if timeout is None:
            timeout = self.DEFAULT_READ_TIMEOUT

        # Read a USB message
        ret = self._read_message(timeout)
        if len(ret) == nbytes:
            return ret

        _logger.debug(f"USBTMC read message contained data {ret.decode()}")
        raise QMI_EndOfInputException(
            f"The read message did not contain expected bytes of data ({len(ret)} != {nbytes}."
        )

    def read_until(self, message_terminator: bytes, timeout: float | None) -> bytes:
        """The specified message_terminator is ignored. Instead, the instrument must autonomously indicate the end
        of the message according to the USBTMC protocol.

        As the message_terminator is not used, we forward simply the call to the `read_until_timeout` call.

        Parameters:
            message_terminator: This input is ignored.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.
        """
        return self.read_until_timeout(0, timeout)

    def read_until_timeout(self, nbytes: int, timeout: float | None) -> bytes:
        """Read a single USBTMC message from the instrument.

        If the timeout expires before the message is received, the read is
        aborted and any data already received are discarded. In this
        case an empty bytes string is returned.

        Parameters:
            nbytes: This input is ignored.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.
        """
        self._check_is_open()

        # USB requires a timeout
        if timeout is None:
            timeout = self.DEFAULT_READ_TIMEOUT

        # Read a new message from the instrument.
        try:
            data = self._read_message(timeout)
        except QMI_TimeoutException:
            data = bytes()

        return data

    def discard_read(self) -> None:
        try:
            self._read_message(0.0)
        except QMI_TimeoutException:
            return  # Nothing was in the instrument buffer, so we just continue.

    def _read_message(self, timeout):
        """Read one USBTMC message from the instrument.
        This should be implemented in deriving classes.

        Parameters:
            timeout: Obligatory parameter to set the timeout for reading.

        Raises:
            QMI_TimeoutException: If the read is not done within timeout period.
        """
        raise NotImplementedError("QMI_UsbTmcTransport.read not implemented")

    @staticmethod
    def _format_resources(resources: list[str]) -> list[str]:
        transports = set()
        for res in resources:
            parts = res.split("::")
            if len(parts) >= 5 and parts[0].startswith("USB") and parts[-1] == "INSTR":
                try:
                    vendorid = int(parts[1], 0)
                    productid = int(parts[2], 0)
                    serialnr = parts[3]
                    transports.add("usbtmc:vendorid=0x{:04x}:productid=0x{:04x}:serialnr={}"
                                   .format(vendorid, productid, serialnr))
                except ValueError:
                    pass  # ignore malformed resource strings

        return sorted(list(transports))

    @staticmethod
    def list_resources() -> list[str]:
        """List available resources from USB connections.
        This should be implemented in deriving classes.

        Returns:
            resources: List of available resources in QMI's USBTMC transport string format.
        """
        raise NotImplementedError("QMI_UsbTmcTransport.list_resources not implemented")


class QMI_Vxi11Transport(QMI_Transport):
    """ VXI-11 based transport to a supported device. """

    def __init__(self, host: str) -> None:
        """ Initialize the VXI-11 transport by connecting to the specified host.

        Parameters:
            host: Host name or address of the device.

        Raises:
            ~qmi.core.exceptions.QMI_TransportDescriptorException: If the host string is invalid.
        """
        super().__init__()

        QMI_TcpTransport._validate_host(host)

        self._host = host
        self._instr: vxi11.Instrument | None = None
        self._read_buffer = bytes()

    @property
    def _safe_instr(self) -> vxi11.Instrument:
        """ The _safe_instr property should be used inside the QMI_Transport code if-and-only-if we are 100% sure that
        the _instr attribute is not None.

        This aids in static typechecking, since whereas the type of _instr is Optional[T], the result of this method is
        guaranteed to be of type T. It is a QMI-internal bug if this property is used in case _instr is None. In that
        case, we raise an AssertionError, and we hope the users will complain to us, so we can fix the bug in the
        library.

        Raises: AssertionError: in case the property is used when the underlying value of _instr is None.

        Returns: The value of _instr, if it is not None. """
        assert self._instr is not None
        return self._instr

    def _open_transport(self) -> None:
        _logger.debug("Opening %s", self)

        # Open actual transport.
        try:
            self._instr = vxi11.Instrument(self._host)
            self._safe_instr.open()
        except vxi11.vxi11.Vxi11Exception as err:
            raise QMI_InstrumentException(f"Error attempting to open VXI11 transport to {self._host}") from err

    def close(self) -> None:
        _logger.debug("Closing %s", self)
        super().close()
        try:
            self._safe_instr.close()
        except vxi11.vxi11.Vxi11Exception as err:
            raise QMI_InstrumentException("Error attempting to close VXI11 transport.") from err

    def write(self, data: bytes) -> None:
        self._check_is_open()
        try:
            self._safe_instr.write_raw(data)
        except vxi11.vxi11.Vxi11Exception as err:
            raise QMI_InstrumentException() from err

    def read(self, nbytes: int, timeout: float | None = None) -> bytes:
        self._check_is_open()
        nbuf = len(self._read_buffer)
        if nbuf >= nbytes:
            # The requested number of bytes are already in the buffer. Return them immediately.
            ret = self._read_buffer[:nbytes]
            self._read_buffer = self._read_buffer[nbytes:]
            return ret

        old_timeout = self._safe_instr.timeout
        if timeout:
            self._safe_instr.timeout = timeout

        try:
            while len(self._read_buffer) < nbytes:
                self._read_buffer += self._safe_instr.read_raw(self._safe_instr.max_recv_size)

        except vxi11.vxi11.Vxi11Exception as err:
            if err.err == 15:
                # Raise timeout exception separately to provide opportunity for upper layer to handle it.
                raise QMI_TimeoutException(f"Timeout error attempting to read {nbytes} bytes") from err
            else:
                raise QMI_EndOfInputException(f"Error attempting to read {nbytes} bytes.") from err

        finally:
            self._safe_instr.timeout = old_timeout

        ret = self._read_buffer
        self._read_buffer = bytes()
        return ret

    def read_until(self, message_terminator: bytes, timeout: float | None = None) -> bytes:
        self._check_is_open()
        if len(message_terminator) != 1:
            raise QMI_InstrumentException(
                f"VXI11 instrument only support 1 byte terminating character, received {message_terminator!r}."
            )

        nbuf = len(self._read_buffer)
        if nbuf > 0 and message_terminator in self._read_buffer:
            # The requested response is already in the buffer. Return it immediately.
            terminator_index = self._read_buffer.index(message_terminator)
            ret = self._read_buffer[:terminator_index]
            self._read_buffer = self._read_buffer[terminator_index:]
            return ret

        # Set terminator, but keep old value.
        old_term_char = self._safe_instr.term_char
        self._safe_instr.term_char = message_terminator

        # Set timeout if available.
        old_timeout = self._safe_instr.timeout
        if timeout:
            self._safe_instr.timeout = timeout

        try:
            while True:
                self._read_buffer += self._safe_instr.read_raw(self._safe_instr.max_recv_size)
                # Validate terminator.
                data_term_char = self._read_buffer[-1:]  # use slice rather than index to get back bytes()
                if data_term_char == message_terminator:
                    break

        except vxi11.vxi11.Vxi11Exception as err:
            if err.err == 15:
                # Raise timeout exception separately to provide opportunity for upper layer to handle it.
                raise QMI_TimeoutException("Timeout error attempting to read bytes until {!r} char received".format(
                    message_terminator)) from err
            else:
                raise QMI_InstrumentException("Error attempting to read bytes until {!r} char received".format(
                    message_terminator)) from err

        finally:
            # Revert terminator and timeout to previous value
            self._safe_instr.term_char = old_term_char
            self._safe_instr.timeout = old_timeout

        ret = self._read_buffer
        self._read_buffer = bytes()
        return ret

    def read_until_timeout(self, nbytes: int, timeout: float) -> bytes:
        try:
            return self.read(nbytes, timeout)

        except QMI_TimeoutException:
            # Return whatever was read until timeout and clear the buffer.
            ret = self._read_buffer
            self._read_buffer = bytes()
            return ret

    def discard_read(self) -> None:
        self._check_is_open()
        old_timeout = self._safe_instr.timeout
        self._safe_instr.timeout = 0.0  # Immediate read
        # Clear any possible data in read buffer first
        self._read_buffer = bytes()
        while True:
            try:
                self._safe_instr.read_raw(1)

            except vxi11.vxi11.Vxi11Exception as err:
                if err.err == 15:
                    break
                else:
                    self._safe_instr.timeout = old_timeout
                    raise QMI_InstrumentException("Error attempting to read a byte") from err

            except TimeoutError:
                break

        self._safe_instr.timeout = old_timeout


def list_usbtmc_transports() -> list[str]:
    """Return a list of currently detected USBTMC transports."""
    if sys.platform.lower().startswith("win"):
        from qmi.core.transport_usbtmc_visa import QMI_VisaUsbTmcTransport
        return QMI_VisaUsbTmcTransport.list_resources()
    else:
        # On Linux, we use a copy of python-usbtmc which is integrated in QMI.
        from qmi.core.transport_usbtmc_pyusb import QMI_PyUsbTmcTransport
        return QMI_PyUsbTmcTransport.list_resources()


def create_transport(
        transport_descriptor: str, default_attributes: dict[str, Any] | None = None
) -> QMI_Transport:
    """Create a bidirectional communication channel.

    A transport_descriptor specifies all information that may be needed to open a transport, including parameters
    such as port number, baud rate, etc. Certain entries are obligatory, like giving the host IP address for UDP and
    TCP transports. Other entries are optional, and are indicated with `<`, `>` characters. For those entries, if
    not given, the string format below indicates the default value used in that case with the `=value` part. Do not
    include the `<`, `>` characters in the strings.

    String format:
      - VXI-11 instrument: "vxi11:host"
      - UDP connection:    "udp:host<:port>"
      - TCP connection:    "tcp:host<:port><:connect_timeout=10>"
      - Serial port:       "serial:device<:baudrate=115200><:databits=8><:parity=N><:stopbits=1>"
      - USBTMC device:     "usbtmc:vendorid:productid:serialnr"
      - GPIB device:       "gpib:<board=None:>primary_addr<:secondary_addr=None><:connect_timeout=30.0>"

    UDP, TCP and VXI-11:
      - "host" (for UDP, TCP & VXI-11 transports) specifies the host name or IP address of the UDP server/TCP client.
        Numerical IPv6 addresses must be enclosed in square brackets, e.g. "tcp:[2620:0:2d0:200::8]:5000".
      - "port" (for UDP and TCP transports) specifies the UDP/TCP port number of the server/client.
      - "connect_timeout" is TCP connection timeout.

     Serial:
      - "device" is the name of the serial port, for example "COM3" or "/dev/ttyUSB0".
      - "baudrate" specifies the number of bits per second.
        This attribute is only required for instruments with a configurable baud rate.
      - "bytesize" specifies the number of data bits per character (valid range 5 - 8).
        This attribute is only required for instruments with a configurable character format.
      - "parity" specifies the parity bit ('O' or 'E' or ''N').
        This attribute is only required for instruments with a configurable character format.
      - "stopbits" specifies the number of stop bits (1 or 1.5 or 2).
        This attribute is only required for instruments with a configurable character format.
      - "rtscts" enables or disables RTS/CTS flow control.
        Possible values are True and False; the default is False.

    USBTMC:
      - "vendorid" is the USB Vendor ID as a decimal number or as hexadecimal with 0x prefix.
      - "productid" is the USB Product ID as a decimal number or as hexadecimal with 0x prefix.
      - "serialnr" is the USB serial number string.

    GPIB:
      - "primary_addr" is GPIB device number (integer).
      - "board" is optional GPIB interface number (in VISA syntax GPIB[board]::...).
      - "secondary_addr" is optional secondary device address number.
      - "connect_timeout" is for opening resource for GPIB device, in seconds.
    """
    if SerialTransportDescriptorParser.match_interface(transport_descriptor):
        attributes = SerialTransportDescriptorParser.parse_parameter_strings(transport_descriptor, default_attributes)
        return QMI_SerialTransport(**attributes)
    elif UdpTransportDescriptorParser.match_interface(transport_descriptor):
        attributes = UdpTransportDescriptorParser.parse_parameter_strings(transport_descriptor, default_attributes)
        return QMI_UdpTransport(**attributes)
    elif TcpTransportDescriptorParser.match_interface(transport_descriptor):
        attributes = TcpTransportDescriptorParser.parse_parameter_strings(transport_descriptor, default_attributes)
        return QMI_TcpTransport(**attributes)
    elif UsbTmcTransportDescriptorParser.match_interface(transport_descriptor):
        attributes = UsbTmcTransportDescriptorParser.parse_parameter_strings(transport_descriptor, default_attributes)
        if sys.platform.lower().startswith("win"):
            from qmi.core.transport_usbtmc_visa import QMI_VisaUsbTmcTransport
            return QMI_VisaUsbTmcTransport(**attributes)
        else:
            # On Linux, we use a copy of python-usbtmc which is integrated in QMI.
            from qmi.core.transport_usbtmc_pyusb import QMI_PyUsbTmcTransport
            return QMI_PyUsbTmcTransport(**attributes)

    elif GpibTransportDescriptorParser.match_interface(transport_descriptor):
        attributes = GpibTransportDescriptorParser.parse_parameter_strings(transport_descriptor, default_attributes)
        if sys.platform.lower().startswith("win"):
            from qmi.core.transport_gpib_visa import QMI_VisaGpibTransport
            return QMI_VisaGpibTransport(**attributes)
        else:
            # This is a Windows-specific transport for National Instruments GPIB-USB-HS.
            raise QMI_TransportDescriptorException(
                "Gpib transport descriptor is for NI GPIB-USB-HS device and Windows-only."
            )

    elif Vxi11TransportDescriptorParser.match_interface(transport_descriptor):
        attributes = Vxi11TransportDescriptorParser.parse_parameter_strings(transport_descriptor, default_attributes)
        return QMI_Vxi11Transport(**attributes)
    else:
        raise QMI_TransportDescriptorException(f"Unknown type in transport descriptor {transport_descriptor!r}")
