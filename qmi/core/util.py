"""Utility functions for QMI."""

import re
import threading
from typing import Any


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


def check_value_structures_equal(value1: Any, value2: Any) -> bool:
    """Check if two values have matching types and container structure.

    Scalar values must have exactly the same type. Lists, tuples and sets must
    have the same container type, length, and compatible element types.
    Dictionaries must have the same keys and compatible value types.
    """

    if type(value1) is not type(value2):  # noqa: E721
        return False

    if isinstance(value1, dict):
        if len(value1) != len(value2):
            return False
        if set(value1) != set(value2):
            return False
        return all(check_value_structures_equal(value1[key], value2[key]) for key in value1)

    if isinstance(value1, (list, tuple)):
        if len(value1) != len(value2):
            return False
        return all(
            check_value_structures_equal(item1, item2)
            for item1, item2 in zip(value1, value2, strict=True)
        )

    if isinstance(value1, set):
        if len(value1) != len(value2):
            return False
        value2_signatures = [_make_value_structure_signature(item) for item in value2]
        for item in value1:
            signature = _make_value_structure_signature(item)
            try:
                value2_signatures.remove(signature)
            except ValueError:
                return False
        return True

    return True


def _make_value_structure_signature(value: Any) -> Any:
    """Return a hashable signature for set element structure comparisons."""

    if isinstance(value, dict):
        return (
            dict,
            tuple(
                sorted(
                    ((key, _make_value_structure_signature(sub_value)) for key, sub_value in value.items()),
                    key=repr
                )
            )
        )
    if isinstance(value, list):
        return (list, tuple(_make_value_structure_signature(item) for item in value))
    if isinstance(value, tuple):
        return (tuple, tuple(_make_value_structure_signature(item) for item in value))
    if isinstance(value, set):
        return (set, tuple(sorted((_make_value_structure_signature(item) for item in value), key=repr)))
    return type(value)


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
