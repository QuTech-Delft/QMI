"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.newport import Newport_Smc100Cc, ControlLoopState
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
        Newport_Smc100Cc.PW0_EXEC_TIME = 0.1
        Newport_Smc100Cc.COMMAND_EXEC_TIME = 0.01
        self.instr: Newport_Smc100Cc = qmi.make_instrument(
            "sam_controller", Newport_Smc100Cc, self.TRANSPORT_STR, "FT5TMFGL",
            {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
            90210)
        self.instr = cast(Newport_Smc100Cc, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_set_encoder_increment_sets_increment(self):
        """Test set encoder increment."""
        state = "14"  # Set to CONFIGURATION state to go to _enter_configuration_state.
        increment = 0.004
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}SU{increment}\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]

        self.instr.set_encoder_increment_value(increment)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_encoder_increment_with_controller_address_sets_increment(self):
        """Test set encoder increment with controller address."""
        state = "14"  # Set to CONFIGURATION state to go to _enter_configuration_state.
        increment = 0.004
        controller_address = 3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{controller_address}TS\r\n"),
            call(f"{controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{controller_address}SU{increment}\r\n"),
            call(f"{controller_address}PW0\r\n")
        ]

        self.instr.set_encoder_increment_value(increment, controller_address)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_encoder_increment_value_gets_value(self):
        """Test get encoder increment value."""
        state = "14"  # Set to CONFIGURATION state to go to _enter_configuration_state.
        encoder_resolution = TRA12CC.ENCODER_RESOLUTION
        expected_encoder_unit = 10
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}SU %s" % (encoder_resolution / expected_encoder_unit), "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SU?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_encoder_unit = self.instr.get_encoder_increment_value()

        self.assertEqual(expected_encoder_unit, actual_encoder_unit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_driver_voltage(self):
        """Test getting driver voltage."""
        state = "14"  # Set to CONFIGURATION state to go to _enter_configuration_state.
        expected_value = 24
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}DV %i" % expected_value, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_value = self.instr.get_driver_voltage()

        self.assertEqual(actual_value, expected_value)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_driver_voltage(self):
        """Test setting driver voltage."""
        state = "14"  # Set to CONFIGURATION state to go to _enter_configuration_state.
        driver_voltage = 24
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"1DV{driver_voltage}\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]

        self.instr.set_driver_voltage(driver_voltage)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_frequency = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}FD%s" % expected_frequency, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}FD?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_frequency = self.instr.get_low_pass_filter_cutoff_frequency()

        self.assertEqual(expected_frequency, actual_frequency)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_low_pass_filter_cutoff_frequency_gets_frequency_in_configuration(self):
        """Test get low pass filter cutoff frequency in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state to exit through config_state exit.
        expected_frequency = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}FD%s" % expected_frequency, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}FD?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_frequency = self.instr.get_low_pass_filter_cutoff_frequency()

        self.assertEqual(expected_frequency, actual_frequency)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_low_pass_filter_cutoff_frequency_with_persist_sets_frequency(self):
        """Test set low pass filter cutoff frequency with persist."""
        state = "14"  # Set to CONFIGURATION state to get the shortest path.
        frequency = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}FD{frequency}\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_low_pass_filter_cutoff_frequency(frequency, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_low_pass_filter_cutoff_frequency_sets_frequency(self):
        """Test set low pass filter cutoff frequency."""
        state = "3C"  # Set to DISABLE state to get the shortest path.
        frequency = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}FD{frequency}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_low_pass_filter_cutoff_frequency(frequency)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_limit = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}FE%s" % expected_limit, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}FE?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_limit = self.instr.get_following_error_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_following_error_limit_gets_limit_in_configuration(self):
        """Test get following error limit gets limit in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state to exit through config_state exit.
        expected_limit = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}FE%s" % expected_limit, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}FE?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_limit = self.instr.get_following_error_limit()

        self.assertEqual(expected_limit, actual_limit)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_following_error_limit_with_persist_sets_limit(self):
        """Test set following error limit with persist."""
        state = "14"  # Set to CONFIGURATION state to get the shortest path.
        limit = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}FE{limit}\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_following_error_limit(limit, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_following_error_limit_sets_limit(self):
        """Test set following error limit."""
        state = "3C"  # Set to DISABLE state to get the shortest path.
        limit = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}FE{limit}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_following_error_limit(limit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_compensation = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}FF %s" % expected_compensation, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}FF?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_compensation = self.instr.get_friction_compensation()

        self.assertEqual(expected_compensation, actual_compensation)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_friction_compensation_gets_compensation_in_configuration(self):
        """Test get friction compensation gets value in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state to get the config_state exit.
        expected_compensation = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}FF %s" % expected_compensation, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}FF?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_compensation = self.instr.get_friction_compensation()

        self.assertEqual(expected_compensation, actual_compensation)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_with_persist_sets_compensation(self):
        """Test set friction compensation with persist."""
        state = "14"  # Set to CONFIGURATION state.
        driver_voltage = 100.0
        compensation = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}DV {driver_voltage}", "@", "@"
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}FF{compensation}\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_friction_compensation(compensation, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_sets_compensation(self):
        """Test set friction compensation."""
        state = "3C"  # Set to DISABLE state.
        compensation = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}FF{compensation}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_friction_compensation(compensation)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_sets_compensation_from_ready(self):
        """Test set friction compensation sets compensation from READY state."""
        state = "32"  # Set to READY state.
        compensation = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM1\r\n"),
            call(f"{self.controller_address}FF{compensation}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_friction_compensation(compensation)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_friction_compensation_throws_exception(self):
        """Test set friction compensation with error on input value being out-of-range."""
        state = "14"  # Set to CONFIGURATION state directly.
        persist = True  # We can do this only in persist mode
        expected_exceptions = [
            "Provided value %.3f not in valid range 0 <= friction_compensation < %.1f.",
            "Provided value %.1f not in valid range 0 <= friction_compensation < %.1f."
        ]
        driver_voltage = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}DV {driver_voltage}", "@",
            f"1TS0000{state}", f"{self.controller_address}DV {driver_voltage}", "@"
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}DV?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]

        out_of_bounds = [-0.001, driver_voltage]
        for e, value in enumerate(out_of_bounds):
            with self.assertRaises(QMI_InstrumentException) as exc:
                self.instr.set_friction_compensation(value, persist)

            self.assertEqual(expected_exceptions[e] % (value, driver_voltage), str(exc.exception))

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_derivative_gain_gets_gain(self):
        """Test get derivative gain."""
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}KD%s" % expected_gain, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KD?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_gain = self.instr.get_derivative_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_derivative_gain_with_persist_sets_gain(self):
        """Test set derivative gain with persist."""
        state = "14"  # Set to CONFIGRATION state.
        gain = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KD%s\r\n" % gain),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_derivative_gain(gain, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_derivative_gain_sets_gain(self):
        """Test set derivative gain."""
        state = "3C"  # Set to DISABLE state to get the shortest path.
        gain = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KD{gain}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_derivative_gain(gain)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_derivative_gain_sets_gain_from_ready(self):
        """Test set derivative gain sets gain also from READY state."""
        state = "34"  # Set to READY state.
        gain = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM1\r\n"),
            call(f"{self.controller_address}KD{gain}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_derivative_gain(gain)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}KI %s" % expected_gain, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KI?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_gain = self.instr.get_integral_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_integral_gain_gets_gain_in_configuration(self):
        """Test get integral gain gets gain in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state to exit through config_state exit.
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}KI %s" % expected_gain, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KI?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_gain = self.instr.get_integral_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_integral_gain_with_persist_sets_gain(self):
        """Test set integral gain with persist."""
        state = "14"  # Set to CONFIGURATION state.
        gain = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KI%s\r\n" % gain),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_integral_gain(gain, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_integral_gain_sets_gain(self):
        """Test set integral gain."""
        state = "3C"  # Set to DISABLE state.
        gain = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KI%s\r\n" % gain),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_integral_gain(gain)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}KP %s" % expected_gain, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KP?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_gain = self.instr.get_proportional_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_proportional_gain_gets_gain_in_configuration(self):
        """Test get proportional gain in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state.
        expected_gain = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}KP %s" % expected_gain, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KP?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_gain = self.instr.get_proportional_gain()

        self.assertEqual(expected_gain, actual_gain)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_proportional_gain_with_persist_sets_gain(self):
        """Test set proportional gain with persist."""
        state = "14"  # Set to CONFIGURATION state.
        gain = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KP{gain}\r\n"),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_proportional_gain(gain, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_proportional_gain_sets_gain(self):
        """Test set proportional gain."""
        state = "3C"  # Set to DISABLE state.
        gain = 1.3
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KP{gain}\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_proportional_gain(gain)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_vff = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}KV%s" % expected_vff, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KV?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_vff = self.instr.get_velocity_feed_forward()

        self.assertEqual(expected_vff, actual_vff)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_velocity_feed_forward_gets_vff_in_configuration(self):
        """Test get velocity feed forward in CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state.
        expected_vff = 1.0
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}KV%s" % expected_vff, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}KV?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_vff = self.instr.get_velocity_feed_forward()

        self.assertEqual(expected_vff, actual_vff)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_feed_forward_with_persist_sets_vff(self):
        """Test set velocity feed forward with persist."""
        state = "14"  # Set to CONFIGURATION state.
        vff = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KV%s\r\n" % vff),
            call(f"{self.controller_address}PW0\r\n"),
        ]

        self.instr.set_velocity_feed_forward(vff, persist)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_velocity_feed_forward_sets_vff(self):
        """Test set velocity feed forward."""
        state = "3C"  # Set to DISABLE state.
        vff = 1.3
        persist = True
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}KV%s\r\n" % vff),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        self.instr.set_velocity_feed_forward(vff)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

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
        state = "3C"  # Set to DISABLE state to get the shortest path.
        expected_state = 1
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"{self.controller_address}SC %s" % expected_state, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SC?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_state = self.instr.get_control_loop_state()
        self.assertEqual(actual_state, ControlLoopState(expected_state))

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_state_configuration_or_disable_check_from_ready(self):
        """Test getting a controller config state from READY state."""
        state = "34"  # Set to READY state
        response = "0"  # Give a valid response
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", "@", f"{self.controller_address}SC %s" % response, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}SC?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}MM1\r\n"),
            call(f"{self.controller_address}MM0\r\n"),
        ]

        actual_state = self.instr.get_control_loop_state()
        self.assertEqual(actual_state, ControlLoopState(int(response)))

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_state_configuration_or_disable_check_from_configuration(self):
        """Test getting a controller config state from CONFIGURATION state."""
        state = "14"  # Set to CONFIGURATION state to go to _enter_configuration_state.
        expected_state = 1
        self._scpi_mock.ask.side_effect = [
            f"1TS0000{state}", f"1TS0000{state}", f"{self.controller_address}SC %s" % expected_state, "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}SC?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        expected_write_calls = [
            call(f"{self.controller_address}PW0\r\n"),
        ]

        actual_state = self.instr.get_control_loop_state()
        self.assertEqual(actual_state, ControlLoopState(expected_state))

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_control_loop_state(self):
        """Test setting control loop state."""
        state = "3C"  # Set to DISABLE state to get the shortest path.
        loop_state = 1
        self._scpi_mock.ask.side_effect = [f"1TS0000{state}", "@"]
        expected_ask_calls = [
            call(f"{self.controller_address}TS\r\n"),
            call(f"{self.controller_address}TE\r\n"),
        ]
        expected_write_calls = [
            call(f"{self.controller_address}SC{loop_state}\r\n"),
            call(f"{self.controller_address}MM0\r\n")
        ]

        self.instr.set_control_loop_state(loop_state)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_control_loop_state_excepts(self):
        """Test setting control loop state excepts with type out-of-range."""
        loop_state = 2
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_control_loop_state(loop_state)

        self._scpi_mock.write.assert_not_called()
        self._scpi_mock.ask.assert_not_called()
