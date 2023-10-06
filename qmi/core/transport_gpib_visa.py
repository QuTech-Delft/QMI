import os, sys
import logging
from typing import Optional

from qmi.core.exceptions import QMI_TimeoutException, QMI_TransportDescriptorException, QMI_InstrumentException,\
    QMI_RuntimeException, QMI_EndOfInputException, QMI_Exception
from qmi.core.transport import QMI_Transport

if sys.platform == "win32":
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
    - Neither System Controller nor Autpolling were enabled.
    """

    def __init__(
            self,
            devicenr: int,
            if_id: Optional[int] = None,
            secondnr: Optional[int] = None,
            timeout: Optional[float] = 30
    ):
        """Initialization of the Gpib transport.

        Parameters:
            devicenr: The device number to initialize.
            if_id: Optional interface ID, "GPIBx", number?
            secondnr: Optional Secondary device number.
            timeout: The device timeout for calls. Default is 30s.
        """
        _logger.debug("Opening GPIB device nr (%i)", devicenr)
        super().__init__()
        self._devicenr = devicenr
        self._if_id = if_id if if_id is not None else ""
        self._secondnr = secondnr
        self._timeout = timeout
        self._device: Optional[pyvisa.ResourceManager] = None
        self._read_buffer = bytes()

    def _open_transport(self) -> None:
        visa_resource = f"GPIB{self._if_id}::{self._devicenr}::"
        if self._secondnr:
            visa_resource += f"{self._secondnr}::INSTR"
        else:
            visa_resource += "INSTR"

        rm = pyvisa.ResourceManager()
        try:
            self._device = rm.open_resource(visa_resource, timeout=self._timeout * 1000, write_termination='\n',
                                read_termination='\n')

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
        return f"QMI_VisaGpibTransport GPIB::{self._devicenr}::INSTR"

    def close(self) -> None:
        _logger.debug("Closing GPIB device nr %i", self._devicenr)
        super().close()

    def write(self, data: bytes) -> None:
        self._check_is_open()

        self._safe_device.timeout = int(self._timeout * 1000)
        self._safe_device.write_raw(data)

    def read(self, nbytes: int, timeout: Optional[float]) -> bytes:
        """Read a specified number of bytes from the transport.

        All bytes must belong to the same GPIB message.

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
        nbuf = len(self._read_buffer)
        while True:
            if nbuf == nbytes:
                # The requested number of bytes are already in the buffer. Return them immediately.
                ret = self._read_buffer
                self._read_buffer = bytes()
                return ret

            # GPIB requires a timeout
            if timeout is None:
                timeout = self._timeout

            # Read buffer was of wrong length or is empty - read a new message from the instrument.
            self._read_buffer += self._read_message(timeout)
            nbuf = len(self._read_buffer)
            if nbuf != nbytes:
                _logger.debug("GPIB read buffer contained data %s" % self._read_buffer.decode())
                self._read_buffer = bytes()
                raise QMI_EndOfInputException(
                    f"The read buffer did not contain expected bytes of data ({nbuf} != {nbytes}."
                )

    def read_until(self, message_terminator: bytes, timeout: Optional[float]) -> bytes:
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

    def read_until_timeout(self, nbytes: int, timeout: float) -> bytes:
        """Read a single GPIB message from the instrument.

        If there is already data in the buffer, return it.

        If the timeout expires before the message is received, the read is
        aborted and any data already received are discarded. In this
        case QMI_TimeoutException is raised.

        Parameters:
            nbytes: This input is ignored.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the timeout expires before the
            requested number of bytes are available.
        """
        self._check_is_open()

        # USB requires a timeout
        if timeout is None:
            timeout = self._timeout

        data = bytes()
        if self._read_buffer:
            # Data already available in buffer; return it now.
            data += self._read_buffer
            self._read_buffer = bytes()

        # Read a new message from the instrument.
        data += self._read_message(timeout)

        return data

    def discard_read(self) -> None:
        # We should empty the buffer, or if it is empty, discard the next message from the source
        if not len(self._read_buffer):
            # Read buffer is empty - read a new message from the instrument.
            try:
                self._read_message(0.0)
            except QMI_TimeoutException:
                pass  # Nothing to discard.

        else:
            self._read_buffer = bytes()

    def _read_message(self, timeout):
        self._safe_device.timeout = 1 + int(timeout * 1000)
        try:
            data = self._safe_device.read_raw()
        except pyvisa.errors.VisaIOError as exc:
            if exc.error_code == pyvisa.errors.VI_ERROR_TMO:
                raise QMI_TimeoutException(str(exc)) from exc

            raise QMI_Exception("Unknown pyvisa exception") from exc

        return data
