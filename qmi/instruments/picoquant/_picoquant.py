""" This module contains the base class for QMI instrument driver for the Picoquant 'Harp instruments."""

import ctypes
import enum
import logging
import time
from enum import Enum
from threading import Lock
from typing import TypeVar, Type

import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.messaging import _PeerTcpConnection
from qmi.core.pubsub import QMI_Signal
from qmi.core.rpc import rpc_method
from qmi.instruments.picoquant.support._decoders import EventFilterMode, SYNC_TYPE
from qmi.instruments.picoquant.support._realtime import RealTimeHistogram, RealTimeCountRate, NUM_CHANNELS
from qmi.instruments.picoquant.support._events import _FetchEventsThread, _MODE
from qmi.instruments.picoquant.support._library_wrapper import _LibWrapper

_logger = logging.getLogger(__name__)

_ENUM_T = TypeVar('_ENUM_T', bound=Enum)
MAX_MESSAGE_SIZE = _PeerTcpConnection.MAX_MESSAGE_SIZE


def _str_to_enum(enum_type: Type[_ENUM_T], str_value: str) -> _ENUM_T:
    """Convert a string value to an Enum-type value, by comparing it to the enum value names."""
    try:
        return enum_type[str_value]
    except KeyError:
        allowed_values = tuple(ev.name for ev in enum_type)
        raise ValueError("Bad value {!r}, expected one of {!r}".format(str_value, allowed_values))


@enum.unique
class _EDGE(enum.Enum):
    """Symbolic constants for routines that take an `edge` argument:

    * Function :func:`~MultiHarpDevice.setMeasurementControl`, `startedge` and `stopedge` arguments;
    * Function :func:`~MultiHarpDevice.setSyncEdgeTrigger`, `edge` argument;
    * Function :func:`~MultiHarpDevice.setInputEdgeTrigger`, `edge` argument.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """
    RISING = 1
    """Rising edge."""
    FALLING = 0
    """Falling edge."""


@enum.unique
class _FEATURE(enum.IntFlag):
    """Bitfield constants for the return value of the :func:`~MultiHarpDevice.getFeatures` function.

    These are defined as preprocessor symbols in the ``mhdefin.h`` C header file.
    """
    DLL = 0x0001
    """DLL License available."""
    TTTR = 0x0002
    """TTTR mode available."""
    MARKERS = 0x0004
    """Markers available."""
    LOWRES = 0x0008
    """Long range mode available"""
    TRIGOUT = 0x0010
    """Trigger output available."""
    PROG_TD = 0x0020
    """Programmable deadtime available."""


class _PicoquantHarp(QMI_Instrument):

    # Some functions have model-dependent variable/string differences. Use this to distinguish
    _MODEL: str = ""

    # The QMI RPC mechanism can not handle messages larger than what is set in qmi.core.messaging.
    # To avoid RPC errors, we limit the number of events returned per call.
    MAX_EVENTS_PER_CALL = MAX_MESSAGE_SIZE

    # Signal published to report real-time histograms based on T2 event data.
    sig_histogram = QMI_Signal([RealTimeHistogram])

    # Signal published to report real-time count rates based on T2 event data.
    sig_countrate = QMI_Signal([RealTimeCountRate])

    def __init__(self, context: QMI_Context, name: str, serial_number: str, max_pending_events: int = 10 ** 8) -> None:
        """Instantiate the instrument driver. This is the base class for all *Harp instruments.

        Parameters:
            context: the QMI_Context that manages us
            name: the name of the instrument instance
            serial_number: the serial number of the instrument to be opened.
            max_pending_events: Only Relevant for T2 capturing. Defaults to 10e8 events.
        """
        super().__init__(context, name)
        self._serial_number = serial_number
        self._max_pending_events = max_pending_events
        self._lazy_lib: _LibWrapper | None = None
        self._devidx = -1
        self._lib_version: str = ""
        self._fetch_events_thread: _FetchEventsThread | None = None
        self._mode: _MODE | None = None
        self._measurement_running = False
        self._measurement_start_time = 0.0
        self._event_filter_channels: dict[int, EventFilterMode] = {}
        self._event_filter_aperture = (0, 0)
        self._actuallen = 65536  # Actual histogram length value

        # The instrument may be accessed concurrently by two threads:
        #  - public API functions are called through the RPC thread that manages this instrument instance
        #  - the function _read_fifo() is called by the background event fetching thread.
        # For this reason, interaction with the instrument must be protected with an explicit mutex.
        self._device_lock = Lock()

    @property
    def _max_dev_num(self):
        raise NotImplementedError()

    @property
    def _ttreadmax(self):
        raise NotImplementedError()

    @property
    def _model(self):
        raise NotImplementedError()

    @property
    def _lib(self) -> _LibWrapper:
        raise NotImplementedError

    def _read_fifo(self) -> np.ndarray:
        """Read event FIFO data.

        This is an internal method. It gets called by the background thread when measuring in T2 mode.

        CPU time during wait for completion will be yielded to other processes/threads. The call will return after a
        timeout period of approximately 1 ms if no more data could be fetched. The actual time to return may vary
        towards 2..3 ms due to USB overhead and operating system latencies.

        Returns:
            Raw FIFO data as a 1-dimensional array of 32-bit unsigned integers.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            fifo_data = np.empty(self._ttreadmax, dtype=np.uint32)
            buffer = fifo_data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32))
            n_actual = ctypes.c_int()
            if self._model == "MH":
                self._lib.ReadFiFo(self._devidx, buffer, n_actual)

            else:
                self._lib.ReadFiFo(self._devidx, buffer, self._ttreadmax, n_actual)

            n_actual_int = n_actual.value
            return fifo_data[:n_actual_int].copy()

    @rpc_method
    def open(self) -> None:
        """Open the device.

        This method also starts a background thread which will be responsible
        for fetching event data from the instrument.
        """

        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        vers = ctypes.create_string_buffer(8)
        self._lib.GetLibraryVersion(vers)
        self._lib_version = vers.value.decode()
        _logger.debug("Library version = %s", self._lib_version)

        with self._device_lock:
            for devidx in range(self._max_dev_num):
                try:
                    serial = ctypes.create_string_buffer(8)
                    self._lib.OpenDevice(devidx, serial)
                    decoded_serial = serial.value.decode()
                    if not decoded_serial:
                        try:
                            if self._model in ["MH", "HH"]:
                                self._lib.Initialize(devidx, 0, 0)  # HydraHarp and MultiHarp

                            elif self._model in ["PH", "TH260"]:
                                self._lib.Initialize(devidx, 0)  # PicoHarp and TimeHarp

                            else:
                                raise NotImplementedError(f"Model {self._model} is not implemented!")

                        except QMI_InstrumentException:
                            continue

                        serial = ctypes.create_string_buffer(8)
                        self._lib.GetSerialNumber(devidx, serial)
                        decoded_serial = serial.value.decode()

                    if decoded_serial == self._serial_number:
                        self._devidx = devidx
                        break

                    self._lib.CloseDevice(devidx)

                except QMI_InstrumentException:
                    continue

            if self._devidx == -1:
                raise QMI_InstrumentException(f"No device with serial number {self._serial_number!r} found.")

        self._fetch_events_thread = _FetchEventsThread(self._read_fifo,
                                                       self.sig_histogram.publish,  # type: ignore
                                                       self.sig_countrate.publish,  # type: ignore
                                                       self._max_pending_events)
        self._fetch_events_thread.start()

        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the device.

        Stops the background event fetching thread and closes the underlying device.
        """

        self._check_is_open()

        assert (self._fetch_events_thread is not None)
        self._fetch_events_thread.shutdown()
        self._fetch_events_thread.join()
        self._fetch_events_thread = None

        _logger.info("[%s] Closing connection to instrument", self._name)
        with self._device_lock:
            self._devidx = -1
        self._mode = None
        super().close()

    @rpc_method
    def get_error_string(self, error_code: int) -> str:
        """ Get the error string for an error code number.

        Inputs:
            error_code: The error code number to be translated

        Returns:
            Error code's description string.
        """
        self._check_is_open()
        with self._device_lock:
            error_string = ctypes.create_string_buffer(40)
            self._lib.GetErrorString(error_string, error_code)

        _logger.error("[%s] Got error %s", self._name, error_string.value.decode())
        return error_string.value.decode()

    @rpc_method
    def get_hardware_info(self) -> tuple[str, str, str]:
        """Get model, part nr, and version of the device.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            A 3-tuple of consisting of (model, partno, version) strings.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            model = ctypes.create_string_buffer(24)
            partno = ctypes.create_string_buffer(8)
            version = ctypes.create_string_buffer(8)
            self._lib.GetHardwareInfo(self._devidx, model, partno, version)
            decoded_model = model.value.decode()
            decoded_partno = partno.value.decode()
            decoded_version = version.value.decode()
            return decoded_model, decoded_partno, decoded_version

    @rpc_method
    def get_serial_number(self) -> str:
        """Get the device serial number.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            The serial number for example '1035683'.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            serial = ctypes.create_string_buffer(8)
            self._lib.GetSerialNumber(self._devidx, serial)
            return serial.value.decode()

    @rpc_method
    def get_features(self) -> list[str]:
        """Get device features.

        This function is usually not needed by the user. It is mainly for integration in PicoQuant system software
        such as SymPhoTime in order to figure out in a standardized way the capabilities the device has.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            A list of strings, each describing a feature of the device.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            features_bitset = ctypes.c_int()
            self._lib.GetFeatures(self._devidx, features_bitset)
            features = _FEATURE(features_bitset.value)
            return [feature.name for feature in _FEATURE if feature in features and feature.name is not None]

    @rpc_method
    def get_base_resolution(self) -> tuple[float, int]:
        """Get the resolution and binsteps of the device.

        Returns:
            A tuple `(resolution, binsteps)` where resolution (float) is the base resolution in
            picoseconds; binsteps (int) is the number of allowed binning steps.
        """
        self._check_is_open()
        with self._device_lock:
            resolution = ctypes.c_double()
            binsteps = ctypes.c_int()
            self._lib.GetBaseResolution(self._devidx, resolution, binsteps)
            return resolution.value, binsteps.value

    @rpc_method
    def get_debug_info(self) -> str:
        """Get debugging info of the device.

        Call this immediately after receiving an error from any library call or after detecting a `SYSERROR` from
        `get_flags`. In case of `SYSERROR`, please provide this information to support.

        Returns:
            A debug info string (65,655 characters, max).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            debuginfo = ctypes.create_string_buffer(65536)
            if self._model == "MH":
                self._lib.GetDebugInfo(self._devidx, debuginfo)

            else:
                self._lib.GetHardwareDebugInfo(self._devidx, debuginfo)

            return debuginfo.value.decode()

    @rpc_method
    def get_number_of_input_channels(self) -> int:
        """Get number of input channels of the device.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            Number of input channels.
            When a channel index is passed to another method of this driver, the valid range
            of channel index is from 0 to `number_of_channels` - 1.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            nchannels = ctypes.c_int()
            self._lib.GetNumOfInputChannels(self._devidx, nchannels)
            return nchannels.value

    @rpc_method
    def calibrate(self) -> None:
        """Calibrate the <xxx>Harp instrument. <xxx> = Hydra, Pico

        This method should be called before starting a measurement.

        Calibrates the time measurement circuits. This is necessary whenever temperature changes > 5 K occurred.
        Calibrate after warming up of the instrument before starting serious measurements. Warming up takes about 20
        to 30 minutes dependent on the lab temperature. It is completed when the cooling fan starts to run for the first
        time. Calibration takes only a few seconds. Calibration is only important for serious measurements.
        You can use the instrument during the warming-up period for set–up and preliminary measurements. For very long
        measurements, allow some more time for thermal stabilization, calibrate immediately before the measurement
        commences and try to maintain a stable room temperature during the measurement. The permissible ambient
        temperature is 15°C to 35 °C. Do not obstruct the cooling fan at the back and the air inlets at the bottom of
        the housing.
        """
        raise NotImplementedError()

    @rpc_method
    def set_marker_edges(self, me0_str: str, me1_str: str, me2_str: str, me3_str: str) -> None:
        """Set marker edges.

        Change the active edge on which the external TTL signals connected to the marker inputs are triggering.
        Only meaningful in TTTR mode.

        Parameters:
            me0_str (str): edge of marker signal 0.
            me1_str (str): edge of marker signal 1.
            me2_str (str): edge of marker signal 2.
            me3_str (str): edge of marker signal 3.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        me0 = _str_to_enum(_EDGE, me0_str)
        me1 = _str_to_enum(_EDGE, me1_str)
        me2 = _str_to_enum(_EDGE, me2_str)
        me3 = _str_to_enum(_EDGE, me3_str)
        with self._device_lock:
            self._lib.SetMarkerEdges(self._devidx, me0.value, me1.value, me2.value, me3.value)

    @rpc_method
    def set_marker_enable(self, en0: bool, en1: bool, en2: bool, en3: bool) -> None:
        """Set marker enable.

        Used to enable or disable the external TTL marker inputs.
        Only meaningful in TTTR mode.

        Parameters:
            en0: edge of marker signal 0.
            en1: edge of marker signal 1.
            en2: edge of marker signal 2.
            en3: edge of marker signal 3.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetMarkerEnable(self._devidx, int(en0), int(en1), int(en2), int(en3))

    @rpc_method
    def set_marker_holdoff_time(self, holdofftime: int) -> None:
        """Set marker hold-off time.

        Parameters:
            holdofftime: hold-off time in [ns]. Ranges from 0 ns 25500 ns.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetMarkerHoldoffTime(self._devidx, holdofftime)

    @rpc_method
    def start_measurement(self, tacq: int) -> None:
        """Start a measurement.

        Parameters:
            tacq: acquisition time, in [ms], ranging from 1 to 360000000; corresponding to 100 hours)

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        if self._measurement_running:
            raise QMI_InvalidOperationException("Measurement still active")

        assert self._fetch_events_thread is not None
        with self._device_lock:
            self._lib.StartMeas(self._devidx, tacq)

        self._measurement_start_time = time.time()
        self._measurement_running = True
        if self._mode == _MODE.T2:
            # Start collecting data in the background thread.
            self._fetch_events_thread.activate(_MODE.T2)

        elif self._mode == _MODE.T3:
            with self._device_lock:
                # Get sync rate and resolution from the Harp first
                sync_rate = ctypes.c_int()
                self._lib.GetSyncRate(self._devidx, sync_rate)
                resolution = ctypes.c_double()
                self._lib.GetResolution(self._devidx, resolution)

            # Start collecting data in the background thread.
            self._fetch_events_thread.activate(_MODE.T3, sync_rate.value, int(resolution.value))

        _logger.info("[%s] Activated events thread fetching in mode %r", self._name, self._mode)

    @rpc_method
    def stop_measurement(self) -> None:
        """Stop a running measurement.

        This call can be used to force a stop before the acquisition time expires.

        Important:
            For cleanup purposes, this must be called after a measurement, even if the measurement has expired on its
            own!

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        with self._device_lock:
            self._lib.StopMeas(self._devidx)
        if self._mode in [_MODE.T2, _MODE.T3]:
            # Stop collecting data in the background thread.
            self._fetch_events_thread.deactivate()
            _logger.info("[%s] De-activated events thread fetching for mode %r", self._name, self._mode)
        self._measurement_running = False

    @rpc_method
    def get_measurement_active(self) -> bool:
        """Check if measurement is active.

        This method will return False if a measurement has expired on its own, even if
        the method `stop_measurement()` has not yet been called.

        Returns:
            | True - acquisition time still running.
            | False - acquisition time has ended.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            ctcstatus = ctypes.c_int()
            self._lib.CTCStatus(self._devidx, ctcstatus)
            ctcstatus_int = ctcstatus.value
        return ctcstatus_int == 0

    @rpc_method
    def get_measurement_start_time(self) -> float:
        """Return the approximate POSIX timestamp of the start of the current measurement.

        The returned timestamp is based on the computer system clock.
        Its accuracy depends on the latency of USB communication with the instrument,
        process scheduling delay and the accuracy of the system clock.

        Returns:
            POSIX timestamp as a floating point number
        """
        self._check_is_open()
        return self._measurement_start_time

    @rpc_method
    def get_events(self) -> np.ndarray:
        """Return events recorded by the instrument in T2 or T3 mode.

        While a measurement is active, a background thread continuously reads
        event records from the instrument and stores the events in a buffer.
        This method takes all pending events, removes them from the buffer and returns them.

        Events are returned as an array of event records.
        Each event record contains two fields:
        | `type` (uint8): The channel index where the event was recorded, or 64 for a SYNC event.
        | `timestamp` (uint64): Event timestamp as a multiple of the instrument base resolution.

        This method may only be used in T2 or T3 mode.

        Returns:
            Numpy array containing event records.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        _logger.info("[%s] Fetching events from thread in mode %r", self._name, self._mode)
        (_timestamp, events) = self._fetch_events_thread.get_events(self.MAX_EVENTS_PER_CALL)
        return events

    @rpc_method
    def get_timestamped_events(self) -> tuple[float, np.ndarray]:
        """Return events recorded by the instrument in T2 or T3 mode.

        While a measurement is active, a background thread continuously reads
        event records from the instrument and stores the events in a buffer.
        This method takes all pending events, removes them from the buffer and returns them.

        Events are returned as an array of event records.
        Each event record contains two fields:
        | `type` (uint8): The channel index where the event was recorded, or 64 for a SYNC event.
        | `timestamp` (uint64): Event timestamp as a multiple of the instrument base resolution.

        This method may only be used in T2 or T3 mode.

        Returns:
            Tuple `(timestamp, events)`
            where `timestamp` is the approximate wall-clock time where the last event record was received,
            and `events` is a Numpy array containing the event records.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        _logger.info("[%s] Fetching timestamped events from thread in mode %r", self._name, self._mode)
        return self._fetch_events_thread.get_events(self.MAX_EVENTS_PER_CALL)

    @rpc_method
    def get_resolution(self) -> float:
        """Get time resolution.

        Returns:
            The resolution at the current binning (histogram bin width) as a float, in [ps]. Not meaningful in T2 mode.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            resolution = ctypes.c_double()
            self._lib.GetResolution(self._devidx, resolution)
            return resolution.value

    @rpc_method
    def get_sync_rate(self) -> int:
        """Return SYNC rate in events per second (determined every 100 ms).

        Allow at least 100 ms after :func:`initialize` or :func:`setSyncDivider` to get a stable rate meter reading.
        Similarly, wait at least 100 ms to get a new reading (100 ms is the gate time of the counter).

        Returns:
            Sync event rate in events per second.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            syncrate = ctypes.c_int()
            self._lib.GetSyncRate(self._devidx, syncrate)
            return syncrate.value

    @rpc_method
    def get_count_rate(self, channel: int) -> int:
        """Return input channel rate in events per second (determined every 100 ms).

        Allow at least 100 ms after :func:`initialize` to get a stable rate meter reading.
        Similarly, wait at least 100 ms to get a new reading (100 ms is the gate time of the counter).

        Parameters:
            channel: Channel index (range from 0 to `number_of_channels` - 1).

        Returns:
            Channel event rate in events per second.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            cntrate = ctypes.c_int()
            self._lib.GetCountRate(self._devidx, channel, cntrate)
            return cntrate.value

    @rpc_method
    def get_elapsed_measurement_time(self) -> float:
        """Get elapsed measurement time.

        Obtain the elapsed measurement time of a measurement. This relates to the current measurement when
        still running or to the previous measurement when already finished.

        Returns:
            The elapsed measurement time, in [ms].

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            elapsed = ctypes.c_double()
            self._lib.GetElapsedMeasTime(self._devidx, elapsed)
            return float(elapsed.value)

    @rpc_method
    def get_sync_period(self) -> float:
        """Get the sync period.

        This method only gives meaningful results while a measurement is running and after two sync periods have
        elapsed. The return value is undefined in all other cases. Resolution is that of the device's base
        resolution. Accuracy is determined by single shot jitter and clock stability.

        Returns:
            The sync period in [s].

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            period = ctypes.c_double()
            self._lib.GetSyncPeriod(self._devidx, period)
            return period.value

    @rpc_method
    def set_block_events(self, blocked: bool) -> None:
        """Enable or disable blocking event data.

        This feature can be used to "pause" the event data stream.
        The instrument will continue measuring and tagging events, but all
        event records will be discarded by the QMI driver.

        While events are blocked, the instrument will maintain its time base
        such that time intervals between events before and after the pause
        will be correctly represented.

        If real-time histograms are enabled, these will still be updated
        while events are blocked.

        This function only affects measurements in T2 mode.

        Parameter:
            block: True to block all event data, False to resume reporting event data.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        _logger.info("[%s] Setting event data stream blocking to %r", self._name, blocked)
        self._fetch_events_thread.set_block_events(blocked)

    @rpc_method
    def set_event_filter(self,
                         reset_filter: bool = False,
                         channel_filter: dict[int, EventFilterMode] | None = None,
                         sync_aperture: tuple[int, int] | None = None,
                         ) -> None:
        """Configure the event filter.

        When measuring in T2 mode, incoming events are passed through a filter
        to reject uninteresting events. This event filter is implemented in
        the QMI driver software (not inside the instrument).

        The filter is configured separately for each event type.
        Event types 0 to 7 correspond to the normal input channels.
        Event type 64 represents SYNC events.

        Each event type can be configured either to reject all events (`EventFilterMode.NO_EVENTS`),
        or to accept all events (`EventFilterMode.ALL_EVENTS`) or to accept only events that occur
        within a specific time window after a SYNC event (`EventFilterMode.APERTURE`).

        If `EventFilterMode.APERTURE` is selected for the SYNC channel, the filter accepts
        only the SYNC events that are either preceded or followed by a non-SYNC events.
        This mode can be used to discard redundant SYNCs when nothing interesting is happening.

        Parameters:
            reset_filter:   Configure the filter so that all normal events and SYNC events are accepted.
            channel_filter: Mapping from event type to the new event filter mode to be configured.
                            Any event types not specified in the mapping are left in their current setting.
            sync_aperture:  Tuple (delta_min, delta_max) in multiples of the instrument base resolution,
                            defining a time window following each SYNC event.
                            If unspecified or None, the current aperture setting is left unchanged.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None

        if reset_filter:
            # Reset filter so that all event types are accepted (normal input channels, SYNC).
            self._event_filter_channels.clear()
            for event_type in range(NUM_CHANNELS):
                self._event_filter_channels[event_type] = EventFilterMode.ALL_EVENTS
            self._event_filter_channels[SYNC_TYPE] = EventFilterMode.ALL_EVENTS
            _logger.info("[%s] Reset event filter to accept all event types", self._name)

        if channel_filter is not None:
            self._event_filter_channels.update(channel_filter)
            _logger.info("[%s] Set event filter to filter channels %s", self._name, channel_filter)

        if sync_aperture is not None:
            self._event_filter_aperture = sync_aperture
            _logger.info("[%s] Set event sync aperture to be %s", self._name, sync_aperture)

        self._fetch_events_thread.set_event_filter_config(self._event_filter_channels, self._event_filter_aperture)

    @rpc_method
    def set_realtime_histogram(self, channels: list[int], bin_resolution: int, num_bins: int, num_sync: int) -> None:
        """Configure real-time histograms.

        When measuring in T2 mode, the driver can optionally report real-time histograms.
        Each received event is assigned to a histogram bin based on the time interval between
        the last SYNC and the event. The histogram is integrated during several SYNC periods.
        After a configurable number of SYNC events, the integrated histogram is published
        via `sig_histogram`.

        Parameters:
            channels:       List of channels to include in the histogram (range 0 to 7).
            bin_resolution: Resolution of each histogram bin as a multiple of the instrument base resolution.
            num_bins:       Number of bins in the histogram (determines the maximum time interval after SYNC).
            num_sync:       Number of SYNC periods to integrate before publishing the histogram.
                            Specify 0 to disable real-time histograms.
        """
        if bin_resolution < 1:
            raise ValueError("Invalid bin_resolution")
        self._check_is_open()
        assert self._fetch_events_thread is not None
        self._fetch_events_thread.set_histogram_config(channels, bin_resolution, num_bins, num_sync)
        _logger.info(
            "[%s] Set histogram for channels %s to have resolution of %i with %i bins and %i sync periods",
            self._name, channels, bin_resolution, num_bins, num_sync
        )

    @rpc_method
    def set_realtime_countrate(self, sync_aperture: tuple[int, int], num_sync: int) -> None:
        """Configure real-time count rate reporting.

        When measuring in T2 mode, the driver can optionally report real-time count rates.
        Events that fall in a specific time window after the SYNC pulse are counted.
        This counter is integrated during several SYNC periods.
        After a configurable number of SYNC events, the integrated counter values are
        published via `sig_countrate`.

        Parameters:
            sync_aperture:  Tuple (delta_min, delta_max) as a multiple of the instrument base resolution,
                            defining a time window after each SYNC pulse.
            num_sync:       Number of SYNC periods to integrate before publishing the counter value.
                            Specify 0 to disable the real-time countrate monitoring.
        """
        self._check_is_open()
        assert self._fetch_events_thread is not None
        self._fetch_events_thread.set_countrate_config(sync_aperture, num_sync)
        _logger.info(
            "[%s] Set real-time countrate with sync aperture %s with %i sync periods",
            self._name, sync_aperture, num_sync
        )

    @rpc_method
    def set_histogram_length(self, lencode: int) -> int:
        """Set the length of the histogram.

        Set the number of bins of the collected histograms. The histogram length is 65536 which is also the
        default after initialization if `set_histogram_length` is not called.

        Parameters:
            lencode: The histogram length code requesting a histogram of (1024 * 2**`lencode`) bins.
                     Valid range is from 0 to 6.

        Returns:
            The current length (time bin count) of histograms calculated as (1024 * 2**`lencode`).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            actuallen = ctypes.c_int()
            self._lib.SetHistoLen(self._devidx, lencode, actuallen)
            self._actuallen = actuallen.value  # Update actual histogram buffer size
            return actuallen.value  # returns the actual length

    @rpc_method
    def set_measurement_control(self, meascontrol_str: str, startedge_str: str, stopedge_str: str) -> None:
        """Set the measurement control mode.

        This must be called before starting a measurement. The default after initialization (if this function is not
        called) is 0, i.e., software controlled acquisition time. The other modes 1..5 allow hardware triggered
        measurements through TTL signals at the control port or through White Rabbit. Note that this needs custom
        software.

        Parameters:
            meascontrol_str: Measurement control code. Any of 'SINGLESHOT_CTC', 'C1_GATED', 'C1_START_CTC_STOP',
                'C1_START_C2_STOP', 'WR_M2S', 'WR_S2M'.
            startedge_str : Start edge selection. Either 'RISING' or 'FALLING'.
            stopedge_str: Stop edge selection. Either 'RISING' or 'FALLING'.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def clear_histogram_memory(self) -> None:
        """Reset the histogram state to all-zeros.

        Clear the histogram memory of all channels. Only meaningful in histogramming mode.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.ClearHistMem(self._devidx)

    @rpc_method
    def set_offset(self, offset: int) -> None:
        """Set time offset.

        This offset only applies in histogramming and T3 mode. It affects only the difference between stop and start
        before it is put into the T3 record or is used to increment the corresponding histogram bin.

        It is intended for situations where the range of the histogram is not long enough to look at "late" data. By
        means of the offset the "window of view" is shifted to a later range.

        This is not the same as changing or compensating cable delays. If the latter is desired,
        use :func:`setSyncChannelOffset` and/or :func:`setInputChannelOffset`.

        Parameters:
            offset: time offset in [ns], ranging from 0 ns to 100000000 ns.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetOffset(self._devidx, offset)

    @rpc_method
    def set_binning(self, binning: int) -> None:
        """Set time binning.

        Parameters:
            binning: the following values can be used:

                     | 0 = 1× base resolution,
                     | 1 = 2× base resolution,
                     | 2 = 4× base resolution,
                     | 3 = 8× base resolution, and so on.

                     Range is 0 to (`BINSTEPSMAX` - 1).

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetBinning(self._devidx, binning)

    @rpc_method
    def set_stop_overflow(self, stop_ovfl: bool, stopcount: int) -> None:
        """Set stop overflow count value.

        This setting determines if a measurement run will stop if any channel reaches the maximum set by the
        `stopcount` parameter.

        If `stop_ovfl` is False, the measurement will continue but counts above `STOPCNTMAX` in any bin will be clipped.

        Parameters:
            stop_ovfl: If true, the measurement will stop once the limit is reached. If not, the measurement will
                continue.
            stopcount: 1 to 4294967295.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            stop_ovfl_int = 1 if stop_ovfl else 0
            self._lib.SetStopOverflow(self._devidx, stop_ovfl_int, stopcount)

    @rpc_method
    def set_sync_divider(self, divider: int) -> None:
        """Set the SYNC divider value.

        The sync divider must be used to keep the effective sync rate at values < 78 MHz.
        It should only be used with sync sources of stable period.

        Using a larger divider than strictly necessary does not do great harm but it may result in slightly larger
        timing jitter.

        The readings obtained with :func:`get_count_rate` are internally corrected for the divider setting and
        deliver the external (undivided) rate. The sync divider should not be changed while a measurement is running.

        Parameters:
            divider: value ranging from 1 to 16.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetSyncDiv(self._devidx, divider)

    @rpc_method
    def set_sync_cfd(self, level: int, zc: int) -> None:
        """Set Constant Fraction Discriminator (CFD) levels for SYNC input.

        Notes:
            The values are given as a positive numbers although the electrical signals are actually negative.

        Args:
            level: CFD discriminator level in millivolts (mV) range 0 to 1000 representing 0 to -1000 mV.
            zc: CFD zero cross level in millivolts (mV). range 0 to 40 mV representing 0 to 40 mV.
        """
        raise NotImplementedError()

    @rpc_method
    def set_input_cfd(self, channel: int, level: int, zc: int) -> None:
        """Set Constant Fraction Discriminator (CFD) levels for input channel.

        Args:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            level: CFD discriminator level in millivolts (mV) range 0 to 1000 representing 0 to -1000 mV.
            zc: CFD zero cross level in millivolts (mV). range 0 to 40 mV representing 0 to 40 mV.
        """
        raise NotImplementedError()

    @rpc_method
    def set_sync_offset(self, sync_offset: int) -> None:
        """Set SYNC offset.

        This function can replace an adjustable cable delay. A positive offset corresponds to inserting a cable in
        the sync input.

        Parameters:
            sync_offset: SYNC offset, in [ps]. A value ranging from -99999 ps to +99999 ps.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def set_sync_channel_offset(self, value: int) -> None:
        """Set SYNC channel offset.

        This is equivalent to changing the cable delay on the sync input. Actual resolution is the device's base
        resolution.

        Parameters:
            value: SYNC channel offset, in [ps]. A value ranging from -99999 ps to +99999 ps.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def set_input_channel_offset(self, channel: int, value: int) -> None:
        """Set input channel offset.

        This is equivalent to changing the cable delay on the chosen input. Actual resolution is the device's base
        resolution.

        Parameters:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            value: channel offset, in [ps]. A value ranging from -99999 ps to +99999 ps.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            self._lib.SetInputChannelOffset(self._devidx, channel, value)

    @rpc_method
    def set_input_channel_enable(self, channel: int, enable: bool) -> None:
        """Enable or disable the input channel.

        Parameters:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            enable: True to enable the channel, False to disable.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            enable_int = 1 if enable else 0
            self._lib.SetInputChannelEnable(self._devidx, channel, enable_int)

    @rpc_method
    def get_flags(self) -> list[str]:
        """Get flags.

        Returns:
            A list of active flags, represented as short strings.
            See the definition of the :class:`~qmi.instruments.picoquant.<xxx>harp_wrapper.FLAG`
            type for possible values. <xxx> = multi, hydra, pico or time.
            The meaning of these flags is not fully documented.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_histogram(self, channel: int, clear: int | None = None) -> np.ndarray:
        """Get histogram data array from a specific channel. Note that MH_GetHistogram cannot be used with the
        shortest two histogram lengths of 1024 and 2048 bins. You need to use MH_GetAllHistograms in this case.

        Parameters:
            channel: Channel index (range from 0 to `number_of_channels` - 1).
            clear: Optional input for HydraHarp only: 0 = keep histogram in buffer, 1 = clear buffer

        Returns:
              Histogram data array for given input channel.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            # The histogram buffer size must correspond to the default or the value obtained through MH_SetHistoLen().
            hist_data = np.empty(self._actuallen, dtype=np.uint32)
            ctypes_hist_data = hist_data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32))
            if clear is not None:
                self._lib.GetHistogram(self._devidx, ctypes_hist_data, channel, clear)

            else:
                self._lib.GetHistogram(self._devidx, ctypes_hist_data, channel)

            return hist_data.copy()

    @rpc_method
    def get_all_histograms(self) -> np.ndarray:
        """Get histogram data array from a specific channel. The multidimensional array receiving the data must be
         shaped according to the number of input channels of the device and the chosen histogram length.

        Returns:
              Histogram data arrays of all channels.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_warnings(self) -> list[str]:
        """Get a list of warnings.

        Returns:
            A list of strings. See the definition of the :class:`~qmi.instruments.picoquant.<xxx>harp_wrapper.WARNING`
            type for possible values. <xxx> = multi, hydra, pico or time.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_warnings_text(self, warnings: int) -> str:
        """Translates warnings into human-readable text.

        Parameters:
            warnings: integer bitfield obtained from MH_GetWarnings

        Returns:
            The warning text string.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        self._check_is_open()
        with self._device_lock:
            text = ctypes.create_string_buffer(16384)
            self._lib.GetWarningsText(self._devidx, text, warnings)
            return text.value.decode()

    @rpc_method
    def set_trigger_output(self, period: int) -> None:
        """Set trigger output.

        Set the period of the programmable trigger output. The period 0 switches it off.

        Parameters:
            period: Period in units of 100 ns range is 0 to 16777215.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()

    @rpc_method
    def get_module_info(self) -> list[tuple[int, int]]:
        """Get the model and version codes of all modules of the device.

        Note:
            This function can only be used after the :func:`initialize` method was successfully called.

        Returns:
            List of tuples (modelcode, versioncode).
            This information may be needed for support queries.
            The meaning of these numbers is not documented.

        Raises:
            QMI_InstrumentException: in case of a library error.
        """
        raise NotImplementedError()
