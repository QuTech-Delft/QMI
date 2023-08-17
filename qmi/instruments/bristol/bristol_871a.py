"""Instrument driver for the Bristol 871A Laser Wavelength Meter."""

import collections
import logging
import math
import struct
import time
from typing import List, NamedTuple, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.thread import QMI_Thread
from qmi.core.transport import create_transport, QMI_Transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Wavelength measurements produced by instrument.
Measurement = NamedTuple(
    "Measurement",
    [
        ("timestamp", float),
        ("index", int),
        ("status", int),
        ("wavelength", float),
        ("power", float),
    ],
)


class _ReaderThread(QMI_Thread):
    """Background thread to read streaming samples from the instrument's RS-422 port."""

    # Check for thread shutdown request every POLL_DURATION seconds.
    POLL_DURATION = 0.100

    def __init__(self, transport: QMI_Transport, queue: collections.deque) -> None:
        # A more specific type annotation would be "queue: Deque[Measurement]".
        # However we can not use it because "Deque" does not exist in Python 3.5.3.
        super().__init__()
        self._transport = transport
        self._queue = queue

    def run(self) -> None:
        """Read measurements from serial port and append to internal queue."""

        while not self._shutdown_requested:
            # Read next measurement from serial stream.
            measurement = self._read_measurement()

            if measurement is not None:
                # Append measurement to queue.
                # NOTE: Appending to a deque is thread-safe.
                self._queue.append(measurement)

    def _read_measurement(self) -> Optional[Measurement]:
        """Read a single measurement from the serial port.

        Returns:
            Next measurement, or None if shutdown requested before a complete measurement was received.
        """

        # Skip until start-of-measurement byte.
        while not self._shutdown_requested:
            data = self._transport.read_until_timeout(1, timeout=self.POLL_DURATION)
            if data == b"\x7e":
                # Got start-of-measurement byte.
                break

        if self._shutdown_requested:
            return None

        # Take timestamp of measurement.
        timestamp = time.time()

        # Receive complete measurement (20 bytes after decoding).
        message_length = 20
        buf = bytearray()
        escape_pending = False
        while (not self._shutdown_requested) and (len(buf) < message_length):
            data = self._transport.read_until_timeout(
                message_length - len(buf), timeout=self.POLL_DURATION
            )
            position = data.find(0x7E)
            if position >= 0:
                # Got another start-of-measurement byte (data corruption).
                buf.clear()
                position += 1
                escape_pending = False
            else:
                position = 0
            while position < len(data):
                if escape_pending:
                    # Decode escaped byte.
                    buf.append(data[position] ^ 0x20)
                    position += 1
                    escape_pending = False
                else:
                    # Find next escape sequence.
                    escape_sequence_position = data.find(0x7D, position)
                    if escape_sequence_position < 0:
                        # Copy rest of string.
                        buf.extend(data[position:])
                        break

                    # Copy until next escape sequence.
                    buf.extend(data[position:escape_sequence_position])
                    position = escape_sequence_position + 1
                    escape_pending = True

        if self._shutdown_requested:
            return None

        # Unpack measurement values:
        #   wavelength: double
        #   power: float
        #   status: uint32
        #   index: uint32
        assert len(buf) == message_length
        (wavelength, power, status, index) = struct.unpack("<dfII", buf)

        # Erroneous measurements are signified by the 'status', but also by the
        # (observed, undocumented) fact that the 'wavelength' is returned as 0.0.
        # To prevent accidents, we replace this error value by NaN.
        if wavelength == 0.0:
            wavelength = math.nan

        return Measurement(timestamp, index, status, wavelength, power)


class Bristol_871A(QMI_Instrument):
    """Instrument driver for the Bristol 871A wavelength meter.

    This driver implements two connections to the instrument:

    - A text-based (SCPI) bidirectional channel via TCP port 23, for configuration and on-demand measurements;
    - A binary output channel (RS-422), emitting small packets corresponding to processed measurements.

    Either of the channels (but not both) may be left unspecified at instantiation time.

    Attributes:
        CONDITION_BITS: A dictionary mapping condition values to messages.
        STATUS_BITS: A dictionary mapping status bit indices to a descriptive message.
        DEFAULT_QUEUE_SIZE: An integer that indicates the size of the RS-422 message queue, if no value is specified
            in the constructor.
        RESPONSE_TIMEOUT: The timeout for SCPI commands, in seconds.
        STATUS_MASK: Bitmask value of all status bits that have a defined meaning.
        STATUS_GOOD: Status value of a wavelength measurement without any issues.
    """

    _rpc_constants = ["CONDITION_BITS", "STATUS_BITS", "STATUS_MASK", "STATUS_GOOD"]

    # Condition codes returned by get_condition(), by bit index.
    CONDITION_BITS = {
        0: "The wavelength has already been read for the current scan",
        2: "The previous requested calibration has failed",
        3: "The power value is outside the valid range of the instrument",
        4: "The temperature value is outside the valid rang of the instrument",
        5: "The wavelength value is outside the valid range of the instrument",
        6: "The detector signal is saturated",
        7: "The detector signal is low",
        8: "No measurable signal was detected",
        9: "The pressure value is outside the valid range of the instrument",
        10: "At least one bit is set in the questionable hardware condition register",
    }

    # Status codes returned in the Measurement.status field, by bit index.
    STATUS_BITS = {
        2: "Reference laser locked",
        3: "Etalon fringe error",
        4: "Etalon saturation error",
        7: "Calibration failure",
        11: "Reference laser not stable",
        13: "Temperature high",
        14: "Temperature low",
        15: "Pressure high",
        16: "Pressure low",
        17: "Wavelength outside instrument specification",
        19: "Etalon fringe error",
        20: "Etalon saturation error",
        21: "Calibration in progress",
        22: "Etalon fringe error",
        23: "Etalon saturation error",
        27: "Wavelength accuracy reduced",
        29: "Low detector signal",
        30: "Fringe frequency error",
    }

    # Default queue holds up to 10000 measurements.
    DEFAULT_QUEUE_SIZE = 10000

    # We expect the instrument to respond within 2 seconds.
    RESPONSE_TIMEOUT = 2.0

    # Status bit mask, indicating all bits that have a well-defined meaning.
    STATUS_MASK = 0x68FBE89C

    # Expected status word for correct, accurate samples.
    STATUS_GOOD = 0x00000004

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        scpi_transport: Optional[str],
        serial_transport: Optional[str],
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        """Initialize the instrument driver.

        Args:
            name: Name for this instrument instance.
            scpi_transport: QMI transport descriptor for the SCPI channel.
                If not specified, the SCPI channel will not be opened.
            serial_transport: QMI transport descriptor for the serial output channel.
                If not specified, the SCPI channel will not be opened.

        Raises:
            ValueError: At least one of scpi_transport or serial_transport must be specified.
            QMI_TransportDescriptorException: a bad transport string was specified.
        """
        super().__init__(context, name)

        if scpi_transport is None and serial_transport is None:
            raise ValueError(
                "Either scpi_transport or serial_transport should be specified."
            )

        self._scpi_transport = None  # type: Optional[QMI_Transport]
        self._scpi_protocol = None  # type: Optional[ScpiProtocol]
        self._serial_transport = None  # type: Optional[QMI_Transport]
        self._reader_thread = None  # type: Optional[_ReaderThread]
        self._reader_queue = collections.deque(
            maxlen=queue_size
        )  # type: collections.deque

        if scpi_transport is not None:
            self._scpi_transport = create_transport(scpi_transport)
            self._scpi_protocol = ScpiProtocol(self._scpi_transport)

        if serial_transport is not None:
            self._serial_transport = create_transport(serial_transport)
            self._reader_thread = _ReaderThread(
                self._serial_transport, self._reader_queue
            )
            self._reader_thread.start()

    @rpc_method
    def open(self) -> None:
        """Open the SCPI and/or serial channel to the wavemeter."""
        _logger.info("Opening connection to instrument")
        if self._scpi_transport is not None:
            self._scpi_transport.open()
        if self._serial_transport is not None:
            self._serial_transport.open()
        super().open()
        if self._scpi_transport is not None:
            try:
                self._scpi_handshake()
            except Exception:
                self._scpi_transport.close()
                raise

    @rpc_method
    def close(self) -> None:
        """Close the SCPI and/or serial channel to the wavemeter."""
        _logger.info("Closing connection to instrument")
        self._check_is_open()
        if self._reader_thread is not None:
            self._reader_thread.shutdown()
            self._reader_thread.join()
        super().close()
        if self._serial_transport is not None:
            self._serial_transport.close()
        if self._scpi_transport is not None:
            self._scpi_transport.close()

    def _write_scpi(self, cmd: str) -> None:
        """Send SCPI command to instrument."""

        assert self._scpi_protocol is not None
        self._scpi_protocol.write(cmd)

    def _ask_scpi(self, cmd: str) -> str:
        """Send command to instrument and return response from instrument."""

        assert self._scpi_protocol is not None
        return self._scpi_protocol.ask(cmd).rstrip("\r\n")

    @rpc_method
    def reset(self) -> None:
        """Reset the wavemeter using the SCPI '\\*RST' command.

        This resets (most) settings to their default values.
        """
        _logger.info("Resetting %s", self._name)
        self._write_scpi("*RST")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read wavemeter instrument type and version

        Returns:
            A QMI_InstrumentIdentification instance.
        """
        resp = self._ask_scpi("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(
                "Unexpected response to *IDN?, got {!r}".format(resp)
            )
        return QMI_InstrumentIdentification(
            vendor=words[0].strip(),
            model=words[1].strip(),
            serial=words[2].strip(),
            version=words[3].strip(),
        )

    def _scpi_handshake(self) -> None:
        """Read initial welcome message from Telnet port."""

        assert self._scpi_transport is not None

        while True:
            resp = self._scpi_transport.read_until(
                message_terminator=b"\n", timeout=self.RESPONSE_TIMEOUT
            )
            if resp.find(b"no connections available") >= 0:
                _logger.error("Can not connect to %s SCPI port (%r)", self._name, resp)
                raise QMI_InstrumentException(
                    "Can not connect to {} SCPI port".format(self._name)
                )
            if resp.find(b"Bristol Instruments") >= 0:
                # This is almost the last line of the welcome message. One more empty line follows.
                break

        # Send IDN command.
        self._write_scpi("*IDN?")

        # Wait for IDN response.
        while True:
            resp = self._scpi_transport.read_until(
                message_terminator=b"\n", timeout=self.RESPONSE_TIMEOUT
            )
            if resp.startswith(b"*IDN?"):
                # Got command echo. This should never happen.
                raise QMI_InstrumentException(
                    "Instrument {} sent unexpected command echo".format(self._name)
                )
            if resp.startswith(b"BRISTOL"):
                # Got IDN response.
                break

    @staticmethod
    def _parse_int(resp: str, cmd: str) -> int:
        """Parse integer response from instrument.

        Return integer value or raise QMI_InstrumentException.
        """
        try:
            return int(resp)
        except ValueError:
            raise QMI_InstrumentException(
                "Expecting integer response to command {!r} but got {!r}".format(
                    cmd, resp
                )
            )

    @staticmethod
    def is_valid_measurement(measurement: Measurement) -> bool:
        """Return True if the specified measurement represents a valid, accurate measured wavelength."""
        return (
            (measurement.status & Bristol_871A.STATUS_MASK) == Bristol_871A.STATUS_GOOD
        ) and (measurement.wavelength > 0)

    @rpc_method
    def read_measurement(self) -> Measurement:
        """Read next measurement and return measured value as a Measurement instance."""
        resp = self._ask_scpi(":READ:ALL?")
        timestamp = time.time()
        words = resp.split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(
                "Unexpected response to :READ:ALL? ({!r})".format(resp)
            )
        try:
            index = int(words[0])
            status = int(words[1])
            wavelength = float(words[2])
            power = float(words[3])
        except ValueError:
            raise QMI_InstrumentException(
                "Unexpected response to :READ:ALL? ({!r})".format(resp)
            )
        # Erroneous measurements are signified by the 'status', but also by the
        # (observed, undocumented) fact that the 'wavelength' is returned as 0.0.
        # To prevent accidents, we replace this error value by NaN.
        if wavelength == 0.0:
            wavelength = math.nan
        return Measurement(timestamp, index, status, wavelength, power)

    @rpc_method
    def calibrate(self) -> None:
        """Start calibration of the instrument.

        Calibration takes approximately 2 seconds and interrupts measurements for its duration.
        """
        self._write_scpi(":SENS:CALI")

        # The calibration takes a few seconds and we like to ensure that the process has finished once we return from
        # this function.
        time.sleep(5.0)

    @rpc_method
    def get_auto_calibration_method(self) -> str:
        """Return the current auto-calibration method.

        :return: "OFF" if auto-calibration is disabled;
            "TIME" when time-driven auto-calibration enabled;
            "TEMP" when temperature-driven auto-calibration enabled.
        """
        return self._ask_scpi(":SENS:CALI:METH?")

    @rpc_method
    def set_auto_calibration_method(self, method: str) -> None:
        """Set auto-calibration method.

        :argument method: Valid values are "OFF" or "TIME" or "TEMP".
        """
        method_upper = method.upper()
        if method_upper not in ("OFF", "TIME", "TEMP"):
            raise ValueError("Invalid auto-calibration method {!r}".format(method))
        self._write_scpi(":SENS:CALI:METH %s" % method_upper)

    @rpc_method
    def get_auto_calibration_temperature(self) -> int:
        """Return the temperature change (in units of 0.1 degree Celsius) that will initiate recalibration."""
        cmd = ":SENS:CALI:TEMP?"
        resp = self._ask_scpi(cmd)
        return self._parse_int(resp, cmd)

    @rpc_method
    def set_auto_calibration_temperature(self, delta: int) -> None:
        """Set the temperature change that will initiate recalibration when temperature-driven calibration is enabled.

        :argument delta: Temperature change that will initiate recalibration (in units of 0.1 degree Celcius).
            Valid range: 1 to 50.
        """
        if delta < 1 or delta > 50:
            raise ValueError("Invalid temperature threshold for auto-calibration")
        self._write_scpi(":SENS:CALI:TEMP %d" % delta)

    @rpc_method
    def get_auto_calibration_time(self) -> int:
        """Return the time interval [minutes] for automatic recalibration."""
        cmd = ":SENS:CALI:TIM?"
        resp = self._ask_scpi(cmd)
        return self._parse_int(resp, cmd)

    @rpc_method
    def set_auto_calibration_time(self, interval: int) -> None:
        """Set the time interval for recalibration (when time-driven calibration is enabled).

        :argument interval: Recalibration interval in minutes. Valid range: 5 to 1440.
        """
        if interval < 5 or interval > 1440:
            raise ValueError("Invalid time interval for auto-calibration")
        self._write_scpi(":SENS:CALI:TIM %d" % interval)

    @rpc_method
    def get_condition(self) -> int:
        """Read questionable condition register."""
        cmd = ":STAT:QUES:COND?"
        resp = self._ask_scpi(cmd)
        return self._parse_int(resp, cmd)

    @rpc_method
    def get_trigger_method(self) -> str:
        """Return the current trigger method.

        :return: Trigger method: "INT" for internal triggering;
            "FALL" for external trigger on falling edge;
            "RISE" for external trigger on rising edge.
        """
        return self._ask_scpi(":TRIG:SEQ:METH?")

    @rpc_method
    def set_trigger_method(self, method: str) -> None:
        """Set the trigger method.

        :argument method: Trigger method. Valid values: "INT", "FALL", "RISE".
        """
        method_upper = method.upper()
        if method_upper not in ("INT", "FALL", "RISE"):
            raise ValueError("Invalid trigger setting")
        self._write_scpi(":TRIG:SEQ:METH %s" % method_upper)

    @rpc_method
    def get_trigger_rate(self) -> int:
        """Return current trigger rate (in Hz) for the internal trigger."""
        cmd = ":TRIG:SEQ:RATE:ADJ?"
        resp = self._ask_scpi(cmd)
        return self._parse_int(resp, cmd)

    @rpc_method
    def set_trigger_rate(self, rate: int) -> None:
        """Set trigger rate for the internal trigger.

        Args:
            rate: Trigger rate in Hz, or 0 to adjust to optical illumination.
                Valid values are 20, 50, 100, 250, 500, 1000 and 0.
        """
        if rate not in (0, 20, 50, 100, 250, 500, 1000):
            raise ValueError("Invalid trigger rate")
        if rate == 0:
            self._write_scpi(":TRIG:SEQ:RATE:ADJ")
        else:
            self._write_scpi(":TRIG:SEQ:RATE %d" % rate)

    @rpc_method
    def memory_start(self) -> None:
        """Start recording samples in internal memory in the instrument.

        KNOWN FIRMWARE ISSUE: The MMEM INIT/OPEN/CLOSE/DATA? sequence often stops producing samples after running for
            some hours.
        """
        self._write_scpi(":MMEM:INIT")
        self._write_scpi(":MMEM:OPEN")

    @rpc_method
    def memory_stop(self) -> None:
        """Stop recording samples in internal memory.

        KNOWN FIRMWARE ISSUE: The MMEM INIT/OPEN/CLOSE/DATA? sequence often stops producing samples after running for
            some hours.
        """
        self._write_scpi(":MMEM:CLOSE")

    @rpc_method
    def get_memory_contents(self) -> List[Measurement]:
        """Fetch recorded samples from internal memory.

        KNOWN FIRMWARE ISSUE: The MMEM INIT/OPEN/CLOSE/DATA? sequence often stops producing samples after running for
            some hours.
        """

        self._write_scpi(":MMEM:DATA?")
        assert self._scpi_protocol is not None
        data = self._scpi_protocol.read_binary_data()

        message_length = 20
        nbytes = len(data)
        if nbytes % message_length != 0:
            raise QMI_InstrumentException(
                "Expected multiple of 20 bytes in memory but got {} bytes".format(
                    nbytes
                )
            )
        nsamples = nbytes // message_length

        # Unpack measurement values:
        #   wavelength: double
        #   power: float
        #   status: uint32
        #   index: uint32
        ret = []  # type: List[Measurement]
        timestamp = time.time()
        for i in range(nsamples):
            sample = data[i * message_length : (i + 1) * message_length]
            (wavelength, power, status, index) = struct.unpack("<dfII", sample)
            # Erroneous measurements are signified by the 'status', but also by the
            # (observed, undocumented) fact that the 'wavelength' is returned as 0.0.
            # To prevent accidents, we replace this error value by NaN.
            if wavelength == 0.0:
                wavelength = math.nan
            ret.append(Measurement(timestamp, index, status, wavelength, power))

        return ret

    @rpc_method
    def get_streaming_measurements(self) -> List[Measurement]:
        """Return streaming measurements received from the instrument.

        If the instrument uses a serial transport (in addition to the SCPI transport),
        streaming measurements are received from the instrument and buffered in
        the driver. This method returns the list of measurements currently
        in the buffer and removes them from the buffer.

        The buffer has a maximum size of STREAMING_QUEUE_SIZE measurements.
        If the buffer becomes full, old measurements are dropped automatically.

        Returns:
            A list of measurements received since last call.
        """
        ret = []
        for _ in range(len(self._reader_queue)):
            ret.append(self._reader_queue.popleft())
        return ret
