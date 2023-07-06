"""Unit tests for Rigol DG4102 QMI driver."""

import unittest
from unittest.mock import MagicMock, call, patch

import logging
from typing import cast

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.rigol import Rigol_Dg4102
from qmi.utils.context_managers import open_close


class SuppressLogging:
    """Context manager to temporarily suppress logging during a test."""

    def __enter__(self):
        # Suppress logging of all levels up to ERROR.
        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)

    def __exit__(self, typ, value, tb):
        # Restore default log levels.
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)


class RigolDg4102TestCase(unittest.TestCase):

    def setUp(self):
        qmi.start("TestContext")
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
                'qmi.instruments.rigol.dg4102.create_transport',
                return_value=self._transport_mock):
            self.instr: Rigol_Dg4102 = qmi.make_instrument("instr", Rigol_Dg4102, "transport_descriptor")
            self.instr = cast(Rigol_Dg4102, self.instr)

    def tearDown(self):
        qmi.stop()

    def test_open_close(self):
        """Test that the open and close functions include calls as expected."""
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.open.reset_mock()
        self._transport_mock.write.reset_mock()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_set_source(self):
        """Test wait and clear function."""
        expected_init_source = 1
        new_source = 2
        with open_close(self.instr):
            source_init = self.instr.get_source()
            self.instr.set_source(2)
            source_new = self.instr.get_source()

        self.assertEqual(expected_init_source, source_init)
        self.assertEqual(new_source, source_new)

    def test_get_idn(self):
        """Test get_idn call"""
        vendor = "Rigol"
        model = "DG41202"
        serial = "S192837465"
        version = "3.2.1"
        ret_val = ",".join([vendor, model, serial, version]) + "\n"
        with open_close(self.instr):
            self._transport_mock.read_until.return_value = ret_val.encode("ascii")
            idn = self.instr.get_idn()

        self.assertEqual(vendor, idn.vendor)
        self.assertEqual(model, idn.model)
        self.assertEqual(serial, idn.serial)
        self.assertEqual(version, idn.version)

    def test_get_idn_excepts(self):
        """Test get_idn call"""
        vendor = "Rigol"
        model = "DG41202"
        serial = "S192837465"
        ret_val = ",".join([vendor, model, serial]) + "\n"
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException):
            self._transport_mock.read_until.return_value = ret_val.encode("ascii")
            _ = self.instr.get_idn()

    def test_get_output_state(self):
        """Test instrument state query."""
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"1\n", b"\n"]
            state_1 = self.instr.get_output_state()

        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n", b"\n"]
            state_0 = self.instr.get_output_state()

        self.assertTrue(state_1)
        self.assertFalse(state_0)

    def test_get_output_state_raises_exception(self):
        """Test instrument state query raises exception at non-bool response"""
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException):
            self._transport_mock.read_until.side_effect = [b"true\n"]
            self.instr.get_output_state()

    def test_set_output_state(self):
        """Test setting clock to 'internal' mode."""
        expected_call = [call(b":OUTP1 ON\n")]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'0,"No error"\n']  # For _check_error
            self.instr.set_output_state(True)
            self._transport_mock.write.assert_called_with(b"SYSTem:ERRor?\n")
            self._transport_mock.write.assert_has_calls(expected_call)

    def test_get_waveform(self):
        """Test setting a waveform."""
        waveform = b"SINusoid\n"
        expected_call = b":SOURce1:FUNCtion?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [waveform, b'0,"No error"\n']
            response = self.instr.get_waveform()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(response, waveform.decode().strip())

    def test_set_waveform(self):
        """Test setting a waveform."""
        waveform = "SINusoid"
        expected_call = [call(f":SOURce1:FUNCtion {waveform}\n".encode("ascii"))]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'0,"No error"\n']
            self.instr.set_waveform(waveform)
            self._transport_mock.write.assert_called_with(b"SYSTem:ERRor?\n")
            self._transport_mock.write.assert_has_calls(expected_call)

    def test_get_frequency(self):
        """Test getting a frequency."""
        frequency = b"100000.0\n"
        expected_call = b":SOURce1:FREQ?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [frequency]
            response = self.instr.get_frequency()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(response, float(frequency.decode().strip()))

    def test_get_frequency_excepts(self):
        """Test getting a frequency excepts at non-float(ish) response."""
        frequency = b"100000Hz\n"
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException):
            self._transport_mock.read_until.side_effect = [frequency]
            self.instr.get_frequency()

    def test_set_frequency(self):
        """Test setting a frequency."""
        frequency = "100000.0"
        expected_call = [call(f":SOURce1:FREQ {frequency}\n".encode("ascii"))]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'0,"No error"\n']
            self.instr.set_frequency(float(frequency))
            self._transport_mock.write.assert_called_with(b"SYSTem:ERRor?\n")
            self._transport_mock.write.assert_has_calls(expected_call)

    def test_get_amplitude(self):
        """Test setting an amplitude."""
        amplitude = b"100.0\n"
        expected_call = b":SOURce1:VOLT?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [amplitude]
            response = self.instr.get_amplitude()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(response, float(amplitude.decode().strip()))

    def test_set_amplitude(self):
        """Test setting an amplitude."""
        amplitude = "100.0"
        expected_call = [call(f":SOURce1:VOLT {amplitude}\n".encode("ascii"))]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'0,"No error"\n']
            self.instr.set_amplitude(float(amplitude))
            self._transport_mock.write.assert_called_with(b"SYSTem:ERRor?\n")
            self._transport_mock.write.assert_has_calls(expected_call)

    def test_get_offset(self):
        """Test setting an offset."""
        offset = b"-10.0\n"
        expected_call = b":SOURce1:VOLTage:OFFSet?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [offset]
            response = self.instr.get_offset()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(response, float(offset.decode().strip()))

    def test_set_offset(self):
        """Test setting an offset."""
        offset = "-10.0"
        expected_call = [call(f":SOURce1:VOLTage:OFFSet {offset}\n".encode("ascii"))]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'0,"No error"\n']
            self.instr.set_offset(float(offset))
            self._transport_mock.write.assert_called_with(b"SYSTem:ERRor?\n")
            self._transport_mock.write.assert_has_calls(expected_call)

    def test_get_phase(self):
        """Test setting an phase."""
        phase = b"-180.0\n"
        expected_call = b":SOURce1:PHASe?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [phase]
            response = self.instr.get_phase()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(response, float(phase.decode().strip()))

    def test_set_phase(self):
        """Test setting an phase."""
        phase = "-180.0"
        expected_call = [call(f":SOURce1:PHASe {phase}\n".encode("ascii"))]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'0,"No error"\n']
            self.instr.set_phase(float(phase))
            self._transport_mock.write.assert_called_with(b"SYSTem:ERRor?\n")
            self._transport_mock.write.assert_has_calls(expected_call)


if __name__ == '__main__':
    unittest.main()
