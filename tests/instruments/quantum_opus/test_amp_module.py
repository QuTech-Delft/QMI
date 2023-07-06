"""Testcases of Quantum opus AmpSim Module instrument"""
import unittest
from unittest.mock import call, MagicMock

import qmi
from qmi.instruments.stanford_research_systems import Srs_Sim900
from qmi.instruments.quantum_opus import QuantumOpus_QoAmpSim
from qmi.core.exceptions import QMI_UsageException, QMI_InstrumentException


class TestAmpSimModule(unittest.TestCase):
    """Testcase of Quantum opus AmpSim Module instrument"""

    def setUp(self):
        qmi.start("test_quantum_opus_ampsim900")
        self._sim900 = MagicMock(spec=Srs_Sim900)
        self._port = 6
        self.amp_sim_module = qmi.make_instrument("QOAmpSim", QuantumOpus_QoAmpSim, self._sim900, self._port)

    def tearDown(self):
        qmi.stop()

    def test_get_module_id(self):
        # arrange
        port = 6
        expected_value = 'howdyhi'
        self._sim900.ask_module.return_value = expected_value
        expected_calls = [
            call.ask_module(port, "+A?")
            ]
        # act
        bias_current = self.amp_sim_module .get_module_id()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(bias_current, expected_value)

    def test_get_device_bias_current(self):
        # arrange
        self._sim900.ask_module.return_value = '60000'
        expected_calls = [
            call.ask_module(self._port, "+B?")
            ]
        # act
        self.amp_sim_module.get_device_bias_current()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)

    def test_set_device_bias_current(self):
        # arrange
        bias_current = 19000
        # act
        self.amp_sim_module.set_device_bias_current(bias_current)
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(6, '+B19000;')
        
    def test_set_device_bias_current_raise_out_of_range(self):
        with self.assertRaises(QMI_UsageException):
            self.amp_sim_module.set_device_bias_current(-1)
        with self.assertRaises(QMI_UsageException):
            self.amp_sim_module.set_device_bias_current(70000)

    def test_set_adc_low_gain_mode(self):
        # act
        self.amp_sim_module.set_adc_low_gain_mode()
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+C1;')

    def test_set_adc_high_gain_mode(self):
        # act
        self.amp_sim_module.set_adc_high_gain_mode()
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+C0;')

    def test_get_device_voltage(self):
        # arrange
        self._sim900.ask_module.return_value = '60000'
        expected_calls = [
            call.ask_module(self._port, "+C?")
            ]
        # act
        result = self.amp_sim_module.get_device_voltage()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(result, 60000)

    def test_set_reset_event_duration(self):
        # arrange
        event_duration = 10
        # act
        self.amp_sim_module.set_reset_event_duration(event_duration)
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(6, '+D10;')

    def test_set_reset_event_duration_out_of_range(self):
        with self.assertRaises(QMI_UsageException):
            self.amp_sim_module.set_reset_event_duration(-1)
        with self.assertRaises(QMI_UsageException):
            self.amp_sim_module.set_reset_event_duration(256)

    def test_get_reset_event_duration(self):
        # arrange
        self._sim900.ask_module.return_value = '10'
        expected_calls = [
            call.ask_module(self._port, "+D?")
            ]
        # act
        result = self.amp_sim_module.get_reset_event_duration()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(result, 10)

    def test_set_auto_reset_enabled(self):
        # act
        self.amp_sim_module.set_auto_reset_enabled(True)
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+E1;')

    def test_set_auto_reset_disabled(self):
        # act
        self.amp_sim_module.set_auto_reset_enabled(False)
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+E0;')

    def test_get_auto_reset_enabled(self):
        # arrange
        self._sim900.ask_module.return_value = '1'
        expected_calls = [
            call.ask_module(self._port, "+E?")
            ]
        # act
        result = self.amp_sim_module.get_auto_reset_enabled()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(result, True)

    def test_get_auto_reset_disabled(self):
        # arrange
        self._sim900.ask_module.return_value = '0'
        expected_calls = [
            call.ask_module(self._port, "+E?")
            ]
        # act
        result = self.amp_sim_module.get_auto_reset_enabled()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(result, False)

    def test_initiate_reset_event(self):
        # act
        self.amp_sim_module.initiate_reset_event()
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+F;')

    def test_initiate_auto_bias_function(self):
        # act
        self.amp_sim_module.initiate_auto_bias_function()
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+G;')

    def test_store_bias_current_in_non_volatile_memory(self):
        # act
        self.amp_sim_module.store_bias_current_in_non_volatile_memory(60000)
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+H60000;')

    def test_store_bias_current_in_non_volatile_memory_raise_out_of_range(self):
        with self.assertRaises(QMI_UsageException):
            self.amp_sim_module.store_bias_current_in_non_volatile_memory(-1)
        with self.assertRaises(QMI_UsageException):
            self.amp_sim_module.store_bias_current_in_non_volatile_memory(70000)

    def test_get_bias_current_from_non_volatile_memory(self):
        # arrange
        self._sim900.ask_module.return_value = '19000,0\n'
        expected_calls = [
            call.ask_module(self._port, "+H?;")
            ]
        # act
        bias_current = self.amp_sim_module.get_bias_current_from_non_volatile_memory()
        # assert
        self.assertEqual(self._sim900.method_calls, expected_calls)
        self.assertEqual(bias_current, 19000)

    def test_get_bias_current_from_non_volatile_memory_expect_raise(self):
        # arrange
        self._sim900.ask_module.return_value = '-19000'
        # act
        # assert
        with(self.assertRaises(QMI_InstrumentException)):
            self.amp_sim_module.get_bias_current_from_non_volatile_memory()

    def test_use_device_bias_from_non_volatile_memory(self):
        # act
        self.amp_sim_module.use_device_bias_from_non_volatile_memory()
        # assert
        self._sim900.send_terminated_message.assert_called_once_with(self._port, '+H;')
