import os, sys
import logging

from qmi.core.exceptions import QMI_TimeoutException, QMI_TransportDescriptorException, QMI_InstrumentException,\
    QMI_RuntimeException, QMI_EndOfInputException, QMI_Exception
from qmi.core.transport import QMI_Transport

if sys.platform != "win32":
    raise QMI_RuntimeException("The GPIB transport supports only Windows platforms.")

import usb
import usb.core
from usb.backend import libusb1
try:
    backend = libusb1.get_backend(find_library=lambda x: os.getenv("LIBUSBPATH"))
    usb.core.find(backend=backend)

except usb.core.NoBackendError as exc:
    raise QMI_RuntimeException("LIBUSBPATH environment variable must be set for libusb") from exc

import pyvisa
import pyvisa.errors

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class QMI_VisaGpibTransport(QMI_Transport):
    """The QMI_VisaGpibTransport is developed specifically to use with National Instruments'
    GPIB-USB-HS device under Windows. Note that the device's GPIB settings need to be correct
    for this transport to work. Also, the presumption is that default IVI_VISA library is used.

    This transport was tested with the GPIB device connected to a Tektronix AWG 5014C instrument.
    The instrument's GPIB settings were set to:
    - GPIB interface ID: 0
    - primary address: 1
    - secondary address: None
    - timeout: 30s
    - NO sending of EOI with write nor terminating read with EOS
    - Neither System Controller nor Autopolling were enabled.
    """

    def __init__(
        self,
        primary_addr: int,
        board: int | None = None,
        secondary_addr: int | None = None,
        connect_timeout: float = 30.0
    ) -> None:
        """Initialization of the Gpib transport.

        Parameters:
            primary_addr: The device number to initialize.
            board: Optional interface ID, "GPIBx", number?
            secondary_addr: Optional Secondary device number.
            connect_timeout: The device timeout to open resource, in seconds. Default is 30s.
        """
        _logger.debug("Opening GPIB device nr (%i)", primary_addr)
        super().__init__()
        self._primary_addr = primary_addr
        self._board = board
        self._secondary_addr = secondary_addr
        self._connect_timeout = connect_timeout
        self._device: pyvisa.ResourceManager | None = None
        self._read_buffer = bytes()

    def _open_transport(self) -> None:
        visa_resource = f"GPIB{self._board}::{self._primary_addr}::" if self._board else f"GPIB::{self._primary_addr}::"
        if self._secondary_addr:
            visa_resource = visa_resource + f"{self._secondary_addr}::"

        visa_resource = visa_resource + "INSTR"

        rm = pyvisa.ResourceManager()
        try:
            self._device = rm.open_resource(
                visa_resource,
                open_timeout=int(self._connect_timeout * 1000),
                write_termination='\n',
                read_termination='\n'
            )

        except ValueError as exc:
            if "install a suitable backend" in str(exc):
                raise QMI_TransportDescriptorException("LIBUSBPATH environment variable must be set for libusb") \
                    from exc

            else:
                raise QMI_InstrumentException(exc)

    @property
    def _safe_device(self) -> pyvisa.ResourceManager:
        """ The _safe_device property should be used inside the QMI_Transport code if-and-only-if we are 100% sure that
        the _device attribute is not None.

        This aids in static typechecking, since whereas the type of _device is Optional[T], the result of this method is
        guaranteed to be of type T. It is a QMI-internal bug if this property is used in case _device is None. In that
        case, we raise an AssertionError, and we hope the users will complain to us so we can fix the bug in the
        library.

        Raises: AssertionError: in case the property is used when the underlying value of _device is None.

        Returns: The value of _device, if it is not None. """
        assert self._device is not None
        return self._device

    def __str__(self) -> str:
        if self._board is not None:
            descriptor = f"QMI_VisaGpibTransport GPIB{self._board}::{self._primary_addr}::"
        else:
            descriptor = f"QMI_VisaGpibTransport GPIB::{self._primary_addr}::"
        descriptor = descriptor + f"{self._secondary_addr}::INSTR" if self._secondary_addr else descriptor + "INSTR"
        return descriptor

    def close(self) -> None:
        _logger.debug("Closing GPIB device nr %i", self._primary_addr)
        super().close()

    def write(self, data: bytes) -> None:
        self._check_is_open()
        self._safe_device.timeout = 0.0
        self._safe_device.write_raw(data)

    def read(self, nbytes: int, timeout: float | None) -> bytes:
        self._check_is_open()

        # Read a GPIB message
        ret = self._read_message(timeout)
        if len(ret) == nbytes:
            return ret

        _logger.debug("GPIB read message contained data %s", self._read_buffer.decode())
        raise QMI_EndOfInputException(
            f"The read message did not contain expected bytes of data ({len(ret)} != {nbytes}."
        )

    def read_until(self, message_terminator: bytes, timeout: float | None) -> bytes:
        """The specified message_terminator is ignored. Instead, the instrument must autonomously indicate the end
        of the message according to the GPIB protocol.

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
        # Read a new message from the instrument and ignore timeout.
        try:
            data = self._read_message(timeout)
        except QMI_TimeoutException:
            data = bytes()

        return data

    def discard_read(self) -> None:
        try:
            self._read_message(0.0)
        except QMI_TimeoutException:
            return  # Nothing to discard.

    def _read_message(self, timeout: float | None) -> bytes:
        """Read a GPIB message. A whole message is read from the device in bytes.

        Parameters:
            timeout: Timeout for reading
        """
        if timeout is not None:
            self._safe_device.timeout = int(timeout * 1000)  # in milliseconds

        else:
            self._safe_device.timeout = timeout  # infinite

        try:
            data = self._safe_device.read_raw()
        except pyvisa.errors.VisaIOError as exc:
            if exc.error_code == pyvisa.errors.VI_ERROR_TMO:
                raise QMI_TimeoutException(str(exc)) from exc

            raise QMI_Exception("Unknown pyvisa exception") from exc

        return data
