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
from qmi.instruments.newport.single_axis_motion_controller import Newport_SingleAxisMotionController


class TestDerivingClassCase(unittest.TestCase):
    """Test that the creation of child classes of Newport_Single_Axis_Motion_Controller work as expected."""

    def setUp(self):
        # Add patches
        patcher = patch(
            "qmi.instruments.newport.single_axis_motion_controller.create_transport", spec=QMI_TcpTransport
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("qmi.instruments.newport.single_axis_motion_controller.ScpiProtocol", autospec=True)
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
                "pp_controller", Newport_Smc100Pp, "Beverly_Hills", "FT5TMFGL", {1: UTS100PP}, 90210
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
                "sam_controller",
                Newport_Smc100Cc,
                "Beverly_Hills",
                "FT5TMFGL",
                {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
                90210,
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
                "sam_controller",
                Newport_ConexCc,
                "Beverly_Hills",
                "FT5TMFGL",
                {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
                90210,
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
            "qmi.instruments.newport.single_axis_motion_controller.create_transport", spec=QMI_TcpTransport
        )
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch("qmi.instruments.newport.single_axis_motion_controller.ScpiProtocol", autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUTs
        self.controller_address = 1
        Newport_SingleAxisMotionController.PW0_EXEC_TIME = 0.1
        Newport_SingleAxisMotionController.COMMAND_EXEC_TIME = 0.01
        self.instr: Newport_SingleAxisMotionController = qmi.make_instrument(
            "sam_controller",
            Newport_SingleAxisMotionController,
            self.TRANSPORT_STR,
            "FT5TMFGL",
            {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
            90210,
        )
        self.instr = cast(Newport_SingleAxisMotionController, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_reset_without_controller_address_resets(self):
        """Test reset."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.reset()

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}RS\r\n")
        self._scpi_mock.ask.assert_called_once_with(f"{self.controller_address}TE\r\n")

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
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}VE CONEX-CC 2.0.1", "@"]
        expected_calls = [call(f"{self.controller_address}VE\r\n"), call(f"{self.controller_address}TE\r\n")]
        info = self.instr.get_idn()
        self.assertEqual(info.vendor, "Newport")
        self.assertEqual(info.version, "2.0.1")
        self.assertEqual(info.serial, "FT5TMFGL")
        self.assertEqual(info.model, "CONEX-CC")

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_stage_identifier(self):
        """Test get stage identifier."""
        state = "14"  # Only need to exit from CONFIGURATION mode.
        expected_identifier = "URS100CC"
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{expected_identifier}", "@"]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}ID?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        idn = self.instr.get_stage_identifier()
        self.assertEqual(idn, expected_identifier)

        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)

    def test_get_positioner_error_and_state_gets_positioner_error_and_state(self):
        """Test positioner error and state."""
        self._scpi_mock.ask.return_value = f"{self.controller_address}TS00001E"
        err_and_state = self.instr.get_positioner_error_and_state()

        self.assertEqual(err_and_state[1], "HOMING.")
        self.assertEqual(len(err_and_state[0]), 0)
        self._scpi_mock.ask.assert_called_once_with(f"{self.controller_address}TS\r\n")

    def test_get_positioner_error_and_state_with_an_error_bit(self):
        """Test positioner error gets added to 'errors' and returned, with state."""
        expected_errors = [
            Newport_SingleAxisMotionController.POSITIONER_ERROR_TABLE[9],
            Newport_SingleAxisMotionController.POSITIONER_ERROR_TABLE[12],
            Newport_SingleAxisMotionController.POSITIONER_ERROR_TABLE[13],
        ]
        self._scpi_mock.ask.return_value = f"{self.controller_address}TS004C1E"
        errors, state = self.instr.get_positioner_error_and_state()

        self.assertEqual(state, "HOMING.")
        self.assertListEqual(expected_errors, errors)
        self._scpi_mock.ask.assert_called_once_with(f"{self.controller_address}TS\r\n")

    def test_home_search_homes(self):
        """Test home search."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.home_search()

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}OR\r\n")
        self._scpi_mock.ask.assert_called_once_with(f"{self.controller_address}TE\r\n")

    def test_set_home_search_timeout_sets_timeout(self):
        """Test set home search timeout."""
        state = "14"  # Only need to exit from CONFIGURATION mode.
        timeout = 13
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}OT%s\r\n" % timeout),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        self.instr.set_home_search_timeout(timeout)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_home_search_timeout_with_default_timeout_sets_timeout(self):
        """Test set home search timeout with controller address."""
        timeout = Newport_SingleAxisMotionController.DEFAULT_HOME_SEARCH_TIMEOUT
        state = "14"  # Only need to exit from CONFIGURATION mode.
        self._scpi_mock.ask.side_effect = [f"3TS0000{state}", "@", "@"]
        expected_write_calls = [call(f"3OT{timeout}\r\n"), call("3PW0\r\n")]
        expected_ask_calls = [call("3TS\r\n"), call("3TE\r\n")]
        self.instr.set_home_search_timeout(controller_address=3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_home_search_timeout_gets_timeout(self):
        """Test get home search timeout."""
        expected_timeout = 10
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}OT%s" % expected_timeout, "@"]
        expected_calls = [call(f"{self.controller_address}OT?\r\n"), call(f"{self.controller_address}TE\r\n")]
        actual_timeout = self.instr.get_home_search_timeout()

        self.assertEqual(expected_timeout, actual_timeout)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_home_search_timeout_with_error_throws_exception(self):
        """Test get home search timeout with error."""
        expected_timeout = 10
        expected_error = ["Error", "C", ": Command not allowed"]
        self._scpi_mock.ask.side_effect = [
            f"{self.controller_address}OT%s" % expected_timeout,
            expected_error[1],
            f"{self.controller_address}TBD{expected_error[2]}",
        ]
        expected_calls = [
            call(f"{self.controller_address}OT?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TBC\r\n"),
        ]
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.get_home_search_timeout()

        self._scpi_mock.ask.assert_has_calls(expected_calls)
        self.assertEqual(str(exc.exception), expected_error[0] + f" {expected_error[1]}" + expected_error[2])

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
            self.instr.move_absolute(-1)

        self._scpi_mock.write.assert_not_called()

    def test_move_absolute_moves(self):
        """Test move absolute."""
        state = "32"  # Moves only in "READY" state
        pos = 1
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_absolute(pos)

        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)
        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}PA%s\r\n" % pos)

    def test_move_absolute_excepts_as_not_in_ready_state(self):
        """Test move absolute."""
        state = "3C"  # Moves only in "READY" state
        pos = 1
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n")]
        self._scpi_mock.ask.return_value = "@"
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.move_absolute(pos)

        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)
        self._scpi_mock.write.assert_not_called()

    def test_get_setpoint_gets_setpoint(self):
        """Test get setpoint."""
        expected_sp = 1.2345
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}TH %s" % expected_sp, "@"]
        expected_calls = [call(f"{self.controller_address}TH\r\n"), call(f"{self.controller_address}TE\r\n")]
        actual_sp = self.instr.get_setpoint()
        self.assertEqual(actual_sp, expected_sp)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_position_gets_position(self):
        """Test get position."""
        expected_pos = 1.2345
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}TP %s" % expected_pos, "@"]
        expected_calls = [call(f"{self.controller_address}TP\r\n"), call(f"{self.controller_address}TE\r\n")]
        actual_pos = self.instr.get_position()
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_move_relative_with_negative_displacement_moves(self):
        """Test move relative with negative displacement and controller address."""
        state = "34"  # READY
        pos = -0.1
        self._scpi_mock.ask.side_effect = [f"3TS0000{state}", "@"]
        self.instr.move_relative(pos, 3)

        self._scpi_mock.write.assert_called_once_with(f"3PR{pos}\r\n")
        self._scpi_mock.ask.assert_any_call("3TE\r\n")

    def test_move_relative_moves(self):
        """Test move relative with controller address."""
        state = "34"  # READY
        pos = 1
        self._scpi_mock.ask.side_effect = [f"3TS0000{state}", "@"]
        self.instr.move_relative(pos, 3)

        self._scpi_mock.write.assert_called_once_with(f"3PR{pos}\r\n")
        self._scpi_mock.ask.assert_any_call("3TE\r\n")

    def test_move_relative_excepts(self):
        """Test move relative excepts if controller not in READY state."""
        state = "3C"  # DISABLE
        pos = 1
        self._scpi_mock.ask.side_effect = [f"2TS0000{state}"]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.move_relative(pos, 2)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_any_call("2TS\r\n")

    def test_move_relative_less_than_min_throws_exception(self):
        """Test move relative less than min."""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.move_relative(0.0000000001)

        self._scpi_mock.write.assert_not_called()

    def test_get_motion_time(self):
        """Test get motion time."""
        displacement = 3.21
        expected_time = 1.23
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}PT %s" % expected_time, "@"]
        expected_calls = [
            call(f"{self.controller_address}PT{displacement}\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_time = self.instr.get_motion_time(displacement)
        self.assertEqual(actual_time, expected_time)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_configuration_state_sets_configuration_state(self):
        """Test set configuration state."""
        self.instr.set_configuration_state(True)

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}PW1\r\n")
        self._scpi_mock.ask.assert_not_called()

        self._scpi_mock.write.reset_mock()
        self._scpi_mock.ask.reset_mock()

        self.instr.set_configuration_state(False)

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}PW0\r\n")
        self._scpi_mock.ask.assert_not_called()

    def test_get_configuration_state_gets_configuration_state(self):
        """Test get configuration state with controller address."""
        contr_addr = 3
        expected_state = False
        self._scpi_mock.ask.side_effect = [f"{contr_addr}PW{int(expected_state)}", "@"]

        state = self.instr.is_in_configuration_state(controller_address=contr_addr)

        self.assertEqual(state, expected_state)
        self._scpi_mock.ask.assert_any_call(f"{contr_addr}PW?\r\n")
        self._scpi_mock.ask.assert_any_call(f"{contr_addr}TE\r\n")

    def test_set_disable_state_sets_disable_state(self):
        """Test set disable state."""
        self._scpi_mock.ask.return_value = "@"
        # 1. Test setting state to DISABLE
        self.instr.set_disable_state(True)

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}MM1\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

        # Test setting state to READY
        self._scpi_mock.write.reset_mock()
        self._scpi_mock.ask.reset_mock()
        self.instr.set_disable_state(False)

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}MM0\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_get_disable_state_gets_disable_state(self):
        """Test get disable state with controller address."""
        contr_addr = 2
        expected_state = False
        self._scpi_mock.ask.side_effect = [f"{contr_addr}MM{int(expected_state)}", "@"]

        state = self.instr.is_in_disable_state(controller_address=contr_addr)

        self.assertEqual(state, expected_state)
        self._scpi_mock.ask.assert_any_call(f"{contr_addr}MM?\r\n")
        self._scpi_mock.ask.assert_any_call(f"{contr_addr}TE\r\n")

    def test_get_error_with_no_error_gets_error(self):
        """Test get error with no error."""
        expected_error_code = "@"
        expected_error_message = "No error"
        self._scpi_mock.ask.return_value = expected_error_code

        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_called_once_with(f"{self.controller_address}TE\r\n")

    def test_get_error_with_error_gets_error(self):
        """Test get error with an error."""
        expected_error_code = "C"
        expected_error_message = "Parameter missing or out of range"
        self._scpi_mock.ask.side_effect = [expected_error_code, "Error: " + expected_error_message]
        expected_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TB%s\r\n" % expected_error_code),
        ]
        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_acceleration_gets_acceleration_in_READY_state(self):
        """Test get acceleration in READY state."""
        state = "32"
        expected_acc = 1.5
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}AC %s" % expected_acc, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}AC?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_acc = self.instr.get_acceleration()
        self.assertEqual(actual_acc, expected_acc)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_acceleration_gets_acceleration_in_CONFIGURATION_state(self):
        """Test get acceleration in CONFIGURATION state."""
        state = "14"  # Only need to exit from CONFIGURATION mode.
        expected_acc = 1.5
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            f"1TS0000{state}",
            f"{self.controller_address}AC %s" % expected_acc,
            "@",
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}AC?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_acc = self.instr.get_acceleration()
        self.assertEqual(actual_acc, expected_acc)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_acceleration_with_persist_sets_acceleration(self):
        """Test set acceleration with persist = True."""
        state = "33"
        expected_acc = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}AC{expected_acc}\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        self.instr.set_acceleration(expected_acc, True)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_acceleration_without_persist_sets_acceleration(self):
        """Test set acceleration without persisting, i.e. without entering the configuration state."""
        state = "33"
        expected_acc = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}AC{expected_acc}\r\n"),
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        self.instr.set_acceleration(expected_acc)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_acceleration_outside_bounds_throws_exception(self):
        """Test set acceleration outisde of allowed range raise exception."""
        self._scpi_mock.ask.return_value = "@"
        out_of_bounds = [1e-6, 1e12]

        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_acceleration(value)

        self._scpi_mock.write.assert_not_called()

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
        state = "34"  # Set to READY state to take the shortest path
        expected_vel = 1.5
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}VA %s" % expected_vel, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}VA?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]

        actual_vel = self.instr.get_velocity()

        self.assertEqual(actual_vel, expected_vel)
        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_velocity_gets_velocity_in_configuration(self):
        """Test get velocity in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state.
        expected_vel = 1.5
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            f"1TS0000{state}",
            f"{self.controller_address}VA %s" % expected_vel,
            "@",
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}VA?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_vel = self.instr.get_velocity()
        self.assertEqual(actual_vel, expected_vel)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_with_persist_sets_velocity(self):
        """Test set velocity with persisting the velocity."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        vel = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}VA%s\r\n" % vel),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        self.instr.set_velocity(vel, True)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_without_persist_sets_velocity(self):
        """Test set velocity without persisting, i.e. without entering the configuration state."""
        state = "33"
        vel = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}VA{vel}\r\n"),
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        self.instr.set_velocity(vel)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_jerk_time_gets_jerk_time(self):
        """Test get jerk_time."""
        state = "34"  # READY state
        expected_jerk = 1.5
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}JR %s" % expected_jerk, "@"]
        expected_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}JR?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_jerk = self.instr.get_jerk_time()
        self.assertEqual(actual_jerk, expected_jerk)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_jerk_time_gets_jerk_time_in_configuration(self):
        """Test get jerk_time in CONFIGURATION state."""
        state = "14"  # CONFIGURATION state
        expected_jerk = 1.5
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            f"1TS0000{state}",
            f"{self.controller_address}JR %s" % expected_jerk,
            "@",
        ]
        expected_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}JR?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_jerk = self.instr.get_jerk_time()
        self.assertEqual(actual_jerk, expected_jerk)

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}PW0\r\n")
        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_jerk_time_with_persist_sets_jerk_time(self):
        """Test set jerk_time with persist = True."""
        state = "14"  # CONFIGURATION state
        jerk = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}JR{jerk}\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        self.instr.set_jerk_time(jerk, True)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_jerk_time_without_persist_sets_jerk_time(self):
        """Test set jerk_time without persisting, i.e. without entering the configuration state."""
        state = "34"  # READY state
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        jerk = 0.004
        self._scpi_mock.ask.return_value = "@"
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]

        self.instr.set_jerk_time(jerk)

        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}JR{jerk}\r\n")
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_jerk_time_outside_bounds_throws_exception(self):
        """Test set jerk_time outisde of allowed range raise exception."""
        self._scpi_mock.ask.return_value = "@"
        out_of_bounds = [0.001, 1e12]

        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_jerk_time(value)

        self._scpi_mock.write.assert_not_called()

    def test_stop_motion_stops_motion(self):
        """Test stop motion."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.stop_motion(3)

        self._scpi_mock.write.assert_called_once_with("3ST\r\n")
        self._scpi_mock.ask.assert_called_once_with("3TE\r\n")

    def test_set_backlash_compensation_sets_compensation(self):
        """Test set backlash compensation with controller address."""
        state = "14"  # CONFIGURATION state
        hyst_comp = 0.0
        comp = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"3BH %s" % hyst_comp, "@", "@"]
        expected_ask_calls = [call(f"3TS\r\n"), call(f"3BH?\r\n"), call(f"3TE\r\n"), call(f"3TE\r\n")]
        expected_write_calls = [call(f"3BA{comp}\r\n"), call(f"3PW0\r\n")]
        self.instr.set_backlash_compensation(comp, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_backlash_compensation_excepts_because_hysteresis_compensation(self):
        """Test set backlash compensation exits because hysteresis compensation is enabled."""
        state = "32"  # Will call reset to get into CONFIGURATION state
        hyst_comp = 0.1
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", f"{self.controller_address}BH %s" % hyst_comp, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}BH?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        comp = 0.004
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_backlash_compensation(comp)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_backlash_compensation_gets_compensation(self):
        """Test get backlash compensation."""
        state = "32"  # Will call reset to get into CONFIGURATION state
        expected_compensation = 10
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            "@",
            f"{self.controller_address}BA %s" % expected_compensation,
            "@",
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}BA?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        actual_comp = self.instr.get_backlash_compensation()
        self.assertEqual(expected_compensation, actual_comp)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_hysteresis_compensation_sets_compensation(self):
        """Test set hysteresis compensation with controller address."""
        state = "14"  # CONFIGURATION state
        back_comp = 0.0
        comp = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"3BA %s" % back_comp, "@", "@"]
        expected_ask_calls = [call(f"3TS\r\n"), call(f"3BA?\r\n"), call(f"3TE\r\n"), call(f"3TE\r\n")]
        expected_write_calls = [call(f"3BH{comp}\r\n"), call(f"3PW0\r\n")]
        self.instr.set_hysteresis_compensation(comp, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_hysteresis_compensation_excepts_because_backlash_compensation(self):
        """Test set hysteresis compensation exits because backlash compensation is enabled."""
        state = "32"  # Will call reset to get into CONFIGURATION state
        back_comp = 0.1
        comp = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", f"{self.controller_address}BA %s" % back_comp, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}BA?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_hysteresis_compensation(comp)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_hysteresis_compensation_gets_compensation(self):
        """Test get hysteresis compensation."""
        state = "0A"  # in NOT REFERENCED state, no reset needed
        expected_compensation = 10
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            "@",
            f"{self.controller_address}BH %s" % expected_compensation,
            "@",
        ]
        expected_write_calls = [call(f"{self.controller_address}PW1\r\n"), call(f"{self.controller_address}PW0\r\n")]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}BH?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_comp = self.instr.get_hysteresis_compensation()
        self.assertEqual(expected_compensation, actual_comp)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_home_search_type(self):
        """Test getting home search type."""
        state = "14"  # CONFIGURATION state
        expected_type = 2
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}HT %s" % expected_type, "@"]
        expected_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}HT?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_type = self.instr.get_home_search_type()
        self.assertEqual(actual_type, expected_type)

        self._scpi_mock.ask.assert_has_calls(expected_calls)
        self._scpi_mock.write.assert_called_once_with(f"{self.controller_address}PW0\r\n")

    def test_set_home_search_type(self):
        """Test setting home search type."""
        state = "14"  # CONFIGURATION state
        home_type = 1
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]

        self.instr.set_home_search_type(home_type)

        self._scpi_mock.write.assert_any_call(f"1HT{home_type}\r\n")
        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_home_search_type_excepts(self):
        """Test setting home search type excepts with type out-of-range."""
        home_type = 5
        self._scpi_mock.ask.return_value = "@"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_home_search_type(home_type)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_peak_current_limit_gets_limit(self):
        """Test get peak current limit."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        expected_limit = 1.0
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}QIL %s" % expected_limit, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}QIL?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_limit = self.instr.get_peak_current_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_peak_current_limit_sets_limit(self):
        """Test set peak current limit."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        limit = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}QIL%s\r\n" % limit),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_peak_current_limit(limit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_peak_current_limit_with_error_throws_exception(self):
        """Test set peak current limit with error."""
        out_of_bounds = [0.04999, 3.0001]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_peak_current_limit(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_rms_current_limit_gets_limit(self):
        """Test get rms current limit."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        expected_rms = 10
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}QIR %s" % expected_rms, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}QIR?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_rms = self.instr.get_rms_current_limit()
        self.assertEqual(expected_rms, actual_rms)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_rms_current_limit_sets_limit(self):
        """Test set rms current limit with controller address."""
        state = "0A"  # Set to NOT REFERENCED state
        peak = 2.0
        rms = 0.05
        controller_address = 2
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", f"{controller_address}QIL{peak}", "@", "@"]
        expected_write_calls = [
            call(f"{controller_address}PW1\r\n"),
            call(f"{controller_address}QIR{rms}\r\n"),
            call(f"{controller_address}PW0\r\n"),
        ]
        expected_ask_calls = [
            call(f"{controller_address}TS\r\n"),
            call(f"{controller_address}TE\r\n"),
            call(f"{controller_address}QIL?\r\n"),
            call(f"{controller_address}TE\r\n"),
            call(f"{controller_address}TE\r\n"),
        ]
        self.instr.set_rms_current_limit(rms, controller_address)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_rms_current_limit_sets_limit_under_peak_limit(self):
        """Test set rms current limit works also with lower peak limit."""
        state = "0A"  # Set to NOT REFERENCED state to take the shortest path
        peak = 2.0
        rms = 0.05
        controller_address = 2
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", f"{controller_address}QIL{peak}", "@", "@"]
        expected_write_calls = [call("1PW1\r\n"), call(f"1QIR{rms}\r\n"), call("1PW0\r\n")]
        expected_ask_calls = [call("1TS\r\n"), call("1TE\r\n"), call("1QIL?\r\n"), call("1TE\r\n"), call("1TE\r\n")]
        self.instr.set_rms_current_limit(rms)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_rms_current_limit_excepts_because_peak_limit(self):
        """Test set rms current limit exits because peak limit is lower."""
        state = "0A"  # Set to NOT REFERENCED state
        peak = 1.0
        rms = 1.1
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", f"1QIL{peak}", "@", "@"]
        expected_write_calls = [call("1PW1\r\n"), call("1PW0\r\n")]
        expected_ask_calls = [call("1TS\r\n"), call("1TE\r\n"), call("1QIL?\r\n"), call("1TE\r\n")]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_rms_current_limit(rms)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_rms_current_averaging_time_gets_time(self):
        """Test get rms current averaging time."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        expected_time = 10
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}QIT %s" % expected_time, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}QIT?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_time = self.instr.get_rms_current_averaging_time()

        self.assertEqual(expected_time, actual_time)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_rms_current_averaging_time_sets_time(self):
        """Test set rms current averaging time."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        time = 13
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}QIT%i\r\n" % time),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_rms_current_averaging_time(time)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_rms_current_averaging_time_with_error_throws_exception(self):
        """Test set rms current averaging time with error."""
        out_of_bounds = [0.01, 101]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_rms_current_averaging_time(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_analog_input_value(self):
        """Test getting analog input value."""
        expected_value = 2.0
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}RA %f" % expected_value, "@"]
        expected_calls = [call(f"{self.controller_address}RA\r\n"), call(f"{self.controller_address}TE\r\n")]
        actual_value = self.instr.get_analog_input_value()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_ttl_input_value(self):
        """Test getting ttl input value."""
        expected_value = 5
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}RB %i" % expected_value, "@"]
        expected_calls = [call(f"{self.controller_address}RB\r\n"), call(f"{self.controller_address}TE\r\n")]
        actual_value = self.instr.get_ttl_input_value()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_ttl_output_value(self):
        """Test getting ttl output value."""
        expected_value = 3
        self._scpi_mock.ask.side_effect = [f"{self.controller_address}SB %i" % expected_value, "@"]
        expected_calls = [call(f"{self.controller_address}SB?\r\n"), call(f"{self.controller_address}TE\r\n")]
        actual_value = self.instr.get_ttl_output_value()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_set_ttl_output_value(self):
        """Test setting ttl output value."""
        ttl_output = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_ttl_output_value(ttl_output)

        self._scpi_mock.write.assert_called_once_with(f"1SB{ttl_output}\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_set_ttl_output_value_excepts(self):
        """Test setting ttl output value excepts when value out of valid range."""
        ttl_output_invalid = [-1, 16]
        for value in ttl_output_invalid:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_ttl_output_value(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_controller_rs485_address(self):
        """Test getting controller rs485 address."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        expected_value = 2
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}SA %s" % expected_value, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SA?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_value = self.instr.get_controller_rs485_address()
        self.assertEqual(actual_value, expected_value)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_controller_rs485_address(self):
        """Test setting ttl output value."""
        state = "14"  # Set to CONFIGURATION state to take the shortest path
        controller_rs485_address = 30
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}SA%i\r\n" % controller_rs485_address),
            call(f"{self.controller_address}PW0\r\n"),
        ]
        self.instr.set_controller_rs485_address(controller_rs485_address)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_controller_rs485_address_excepts(self):
        """Test setting ttl output value excepts when value out of valid range."""
        rs485_address_invalid = [1, 32]
        for value in rs485_address_invalid:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_controller_rs485_address(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_negative_software_limit_gets_limit(self):
        """Test get negative software limit."""
        state = "3C"  # Set to DISABLE state to take the shortest path
        expected_limit = -1.0
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}SL %s" % expected_limit, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SL?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_limit = self.instr.get_negative_software_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_negative_software_limit_gets_limit_in_configuration(self):
        """Test get negative software limit in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION
        expected_limit = -1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            f"1TS0000{state}",
            f"{self.controller_address}SL %s" % expected_limit,
            "@",
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SL?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_limit = self.instr.get_negative_software_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_negative_software_limit_without_persist_sets_limit(self):
        """Test set negative software limit without persist."""
        state = "34"  # Set to READY state
        limit = -1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}SL%s\r\n" % limit),
        ]

        self.instr.set_negative_software_limit(limit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_negative_software_limit_with_persist_sets_limit(self):
        """Test set negative software limit with persist."""
        state = "14"  # Set to CONFIGURATION state
        limit = -1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}SL%s\r\n" % limit),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_negative_software_limit(limit, True)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_negative_software_limit_with_error_throws_exception(self):
        """Test set negative software limit with error."""
        out_of_bounds = [0.0001, 1e-12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_negative_software_limit(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()

    def test_get_positive_software_limit_gets_limit(self):
        """Test get positive software limit."""
        state = "3C"  # Set to DISABLE state
        expected_limit = 1.0
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", f"{self.controller_address}SR %s" % expected_limit, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SR?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        actual_limit = self.instr.get_positive_software_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_positive_software_limit_gets_limit_in_configuration(self):
        """Test get positive software limit in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state
        expected_limit = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}",
            f"1TS0000{state}",
            f"{self.controller_address}SR %s" % expected_limit,
            "@",
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SR?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [call(f"{self.controller_address}PW0\r\n")]
        actual_limit = self.instr.get_positive_software_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_positive_software_limit_without_persist_sets_limit(self):
        """Test set positive software limit without persist."""
        state = "34"  # Set to READY state
        limit = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}SR%s\r\n" % limit),
        ]

        self.instr.set_positive_software_limit(limit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_positive_software_limit_with_persist_sets_limit(self):
        """Test set positive software limit with persist."""
        state = "14"  # Set to CONFIGURATION state
        limit = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [call(f"{self.controller_address}TS\r\n"), call(f"{self.controller_address}TE\r\n")]
        expected_write_calls = [
            call(f"{self.controller_address}SR%s\r\n" % limit),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_positive_software_limit(limit, True)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_positive_software_limit_with_error_throws_exception(self):
        """Test set positive software limit with error."""
        out_of_bounds = [-0.0001, 1e12]
        for value in out_of_bounds:
            with self.assertRaises(QMI_InstrumentException):
                self.instr.set_positive_software_limit(value)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()
