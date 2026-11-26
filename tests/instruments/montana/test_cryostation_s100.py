"""Unit test for Montana Cryostation S100 driver."""

import json
import unittest
from unittest.mock import MagicMock, patch

from qmi.instruments.montana import (
    Montana_CryostationS100,
    Montana_CryostationS100_Heater_Properties,
    Montana_CryostationS100_Thermometer_Properties,
)
from qmi.instruments.montana._cryostation_rest import (
    Montana_CryostationRest_Heater_Properties,
    Montana_CryostationRest_System_Goal,
    Montana_CryostationRest_System_State,
    Montana_CryostationRest_Thermometer_Properties,
)
from qmi.instruments.montana.cryostation_s100 import (
    Montana_CryostationS100_System_Goal,
    Montana_CryostationS100_System_State,
)
from tests.instruments.montana.test__cryostation_rest import HEATER_JSON, THERMOMETER_JSON
from tests.patcher import PatcherQmiContext as QMI_Context

PLATFORM = "sampleChamber/temperatureControllers/platform"
CRYOOPTIC = "sampleChamber/temperatureControllers/cryoOptic"
STAGE1 = "cooler/temperatureControllers/stage1"
STAGE2 = "cooler/temperatureControllers/stage2"


class TestCryostationS100(unittest.TestCase):
    """Tests for the S100-specific behaviour: convenience getters, subsystem names and type aliases.

    The REST API behaviour shared with the S50 driver is tested once, directly against the base class, in
    `test__cryostation_rest.py`.
    """

    def setUp(self):
        ctx = QMI_Context("montana-s100-test-context")
        self.ip_address = "192.168.1.1"
        self.instr = Montana_CryostationS100(ctx, "montana_s100_test_instr", self.ip_address)
        self.instr.open()
        self.base_url = f"http://{self.ip_address}:47101/v1"

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

    def test_dataclass_and_enum_aliases(self):
        self.assertIs(Montana_CryostationS100_Thermometer_Properties, Montana_CryostationRest_Thermometer_Properties)
        self.assertIs(Montana_CryostationS100_Heater_Properties, Montana_CryostationRest_Heater_Properties)
        self.assertIs(Montana_CryostationS100_System_State, Montana_CryostationRest_System_State)
        self.assertIs(Montana_CryostationS100_System_Goal, Montana_CryostationRest_System_Goal)

    def test_subsystem_string_aliases(self):
        self.assertEqual(Montana_CryostationS100.SAMPLE_CHAMBER_TEMP_CONTROLLER_PLATFORM_SUBSYSTEM_STR, PLATFORM)
        self.assertEqual(Montana_CryostationS100.SAMPLE_CHAMBER_TEMP_CONTROLLER_CRYOOPTIC_SUBSYSTEM_STR, CRYOOPTIC)

    @patch('urllib.request.urlopen')
    def test_get_platform_thermometer_properties(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"sample": THERMOMETER_JSON})

        data = self.instr.get_platform_thermometer_properties()

        self._assert_get_request(urlopen_mock, f"{self.base_url}/{PLATFORM}/thermometer/properties/sample")
        self.assertIsInstance(data, Montana_CryostationS100_Thermometer_Properties)
        self.assertEqual(data.temperature, THERMOMETER_JSON["temperature"])

    @patch('urllib.request.urlopen')
    def test_get_cryo_optic_thermometer_properties(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"sample": THERMOMETER_JSON})

        data = self.instr.get_cryo_optic_thermometer_properties()

        self._assert_get_request(urlopen_mock, f"{self.base_url}/{CRYOOPTIC}/thermometer/properties/sample")
        self.assertIsInstance(data, Montana_CryostationS100_Thermometer_Properties)
        self.assertEqual(data.temperature, THERMOMETER_JSON["temperature"])

    @patch('urllib.request.urlopen')
    def test_get_cryo_optic_heater_properties(self, urlopen_mock: MagicMock):
        self._mock_get_response(urlopen_mock, {"sample": HEATER_JSON})

        data = self.instr.get_cryo_optic_heater_properties()

        self._assert_get_request(urlopen_mock, f"{self.base_url}/{CRYOOPTIC}/heater/properties/sample")
        self.assertEqual(
            data,
            Montana_CryostationS100_Heater_Properties(current=0.25, power=1.5, restriction=False),
        )

    def test_get_single_thermometer_values(self):
        """Test the getters returning a single thermometer value."""
        cases = [
            ("get_platform_temperature", PLATFORM, THERMOMETER_JSON["temperature"]),
            ("get_platform_stability", PLATFORM, THERMOMETER_JSON["temperatureStability"]),
            ("get_stage1_temperature", STAGE1, THERMOMETER_JSON["temperature"]),
            ("get_stage2_temperature", STAGE2, THERMOMETER_JSON["temperature"]),
            ("get_cryo_optic_temperature", CRYOOPTIC, THERMOMETER_JSON["temperature"]),
            ("get_cryo_optic_stability", CRYOOPTIC, THERMOMETER_JSON["temperatureStability"]),
        ]
        for method_name, subsystem, expected in cases:
            with self.subTest(method=method_name), patch('urllib.request.urlopen') as urlopen_mock:
                self._mock_get_response(urlopen_mock, {"sample": THERMOMETER_JSON})

                value = getattr(self.instr, method_name)()

                self._assert_get_request(urlopen_mock, f"{self.base_url}/{subsystem}/thermometer/properties/sample")
                self.assertEqual(value, expected)

    def test_get_heater_power(self):
        """Test the getters returning the heater power."""
        cases = [
            ("get_platform_heater_power", PLATFORM),
            ("get_cryo_optic_heater_power", CRYOOPTIC),
        ]
        for method_name, subsystem in cases:
            with self.subTest(method=method_name), patch('urllib.request.urlopen') as urlopen_mock:
                self._mock_get_response(urlopen_mock, {"sample": HEATER_JSON})

                value = getattr(self.instr, method_name)()

                self._assert_get_request(urlopen_mock, f"{self.base_url}/{subsystem}/heater/properties/sample")
                self.assertEqual(value, HEATER_JSON["power"])


if __name__ == '__main__':
    unittest.main()
