"""Testcases of SIM922 temperature sensor."""
import unittest
from unittest.mock import call, MagicMock

import qmi
from qmi.instruments.stanford_research_systems import Srs_Sim900
from qmi.instruments.stanford_research_systems import Srs_Sim922
from qmi.core.exceptions import QMI_UsageException, QMI_InstrumentException


class TestSIM922(unittest.TestCase):
    """Testcase of SIM922 temperature sensor."""

    def setUp(self):
        qmi.start("test_siglent_sim922")
        self._sim900 = MagicMock(spec=Srs_Sim900)
        self._port = 1
        self._channel = 2
        self.sim922 = qmi.make_instrument("SIM922", Srs_Sim922, self._sim900, self._port)

    def tearDown(self):
        qmi.stop()

    def test_get_id(self):
        # arrange
        expected_id_string = "test_string"
        expected_calls = [
            call.ask_module(self._port, "*IDN?")
        ]
        self._sim900.ask_module.return_value = expected_id_string
        # act
        actual_id_string = self.sim922.get_id()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(actual_id_string, expected_id_string)

    def test_get_voltage(self):
        # arrange
        expected_voltage_string = "1.108054E+00"
        expected_voltage = 1.108054E+00
        expected_calls = [
            call.ask_module(self._port, f"VOLT? {self._channel}")
        ]
        self._sim900.ask_module.return_value = expected_voltage_string
        # act
        actual_voltage = self.sim922.get_voltage(self._channel)
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(actual_voltage, expected_voltage)

    def test_get_voltage_channel_out_of_bounds(self):
        with self.assertRaises(QMI_UsageException):
            self.sim922.get_voltage(0)
        with self.assertRaises(QMI_UsageException):
            self.sim922.get_voltage(5)

    def test_get_voltage_wrong_voltage(self):
        # arrange
        self._sim900.ask_module.return_value = ""
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            self.sim922.get_voltage(1)

    def test_get_temperature(self):
        # arrange
        expected_temperature_string = "2.299000E+00"
        expected_temperature = 2.299000E+00
        expected_calls = [
            call.ask_module(self._port, f"TVAL? {self._channel}")
        ]
        self._sim900.ask_module.return_value = expected_temperature_string
        # act
        actual_temperature = self.sim922.get_temperature(self._channel)
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(actual_temperature, expected_temperature)

    def test_get_temperature_channel_out_of_bounds(self):
        with self.assertRaises(QMI_UsageException):
            self.sim922.get_temperature(0)
        with self.assertRaises(QMI_UsageException):
            self.sim922.get_temperature(5)

    def test_get_temperature_wrong_temperature(self):
        # arrange
        self._sim900.ask_module.return_value = ""
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            self.sim922.get_temperature(self._channel)

    def test_is_excited_(self):
        expected_excitation_list = [('1', True), ('ON', True), ('0', False), ('OFF', False)]
        for expected_excitation in expected_excitation_list:
            self._sim900.ask_module.return_value = expected_excitation[0]
            with self.subTest(i=expected_excitation[0]):
                self.assertEqual(self.sim922.is_excited(self._channel), expected_excitation[1])

    def test_set_excitation(self):
        expected_call_list = [
            (True, [call.send_terminated_message(self._port, f"EXON {self._channel},ON")]),
            (False, [call.send_terminated_message(self._port, f"EXON {self._channel},OFF")])
        ]
        for expected_call in expected_call_list:
            self._sim900.reset_mock()
            self.sim922.set_excitation(self._channel, current_on=expected_call[0])
            with self.subTest(i=expected_call[0]):
                self.assertEqual(self._sim900.method_calls, expected_call[1])

    def test_set_excitation_not_bool(self):
        with self.assertRaises(QMI_UsageException):
            self.sim922.set_excitation(self._channel, current_on=None)


if __name__ == '___main___':
    unittest.main()
