"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.newport import Newport_Smc100Pp
from qmi.instruments.newport.actuators import UTS100PP


class TestNewportSmc100Pp(unittest.TestCase):
    """
    Tests for the single axis motion controller.
    """

    TRANSPORT_STR = "/dev/cu.usbserial-FT5TMFGL"

    def setUp(self):
        qmi.start("Test100PpControllerContext", console_loglevel="CRITICAL")
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
        self.instr: Newport_Smc100Pp = qmi.make_instrument(
            "sam_controller", Newport_Smc100Pp, self.TRANSPORT_STR, "FT5TMFGL",
            {1: UTS100PP},
            90210)
        self.instr = cast(Newport_Smc100Pp, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_get_micro_step_per_full_step_factor(self):
        """Test getting motor micro-step factor."""
        expected_value = 24
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}FRM %i" % expected_value, "@"]
        expected_calls = [
            call(f"{self.controller_address}FRM?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_value = self.instr.get_micro_step_per_full_step_factor()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_micro_step_per_full_step_factor(self):
        """Test setting motor micro-step factor."""
        micro_step_per_full_step_factor = 24
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_micro_step_per_full_step_factor(micro_step_per_full_step_factor)

        self._scpi_mock.write.assert_called_once_with(f"1FRM{micro_step_per_full_step_factor}\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_set_micro_step_per_full_step_factor_excepts(self):
        """Test setting motor micro-step factor excepts when value out of valid range."""
        micro_step_per_full_step_factor_invalid = [0, 2001]
        for value in micro_step_per_full_step_factor_invalid:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_micro_step_per_full_step_factor(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_motion_distance_per_full_step(self):
        """Test getting motor motion distance."""
        expected_value = 24
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}FRS %i" % expected_value, "@"]
        expected_calls = [
            call(f"{self.controller_address}FRS?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_value = self.instr.get_motion_distance_per_full_step()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_motion_distance_per_full_step(self):
        """Test setting motor motion distance."""
        motion_distance_per_full_step = 24
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_motion_distance_per_full_step(motion_distance_per_full_step)

        self._scpi_mock.write.assert_called_once_with(f"1FRS{motion_distance_per_full_step}\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_set_motion_distance_per_full_step_excepts(self):
        """Test setting motor motion distance excepts when value out of valid range."""
        motion_distance_per_full_step_invalid = [1E-6, 1E12]
        for value in motion_distance_per_full_step_invalid:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_motion_distance_per_full_step(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_base_velocity(self):
        """Test getting motor motion distance."""
        expected_value = 24
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}VB %i" % expected_value, "@"]
        expected_calls = [
            call(f"{self.controller_address}VB?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_value = self.instr.get_base_velocity()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_base_velocity(self):
        """Test setting motor motion distance."""
        base_velocity = 24
        max_vel = 1000
        self._scpi_mock.ask.side_effect = ["@", "@", f"1VA{max_vel}", "@", "@"]
        expected_write_calls = [
            call("1RS\r\n"),
            call("1PW1\r\n"),
            call("1PW0\r\n"),
            call(f"1VB{base_velocity}\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1VA?\r\n"),
            call("1TE\r\n"),
            call("1TE\r\n")
        ]
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_base_velocity(base_velocity)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_base_velocity_excepts(self):
        """Test setting motor motion distance excepts when value out of valid range."""
        max_vel = 1.0
        self._scpi_mock.ask.side_effect = ["@", "@", f"1VA{max_vel}", "@", "@", "@", f"1VA{max_vel}", "@"]
        expected_write_calls = [
            call("1RS\r\n"),
            call("1PW1\r\n"),
            call("1PW0\r\n"),
            call("1RS\r\n"),
            call("1PW1\r\n"),
            call("1PW0\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1VA?\r\n"),
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1VA?\r\n"),
            call("1TE\r\n")
        ]
        base_velocity_invalid = [-0.001, max_vel + 0.1]
        for value in base_velocity_invalid:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_base_velocity(value)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)
