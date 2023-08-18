"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.utils.context_managers import start_stop
from qmi.instruments.newport import Newport_Smc100Pp, Newport_Smc100Cc, Newport_ConexCc
from qmi.instruments.newport.actuators import TRA12CC, TRB6CC, CMA25CCL, UTS100PP
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

    def test_smc100pp(self):
        """
        Test SMC100PP
        """
        expected_rpc_class = "qmi.instruments.newport.smc_100pp.Newport_SMC100PP"
        with start_stop(qmi, "TestSMC100PP", console_loglevel="CRITICAL"):
            # Make DUT
            self.instr: Newport_Smc100Pp = qmi.make_instrument(
                "pp_controller", Newport_Smc100Pp, "Beverly_Hills", "FT5TMFGL",
                {1: UTS100PP}, 90210
            )
            # Test __init__ is of correct module
            self.assertIn(expected_rpc_class, str(self.instr.__init__))

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

    def test_get_idn_address_gets_idn(self):
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

    def test_get_positioner_error_and_state_gets_positioner_error_and_state(self):
        """Test positioner error and state."""
        self._scpi_mock.ask.return_value = f"{self.controller_address}TS00001E"
        err_and_state = self.instr.get_positioner_error_and_state()

        self.assertEqual(err_and_state[1], "HOMING.")
        self.assertEqual(len(err_and_state[0]), 0)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TS\r\n")

    def test_home_search_homes(self):
        """Test home search."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.home_search()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}OR\r\n")
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    # def test_set_home_search_timeout(self):
    #     """Test setting home search timeout."""
    #     self._scpi_mock.ask.return_value = "@"
    #     self.instr.set_home_search_timeout(3.0)
    #
    #     self._scpi_mock.write.assert_called_once_with("1OT3.0\r\n")
    #     self._scpi_mock.ask.assert_called_once_with("1TE\r\n")
    #
    # def test_set_home_search_timeout_default(self):
    #     """Test setting home search timeout."""
    #     default_timeout = Newport_Single_Axis_Motion_Controller.DEFAULT_HOME_SEARCH_TIMEOUT
    #     self._scpi_mock.ask.return_value = "@"
    #     self.instr.set_home_search_timeout()
    #
    #     self._scpi_mock.write.assert_called_once_with(f"1OT{default_timeout}\r\n")
    #     self._scpi_mock.ask.assert_called_once_with("1TE\r\n")
    #
    def test_set_home_search_timeout_sets_timeout(self):
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

    def test_set_home_search_timeout_with_default_timeout_sets_timeout(self):
        """Test set home search timeout with controller address."""
        timeout = Newport_Single_Axis_Motion_Controller.DEFAULT_HOME_SEARCH_TIMEOUT
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
        self.instr.set_home_search_timeout(controller_address=3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_home_search_timeout_gets_timeout(self):
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

    def test_move_absolute_moves(self):
        """Test move absolute."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_absolute(pos)

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}PA%s\r\n" % pos)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_get_position_gets_position(self):
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

    def test_move_relative_moves(self):
        """Test move relative with controller address."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_relative(pos, 3)

        self._scpi_mock.write.assert_called_once_with(f"3PR{pos}\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_enter_configuration_state_enters_configuration_state(self):
        """Test enter configuration state."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.enter_configuration_state()

        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}PW1\r\n")
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_exit_configuration_state_exists_configuration_state(self):
        """Test enter configuration state with controller address."""
        self.instr.exit_configuration_state(3)

        self._scpi_mock.write.assert_called_once_with("3PW0\r\n")

    def test_get_error_with_no_error_gets_error(self):
        """Test get error with no error."""
        expected_error_code = "@"
        expected_error_message = "No error"
        self._scpi_mock.ask.return_value = expected_error_code

        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

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

    def test_get_velocity_gets_velocity(self):
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

    def test_set_velocity_with_persist_sets_velocity(self):
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

    def test_set_velocity_without_persist_sets_velocity(self):
        """Test set velocity without persisting, i.e. without entering the configuration state."""
        vel = 0.004
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_velocity(vel)
        self._scpi_mock.write.assert_called_once_with(
            f"{self.controller_address}VA%s\r\n" % vel)
        self._scpi_mock.ask.assert_called_once_with(
            f"{self.controller_address}TE\r\n")

    def test_stop_motion_stops_motion(self):
        """Test stop motion."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.stop_motion(3)

        self._scpi_mock.write.assert_called_once_with("3ST\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_set_backlash_compensation_sets_compensation(self):
        """Test set backlash compensation with controller address."""
        comp = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "3BH0", "@", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call(f"3BA{comp}\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3TE\r\n"),
            call("3BH?\r\n"),
            call("3TE\r\n"),
            call("3TE\r\n")
        ]
        self.instr.set_backlash_compensation(comp, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_backlash_compensation_gets_compensation(self):
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
