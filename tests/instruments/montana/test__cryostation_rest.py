"""Unit tests for the Montana Cryostation common REST API base class.

The RPC methods implemented by `Montana_CryostationRest_Base` are inherited unchanged by the model-specific
`Montana_CryostationS50` and `Montana_CryostationS100` drivers, so they are tested once here, directly against
the base class. The model-specific test modules only cover their own additions (aliases, subsystem names and,
for the S100, the extra convenience getters).
"""

import json
import logging
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_RuntimeException
from qmi.instruments.montana._cryostation_rest import (
    Montana_CryostationRest_Base,
    Montana_CryostationRest_Heater_Properties,
    Montana_CryostationRest_System_Goal,
    Montana_CryostationRest_System_State,
)
from tests.patcher import PatcherQmiContext as QMI_Context

THERMOMETER_JSON = {
    "resistanceOK": False,
    "resistance": 95.0,
    "temperatureOK": True,
    "temperature": 293.0,
    "temperatureStabilityOK": False,
    "temperatureStability": 10.0,
    "temperatureStable": True,
}
HEATER_JSON = {"current": 0.25, "power": 1.5, "restriction": False}


def setUpModule():
    # Tests below deliberately trigger instrument errors through RPC; silence the remote tracebacks logged by RPC.
    logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)


def tearDownModule():
    logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)


class TestCryostationRestBase(unittest.TestCase):
    """Tests for the shared REST API behaviour of `Montana_CryostationRest_Base`."""

    def setUp(self):
        ctx = QMI_Context("montana-rest-test-context")
        self.ip_address = "192.168.1.1"
        self.instr = Montana_CryostationRest_Base(ctx, "montana_rest_test_instr", self.ip_address)
        self.instr.open()
        self.base_url = f"http://{self.ip_address}:47101/v1"
        self.controller_properties_url = f"{self.base_url}/controller/properties"
        self.controller_methods_url = f"{self.base_url}/controller/methods"
        self.cryocooler_properties_url = f"{self.base_url}/cooler/cryocooler/properties"
        self.sample_chamber_properties_url = (
            f"{self.base_url}/sampleChamber/temperatureControllers/platform/properties"
        )
        self.sample_chamber_thermometer_properties_url = (
            f"{self.base_url}/sampleChamber/temperatureControllers/platform/thermometer/properties"
        )

    def tearDown(self):
        self.instr.close()

    def _mock_get_response(self, urlopen_mock: MagicMock, json_resp: dict) -> None:
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(json.dumps(json_resp), "utf-8")

    def _assert_get_request(self, urlopen_mock: MagicMock, url: str) -> None:
        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, url)
        self.assertEqual(req.method, "GET")
        self.assertIsNone(req.data)

    def _assert_thermometer_properties(self, data) -> None:
        self.assertFalse(data.resistance_ok)
        self.assertEqual(data.resistance, THERMOMETER_JSON["resistance"])
        self.assertTrue(data.temperature_ok)
        self.assertEqual(data.temperature, THERMOMETER_JSON["temperature"])
        self.assertFalse(data.temperature_stability_ok)
        self.assertEqual(data.temperature_stability, THERMOMETER_JSON["temperatureStability"])
        self.assertTrue(data.temperature_stable)

    def test_open_close(self):
        self.instr.close()
        self.assertFalse(self.instr.is_open())
        self.instr.open()
        self.assertTrue(self.instr.is_open())

    def test_open_with_invalid_ip_address(self):
        with self.assertRaises(ValueError):
            Montana_CryostationRest_Base(QMI_Context("montana-invalid-ip-context"), "invalid_ip", "not.an.ip.address")

    @patch('urllib.request.urlopen')
    def test_get_system_goal(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"systemGoal": "Vent"})

        sys_goal = self.instr.get_system_goal()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/systemGoal")
        self.assertEqual(sys_goal, Montana_CryostationRest_System_Goal.VENT)

    @patch('urllib.request.urlopen')
    def test_get_system_state(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"systemState": "Ready"})

        sys_state = self.instr.get_system_state()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/systemState")
        self.assertEqual(sys_state, Montana_CryostationRest_System_State.READY)

    @patch('urllib.request.urlopen')
    def test_cooldown_allowed(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"canCooldown": "true"})

        cooldown_allowed = self.instr.cooldown_allowed()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/canCooldown")
        self.assertTrue(cooldown_allowed)

    @patch('urllib.request.urlopen')
    def test_cooldown_allowed_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400

        with self.assertRaises(QMI_InstrumentException):
            self.instr.cooldown_allowed()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/canCooldown")

    @patch('urllib.request.urlopen')
    def test_warmup_allowed(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"canWarmup": False})

        warmup_allowed = self.instr.warmup_allowed()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/canWarmup")
        self.assertFalse(warmup_allowed)

    @patch('urllib.request.urlopen')
    def test_set_platform_target_temperature(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_target_temperature(4.9)

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformTargetTemperature")
        self.assertEqual(req.method, "PUT")
        self.assertEqual(req.data, b'{\n    "platformTargetTemperature": 4.9\n}')

    @patch('urllib.request.urlopen')
    def test_set_platform_target_temperature_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_platform_target_temperature(4.9)
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformTargetTemperature")

    @patch('urllib.request.urlopen')
    def test_get_platform_target_temperature(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"platformTargetTemperature": 4.9})

        temp = self.instr.get_platform_target_temperature()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/platformTargetTemperature")
        self.assertEqual(temp, 4.9)

    @patch('urllib.request.urlopen')
    def test_get_platform_target_temperature_limit(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"temperatureLimit": 351})

        temp_limit = self.instr.get_platform_target_temperature_limit()

        self._assert_get_request(urlopen_mock, f"{self.sample_chamber_properties_url}/temperatureLimit")
        self.assertEqual(temp_limit, 351)

    @patch('urllib.request.urlopen')
    def test_start_cooldown(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.start_cooldown()

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_methods_url}/cooldown()")
        self.assertEqual(req.method, "POST")
        self.assertIsNone(req.data)

    @patch('urllib.request.urlopen')
    def test_start_warmup(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.start_warmup()

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_methods_url}/warmup()")
        self.assertEqual(req.method, "POST")
        self.assertIsNone(req.data)

    @patch('urllib.request.urlopen')
    def test_enable_platform_bakeout(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.enable_platform_bakeout()

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutEnabled")
        self.assertEqual(req.method, "PUT")
        self.assertEqual(req.data, b'{\n    "platformBakeoutEnabled": true\n}')

    @patch('urllib.request.urlopen')
    def test_enable_platform_bakeout_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400

        with self.assertRaises(QMI_InstrumentException):
            self.instr.enable_platform_bakeout()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutEnabled")

    @patch('urllib.request.urlopen')
    def test_disable_platform_bakeout(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.disable_platform_bakeout()

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutEnabled")
        self.assertEqual(req.method, "PUT")
        self.assertEqual(req.data, b'{\n    "platformBakeoutEnabled": false\n}')

    @patch('urllib.request.urlopen')
    def test_is_platform_bakeout_enabled(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"platformBakeoutEnabled": True})

        enabled = self.instr.is_platform_bakeout_enabled()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/platformBakeoutEnabled")
        self.assertTrue(enabled)

    @patch('urllib.request.urlopen')
    def test_get_platform_bakeout_temperature_limit(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"platformBakeoutTemperatureLimit": 351})

        limit = self.instr.get_platform_bakeout_temperature_limit()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/platformBakeoutTemperatureLimit")
        self.assertEqual(limit, 351)

    @patch('urllib.request.urlopen')
    def test_set_platform_bakeout_temperature(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_bakeout_temperature(312)

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTemperature")
        self.assertEqual(req.method, "PUT")
        self.assertEqual(req.data, b'{\n    "platformBakeoutTemperature": 312\n}')

    @patch('urllib.request.urlopen')
    def test_get_platform_bakeout_temperature(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"platformBakeoutTemperature": 4.9})

        temp = self.instr.get_platform_bakeout_temperature()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/platformBakeoutTemperature")
        self.assertEqual(temp, 4.9)

    @patch('urllib.request.urlopen')
    def test_set_platform_bakeout_time(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_bakeout_time(120)

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.controller_properties_url}/platformBakeoutTime")
        self.assertEqual(req.method, "PUT")
        self.assertEqual(req.data, b'{\n    "platformBakeoutTime": 120\n}')

    @patch('urllib.request.urlopen')
    def test_get_platform_bakeout_time(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"platformBakeoutTime": 180})

        bakeout_time = self.instr.get_platform_bakeout_time()

        self._assert_get_request(urlopen_mock, f"{self.controller_properties_url}/platformBakeoutTime")
        self.assertEqual(bakeout_time, 180)

    @patch('urllib.request.urlopen')
    def test_is_cryocooler_running(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"cryocoolerRunning": False})

        running = self.instr.is_cryocooler_running()

        self._assert_get_request(urlopen_mock, f"{self.cryocooler_properties_url}/cryocoolerRunning")
        self.assertFalse(running)

    @patch('urllib.request.urlopen')
    def test_is_cryocooler_connected(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"deviceConnected": True})

        connected = self.instr.is_cryocooler_connected()

        self._assert_get_request(urlopen_mock, f"{self.cryocooler_properties_url}/deviceConnected")
        self.assertTrue(connected)

    @patch('urllib.request.urlopen')
    def test_get_sample_thermometer_properties(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"sample": THERMOMETER_JSON})

        data = self.instr.get_sample_thermometer_properties()

        self._assert_get_request(urlopen_mock, f"{self.sample_chamber_thermometer_properties_url}/sample")
        self._assert_thermometer_properties(data)

    def test_get_thermometer_properties(self):
        """Test the thermometer properties getters of the other temperature controllers."""
        cases = [
            ("get_cryooptic_thermometer_properties", "sampleChamber/temperatureControllers/cryoOptic"),
            ("get_stage1_thermometer_properties", "cooler/temperatureControllers/stage1"),
            ("get_stage2_thermometer_properties", "cooler/temperatureControllers/stage2"),
        ]
        for method_name, subsystem in cases:
            with self.subTest(method=method_name), patch('urllib.request.urlopen') as urlopen_mock:
                self._mock_get_response(urlopen_mock, {"sample": THERMOMETER_JSON})

                data = getattr(self.instr, method_name)()

                self._assert_get_request(urlopen_mock, f"{self.base_url}/{subsystem}/thermometer/properties/sample")
                self._assert_thermometer_properties(data)

    def test_get_heater_properties(self):
        """Test the heater properties getters of both temperature controllers that expose a heater."""
        cases = [
            ("get_platform_heater_properties", "sampleChamber/temperatureControllers/platform"),
            ("get_cryooptic_heater_properties", "sampleChamber/temperatureControllers/cryoOptic"),
        ]
        for method_name, subsystem in cases:
            with self.subTest(method=method_name), patch('urllib.request.urlopen') as urlopen_mock:
                self._mock_get_response(urlopen_mock, {"sample": HEATER_JSON})

                data = getattr(self.instr, method_name)()

                self._assert_get_request(urlopen_mock, f"{self.base_url}/{subsystem}/heater/properties/sample")
                self.assertIsInstance(data, Montana_CryostationRest_Heater_Properties)
                self.assertEqual(data.current, HEATER_JSON["current"])
                self.assertEqual(data.power, HEATER_JSON["power"])
                self.assertFalse(data.restriction)

    @patch('urllib.request.urlopen')
    def test_get_heater_properties_with_http_error(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 400
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_platform_heater_properties()

    def test_request_when_closed(self):
        self.instr.close()
        with self.assertRaises(QMI_RuntimeException):
            self.instr.get_system_state()
        self.instr.open()

    def test_invalid_request_type(self):
        with self.assertRaises(QMI_RuntimeException):
            self.instr._send_request(f"{self.base_url}/controller/properties/systemState", "DELETE")

    @patch('urllib.request.urlopen')
    def test_http_error_exception(self, urlopen_mock: MagicMock):
        url = f"{self.base_url}/controller/properties/systemState"
        urlopen_mock.side_effect = urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_system_state()

    def test_get_property_without_response(self):
        with patch.object(self.instr, "_send_request", return_value=None):
            with self.assertRaises(QMI_InstrumentException):
                self.instr.get_system_state()


if __name__ == '__main__':
    unittest.main()
