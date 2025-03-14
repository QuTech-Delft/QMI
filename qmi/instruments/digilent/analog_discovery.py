"""QMI driver for the Digilent Analog Discovery 2 board."""

import logging
import time
from enum import Enum

import numpy as np
import pydwf
import pydwf.core.dwf_device
import pydwf.utilities
from pydwf import DwfLibrary

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class OnClose(Enum):
    """On close behaviour of the device."""
    CONTINUE = 0
    STOP = 1
    SHUTDOWN = 2


class Filter(Enum):
    """Analog acquisition filter"""

    DECIMATE = 0  # Store every Nth ADC conversion, where N = ADC frequency /acquisition frequency.
    AVERAGE = 1  # Store the average of N ADC conversions.
    MINMAX = 2  # Store interleaved, the minimum and maximum values, of 2xN conversions.


class AnalogDiscovery2(QMI_Instrument):
    """QMI driver for the Analog Discovery 2 board."""

    def __init__(self, context: QMI_Context, name: str, serial_number: str) -> None:
        super().__init__(context, name)
        self._serial_number = serial_number
        self._device: pydwf.core.dwf_device.DwfDevice | None = None

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening Analog Discovery 2 with serial nr %s ...", self._serial_number)
        self._check_is_closed()
        dwf = self._load_library()
        self._device = self._open_device(dwf)
        super().open()

    def _open_device(self, dwf: DwfLibrary) -> pydwf.core.dwf_device.DwfDevice:
        """Try to open the device for control.

        Returns:
            DwfDevice:               An opened DWF device instance.

        Raises:
            QMI_InstrumentException: If an error was reported by the 'openDwfDevice' DWF C library function.
            ValueError:              Any error in pydwf caused by the underlying C API or otherwise.
        """
        try:
            return pydwf.utilities.openDwfDevice(dwf, serial_number_filter=self._serial_number)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error
        except pydwf.PyDwfError as library_error:
            raise ValueError(str(library_error)) from library_error

    @staticmethod
    def _load_library() -> DwfLibrary:
        try:
            return pydwf.DwfLibrary()
        except pydwf.PyDwfError as library_error:
            raise QMI_UsageException('Could not open library. '
                                     'Are you sure that pydwf is correctly installed?') from library_error

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing Analog Discovery 2 with serial nr %s ...", self._serial_number)
        self._check_is_open()
        assert self._device is not None
        try:
            self._device.close()
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error
        self._device = None
        super().close()

    @rpc_method
    def prepare_analog_output_channel_for_static_output(self, channel: int, voltage: float) -> None:
        """Prepare analog output channel for static output.

        Parameters:
            channel: Channel to prepare for static output.
            voltage: Initial voltage.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_out = self._device.analogOut
        try:
            analog_out.nodeFunctionSet(channel, pydwf.DwfAnalogOutNode.Carrier, pydwf.DwfAnalogOutFunction.Square)
            analog_out.idleSet(channel, pydwf.DwfAnalogOutIdle.Initial)
            analog_out.nodeAmplitudeSet(channel, pydwf.DwfAnalogOutNode.Carrier, voltage)
            analog_out.nodeEnableSet(channel, pydwf.DwfAnalogOutNode.Carrier, True)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

    @rpc_method
    def set_analog_output_voltage_output(self, channel: int, voltage: float) -> None:
        """Set analog output channel to a target voltage.

        Parameters:
            channel: Target channel.
            voltage: Target voltage level.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        try:
            self._device.analogOut.nodeAmplitudeSet(channel, pydwf.DwfAnalogOutNode.Carrier, voltage)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

    @rpc_method
    def get_analog_output_voltage_output(self, channel: int) -> float:
        """Get the set voltage level for the analog output.

        Parameters:
            channel:          The target channel to query.

        Returns:
            voltage_setpoint: The set voltage level of the specified channel.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        try:
            voltage_setpoint = self._device.analogOut.nodeAmplitudeGet(channel, pydwf.DwfAnalogOutNode.Carrier)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

        return voltage_setpoint

    @rpc_method
    def set_device_on_close(self, on_close: OnClose) -> None:
        """Set on close behaviour.

        Parameters:
            on_close: OnClose enum: either CONTINUE, STOP or SHUTDOWN after closing the device.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        try:
            self._device.paramSet(pydwf.DwfDeviceParameter.OnClose, on_close.value)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

    @rpc_method
    def reset_analog_input(self):
        """Resets and configures analog input parameters to default values.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_in = self._device.analogIn
        try:
            analog_in.reset()
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

    @rpc_method
    def prepare_analog_input_sample(
        self,
        channel: int,
        voltage_range: float,
        acquisition_frequency: float,
        adc_filter: Filter = Filter.AVERAGE,
        voltage_offset: float = 0.0,
        buffer_size: int | None = None
    ) -> None:
        """Prepare readout voltage on specified channel.

        Parameters:
            channel:               The channel to prepare.
            voltage_offset:        Offset in volts.
            voltage_range:         Range in voltage defined as peak to peak value centered around the offset value.
            acquisition_frequency: Acquisition frequency in Hz. The device samples ADC operates at 100 MHz.
                                   If an acquisition frequency lower than 100 MHz is provided. The samples will be
                                   filtered using the provided filter rule.
                                   Note that the acquisition is set for both channels.
            adc_filter:            Filter rule to apply to ADC samples. See analog_discovery.Filter for documentation.
            buffer_size:           Adjust the buffer size of the analog in instrument: 16 <= buffer_size <= 8192.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_in = self._device.analogIn
        try:
            analog_in.channelEnableSet(channel, True)
            analog_in.frequencySet(acquisition_frequency)
            if buffer_size is not None:
                analog_in.bufferSizeSet(buffer_size)

            analog_in.channelOffsetSet(channel, channel_offset=voltage_offset)
            analog_in.channelRangeSet(channel, channel_range=voltage_range)
            analog_in.channelFilterSet(channel, pydwf.DwfAnalogInFilter(adc_filter.value))
            analog_in.configure(False, False)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

        # Wait at least 2 seconds with Analog Discovery for the offset to stabilize, before the first reading after
        # device open or offset/range change
        time.sleep(2)

    @rpc_method
    def get_analog_input_sample(self, channel: int) -> float:
        """Readout voltage on specified channel.

        Parameters:
            channel: the target channel to query.

        Raises:
            QMI_UsageException: Raised when a device is used before it is opened.
            QMI_InstrumentException: QMI_InstrumentException is raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_in = self._device.analogIn
        try:
            analog_in.status(False)
            sample = analog_in.statusSample(channel)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

        return sample

    @rpc_method
    def get_analog_input_acquire_samples(self, channel: int, timeout: float | None = None) -> np.ndarray:
        """Acquire analog input samples.

        Parameters:
            channel: The target channel to acquire samples from.
            timeout: Time before timeout exception is raised while waiting on sampling acquisition to finish. This
                     method blocks indefinitely if 'None' is provided and the measurement is not finished.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_TimeoutException:    Raised when a timeout occurs while waiting for the sampling acquisition to finish.
            QMI_InstrumentException: Raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_in = self._device.analogIn
        try:
            # Reconfigure the instrument (reset the auto trigger) and start the acquisition.
            analog_in.configure(True, True)
            time_start = time.monotonic()
            while True:
                status = analog_in.status(True)
                if status == pydwf.DwfState.Done:
                    break
                if (timeout is not None) and (time.monotonic() - time_start) > timeout:
                    raise QMI_TimeoutException('Timeout while waiting for samples.')
                time.sleep(0.01)
            buffer_size = analog_in.bufferSizeGet()
            samples = analog_in.statusData(channel, buffer_size)
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

        return samples

    @rpc_method
    def prepare_analog_input_record(
        self,
        channel: int,
        voltage_range: float,
        record_length: float,
        acquisition_frequency: float,
        voltage_offset: float = 0.0,
        adc_filter: Filter = Filter.AVERAGE
    ) -> None:
        """Prepare an analog input record for specified channel.

        Raises:
            QMI_UsageException: Raised when a device is used before it is opened.
            QMI_InstrumentException: QMI_InstrumentException is raised when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_in = self._device.analogIn
        try:
            analog_in.channelEnableSet(channel, True)
            analog_in.channelOffsetSet(channel, channel_offset=voltage_offset)
            analog_in.channelRangeSet(channel, channel_range=voltage_range)
            analog_in.acquisitionModeSet(pydwf.DwfAcquisitionMode.Record)
            analog_in.frequencySet(acquisition_frequency)
            analog_in.recordLengthSet(record_length)
            analog_in.channelFilterSet(channel, pydwf.DwfAnalogInFilter(adc_filter.value))
        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

        # Wait at least 2 seconds with Analog Discovery for the offset to stabilize, before the first reading after
        # device open or offset/range change
        time.sleep(2)

    @rpc_method
    def get_analog_input_record(self, channel: int, amount_samples: int | None = None) -> list[float]:
        """Obtain a record of input voltages from specified channel.

        Parameters:
            channel:        The target channel to query.
            amount_samples: The amount of samples to take. Only relevant when record length is set to -1.

        Returns:
            sample_record:  A record of input voltages.

        Raises:
            QMI_UsageException:      Raised when a device is used before it is opened.
            QMI_InstrumentException: Raised when data is corrupt or lost or when an unexpected instrument error occurs.
        """
        if self._device is None:
            raise QMI_UsageException("Device should be opened before use.")

        analog_in = self._device.analogIn
        sample_record: np.typing.NDArray[np.float64] = np.array([])
        try:
            if amount_samples is None:
                amount_samples_rational = analog_in.recordLengthGet() // analog_in.frequencyGet()
                amount_samples = int(amount_samples_rational)

            start_time = time.monotonic()
            analog_in.configure(False, True)
            while len(sample_record) < amount_samples and time.monotonic() < start_time + 0.5:
                status = analog_in.status(True)
                if len(sample_record) == 0 and status in (
                    pydwf.DwfState.Config,
                    pydwf.DwfState.Prefill,
                    pydwf.DwfState.Armed
                ):
                    continue

                data_available, data_lost, data_corrupt = analog_in.statusRecord()
                if data_lost > 0 or data_corrupt > 0:
                    raise QMI_InstrumentException('Data was corrupt or lost when obtaining analog input record.')
                if data_available == 0:
                    continue
                if data_available + len(sample_record) > amount_samples:
                    data_available = amount_samples - len(sample_record)

                samples = analog_in.statusData(channel, data_available)
                sample_record = np.append(sample_record, samples)

        except pydwf.DwfLibraryError as library_error:
            raise QMI_InstrumentException(str(library_error)) from library_error

        return list(sample_record)
