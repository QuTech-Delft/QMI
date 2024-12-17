import importlib
import logging
import time
import enum
from typing import TYPE_CHECKING
from collections.abc import Callable
import ctypes

import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException, QMI_UnknownNameException
from qmi.core.rpc import rpc_method

if TYPE_CHECKING:
    from picosdk.ps3000a import ps3000a
    from picosdk.ps4000a import ps4000a
    _ps: ps3000a | ps4000a | None = None

else:
    _ps = None

# Global dictionary for the imported library commands.
COMMAND_DICT: dict[str, Callable] = dict()
# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def _import_modules(library: str) -> None:
    """Import the "picosdk" module. And update the dictionary of commands in the library.

    This import is done in a function, instead of at the top-level, to avoid an unnecessary dependency for
    programs that do not access the instrument directly. NOTE that only ONE module can be loaded at any time.
    If "ps3000a" is imported to _ps, you cannot use Picoscopes based on "ps4000a" libraries with the same instance.

    parameters:
        library: module library string to import. Like "3000a"
    """
    global _ps, COMMAND_DICT
    library = f"ps{library}"
    if _ps is None:
        ps_lib = importlib.import_module(f"picosdk.{library}")
        _ps = getattr(ps_lib, f"{library}")

    # Map generic commands names without model number into the current model's library module commands
    lib_name = _ps.name
    if lib_name != library:
        raise QMI_UnknownNameException(f"Module library {library} does not match loaded {lib_name} module!")

    commands = [_ for _ in _ps.__dict__ if _.startswith("ps")]
    for command in commands:
        COMMAND_DICT[command.lstrip(lib_name)] = getattr(_ps, command)


def _check_error(status: int) -> None:
    """Raise QMI_InstrumentException when the status code is not equal to `PICO_OK`."""
    assert _ps is not None
    if status != _ps.PICO_STATUS["PICO_OK"]:
        raise QMI_InstrumentException("PicoSDK returned status {}".format(_ps.PICO_STATUS_LOOKUP.get(status, "???")))


class ChannelCoupling(enum.IntEnum):
    """Input coupling configurable for each oscilloscope channel."""
    AC = 0
    DC = 1


class TriggerEdge(enum.IntEnum):
    """Configurable trigger edge modes."""
    RISING = 2
    FALLING = 3
    RISING_OR_FALLING = 4
    NONE = 10


class PicoTech_PicoScope(QMI_Instrument):
    """Base class for PicoTech's PicoScope USB oscilloscope instrument drivers.

    Attributes:
        MIN_SAMPLE_VALUE: Min sample value of int16 range.
        MAX_SAMPLE_VALUE: Max sample value of int16 range.
        NUM_CHANNELS:     Number of oscilloscope channels.
        NUM_INPUT_RANGES: Number of supported input ranges. Range '0' is not supported.
    """
    MIN_SAMPLE_VALUE = -32767
    MAX_SAMPLE_VALUE = 32767
    NUM_CHANNELS = 0
    NUM_INPUT_RANGES = 0

    @staticmethod
    def list_instruments(library: str) -> list[str]:
        """Return a list of serial numbers of detected PicoScope instruments of a specific library type.

        Parameters:
            library: The library type to list, e.g. "3000a"

        Returns:
            serials: A list of serial numbers of devices found which use input library type.
        """
        _import_modules(library)
        max_len = 1024
        par_count = ctypes.c_int16(0)
        par_serials = ctypes.create_string_buffer(max_len)
        par_serialslen = ctypes.c_int16(max_len)
        err = COMMAND_DICT["EnumerateUnits"](ctypes.byref(par_count), par_serials, ctypes.byref(par_serialslen))
        _check_error(err)
        serials = par_serials.value.decode("iso8859-1")
        if serials:
            return serials.split(",")
        else:
            return []

    def __init__(self, context: QMI_Context, name: str, serial_number: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:          Name for this instrument instance.
            serial_number: Serial number of the Picoscope.
        """
        super().__init__(context, name)
        self._serial_number = serial_number
        self._handle: ctypes.c_int16 | None = None
        self._num_samples: int = 0
        self._time_base_interval_ns: float = 0.0
        self._library: str = ""  # The sw library name, e.g. 3000a

    @property
    def _ps_attr(self):
        assert _ps is not None
        return _ps

    @rpc_method
    def get_input_ranges(self) -> dict[int, float]:
        """Return a dictionary mapping supported input range indexes to the corresponding input range in Volt."""
        self._check_is_open()
        return dict((sel, volt) for (sel, volt) in self._ps_attr.PICO_VOLTAGE_RANGE.items()
                    if sel < self.NUM_INPUT_RANGES)

    @rpc_method
    def open(self) -> None:
        _import_modules(self._library)

        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)

        par_handle = ctypes.c_int16(0)
        par_serial = ctypes.create_string_buffer(self._serial_number.encode("iso8859-1"))
        err = COMMAND_DICT["OpenUnit"](ctypes.byref(par_handle), par_serial)
        _check_error(err)

        self._handle = par_handle

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("[%s] Closing connection to instrument", self._name)
        COMMAND_DICT["Stop"](self._handle)
        COMMAND_DICT["CloseUnit"](self._handle)
        # Reset values in `close` for eventual re-open.
        self._handle = None
        self._num_samples = 0
        self._time_base_interval_ns = 0.0

        super().close()

    @rpc_method
    def get_device_variant(self) -> str:
        """Get the type of PicoScope (for example "4824")."""
        self._check_is_open()
        max_len = 1024
        par_string = ctypes.create_string_buffer(max_len)
        par_size = ctypes.c_int16(max_len)
        info = self._ps_attr.PICO_INFO["PICO_VARIANT_INFO"]
        err = COMMAND_DICT["GetUnitInfo"](self._handle, par_string, max_len, ctypes.byref(par_size), info)
        _check_error(err)
        return par_string.value.decode("iso8859-1")

    @rpc_method
    def get_serial_number(self) -> str:
        """Get the batch and serial number of the device."""
        self._check_is_open()
        max_len = 1024
        par_string = ctypes.create_string_buffer(max_len)
        par_size = ctypes.c_int16(max_len)
        info = self._ps_attr.PICO_INFO["PICO_BATCH_AND_SERIAL"]
        err = COMMAND_DICT["GetUnitInfo"](self._handle, par_string, max_len, ctypes.byref(par_size), info)
        _check_error(err)
        return par_string.value.decode("iso8859-1")

    @rpc_method
    def set_channel(
        self, channel: int, enable: bool, coupling: ChannelCoupling, range_sel: int, offset: float
            ) -> None:
        """Configure an oscilloscope input channel.

        Parameters:
            channel:    Input channel (range 0 .. 3).
            enable:     True to enable the channel, False to disable it.
            coupling:   Input coupling (`ChannelCoupling.AC` or `ChannelCoupling.DC`).
            range_sel:  Input range selector (range 0 .. 9). See `get_input_ranges()`.
            offset:     Analog input offset in Volt.
                        This offset is added to the analog input signal before digitizing the signal.
        """
        self._check_is_open()
        if (channel < 0) or (channel >= self.NUM_CHANNELS):
            raise ValueError("Invalid channel index")
        if (range_sel < 0) or (range_sel >= self.NUM_INPUT_RANGES):
            raise ValueError("Invalid input range")

        coupling = self._ps_attr.PICO_COUPLING[coupling.name]
        err = COMMAND_DICT["SetChannel"](self._handle, channel, int(enable), coupling, range_sel, offset)
        _check_error(err)

    @rpc_method
    def set_trigger(self, enable: bool, channel: int, threshold: int, edge: TriggerEdge) -> None:
        """Configure the trigger mode of the oscilloscope.

        Parameters:
            enable:     True to enable triggering, False to disable the trigger.
            channel:    Source channel to trigger on (range 0 .. 7).
            threshold:  Trigger level as an ADC code (range -32767 .. +32767).
            edge:       Trigger edge (`TriggerEdge.RISING` or `TriggerEdge.FALLING`
                        or `TriggerEdge.RISING_OR_FALLING`).
        """
        self._check_is_open()
        if (channel < 0) or (channel >= self.NUM_CHANNELS):
            raise ValueError("Invalid channel index")
        if (threshold < self.MIN_SAMPLE_VALUE) or (threshold > self.MAX_SAMPLE_VALUE):
            raise ValueError("Invalid threshold")

        err = COMMAND_DICT["SetSimpleTrigger"](self._handle, int(enable), channel, threshold, int(edge), 0, 0)
        _check_error(err)

    @rpc_method
    def disable_trigger(self):
        """ Disables all triggers in all channels """
        self._check_is_open()
        err = COMMAND_DICT["SetTriggerChannelConditions"](self._handle, None, 0)
        _check_error(err)

    @rpc_method
    def stop(self) -> None:
        """Stop any ongoing acquisition."""
        self._check_is_open()
        err = COMMAND_DICT["Stop"](self._handle)
        _check_error(err)

    @rpc_method
    def is_block_ready(self) -> bool:
        """Return True if a block acquisition has completed, or False if the acquisition is still in progress.
        Only call this function after starting an acquisition via `run_block()`.
        """
        self._check_is_open()
        par_ready = ctypes.c_int16()
        err = COMMAND_DICT["IsReady"](self._handle, ctypes.byref(par_ready))
        _check_error(err)
        return par_ready.value != 0

    @rpc_method
    def wait_block_ready(self, timeout: float) -> None:
        """Wait until the running block acquisition has completed. Uses the "is_block_ready" above.

        Parameters:
            timeout: Maximum time to wait in seconds.

        Raises:
            ValueError:           If the timeout input value is negative.
            QMI_TimeoutException: If the timeout expires before a block is ready.
        """
        self._check_is_open()
        if timeout < 0:
            raise ValueError("Invalid timeout")

        endtime = time.monotonic() + timeout
        while True:
            par_ready = self.is_block_ready()
            if par_ready:
                break
            elif time.monotonic() >= endtime:
                raise QMI_TimeoutException("Timeout while waiting for block from PicoScope")

            time.sleep(0.01)

    @rpc_method
    def get_block_data(self, channels: list[int]) -> tuple[np.ndarray, float, list[bool]]:
        """Retrieve a block of data, previously acquired via `run_block()`.

        Samples are returned as 16-bit signed integers, where the value
        (2**16-1) corresponds to the maximum positive voltage and -(2**16-1)
        corresponds to the most negative voltage in the input range.

        The number of retrieved samples corresponds to the sum of pre-trigger
        and post-trigger samples as specified in the call to `run_block()`.

        Parameters:
            channels: List of channels for which to retrieve samples and overrange indications.

        Returns:
            samples:   A 2D Numpy array with shape (num_channels, num_samples) containing signed 16-bit samples.
            time_base_interval_ns: The time interval between samples as a floating point number in nanoseconds.
            overrange: A list of booleans indicating whether overvoltage occurred on the selected channels.

        Raises:
            ValueError:              If a channel number in 'channels' is invalid.
            QMI_InstrumentException: If unexpected number of samples were obtained.
        """
        self._check_is_open()

        for chan in channels:
            if (chan < 0) or (chan >= self.NUM_CHANNELS):
                raise ValueError("Invalid channel index")

        # Allocate data buffers.
        buffers: list[ctypes.Array[ctypes.c_int16]] = []
        for chan in range(self.NUM_CHANNELS):

            # Allocate real buffer for selected channels, zero-length buffer for non-selected channels.
            if chan in channels:
                buf_len = self._num_samples
            else:
                buf_len = 0
            buf = (ctypes.c_int16 * buf_len)()
            buffers.append(buf)

            # Register allocated buffer with driver.
            err = COMMAND_DICT["SetDataBuffer"](self._handle, chan, buf, buf_len, 0, 0)
            _check_error(err)

        # Retrieve data.
        par_num_samples = ctypes.c_uint32(self._num_samples)
        par_overflow = ctypes.c_int16(0)
        err = COMMAND_DICT["GetValues"](
            self._handle,
            0,  # startIndex
            ctypes.byref(par_num_samples),
            1,  # downSampleRatio
            0,  # downSampleRatioMode
            0,  # segmentIndex
            ctypes.byref(par_overflow),
        )
        _check_error(err)

        got_samples = par_num_samples.value
        if got_samples != self._num_samples:
            raise QMI_InstrumentException(
                "Got {} samples from PicoScope while expecting {} samples".format(got_samples, self._num_samples)
            )

        # Convert data to Numpy array.
        samples: np.typing.NDArray[np.int16] = np.empty((len(channels), self._num_samples), dtype=np.int16)
        for (i, chan) in enumerate(channels):
            samples[i] = np.ctypeslib.as_array(buffers[chan])

        # Extract overrange markers.
        overrange = [bool((par_overflow.value >> chan) & 1) for chan in channels]

        return samples, self._time_base_interval_ns, overrange

    @rpc_method
    def run_block(self, num_pretrig_samples: int, num_posttrig_samples: int, time_base: int) -> None:
        raise NotImplementedError("Method 'run_block' is not implemented in the base class")

    @rpc_method
    def get_sampling_interval(self, time_base: int) -> float:
        raise NotImplementedError("Method 'get_sampling_interval' is not implemented in the base class")
