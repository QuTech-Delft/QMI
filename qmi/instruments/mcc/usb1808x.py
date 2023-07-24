"""
Instrument driver for the Measurement Computing USB-1808X DAQ.
"""

import logging
import typing

from typing import List, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

# Lazy import of the "uldaq" module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    import uldaq
else:
    uldaq = None


_logger = logging.getLogger(__name__)


def _import_modules() -> None:
    """Import the "uldaq" library.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global uldaq
    if uldaq is None:
        import uldaq  # pylint: disable=W0621


class MCC_USB1808X(QMI_Instrument):
    """Instrument driver for the Measurement Computing USB-1808X DAQ.

    This driver implements only a subset of the features of the USB-1808X.
    Only programmatic read/write access to DIO pins and analog input/output
    is supported. Advanced features such as timers, counters, triggering,
    scanning, waveforms etc. are not yet supported.
    """

    def __init__(self, context: QMI_Context, name: str, unique_id: str) -> None:
        super().__init__(context, name)
        self._unique_id = unique_id
        self._device = None  # type: Optional[uldaq.DaqDevice]
        self._dio_device = None  # type: Optional[uldaq.DioDevice]
        self._ai_device = None  # type: Optional[uldaq.AiDevice]
        self._ao_device = None  # type: Optional[uldaq.AoDevice]

        # Import the "uldaq" module.
        _import_modules()

    @staticmethod
    def list_instruments() -> List[str]:
        """Return a list of unique_ids of connected devices."""

        _import_modules()
        instruments = []
        device_descriptors = uldaq.get_daq_device_inventory(uldaq.InterfaceType.USB)
        for device_descriptor in device_descriptors:
            if device_descriptor.product_name == "USB-1808X":
                instruments.append(device_descriptor.unique_id)
        return instruments

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()

        device = None

        device_descriptors = uldaq.get_daq_device_inventory(uldaq.InterfaceType.USB)
        for device_descriptor in device_descriptors:
            if (device_descriptor.product_name == "USB-1808X") and (
                device_descriptor.unique_id == self._unique_id
            ):
                device = uldaq.DaqDevice(device_descriptor)

        if device is None:
            raise QMI_InstrumentException(
                f"USB-1808X with unique_id {self._unique_id!r} not found"
            )

        try:
            _logger.debug(
                "%s: Connecting to USB-1808X device %s", self._name, self._unique_id
            )
            device.connect()

            try:
                dio_device = device.get_dio_device()
                ai_device = device.get_ai_device()
                ao_device = device.get_ao_device()
            except:
                dio_device = None
                ai_device = None
                ao_device = None
                device.disconnect()
                raise

        except:
            device.release()
            raise

        self._device = device
        self._dio_device = dio_device
        self._ai_device = ai_device
        self._ao_device = ao_device

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        assert self._device is not None
        _logger.debug(
            "%s: Closing connection to USB-1808X device %s", self._name, self._unique_id
        )
        self._dio_device = None
        self._ai_device = None
        self._ao_device = None
        self._device.disconnect()
        self._device.release()
        self._device = None
        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return a QMI_InstrumentIdentification instance."""
        self._check_is_open()
        assert self._device is not None
        desc = self._device.get_descriptor()
        cfg = self._device.get_config()
        version = cfg.get_version(uldaq.DevVersionType.FW_MAIN)
        return QMI_InstrumentIdentification(
            vendor="Measurement Computing",
            model=desc.product_name,
            serial=desc.unique_id,
            version=version,
        )

    @rpc_method
    def get_dio_num_channels(self) -> int:
        """Return the number of digital input/output channels."""
        self._check_is_open()
        assert self._dio_device is not None
        info = self._dio_device.get_info()
        return info.get_port_info(uldaq.DigitalPortType.AUXPORT).number_of_bits

    @rpc_method
    def get_dio_direction(self) -> List[bool]:
        """Return the configured direction (input or output) for each digital channel.

        :return: List of directions, where directions[i] is True if
                 channel i is configured for output, or directions[i] is False
                 if channel i is configured for input.
        """
        self._check_is_open()
        assert self._dio_device is not None
        cfg = self._dio_device.get_config()
        directions = cfg.get_port_direction(uldaq.DigitalPortType.AUXPORT)
        return [(d == uldaq.DigitalDirection.OUTPUT) for d in directions]

    @rpc_method
    def set_dio_direction(self, channel: int, output: bool) -> None:
        """Configure an digital channel as input or output channel.

        :param channel: Digital channel index (0 .. nchan-1).
        :param output: True to configure the channel for output;
                       False to configure the channel for input.
        """
        self._check_is_open()
        assert self._dio_device is not None
        d = uldaq.DigitalDirection.OUTPUT if output else uldaq.DigitalDirection.INPUT
        self._dio_device.d_config_bit(uldaq.DigitalPortType.AUXPORT, channel, d)

    @rpc_method
    def get_dio_input_bit(self, channel: int) -> bool:
        """Read input levels of the digital channels.

        :param channel: Digital channel index (0 .. nchan-1).
        :return: True if the input signal is high, False if the signal is low.
        """
        self._check_is_open()
        assert self._dio_device is not None
        return self._dio_device.d_bit_in(uldaq.DigitalPortType.AUXPORT, channel)

    @rpc_method
    def set_dio_output_bit(self, channel: int, value: bool) -> None:
        """Set a digital output channel to the specified level.

        The digital channel must be configured in output mode
        (see set_dio_direction) before using this function.

        :param channel: Digital channel index (0 .. nchan-1).
        :param value: True to set the output high, False to set the output low.
        """
        self._check_is_open()
        assert self._dio_device is not None
        return self._dio_device.d_bit_out(uldaq.DigitalPortType.AUXPORT, channel, value)

    @rpc_method
    def get_ai_num_channels(self) -> int:
        """Return the number of analog input channels."""
        self._check_is_open()
        assert self._ai_device is not None
        return self._ai_device.get_info().get_num_chans()

    @rpc_method
    def get_ai_ranges(self) -> List[str]:
        """Return the supported analog input ranges.

        Ranges have names such as "UNI2VOLTS" for 0 .. 2 Volt
        or "BIP10VOLTS" for -10 .. +10 Volt..
        """
        self._check_is_open()
        assert self._ai_device is not None
        ranges = self._ai_device.get_info().get_ranges(uldaq.AiChanType.VOLTAGE)
        return [urange.name for urange in ranges]

    @rpc_method
    def get_ai_value(self, channel: int, input_mode: str, analog_range: str) -> float:
        """Read the input voltage of an analog input channel.

        :param channel: Analog input channel index (0 .. nchan-1).
        :param input_mode: Input mode, "SINGLE_ENDED" or "DIFFERENTIAL".
        :param analog_range: Name of the input range to use for the channel.
        :return: Input level in Volt.
        """
        self._check_is_open()
        assert self._ai_device is not None
        mod = uldaq.AiInputMode[input_mode]
        urange = uldaq.Range[analog_range]
        return self._ai_device.a_in(channel, mod, urange, uldaq.AInFlag.DEFAULT)

    @rpc_method
    def get_ao_num_channels(self) -> int:
        """Return the number of analog output channels."""
        self._check_is_open()
        assert self._ao_device is not None
        return self._ao_device.get_info().get_num_chans()

    @rpc_method
    def get_ao_ranges(self) -> List[str]:
        """Return the supported analog output ranges.

        Ranges have names such as "UNI2VOLTS" for 0 .. 2 Volt
        or "BIP10VOLTS" for -10 .. +10 Volt..
        """
        self._check_is_open()
        assert self._ao_device is not None
        ranges = self._ao_device.get_info().get_ranges()
        return [urange.name for urange in ranges]

    @rpc_method
    def set_ao_value(self, channel: int, analog_range: str, value: float) -> None:
        """Set an analog output channel to the specified voltage.

        :param channel: Analog output channel index (0 .. nchan-1).
        :param analog_range: Name of the output range to use for the channel.
        :param value: Output level in Volt.
        """
        self._check_is_open()
        assert self._ao_device is not None
        urange = uldaq.Range[analog_range]
        self._ao_device.a_out(channel, urange, uldaq.AOutFlag.DEFAULT, value)
