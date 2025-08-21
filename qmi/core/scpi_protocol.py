"""Implementation of SCPI protocol primitives."""

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_Transport


class ScpiProtocol:
    """Implement SCPI protocol primitives.

    An `ScpiProtocol` instance may be instantiated by `QMI_Instrument` classes
    that talk *SCPI* over some transport.
    After instantiation, the `ScpiProtocol` primitives should be used to talk to the instrument.

    Note that the `ScpiProtocol` does not take ownership of the transport. The transport's owner is
    responsible for closing the transport even when the `ScpiProtocol` is used.

    Example::

        self._transport = transport_descriptor.create()
        self._scpi = ScpiProtocol(self._transport)

        idn = self._scpi.ask("*IDN?")
    """

    def __init__(self,
                 transport: QMI_Transport,
                 command_terminator: str = "\n",
                 response_terminator: str = "\n",
                 default_timeout: float | None = None
                 ):
        """Initialize the SCPI protocol handler.

        Parameters:
            transport: Instance of `QMI_Transport` to use for sending SCPI commands to the instrument.
            command_terminator: Termination string to append when sending SCPI commands.
                This defaults to *newline* as specified by the SCPI standard.
            response_terminator: Termination string expected at the end of SCPI response messages.
                This defaults to *newline* as specified by the SCPI standard.
            default_timeout: Optional default response timeout in seconds.
                The default is to wait indefinitely until a response is received.
        """

        # The SCPI standard prescribes that a single newline character should work both for sending and receiving.
        # Just to be sure, we allow them to be overridden in case we encounter an instrument that doesn't follow
        # the standard properly.

        encoded_command_terminator  = command_terminator.encode("ascii")
        encoded_response_terminator = response_terminator.encode("ascii")

        self._transport           = transport
        self._command_terminator  = encoded_command_terminator
        self._response_terminator = encoded_response_terminator
        self._default_timeout     = default_timeout

    def write(self, cmd: str) -> None:
        """Send an SCPI command."""
        binary_cmd = cmd.encode("ascii") + self._command_terminator
        self._transport.write(binary_cmd)

    def write_raw(self, cmd: bytes) -> None:
        """Send an SCPI command already encoded as bytes"""
        binary_cmd = cmd + self._command_terminator
        self._transport.write(binary_cmd)

    def ask(self, cmd: str, timeout: float | None = None, discard: bool = False) -> str:
        """Send an SCPI command, then read and return the response.

        Parameters:
            cmd: SCPI command string.
            timeout: Optional response timeout in seconds.
            discard: Discard contents in read buffer before asking. Default is False.

        Returns:
            Response message with message terminator removed.
        """

        if timeout is None:
            timeout = self._default_timeout

        if discard:
            self._transport.discard_read()

        # Send command.
        self.write(cmd)

        # Read response.
        response = self._transport.read_until(message_terminator=self._response_terminator, timeout=timeout)
        if not response.endswith(self._response_terminator):
            raise QMI_InstrumentException("Bad response")

        response = response[:-len(self._response_terminator)]

        decoded_response = response.decode("ascii")

        return decoded_response

    def read_binary_data(self,
                         read_terminator_flag: bool = True,
                         timeout: float | None = None
                         ) -> bytes:
        """Read a binary data block formatted as in SCPI *definite length arbitrary block response data*.

        Parameters:
            read_terminator_flag: True to expect a message terminator after the binary data.
                This should be True (the default) if the binary data block is the last
                or only data element in the response message.
            timeout: Optional timeout in seconds.
        """

        if timeout is None:
            timeout = self._default_timeout

        # First byte: "#"
        # Second byte: decimal digit representing number of decimal digits in the length.
        header = self._transport.read(2, timeout=timeout)

        if header[0] != ord("#"):
            raise QMI_InstrumentException(f"Invalid binary data format, expecting '#' but got {header[0:1]!r}")

        if not header[1:].isdigit():
            msg = f"Invalid binary data format, expecting digit but got {header[1:]!r}"
            raise QMI_InstrumentException(msg)

        # Read data size.
        num_digits = int(header[1:])

        if num_digits == 0:
            raise QMI_InstrumentException(f"Invalid binary data format {header!r}")

        header2 = self._transport.read(num_digits, timeout=timeout)
        if not header2.isdigit():
            msg = f"Invalid binary data format, expecting data size but got {header2!r}"
            raise QMI_InstrumentException(msg)
        num_bytes = int(header2)

        # Read binary data.
        data = self._transport.read(num_bytes, timeout=timeout)

        if read_terminator_flag:
            # Read response terminator.
            tail = self._transport.read(len(self._response_terminator), timeout=timeout)
            if tail != self._response_terminator:
                msg = f"Invalid binary data format, expecting newline but got {tail!r}"
                raise QMI_InstrumentException(msg)

        return data
