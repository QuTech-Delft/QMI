"""Instrument driver for the stanford research system sim900 module."""

import time

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException


class Sim900(QMI_Instrument):
    """Instrument driver for the stanford research system sim900 module."""

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver.

        Arguments:
            name: Name for this instrument instance.
            transport: Transport descriptor to access the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"port": 5025})
        self._scpi = ScpiProtocol(self._transport)

    @rpc_method
    def open(self) -> None:
        """See base class."""
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """See base class."""
        super().close()
        self._transport.close()

    @rpc_method
    def input_bytes_waiting(self, port: int) -> int:
        """Input Bytes Waiting

        Query bytes waiting on the input buffer of the specified port.

        Arguments:
            port: port to query number of input bytes waiting.

        Returns:
            The integer number of bytes waiting to be read by the host.

        """
        self._check_is_open()
        self._check_port(port)
        response = self._scpi.ask(f"NINP? {port}", timeout=0.1)
        try:
            return int(response)
        except ValueError as err:
            raise QMI_InstrumentException(
                f"Expected response to be of type int, instead received \"{response}\".") from err

    @rpc_method
    def get_raw_bytes(self, port: int, num_bytes: int) -> bytes:
        """Get Raw Bytes from Port

        The RAWN command retrieves exactly i bytes from the specified port and return them.

        Arguments:
            port: port number to retrieve from.
            num_bytes: amount of bytes to retrieve.

        Returns:
            The queried bytes.
        """
        self._check_is_open()
        self._check_port(port)
        self._scpi.write(f"RAWN? {port},{num_bytes}")
        return self._transport.read(num_bytes, timeout=0.1)

    @rpc_method
    def send_terminated_message(self, port: int, message: str) -> None:
        """Send Terminated Message to Port

        The send terminated message transfers the message followed by the <term>
        sequence to the specified port.

        Arguments:
            port: port number to send terminated message to.
            message: message to send.
        """
        self._check_is_open()
        self._check_port(port)
        self._scpi.write(f"SNDT {port},\"{message}\"")

    @rpc_method
    def ask_module(self, port: int, message: str, delay: float = 0.500) -> str:
        """Ask module for data.

        This is a helper function that simulates the SCPI _ask_ functionality. It is important that this function is
        executed atomically to avoid race conditions.

        Arguments:
            port: port number of module to ask for data
            message: message to send
            delay: how long the function should wait before the full response is available

        Returns:
           The ascii decoded message excluding the terminator.
        """
        self.send_terminated_message(port, message)
        time.sleep(delay)
        num_bytes = self.input_bytes_waiting(port)
        response = self.get_raw_bytes(port, num_bytes)
        if not response.endswith('\n'.encode('ascii')):
            raise QMI_InstrumentException(f"Bad response, expected \"\\n\", received {response[-1]!r}.")
        decoded_response = response[:-1].decode("ascii")
        return decoded_response

    def _check_port(self, port: int):
        """ Validate the port number.

        Checks whether the specified port number is valid for the SIM900.

        Arguments:
            port: port number to validate.

        Raises:
            QMI_UsageException: Invalid port specified
        """
        if not 1 <= port <= 8:
            raise QMI_UsageException(f"Port should be between 1 and 8, but is {port}.")
