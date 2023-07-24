"""Unit test for Montana Cryostation S50 driver."""

import json
import unittest
from unittest.mock import MagicMock, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException

from qmi.instruments.montana import Montana_CryostationS50
from qmi.instruments.montana.cryostation_s50 import Montana_CryostationS50_System_Goal, Montana_CryostationS50_System_State


class TestCryostation50(unittest.TestCase):

    def setUp(self):
        qmi.start("montana-s50-test-context")
        self.ip_addres = "192.168.1.1"
        self.instr: Montana_CryostationS50 = qmi.make_instrument(
            "montana_s50_test_instr", Montana_CryostationS50, self.ip_addres)
        self.instr.open()
        self.controller_properties_url = f"http://{self.ip_addres}:47101/v1/controller/properties"
        self.controller_methods_url = f"http://{self.ip_addres}:47101/v1/controller/methods"
        self.cryocooler_properties_url = f"http://{self.ip_addres}:47101/v1/cooler/cryocooler/properties"
        self.sample_chamber_properties_url = f"http://{self.ip_addres}:47101/v1/sampleChamber/temperatureControllers/platform/properties"
        self.sample_chamber_thermometer_properties_url = f"http://{self.ip_addres}:47101/v1/sampleChamber/temperatureControllers/platform/thermometer/properties"

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_open_close(self):
        self.instr.close()
        self.assertFalse(self.instr.is_open())
        self.instr.open()
        self.assertTrue(self.instr.is_open())

    @patch('urllib.request.urlopen')
    def test_get_system_goal(self, urlopen_mock: MagicMock):
        expected_system_goal = "Vent"
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"systemGoal": "{expected_system_goal}"}}', 'utf-8')

        sys_goal = self.instr.get_system_goal()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/systemGoal")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(sys_goal, Montana_CryostationS50_System_Goal.VENT)

    @patch('urllib.request.urlopen')
    def test_get_system_state(self, urlopen_mock: MagicMock):
        expected_system_state = "Ready"
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"systemState": "{expected_system_state}"}}', 'utf-8')

        sys_state = self.instr.get_system_state()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/systemState")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(sys_state, Montana_CryostationS50_System_State.READY)

    @patch('urllib.request.urlopen')
    def test_cooldown_allowed(self, urlopen_mock: MagicMock):
        expected_cooldown_allowed = "true"
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"canCooldown": "{expected_cooldown_allowed}"}}', 'utf-8')

        cooldown_allowed = self.instr.cooldown_allowed()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/canCooldown")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertTrue(cooldown_allowed)

    @patch('urllib.request.urlopen')
    def test_cooldown_allowed_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400
        with self.assertRaises(QMI_InstrumentException):
            self.instr.cooldown_allowed()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/canCooldown")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)

    @patch('urllib.request.urlopen')
    def test_warmup_allowed(self, urlopen_mock: MagicMock):
        expected_warmup_allowed = "false"
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"canWarmup": {expected_warmup_allowed}}}', 'utf-8')

        warmup_allowed = self.instr.warmup_allowed()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/canWarmup")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertFalse(warmup_allowed)

    @patch('urllib.request.urlopen')
    def test_set_platform_target_temperature(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_target_temperature(4.9)
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformTargetTemperature")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformTargetTemperature": 4.9\n}')

    @patch('urllib.request.urlopen')
    def test_set_platform_target_temperature_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_platform_target_temperature(4.9)
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformTargetTemperature")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformTargetTemperature": 4.9\n}')

    @patch('urllib.request.urlopen')
    def test_get_platform_target_temperature(self, urlopen_mock: MagicMock):
        expected_target_temp = 4.9

        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"platformTargetTemperature": {expected_target_temp}}}', 'utf-8')

        self.instr.get_platform_target_temperature()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformTargetTemperature")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)

    @patch('urllib.request.urlopen')
    def test_start_cooldown(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200
        self.instr.start_cooldown()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_methods_url}/cooldown()")
        self.assertEqual(req.method, 'POST')
        self.assertIsNone(req.data)

    @patch('urllib.request.urlopen')
    def test_start_warmup(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200
        self.instr.start_warmup()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_methods_url}/warmup()")
        self.assertEqual(req.method, 'POST')
        self.assertIsNone(req.data)

    @patch('urllib.request.urlopen')
    def test_enable_platform_bakeout(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200
        self.instr.enable_platform_bakeout()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutEnabled")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformBakeoutEnabled": true\n}')

    @patch('urllib.request.urlopen')
    def test_enable_platform_bakeout_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400

        with self.assertRaises(QMI_InstrumentException):
            self.instr.enable_platform_bakeout()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutEnabled")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformBakeoutEnabled": true\n}')

    @patch('urllib.request.urlopen')
    def test_disable_platform_bakeout(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200
        self.instr.disable_platform_bakeout()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutEnabled")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformBakeoutEnabled": false\n}')

    @patch('urllib.request.urlopen')
    def test_set_platform_bakeout_temperature(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_bakeout_temperature(312)
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTemperature")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformBakeoutTemperature": 312\n}')

    @patch('urllib.request.urlopen')
    def test_get_platform_bakeout_temperature(self, urlopen_mock: MagicMock):
        expected_bakeout_temp = 4.9

        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"platformBakeoutTemperature": {expected_bakeout_temp}}}', 'utf-8')

        bakeout_temp = self.instr.get_platform_bakeout_temperature()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTemperature")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(bakeout_temp, expected_bakeout_temp)

    @patch('urllib.request.urlopen')
    def test_get_platform_bakeout_temperature_limit(self, urlopen_mock: MagicMock):
        expected_bakeout_temp_limit = 351

        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"platformBakeoutTemperatureLimit": {expected_bakeout_temp_limit}}}', 'utf-8')

        bakeout_temp = self.instr.get_platform_bakeout_temperature_limit()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTemperatureLimit")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(bakeout_temp, expected_bakeout_temp_limit)

    @patch('urllib.request.urlopen')
    def test_get_platform_target_temperature_limit(self, urlopen_mock: MagicMock):
        expected_temp_limit = 351

        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"temperatureLimit": {expected_temp_limit}}}', 'utf-8')

        bakeout_temp = self.instr.get_platform_target_temperature_limit()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.sample_chamber_properties_url}/temperatureLimit")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(bakeout_temp, expected_temp_limit)

    @patch('urllib.request.urlopen')
    def test_set_platform_bakeout_time(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_bakeout_time(120)
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTime")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformBakeoutTime": 120\n}')

    @patch('urllib.request.urlopen')
    def test_get_platform_bakeout_time(self, urlopen_mock: MagicMock):
        expected_bakeout_time = 180

        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"platformBakeoutTime": {expected_bakeout_time}}}', 'utf-8')

        bakeout_time = self.instr.get_platform_bakeout_time()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTime")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(bakeout_time, expected_bakeout_time)

    @patch('urllib.request.urlopen')
    def test_is_crycooler_running(self, urlopen_mock: MagicMock):
        expected_is_cryocooler_running = "false"
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"cryocoolerRunning": {expected_is_cryocooler_running}}}', 'utf-8')

        is_cryocooler_running = self.instr.is_cryocooler_running()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.cryocooler_properties_url}/cryocoolerRunning")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertFalse(is_cryocooler_running)

    @patch('urllib.request.urlopen')
    def test_is_crycooler_connected(self, urlopen_mock: MagicMock):
        expected_is_cryocooler_connected = "true"
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            f'{{"deviceConnected": {expected_is_cryocooler_connected}}}', 'utf-8')

        is_cryocooler_connected = self.instr.is_cryocooler_connected()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.cryocooler_properties_url}/deviceConnected")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertTrue(is_cryocooler_connected)

    @patch('urllib.request.urlopen')
    def test_get_sample_thermometer_properties(self, urlopen_mock: MagicMock):
        expected_resistance_ok = False
        expected_temperature_ok = True
        expected_temperature_stability_ok = False
        expected_resistance = 95
        expected_temperature = 293
        expected_temperature_stability = 10
        expected_temperature_stable = True
        json_resp = {
            "sample": {
                "resistanceOK": expected_resistance_ok,
                "resistance": expected_resistance,
                "temperatureOK": expected_temperature_ok,
                "temperature": expected_temperature,
                "temperatureStabilityOK": expected_temperature_stability_ok,
                "temperatureStability": expected_temperature_stability,
                "temperatureStable": expected_temperature_stable
            }
        }

        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(json.dumps(json_resp), 'utf-8')

        sample_data = self.instr.get_sample_thermometer_properties()
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.sample_chamber_thermometer_properties_url}/sample")
        self.assertEqual(req.method, 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(sample_data.resistance, expected_resistance)
        self.assertFalse(sample_data.resistance_ok)
        self.assertEqual(sample_data.temperature, expected_temperature)
        self.assertTrue(sample_data.temperature_ok)
        self.assertEqual(sample_data.temperature_stability, expected_temperature_stability)
        self.assertTrue(sample_data.temperature_stable)
        self.assertFalse(sample_data.temperature_stability_ok)


if __name__ == '__main__':
    unittest.main()
