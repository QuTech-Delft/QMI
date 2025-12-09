"""Extension of the QMI_UsbTmcTransport class utilizing usb.core and qmi.core.usbtmc packages."""

import usb.core

from qmi.core import usbtmc as usbtmc
from qmi.core.exceptions import QMI_TimeoutException
from qmi.core.transport import QMI_UsbTmcTransport


class QMI_PyUsbTmcTransport(QMI_UsbTmcTransport):

    def __init__(self, vendorid: int, productid: int, serialnr: str) -> None:
        super().__init__(vendorid, productid, serialnr)
        self._device: usbtmc.Instrument | None = None

    def _open_transport(self) -> None:
        self._device = usbtmc.Instrument(self.vendorid, self.productid, self.serialnr)
        self._device.open()

    def close(self) -> None:
        super().close()
        if self._device is not None:
            self._device.close()

    @property
    def _safe_device(self) -> usbtmc.Instrument:
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
        self._safe_device.timeout = self.WRITE_TIMEOUT
        self._safe_device.write_raw(data)

    def _read_message(self, timeout):
        self._safe_device.timeout = timeout
        try:
            data = self._safe_device.read_raw()
        except usb.core.USBError as exc:
            if exc.errno == 110:
                # Timeout
                raise QMI_TimeoutException(str(exc)) from exc
            else:
                raise
        return data

    @staticmethod
    def list_resources():
        resources = usbtmc.list_resources()
        formatted_resources = QMI_UsbTmcTransport._format_resources(resources)
        return formatted_resources
