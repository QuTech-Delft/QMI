"""Unit-tests for the AlphaLab MR3 instrument driver."""

import logging
import math
import unittest
from unittest.mock import MagicMock, call, patch

from qmi.core.exceptions import (
    QMI_InstrumentException,
    QMI_InvalidOperationException,
    QMI_TimeoutException,
    QMI_UsageException,
)
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.instruments.alphalab.mr3 import AlphaLab_MR3, ParsedDataPoint

from tests.patcher import PatcherQmiContext as QMI_Context

ACK = b"\x08"
TRM = b"\x07"


def make_data_point(
    value: int,
    decimal: int = 0,
    negative: bool = False,
    ignore: bool = False,
    field_type: int = 0,
    settings_changed: bool = False,
) -> bytes:
    """Build a six-byte STREAM_DATA data point."""
    byte_1 = (ignore << 6) | (field_type << 4) | (settings_changed << 1)
    byte_2 = (negative << 3) | decimal
    return bytes([byte_1, byte_2]) + value.to_bytes(4, "big")


def make_chunks(msg: bytes) -> list[bytes]:
    """Split an ASCII message into 20-byte chunks with ACK/TRM terminators, padding the last chunk with spaces."""
    pieces = [msg[i:i + 20] for i in range(0, len(msg), 20)]
    pieces[-1] = pieces[-1].ljust(20, b" ")
    return [piece + (TRM if i == len(pieces) - 1 else ACK) for i, piece in enumerate(pieces)]


class ParsedDataPointTestCase(unittest.TestCase):
    """Tests for the data point decoding and value calculation."""

    def test_parse_all_fields(self):
        """All status bits and the value are decoded from the right bit positions."""
        data_point = AlphaLab_MR3._parse_data_point(bytes([0b01111110, 0b00001101, 0x01, 0x02, 0x03, 0x04]))

        expected = ParsedDataPoint(
            ignore_flag=True,
            field_type=3,
            hide_1=True,
            hide_2=True,
            check_settings_flag=True,
            sign=True,
            decimal=5,
            data_value=0x01020304,
        )
        self.assertEqual(expected, data_point)

    def test_parse_ignores_unused_bits(self):
        """The unused bits do not affect the decoded fields."""
        data_point = AlphaLab_MR3._parse_data_point(bytes([0b10000001, 0b11110000, 0, 0, 0, 7]))

        self.assertEqual(
            ParsedDataPoint(False, 0, False, False, False, False, 0, 7),
            data_point,
        )

    def test_parse_wrong_length_raises(self):
        """A data point that is not six bytes long raises an exception."""
        with self.assertRaises(QMI_InstrumentException):
            AlphaLab_MR3._parse_data_point(b"\x00" * 5)

    def test_calculate_value(self):
        """The value is scaled by the number of decimals and signed by the sign bit."""
        for raw, decimal, negative, expected in [
            (12345, 0, False, 12345.0),
            (12345, 2, False, 123.45),
            (12345, 3, True, -12.345),
            (0xFFFFFFFF, 7, False, 429.4967295),
        ]:
            with self.subTest(raw=raw, decimal=decimal, negative=negative):
                data_point = AlphaLab_MR3._parse_data_point(make_data_point(raw, decimal, negative))
                self.assertAlmostEqual(expected, data_point.calculate_value())

    def test_calculate_value_ignored_is_nan(self):
        """A data point flagged as null yields NaN."""
        data_point = AlphaLab_MR3._parse_data_point(make_data_point(100, ignore=True))
        self.assertTrue(math.isnan(data_point.calculate_value()))


class AlphaLabMR3TestCase(unittest.TestCase):
    """Tests for the instrument driver with a mocked serial transport."""

    def setUp(self) -> None:
        logging.getLogger("qmi.instruments.alphalab.mr3").setLevel(logging.CRITICAL)
        patcher = patch("qmi.instruments.alphalab.mr3.create_transport")
        self.create_transport = patcher.start()
        self.addCleanup(patcher.stop)
        self.transport = MagicMock()
        self.create_transport.return_value = self.transport

        self.instr = AlphaLab_MR3(QMI_Context("test_alphalab_mr3"), "mr3", "serial:COM1")
        self.instr.open()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()

    def _set_stream_response(self, *data_points: bytes, terminator: bytes = ACK) -> None:
        self.transport.read.return_value = b"".join(data_points) + terminator

    def test_init_transport(self):
        """The transport is created with the serial settings the meter requires."""
        self.create_transport.assert_called_once_with(
            "serial:COM1", default_attributes={"baudrate": 115200, "timeout": 2.0}
        )

    def test_open_close(self):
        """Opening and closing opens and closes the transport."""
        self.transport.open.assert_called_once_with()
        self.instr.close()
        self.transport.close.assert_called_once_with()
        self.assertFalse(self.instr.is_open())

    def test_open_twice_raises(self):
        """Opening an already open instrument raises an exception."""
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.open()

    def test_methods_require_open(self):
        """Methods that talk to the meter raise an exception when the instrument is closed."""
        self.instr.close()
        for method in (
            self.instr.get_idn,
            self.instr.get_properties,
            self.instr.get_settings,
            self.instr.perform_measurement,
            self.instr.get_x_field,
        ):
            with self.subTest(method=method.__name__):
                with self.assertRaises(QMI_InvalidOperationException):
                    method()

        self.transport.write.assert_not_called()

    def test_get_properties_multiple_chunks(self):
        """A multi-chunk message is acknowledged per chunk, concatenated and parsed."""
        msg = b"METER_NAME=MR3:FIRMWARE=1.23:TABLE_HEADERS=Time,X (mG),Y (mG):NO_SETTINGS:"
        chunks = make_chunks(msg)
        self.assertEqual(4, len(chunks))
        self.transport.read.side_effect = chunks

        properties = self.instr.get_properties()

        self.assertEqual(
            {"METER_NAME": "MR3", "FIRMWARE": "1.23", "TABLE_HEADERS": "Time,X (mG),Y (mG)", "NO_SETTINGS": ""},
            properties,
        )
        self.assertEqual(
            [call(b"\x01" + 5 * b"\xaa")] + 3 * [call(6 * ACK)],
            self.transport.write.call_args_list,
        )
        self.transport.read.assert_called_with(21, timeout=1.0)

    def test_get_idn(self):
        """The identification is built from the METER_NAME and FIRMWARE properties."""
        self.transport.read.side_effect = make_chunks(b"METER_NAME=MR3:FIRMWARE=V2.0:")

        idn = self.instr.get_idn()

        self.assertEqual(QMI_InstrumentIdentification("AlphaLab", "MR3", None, "V2.0"), idn)

    def test_get_idn_missing_properties(self):
        """Missing properties result in None fields in the identification."""
        self.transport.read.side_effect = make_chunks(b"BASE_FREQ=0.25:")

        idn = self.instr.get_idn()

        self.assertEqual(QMI_InstrumentIdentification("AlphaLab", None, None, None), idn)

    def test_get_settings(self):
        """The settings command is sent and the reply is parsed, ignoring the filler bytes after the last colon."""
        self.transport.read.return_value = b"CURR_FREQ=1:REC_CHG:\x00X=?" + TRM

        settings = self.instr.get_settings()

        self.assertEqual({"CURR_FREQ": "1", "REC_CHG": ""}, settings)
        self.transport.write.assert_called_once_with(b"\x02" + 5 * b"\xaa")

    def test_message_unexpected_terminator_raises(self):
        """A chunk ending with a byte other than ACK or TRM raises an exception."""
        self.transport.read.return_value = 20 * b"A" + b"\x00"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_settings()

    def test_message_without_end_raises(self):
        """A message that does not end within the maximum number of chunks raises an exception."""
        self.transport.read.return_value = 20 * b"A" + ACK

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_settings()

        self.assertEqual(AlphaLab_MR3.MAX_CHUNKS, self.transport.read.call_count)

    def test_perform_measurement(self):
        """A measurement record is requested and its values are returned by the getters."""
        self._set_stream_response(
            make_data_point(42),
            make_data_point(1234, decimal=1),
            make_data_point(567, decimal=2, negative=True),
            make_data_point(0),
            make_data_point(1500, decimal=1),
        )

        self.instr.perform_measurement()

        self.transport.write.assert_called_once_with(b"\x03" + 5 * b"\xaa")
        self.transport.read.assert_called_once_with(31, timeout=2.0)
        self.assertAlmostEqual(123.4, self.instr.get_x_field())
        self.assertAlmostEqual(-5.67, self.instr.get_y_field())
        self.assertAlmostEqual(0.0, self.instr.get_z_field())
        self.assertAlmostEqual(150.0, self.instr.get_magnitude_field())

    def test_perform_measurement_terminate_byte(self):
        """A record ending with a TRM byte is accepted."""
        self._set_stream_response(*(5 * [make_data_point(1)]), terminator=TRM)

        self.instr.perform_measurement()

        self.assertEqual(1.0, self.instr.get_x_field())

    def test_perform_measurement_null_axis(self):
        """Axes flagged as null are returned as NaN."""
        self._set_stream_response(
            make_data_point(0),
            make_data_point(10),
            make_data_point(0, ignore=True),
            make_data_point(0, ignore=True),
            make_data_point(10),
        )

        self.instr.perform_measurement()

        self.assertEqual(10.0, self.instr.get_x_field())
        self.assertTrue(math.isnan(self.instr.get_y_field()))
        self.assertTrue(math.isnan(self.instr.get_z_field()))

    def test_perform_measurement_settings_changed_logs_warning(self):
        """A data point with the settings-changed flag logs a warning."""
        self._set_stream_response(make_data_point(0, settings_changed=True), *(4 * [make_data_point(0)]))

        with self.assertLogs("qmi.instruments.alphalab.mr3", logging.WARNING):
            self.instr.perform_measurement()

    def test_perform_measurement_bad_terminator_raises(self):
        """A record not ending with ACK or TRM raises an exception."""
        self._set_stream_response(*(5 * [make_data_point(0)]), terminator=b"\x00")

        with self.assertRaises(QMI_InstrumentException):
            self.instr.perform_measurement()

    def test_failed_measurement_discards_previous(self):
        """A failed measurement discards the previous measurement instead of leaving stale data."""
        self._set_stream_response(*(5 * [make_data_point(1)]))
        self.instr.perform_measurement()
        self.transport.read.side_effect = QMI_TimeoutException("timeout")

        with self.assertRaises(QMI_TimeoutException):
            self.instr.perform_measurement()

        with self.assertRaises(QMI_UsageException):
            self.instr.get_x_field()

    def test_getters_without_measurement_raise(self):
        """The getters raise an exception if no measurement was performed."""
        for getter in (
            self.instr.get_time,
            self.instr.get_x_field,
            self.instr.get_y_field,
            self.instr.get_z_field,
            self.instr.get_magnitude_field,
            self.instr.get_data_points,
        ):
            with self.subTest(getter=getter.__name__):
                with self.assertRaises(QMI_UsageException):
                    getter()

        with self.assertRaises(QMI_UsageException):
            self.instr.get_data_point("x_axis")

    def test_get_time(self):
        """The time is the first data point of the record."""
        self._set_stream_response(make_data_point(1234, decimal=2), *(4 * [make_data_point(0)]))

        self.instr.perform_measurement()

        self.assertAlmostEqual(12.34, self.instr.get_time())

    def test_get_data_points(self):
        """All data points are returned in record order, labelled with the default labels."""
        self._set_stream_response(*(make_data_point(value) for value in range(5)))

        self.instr.perform_measurement()
        data_points = self.instr.get_data_points()

        self.assertEqual(list(AlphaLab_MR3.DATA_LABELS), list(data_points))
        self.assertEqual([0, 1, 2, 3, 4], [data_point.data_value for data_point in data_points.values()])
        self.assertEqual("y_axis", self.instr.get_data_point("y_axis").label)
        self.assertEqual(2.0, self.instr.get_data_point("y_axis").calculate_value())

    def test_get_data_point_unknown_label_raises(self):
        """Requesting a label that is not in the measurement raises an exception."""
        self._set_stream_response(*(5 * [make_data_point(0)]))
        self.instr.perform_measurement()

        with self.assertRaises(QMI_UsageException):
            self.instr.get_data_point("w_axis")


class AlphaLabMR3DataLabelsTestCase(unittest.TestCase):
    """Tests for resolving empty data labels from the TABLE_HEADERS meter property."""

    PROPERTIES = b"METER_NAME=MR3:TABLE_HEADERS=Time (s), X (mG), Y (mG), Z (mG), Mag (mG):"

    def setUp(self) -> None:
        logging.getLogger("qmi.instruments.alphalab.mr3").setLevel(logging.CRITICAL)
        patcher = patch("qmi.instruments.alphalab.mr3.create_transport")
        self.transport = MagicMock()
        patcher.start().return_value = self.transport
        self.addCleanup(patcher.stop)

        self.instr = AlphaLab_MR3(QMI_Context("test_alphalab_mr3_labels"), "mr3", "serial:COM1")
        self.instr.open()
        self.stream_response = b"".join(make_data_point(value) for value in range(5)) + ACK

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()

    def test_default_labels_do_not_query_properties(self):
        """With no empty labels, only the stream command is sent."""
        self.transport.read.side_effect = [self.stream_response]

        self.instr.perform_measurement()

        self.transport.write.assert_called_once_with(b"\x03" + 5 * b"\xaa")

    def test_empty_labels_resolved(self):
        """Empty labels are replaced by the stripped TABLE_HEADERS entries at the same position."""
        self.instr.DATA_LABELS = ("", "x_axis", "", "", "")
        self.transport.read.side_effect = make_chunks(self.PROPERTIES) + [self.stream_response]

        self.instr.perform_measurement()

        self.assertEqual(
            ["Time (s)", "x_axis", "Y (mG)", "Z (mG)", "Mag (mG)"],
            list(self.instr.get_data_points()),
        )
        self.assertEqual("Y (mG)", self.instr.get_data_point("Y (mG)").label)
        self.assertEqual(b"\x01" + 5 * b"\xaa", self.transport.write.call_args_list[0].args[0])
        self.assertEqual(b"\x03" + 5 * b"\xaa", self.transport.write.call_args_list[-1].args[0])
        # The convenience methods select by position, so they work with any labels.
        self.assertEqual(0.0, self.instr.get_time())
        self.assertEqual(1.0, self.instr.get_x_field())
        self.assertEqual(2.0, self.instr.get_y_field())
        self.assertEqual(3.0, self.instr.get_z_field())
        self.assertEqual(4.0, self.instr.get_magnitude_field())

    def test_table_headers_cached(self):
        """The meter properties are read only once for repeated measurements."""
        self.instr.DATA_LABELS = ("", "", "", "", "")
        self.transport.read.side_effect = make_chunks(self.PROPERTIES) + 2 * [self.stream_response]

        self.instr.perform_measurement()
        self.instr.perform_measurement()

        idn_calls = [c for c in self.transport.write.call_args_list if c.args[0][:1] == b"\x01"]
        self.assertEqual(1, len(idn_calls))

    def test_table_headers_reread_after_settings_change(self):
        """The meter properties are read again after the meter reported changed settings."""
        self.instr.DATA_LABELS = ("", "", "", "", "")
        changed_response = make_data_point(0, settings_changed=True) + self.stream_response[6:]
        self.transport.read.side_effect = (
            make_chunks(self.PROPERTIES) + [changed_response] + make_chunks(self.PROPERTIES) + [self.stream_response]
        )

        self.instr.perform_measurement()
        self.instr.perform_measurement()

        idn_calls = [c for c in self.transport.write.call_args_list if c.args[0][:1] == b"\x01"]
        self.assertEqual(2, len(idn_calls))

    def test_table_headers_reread_after_reopen(self):
        """The cached table headers are discarded when the connection is closed."""
        self.instr.DATA_LABELS = ("", "", "", "", "")
        self.transport.read.side_effect = 2 * (make_chunks(self.PROPERTIES) + [self.stream_response])

        self.instr.perform_measurement()
        self.instr.close()
        self.instr.open()
        self.instr.perform_measurement()

        idn_calls = [c for c in self.transport.write.call_args_list if c.args[0][:1] == b"\x01"]
        self.assertEqual(2, len(idn_calls))

    def test_missing_table_header_raises(self):
        """An empty label without a TABLE_HEADERS entry at its position raises an exception."""
        self.instr.DATA_LABELS = ("Time", "x_axis", "y_axis", "z_axis", "")
        self.transport.read.side_effect = make_chunks(b"TABLE_HEADERS=Time,X:")

        with self.assertRaises(QMI_InstrumentException):
            self.instr.perform_measurement()

    def test_missing_table_headers_property_raises(self):
        """An empty label raises an exception if the meter has no TABLE_HEADERS property."""
        self.instr.DATA_LABELS = ("", "x_axis", "y_axis", "z_axis", "Magnitude")
        self.transport.read.side_effect = make_chunks(b"METER_NAME=MR3:")

        with self.assertRaises(QMI_InstrumentException):
            self.instr.perform_measurement()

    def test_duplicate_labels_raise(self):
        """Resolved labels that are not unique raise an exception, before a record is requested."""
        self.instr.DATA_LABELS = ("Time", "X (mG)", "", "z_axis", "Magnitude")
        self.transport.read.side_effect = make_chunks(b"TABLE_HEADERS=Time,X (mG),X (mG),Z,M:")

        with self.assertRaises(QMI_UsageException):
            self.instr.perform_measurement()

        self.assertNotIn(call(b"\x03" + 5 * b"\xaa"), self.transport.write.call_args_list)


if __name__ == "__main__":
    unittest.main()
