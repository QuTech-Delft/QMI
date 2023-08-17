"""Test for the Bristol 871A driver."""
import struct
import logging

from math import isnan

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast

from dataclasses import dataclass


from qmi.core.transport import QMI_Transport
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.instruments.bristol.bristol_871a import Bristol_871A
from qmi.instruments.bristol.bristol_871a import _ReaderThread
from qmi.instruments.bristol.bristol_871a import Measurement
from qmi.core.exceptions import QMI_InstrumentException


# Disable all logging
logging.disable(logging.CRITICAL)


@dataclass
class TestMetaReaderThread:
    """Test meta data."""

    transport: MagicMock
    super: MagicMock
    queue: MagicMock()
    reader: _ReaderThread


@dataclass
class TestMeta871a:
    """Test meta data."""

    serial: MagicMock
    serial_str: MagicMock
    scpi_transport: MagicMock
    scpi_protocol: MagicMock
    scpi_str: MagicMock
    name: MagicMock
    super: MagicMock
    reader: MagicMock
    queue: MagicMock()
    instr: Bristol_871A


class TestReaderThread(TestCase):
    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_super = MagicMock()
        mock_queue = MagicMock()

        reader = _ReaderThread(mock_transport, mock_queue)

        self._patcher_super = patch(
            "qmi.instruments.bristol.bristol_871a.super", mock_super
        )
        self._patcher_super.start()

        self.meta = TestMetaReaderThread(
            transport=mock_transport,
            super=mock_super,
            queue=mock_queue,
            reader=reader,
        )

    def tearDown(self):
        self.meta = None
        self._patcher_super.stop()

    def test_init(self):
        """_ReaderThread.__init__(), happy flow"""
        self.assertEqual(self.meta.reader._transport, self.meta.transport)
        self.assertEqual(self.meta.reader._queue, self.meta.queue)

    class TestException(Exception):
        pass

    def test_run(self):
        """_ReaderThread.run(), happy flow."""
        # using TestException to exit the while loop.
        mock_measurement = MagicMock()

        self.meta.queue.append = MagicMock(side_effect=self.TestException)
        self.meta.reader._read_measurement = MagicMock(side_effect=[None, mock_measurement])
        with self.assertRaises(self.TestException):
            self.meta.reader.run()

        self.meta.reader._read_measurement.assert_called_with()
        self.meta.queue.append.assert_called_once_with(mock_measurement)

    def test_read_measurement(self):
        """_ReaderThread._read_measurement(), happy flow."""
        mock_wavelength = 0.0
        mock_power = 1.001
        mock_status = 5
        mock_index = 6

        mock_data_0 = b"\x00"
        mock_data_1 = b"\x7e"
        mock_data_2 = struct.pack(
            "<dfII",
            mock_wavelength,
            mock_power,
            mock_status,
            mock_index,
        )
        mock_data_3 = b"0x7d"
        mock_time = MagicMock()
        self.meta.transport.read_until_timeout = MagicMock(
            side_effect=[mock_data_0, mock_data_1, mock_data_2, mock_data_3]
        )

        with patch("qmi.instruments.bristol.bristol_871a.time.time", mock_time):
            rt_val = self.meta.reader._read_measurement()

        self.assertEqual(rt_val.timestamp, mock_time())
        self.assertTrue(isnan(rt_val.wavelength))
        self.assertAlmostEqual(rt_val.power, mock_power, 3)
        self.assertEqual(rt_val.status, mock_status)
        self.assertEqual(rt_val.index, mock_index)

    def test_read_measurement_corrupt(self):
        """_ReaderThread._read_measurement(), data corrupt."""
        # corruption occurs due to a second start token within a message.
        # the driver should clear the buffer and parse the new message.
        mock_wavelength = 0.0
        mock_power = 1.001
        mock_status = 5
        mock_index = 6

        mock_data_1 = b"\x7e"
        mock_data_2 = b"\x7e"
        mock_data_3 = struct.pack(
            "<dfII",
            mock_wavelength,
            mock_power,
            mock_status,
            mock_index,
        )
        mock_data_4 = b"0x7d"

        mock_time = MagicMock()
        self.meta.transport.read_until_timeout = MagicMock(
            side_effect=[mock_data_1, mock_data_2, mock_data_3, mock_data_4]
        )

        with patch("qmi.instruments.bristol.bristol_871a.time.time", mock_time):
            rt_val = self.meta.reader._read_measurement()

        self.assertEqual(rt_val.timestamp, mock_time())
        self.assertTrue(isnan(rt_val.wavelength))
        self.assertAlmostEqual(rt_val.power, mock_power, 3)
        self.assertEqual(rt_val.status, mock_status)
        self.assertEqual(rt_val.index, mock_index)

    def test_read_measurement_shutdown_requested(self):
        """See that the function returns early if shutdown requested."""
        with patch("qmi.instruments.bristol.bristol_871a.time.time", MagicMock()):
            self.meta.reader._shutdown_requested = True
            rt_val = self.meta.reader._read_measurement()

        self.assertIsNone(rt_val)


class TestBristol_871A(TestCase):
    """Testcase for the Bristol_871A class."""

    def setUp(self):
        mock_transport_serial = MagicMock(spec=QMI_Transport)
        mock_transport_serial_str = MagicMock()
        mock_transport_scpi = MagicMock(spec=QMI_Transport)
        mock_transport_scpi_str = MagicMock()
        mock_name = MagicMock()
        mock_scpi = MagicMock(spec=ScpiProtocol)
        mock_super = MagicMock()
        mock_reader = MagicMock(spec=_ReaderThread)
        mock_queue = MagicMock()

        def se_create_transport(transport):
            if transport == mock_transport_scpi_str:
                return mock_transport_scpi
            elif transport == mock_transport_serial_str:
                return mock_transport_serial

        with patch(
            "qmi.instruments.bristol.bristol_871a.create_transport",
            side_effect=se_create_transport,
        ), patch("qmi.instruments.bristol.bristol_871a.ScpiProtocol", mock_scpi), patch(
            "qmi.instruments.bristol.bristol_871a._ReaderThread", mock_reader
        ), patch(
            "qmi.instruments.bristol.bristol_871a.collections.deque", mock_queue
        ):
            instr = Bristol_871A(
                MagicMock(),
                mock_name,
                mock_transport_scpi_str,
                mock_transport_serial_str,
            )

        self._patcher_super = patch(
            "qmi.instruments.bristol.bristol_871a.super", mock_super
        )
        self._patcher_super.start()

        self.meta = TestMeta871a(
            serial=mock_transport_serial,
            scpi_protocol=mock_scpi,
            scpi_transport=mock_transport_scpi,
            serial_str=mock_transport_serial_str,
            scpi_str=mock_transport_scpi_str,
            name=mock_name,
            super=mock_super,
            reader=mock_reader,
            queue=mock_queue,
            instr=cast(Bristol_871A, instr),
        )

    def tearDown(self):
        self.meta = None
        self._patcher_super.stop()

    def test_init(self):
        """Bristol_871A.__init__(), happy flow"""
        self.meta.queue.assert_called_once_with(
            maxlen=self.meta.instr.DEFAULT_QUEUE_SIZE
        )
        self.assertEqual(self.meta.instr._serial_transport, self.meta.serial)
        self.meta.scpi_protocol.assert_called_once_with(self.meta.scpi_transport)
        self.assertEqual(self.meta.instr._scpi_protocol, self.meta.scpi_protocol())
        self.meta.reader.assert_called_once_with(self.meta.serial, self.meta.queue())
        self.meta.reader().start.assert_called_once_with()

    def test_init_value_error(self):
        """Bristol_871A.__init__(), value error handling"""
        with self.assertRaises(ValueError):
            Bristol_871A(
                object(),
                "fouteboel",
                None,
                None,
            )

    def test_open(self):
        """Bristol_871A.open(), happy flow."""
        self.meta.instr._scpi_handshake = MagicMock()

        self.meta.instr.open()
        self.meta.scpi_transport.open.assert_called_once_with()
        self.meta.serial.open.assert_called_once_with()
        self.meta.super().open.assert_called_once_with()
        self.meta.instr._scpi_handshake.assert_called_once_with()

    def test_open_scpi_handshake_exception(self):
        """Bristol_871A.open(), scpi handshake exception handling."""
        self.meta.instr._scpi_handshake = MagicMock(side_effect=Exception)
        with self.assertRaises(Exception):
            self.meta.instr.open()
        self.meta.scpi_transport.close.assert_called_once_with()

    def test_close(self):
        """Bristol_871A.close(), happy flow."""
        self.meta.instr._check_is_open = MagicMock()

        self.meta.instr.close()
        self.meta.instr._check_is_open.assert_called_once_with()
        self.meta.reader().shutdown.assert_called_once_with()
        self.meta.reader().join.assert_called_once_with()
        self.meta.super().close.assert_called_once_with()
        self.meta.serial.close.assert_called_once_with()
        self.meta.scpi_transport.close.assert_called_once_with()

    def test_write_scpi(self):
        """Bristol_871A._write_scpi(), happy flow."""
        mock_cmd = MagicMock()
        self.meta.instr._write_scpi(mock_cmd)
        self.meta.scpi_protocol().write.assert_called_once_with(mock_cmd)

    def test_ask_scpi(self):
        """Bristol_871A._ask_scpi(), happy flow."""
        mock_cmd = MagicMock()
        rt_val = self.meta.instr._ask_scpi(mock_cmd)
        self.meta.scpi_protocol().ask.assert_called_once_with(mock_cmd)
        self.assertEqual(rt_val, self.meta.scpi_protocol().ask().rstrip("\r\n"))

    def test_reset(self):
        """Bristol_871A.reset(), happy flow."""
        self.meta.instr._write_scpi = MagicMock()
        self.meta.instr.reset()
        self.meta.instr._write_scpi.assert_called_once_with("*RST")

    def test_get_idn(self):
        """Bristol_871A.get_idn(), happy flow."""
        mock_resp = "VENDOR,MODEL,SERIAL,VERSION"

        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)

        rt_val = self.meta.instr.get_idn()
        self.assertEqual(rt_val.vendor, "VENDOR")
        self.assertEqual(rt_val.model, "MODEL")
        self.assertEqual(rt_val.serial, "SERIAL")
        self.assertEqual(rt_val.version, "VERSION")

    def test_get_idn_invalid_response(self):
        """Bristol_871A.get_idn(), invalid response handling."""
        mock_resp = ""
        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self.meta.instr.get_idn()

    def test_scpi_handshake(self):
        """Bristol_871A.scpi_handshake(), happy flow."""
        mock_resp_1 = b"Bristol Instruments"
        mock_resp_2 = b"BRISTOL"

        self.meta.scpi_transport.read_until = MagicMock(
            side_effect=[mock_resp_1, mock_resp_2]
        )
        self.meta.instr._write_scpi = MagicMock()

        self.meta.instr._scpi_handshake()

        self.meta.scpi_transport.read_until.assert_has_calls(
            [
                call(
                    message_terminator=b"\n", timeout=self.meta.instr.RESPONSE_TIMEOUT
                ),
                call(
                    message_terminator=b"\n", timeout=self.meta.instr.RESPONSE_TIMEOUT
                ),
            ]
        )
        self.meta.instr._write_scpi.assert_called_once_with("*IDN?")

    def test_scpi_handshake_no_connection(self):
        """Bristol_871A.scpi_handshake(), no connection handling."""
        mock_resp = b"no connections available"

        self.meta.scpi_transport.read_until = MagicMock(return_value=mock_resp)

        with self.assertRaises(QMI_InstrumentException):
            self.meta.instr._scpi_handshake()

        self.meta.scpi_transport.read_until.assert_has_calls(
            [
                call(
                    message_terminator=b"\n", timeout=self.meta.instr.RESPONSE_TIMEOUT
                ),
            ]
        )

    def test_scpi_handshake_invalid_response(self):
        """Bristol_871A.scpi_handshake(), invalid response handling."""
        mock_resp_1 = b"Bristol Instruments"
        mock_resp_2 = b"*IDN?"

        self.meta.scpi_transport.read_until = MagicMock(
            side_effect=[mock_resp_1, mock_resp_2]
        )
        self.meta.instr._write_scpi = MagicMock()

        with self.assertRaises(QMI_InstrumentException):
            self.meta.instr._scpi_handshake()

        self.meta.scpi_transport.read_until.assert_has_calls(
            [
                call(
                    message_terminator=b"\n", timeout=self.meta.instr.RESPONSE_TIMEOUT
                ),
                call(
                    message_terminator=b"\n", timeout=self.meta.instr.RESPONSE_TIMEOUT
                ),
            ]
        )
        self.meta.instr._write_scpi.assert_called_once_with("*IDN?")

    def test_parse_int(self):
        """Bristol_871A._parse_int(), happy flow."""
        mock_resp = MagicMock()
        mock_cmd = MagicMock()
        rt_val = self.meta.instr._parse_int(mock_resp, mock_cmd)
        self.assertEqual(rt_val, int(mock_resp))

    def test_parse_int_invalid_response(self):
        """Bristol_871A._parse_int(), invalid response handling."""
        mock_resp = "INVALID"
        mock_cmd = MagicMock()
        with self.assertRaises(QMI_InstrumentException):
            self.meta.instr._parse_int(mock_resp, mock_cmd)

    def _test_is_valid_measurement(self, status, wavelength, is_valid):
        mock_value = Measurement(
            status=status, wavelength=wavelength, timestamp=0, index=0, power=0
        )
        rt_val = self.meta.instr.is_valid_measurement(mock_value)
        self.assertEqual(rt_val, is_valid)

    def test_is_valid_measurement(self):
        """Bristol_871A.is_valid_measurement(), happy flow."""
        self._test_is_valid_measurement(0x4, 1, True)
        self._test_is_valid_measurement(0x4, 0, False)
        self._test_is_valid_measurement(0x0, 1, False)

    def test_read_measurement(self):
        """Bristol_871A.read_measurement(), happy flow."""
        mock_wavelength = 0.0
        mock_power = 1.001
        mock_status = 5
        mock_index = 6
        mock_resp = f"{mock_index},{mock_status},{mock_wavelength},{mock_power}"
        mock_time = MagicMock()
        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)

        with patch("qmi.instruments.bristol.bristol_871a.time.time", mock_time):
            rt_val = self.meta.instr.read_measurement()

        self.assertEqual(rt_val.timestamp, mock_time())
        self.assertEqual(rt_val.index, mock_index)
        self.assertEqual(rt_val.status, mock_status)
        self.assertTrue(isnan(rt_val.wavelength))
        self.assertEqual(rt_val.power, mock_power)

        self.meta.instr._ask_scpi.assert_called_once_with(":READ:ALL?")

    def test_read_measurement_invalid_response(self):
        """Bristol_871A.read_measurement(), invalid response handling."""
        mock_resp = ""
        mock_time = MagicMock()
        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)

        with patch("qmi.instruments.bristol.bristol_871a.time.time", mock_time):
            with self.assertRaises(QMI_InstrumentException):
                self.meta.instr.read_measurement()

        self.meta.instr._ask_scpi.assert_called_once_with(":READ:ALL?")

    def test_read_measurement_value_error(self):
        """Bristol_871A.read_measurement(), value error handling."""
        mock_resp = "INVALID,INVALID,INVALID,INVALID"
        mock_time = MagicMock()
        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)

        with patch("qmi.instruments.bristol.bristol_871a.time.time", mock_time):
            with self.assertRaises(QMI_InstrumentException):
                self.meta.instr.read_measurement()

        self.meta.instr._ask_scpi.assert_called_once_with(":READ:ALL?")

    def test_calibrate(self):
        """Bristol_871A.calibrate(), happy flow."""
        self.meta.instr._write_scpi = MagicMock()
        with patch("qmi.instruments.bristol.bristol_871a.time.sleep", MagicMock()):
            self.meta.instr.calibrate()
        self.meta.instr._write_scpi.assert_called_once_with(":SENS:CALI")

    def _test_get_generic(self, function_name, cmd):
        mock_resp = MagicMock()
        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)
        rt_val = getattr(self.meta.instr, function_name)()
        self.assertEqual(rt_val, mock_resp)
        self.meta.instr._ask_scpi.assert_called_once_with(cmd)

    def test_get_auto_calibration_method(self):
        """Bristol_871A.get_auto_calibration_method(), happy flow."""
        self._test_get_generic("get_auto_calibration_method", ":SENS:CALI:METH?")

    def test_get_trigger_method(self):
        """Bristol_871A.get_trigger_method(), happy flow."""
        self._test_get_generic("get_trigger_method", ":TRIG:SEQ:METH?")

    def _test_get_int(self, function_name, cmd):
        mock_resp = MagicMock()
        mock_int = MagicMock()
        self.meta.instr._ask_scpi = MagicMock(return_value=mock_resp)
        self.meta.instr._parse_int = MagicMock(return_value=mock_int)
        rt_val = getattr(self.meta.instr, function_name)()
        self.assertEqual(rt_val, mock_int)
        self.meta.instr._ask_scpi.assert_called_once_with(cmd)
        self.meta.instr._parse_int.assert_called_once_with(mock_resp, cmd)

    def test_get_auto_calibration_temperature(self):
        """Bristol_871A.get_auto_calibration_temperature(), happy flow."""
        self._test_get_int("get_auto_calibration_temperature", ":SENS:CALI:TEMP?")

    def test_get_auto_calibration_time(self):
        """Bristol_871A.get_auto_calibration_time(), happy flow."""
        self._test_get_int("get_auto_calibration_time", ":SENS:CALI:TIM?")

    def test_get_condition(self):
        """Bristol_871A.get_condition(), happy flow."""
        self._test_get_int("get_condition", ":STAT:QUES:COND?")

    def test_get_trigger_rate(self):
        """Bristol_871A.get_trigger_rate(), happy flow."""
        self._test_get_int("get_trigger_rate", ":TRIG:SEQ:RATE:ADJ?")

    def _test_set_str(self, function_name, cmd, value):
        self.meta.instr._write_scpi = MagicMock()
        getattr(self.meta.instr, function_name)(value)
        self.meta.instr._write_scpi.assert_called_once_with(cmd % value.upper())

    def test_set_auto_calibration_method(self):
        """Bristol_871A.set_auto_calibration_method(), happy flow."""
        self._test_set_str("set_auto_calibration_method", ":SENS:CALI:METH %s", "OFF")
        self._test_set_str("set_auto_calibration_method", ":SENS:CALI:METH %s", "TIME")
        self._test_set_str("set_auto_calibration_method", ":SENS:CALI:METH %s", "TEMP")

    def test_set_trigger_method(self):
        """Bristol_871A.set_trigger_method(), happy flow."""
        self._test_set_str("set_trigger_method", ":TRIG:SEQ:METH %s", "INT")
        self._test_set_str("set_trigger_method", ":TRIG:SEQ:METH %s", "FALL")
        self._test_set_str("set_trigger_method", ":TRIG:SEQ:METH %s", "RISE")

    def test_set_auto_calibration_method_value_error(self):
        """Bristol_871A.set_auto_calibration_method(), value error handling."""
        with self.assertRaises(ValueError):
            self._test_set_str("set_auto_calibration_method", ":SENS:CALI:METH %s", "")

    def test_set_trigger_method_value_error(self):
        """Bristol_871A.set_trigger_method(), value error handling."""
        with self.assertRaises(ValueError):
            self._test_set_str("set_trigger_method", ":TRIG:SEQ:METH %s", "")

    def _test_set_int(self, function_name, cmd, value):
        self.meta.instr._write_scpi = MagicMock()
        getattr(self.meta.instr, function_name)(value)
        try:
            self.meta.instr._write_scpi.assert_called_once_with(cmd % value)
        except TypeError:
            self.meta.instr._write_scpi.assert_called_once_with(cmd)

    def test_set_auto_calibration_temperature(self):
        """Bristol_871A.set_auto_calibration_temperature(), happy flow."""
        self._test_set_int("set_auto_calibration_temperature", ":SENS:CALI:TEMP %d", 1)
        self._test_set_int("set_auto_calibration_temperature", ":SENS:CALI:TEMP %d", 50)

    def test_set_auto_calibration_time(self):
        """Bristol_871A.set_auto_calibration_time(), happy flow."""
        self._test_set_int("set_auto_calibration_time", ":SENS:CALI:TIM %d", 5)
        self._test_set_int("set_auto_calibration_time", ":SENS:CALI:TIM %d", 1440)

    def test_set_trigger_rate(self):
        """Bristol_871A.set_trigger_rate(), happy flow."""
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE:ADJ", 0)
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", 20)
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", 50)
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", 100)
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", 250)
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", 500)
        self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", 1000)

    def test_set_auto_calibration_temperature_value_error(self):
        """Bristol_871A.set_auto_calibration_temperature(), value error handling."""
        with self.assertRaises(ValueError):
            self._test_set_int(
                "set_auto_calibration_temperature", ":SENS:CALI:TEMP %d", 0
            )

    def test_set_auto_calibration_time_value_error(self):
        """Bristol_871A.set_auto_calibration_time(), value error handling."""
        with self.assertRaises(ValueError):
            self._test_set_int("set_auto_calibration_time", ":SENS:CALI:TIM %d", 0)

    def test_set_trigger_rate_value_error(self):
        """Bristol_871A.set_trigger_rate(), value error handling."""
        with self.assertRaises(ValueError):
            self._test_set_int("set_trigger_rate", ":TRIG:SEQ:RATE %d", -1)

    def test_memory_start(self):
        """Bristol_871A.memory_start(), happy flow."""
        self.meta.instr._write_scpi = MagicMock()
        self.meta.instr.memory_start()
        self.meta.instr._write_scpi.assert_has_calls(
            [
                call(":MMEM:INIT"),
                call(":MMEM:OPEN"),
            ]
        )

    def test_memory_stop(self):
        """Bristol_871A.memory_stop(), happy flow."""
        self.meta.instr._write_scpi = MagicMock()
        self.meta.instr.memory_stop()
        self.meta.instr._write_scpi.assert_called_once_with(
            ":MMEM:CLOSE",
        )

    def test_get_memory_contents(self):
        """Bristol_871A.get_memory_contents(), happy flow."""
        mock_wavelength = 0.0
        mock_power = 1.001
        mock_status = 5
        mock_index = 6
        mock_resp = struct.pack(
            "<dfII", mock_wavelength, mock_power, mock_status, mock_index
        )
        mock_time = MagicMock()
        self.meta.instr._write_scpi = MagicMock()
        self.meta.scpi_protocol().read_binary_data = MagicMock(return_value=mock_resp)

        with patch("qmi.instruments.bristol.bristol_871a.time.time", mock_time):
            rt_val = self.meta.instr.get_memory_contents()

        self.meta.scpi_protocol().read_binary_data.assert_called_once_with()
        self.assertEqual(rt_val[0].timestamp, mock_time())
        self.assertTrue(isnan(rt_val[0].wavelength))
        self.assertAlmostEqual(rt_val[0].power, mock_power, 3)
        self.assertEqual(rt_val[0].status, mock_status)
        self.assertEqual(rt_val[0].index, mock_index)

    def test_get_memory_contents_invalid_response(self):
        """Bristol_871A.get_memory_contents(), invalid response handling."""
        mock_resp = [
            MagicMock()
        ]  # data length should be modules of 20, data length 1 is not and should result in an error.
        self.meta.instr._write_scpi = MagicMock()
        self.meta.scpi_protocol().read_binary_data = MagicMock(return_value=mock_resp)

        with self.assertRaises(QMI_InstrumentException):
            self.meta.instr.get_memory_contents()

    def test_get_streaming_measurements(self):
        """Bristol_871A.get_streaming_measurements(), happy flow."""
        with patch("qmi.instruments.bristol.bristol_871a.len", return_value=1):
            rt_val = self.meta.instr.get_streaming_measurements()
        self.meta.queue().popleft.assert_called_once_with()
        self.assertEqual(rt_val[0], self.meta.queue().popleft())
