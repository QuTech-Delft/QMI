"""Utility functions for QMI."""

import re
import threading


def is_valid_object_name(name: str) -> bool:
    """Check that the specified name is an acceptable name for QMI.

    This function is used to check names for QMI contexts,
    QMI RPC objects, QMI instruments and QMI signals.

    Valid names contain at least 1 and at most 63 characters
    and consist of only letters, digits or the characters ``- _ ( )``.

    (Internally, QMI may use names which do not meet these criteria.)

    Parameters:
        name: Name to be validated.

    Returns:
        True if the named is valid, False if it is not valid.
    """

    if len(name) > 63:
        return False
    if not re.match(r"^[-_a-zA-Z0-9()]+$", name):
        return False
    return True


def format_address_and_port(address: tuple[str, int]) -> str:
    """Format a host address and port number as a string ``"<host>:<port>"``.

    The host address may either be an IP address or a host name.

    If an IPv6 address is used, the formatting will add square brackets
    around the host address to separate it from the port number
    (see also RFC 3986, section 3.2.2).

    Parameters:
        address: Tuple (host, port).

    Returns:
        String containing the formatted address and port.
    """

    (host, port) = address
    if ':' in host:
        host = '[' + host + ']'
    return host + ':' + str(port)


def parse_address_and_port(address: str) -> tuple[str, int]:
    """Parse host address and port number.

    The host address may either be an IP address or a host name.

    Parameters:
        address: String in format ``"<host>:<port>"``
            where `<host>` is either a host name or an IPv4 or IPv6 address,
            and `<port>` is a decimal TCP/UDP port number.
            If `<host>` is an IPv6 address, it must be enclosed in square brackets
            (e.g. "[::1]:5001") to avoid ambiguous interpretation of the ``:`` symbol.

    Returns:
        Tuple (host, port).

    Raises:
        ValueError: If an invalid address format is detected.
    """

    parts = address.rsplit(":", 1)
    if len(parts) != 2:
        raise ValueError("Invalid address format, expecting 'host:port'")
    (host, port_str) = parts

    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    port = int(port_str)

    return (host, port)


class AtomicCounter:
    """Simple atomic counter."""

    def __init__(self, initial_value: int = 0) -> None:
        self.lock = threading.Lock()
        self.count = initial_value

    def inc(self) -> None:
        """Increase the counter value by 1."""
        with self.lock:
            self.count += 1

    def dec(self) -> None:
        """Decrease the counter value by 1."""
        with self.lock:
            self.count -= 1

    def value(self) -> int:
        """Return the current counter value."""
        with self.lock:
            return self.count
