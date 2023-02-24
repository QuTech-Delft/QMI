"""
Instrument driver for the four-channel Bristol Fiber-Optic Switch (FOS)

.. autoclass:: Bristol_FOS
   :members:
   :undoc-members:
"""

import typing
from typing import Optional

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method

# Lazy import of the "uldaq" module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    import uldaq
else:
    uldaq = None


def _import_modules() -> None:
    """Import the "uldaq" library.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global uldaq
    if uldaq is None:
        import uldaq  #pylint: disable=W0621


class Bristol_FOS(QMI_Instrument):

    def __init__(self, context: QMI_Context, name: str, unique_id: str) -> None:
        super().__init__(context, name)
        self._unique_id = unique_id
        self._device = None
        self._dio_device = None

        # Import the "uldaq" module.
        _import_modules()

    @staticmethod
    def _find_device_descriptor(unique_id: str) -> "Optional[uldaq.DaqDeviceDescriptor]":
        _import_modules()
        device_descriptors = uldaq.get_daq_device_inventory(uldaq.InterfaceType.ANY)
        for device_descriptor in device_descriptors:
            if device_descriptor.unique_id == unique_id:
                return device_descriptor
        return None  # Device not found.

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()

        device_descriptor = self._find_device_descriptor(self._unique_id)
        if device_descriptor is None:
            raise ValueError("Bristol FOS with unique_id {!r} not found.".format(self._unique_id))

        device = uldaq.DaqDevice(device_descriptor)
        try:
            device.connect()
            try:
                dio_device = device.get_dio_device()
                dio_device.d_config_port(uldaq.DigitalPortType.FIRSTPORTA, uldaq.DigitalDirection.OUTPUT)
            except:
                device.disconnect()
                raise
        except:
            device.release()
            raise

        self._device = device
        self._dio_device = dio_device

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        assert self._device is not None
        self._device.disconnect()
        self._device.release()
        self._device = None
        self._dio_device = None
        super().close()

    @rpc_method
    def select_channel(self, channel: int) -> None:
        self._check_is_open()
        if not channel in [1, 2, 3, 4]:
            raise ValueError("Bad channel: {}".format(channel))
        assert self._dio_device is not None
        # Note that the 'channel parameter has values 1..4 ; these are mapped to value 0..3 here.
        self._dio_device.d_out(uldaq.DigitalPortType.FIRSTPORTA, channel - 1)
