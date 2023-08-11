"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.utils.context_managers import start_stop
from qmi.instruments.newport import Newport_Smc100Cc, Newport_ConexCc
from qmi.instruments.newport.actuators import TRA12CC, TRB6CC, CMA25CCL
from qmi.instruments.newport.single_axis_motion_controller import Newport_Single_Axis_Motion_Controller


class TestDerivingClassCase(unittest.TestCase):
    """Test that the creation of child classes of Newport_Single_Axis_Motion_Controller work as expected."""

    def setUp(self):
        # Add patches
        patcher = patch(
            'qmi.instruments.newport.single_axis_motion_controller.create_transport', spec=QMI_TcpTransport)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch(
            'qmi.instruments.newport.single_axis_motion_controller.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_smc100cc(self):
        """
        Test SMC100CC
        """
        expected_rpc_class = "qmi.instruments.newport.smc_100cc.Newport_SMC100CC"
        with start_stop(qmi, "TestSMC100CC", console_loglevel="CRITICAL"):
            # Make DUT
            self.instr: Newport_Smc100Cc = qmi.make_instrument(
                "sam_controller", Newport_Smc100Cc, "Beverly_Hills", "FT5TMFGL",
                {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL}, 90210
            )
            # Test __init__ is of correct module
            self.assertIn(expected_rpc_class, str(self.instr.__init__))

    def test_conex_cc(self):
        """
        Test Conex CC
        """
        expected_rpc_class = "qmi.instruments.newport.conex_cc.Newport_ConexCC"
        with start_stop(qmi, "TestConexCC", console_loglevel="CRITICAL"):
            # Make DUT
            self.instr: Newport_ConexCc = qmi.make_instrument(
                "sam_controller", Newport_ConexCc, "Beverly_Hills", "FT5TMFGL",
                {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL}, 90210
            )
            # Test __init__ is of correct module
            self.assertIn(expected_rpc_class, str(self.instr.__init__))


class TestSingleAxisMotionController(unittest.TestCase):
    """
    Tests for the single axis motion controller.
    """

    TRANSPORT_STR = "/dev/cu.usbserial-FT5TMFGL"

    def setUp(self):
        qmi.start("TestSamControllerContext", console_loglevel="CRITICAL")
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
        self.instr: Newport_Single_Axis_Motion_Controller = qmi.make_instrument(
            "sam_controller", Newport_Single_Axis_Motion_Controller, self.TRANSPORT_STR, "FT5TMFGL",
            {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
            90210)
        self.instr = cast(Newport_Single_Axis_Motion_Controller, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_reset_without_controller_address_resets(self):
        """Test reset."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.reset()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}RS\r\n")
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_reset_with_controller_address_resets(self):
        """Test reset with controller address."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.reset(3)

        self._scpi_mock.write.assert_called_once_with("3RS\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_build_command_with_invalid_controller_address_throws_exception(self):
        """Test build command with invalid controller address."""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.reset(4)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_idn_without_controller_address_gets_idn(self):
        """Test get idn."""
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}VE CONEX-CC 2.0.1", "@"]
        expected_calls = [
            call(f"{self.controller_address}VE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        info = self.instr.get_idn()
        self.assertEqual(info.vendor, "Newport")
        self.assertEqual(info.version, "2.0.1")
        self.assertEqual(info.serial, "FT5TMFGL")
        self.assertEqual(info.model, "CONEX-CC")

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_idn_with_controller_address_gets_idn(self):
        """Test get idn with controller_address."""
        self._scpi_mock.ask.side_effect = ["3VE CONEX-CC 2.0.1", "@"]
        expected_calls = [
            call("3VE\r\n"),
            call("3TE\r\n")
        ]
        info = self.instr.get_idn(3)
        self.assertEqual(info.vendor, "Newport")
        self.assertEqual(info.version, "2.0.1")
        self.assertEqual(info.serial, "FT5TMFGL")
        self.assertEqual(info.model, "CONEX-CC")

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_positioner_error_and_state_without_controller_address_gets_positioner_error_and_state(self):
        """Test positioner error and state."""
        self._scpi_mock.ask.return_value = f"{self.controller_address}TS00001E"
        err_and_state = self.instr.get_positioner_error_and_state()

        self.assertEqual(err_and_state[1], "HOMING.")
        self.assertEqual(len(err_and_state[0]), 0)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TS\r\n")

    def test_get_positioner_error_and_state_with_controller_address_gets_positioner_error_and_state(self):
        """Test positioner error and state with controller address."""
        self._scpi_mock.ask.return_value = f"{self.controller_address}TS00001E"
        err_and_state = self.instr.get_positioner_error_and_state(3)

        self.assertEqual(err_and_state[1], "HOMING.")
        self.assertEqual(len(err_and_state[0]), 0)
        self._scpi_mock.ask.assert_called_once_with("3TS\r\n")

    def test_home_search_without_controller_address_homes(self):
        """Test home search."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.home_search()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}OR\r\n")
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_home_search_with_controller_address_homes(self):
        """Test home search with controller address."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.home_search(3)

        self._scpi_mock.write.assert_called_once_with("3OR\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_move_absolute_more_than_max_thrown_exception(self):
        """Test move absolute more than max."""
        self._scpi_mock.ask.return_value = "@"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.move_absolute(1000000)

        self._scpi_mock.write.assert_not_called()

    def test_move_absolute_less_than_min_throws_exception(self):
        """Test move absolute less than min."""
        self._scpi_mock.ask.return_value = "@"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.move_absolute(0.0000000001)

        self._scpi_mock.write.assert_not_called()

    def test_move_absolute_without_controller_address_moves(self):
        """Test move absolute."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_absolute(pos)

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}PA%s\r\n" % pos)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_move_absolute_with_controller_address_moves(self):
        """Test move absolute with controller address."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_absolute(pos, 3)

        self._scpi_mock.write.assert_called_once_with(f"3PA{pos}\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_get_position_without_controller_address_gets_position(self):
        """Test get position."""
        expected_pos = 1.2345
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}TP %s" % expected_pos, "@"]
        expected_calls = [
            call(f"{self.controller_address}TP\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_pos = self.instr.get_position()
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_position_with_controller_address_gets_position(self):
        """Test get position with controller address."""
        expected_pos = 1.2345
        self._scpi_mock.ask.side_effect = [f"3TP {expected_pos}", "@"]
        expected_calls = [
            call("3TP\r\n"),
            call("3TE\r\n")
        ]
        actual_pos = self.instr.get_position(3)
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_move_relative_without_controller_address_moves(self):
        """Test move relative."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_relative(pos)

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}PR%s\r\n" % pos)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_move_relative_with_controller_address_moves(self):
        """Test move relative with controller address."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_relative(pos, 3)

        self._scpi_mock.write.assert_called_once_with(f"3PR{pos}\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_enter_configuration_state_without_controller_address_enters_configuration_state(self):
        """Test enter configuration state."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.enter_configuration_state()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}PW1\r\n")
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_enter_configuration_state_with_controller_address_enters_configuration_state(self):
        """Test enter configuration state with controller address."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.enter_configuration_state(3)

        self._scpi_mock.write.assert_called_once_with("3PW1\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_exit_configuration_state_without_controller_address_exists_configuration_state(self):
        """Test enter configuration state."""
        self.instr.exit_configuration_state()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}PW0\r\n")

    def test_exit_configuration_state_with_controller_address_exists_configuration_state(self):
        """Test enter configuration state with controller address."""
        self.instr.exit_configuration_state(3)

        self._scpi_mock.write.assert_called_once_with("3PW0\r\n")

    def test_get_home_search_timeout_without_controller_address_gets_timeout(self):
        """Test get home search timeout."""
        expected_timeout = 10
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}OT%s" % expected_timeout, "@"]
        expected_calls = [
            call(f"{self.controller_address}OT?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_timeout = self.instr.get_home_search_timeout()

        self.assertEqual(expected_timeout, actual_timeout)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_home_search_timeout_with_controller_address_gets_timeout(self):
        """Test get home search timeout with controller address."""
        expected_timeout = 10
        self._scpi_mock.ask.side_effect = [f"3OT{expected_timeout}", "@"]
        expected_calls = [
            call("3OT?\r\n"),
            call("3TE\r\n")
        ]
        actual_timeout = self.instr.get_home_search_timeout(3)

        self.assertEqual(expected_timeout, actual_timeout)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_home_search_timeout_with_error_throws_exception(self):
        """Test get home search timeout with error."""
        expected_timeout = 10
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}OT%s" %
                                           expected_timeout, "C", f"{self.controller_address}TBD: Command not allowed"]
        expected_calls = [
            call(f"{self.controller_address}OT?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TBC\r\n")
        ]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_home_search_timeout()

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_error_with_no_error_and_without_controller_address_gets_error(self):
        """Test get error with no error."""
        expected_error_code = "@"
        expected_error_message = "No error"
        self._scpi_mock.ask.return_value = expected_error_code

        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_get_error_with_no_error_and_controller_address(self):
        """Test get error with no error with controller address."""
        expected_error_code = "@"
        expected_error_message = "No error"
        self._scpi_mock.ask.return_value = expected_error_code

        actual_error = self.instr.get_error(3)

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_get_error_with_error_gets_error(self):
        """Test get error with an error."""
        expected_error_code = "C"
        expected_error_message = "Parameter missing or out of range"
        self._scpi_mock.ask.side_effect = [
            expected_error_code, "Error: " + expected_error_message]
        expected_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TB%s\r\n" % expected_error_code)
        ]
        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

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

    def test_set_home_search_timeout_without_controller_address_sets_timeout(self):
        """Test set home search timeout."""
        timeout = 13
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}OT%s\r\n" % timeout),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_home_search_timeout(timeout)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_home_search_timeout_with_controller_address_sets_timeout(self):
        """Test set home search timeout with controller address."""
        timeout = 13
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call(f"3OT{timeout}\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3TE\r\n"),
            call("3TE\r\n")
        ]
        self.instr.set_home_search_timeout(timeout, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_encoder_increment_value_without_controller_address_gets_value(self):
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

    def test_get_encoder_increment_value_with_controller_address_gets_value(self):
        """Test get encoder increment value with controller address."""
        expected_encoder_unit = 10
        encoder_resolution = CMA25CCL.ENCODER_RESOLUTION
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"3SU {encoder_resolution / expected_encoder_unit}", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3SU?\r\n"),
            call("3TE\r\n")
        ]
        actual_encoder_unit = self.instr.get_encoder_increment_value(3)
        self.assertEqual(expected_encoder_unit, actual_encoder_unit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_more_than_max_throws_exception(self):
        """Test set velocity more than max."""
        self._scpi_mock.ask.return_value = "@"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_velocity(1000000)

        self._scpi_mock.write.assert_not_called()

    def test_set_velocity_less_than_min_throws_exception(self):
        """Test set velocity less than min."""
        self._scpi_mock.ask.return_value = "@"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_velocity(0.0000000001)

        self._scpi_mock.write.assert_not_called()

    def test_get_velocity_without_controller_address_gets_velocity(self):
        """Test get velocity."""
        expected_pos = 1.5
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"{self.controller_address}VA %s" % expected_pos, "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}VA?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_pos = self.instr.get_velocity()
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_velocity_with_controller_address_gets_velocity(self):
        """Test get velocity with controller address."""
        expected_pos = 1.5
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"3VA {expected_pos}", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3VA?\r\n"),
            call("3TE\r\n")
        ]
        actual_pos = self.instr.get_velocity(3)
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_with_persist_and_without_controller_address_sets_velocity(self):
        """Test set velocity with persisting the velocity."""
        vel = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}VA%s\r\n" % vel),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_velocity(vel, True)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_with_persist_and_controller_address_sets_velocity(self):
        """Test set velocity with persisting the velocity and providing a controller address."""
        vel = 0.1
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call(f"3VA{vel}\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3TE\r\n"),
            call("3TE\r\n")
        ]
        self.instr.set_velocity(vel, True, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_without_persist_sets_velocity(self):
        """Test set velocity without persisting, i.e. without entering the configuration state."""
        vel = 0.004
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_velocity(vel)
        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}VA%s\r\n" % vel)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_stop_motion_without_controller_address_stops_motion(self):
        """Test stop motion."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.stop_motion(3)

        self._scpi_mock.write.assert_called_once_with("3ST\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_stop_motion_with_controller_address_stops_motion(self):
        """Test stop motion with controller address."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.stop_motion()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}ST\r\n")
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_set_backlash_compensation_with_controller_address_sets_compensation(self):
        """Test set backlash compensation with controller address."""
        comp = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call(f"3BA{comp}\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3TE\r\n"),
            call("3TE\r\n")
        ]
        self.instr.set_backlash_compensation(comp, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_backlash_compensation_without_controller_address_sets_compensation(self):
        """Test set backlash compensation."""
        comp = 13
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}BA{comp}\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_backlash_compensation(comp)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_backlash_compensation_without_controller_address_gets_compensation(self):
        """Test get backlash compensation."""
        comp = 10
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"{self.controller_address}BA {comp}", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}BA?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_comp = self.instr.get_backlash_compensation()
        self.assertEqual(comp, actual_comp)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_backlash_compensation_with_controller_address_gets_compensation(self):
        """Test get backlash compensation with controller address."""
        comp = 10
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"3BA {comp}", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3BA?\r\n"),
            call("3TE\r\n")
        ]
        actual_comp = self.instr.get_backlash_compensation(3)
        self.assertEqual(comp, actual_comp)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)
