"""Unit test for Tektronix AFG31000 driver."""

import math
from typing import cast
import unittest
from unittest.mock import MagicMock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.tektronix import Waveform, BurstMode, TriggerEdge, Tektronix_Afg31000


class TestAFG31000(unittest.TestCase):

    def setUp(self):
        qmi.start("TestContext")
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
                'qmi.instruments.tektronix.afg31000.create_transport',
                return_value=self._transport_mock):
            self.instr: Tektronix_Afg31000 = qmi.make_instrument("instr", Tektronix_Afg31000, "transport_descriptor")
            self.instr = cast(Tektronix_Afg31000, self.instr)

    def tearDown(self):
        qmi.stop()

    def _open_helper(self):
        """Open instrument and check transport calls."""
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.write.assert_called_once_with(b"*CLS\n")
        self._transport_mock.open.reset_mock()
        self._transport_mock.write.reset_mock()

    def _prep_cmd_no_error(self):
        """Prepare transport mock for error check without error."""
        self._transport_mock.read_until.side_effect = [b"1\n", b'0,"No error"\n']

    def _assert_cmd_no_error(self, expect_commands):
        """Assert that the driver sent the specified command."""
        expect_calls = [call(cmd) for cmd in expect_commands]
        expect_calls += [
            call(b"*OPC?\n"),
            call(b"SYST:ERR?\n")
        ]
        self.assertEqual(self._transport_mock.write.mock_calls, expect_calls)

    def _prep_cmd_with_error(self):
        """Prepare transport mock for error check that detects an error."""
        self._transport_mock.read_until.side_effect = [b"1\n", b'-10,"Some error"\n']

    def _assert_cmd_with_error(self, expect_commands):
        """Assert that the driver sent the specified command."""
        expect_calls = [call(cmd) for cmd in expect_commands]
        expect_calls += [
            call(b"*OPC?\n"),
            call(b"SYST:ERR?\n"),
            call(b"*CLS\n")
        ]
        self.assertEqual(self._transport_mock.write.mock_calls, expect_calls)

    def test_open_close(self):
        self._open_helper()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_open_comm_error(self):
        self._transport_mock.write.side_effect = OSError("fake error")
        with self.assertRaises(OSError):
            self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.write.assert_called_once_with(b"*CLS\n")
        self._transport_mock.close.assert_called_once_with()

    def test_get_idn(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"vendor,model,serial,version\n"
        idn = self.instr.get_idn()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"*IDN?\n")
        self.assertEqual(idn.vendor, "vendor")
        self.assertEqual(idn.model, "model")
        self.assertEqual(idn.serial, "serial")
        self.assertEqual(idn.version, "version")

    def test_get_idn_fail(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"nonsense\n"
        with self.assertRaises(QMI_InstrumentException):
            idn = self.instr.get_idn()
        self.instr.close()

    def test_reset(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.reset()
        self.instr.close()
        self._assert_cmd_no_error([b"*CLS\n", b"*RST\n"])

    def test_get_external_reference_enabled(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"INT\n"
        ret = self.instr.get_external_reference_enabled()
        self._transport_mock.write.assert_called_once_with(b"SOURCE:ROSCILLATOR:SOURCE?\n")
        self._transport_mock.write.reset_mock()
        self.assertFalse(ret)

        self._transport_mock.read_until.return_value = b"EXT\n"
        ret = self.instr.get_external_reference_enabled()
        self.instr.close()
        self.assertTrue(ret)

    def test_get_external_reference_enabled_fail(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"ehm\n"
        with self.assertRaises(QMI_InstrumentException):
            ret = self.instr.get_external_reference_enabled()
        self.instr.close()

    def test_set_external_reference_enabled(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_external_reference_enabled(False)
        self._assert_cmd_no_error([b"SOURCE:ROSCILLATOR:SOURCE INT\n"])
        self._transport_mock.write.reset_mock()

        self._prep_cmd_no_error()
        self.instr.set_external_reference_enabled(True)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE:ROSCILLATOR:SOURCE EXT\n"])

    def test_get_output_enabled(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"0\n"
        ret = self.instr.get_output_enabled(1)
        self._transport_mock.write.assert_called_once_with(b"OUTPUT1:STATE?\n")
        self._transport_mock.write.reset_mock()
        self.assertFalse(ret)

        self._transport_mock.read_until.return_value = b"1\n"
        ret = self.instr.get_output_enabled(2)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"OUTPUT2:STATE?\n")
        self.assertTrue(ret)

    def test_get_output_enabled_bad_response(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"ehm\n"
        with self.assertRaises(QMI_InstrumentException):
            ret = self.instr.get_output_enabled(1)
        self.instr.close()

    def test_set_output_enabled(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_output_enabled(1, True)
        self.instr.close()
        self._assert_cmd_no_error([b"OUTPUT1:STATE 1\n"])

    def test_get_waveform(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"SIN\n"
        ret = self.instr.get_waveform(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:FUNCTION:SHAPE?\n")
        self.assertEqual(ret, Waveform.SINE)

    def test_set_waveform(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_waveform(1, Waveform.PULSE)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:FUNCTION:SHAPE PULS\n"])

    def test_get_sweep_enabled(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"CW\n"
        ret = self.instr.get_sweep_enabled(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:FREQUENCY:MODE?\n")
        self.assertFalse(ret)

    def test_get_continuous_frequency(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"1000000\n"
        ret = self.instr.get_continuous_frequency(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:FREQUENCY:CW?\n")
        self.assertEqual(ret, 1.0e6)

    def test_get_continuous_frequency_bad_response(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"big\n"
        with self.assertRaises(QMI_InstrumentException):
            ret = self.instr.get_continuous_frequency(1)
        self.instr.close()

    def test_set_continuous_frequency(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_continuous_frequency(1, 100.0e3)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:FREQUENCY:MODE CW\n",
                                   b"SOURCE1:FREQUENCY:CW 100000.000000\n"])

    def test_get_amplitude(self):
        self._open_helper()
        self._transport_mock.read_until.side_effect = [b"0.5\n", b"3.3\n"]
        ret = self.instr.get_amplitude(1)
        self.instr.close()
        self.assertEqual(self._transport_mock.write.mock_calls, [
            call(b"SOURCE1:VOLTAGE:LEVEL:LOW?\n"),
            call(b"SOURCE1:VOLTAGE:LEVEL:HIGH?\n")
        ])
        self.assertEqual(ret, (0.5, 3.3))

    def test_set_amplitude(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_amplitude(1, 0.0, 5.0)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:VOLTAGE:LEVEL:LOW 0.0000\n",
                                   b"SOURCE1:VOLTAGE:LEVEL:HIGH 5.0000\n"])

    def test_get_pulse_duty_cycle(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"0.15\n"
        ret = self.instr.get_pulse_duty_cycle(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:PULSE:DCYCLE?\n")
        self.assertEqual(ret, 0.15)

    def test_set_pulse_duty_cycle(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_pulse_duty_cycle(1, 0.5)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:PULSE:HOLD DUTY\n",
                                   b"SOURCE1:PULSE:DCYCLE 0.500000\n"])

    def test_get_pulse_delay(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"1E-9\n"
        ret = self.instr.get_pulse_delay(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:PULSE:DELAY?\n")
        self.assertEqual(ret, 1.0e-9)

    def test_set_pulse_delay(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_pulse_delay(1, 0.25e-9)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:PULSE:DELAY 0.00000000025\n"])

    def test_get_burst_mode(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"GAT\n"
        ret = self.instr.get_burst_mode(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:BURST:MODE?\n")
        self.assertEqual(ret, BurstMode.GATED)

    def test_set_burst_mode(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_burst_mode(1, BurstMode.TRIGGERED)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:BURST:MODE TRIG\n"])

    def test_get_burst_count(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"5\n"
        ret = self.instr.get_burst_count(1)
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:BURST:NCYCLES?\n")
        self._transport_mock.write.reset_mock()
        self.assertEqual(ret, 5)

        self._transport_mock.read_until.return_value = b"9.9E+37\n"
        ret = self.instr.get_burst_count(2)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE2:BURST:NCYCLES?\n")
        self.assertEqual(ret, math.inf)

    def test_set_burst_count(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_burst_count(1, 100)
        self._assert_cmd_no_error([b"SOURCE1:BURST:NCYCLES 100\n"])
        self._transport_mock.write.reset_mock()

        self._prep_cmd_no_error()
        self.instr.set_burst_count(1, math.inf)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:BURST:NCYCLES INF\n"])

    def test_get_burst_enabled(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"1\n"
        ret = self.instr.get_burst_enabled(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"SOURCE1:BURST:STATE?\n")
        self.assertTrue(ret)

    def test_set_burst_enabled(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_burst_enabled(1, True)
        self.instr.close()
        self._assert_cmd_no_error([b"SOURCE1:BURST:STATE 1\n"])

    def test_get_external_trigger_enabled(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"EXT\n"
        ret = self.instr.get_external_trigger_enabled()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"TRIGGER:SOURCE?\n")
        self.assertTrue(ret)

    def test_set_external_trigger_enabled(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_external_trigger_enabled(True)
        self.instr.close()
        self._assert_cmd_no_error([b"TRIGGER:SOURCE EXT\n"])

    def test_get_trigger_edge(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"NEG\n"
        ret = self.instr.get_trigger_edge()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"TRIGGER:SLOPE?\n")
        self.assertEqual(ret, TriggerEdge.FALLING)

    def test_set_trigger_edge(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_trigger_edge(TriggerEdge.RISING)
        self.instr.close()
        self._assert_cmd_no_error([b"TRIGGER:SLOPE POS\n"])

    def test_get_output_load_impedance(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"50\n"
        ret = self.instr.get_output_load_impedance(1)
        self._transport_mock.write.assert_called_once_with(b"OUTPUT1:IMPEDANCE?\n")
        self._transport_mock.write.reset_mock()
        self.assertEqual(ret, 50.0)

        self._transport_mock.read_until.return_value = b"9.9E+37\n"
        ret = self.instr.get_output_load_impedance(2)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"OUTPUT2:IMPEDANCE?\n")
        self.assertEqual(ret, math.inf)

    def test_set_output_load_impedance(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_output_load_impedance(1, 10.0e3)
        self._assert_cmd_no_error([b"OUTPUT1:IMPEDANCE 10000.0\n"])
        self._transport_mock.write.reset_mock()

        self._prep_cmd_no_error()
        self.instr.set_output_load_impedance(2, math.inf)
        self.instr.close()
        self._assert_cmd_no_error([b"OUTPUT2:IMPEDANCE INF\n"])

    def test_get_output_inverted(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"INV\n"
        ret = self.instr.get_output_inverted(1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"OUTPUT1:POLARITY?\n")
        self.assertTrue(ret)

    def test_set_output_inverted(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_output_inverted(1, False)
        self.instr.close()
        self._assert_cmd_no_error([b"OUTPUT1:POLARITY NORM\n"])
        self._transport_mock.write.reset_mock()

    def test_set_display_brightness(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_display_brightness(0.25)
        self.instr.close()
        self._assert_cmd_no_error([b"DISPLAY:BRIGHTNESS 0.250\n"])
        self._transport_mock.write.reset_mock()

    def test_command_error(self):
        self._open_helper()
        self._prep_cmd_with_error()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_external_reference_enabled(True)
        self.instr.close()
        self._assert_cmd_with_error([b"SOURCE:ROSCILLATOR:SOURCE EXT\n"])

    def test_bad_channel(self):
        self._open_helper()
        with self.assertRaises(ValueError):
            ret = self.instr.get_output_enabled(0)
        with self.assertRaises(ValueError):
            ret = self.instr.get_output_enabled(3)
        self.instr.close()


if __name__ == '__main__':
    unittest.main()
