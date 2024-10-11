"""
Instrument driver for the four-channel Bristol Fiber-Optic Switch (FOS)
"""

import logging
import sys
import typing
from typing import Optional

import qmi.core.exceptions
from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method

# Lazy import of the "uldaq" or "ul" and "enums" modules. See the function _import_modules() below.
uldaq = None
ul, enums = None, None
if typing.TYPE_CHECKING:
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        import uldaq  # type: ignore

    if sys.platform.startswith("win"):
        from mcculw import ul  # type: ignore
        from mcculw import enums  # type: ignore


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def _import_modules() -> None:
    """Import the "uldaq" library or "mcculw" modules.

    This import is done in a function, instead of at the top-level, to avoid unnecessary
    dependencies for programs that do not access the instrument directly.
    """
    global uldaq, ul, enums
    _logger.debug("Importing %s modules", sys.platform)
    if (sys.platform.startswith("linux") or sys.platform == "darwin") and uldaq is None:
        import uldaq  # type: ignore

    elif sys.platform.startswith("win") and (ul is None or enums is None):
        from mcculw import ul, enums  # type: ignore


class _Bristol_FosUnix:
    """Unix version for the Bristol FOS instrument driver."""
    def __init__(self, unique_id: str) -> None:
        self._unique_id = unique_id
        self._device = None
        self._dio_device = None

    @property
    def device(self) -> "uldaq.DaqDevice":  # type: ignore
        """Property for holding the DAQ device object."""
        assert self._device is not None
        return self._device

    @property
    def dio_device(self) -> "uldaq.DioDevice":  # type: ignore
        """Property for holding the DIO device object."""
        assert self._dio_device is not None
        return self._dio_device

    @staticmethod
    def _find_device_descriptor(unique_id: str) -> "Optional[uldaq.DaqDeviceDescriptor]":  # type: ignore
        """A method to retrieve a specific instrument's 'device descriptor' object based on unique ID of the instrument.

        Parameters:
            unique_id:         A unique ID string.

        Returns:
            device_descriptor: The device descriptor with matching unique ID or None.
        """
        assert uldaq is not None
        device_descriptors = uldaq.get_daq_device_inventory(uldaq.InterfaceType.ANY)
        for device_descriptor in device_descriptors:
            if device_descriptor.unique_id == unique_id:
                return device_descriptor

        return None  # Device not found.

    @rpc_method
    def open(self) -> None:
        device_descriptor = self._find_device_descriptor(self._unique_id)
        if device_descriptor is None:
            _logger.error("Bristol FOS with unique_id '%s' not found.", self._unique_id)
            raise ValueError(f"Bristol FOS with unique_id '{self._unique_id!r}' not found.")

        assert uldaq is not None
        device = uldaq.DaqDevice(device_descriptor)
        try:
            device.connect()
            try:
                dio_device = device.get_dio_device()
                dio_device.d_config_port(uldaq.DigitalPortType.FIRSTPORTA, uldaq.DigitalDirection.OUTPUT)

            except Exception as exc:
                device.disconnect()
                raise Exception from exc

        except Exception as exc:
            device.release()
            _logger.error("Bristol FOS device connection failed with: %s", str(exc))
            raise qmi.core.exceptions.QMI_InstrumentException("Bristol FOS device connection failed.") from exc

        self._device = device
        self._dio_device = dio_device

    @rpc_method
    def close(self) -> None:
        self.device.disconnect()
        self.device.release()
        self._device = None
        self._dio_device = None

    @rpc_method
    def select_channel(self, channel: int) -> None:
        assert uldaq is not None
        # Note that the 'channel parameter has values 1..4 ; these are mapped to value 0..3 here.
        self.dio_device.d_out(uldaq.DigitalPortType.FIRSTPORTA, channel - 1)


class _Bristol_FosWindows:
    """Windows version for the Bristol FOS instrument driver"""

    def __init__(self, unique_id: str, board_id: int) -> None:
        self._unique_id = unique_id
        self._board_id = board_id

    @property
    def board_id(self) -> int:
        """A property for instrument board number. It must be within [0, 99]."""
        assert 0 <= self._board_id <= 99
        return self._board_id

    @board_id.setter
    def board_id(self, new_id: int) -> None:
        """A property for setting a new instrument board number. It must be within [0, 99]."""
        assert isinstance(new_id, int)
        assert 0 <= new_id <= 99
        self._board_id = new_id

    @staticmethod
    def _find_device_descriptor(unique_id: str) -> "Optional[structs.DaqDeviceDescriptor]":  # type: ignore
        """A method to retrieve a specific instrument's 'device descriptor' object based on unique ID of the instrument.

        Parameters:
            unique_id:         A unique ID string.

        Returns:
            device_descriptor: The device descriptor with matching unique ID or None.
        """
        assert ul is not None and enums is not None
        device_descriptors = ul.get_daq_device_inventory(enums.InterfaceType.ANY)
        for device_descriptor in device_descriptors:
            if device_descriptor.unique_id == unique_id:
                return device_descriptor

        return None  # Device not found.

    @rpc_method
    def open(self) -> None:
        assert ul is not None and enums is not None
        ul.ignore_instacal()  # With this we ignore 'cg.cfg' file and enable runtime configuring.
        device_descriptor = self._find_device_descriptor(self._unique_id)
        if device_descriptor is None:
            _logger.error("Bristol FOS with unique_id '%s' not found.", self._unique_id)
            raise ValueError(f"Bristol FOS with unique_id '{self._unique_id!r}' not found.")

        try:
            ul.create_daq_device(self.board_id, device_descriptor)
            assert self.board_id == ul.get_board_number(
                device_descriptor
            ), f"{self.board_id} != {ul.get_board_number(device_descriptor)}"
            ul.d_config_port(self.board_id, enums.DigitalPortType.FIRSTPORTA, enums.DigitalIODirection.OUT)

        except Exception as exc:
            _logger.error("Bristol FOS device configuration failed with: %s", str(exc))
            ul.release_daq_device(self.board_id)
            raise qmi.core.exceptions.QMI_InstrumentException("Bristol FOS device port configuration failed.") from exc

    @rpc_method
    def close(self) -> None:
        assert ul is not None
        ul.release_daq_device(self.board_id)

    @rpc_method
    def select_channel(self, channel: int) -> None:
        assert ul is not None
        # Note that the 'channel parameter has values 1..4 ; these are mapped to value 0..3 here.
        ul.d_out(self._board_id, enums.DigitalPortType.FIRSTPORTA, channel - 1)


class Bristol_Fos(QMI_Instrument):
    """Base class for the Bristol FOS instrument driver"""

    def __init__(self, context: QMI_Context, name: str, unique_id: str, board_id: int = 0) -> None:
        """Base class initialization. Depending on the system platform, a Windows-compatible or
        Unix-compatible driver version is instantiated.

        Attributes:
            fos:        The instantiated FOS device on the driver.

        Parameters:
            context:    A QMI_Context instance.
            name:       Name for the instrument in the context.
            unique_id:  An unique identification number, a.k.a. serial number of the device.
            board_id:   Board number for Windows driver. Not used for Unix driver.
        """
        super().__init__(context, name)
        if sys.platform.startswith("win"):
            self.fos = _Bristol_FosWindows(unique_id, board_id)

        else:
            self.fos = _Bristol_FosUnix(unique_id)

        # Import the support module.
        _import_modules()

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        self.fos.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        self.fos.close()
        super().close()

    @rpc_method
    def select_channel(self, channel: int) -> None:
        """Method for selecting an output channel for DIO device.

        Parameters:
            channel:     The output channel number. Must be in range [1, 4].

        Raises:
            ValueError:  At invalid channel number.
        """
        self._check_is_open()
        if channel not in range(1, 5):
            raise ValueError("Bad channel: {}".format(channel))

        self.fos.select_channel(channel)
