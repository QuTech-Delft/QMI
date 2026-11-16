"""Instrument driver for the AlphaLab MR3 three-axis magnetic field meter.

The meter communicates over a (USB) serial port using the generic AlphaLab "Data Acquisition Communication Protocol",
see https://www.alphalabinc.com/wp-content/uploads/2018/02/alphaapp_comm_protocol.pdf. Only the identification,
settings and stream commands of that protocol are implemented here.

Every command sent to the meter is six bytes long: one command byte followed by five "don't matter" bytes.
"""

import logging
import math
from dataclasses import dataclass

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class ParsedDataPoint:
    """A single six-byte data point from a STREAM_DATA record, decoded into its fields.

    Bit layout of the data point (byte 1 is received first)::

        Byte 1:     x I F F H1 H2 C x
        Byte 2:     x x x x S  D  D D
        Byte 3-6:   N (32-bit unsigned integer, most significant byte first)

    Attributes:
        ignore_flag:         I-bit. If True, the data point is null (e.g. an unused axis) and must be ignored.
        field_type:          FF-bits. Field type of the data: 0 = DC, 1 = AC, 2 = peak hold (PH).
        hide_1:              H1-bit. If True, the data point is placed in the continuous (recorded) data stream.
        hide_2:              H2-bit. If True, the data point is hidden from the instantaneous data stream.
        check_settings_flag: C-bit. If True, the meter settings were changed at the meter since the previous record
                             and should be re-queried.
        sign:                S-bit. If True, the value is negative.
        decimal:             DDD-bits. Number of decimal places (0-7); the value is `data_value / 10**decimal`.
        data_value:          N-bits. Unsigned, unscaled magnitude of the value.
        label:               Name of the data point within the record, e.g. "x_axis".
    """

    ignore_flag: bool
    field_type: int
    hide_1: bool
    hide_2: bool
    check_settings_flag: bool
    sign: bool
    decimal: int
    data_value: int
    label: str = ""

    def calculate_value(self) -> float:
        """Calculate the signed, scaled value of the data point.

        Returns:
            The value in the unit the meter reports for this data point, or NaN if the data point is flagged to be
            ignored.
        """
        if self.ignore_flag:
            return math.nan

        value = self.data_value / 10**self.decimal
        return -value if self.sign else value


class AlphaLab_MR3(QMI_Instrument):
    """Instrument driver for the AlphaLab MR3 three-axis magnetic field meter.

    A measurement is done in two steps: `perform_measurement` requests one record from the meter and stores it, after
    which the `get_*` methods return values from that stored record. This way, all values returned after a single
    `perform_measurement` call belong to the same sample.

    The data points of a record are stored under the labels in `DATA_LABELS`, which is an RPC property and can thus be
    changed through the proxy. A label set to an empty string is replaced by the corresponding entry of the
    TABLE_HEADERS meter property, e.g. "X (mG)", which also tells the unit of the value. The convenience methods
    `get_time`, `get_x_field`, etc. select the data point by its position in the record and therefore work for any
    labels; `get_data_point` selects a data point by its (resolved) label.

    Attributes:
        DONT_MATTER:     Filler byte used to pad commands to six bytes.
        ACK:             Acknowledge byte. Sent by the meter when more data follows, and by us to request it.
        TRM:             Terminate byte. Sent by the meter when the last chunk of a message has been sent.
        IDN:             ID_METER_PROP command byte, requests the meter properties.
        GET_SET:         ID_METER_SETT command byte, requests the meter settings.
        STREAM_DATA:     STREAM_DATA command byte, requests a single measurement record.
        DATA_LABELS:     Labels of the data points in a STREAM_DATA record, in the order they are received. An empty
                         string means: use the corresponding entry of the TABLE_HEADERS meter property.
        CHUNK_SIZE:      Number of data bytes in a single chunk of an ASCII message.
        MAX_CHUNKS:      Maximum number of chunks read for a single ASCII message before giving up.
        DATA_POINT_SIZE: Number of bytes in a single data point of a STREAM_DATA record.
    """

    _rpc_properties = {"DATA_LABELS"}

    DONT_MATTER = b"\xaa"
    ACK = b"\x08"
    TRM = b"\x07"
    IDN = b"\x01"
    GET_SET = b"\x02"
    STREAM_DATA = b"\x03"
    DATA_LABELS: tuple[str, ...] = ("Time", "x_axis", "y_axis", "z_axis", "Magnitude")
    CHUNK_SIZE = 20
    MAX_CHUNKS = 30
    DATA_POINT_SIZE = 6

    # Positions of the data points in a STREAM_DATA record.
    _TIME_INDEX = 0
    _X_INDEX = 1
    _Y_INDEX = 2
    _Z_INDEX = 3
    _MAGNITUDE_INDEX = 4

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the driver.

        The `self._data_points` is a dictionary consisting of a data point per (resolved) label in `DATA_LABELS`, in
        record order. The `self._table_headers` caches the TABLE_HEADERS meter property, once it is needed.

        Parameters:
            context:   The QMI context.
            name:      Name for this instrument instance.
            transport: QMI transport descriptor for the serial port, e.g. "serial:COM3". The baud rate defaults to
                       115200, the only rate supported by the meter.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "timeout": 2.0})
        self._data_points: dict[str, ParsedDataPoint] = {}
        self._table_headers: list[str] | None = None

    @staticmethod
    def _parse_data_point(data_point: bytes) -> ParsedDataPoint:
        """Decode a single six-byte data point of a STREAM_DATA record. See `ParsedDataPoint` for the bit layout.

        Parameters:
            data_point: The six bytes of the data point.

        Returns:
            The decoded data point, with an empty label.

        Raises:
            QMI_InstrumentException: If the data point does not consist of exactly six bytes.
        """
        if len(data_point) != AlphaLab_MR3.DATA_POINT_SIZE:
            raise QMI_InstrumentException(
                f"Expected a data point of {AlphaLab_MR3.DATA_POINT_SIZE} bytes, got {len(data_point)} bytes"
            )

        byte_1 = data_point[0]
        byte_2 = data_point[1]
        return ParsedDataPoint(
            ignore_flag=bool(byte_1 & 0b01000000),
            field_type=(byte_1 & 0b00110000) >> 4,
            hide_1=bool(byte_1 & 0b00001000),
            hide_2=bool(byte_1 & 0b00000100),
            check_settings_flag=bool(byte_1 & 0b00000010),
            sign=bool(byte_2 & 0b00001000),
            decimal=byte_2 & 0b00000111,
            data_value=int.from_bytes(data_point[2:6], "big"),
        )

    @staticmethod
    def _parse_key_value_message(msg: bytes) -> dict[str, str]:
        """Parse an ASCII message of the form "Key1=Value1:Key2=Value2:...:KeyN=ValueN:" into a dictionary.

        Anything after the last colon, such as the filler bytes that pad the final chunk, is discarded. Fields without
        an equal sign are tags (e.g. "NO_SETTINGS") and get an empty string as value.

        Parameters:
            msg: The concatenated data bytes of the message.

        Returns:
            Dictionary mapping each key to its value, both as stripped strings.
        """
        result: dict[str, str] = {}
        for field in msg.decode("ascii", errors="replace").split(":")[:-1]:
            key, _, value = field.partition("=")
            key = key.strip(" \x00")
            if key:
                result[key] = value.strip(" \x00")

        return result

    def _send_command(self, command: bytes) -> None:
        """Send a command byte padded with five "don't matter" bytes to the meter."""
        self._transport.write(command + 5 * self.DONT_MATTER)

    def _get_stream_data(self) -> bytes:
        """Request and read a single STREAM_DATA record.

        The record consists of one six-byte data point per entry in `DATA_LABELS`, followed by an ACK byte. In some
        meter modes the record ends with a TRM byte instead, which is also accepted.

        Returns:
            response: The data points of the record, without the trailing ACK/TRM byte.

        Raises:
            QMI_InstrumentException: If the record does not end with an ACK or TRM byte.
            QMI_TimeoutException:    If the meter did not send the full record in time.
        """
        expected_response_length = len(self.DATA_LABELS) * self.DATA_POINT_SIZE + 1
        self._send_command(self.STREAM_DATA)
        response = self._transport.read(expected_response_length, timeout=2.0)
        terminator = response[-1:]
        if terminator not in (self.ACK, self.TRM):
            raise QMI_InstrumentException(f"Unexpected end of stream data record: {terminator!r}")

        return response[:-1]

    def _get_data_until_trm(self) -> bytes:
        """Read an ASCII message that the meter sends in chunks, after a command has been sent.

        Each chunk consists of `CHUNK_SIZE` data bytes followed by an ACK byte if more chunks follow, or a TRM byte
        if it is the last chunk. Every ACK is answered with six ACK bytes to request the next chunk.

        Returns:
            The concatenated data bytes of all chunks. The last chunk may contain filler bytes.

        Raises:
            QMI_InstrumentException: If a chunk ends with an unexpected byte, or if the message is longer than
                                     `MAX_CHUNKS` chunks.
            QMI_TimeoutException:    If a chunk was not received in time.
        """
        msg = b""
        for _ in range(self.MAX_CHUNKS):
            chunk = self._transport.read(self.CHUNK_SIZE + 1, timeout=1.0)
            msg += chunk[:-1]
            terminator = chunk[-1:]
            if terminator == self.TRM:
                return msg

            if terminator != self.ACK:
                raise QMI_InstrumentException(f"Unexpected end of message chunk: {terminator!r}")

            # More data to come, so request the next chunk.
            self._transport.write(6 * self.ACK)

        raise QMI_InstrumentException(f"No end of message received within {self.MAX_CHUNKS} chunks")

    def _resolve_data_labels(self) -> list[str]:
        """Get the data labels, with empty labels replaced by the corresponding TABLE_HEADERS entries.

        The TABLE_HEADERS meter property is only read from the meter if a label is empty and the property has not been
        read since opening the connection or since the meter reported changed settings.

        Returns:
            The resolved data labels, in record order.

        Raises:
            QMI_InstrumentException: If an empty label has no corresponding entry in TABLE_HEADERS.
            QMI_UsageException:      If the resolved labels are not unique.
        """
        labels = list(self.DATA_LABELS)
        if "" in labels:
            if self._table_headers is None:
                table_headers = self.get_properties().get("TABLE_HEADERS", "")
                self._table_headers = [header.strip() for header in table_headers.split(",")] if table_headers else []

            for index, label in enumerate(labels):
                if label == "":
                    if index >= len(self._table_headers):
                        raise QMI_InstrumentException(
                            f"No TABLE_HEADERS entry for empty data label at position {index}: {self._table_headers}"
                        )

                    labels[index] = self._table_headers[index]

        if len(set(labels)) != len(labels):
            raise QMI_UsageException(f"Data labels must be unique, got {labels}")

        return labels

    def _check_measurement_available(self) -> None:
        """Check that the instrument is open and a measurement is available.

        Raises:
            QMI_InvalidOperationException: If the instrument is not open.
            QMI_UsageException:            If no measurement is available.
        """
        self._check_is_open()
        if not self._data_points:
            raise QMI_UsageException("No measurement available, call perform_measurement first.")

    def _get_data_point_at(self, index: int) -> ParsedDataPoint:
        """Get the data point at the given position of the most recent measurement record.

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        self._check_measurement_available()
        return list(self._data_points.values())[index]

    @rpc_method
    def open(self) -> None:
        """Open the serial connection to the meter."""
        self._check_is_closed()
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the serial connection to the meter and discard the stored measurement."""
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)
        self._data_points = {}
        self._table_headers = None
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read the meter properties and return the instrument identification.

        Returns:
            Identification with the METER_NAME property as model and the FIRMWARE property as version. The meter does
            not report a serial number.
        """
        self._check_is_open()
        properties = self.get_properties()
        return QMI_InstrumentIdentification(
            vendor="AlphaLab",
            model=properties.get("METER_NAME"),
            serial=None,
            version=properties.get("FIRMWARE"),
        )

    @rpc_method
    def get_properties(self) -> dict[str, str]:
        """Read the static meter properties (ID_METER_PROP command).

        Returns:
            Dictionary of property names and values, e.g. "METER_NAME", "FIRMWARE" and "TABLE_HEADERS". Tags without a
            value, such as "NO_SETTINGS", have an empty string as value.
        """
        self._check_is_open()
        self._send_command(self.IDN)
        return self._parse_key_value_message(self._get_data_until_trm())

    @rpc_method
    def get_settings(self) -> dict[str, str]:
        """Read the user-selectable meter settings (ID_METER_SETT command).

        Returns:
            Dictionary of setting names and values, e.g. "CURR_FREQ".
        """
        self._check_is_open()
        # The protocol document is ambiguous on whether one or six ACK bytes request the next chunk here; sending six
        # bytes, as for ID_METER_PROP, works.
        self._send_command(self.GET_SET)
        return self._parse_key_value_message(self._get_data_until_trm())

    @rpc_method
    def perform_measurement(self) -> None:
        """Request a single measurement record from the meter and store it.

        A record consists of five data points: time, the field along the x, y and z axes, and the field magnitude. Use
        the `get_*` methods to retrieve the values. The data points are labelled according to `DATA_LABELS`, see
        the class description. The previously stored record is discarded, also when the measurement fails.

        Raises:
            QMI_InstrumentException: If the meter sent an invalid record, or an empty data label cannot be resolved.
            QMI_TimeoutException:    If the meter did not respond in time.
            QMI_UsageException:      If the resolved data labels are not unique.
        """
        self._check_is_open()
        self._data_points = {}
        # Resolve the labels first, as this may require a separate query to the meter.
        labels = self._resolve_data_labels()
        raw_response = self._get_stream_data()

        data_points: dict[str, ParsedDataPoint] = {}
        for index, label in enumerate(labels):
            offset = index * self.DATA_POINT_SIZE
            data_point = self._parse_data_point(raw_response[offset : offset + self.DATA_POINT_SIZE])
            data_point.label = label
            data_points[label] = data_point

        if any(data_point.check_settings_flag for data_point in data_points.values()):
            _logger.warning("[%s] Meter settings were changed at the meter", self._name)
            # The table headers may have changed with the settings, so read them again when they are needed.
            self._table_headers = None

        self._data_points = data_points

    @rpc_method
    def get_data_points(self) -> dict[str, ParsedDataPoint]:
        """Get all data points of the most recent measurement.

        Returns:
            Dictionary mapping each (resolved) data label to its data point, in record order.

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        self._check_measurement_available()
        return dict(self._data_points)

    @rpc_method
    def get_data_point(self, label: str) -> ParsedDataPoint:
        """Get the data point with the given label from the most recent measurement.

        Parameters:
            label: Label of the data point, i.e. an entry of `DATA_LABELS` or, for an empty entry, the corresponding
                   TABLE_HEADERS entry, as used during the most recent measurement.

        Returns:
            The data point with the given label.

        Raises:
            QMI_UsageException: If no measurement is available, or no data point has the given label.
        """
        self._check_measurement_available()
        try:
            return self._data_points[label]
        except KeyError:
            raise QMI_UsageException(
                f"No data point with label {label!r}, available labels: {list(self._data_points)}"
            ) from None

    # Convenience methods, selecting the data point by its position in the record.

    @rpc_method
    def get_time(self) -> float:
        """Get the time data point from the most recent measurement.

        Returns:
            The time, or the sample number, depending on the meter; see the TABLE_HEADERS meter property.

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        return self._get_data_point_at(self._TIME_INDEX).calculate_value()

    @rpc_method
    def get_x_field(self) -> float:
        """Get the field along the x axis from the most recent measurement.

        Returns:
            The field value, or NaN if the meter flagged the value as null (e.g. when measuring in one-axis mode).

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        return self._get_data_point_at(self._X_INDEX).calculate_value()

    @rpc_method
    def get_y_field(self) -> float:
        """Get the field along the y axis from the most recent measurement.

        Returns:
            The field value, or NaN if the meter flagged the value as null (e.g. when measuring in one-axis mode).

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        return self._get_data_point_at(self._Y_INDEX).calculate_value()

    @rpc_method
    def get_z_field(self) -> float:
        """Get the field along the z axis from the most recent measurement.

        Returns:
            The field value, or NaN if the meter flagged the value as null (e.g. when measuring in one-axis mode).

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        return self._get_data_point_at(self._Z_INDEX).calculate_value()

    @rpc_method
    def get_magnitude_field(self) -> float:
        """Get the magnitude of the field from the most recent measurement.

        Returns:
            The field magnitude, or NaN if the meter flagged the value as null.

        Raises:
            QMI_UsageException: If no measurement is available.
        """
        return self._get_data_point_at(self._MAGNITUDE_INDEX).calculate_value()
