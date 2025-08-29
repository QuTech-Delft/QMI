"""Extension of the QMI_UsbTmcTransport class utilizing usb.core with libusb1 backend and pyvisa packages."""

import os, sys
from qmi.core.exceptions import QMI_TimeoutException, QMI_TransportDescriptorException, QMI_InstrumentException,\
    QMI_RuntimeException
from qmi.core.transport import QMI_UsbTmcTransport

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


class QMI_VisaUsbTmcTransport(QMI_UsbTmcTransport):

    def __init__(self, vendorid: int, productid: int, serialnr: str) -> None:
        super().__init__(vendorid, productid, serialnr)
        self._device: pyvisa.ResourceManager | None = None

    def _open_transport(self) -> None:
        visa_resource = f"USB::0x{self.vendorid:04x}::0x{self.productid:04x}::{self.serialnr}::INSTR"
        rm = pyvisa.ResourceManager()
        try:
            self._device = rm.open_resource(visa_resource)

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

    def write(self, data: bytes) -> None:
        self._check_is_open()

        self._safe_device.timeout = int(1000 * self.WRITE_TIMEOUT)
        self._safe_device.write_raw(data)

    def _read_message(self, timeout):
        self._safe_device.timeout = 1 + int(timeout * 1000)
        try:
            data = self._safe_device.read_raw()
        except pyvisa.errors.VisaIOError as exc:
            if exc.error_code == pyvisa.errors.VI_ERROR_TMO:
                raise QMI_TimeoutException(str(exc)) from exc
            else:
                raise
        return data

    @staticmethod
    def list_resources():
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        formatted_resources = QMI_UsbTmcTransport._format_resources(resources)
        return formatted_resources
