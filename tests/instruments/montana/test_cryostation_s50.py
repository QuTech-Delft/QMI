"""Unit test for Montana Cryostation S50 driver."""

import unittest
from unittest.mock import MagicMock, patch

from qmi.instruments.montana import Montana_CryostationS50
from qmi.instruments.montana._cryostation_rest import (
    Montana_CryostationRest_Heater_Properties,
    Montana_CryostationRest_System_Goal,
    Montana_CryostationRest_System_State,
    Montana_CryostationRest_Thermometer_Properties,
)
from qmi.instruments.montana.cryostation_s50 import (
    Montana_CryostationS50_Heater_Properties,
    Montana_CryostationS50_System_Goal,
    Montana_CryostationS50_System_State,
    Montana_CryostationS50_Thermometer_Properties,
)
from tests.patcher import PatcherQmiContext as QMI_Context


class TestCryostationS50(unittest.TestCase):
    """Tests for the S50 driver.

    `Montana_CryostationS50` adds no behaviour of its own on top of `Montana_CryostationRest_Base`: the full
    REST API behaviour is tested once, directly against the base class, in `test__cryostation_rest.py`. Here we
    only check that the model-specific aliases are correct and that the concrete driver is wired up correctly.
    """

    def setUp(self):
        ctx = QMI_Context("montana-s50-test-context")
        self.ip_address = "192.168.1.1"
        self.instr = Montana_CryostationS50(ctx, "montana_s50_test_instr", self.ip_address)
        self.instr.open()
        self.base_url = f"http://{self.ip_address}:47101/v1"

    def tearDown(self):
        self.instr.close()

    def test_dataclass_and_enum_aliases(self):
        self.assertIs(Montana_CryostationS50_Thermometer_Properties, Montana_CryostationRest_Thermometer_Properties)
        self.assertIs(Montana_CryostationS50_Heater_Properties, Montana_CryostationRest_Heater_Properties)
        self.assertIs(Montana_CryostationS50_System_State, Montana_CryostationRest_System_State)
        self.assertIs(Montana_CryostationS50_System_Goal, Montana_CryostationRest_System_Goal)

    @patch('urllib.request.urlopen')
    def test_get_system_state(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200
        urlopen_mock.return_value.__enter__.return_value.read.return_value = bytes(
            '{"systemState": "Ready"}', 'utf-8')

        sys_state = self.instr.get_system_state()

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.base_url}/controller/properties/systemState")
        self.assertEqual(req.method, 'GET')
        self.assertEqual(sys_state, Montana_CryostationS50_System_State.READY)

    @patch('urllib.request.urlopen')
    def test_set_platform_target_temperature(self, urlopen_mock: MagicMock):
        urlopen_mock.return_value.__enter__.return_value.status = 200

        self.instr.set_platform_target_temperature(4.9)

        urlopen_mock.assert_called_once()
        req = urlopen_mock.call_args.args[0]
        self.assertEqual(req.full_url, f"{self.base_url}/controller/properties/platformTargetTemperature")
        self.assertEqual(req.method, 'PUT')
        self.assertEqual(req.data, b'{\n    "platformTargetTemperature": 4.9\n}')


if __name__ == '__main__':
    unittest.main()
