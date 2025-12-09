"""Unit-tests for Rohde&Schwarz base class."""
import logging
import unittest
from unittest.mock import call, patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.rohde_schwarz.rs_base_signal_gen import RohdeSchwarz_Base

from tests.patcher import PatcherQmiContext as QMI_Context


class TestRohdeSchwarzBase(unittest.TestCase):

    def setUp(self):
        logging.getLogger("qmi.instruments.rohde_schwarz.rs_base_signal_gen").setLevel(logging.CRITICAL)
        ctx = QMI_Context("TestRohdeSchwarzBaseContext")
        # Add patches
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher2 = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.ScpiProtocol', autospec=True)
        self._scpi_mock = patcher2.start().return_value
        self.addCleanup(patcher2.stop)
        # Make DUT
        self.instr: RohdeSchwarz_Base = RohdeSchwarz_Base(ctx, "RSB100a", "")
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        logging.getLogger("qmi.instruments.rohde_schwarz.rs_base_signal_gen").setLevel(logging.NOTSET)

    def test_get_idn(self):
        """Test ident. """
        vendor = "vendor"
        model = "model"
        serial = "serial"
        version = "version"
        self._scpi_mock.ask.return_value = f"{vendor},{model},{serial},{version}"

        ident = self.instr.get_idn()

        self._scpi_mock.ask.assert_called_once_with("*IDN?")
        self.assertEqual(ident.vendor, vendor)
        self.assertEqual(ident.model, model)
        self.assertEqual(ident.serial, serial)
        self.assertEqual(ident.version, version)

    def test_wrong_idn_response(self):
        """Test ident. raises QMI_InstrumentException by a non-sense response."""
        self._scpi_mock.ask.return_value = "nonsense"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

        self._scpi_mock.ask.assert_called_once_with("*IDN?")

    def test_get_idn_works_even_with_with_valueerror(self):
        """Test the case where the _internal_poll_calibration_finished gives ValueError."""
        resp = b"nonsense"
        self.instr._calibrating = True
        self._transport_mock.read_until.side_effect = [resp + b"\r\n"]
        self._scpi_mock.ask.return_value = "vendor,model,serial,version"

        self.instr.get_idn()

        self.assertEqual(self.instr._calibration_error, "Unexpected response to calibration command: {!r}".format(resp))

    def test_start_calibration_excepts(self):
        """Test start calibration excepts when previous calibration is still pending."""
        self._transport_mock.read_until.side_effect = [b"1\r\n"]
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.start_calibration()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.start_calibration()

    def test_check_calibrating_excepts_with_timeout(self):
        """Test the case where the internal _check_calibration call excepts."""
        self.instr._calibrating = True
        expected_exception = "Calibration in progress"
        self._transport_mock.read_until.side_effect = [QMI_TimeoutException]

        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.get_idn()

        self.assertEqual(str(exc.exception), expected_exception)

    def test_reset(self):
        """Test reset."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        expected_calls = [
            call("*CLS"),
            call("*RST")
        ]

        self.instr.reset()

        self._scpi_mock.write.assert_has_calls(expected_calls)
        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_error(self):
        """Test command with error response."""
        self._scpi_mock.ask.return_value = "1,\"Huge error\""
        expected_calls = [
            call("*CLS"),
            call("*RST")
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.reset()

        self._scpi_mock.write.assert_has_calls(expected_calls)
        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_wrong_float_value(self):
        """Test wrong float value response."""
        self._scpi_mock.ask.return_value = "not a float"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_frequency()

    def test_wrong_bool_value(self):
        """Test wrong bool value response."""
        self._scpi_mock.ask.return_value = "not a bool"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_output_state()

    def test_poll_calibration_in_progress(self):
        """Test calibration state polling."""
        # Device doesn't respond during calibration
        self._transport_mock.read_until.side_effect = QMI_TimeoutException

        self.instr._calibrating = True
        result = self.instr.poll_calibration()

        self.assertIsNone(result)

    def test_poll_calibration_not_started(self):
        """Test calibration state polling."""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.poll_calibration()

    def test_poll_calibration_result_ok(self):
        """Test calibration state polling."""
        # Calibration result.
        calibration_result = 123
        self._transport_mock.read_until.return_value = bytes(str(calibration_result).encode("ascii")) + b"\r\n"

        # Calibration state query response.
        self._scpi_mock.ask.return_value = "0,\"No error\""

        self.instr._calibrating = True
        result = self.instr.poll_calibration()

        self.assertEqual(result, calibration_result)
        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_poll_calibration_error(self):
        """Test calibration state polling."""
        logging.getLogger("qmi.instruments.rohde_schwarz.rs_base_signal_gen").setLevel(logging.ERROR)
        # Calibration result.
        calibration_result = 456
        self._transport_mock.read_until.return_value = bytes(str(calibration_result).encode("ascii")) + b"\r\n"

        # Calibration state query response.
        self._scpi_mock.ask.return_value = "1,\"Some error\""

        self.instr._calibrating = True
        with self.assertRaises(QMI_InstrumentException):
            self.instr.poll_calibration()

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_get_set_frequency(self):
        """Test get/set frequency."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_frequency()

        self._scpi_mock.ask.assert_called_once_with(":FREQ?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_frequency(target_value)

        self._scpi_mock.write.assert_called_once_with(f":FREQ {target_value}")

    def test_get_set_phase(self):
        """Test get/set phase."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_phase()

        self._scpi_mock.ask.assert_called_once_with(":PHAS?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_phase(target_value)

        self._scpi_mock.write.assert_called_once_with(f":PHAS {target_value}")

    def test_get_set_power(self):
        """Test get/set power."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_power()

        self._scpi_mock.ask.assert_called_once_with(":POW?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_power(target_value)

        self._scpi_mock.write.assert_called_once_with(f":POW {target_value}")

    def test_get_set_output_state(self):
        """Test get/set output state."""
        # Test get.
        value = "0"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_output_state()

        self._scpi_mock.ask.assert_called_once_with(":OUTP?")
        self.assertEqual(result, False)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_output_state(target_value)

            self._scpi_mock.write.assert_called_once_with(":OUTP {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_output_policy(self):
        """Test get/set output policy."""
        # Test get.
        value = "OFF"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_power_on_output_policy()

        self._scpi_mock.ask.assert_called_once_with(":OUTP:PON?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("OFF", "off", "UNCH", "unch"):
            self.instr.set_power_on_output_policy(target_value)

            self._scpi_mock.write.assert_called_once_with(f":OUTP:PON {target_value.upper()}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_power_on_output_policy("chaos")

    def test_get_set_ref_source(self):
        """Test get/set reference source."""
        # Test get.
        value = "INT"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_reference_source()

        self._scpi_mock.ask.assert_called_once_with(":ROSC:SOUR?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("INT", "int", "EXT", "ext"):
            self.instr.set_reference_source(target_value)

            self._scpi_mock.write.assert_called_once_with(f":ROSC:SOUR {target_value.upper()}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_reference_source("theoracle")

    def test_get_set_pulsemod_enable(self):
        """Test get/set pulse modulation."""
        # Test get.
        value = "0"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_pulsemod_enabled()

        self._scpi_mock.ask.assert_called_once_with(":PULM:STAT?")
        self.assertEqual(result, False)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_pulsemod_enabled(target_value)

            self._scpi_mock.write.assert_called_once_with(":PULM:STAT {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_pulsemod_ext_source(self):
        """Test get/set external pulse modulation source."""
        # Test get.
        value = "INT"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_pulsemod_ext_source()

        self._scpi_mock.ask.assert_called_once_with(":PULM:SOUR?")
        self.assertEqual(result, False)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_pulsemod_ext_source(target_value)

            self._scpi_mock.write.assert_called_once_with(":PULM:SOUR {}".format(
                "EXT" if target_value else "INT"
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_pulsemod_ext_source_excepts(self):
        """Test get external pulse modulation source excepts."""
        value = "ENT"
        self._scpi_mock.ask.return_value = value

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_pulsemod_ext_source()

    def test_get_set_pulsemod_polarity(self):
        """Test get/set pulse modulation polarity."""
        # Test get.
        value = "INV"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_pulsemod_polarity()

        self._scpi_mock.ask.assert_called_once_with(":PULM:POL?")
        self.assertEqual(result, True)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_pulsemod_polarity(target_value)

            self._scpi_mock.write.assert_called_once_with(":PULM:POL {}".format(
                "INV" if target_value else "NORM"
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_pulsemod_polarity_excepts(self):
        """Test get pulse modulation polarity excepts."""
        # Test get.
        value = "NINV"
        self._scpi_mock.ask.return_value = value

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_pulsemod_polarity()

    def test_get_set_iq_enable(self):
        """Test get/set IQ enable."""
        # Test get.
        value = "1"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_enabled()

        self._scpi_mock.ask.assert_called_once_with(":IQ:STAT?")
        self.assertEqual(result, True)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_iq_enabled(target_value)

            self._scpi_mock.write.assert_called_once_with(":IQ:STAT {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_iq_wideband(self):
        """Test get/set IQ wideband."""
        # Test get.
        value = "0"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_wideband()

        self._scpi_mock.ask.assert_called_once_with(":IQ:WBST?")
        self.assertEqual(result, False)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_iq_wideband(target_value)

            self._scpi_mock.write.assert_called_once_with(":IQ:WBST {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()

    def test_get_set_iq_crest(self):
        """Test get/set IQ crest factor."""
        # Test get.
        value = 123.345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_crest_factor()

        self._scpi_mock.ask.assert_called_once_with(":IQ:CRES?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        target_value = 456.789

        self.instr.set_iq_crest_factor(target_value)

        self._scpi_mock.write.assert_called_once_with(f":IQ:CRES {target_value}")

    def test_get_set_iq_quad_offset(self):
        """Test get/set IQ quadrature offset."""
        # Test get.
        value = 1.2345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_quadrature_offset()

        self._scpi_mock.ask.assert_called_once_with(":IQ:IMP:QUAD?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in [-8, -2, 0, 2, 8]:
            self.instr.set_iq_quadrature_offset(target_value)

            self._scpi_mock.write.assert_called_once_with(f":IQ:IMP:QUAD {target_value:.2f}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_iq_quadrature_offset(-10)

        with self.assertRaises(ValueError):
            self.instr.set_iq_quadrature_offset(10)

    def test_get_set_iq_leakage_i(self):
        """Test get/set IQ leakage."""
        # Test get.
        value = 1.2345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_leakage_i()

        self._scpi_mock.ask.assert_called_once_with(":IQ:IMP:LEAK:I?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in [-5, -2, 0, 2, 5]:
            self.instr.set_iq_leakage_i(target_value)

            self._scpi_mock.write.assert_called_once_with(f":IQ:IMP:LEAK:I {target_value:.2f}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_iq_leakage_i(-6)

        with self.assertRaises(ValueError):
            self.instr.set_iq_leakage_i(6)

    def test_get_set_iq_leakage_q(self):
        """Test get/set IQ leakage."""
        # Test get.
        value = 1.2345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_leakage_q()

        self._scpi_mock.ask.assert_called_once_with(":IQ:IMP:LEAK:Q?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in [-5, -2, 0, 2, 5]:
            self.instr.set_iq_leakage_q(target_value)

            self._scpi_mock.write.assert_called_once_with(f":IQ:IMP:LEAK:Q {target_value:.2f}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_iq_leakage_q(-6)

        with self.assertRaises(ValueError):
            self.instr.set_iq_leakage_q(6)

    def test_get_set_iq_imbalance(self):
        """Test get/set IQ imbalance."""
        # Test get.
        value = 1.2345
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_gain_imbalance()

        self._scpi_mock.ask.assert_called_once_with(":IQ:IMP:IQR:MAGN?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in [-1, -0.5, 0, 0.5, 1]:
            self.instr.set_iq_gain_imbalance(target_value)

            self._scpi_mock.write.assert_called_once_with(f":IQ:IMP:IQR:MAGN {target_value:.3f}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_iq_gain_imbalance(-2)

        with self.assertRaises(ValueError):
            self.instr.set_iq_gain_imbalance(2)

    def test_get_errors_with_no_error(self):
        """Test no errors in queue."""
        self._scpi_mock.ask.return_value = "0,\"No error\""
        self.instr.get_errors()

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_get_errors_with_errors(self):
        """Test errors in queue."""
        self._scpi_mock.ask.return_value = "1,\"Some error\""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_errors()

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:ALL?")

    def test_get_error_queue_length(self):
        """Test error queue length."""
        expected = 1
        self._scpi_mock.ask.return_value = expected
        actual = self.instr.get_error_queue_length()

        self.assertEqual(actual, expected)

        self._scpi_mock.ask.assert_called_once_with("SYST:ERR:COUN?")


class TestRohdeSchwarzBasePowerLimited(unittest.TestCase):

    def setUp(self):
        ctx = QMI_Context("TestRohdeSchwarzBasePLContext")
        # Add patches
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.ScpiProtocol', autospec=True)
        self._scpi_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.maxpower = 10  # max_continuous_power
        self.instr: RohdeSchwarz_Base = RohdeSchwarz_Base(ctx, "RSB100a", "", self.maxpower)
        self.instr.open()

    def tearDown(self):
        self.instr.close()

    def test_set_power_below_max(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "0,\"No error\""  # query to error state
        ]
        target_value = 0.5 * self.maxpower

        self.instr.set_power(target_value)

        self._scpi_mock.write.assert_called_once_with(f":POW {target_value}")

    def test_set_power_above_max_ok(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        self.instr.set_power(target_value)

        self._scpi_mock.write.assert_called_once_with(f":POW {target_value}")

    def test_set_power_above_max_fail1(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "OFF",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_power(target_value)

        self._scpi_mock.write.assert_not_called()

    def test_set_power_above_max_fail2(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "ON",  # response to query pulsemod enabled
            "INT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_power(target_value)

        self._scpi_mock.write.assert_not_called()

    def test_set_power_above_max_fail3(self):
        """Test set power with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "INV",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]
        target_value = 2 * self.maxpower

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_power(target_value)

        self._scpi_mock.write.assert_not_called()

    def test_set_output_enable_below_max(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            0.5 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_output_state(True)

        self._scpi_mock.write.assert_called_once_with(":OUTP 1")

    def test_set_output_enable_above_max_ok(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_output_state(True)

        self._scpi_mock.write.assert_called_once_with(":OUTP 1")

    def test_set_output_enable_above_max_fail1(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "OFF",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_state(True)

        self._scpi_mock.write.assert_not_called()

    def test_set_output_enable_above_max_fail2(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "ON",  # response to query pulsemod enabled
            "INT",  # response to query pulsemod ext source
            "NORM",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_state(True)

        self._scpi_mock.write.assert_not_called()

    def test_set_output_enable_above_max_fail3(self):
        """Test set output enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "ON",  # response to query pulsemod enabled
            "EXT",  # response to query pulsemod ext source
            "INV",  # response to query pulsemod polarity
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_output_state(True)

        self._scpi_mock.write.assert_not_called()

    def test_set_pulsemod_enable_below_max(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            0.5 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_enabled(False)

        self._scpi_mock.write.assert_called_once_with(":PULM:STAT 0")

    def test_set_pulsemod_enable_above_max_ok(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_enabled(True)

        self._scpi_mock.write.assert_called_once_with(":PULM:STAT 1")

    def test_set_pulsemod_enable_above_max_fail(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pulsemod_enabled(False)

        self._scpi_mock.write.assert_not_called()

    def test_set_pulsemod_ext_source_below_max(self):
        """Test set pulsemod external source with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            0.5 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_ext_source(False)

        self._scpi_mock.write.assert_called_once_with(":PULM:SOUR INT")

    def test_set_pulsemod_ext_source_above_max_ok(self):
        """Test set pulsemod external source with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_ext_source(True)

        self._scpi_mock.write.assert_called_once_with(":PULM:SOUR EXT")

    def test_set_pulsemod_ext_source_above_max_fail(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pulsemod_ext_source(False)

        self._scpi_mock.write.assert_not_called()

    def test_set_pulsemod_polarity_below_max(self):
        """Test set pulsemod polarity with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            0.5 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_polarity(True)

        self._scpi_mock.write.assert_called_once_with(":PULM:POL INV")

    def test_set_pulsemod_polarity_above_max_ok(self):
        """Test set pulsemod polarity with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            "0,\"No error\""  # query to error state
        ]

        self.instr.set_pulsemod_polarity(False)

        self._scpi_mock.write.assert_called_once_with(":PULM:POL NORM")

    def test_set_pulsemod_polarity_above_max_fail(self):
        """Test set pulsemod enable with maximum power set."""
        self._scpi_mock.ask.side_effect = [
            2 * self.maxpower,  # response to query power
            "0,\"No error\""  # query to error state
        ]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_pulsemod_polarity(True)

        self._scpi_mock.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
