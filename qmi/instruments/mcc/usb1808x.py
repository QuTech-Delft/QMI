"""
Instrument driver for the Measurement Computing USB-1808X DAQ.
"""

import logging
import sys
from typing import TYPE_CHECKING

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

# Lazy import of the "uldaq" or "mcculw" modules. See the function _import_modules() below.
uldaq = None
ul, enums, device_info = None, None, None
if TYPE_CHECKING:
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        import uldaq  # type: ignore

    if sys.platform.startswith("win"):
        from mcculw import ul  # type: ignore
        from mcculw import enums  # type: ignore
        from mcculw import device_info  # type: ignore


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)
# Constants for USB-1808X model
ANALOG_INPUTS = 8
ANALOG_OUTPUTS = 2
DIGITAL_CHANNELS = 4
ADC_CONVERTER_RESOLUTION = 18  # bits


def _import_modules() -> None:
    """Import the "uldaq" or "mcculw" modules.

    This import is done in a function, instead of at the top-level, to avoid unnecessary
    dependencies for programs that do not access the instrument directly.
    """
    global uldaq, ul, enums, device_info
    _logger.debug("Importing %s modules", sys.platform)
    if (sys.platform.startswith("linux") or sys.platform == "darwin") and uldaq is None:
        import uldaq  # type: ignore

    elif sys.platform.startswith("win") and (ul is None or enums is None):
        from mcculw import ul, enums, device_info  # type: ignore


class _Mcc_Usb1808xUnix:
    """Unix version for the Measurement Computing USB-1808X DAQ driver."""

    def __init__(self, unique_id: str) -> None:
        self._unique_id = unique_id
        self._device = None
        self._dio_device = None
        self._ai_device = None
        self._ao_device = None

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

    @property
    def ai_device(self) -> "uldaq.AiDevice":  # type: ignore
        """Property for holding the AI device object."""
        assert self._ai_device is not None
        return self._ai_device

    @property
    def ao_device(self) -> "uldaq.AoDevice":  # type: ignore
        """Property for holding the AO device object."""
        assert self._ao_device is not None
        return self._ao_device

    @staticmethod
    def _find_device_descriptor(unique_id: str) -> "uldaq.DaqDeviceDescriptor | None":  # type: ignore
        """A method to retrieve a specific instrument's 'device descriptor' object based on unique ID of the instrument.

        Parameters:
            unique_id:         A unique ID string.

        Returns:
            device_descriptor: The device descriptor with matching unique ID or None.
        """
        assert uldaq is not None
        device_descriptors = uldaq.get_daq_device_inventory(uldaq.InterfaceType.USB)
        for device_descriptor in device_descriptors:
            if device_descriptor.unique_id == unique_id:
                return device_descriptor

        return None  # Device not found.

    @staticmethod
    def list_instruments() -> list[str]:
        """Retrieve a list of unique_ids of connected USB-1808X devices."""
        assert uldaq is not None
        instruments = []
        device_descriptors = uldaq.get_daq_device_inventory(uldaq.InterfaceType.USB)
        for device_descriptor in device_descriptors:
            if device_descriptor.product_name == "USB-1808X":
                instruments.append(device_descriptor.unique_id)

        return instruments

    def open(self) -> None:
        device_descriptor = self._find_device_descriptor(self._unique_id)
        if device_descriptor is None:
            _logger.error("MCC USB-1808X with unique_id '%s' not found.", self._unique_id)
            raise ValueError(f"MCC USB-1808X with unique_id {self._unique_id!r} not found.")

        assert uldaq is not None
        device = uldaq.DaqDevice(device_descriptor)
        dio_device, ai_device, ao_device = None, None, None
        try:
            _logger.debug(
                "Connecting to USB-1808X device %s", self._unique_id
            )
            device.connect()
            try:
                dio_device = device.get_dio_device()
                ai_device = device.get_ai_device()
                ao_device = device.get_ao_device()
            except Exception as exc:
                device.disconnect()
                raise Exception from exc

        except Exception as exc:
            device.release()
            raise Exception from exc

        finally:
            self._device = device
            self._dio_device = dio_device
            self._ai_device = ai_device
            self._ao_device = ao_device

    def close(self) -> None:
        self._dio_device = None
        self._ai_device = None
        self._ao_device = None
        self.device.disconnect()
        self.device.release()
        self._device = None

    def get_idn(self) -> QMI_InstrumentIdentification:
        desc = self.device.get_descriptor()
        cfg = self.device.get_config()
        version = cfg.get_version(uldaq.DevVersionType.FW_MAIN)
        return QMI_InstrumentIdentification(
            vendor="Measurement Computing",
            model=desc.product_name,
            serial=desc.unique_id,
            version=version,
        )

    def get_dio_num_channels(self) -> int:
        info = self.dio_device.get_info()
        return info.get_port_info(uldaq.DigitalPortType.AUXPORT).number_of_bits

    def get_dio_direction(self) -> list[bool]:
        cfg = self.dio_device.get_config()
        directions = cfg.get_port_direction(uldaq.DigitalPortType.AUXPORT)
        return [(d == uldaq.DigitalDirection.OUTPUT) for d in directions]

    def set_dio_direction(self, channel: int, output: bool) -> None:
        d = uldaq.DigitalDirection.OUTPUT if output else uldaq.DigitalDirection.INPUT
        self.dio_device.d_config_bit(uldaq.DigitalPortType.AUXPORT, channel, d)

    def get_dio_input_bit(self, channel: int) -> int:
        return self.dio_device.d_bit_in(uldaq.DigitalPortType.AUXPORT, channel)

    def set_dio_output_bit(self, channel: int, value: int) -> None:
        return self.dio_device.d_bit_out(uldaq.DigitalPortType.AUXPORT, channel, value)

    def get_ai_num_channels(self) -> int:
        return self.ai_device.get_info().get_num_chans()

    def get_ai_ranges(self) -> list[str]:
        ranges = self.ai_device.get_info().get_ranges(uldaq.AiChanType.VOLTAGE)
        return [urange.name for urange in ranges]

    def get_ai_value(self, channel: int, input_mode: str, analog_range: str) -> float:
        mod = uldaq.AiInputMode[input_mode]
        urange = uldaq.Range[analog_range]
        return self.ai_device.a_in(channel, mod, urange, uldaq.AInFlag.DEFAULT)

    def get_ao_num_channels(self) -> int:
        return self.ao_device.get_info().get_num_chans()

    def get_ao_ranges(self) -> list[str]:
        ranges = self.ao_device.get_info().get_ranges()
        return [urange.name for urange in ranges]

    def set_ao_value(self, channel: int, analog_range: str, value: float) -> None:
        urange = uldaq.Range[analog_range]
        self.ao_device.a_out(channel, urange, uldaq.AOutFlag.DEFAULT, value)


class _Mcc_Usb1808xWindows:
    """Windows version for the Measurement Computing USB-1808X DAQ driver."""

    def __init__(self, unique_id: str, board_id: int) -> None:
        self._unique_id = unique_id
        self._board_id = board_id
        # Variable to hold device info object
        self._device_info = None

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

    @property
    def device_info(self) -> "device_info.DaqDeviceInfo":  # type: ignore
        """A property for device info object."""
        assert self._device_info is not None
        return self._device_info

    @staticmethod
    def _find_device_descriptor(unique_id: str) -> "ul.DaqDeviceDescriptor | None":  # type: ignore
        """A method to retrieve a specific instrument's 'device descriptor' object based on unique ID of the instrument.

        Parameters:
            unique_id:         A unique ID string.

        Returns:
            device_descriptor: The device descriptor with matching unique ID or None.
        """
        assert ul is not None and enums is not None
        device_descriptors = ul.get_daq_device_inventory(enums.InterfaceType.USB)
        for device_descriptor in device_descriptors:
            if device_descriptor.unique_id == unique_id:
                return device_descriptor

        return None  # Device not found.

    @staticmethod
    def list_instruments() -> list[str]:
        """Return a list of unique_ids of connected devices."""
        assert ul is not None and enums is not None
        instruments = []
        device_descriptors = ul.get_daq_device_inventory(enums.InterfaceType.USB)
        for device_descriptor in device_descriptors:
            if device_descriptor.product_name == "USB-1808X":
                instruments.append(device_descriptor.unique_id)
                
        return instruments

    def open(self) -> None:
        assert ul is not None and enums is not None
        ul.ignore_instacal()  # With this we ignore 'cg.cfg' file and enable runtime configuring.
        device_descriptor = self._find_device_descriptor(self._unique_id)
        if device_descriptor is None:
            _logger.error("MCC USB-1808X with unique_id '%s' not found.", self._unique_id)
            raise ValueError(f"MCC USB-1808X with unique_id {self._unique_id!r} not found.")

        try:
            ul.create_daq_device(self.board_id, device_descriptor)
            assert self.board_id == ul.get_board_number(
                device_descriptor
            ), f"Board ID {self.board_id} != {ul.get_board_number(device_descriptor)}"
            self._device_info = device_info.DaqDeviceInfo(self.board_id)

        except Exception as exc:
            _logger.error("MCC USB-1808X device configuration failed with: %s", str(exc))
            ul.release_daq_device(self.board_id)
            raise QMI_InstrumentException("MCC USB-1808X device port configuration failed.") from exc

    def close(self) -> None:
        _logger.debug("Closing connection to USB-1808X device %s, board %i", self._unique_id, self.board_id)
        assert ul is not None
        ul.release_daq_device(self.board_id)

    def get_idn(self) -> QMI_InstrumentIdentification:
        version = ul.get_config_string(
            enums.InfoType.BOARDINFO, self._board_id, enums.FirmwareVersionType.MAIN, enums.BoardInfo.DEVVERSION, 16
        )
        return QMI_InstrumentIdentification(
            vendor="Measurement Computing",
            model=self.device_info.product_name,
            serial=self.device_info.unique_id,
            version=version,
        )

    def get_dio_num_channels(self) -> int:
        dio_info = self.device_info.get_dio_info().port_info[0].num_bits
        return dio_info.num_ports

    def get_dio_direction(self) -> list[bool]:
        dio_info = self.device_info.get_dio_info()
        directions = [ul.get_config(
            enums.InfoType.DIGITALINFO, self._board_id, i, enums.DigitalInfo.CONFIG,
        ) for i in range(dio_info.num_ports)]
        return [(d == enums.DigitalIODirection.OUT) for d in directions]

    def set_dio_direction(self, channel: int, output: bool) -> None:
        d = enums.DigitalIODirection.OUT if output else enums.DigitalIODirection.IN
        port = self.device_info.get_dio_info().port_info[enums.DigitalPortType.AUXPORT]
        ul.d_config_bit(self._board_id, port.type, channel, d)

    def get_dio_input_bit(self, channel: int) -> int:
        port = self.device_info.get_dio_info().port_info[enums.DigitalPortType.AUXPORT]
        return ul.d_bit_in(self._board_id, port.type, channel)

    def set_dio_output_bit(self, channel: int, value: int) -> None:
        port = self.device_info.get_dio_info().port_info[enums.DigitalPortType.AUXPORT]
        return ul.d_bit_out(self.board_id, port.type, channel, value)

    def get_ai_num_channels(self) -> int:
        return self.device_info.get_ai_info().num_chans

    def get_ai_ranges(self) -> list[str]:
        ranges = self.device_info.get_ai_info().supported_ranges
        return [urange.name for urange in ranges]

    def get_ai_value(self, channel: int, input_mode: str, analog_range: str) -> float:
        # input_mode is not used with mcculw at this call.
        urange = enums.ULRange[analog_range]
        return ul.a_in(self.board_id, channel, urange)

    def get_ao_num_channels(self) -> int:
        return self.device_info.get_ao_info().num_chans

    def get_ao_ranges(self) -> list[str]:
        ranges = self.device_info.get_ao_info().supported_ranges
        return [urange.name for urange in ranges]

    def set_ao_value(self, channel: int, analog_range: str, value: float) -> None:
        urange = enums.ULRange[analog_range]
        # For mcculw we need to scale the value into range 0..1.
        scaled_value = (value - urange.range_min) / (urange.range_max - urange.range_min)
        # Then we convert the scaled value in the A/D converter range 0..2^ADC_CONVERTER_RESOLUTION - 1
        i_value = int(round(2 ** ADC_CONVERTER_RESOLUTION * scaled_value))
        i_value = i_value - 1 if i_value > 0 else i_value  # With value < 0.000002 we would get -1 otherwise.
        ul.a_out(self.board_id, channel, urange, i_value)


class MCC_USB1808X(QMI_Instrument):
    """Instrument driver for the Measurement Computing USB-1808X DAQ.

    This driver implements only a subset of the features of the USB-1808X.
    Only programmatic read/write access to DIO pins and analog input/output
    is supported. Advanced features such as timers, counters, triggering,
    scanning, waveforms etc. are not yet supported.

    Note that MCC USB-1808X has only one digital port (AUXPORT) and this port contains the digital I/O channels
    as bits 0-3.
    """

    def __init__(self, context: QMI_Context, name: str, unique_id: str, board_id: int = 0) -> None:
        """Base class initialization. Depending on the system platform, a Windows-compatible or
        Unix-compatible driver version is instantiated.

        Parameters:
            context:    A QMI_Context instance.
            name:       Name for the instrument in the context.
            unique_id:  An unique identification number, a.k.a. serial number of the device.
            board_id:   Board number for Windows driver. Not used for Unix driver.

        Properties:
            device:     The Windows|Linux object for MCC USB-1808X device on the driver.
        """
        super().__init__(context, name)
        if sys.platform.startswith("win"):
            self._device = _Mcc_Usb1808xWindows(unique_id, board_id)

        elif sys.platform.startswith("linux"):
            self._device = _Mcc_Usb1808xUnix(unique_id)

        else:
            self._device = None

        # Import the support modules.
        _import_modules()

    @property
    def device(self) -> _Mcc_Usb1808xUnix | _Mcc_Usb1808xWindows:
        assert self._device is not None
        return self._device

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        self.device.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.debug(
            "%s: Closing connection to USB-1808X device %s", self._name, self.device._unique_id
        )
        self.device.close()
        self._device = None
        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return a QMI_InstrumentIdentification instance."""
        self._check_is_open()
        return self.device.get_idn()

    @rpc_method
    def get_dio_num_channels(self) -> int:
        """Return the number of digital input/output channels from all digital ports present.

        For USB-1808X we should have total of four channels.

        Returns:
            number_of_bits: The number of channels (bits) in digital ports.
        """
        self._check_is_open()
        return self.device.get_dio_num_channels()

    @rpc_method
    def get_dio_direction(self) -> list[bool]:
        """Return the configured direction (input or output) of all AUX ports and their channels on the device.
        USB-1808X has only one AUX port with four digital channels (bits).

        Returns:
            directions_list: List of directions, where an item is True if the channel is configured for output,
                             or False if the channel is configured for input.
                             Index number of the list is the respective channel number.
        """
        self._check_is_open()
        return self.device.get_dio_direction()

    @rpc_method
    def set_dio_direction(self, channel: int, output: bool) -> None:
        """Configure a digital channel on the AUX port as input or output channel.

        Parameters:
            channel: Digital channel number (0 .. DIGITAL_CHANNELS - 1).
            output:  True to configure the channel for output, False to configure the channel for input.
        """
        if channel not in range(DIGITAL_CHANNELS):
            raise ValueError(f"Invalid digital channel number: {channel}. "
                             f"Possible values are {list(range(DIGITAL_CHANNELS))}")

        self._check_is_open()
        self.device.set_dio_direction(channel, output)

    @rpc_method
    def get_dio_input_bit(self, channel: int) -> bool:
        """Read input level of an AUX port digital channel.

        Parameters:
            channel: Digital channel number (0 .. DIGITAL_CHANNELS - 1).

        Returns:
            d_bit_in: True if the input signal is high, False if the signal is low.
        """
        if channel not in range(DIGITAL_CHANNELS):
            raise ValueError(f"Invalid digital channel number: {channel}. "
                             f"Possible values are {list(range(DIGITAL_CHANNELS))}")

        self._check_is_open()
        return bool(self.device.get_dio_input_bit(channel))

    @rpc_method
    def set_dio_output_bit(self, channel: int, value: bool) -> None:
        """Set a digital output channel on the AUX port to the specified level.

        The digital channel must be configured in output mode (see set_dio_direction) before using this function.

        Parameters:
            channel: Digital channel number (0 .. DIGITAL_CHANNELS - 1).
            value:   True to set the output high, False to set the output low.
        """
        if channel not in range(DIGITAL_CHANNELS):
            raise ValueError(f"Invalid digital channel number: {channel}. "
                             f"Possible values are {list(range(DIGITAL_CHANNELS))}")

        self._check_is_open()
        self.device.set_dio_output_bit(channel, int(value))

    @rpc_method
    def get_ai_num_channels(self) -> int:
        """Return the number of analog input channels."""
        self._check_is_open()
        return self.device.get_ai_num_channels()

    @rpc_method
    def get_ai_ranges(self) -> list[str]:
        """Get the supported analog input ranges of the device.

        Returns:
            ranges: The supported device range names. Ranges have names such as "UNI2VOLTS" for 0 .. 2 Volt or
                    "BIP10VOLTS" for -10 .. +10 Volt, see mcculw.enums or uldaq.ul_enums for more details.
        """
        self._check_is_open()
        return self.device.get_ai_ranges()

    @rpc_method
    def get_ai_value(self, channel: int, input_mode: str, analog_range: str) -> float:
        """Read the input voltage of an analog input channel.

        Parameters:
            channel:      Analog input channel index (0 .. ANALOG_INPUTS).
            input_mode:   Input mode, "SINGLE_ENDED" or "DIFFERENTIAL".
            analog_range: Name of the input range to use for the channel.

        Returns:
            a_in_value: The analog input level in Volts.
        """
        if channel not in range(ANALOG_INPUTS):
            raise ValueError(f"Invalid analog imput channel number: {channel}. "
                             f"Possible values are {list(range(ANALOG_INPUTS))}")

        self._check_is_open()
        return self.device.get_ai_value(channel, input_mode, analog_range)

    @rpc_method
    def get_ao_num_channels(self) -> int:
        """Return the number of analog output channels."""
        self._check_is_open()
        return self.device.get_ao_num_channels()

    @rpc_method
    def get_ao_ranges(self) -> list[str]:
        """Return the supported analog output ranges of the device.

        Returns:
            ranges: The supported device range names. Ranges have names such as "UNI2VOLTS" for 0 .. 2 Volt or
                    "BIP10VOLTS" for -10 .. +10 Volt, see mcculw.enums or uldaq.ul_enums for more details.
        """
        self._check_is_open()
        return self.device.get_ao_ranges()

    @rpc_method
    def set_ao_value(self, channel: int, analog_range: str, value: float) -> None:
        """Set an analog output channel to the specified voltage.

        Parameters:
            channel:      Analog output channel index (0 .. ANALOG_OUTPUTS).
            analog_range: Name of the output range to use for the channel.
            value:        Output level in Volt.
        """
        if channel not in range(ANALOG_OUTPUTS):
            raise ValueError(f"Invalid analog output channel number: {channel}. "
                             f"Possible values are {list(range(ANALOG_OUTPUTS))}")

        self._check_is_open()
        self.device.set_ao_value(channel, analog_range, value)
