"""Unit test for Montana Cryostation driver."""

import logging
import math
import unittest
import warnings
from unittest.mock import MagicMock, Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.montana import Montana_Cryostation


class TestCryostation(unittest.TestCase):

    def setUp(self):
        qmi.start("TestContext")
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
                'qmi.instruments.montana.cryostation.create_transport',
                return_value=self._transport_mock):
            self.instr: Montana_Cryostation = qmi.make_instrument("instr", Montana_Cryostation, "transport_descriptor")

    def tearDown(self):
        logging.getLogger("qmi.instruments.montana.cryostation").setLevel(logging.NOTSET)
        qmi.stop()

    def _suppress_logging(self):
        logging.getLogger("qmi.instruments.montana.cryostation").setLevel(logging.CRITICAL)

    def test_open_close(self):
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_get_alarm_state(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"01", b"F"]

        alarm_state = self.instr.get_alarm_state()
        self.assertFalse(alarm_state)

        self._transport_mock.write.assert_called_once_with(b"03GAS")
        self.assertEqual(self._transport_mock.read.call_args_list, [
            call(2, Montana_Cryostation.RESPONSE_TIMEOUT),
            call(1, Montana_Cryostation.RESPONSE_TIMEOUT)
        ])

        self._transport_mock.read.side_effect = [b"01", b"T"]

        alarm_state = self.instr.get_alarm_state()
        self.assertTrue(alarm_state)

        self.instr.close()

    def test_get_chamber_pressure(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"08", b"660848.6"]
        chamber_pressure = self.instr.get_chamber_pressure("mTorr")
        self.assertAlmostEqual(chamber_pressure, 660848.6)
        self._transport_mock.write.assert_called_once_with(b"03GCP")

        self._transport_mock.read.side_effect = [b"08", b"660848.6"]
        chamber_pressure = self.instr.get_chamber_pressure("Pa")
        self.assertAlmostEqual(chamber_pressure, 660848.6 * (101325.0 / 760000.0))

        self._transport_mock.read.side_effect = [b"08", b"660848.6"]
        chamber_pressure = self.instr.get_chamber_pressure("atm")
        self.assertAlmostEqual(chamber_pressure, 660848.6 / 760000.0)

        self.instr.close()

    def test_get_magnet_state(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"14", b"MAGNET ENABLED"]
        magnet_state = self.instr.get_magnet_state()
        self.assertTrue(magnet_state)
        self._transport_mock.write.assert_called_once_with(b"03GMS")

        self._transport_mock.read.side_effect = [b"15", b"MAGNET DISABLED"]
        magnet_state = self.instr.get_magnet_state()
        self.assertFalse(magnet_state)

        self._transport_mock.read.side_effect = [
            b"83", b"System not able to execute command at this time. Activate the magnet module first. "]
        magnet_state = self.instr.get_magnet_state()
        self.assertIsNone(magnet_state)

        self.instr.close()

    def test_get_magnet_target_field(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"08", b"0.670000"]
        target = self.instr.get_magnet_target_field()
        self.assertAlmostEqual(target, 0.67)
        self._transport_mock.write.assert_called_once_with(b"04GMTF")

        self._transport_mock.read.side_effect = [b"09", b"-9.999999"]
        target = self.instr.get_magnet_target_field()
        self.assertTrue(math.isnan(target))

        self.instr.close()

    def test_get_platform_heater_power(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"05", b"4.904"]
        power = self.instr.get_platform_heater_power()
        self.assertAlmostEqual(power, 4.904)
        self._transport_mock.write.assert_called_once_with(b"04GPHP")

        self._transport_mock.read.side_effect = [b"06", b"-0.100"]
        power = self.instr.get_platform_heater_power()
        self.assertTrue(math.isnan(power))

        self.instr.close()

    def test_get_pid_integral_frequency(self):
        self._transport_mock.read.side_effect = [b"05", b"0.100"]

        self.instr.open()
        v = self.instr.get_pid_integral_frequency()
        self.instr.close()

        self.assertAlmostEqual(v, 0.1)
        self._transport_mock.write.assert_called_once_with(b"05GPIDF")

    def test_get_pid_proportional_gain(self):
        self._transport_mock.read.side_effect = [b"05", b"0.300"]

        self.instr.open()
        v = self.instr.get_pid_proportional_gain()
        self.instr.close()

        self.assertAlmostEqual(v, 0.3)
        self._transport_mock.write.assert_called_once_with(b"05GPIDK")

    def test_get_pid_derivative_time(self):
        self._transport_mock.read.side_effect = [b"05", b"0.100"]

        self.instr.open()
        v = self.instr.get_pid_derivative_time()
        self.instr.close()

        self.assertAlmostEqual(v, 0.1)
        self._transport_mock.write.assert_called_once_with(b"05GPIDT")

    def test_get_platform_stability(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"08", b"10.20239"]
        v = self.instr.get_platform_stability()
        self.assertAlmostEqual(v, 10.20239)
        self._transport_mock.write.assert_called_once_with(b"03GPS")

        self._transport_mock.read.side_effect = [b"08", b"-0.10000"]
        v = self.instr.get_platform_stability()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_get_stage_1_temperature(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"06", b"274.92"]
        v = self.instr.get_stage_1_temperature()
        self.assertAlmostEqual(v, 274.92)
        self._transport_mock.write.assert_called_once_with(b"04GS1T")

        self._transport_mock.read.side_effect = [b"05", b"-0.10"]
        v = self.instr.get_stage_1_temperature()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_get_stage_2_temperature(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"06", b"275.84"]
        v = self.instr.get_stage_2_temperature()
        self.assertAlmostEqual(v, 275.84)
        self._transport_mock.write.assert_called_once_with(b"04GS2T")

        self._transport_mock.read.side_effect = [b"05", b"-0.10"]
        v = self.instr.get_stage_2_temperature()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_get_platform_temperature(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"07", b"289.904"]
        v = self.instr.get_platform_temperature()
        self.assertAlmostEqual(v, 289.904)
        self._transport_mock.write.assert_called_once_with(b"03GPT")

        self._transport_mock.read.side_effect = [b"06", b"-0.100"]
        v = self.instr.get_platform_temperature()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_timeout(self):
        self.instr.open()

        self._transport_mock.read.side_effect = QMI_TimeoutException("too late")
        with self.assertRaises(QMI_TimeoutException):
            v = self.instr.get_platform_temperature()
        self._transport_mock.write.assert_called_once_with(b"03GPT")

        self.instr.close()

    def test_get_sample_stability(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"07", b"0.00900"]
        v = self.instr.get_sample_stability()
        self.assertAlmostEqual(v, 0.009)
        self._transport_mock.write.assert_called_once_with(b"03GSS")

        self._transport_mock.read.side_effect = [b"08", b"-0.10000"]
        v = self.instr.get_sample_stability()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_get_sample_temperature(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"07", b"289.904"]
        v = self.instr.get_sample_temperature()
        self.assertAlmostEqual(v, 289.904)
        self._transport_mock.write.assert_called_once_with(b"03GST")

        self._transport_mock.read.side_effect = [b"06", b"-0.100"]
        v = self.instr.get_sample_temperature()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_get_temperature_setpoint(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"04", b"4.20"]
        v = self.instr.get_temperature_setpoint()
        self.assertAlmostEqual(v, 4.2)
        self._transport_mock.write.assert_called_once_with(b"04GTSP")

        self.instr.close()

    def test_get_user_stability(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"07", b"0.00900"]
        v = self.instr.get_user_stability()
        self.assertAlmostEqual(v, 0.009)
        self._transport_mock.write.assert_called_once_with(b"03GUS")

        self._transport_mock.read.side_effect = [b"08", b"-0.10000"]
        v = self.instr.get_user_stability()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_get_user_temperature(self):
        self.instr.open()

        self._transport_mock.read.side_effect = [b"05", b"3.498"]
        v = self.instr.get_user_temperature()
        self.assertAlmostEqual(v, 3.498)
        self._transport_mock.write.assert_called_once_with(b"03GUT")

        self._transport_mock.read.side_effect = [b"06", b"-0.100"]
        v = self.instr.get_user_temperature()
        self.assertTrue(math.isnan(v))

        self.instr.close()

    def test_set_pid_integral_frequency(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"44", b"OK, Gain = 0.300, Freq = 0.100, Time = 0.100"]
        self.instr.set_pid_integral_frequency(0.1)
        self._transport_mock.write.assert_called_once_with(b"11SPIDF 0.100")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"28", b"Error: Invalid PID parameter"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pid_integral_frequency(0.1)

        with self.assertRaises(ValueError):
            self.instr.set_pid_integral_frequency(-1)

        with self.assertRaises(ValueError):
            self.instr.set_pid_integral_frequency(101)

        self.instr.close()

    def test_set_pid_proportional_gain(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"44", b"OK, Gain = 0.300, Freq = 0.100, Time = 0.100"]
        self.instr.set_pid_proportional_gain(0.1)
        self._transport_mock.write.assert_called_once_with(b"11SPIDK 0.100")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"28", b"Error: Invalid PID parameter"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pid_proportional_gain(0.1)

        with self.assertRaises(ValueError):
            self.instr.set_pid_proportional_gain(-1)

        with self.assertRaises(ValueError):
            self.instr.set_pid_proportional_gain(101)

        self.instr.close()

    def test_set_pid_derivative_time(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"44", b"OK, Gain = 0.300, Freq = 0.100, Time = 0.100"]
        self.instr.set_pid_derivative_time(0.1)
        self._transport_mock.write.assert_called_once_with(b"11SPIDT 0.100")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"28", b"Error: Invalid PID parameter"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pid_derivative_time(0.1)

        with self.assertRaises(ValueError):
            self.instr.set_pid_derivative_time(-1)

        with self.assertRaises(ValueError):
            self.instr.set_pid_derivative_time(101)

        self.instr.close()

    def test_set_temperature_setpoint(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"32", b"OK, Temperature Set Point = 4.20"]
        self.instr.set_temperature_setpoint(5)
        self._transport_mock.write.assert_called_once_with(b"09STSP 5.00")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"24", b"Error: Invalid set point"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_temperature_setpoint(5)

        with self.assertRaises(ValueError):
            self.instr.set_temperature_setpoint(1)

        with self.assertRaises(ValueError):
            self.instr.set_temperature_setpoint(351)

        self.instr.close()

    def test_start_standby(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"02", b"OK"]
        self.instr.start_standby()
        self._transport_mock.write.assert_called_once_with(b"03SSB")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"39", b"System not able to standby at this time"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.start_standby()

        self.instr.close()

    def test_start_warmup(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"02", b"OK"]
        self.instr.start_warmup()
        self._transport_mock.write.assert_called_once_with(b"03SWU")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"39", b"System not able to warmup at this time"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.start_warmup()

        self.instr.close()

    def test_start_cooldown(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"02", b"OK"]
        self.instr.start_cooldown()
        self._transport_mock.write.assert_called_once_with(b"03SCD")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"39", b"System not able to cooldown at this time"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.start_cooldown()

        self.instr.close()

    def test_stop_system(self):
        self._suppress_logging()
        self.instr.open()

        self._transport_mock.read.side_effect = [b"02", b"OK"]
        self.instr.stop_system()
        self._transport_mock.write.assert_called_once_with(b"03STP")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"39", b"System not able to stop at this time"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.stop_system()

        self.instr.close()

    def test_set_platform_heater_power(self):
        self._suppress_logging()

        self.instr.open()

        # Note: this is probably not the exact string sent by Montana
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]

        self.instr.set_platform_heater_power(0.123)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.1230")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power(1.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 1.0000")

        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.set_platform_heater_power(1.1)

        # Turn heater off before closing the instrument.
        # We will separately test scenarios where the instrument is closed with the heater still on.
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power(0.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.0000")

        self.instr.close()

    def test_set_platform_heater_power_failed(self):
        self._suppress_logging()

        self.instr.open()

        # Simulate a failure while trying to set the heater.
        self._transport_mock.read.side_effect = [
            b"18", b"heater out of fuel",
            b"35", b"OK, Platform Heater Power Set Point"
        ]

        # Attempting to set the heater will raise an exception.
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_platform_heater_power(0.123)

        # After the failed attempt to set the heater, the driver will
        # set turn the heater off as a safety measure.
        self.assertEqual(self._transport_mock.write.call_args_list, [
            call(b"11SPHP 0.1230"),
            call(b"11SPHP 0.0000")
        ])

        self.instr.close()

    def test_set_platform_heater_power_burst(self):
        self._suppress_logging()

        self.instr.open()

        # Set the heater to high power.
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(5.0, 2.5)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 5.0000")

        # Then immediately turn the heater back off.
        # We do not test the time limit yet.
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(0.0, 0.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.0000")

        # Test out-of-range values.
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.set_platform_heater_power_burst(10.1, 1.0)

        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.set_platform_heater_power_burst(1.0, 30.1)

        self.instr.close()

    @patch("qmi.instruments.montana.cryostation.threading.Timer")
    def test_set_platform_heater_power_burst_timelimit(self, timer_mock):
        self._suppress_logging()

        self.instr.open()

        timer_instance_mock = Mock()
        timer_mock.return_value = timer_instance_mock

        # Set the heater to high power.
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(10.0, 1.2)
        self._transport_mock.write.assert_called_once_with(b"12SPHP 10.0000")

        # Driver should have started a background timer thread.
        timer_mock.assert_called_once()
        timer_instance_mock.start.assert_called_once()
        (timer_interval, timer_callback) = timer_mock.call_args[0]
        self.assertEqual(timer_interval, 1.2)

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]

        # Now invoke the timer callback so the driver will think the time limit passed.
        # At this point the driver must turn off the heater.
        timer_callback()
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.0000")

        self.instr.close()

        # The callback thread should be cleaned up when the driver is closed.
        timer_instance_mock.join.assert_called_once()

    @patch("qmi.instruments.montana.cryostation.threading.Timer")
    def test_set_platform_heater_power_burst_extended(self, timer_mock):
        self._suppress_logging()

        self.instr.open()

        timer_instance_mock = Mock()
        timer_mock.return_value = timer_instance_mock

        # Set the heater to high power.
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(5.0, 1.5)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 5.0000")

        # Driver should have started a background timer thread.
        timer_mock.assert_called_once()
        timer_instance_mock.start.assert_called_once()

        timer_instance2_mock = Mock()
        timer_mock.return_value = timer_instance2_mock

        # Set heater power again.
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(5.0, 1.5)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 5.0000")

        # Driver should have canceled and restarted the timer.
        timer_instance_mock.cancel.assert_called_once()
        timer_instance_mock.join.assert_called_once()
        timer_instance2_mock.start.assert_called_once()

        # Set "safe" heater power with the normal function.
        # This should cancel the timer.
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power(0.1)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.1000")

        timer_instance2_mock.cancel.assert_called_once()
        timer_instance2_mock.join.assert_called_once()

        # Turn heater off.
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power(0.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.0000")

        self.instr.close()

    def test_set_platform_heater_power_off_on_close(self):
        self.instr.open()

        # Set the heater to high power.
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(5.0, 10.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 5.0000")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]

        # Close the driver with the heater still on.
        self.instr.close()

        # The driver should have turned off the heater while closing.
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.0000")

    def test_set_platform_heater_power_off_on_shutdown(self):
        self.instr.open()

        # Set the heater to high power.
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(5.0, 10.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 5.0000")

        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]

        # Stop QMI without closing the driver.
        # The driver should turn off the heater during cleanup.
        with warnings.catch_warnings():
            # Suppress warning for stopping QMI without closing instrument.
            warnings.simplefilter("ignore", ResourceWarning)
            qmi.stop()

        # The driver should have turned off the heater during cleanup.
        self._transport_mock.write.assert_called_once_with(b"11SPHP 0.0000")

        # Start QMI again because tearDown() wants to stop it.
        qmi.start("TestContext")

    @patch("time.sleep")
    def test_set_platform_heater_power_off_retry(self, sleep_mock):
        self._suppress_logging()

        self.instr.open()

        # Set the heater to high power.
        self._transport_mock.read.side_effect = [b"35", b"OK, Platform Heater Power Set Point"]
        self.instr.set_platform_heater_power_burst(5.0, 10.0)
        self._transport_mock.write.assert_called_once_with(b"11SPHP 5.0000")

        # Close the driver with the heater still on.
        # The driver will try to turn off the heater, but the first attempt fails.
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [
            b"34", b"NO, gonna keep heating the diamond",
            b"35", b"OK, Platform Heater Power Set Point"
        ]

        self.instr.close()

        # Expect two attempts to turn off the heater.
        self.assertEqual(self._transport_mock.write.call_args_list, [
            call(b"11SPHP 0.0000"),
            call(b"11SPHP 0.0000")
        ])


if __name__ == '__main__':
    unittest.main()
