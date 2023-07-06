"""Unit test for Quantum Composers 9530 Pulse Generator."""

import logging
from typing import cast
import unittest
from unittest.mock import MagicMock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.quantum_composers import QuantumComposers_9530
from qmi.instruments.quantum_composers import (
    RefClkSource, PulseMode, TriggerMode, TriggerEdge, OutputDriver
)


class SuppressLogging:
    """Context manager to temporarily suppress logging during a test."""

    def __enter__(self):
        # Suppress logging of all levels up to ERROR.
        logging.getLogger("qmi.instruments.quantum_composers.pulse_generator9530").setLevel(logging.CRITICAL)

    def __exit__(self, typ, value, tb):
        # Restore default log levels.
        logging.getLogger("qmi.instruments.quantum_composers.pulse_generator9530").setLevel(logging.NOTSET)


class TestPulseGenerator9530(unittest.TestCase):

    def setUp(self):
        qmi.start("TestContext")
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
                'qmi.instruments.quantum_composers.pulse_generator9530.create_transport',
                return_value=self._transport_mock):
            self.instr: QuantumComposers_9530 = qmi.make_instrument("instr", QuantumComposers_9530, "transport_descriptor")
            self.instr = cast(QuantumComposers_9530, self.instr)

    def tearDown(self):
        qmi.stop()

    def test_open_close(self):
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_get_idn(self):
        self._transport_mock.read_until.return_value = b"vendor,model,serial,version\r\n"
        self.instr.open()
        idn = self.instr.get_idn()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"*IDN?\r\n")
        self.assertEqual(idn.vendor, "vendor")
        self.assertEqual(idn.model, "model")
        self.assertEqual(idn.serial, "serial")
        self.assertEqual(idn.version, "version")

    def test_get_idn_fail(self):
        self._transport_mock.read_until.return_value = b"nonsense\r\n"
        self.instr.open()
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            idn = self.instr.get_idn()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"*IDN?\r\n")

    def test_reset(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.reset()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"*RST\r\n")

    def test_get_num_channels(self):
        self._transport_mock.read_until.return_value = b"T0, CHA, CHB, CHC, CHD\r\n"
        self.instr.open()
        num_channels = self.instr.get_num_channels()
        self.instr.close()
        self.assertEqual(num_channels, 4)
        self._transport_mock.write.assert_called_once_with(b":INST:CAT?\r\n")

    def test_get_num_channels_fail(self):
        self._transport_mock.read_until.return_value = b"?3\r\n"
        self.instr.open()
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            num_channels = self.instr.get_num_channels()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":INST:CAT?\r\n")

    def test_get_refclk_source(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"INT\r\n"
        source = self.instr.get_refclk_source()
        self.assertEqual(source, RefClkSource.INTERNAL)

        self._transport_mock.read_until.return_value = b"EXT\r\n"
        source = self.instr.get_refclk_source()
        self.assertEqual(source, RefClkSource.EXTERNAL)

        self._transport_mock.read_until.return_value = b"XPL\r\n"
        source = self.instr.get_refclk_source()
        self.assertEqual(source, RefClkSource.EXTPLL)

        self._transport_mock.read_until.return_value = b"XPL?\r\n"
        source = self.instr.get_refclk_source()
        self.assertEqual(source, RefClkSource.EXTPLL)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:ICL:MOD?\r\n"),
            call(b":PULSE0:ICL:MOD?\r\n"),
            call(b":PULSE0:ICL:MOD?\r\n"),
            call(b":PULSE0:ICL:MOD?\r\n"),
        ])

    def test_get_refclk_source_fail(self):
        self._transport_mock.read_until.return_value = b"unknown\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            source = self.instr.get_refclk_source()
        self.instr.close()

    def test_is_refclk_pll_locked(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"XPL\r\n"
        locked = self.instr.is_refclk_pll_locked()
        self.assertTrue(locked)

        self._transport_mock.read_until.return_value = b"XPL?\r\n"
        locked = self.instr.is_refclk_pll_locked()
        self.assertFalse(locked)

        self._transport_mock.read_until.return_value = b"INT\r\n"
        locked = self.instr.is_refclk_pll_locked()
        self.assertFalse(locked)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:ICL:MOD?\r\n"),
            call(b":PULSE0:ICL:MOD?\r\n"),
            call(b":PULSE0:ICL:MOD?\r\n"),
        ])

    def test_set_refclk_source(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_refclk_source(RefClkSource.INTERNAL)
        self.instr.set_refclk_source(RefClkSource.EXTERNAL)
        self.instr.set_refclk_source(RefClkSource.EXTPLL)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:ICL:MOD INT\r\n"),
            call(b":PULSE0:ICL:MOD EXT\r\n"),
            call(b":PULSE0:ICL:MOD XPL\r\n"),
        ])

    def test_get_refclk_rate(self):
        self._transport_mock.read_until.return_value = b"50\r\n"
        self.instr.open()
        rate = self.instr.get_refclk_rate()
        self.instr.close()
        self.assertEqual(rate, 50)
        self._transport_mock.write.assert_called_once_with(b":PULSE0:ICL:RAT?\r\n")

    def test_bad_int_response(self):
        self._transport_mock.read_until.return_value = b"not_int\r\n"
        self.instr.open()
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            rate = self.instr.get_refclk_rate()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:ICL:RAT?\r\n")

    def test_set_refclk_rate(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_refclk_rate(10)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:ICL:RAT 10\r\n")

    def test_get_refclk_level(self):
        self._transport_mock.read_until.return_value = b"0.50\r\n"
        self.instr.open()
        level = self.instr.get_refclk_level()
        self.instr.close()
        self.assertEqual(level, 0.5)
        self._transport_mock.write.assert_called_once_with(b":PULSE0:ICL:LEV?\r\n")

    def test_bad_float_response(self):
        self._transport_mock.read_until.return_value = b"not_float\r\n"
        self.instr.open()
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            level = self.instr.get_refclk_level()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:ICL:LEV?\r\n")

    def test_set_refclk_level(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_refclk_level(1.5)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:ICL:LEV 1.500\r\n")

    def test_set_refclk_external(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_refclk_external(rate=10, level=1.0, use_pll=True)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:ICL:MOD XPL\r\n"),
            call(b":PULSE0:ICL:RAT 10\r\n"),
            call(b":PULSE0:ICL:LEV 1.000\r\n"),
        ])

    def test_get_output_enabled(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"1\r\n"
        enabled = self.instr.get_output_enabled()
        self.assertTrue(enabled)

        self._transport_mock.read_until.return_value = b"0\r\n"
        enabled = self.instr.get_output_enabled()
        self.assertFalse(enabled)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:STAT?\r\n"),
            call(b":PULSE0:STAT?\r\n"),
        ])

    def test_bad_bool_response(self):
        self._transport_mock.read_until.return_value = b"maybe\r\n"
        self.instr.open()
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            enabled = self.instr.get_output_enabled()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:STAT?\r\n")

    def test_set_output_enabled(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_output_enabled(True)
        self.instr.set_output_enabled(False)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:STAT 1\r\n"),
            call(b":PULSE0:STAT 0\r\n"),
        ])

    def test_set_output_enabled_fail(self):
        self._transport_mock.read_until.return_value = b"?3\r\n"
        self.instr.open()
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_enabled(True)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:STAT 1\r\n")

    def test_set_output_enabled_fail_nonsense(self):
        self.instr.open()
        self._transport_mock.read_until.return_value = b"?unknown_error\r\n"
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_enabled(True)
        self._transport_mock.read_until.return_value = b"?100\r\n"
        with SuppressLogging(), self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_enabled(True)
        self.instr.close()

    def test_get_t0_period(self):
        self._transport_mock.read_until.return_value = b"2.718281828\r\n"
        self.instr.open()
        period = self.instr.get_t0_period()
        self.instr.close()
        self.assertEqual(period, 2.718281828)
        self._transport_mock.write.assert_called_once_with(b":PULSE0:PER?\r\n")

    def test_set_t0_period(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_t0_period(3.141592653589793)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:PER 3.141592654\r\n")

    def test_set_t0_period(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_t0_period(3.141592653589793)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:PER 3.141592654\r\n")

    def test_get_t0_mode(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"NORM\r\n"
        mode = self.instr.get_t0_mode()
        self.assertEqual(mode, PulseMode.NORMAL)

        self._transport_mock.read_until.return_value = b"SING\r\n"
        mode = self.instr.get_t0_mode()
        self.assertEqual(mode, PulseMode.SINGLE)

        self._transport_mock.read_until.return_value = b"BURS\r\n"
        mode = self.instr.get_t0_mode()
        self.assertEqual(mode, PulseMode.BURST)

        self._transport_mock.read_until.return_value = b"DCYC\r\n"
        mode = self.instr.get_t0_mode()
        self.assertEqual(mode, PulseMode.DUTYCYCLE)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:MOD?\r\n"),
            call(b":PULSE0:MOD?\r\n"),
            call(b":PULSE0:MOD?\r\n"),
        ])

    def test_get_t0_mode_fail(self):
        self._transport_mock.read_until.return_value = b"unknown\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            mode = self.instr.get_t0_mode()
        self.instr.close()

    def test_set_t0_mode(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_t0_mode(PulseMode.NORMAL)
        self.instr.set_t0_mode(PulseMode.SINGLE)
        self.instr.set_t0_mode(PulseMode.BURST)
        self.instr.set_t0_mode(PulseMode.DUTYCYCLE)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:MOD NORM\r\n"),
            call(b":PULSE0:MOD SING\r\n"),
            call(b":PULSE0:MOD BURS\r\n"),
            call(b":PULSE0:MOD DCYC\r\n"),
        ])

    def test_get_t0_burst_count(self):
        self._transport_mock.read_until.return_value = b"5\r\n"
        self.instr.open()
        burst = self.instr.get_t0_burst_count()
        self.instr.close()
        self.assertEqual(burst, 5)
        self._transport_mock.write.assert_called_once_with(b":PULSE0:BCO?\r\n")

    def test_set_t0_burst_count(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_t0_burst_count(21)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:BCO 21\r\n")

    def test_get_t0_duty_cycle(self):
        self._transport_mock.read_until.side_effect = [
            b"3\r\n",
            b"7\r\n"
        ]
        self.instr.open()
        duty_cycle = self.instr.get_t0_duty_cycle()
        self.instr.close()
        self.assertEqual(duty_cycle, (3, 7))
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:PCO?\r\n"),
            call(b":PULSE0:OCO?\r\n"),
        ])

    def test_set_t0_duty_cycle(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_t0_duty_cycle(5, 11)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:PCO 5\r\n"),
            call(b":PULSE0:OCO 11\r\n"),
        ])

    def test_get_trigger_mode(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"DIS\r\n"
        mode = self.instr.get_trigger_mode()
        self.assertEqual(mode, TriggerMode.DISABLED)

        self._transport_mock.read_until.return_value = b"TRIG\r\n"
        mode = self.instr.get_trigger_mode()
        self.assertEqual(mode, TriggerMode.ENABLED)

        self._transport_mock.read_until.return_value = b"DUAL\r\n"
        mode = self.instr.get_trigger_mode()
        self.assertEqual(mode, TriggerMode.DUAL)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:TRIG:MOD?\r\n"),
            call(b":PULSE0:TRIG:MOD?\r\n"),
            call(b":PULSE0:TRIG:MOD?\r\n"),
        ])

    def test_get_trigger_mode_fail(self):
        self._transport_mock.read_until.return_value = b"unknown\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            mode = self.instr.get_trigger_mode()
        self.instr.close()

    def test_set_trigger_mode(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_trigger_mode(TriggerMode.DISABLED)
        self.instr.set_trigger_mode(TriggerMode.ENABLED)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:TRIG:MOD DIS\r\n"),
            call(b":PULSE0:TRIG:MOD TRIG\r\n"),
        ])

    def test_get_trigger_edge(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"RIS\r\n"
        mode = self.instr.get_trigger_edge()
        self.assertEqual(mode, TriggerEdge.RISING)

        self._transport_mock.read_until.return_value = b"FALL\r\n"
        mode = self.instr.get_trigger_edge()
        self.assertEqual(mode, TriggerEdge.FALLING)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:TRIG:EDGE?\r\n"),
            call(b":PULSE0:TRIG:EDGE?\r\n"),
        ])

    def test_get_trigger_edge_fail(self):
        self._transport_mock.read_until.return_value = b"unknown\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            edge = self.instr.get_trigger_edge()
        self.instr.close()

    def test_set_trigger_edge(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_trigger_edge(TriggerEdge.RISING)
        self.instr.set_trigger_edge(TriggerEdge.FALLING)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE0:TRIG:EDGE RIS\r\n"),
            call(b":PULSE0:TRIG:EDGE FALL\r\n"),
        ])

    def test_get_trigger_level(self):
        self._transport_mock.read_until.return_value = b"0.90\r\n"
        self.instr.open()
        level = self.instr.get_trigger_level()
        self.instr.close()
        self.assertEqual(level, 0.90)
        self._transport_mock.write.assert_called_once_with(b":PULSE0:TRIG:LEVEL?\r\n")

    def test_set_trigger_level(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_trigger_level(1.23)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE0:TRIG:LEVEL 1.230\r\n")

    def test_get_channel_enabled(self):
        self._transport_mock.read_until.return_value = b"0\r\n"
        self.instr.open()
        enabled = self.instr.get_channel_enabled(3)
        self.instr.close()
        self.assertFalse(enabled)
        self._transport_mock.write.assert_called_once_with(b":PULSE3:STAT?\r\n")

    def test_set_channel_enabled(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_channel_enabled(4, True)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE4:STAT 1\r\n")

    def test_get_channel_width(self):
        self._transport_mock.read_until.return_value = b"0.01234567891\r\n"
        self.instr.open()
        width = self.instr.get_channel_width(5)
        self.instr.close()
        self.assertEqual(width, 0.01234567891)
        self._transport_mock.write.assert_called_once_with(b":PULSE5:WIDT?\r\n")

    def test_set_channel_width(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_channel_width(6, 1.23456789125)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE6:WIDT 1.23456789125\r\n")

    def test_get_channel_delay(self):
        self._transport_mock.read_until.return_value = b"0.23456789123\r\n"
        self.instr.open()
        width = self.instr.get_channel_delay(7)
        self.instr.close()
        self.assertEqual(width, 0.23456789123)
        self._transport_mock.write.assert_called_once_with(b":PULSE7:DEL?\r\n")

    def test_set_channel_delay(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_channel_delay(8, 0.34567891275)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE8:DEL 0.34567891275\r\n")

    def test_get_channel_mode(self):
        self._transport_mock.read_until.return_value = b"NORM\r\n"
        self.instr.open()
        mode = self.instr.get_channel_mode(1)
        self.instr.close()
        self.assertEqual(mode, PulseMode.NORMAL)
        self._transport_mock.write.assert_called_once_with(b":PULSE1:CMOD?\r\n")

    def test_get_channel_mode_fail(self):
        self._transport_mock.read_until.return_value = b"unknown\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            edge = self.instr.get_channel_mode(1)
        self.instr.close()

    def test_set_channel_mode(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_channel_mode(2, PulseMode.BURST)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE2:CMOD BURS\r\n")

    def test_get_channel_burst_count(self):
        self._transport_mock.read_until.return_value = b"11\r\n"
        self.instr.open()
        burst = self.instr.get_channel_burst_count(3)
        self.instr.close()
        self.assertEqual(burst, 11)
        self._transport_mock.write.assert_called_once_with(b":PULSE3:BCO?\r\n")

    def test_set_channel_burst_count(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_channel_burst_count(3, 4)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE3:BCO 4\r\n")

    def test_get_channel_duty_cycle(self):
        self._transport_mock.read_until.side_effect = [
            b"8\r\n",
            b"9\r\n",
        ]
        self.instr.open()
        duty_cycle = self.instr.get_channel_duty_cycle(1)
        self.instr.close()
        self.assertEqual(duty_cycle, (8, 9))
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE1:PCO?\r\n"),
            call(b":PULSE1:OCO?\r\n"),
        ])

    def test_set_channel_duty_cycle(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_channel_duty_cycle(1, 10, 11)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE1:PCO 10\r\n"),
            call(b":PULSE1:OCO 11\r\n"),
        ])

    def test_get_output_driver(self):
        self.instr.open()

        self._transport_mock.read_until.return_value = b"TTL\r\n"
        driver = self.instr.get_output_driver(2)
        self.assertEqual(driver, OutputDriver.TTL)

        self._transport_mock.read_until.return_value = b"ADJ\r\n"
        driver = self.instr.get_output_driver(3)
        self.assertEqual(driver, OutputDriver.ADJUSTABLE)

        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE2:OUTP:MODE?\r\n"),
            call(b":PULSE3:OUTP:MODE?\r\n"),
        ])

    def test_set_output_driver(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_output_driver(2, OutputDriver.TTL)
        self.instr.set_output_driver(3, OutputDriver.ADJUSTABLE)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b":PULSE2:OUTP:MODE TTL\r\n"),
            call(b":PULSE3:OUTP:MODE ADJ\r\n"),
        ])

    def test_get_output_ampliude(self):
        self._transport_mock.read_until.return_value = b"3.14\r\n"
        self.instr.open()
        ampl = self.instr.get_output_amplitude(1)
        self.instr.close()
        self.assertEqual(ampl, 3.14)
        self._transport_mock.write.assert_called_once_with(b":PULSE1:OUTP:AMPL?\r\n")

    def test_set_output_ampliude(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_output_amplitude(2, 3.3)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE2:OUTP:AMPL 3.300\r\n")

    def test_get_output_inverted(self):
        self._transport_mock.read_until.return_value = b"INV\r\n"
        self.instr.open()
        inv = self.instr.get_output_inverted(1)
        self.instr.close()
        self.assertTrue(inv)
        self._transport_mock.write.assert_called_once_with(b":PULSE1:POL?\r\n")

    def test_set_output_inverted(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_output_inverted(2, False)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":PULSE2:POL NORM\r\n")

    def test_bad_channel(self):
        self.instr.open()
        with self.assertRaises(ValueError):
            self.instr.get_channel_enabled(0)
        with self.assertRaises(ValueError):
            self.instr.set_channel_enabled(0, True)
        with self.assertRaises(ValueError):
            self.instr.get_channel_width(0)
        with self.assertRaises(ValueError):
            self.instr.set_channel_width(0, 0.1)
        with self.assertRaises(ValueError):
            self.instr.get_channel_delay(0)
        with self.assertRaises(ValueError):
            self.instr.set_channel_delay(0, 0.1)
        with self.assertRaises(ValueError):
            self.instr.get_channel_mode(0)
        with self.assertRaises(ValueError):
            self.instr.set_channel_mode(0, PulseMode.NORMAL)
        with self.assertRaises(ValueError):
            self.instr.get_channel_burst_count(0)
        with self.assertRaises(ValueError):
            self.instr.set_channel_burst_count(0, 1)
        with self.assertRaises(ValueError):
            self.instr.get_channel_duty_cycle(0)
        with self.assertRaises(ValueError):
            self.instr.set_channel_duty_cycle(0, 1, 2)
        with self.assertRaises(ValueError):
            self.instr.get_output_driver(0)
        with self.assertRaises(ValueError):
            self.instr.set_output_driver(0, OutputDriver.TTL)
        with self.assertRaises(ValueError):
            self.instr.get_output_amplitude(0)
        with self.assertRaises(ValueError):
            self.instr.set_output_amplitude(0, 3.0)
        with self.assertRaises(ValueError):
            self.instr.get_output_inverted(0)
        with self.assertRaises(ValueError):
            self.instr.set_output_inverted(0, False)
        self.instr.close()

    def test_out_of_range(self):
        self.instr.open()
        with self.assertRaises(ValueError):
            self.instr.set_t0_period(0)
        with self.assertRaises(ValueError):
            self.instr.set_t0_period(10000)
        self.instr.close()

    def test_set_display_enabled(self):
        self._transport_mock.read_until.return_value = b"ok\r\n"
        self.instr.open()
        self.instr.set_display_enabled(False)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b":DISP:ENAB 0\r\n")


if __name__ == '__main__':
    unittest.main()
