import unittest
from unittest.mock import call, patch
import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.siglent import Siglent_Ssa3000x


class TestSSA3000X(unittest.TestCase):

    def setUp(self):
        # Add patches
        patcher = patch('qmi.instruments.siglent.ssa3000x.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.siglent.ssa3000x.ScpiProtocol', autospec=True)
        self._scpi_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.instr = Siglent_Ssa3000x(QMI_Context("test_siglent"), name="siglent", transport_descr="")
        self.instr._TIMEOUT = 0.01  # Make testing faster
        self.instr.open()

    def tearDown(self):
        self.instr.close()

    def test_channel_exception(self):
        with self.assertRaises(QMI_UsageException):
            _ = self.instr.get_spectrum(0)
        with self.assertRaises(QMI_UsageException):
            _ = self.instr.get_spectrum(5)

    def test_get_id(self):
        """ Test case for `get_id(...)` function. """
        # arrange
        expected_id_string = "test_string"
        self._scpi_mock.ask.return_value = expected_id_string
        # act
        actual_val = self.instr.get_id()
        # assert
        self._scpi_mock.ask.assert_called_once_with("*IDN?", discard=True)
        self.assertEqual(actual_val, expected_id_string)

    def test_nullbyte(self):
        """ Test case for discarding null byte. """
        # arrange
        expected_id_string = "test_string"
        self._scpi_mock.ask.return_value = "\0" + expected_id_string
        # act
        actual_val = self.instr.get_id()
        # assert
        self._scpi_mock.ask.assert_called_once_with("*IDN?", discard=True)
        self.assertEqual(actual_val, expected_id_string)

    def test_get_freq_span(self):
        expected = 0.1
        self._scpi_mock.ask.return_value = str(expected)
        # act
        actual = self.instr.get_freq_span()
        # assert
        self._scpi_mock.ask.assert_called_once_with(":FREQ:SPAN?", discard=True)
        self.assertEqual(actual, expected)

    def test_get_freq_span_invalid(self):
        self._scpi_mock.ask.return_value = "unfloatable_string"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_freq_span()

    def test_set_freq_span(self):
        self.instr.set_freq_span(0)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:SPAN 0.000000000 GHz")  # assert

        self.instr.set_freq_span(100)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:SPAN 0.000000100 GHz")  # assert

        self.instr.set_freq_span(3.2e9)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:SPAN 3.200000000 GHz")  # assert

    def test_set_freq_span_invalid(self):
        with self.assertRaises(ValueError):
            self.instr.set_freq_span(50)

    def test_get_freq_center(self):
        expected = 10
        self._scpi_mock.ask.return_value = str(expected)
        # act
        actual = self.instr.get_freq_center()
        # assert
        self._scpi_mock.ask.assert_called_once_with(":FREQ:CENT?", discard=True)
        self.assertEqual(actual, expected)

    def test_get_freq_center_invalid(self):
        self._scpi_mock.ask.return_value = "unfloatable_string"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_freq_center()

    def test_set_freq_center_with_zero_span(self):
        self._scpi_mock.ask.return_value = str(0)  # assume asking for span

        self.instr.set_freq_center(0)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:CENT 0.000000000 GHz")  # assert

        self.instr.set_freq_center(3.2e9)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:CENT 3.200000000 GHz")  # assert

    def test_set_freq_center(self):
        self._scpi_mock.ask.return_value = str(100)  # assume asking for span

        self.instr.set_freq_center(50)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:CENT 0.000000050 GHz")  # assert

        self.instr.set_freq_center(3.199999950e9)  # act
        self._scpi_mock.write.assert_called_with(":FREQ:CENT 3.199999950 GHz")  # assert

        with self.assertRaises(ValueError):
            self.instr.set_freq_center(0)

        with self.assertRaises(ValueError):
            self.instr.set_freq_center(3.2e9)

    def test_get_freq_start(self):
        expected = 0.1
        self._scpi_mock.ask.return_value = str(expected)
        # act
        actual = self.instr.get_freq_start()
        # assert
        self._scpi_mock.ask.assert_called_once_with(":FREQ:STAR?", discard=True)
        self.assertEqual(actual, expected)

    def test_get_freq_start_invalid(self):
        self._scpi_mock.ask.return_value = "unfloatable_string"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_freq_start()

    def test_get_freq_stop(self):
        expected = 0.1
        self._scpi_mock.ask.return_value = str(expected)
        # act
        actual = self.instr.get_freq_stop()
        # assert
        self._scpi_mock.ask.assert_called_once_with(":FREQ:STOP?", discard=True)
        self.assertEqual(actual, expected)

    def test_get_freq_stop_invalid(self):
        self._scpi_mock.ask.return_value = "unfloatable_string"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_freq_stop()

    def test_get_trace_format(self):
        valid_formats = ["ASCii", "REAL"]
        for expected in valid_formats:
            with self.subTest(i=expected):
                # arrange
                self._scpi_mock.reset_mock()
                self._scpi_mock.ask.return_value = expected
                # act
                actual = self.instr.get_trace_format()
                # assert
                self._scpi_mock.ask.assert_called_once_with(":FORM?", discard=True)
                self.assertEqual(actual, expected)

    def test_get_trace(self):
        expected = [0.1, 0.2, 0.3]
        self._scpi_mock.ask.side_effect = ["ASCii", ",".join([str(val) for val in expected])+","]
        # act
        actual = self.instr.get_trace(1)
        # assert
        self._scpi_mock.ask.assert_has_calls([call(":TRAC:DATA? 1", discard=True)])
        self.assertListEqual(actual, expected)

    def test_get_trace_wrong_format(self):
        self._scpi_mock.ask.return_value = "REAL"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_trace(1)

    def test_get_trace_wrong_data(self):
        self._scpi_mock.ask.side_effect = ["ASCii", "not_floatable_string,"]
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_trace(1)

    def test_get_spectrum(self):
        expected = (np.array([1, 2, 3]), np.array([0.1, 0.2, 0.3]))
        self._scpi_mock.ask.side_effect = [
            str(expected[0][0]),
            str(expected[0][-1]),
            "ASCii",
            ",".join([str(val) for val in list(expected[1])])+","
        ]
        # act
        actual = self.instr.get_spectrum(1)
        # assert
        self.assertListEqual(list(actual[0]), list(expected[0]))
        self.assertListEqual(list(actual[1]), list(expected[1]))

    def test_get_spectrum_wrong_freq(self):
        self._scpi_mock.ask.side_effect = [
            "1.0",  # start
            "0.0",  # stop
            "ASCii",  # format
            "0.1,"  # trace data
        ]
        # act
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_spectrum(1)

    def test_get_spectrum_wrong_trace(self):
        self._scpi_mock.ask.side_effect = [
            "0.0",  # start
            "1.0",  # stop
            "ASCii",  # format
            ""  # trace data
        ]
        # act
        with self.assertRaises(QMI_InstrumentException):
            _ = self.instr.get_spectrum(1)
