"""Implementation of the QMI_HislipTransport class, a transport for the HiSLIP protocol based on PyVISA."""

import logging

import pyvisa
import pyvisa.errors

from qmi.core.exceptions import QMI_EndOfInputException, QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport, QMI_Transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

#: Default HiSLIP sub-address, used when the transport descriptor does not specify one.
DEFAULT_HISLIP_SUB_ADDRESS = "hislip0"

#: Default HiSLIP port number, used when the transport descriptor does not specify one.
DEFAULT_HISLIP_PORT = 4880


class QMI_HislipTransport(QMI_Transport):
    """HiSLIP (High-Speed LAN Instrument Protocol) based transport to a supported device, implemented as a wrapper
    around PyVISA.

    PyVISA selects its backend automatically: it uses an installed IVI VISA library (NI-VISA, Keysight IO
    libraries, R&S VISA, etc.) when available, and otherwise falls back to the pure-Python `pyvisa-py` backend.
    """

    def __init__(
        self,
        ip_address: str,
        sub_address: str = DEFAULT_HISLIP_SUB_ADDRESS,
        port: int = DEFAULT_HISLIP_PORT
    ) -> None:
        """Initialize the HiSLIP transport by connecting to the specified instrument.

        Parameters:
            ip_address: IP address of the instrument.
            sub_address: HiSLIP sub-address of the instrument.
            port: HiSLIP port number of the instrument.

        Raises:
            ~qmi.core.exceptions.QMI_TransportDescriptorException: If the IP address or port is invalid.
        """
        super().__init__()

        QMI_TcpTransport._validate_host(ip_address)
        QMI_TcpTransport._validate_port(port)

        self._ip_address = ip_address
        self._sub_address = sub_address
        self._port = port
        self._visa_resource = f"TCPIP::{ip_address}::{sub_address},{port}::INSTR"
        self._device: pyvisa.resources.MessageBasedResource | None = None

    def __str__(self) -> str:
        return f"QMI_HislipTransport {self._visa_resource}"

    @property
    def _safe_device(self) -> pyvisa.resources.MessageBasedResource:
        """ The _safe_device property should be used inside the QMI_Transport code if-and-only-if we are 100% sure
        that the _device attribute is not None.

        This aids in static typechecking, since whereas the type of _device is Optional[T], the result of this
        method is guaranteed to be of type T. It is a QMI-internal bug if this property is used in case _device is
        None. In that case, we raise an AssertionError, and we hope the users will complain to us so we can fix the
        bug in the library.

        Raises: AssertionError: in case the property is used when the underlying value of _device is None.

        Returns: The value of _device, if it is not None. """
        assert self._device is not None
        return self._device

    def _open_transport(self) -> None:
        _logger.debug("Opening %s", self)
        rm = pyvisa.ResourceManager()
        try:
            self._device = rm.open_resource(self._visa_resource)
        except pyvisa.errors.VisaIOError as exc:
            raise QMI_InstrumentException(f"Error attempting to open HiSLIP transport to {self._visa_resource}") \
                from exc

    def close(self) -> None:
        _logger.debug("Closing %s", self)
        super().close()
        self._safe_device.close()

    def write(self, data: bytes) -> None:
        self._check_is_open()
        self._safe_device.write_raw(data)

    def _read_message(self, timeout: float | None) -> bytes:
        """Read a single HiSLIP response message. HiSLIP messages are self-delimiting (the instrument indicates
        the end of a message as part of the protocol), so a whole message is read from the device in one go.

        Parameters:
            timeout: Timeout for reading, in seconds, or None to wait indefinitely.
        """
        self._safe_device.timeout = int(timeout * 1000) if timeout is not None else None
        try:
            return self._safe_device.read_raw()
        except pyvisa.errors.VisaIOError as exc:
            if exc.error_code == pyvisa.errors.VI_ERROR_TMO:
                raise QMI_TimeoutException(str(exc)) from exc
            raise QMI_EndOfInputException(str(exc)) from exc

    def read(self, nbytes: int, timeout: float | None) -> bytes:
        self._check_is_open()
        ret = self._read_message(timeout)
        if len(ret) == nbytes:
            return ret

        raise QMI_EndOfInputException(
            f"The read message did not contain expected bytes of data ({len(ret)} != {nbytes})."
        )

    def read_until(self, message_terminator: bytes, timeout: float | None) -> bytes:
        """The specified message_terminator is ignored. Instead, the instrument must autonomously indicate the end
        of the message according to the HiSLIP protocol.

        As the message_terminator is not used, we forward simply the call to the `read_until_timeout` call.

        Parameters:
            message_terminator: This input is ignored.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.
        """
        return self.read_until_timeout(0, timeout)

    def read_until_timeout(self, nbytes: int, timeout: float | None) -> bytes:
        """Read a single HiSLIP message from the instrument.

        If the timeout expires before the message is received, the read is aborted and no data are returned.

        Parameters:
            nbytes: This input is ignored.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.
        """
        self._check_is_open()
        try:
            return self._read_message(timeout)
        except QMI_TimeoutException:
            return bytes()

    def discard_read(self) -> None:
        self._check_is_open()
        try:
            self._read_message(0.0)
        except QMI_TimeoutException:
            return  # Nothing to discard.

    def query(self, data: str) -> str:
        """Write a SCPI command to the instrument and return the response.

        Parameters:
            data: SCPI command string to write to the instrument.

        Returns:
            The response string received from the instrument.
        """
        self._check_is_open()
        return self._safe_device.query(data)

    def clear(self) -> None:
        """Send a HiSLIP device clear to the instrument, aborting any operation in progress and clearing the
        instrument's input and output buffers."""
        self._check_is_open()
        self._safe_device.clear()

    def read_stb(self) -> int:
        """Read the status byte of the instrument.

        Returns:
            The status byte value.
        """
        self._check_is_open()
        return self._safe_device.read_stb()
