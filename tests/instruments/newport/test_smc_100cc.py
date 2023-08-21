"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.newport import Newport_Smc100Cc
from qmi.instruments.newport.actuators import TRA12CC, TRB6CC, CMA25CCL


class TestNewportSmc100Cc(unittest.TestCase):
    """
    Tests for the single axis motion controller.
    """

    TRANSPORT_STR = "/dev/cu.usbserial-FT5TMFGL"

    def setUp(self):
        qmi.start("Test100CcControllerContext", console_loglevel="CRITICAL")
        # Add patches
        patcher = patch(
            'qmi.instruments.newport.single_axis_motion_controller.create_transport', spec=QMI_TcpTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch(
            'qmi.instruments.newport.single_axis_motion_controller.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUTs
        self.controller_address = 1
        self.instr: Newport_Smc100Cc = qmi.make_instrument(
            "sam_controller", Newport_Smc100Cc, self.TRANSPORT_STR, "FT5TMFGL",
            {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
            90210)
        self.instr = cast(Newport_Smc100Cc, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_set_encoder_resolution_without_controller_address_sets_resolution(self):
        """Test set encoder resolution."""
        resolution = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}SU%s\r\n" % resolution),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_encoder_increment_value(resolution)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_encoder_resolution_with_controller_address_sets_resolution(self):
        """Test set encoder resolution with controller address."""
        resolution = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call(f"3SU{resolution}\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3TE\r\n"),
            call("3TE\r\n")
        ]
        self.instr.set_encoder_increment_value(resolution, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_encoder_increment_value_gets_value(self):
        """Test get encoder increment value."""
        expected_encoder_unit = 10
        encoder_resolution = TRA12CC.ENCODER_RESOLUTION
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"{self.controller_address}SU %s" % (encoder_resolution / expected_encoder_unit), "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}SU?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_encoder_unit = self.instr.get_encoder_increment_value()
        self.assertEqual(expected_encoder_unit, actual_encoder_unit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_driver_voltage(self):
        """Test getting driver voltage."""
        expected_value = 24
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}DV %i" % expected_value, "@"]
        expected_calls = [
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_value = self.instr.get_driver_voltage()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_driver_voltage(self):
        """Test setting driver voltage."""
        driver_voltage = 24
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_driver_voltage(driver_voltage)

        self._scpi_mock.write.assert_called_once_with(f"1DV{driver_voltage}\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_set_driver_voltage_excepts(self):
        """Test setting driver voltage excepts when value out of valid range."""
        driver_voltage_invalid = [11.9, 48.1]
        for value in driver_voltage_invalid:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_driver_voltage(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_low_pass_filter_cutoff_frequency_gets_frequency(self):
        """Test get low pass filter cutoff frequency."""
        expected_frequency = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}FD%s" % expected_frequency, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}FD?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_frequency = self.instr.get_low_pass_filter_cutoff_frequency()

        self.assertEqual(expected_frequency, actual_frequency)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_low_pass_filter_cutoff_frequency_with_persist_sets_frequency(self):
        """Test set low pass filter cutoff frequency with persist."""
        frequency = 1.3
        persist = True
        self._scpi_mock.ask.return_value = "@"
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}FD%s\r\n" % frequency),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_low_pass_filter_cutoff_frequency(frequency, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_low_pass_filter_cutoff_frequency_sets_frequency(self):
        """Test set low pass filter cutoff frequency."""
        frequency = 1.3
        expected_call = f"1FD{frequency}\r\n"
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_low_pass_filter_cutoff_frequency(frequency)

        self._scpi_mock.write.assert_called_once_with(expected_call)

    def test_set_low_pass_filter_cutoff_frequency_with_error_throws_exception(self):
        """Test set low pass filter cutoff frequency with error."""
        out_of_bounds = [1E-6, 2000]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_low_pass_filter_cutoff_frequency(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_following_error_limit_gets_limit(self):
        """Test get following error limit."""
        expected_limit = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}FE%s" % expected_limit, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}FE?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_limit = self.instr.get_following_error_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_following_error_limit_with_persist_sets_limit(self):
        """Test set following error limit with persist."""
        limit = 1.3
        persist = True
        self._scpi_mock.ask.return_value = "@"
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}FE%s\r\n" % limit),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_following_error_limit(limit, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_following_error_limit_sets_limit(self):
        """Test set following error limit."""
        limit = 1.3
        expected_call = f"1FE{limit}\r\n"
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_following_error_limit(limit)

        self._scpi_mock.write.assert_called_once_with(expected_call)

    def test_set_following_error_limit_with_error_throws_exception(self):
        """Test set following error limit with error."""
        out_of_bounds = [1E-6, 1E12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_following_error_limit(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_friction_compensation_gets_compensation(self):
        """Test get friction compensation."""
        expected_compensation = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}FF%s" % expected_compensation, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}FF?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_compensation = self.instr.get_friction_compensation()

        self.assertEqual(expected_compensation, actual_compensation)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_with_persist_sets_compensation(self):
        """Test set friction compensation with persist."""
        driver_voltage = 100.0
        compensation = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}DV{driver_voltage}", "@", "@", "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}FF%s\r\n" % compensation),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_friction_compensation(compensation, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_sets_compensation(self):
        """Test set friction compensation."""
        driver_voltage = 100.0
        compensation = 1.3
        expected_write_call = f"1FF{compensation}\r\n"
        expected_ask_calls = [
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]

        self._scpi_mock.ask.side_effect = [f"{self.controller_address}DV{driver_voltage}", "@", "@"]
        self.instr.set_friction_compensation(compensation)

        self._scpi_mock.write.assert_called_once_with(expected_write_call)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_with_error_throws_exception(self):
        """Test set friction compensation with error."""
        driver_voltage = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1DV{driver_voltage}", "@", f"1DV{driver_voltage}", "@"
        ]
        expected_ask_calls = [
            call("1DV?\r\n"),
            call("1TE\r\n"),
            call("1DV?\r\n"),
            call("1TE\r\n")
        ]
        out_of_bounds = [-0.001, driver_voltage]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_friction_compensation(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_derivative_gain_gets_gain(self):
        """Test get derivative gain."""
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}KD%s" % expected_gain, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}KD?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_gain = self.instr.get_derivative_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_derivative_gain_with_persist_sets_gain(self):
        """Test set derivative gain with persist."""
        gain = 1.3
        persist = True
        self._scpi_mock.ask.return_value = "@"
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}KD%s\r\n" % gain),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_derivative_gain(gain, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_derivative_gain_sets_gain(self):
        """Test set derivative gain."""
        gain = 1.3
        expected_call = f"1KD{gain}\r\n"
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_derivative_gain(gain)

        self._scpi_mock.write.assert_called_once_with(expected_call)

    def test_set_derivative_gain_with_error_throws_exception(self):
        """Test set derivative gain with error."""
        out_of_bounds = [-1E-6, 1E12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_derivative_gain(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_integral_gain_gets_gain(self):
        """Test get integral gain."""
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}KI%s" % expected_gain, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}KI?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_gain = self.instr.get_integral_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_integral_gain_with_persist_sets_gain(self):
        """Test set integral gain with persist."""
        gain = 1.3
        persist = True
        self._scpi_mock.ask.return_value = "@"
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}KI%s\r\n" % gain),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_integral_gain(gain, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_integral_gain_sets_gain(self):
        """Test set integral gain."""
        gain = 1.3
        expected_call = f"1KI{gain}\r\n"
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_integral_gain(gain)

        self._scpi_mock.write.assert_called_once_with(expected_call)

    def test_set_integral_gain_with_error_throws_exception(self):
        """Test set integral gain with error."""
        out_of_bounds = [-1E-6, 1E12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_integral_gain(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_proportional_gain_gets_gain(self):
        """Test get proportional gain."""
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}KP%s" % expected_gain, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}KP?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_gain = self.instr.get_proportional_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_proportional_gain_with_persist_sets_gain(self):
        """Test set proportional gain with persist."""
        gain = 1.3
        persist = True
        self._scpi_mock.ask.return_value = "@"
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}KP%s\r\n" % gain),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_proportional_gain(gain, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_proportional_gain_sets_gain(self):
        """Test set proportional gain."""
        gain = 1.3
        expected_call = f"1KP{gain}\r\n"
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_proportional_gain(gain)

        self._scpi_mock.write.assert_called_once_with(expected_call)

    def test_set_proportional_gain_with_error_throws_exception(self):
        """Test set proportional gain with error."""
        out_of_bounds = [-1E-6, 1E12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_proportional_gain(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_velocity_feed_forward_gets_vff(self):
        """Test get velocity feed forward."""
        expected_vff = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@",
            f"{self.controller_address}KD%s" % expected_vff, "@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}KV?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_vff = self.instr.get_velocity_feed_forward()

        self.assertEqual(expected_vff, actual_vff)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_feed_forward_with_persist_sets_vff(self):
        """Test set velocity feed forward with persist."""
        vff = 1.3
        persist = True
        self._scpi_mock.ask.return_value = "@"
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}KV%s\r\n" % vff),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_velocity_feed_forward(vff, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_feed_forward_sets_vff(self):
        """Test set velocity feed forward."""
        vff = 1.3
        expected_call = f"1KV{vff}\r\n"
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_velocity_feed_forward(vff)

        self._scpi_mock.write.assert_called_once_with(expected_call)

    def test_set_velocity_feed_forward_with_error_throws_exception(self):
        """Test set velocity feed forward with error."""
        out_of_bounds = [-1E-6, 1E12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_velocity_feed_forward(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_control_loop_state(self):
        """Test getting control loop state."""
        expected_state = 1
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}SC %s" % expected_state, "@"]
        expected_calls = [
            call(f"{self.controller_address}SC?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_type = self.instr.get_control_loop_state()
        self.assertEqual(actual_type, expected_state)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_control_loop_state(self):
        """Test setting control loop state."""
        loop_state = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_control_loop_state(loop_state)

        self._scpi_mock.write.assert_called_once_with(f"1SC{loop_state}\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_set_control_loop_state_excepts(self):
        """Test setting control loop state excepts with type out-of-range."""
        loop_state = 2
        self._scpi_mock.ask.return_value = "@"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_control_loop_state(loop_state)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()
