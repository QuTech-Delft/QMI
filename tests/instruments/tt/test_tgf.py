"""Unit test for AimTTi TGF3000 and TGF4000 series instrument driver."""

import math
import time
from typing import cast
import unittest
from unittest.mock import MagicMock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.tt import AimTTi_Tgf30004000, WaveformType, CounterInputChannel


class TestTGF(unittest.TestCase):

    def setUp(self):
        qmi.start("Test_tgf_3000_4000")
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
                'qmi.instruments.tt.tgf.create_transport',
                return_value=self._transport_mock):
            self.instr: AimTTi_Tgf30004000 = qmi.make_instrument("instr", AimTTi_Tgf30004000, "transport_descriptor")
            self.instr = cast(AimTTi_Tgf30004000, self.instr)

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
        self._transport_mock.read_until.return_value = b"+0\r\n"
        self._transport_mock.write.reset_mock()

    def _assert_cmds(self, expect_commands):
        """Assert that the driver sent the specified commands."""
        expect_calls = [call(cmd) for cmd in expect_commands]
        expect_calls.append(call(b"EER?\n"))
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
        self._transport_mock.read_until.return_value = b"vendor,model,serial,version\r\n"
        idn = self.instr.get_idn()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"*IDN?\n")
        self.assertEqual(idn.vendor, "vendor")
        self.assertEqual(idn.model, "model")
        self.assertEqual(idn.serial, "serial")
        self.assertEqual(idn.version, "version")

    def test_get_idn_fail(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"nonsense\r\n"
        with self.assertRaises(QMI_InstrumentException):
            idn = self.instr.get_idn()
        self.instr.close()

    def test_reset(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.reset()
        self.instr.close()
        self._assert_cmds([b"*CLS\n", b"*RST\n"])

    def test_set_output_enabled(self):
        self._open_helper()

        self._prep_cmd_no_error()
        self.instr.set_output_enabled(1, True)
        self._assert_cmds([b"CHN 1;OUTPUT ON\n"])

        self._prep_cmd_no_error()
        self.instr.set_output_enabled(2, False)
        self.instr.close()
        self._assert_cmds([b"CHN 2;OUTPUT OFF\n"])

    def test_set_output_enabled_fail(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"-111\r\n"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_enabled(1, True)
        self.instr.close()
        self.assertEqual(self._transport_mock.write.mock_calls, [
            call(b"CHN 1;OUTPUT ON\n"),
            call(b"EER?\n")
        ])

    def test_nonsense_error(self):
        self._open_helper()
        self._transport_mock.read_until.return_value = b"nonsense\r\n"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_enabled(1, True)
        self.instr.close()
        self.assertEqual(self._transport_mock.write.mock_calls, [
            call(b"CHN 1;OUTPUT ON\n"),
            call(b"EER?\n")
        ])

    def test_set_output_inverted(self):
        self._open_helper()

        self._prep_cmd_no_error()
        self.instr.set_output_inverted(1, True)
        self._assert_cmds([b"CHN 1;OUTPUT INVERT\n"])

        self._prep_cmd_no_error()
        self.instr.set_output_inverted(2, False)
        self.instr.close()
        self._assert_cmds([b"CHN 2;OUTPUT NORMAL\n"])

    def test_set_output_load_impedance(self):
        self._open_helper()

        self._prep_cmd_no_error()
        self.instr.set_output_load_impedance(1, 50.0)
        self._assert_cmds([b"CHN 1;ZLOAD 50\n"])

        self._prep_cmd_no_error()
        self.instr.set_output_load_impedance(2, math.inf)
        self.instr.close()
        self._assert_cmds([b"CHN 2;ZLOAD OPEN\n"])

    def test_set_waveform(self):
        self._open_helper()

        self._prep_cmd_no_error()
        self.instr.set_waveform(1, WaveformType.SINE)
        self._assert_cmds([b"CHN 1;WAVE SINE\n"])

        self._prep_cmd_no_error()
        self.instr.set_waveform(2, WaveformType.SQUARE)
        self.instr.close()
        self._assert_cmds([b"CHN 2;WAVE SQUARE\n"])

    def test_set_frequency(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_frequency(1, 12345678.123456)
        self.instr.close()
        self._assert_cmds([b"CHN 1;FREQ 12345678.123456\n"])

    def test_set_square_duty_cycle(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_square_duty_cycle(1, 12.345)
        self.instr.close()
        self._assert_cmds([b"CHN 1;SQRSYMM 12.345\n"])

    def test_set_ramp_symmetry(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_ramp_symmetry(1, 34.567)
        self.instr.close()
        self._assert_cmds([b"CHN 1;RMPSYMM 34.567\n"])

    def test_set_amplitude(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_amplitude(1, 2.345, -0.678)
        self.instr.close()
        self._assert_cmds([b"CHN 1;AMPL 2.345;DCOFFS -0.678\n"])

    def test_set_phase(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_phase(1, 123.456)
        self.instr.close()
        self._assert_cmds([b"CHN 1;PHASE 123.456\n"])

    def test_get_external_reference_enabled(self):
        self._open_helper()

        self._transport_mock.read_until.return_value = b"INT\r\n"
        ret = self.instr.get_external_reference_enabled()
        self.assertFalse(ret)
        self._transport_mock.write.assert_called_once_with(b"CLKSRC?\n")

        self._transport_mock.read_until.return_value = b"EXT\r\n"
        ret = self.instr.get_external_reference_enabled()
        self.assertTrue(ret)

        self._transport_mock.read_until.return_value = b"ehm\r\n"
        with self.assertRaises(QMI_InstrumentException):
            ret = self.instr.get_external_reference_enabled()
        self.instr.close()

    def test_set_external_reference_enabled(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_external_reference_enabled(True)
        self.instr.close()
        self._assert_cmds([b"CLKSRC EXT\n"])

    def test_set_counter_enabled(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_counter_enabled(True)
        self.instr.close()
        self._assert_cmds([b"CNTRSWT ON\n"])

    def test_set_counter_input(self):
        self._open_helper()
        self._prep_cmd_no_error()
        self.instr.set_counter_input(CounterInputChannel.TRIG_IN)
        self.instr.close()
        self._assert_cmds([b"CNTRCPLNG DC\n"])

    def test_read_frequency(self):
        self._open_helper()
        self._transport_mock.read_until.side_effect = [b"125.001Hz\r\n", b"0.25\r\n", b"10x4Hz\r\n"]

        fake_time = time.time()
        with patch("qmi.instruments.tt.tgf.time.time", return_value=fake_time):
            ret = self.instr.read_frequency()
        self.assertEqual(ret.timestamp, fake_time)
        self.assertEqual(ret.frequency, 125.001)
        self._transport_mock.write.assert_called_once_with(b"CNTRVAL?\n")

        with self.assertRaises(QMI_InstrumentException):
            ret = self.instr.read_frequency()

        with self.assertRaises(QMI_InstrumentException):
            ret = self.instr.read_frequency()

        self.instr.close()

    def test_set_local(self):
        self._open_helper()
        self.instr.set_local()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"LOCAL\n")

    def test_bad_channel(self):
        self._open_helper()
        with self.assertRaises(ValueError):
            self.instr.set_output_enabled(0, True)
        with self.assertRaises(ValueError):
            self.instr.set_frequency(3, 100.0e3)
        self.instr.close()


if __name__ == '__main__':
    unittest.main()
