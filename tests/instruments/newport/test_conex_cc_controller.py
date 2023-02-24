"""Unit tests for Newport CONEX-CC controller."""
import logging
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.newport.actuators import TRA12CC
from qmi.instruments.newport.conex_cc_controller import Newport_ConexCC_Controller


class TestCONEXCCController(unittest.TestCase):

    TRANSPORT_STR = "/dev/cu.usbserial-FT5TMFGL"

    def setUp(self):
        qmi.start("TestConexContext", console_loglevel="CRITICAL")
        # Add patches
        patcher = patch('qmi.instruments.newport.conex_cc_controller.create_transport', spec=QMI_TcpTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.newport.conex_cc_controller.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUTs
        self.instr: Newport_ConexCC_Controller = qmi.make_instrument("CONEXCCControllerA", Newport_ConexCC_Controller, self.TRANSPORT_STR, TRA12CC)
        self.instr = cast(Newport_ConexCC_Controller, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_reset(self):
        """Test reset."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.reset()

        self._scpi_mock.write.assert_called_once_with("1RS\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_get_revision_info(self):
        """Test get revision info."""
        self._scpi_mock.ask.side_effect = ["1VE CONEX-CC 2.0.1", "@"]
        expected_calls = [
            call("1VE\r\n"),
            call("1TE\r\n")
        ]
        info = self.instr.get_revision_info()
        self.assertEqual(info.vendor, "Newport")
        self.assertEqual(info.version, "2.0.1")
        self.assertEqual(info.serial, "FT5TMFGL")
        self.assertEqual(info.model, "CONEX-CC")

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_positioner_error_and_state(self):
        """Test positioner error and state."""
        self._scpi_mock.ask.return_value = "1TS00001E"
        err_and_state = self.instr.get_positioner_error_and_state()

        self.assertEqual(err_and_state[1], "HOMING.")
        self.assertEqual(len(err_and_state[0]), 0)
        self._scpi_mock.ask.assert_called_once_with("1TS\r\n")

    def test_home_search(self):
        """Test home search."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.home_search()

        self._scpi_mock.write.assert_called_once_with("1OR\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_move_absolute_more_than_max(self):
        """Test move absolute more than max."""
        self._scpi_mock.ask.return_value = "@"
        
        with self.assertRaises(QMI_InstrumentException):
            self.instr.move_absolute(1000000)

        self._scpi_mock.write.assert_not_called()

    def test_move_absolute_less_than_min(self):
        """Test move absolute less than min."""
        self._scpi_mock.ask.return_value = "@"
        
        with self.assertRaises(QMI_InstrumentException):
            self.instr.move_absolute(0.0000000001)

        self._scpi_mock.write.assert_not_called()

    def test_move_absolute(self):
        """Test move absolute."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_absolute(pos)

        self._scpi_mock.write.assert_called_once_with("1PA%s\r\n" % pos)
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_get_position(self):
        """Test get position."""
        expected_pos = 1.2345
        self._scpi_mock.ask.side_effect = ["1TP %s" % expected_pos, "@"]
        expected_calls = [
            call("1TP\r\n"),
            call("1TE\r\n")
        ]
        actual_pos = self.instr.get_position()
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_encoder_increment_value(self):
        """Test get encoder increment value."""
        expected_encoder_increment_value = 1.2345
        self._scpi_mock.ask.side_effect = ["1SU %s" % expected_encoder_increment_value, "@"]
        expected_calls = [
            call("1SU?\r\n"),
            call("1TE\r\n")
        ]
        actual_encoder_increment_value = self.instr.get_encoder_increment_value()
        self.assertEqual(actual_encoder_increment_value, expected_encoder_increment_value)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_move_relative(self):
        """Test move relative."""
        pos = 1
        self._scpi_mock.ask.return_value = "@"
        self.instr.move_relative(pos)

        self._scpi_mock.write.assert_called_once_with("1PR%s\r\n" % pos)
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_enter_configuration_state(self):
        """Test enter configuration state."""
        self._scpi_mock.ask.return_value = "@"
        self.instr.enter_configuration_state()

        self._scpi_mock.write.assert_called_once_with("1PW1\r\n")
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_exit_configuration_state(self):
        """Test enter configuration state."""
        self.instr.exit_configuration_state()

        self._scpi_mock.write.assert_called_once_with("1PW0\r\n")

    def test_get_home_search_timeout(self):
        """Test get home search timeout."""
        expected_timeout = 10
        self._scpi_mock.ask.side_effect = ["1OT%s" % expected_timeout, "@"]
        expected_calls = [
            call("1OT?\r\n"),
            call("1TE\r\n")
        ]
        actual_timeout = self.instr.get_home_search_timeout()

        self.assertEqual(expected_timeout, actual_timeout)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_home_search_timeout_with_error(self):
        """Test get home search timeout with error."""
        expected_timeout = 10
        self._scpi_mock.ask.side_effect = ["1OT%s" % expected_timeout, "C", "1TBD: Command not allowed"]
        expected_calls = [
            call("1OT?\r\n"),
            call("1TE\r\n"),
            call("1TBC\r\n")
        ]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_home_search_timeout()

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_get_error_no_error(self):
        """Test get error with no error."""
        expected_error_code = "@"
        expected_error_message = "No error"
        self._scpi_mock.ask.return_value =  expected_error_code

        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_get_error_with_error(self):
        """Test get error with an error."""
        expected_error_code = "C"
        expected_error_message = "Parameter missing or out of range"
        self._scpi_mock.ask.side_effect = [expected_error_code, "Error: " + expected_error_message]
        expected_calls = [
            call("1TE\r\n"),
            call("1TB%s\r\n" % expected_error_code)
        ]
        actual_error = self.instr.get_error()

        self.assertEqual(actual_error[0], expected_error_code)
        self.assertEqual(actual_error[1], expected_error_message)

        self._scpi_mock.ask.assert_has_calls(expected_calls)

    def test_setup_encoder_resolution(self):
        """Test setup encoder resolution."""
        resolution = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("1RS\r\n"),
            call("1PW1\r\n"),
            call("1SU%s\r\n"%resolution),
            call("1PW0\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1TE\r\n")
        ]
        self.instr.setup_encoder_resolution(resolution)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_setup_home_search_timeout(self):
        """Test setup home search timeout."""
        timeout = 13
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("1RS\r\n"),
            call("1PW1\r\n"),
            call("1OT%s\r\n"%timeout),
            call("1PW0\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1TE\r\n")
        ]
        self.instr.setup_home_search_timeout(timeout)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_encoder_unit(self):
        """Test get encoder unit."""
        expected_encoder_unit = 10
        encoder_resolution = TRA12CC.ENCODER_RESOLUTION
        self._scpi_mock.ask.side_effect = ["@", "1SU %s" % (encoder_resolution / expected_encoder_unit), "@"]
        expected_write_calls = [
            call("1PW1\r\n"),
            call("1PW0\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1SU?\r\n"),
            call("1TE\r\n")
        ]
        actual_encoder_unit = self.instr.get_encoder_unit()
        self.assertEqual(expected_encoder_unit, actual_encoder_unit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_more_than_max(self):
        """Test set velocity more than max."""
        self._scpi_mock.ask.return_value = "@"
        
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_velocity(1000000)

        self._scpi_mock.write.assert_not_called()

    def test_set_velocity_less_than_min(self):
        """Test set velocity less than min."""
        self._scpi_mock.ask.return_value = "@"
        
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_velocity(0.0000000001)

        self._scpi_mock.write.assert_not_called()

    def test_set_velocity(self):
        """Test set velocity."""
        vel = 0.01
        self._scpi_mock.ask.return_value = "@"
        self.instr.set_velocity(vel)

        self._scpi_mock.write.assert_called_once_with("1VA%s\r\n" % vel)
        self._scpi_mock.ask.assert_called_once_with("1TE\r\n")

    def test_get_velocity(self):
        """Test get velocity."""
        expected_pos = 1.5
        self._scpi_mock.ask.side_effect = ["@", "1VA %s" % expected_pos, "@"]
        expected_write_calls = [
            call("1PW1\r\n"),
            call("1PW0\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1VA?\r\n"),
            call("1TE\r\n")
        ]
        actual_pos = self.instr.get_velocity()
        self.assertEqual(actual_pos, expected_pos)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_setup_velocity(self):
        """Test setup velocity."""
        vel = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("1RS\r\n"),
            call("1PW1\r\n"),
            call("1VA%s\r\n"%vel),
            call("1PW0\r\n")
        ]
        expected_ask_calls = [
            call("1TE\r\n"),
            call("1TE\r\n"),
            call("1TE\r\n")
        ]
        self.instr.setup_velocity(vel)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)


if __name__ == '__main__':
    unittest.main()
