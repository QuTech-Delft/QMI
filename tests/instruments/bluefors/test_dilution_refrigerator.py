"""Unit-tests for the Bluefors dilution refrigerator instrument driver."""

import json
import math
import unittest
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException, QMI_UsageException
from qmi.instruments.bluefors import Bluefors_DilutionRefrigerator, State

from tests.patcher import PatcherQmiContext as QMI_Context

IP = "192.168.1.10"
BASE_URL = f"http://{IP}:49099"


def make_value_entry(value: str, status: str = "SYNCHRONIZED", exception: str = "") -> dict[str, Any]:
    """Build a single value entry as returned by the Bluefors HTTP API."""
    return {
        "type": "Value.Number.Float",
        "content": {
            "owner": "owner",
            "latest_value": {"value": value, "date": 1700000000000, "status": status, "exception": exception},
        },
    }


def make_response(read_value: bytes) -> MagicMock:
    """Build a mocked context manager for `urllib.request.urlopen`, returning `read_value` on `read()`."""
    response = MagicMock()
    response.read.return_value = read_value
    context_manager = MagicMock()
    context_manager.__enter__.return_value = response
    context_manager.__exit__.return_value = False
    return context_manager


class FakeServer:
    """Routes mocked `urlopen` calls to responses based on the value key in the URL."""

    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}
        self.raw: dict[str, bytes] = {}
        self.post_status = "SYNCHRONIZED"
        self.requests: list[Any] = []

    def set_value(self, key: str, value: str, **kwargs: Any) -> None:
        self.values[key] = make_value_entry(value, **kwargs)

    def set_unavailable(self, key: str) -> None:
        self.values[key] = {"type": None, "content": {}}

    def __call__(self, request: Any, timeout: float | None = None) -> MagicMock:
        self.requests.append(request)
        url: str = request.full_url
        path = url[len(BASE_URL):]
        for raw_path, raw in self.raw.items():
            if path.startswith(raw_path):
                return make_response(raw)

        if request.data is not None:
            posted = json.loads(request.data)
            name = next(iter(posted["data"]))
            answer = {"data": {name: make_value_entry("1", status=self.post_status)}}
            return make_response(json.dumps(answer).encode())

        key = path.split("?")[0].removeprefix("/values/").replace("/", ".")
        return make_response(json.dumps({"data": {key: self.values[key]}}).encode())


class BlueforsTestCaseBase(unittest.TestCase):
    """Common set-up: an opened instrument with a mocked HTTP server."""

    def setUp(self) -> None:
        self.server = FakeServer()
        patcher = patch("urllib.request.urlopen", side_effect=self.server)
        self.urlopen = patcher.start()
        self.addCleanup(patcher.stop)
        self.context = MagicMock(spec=QMI_Context)
        self.context.name = "context"
        self.instr = Bluefors_DilutionRefrigerator(self.context, "bf", IP)
        self.instr.open()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()


class ConstructionTestCase(unittest.TestCase):
    """Tests for the constructor and open/close."""

    def setUp(self) -> None:
        self.context = MagicMock(spec=QMI_Context)
        self.context.name = "context"

    def test_insecure_url(self):
        """The insecure port 49099 with HTTP is used by default."""
        instr = Bluefors_DilutionRefrigerator(self.context, "bf", IP)
        self.assertEqual(BASE_URL, instr._baseurl)

    def test_secure_url(self):
        """The secure port 49098 with HTTPS is used when requested."""
        instr = Bluefors_DilutionRefrigerator(self.context, "bf", IP, secure_port=True, access_key="abc")
        self.assertEqual(f"https://{IP}:49098", instr._baseurl)

    def test_secure_without_key_raises(self):
        """A secure connection requires an access key."""
        with self.assertRaises(QMI_InstrumentException):
            Bluefors_DilutionRefrigerator(self.context, "bf", IP, secure_port=True)

    def test_invalid_address_raises(self):
        """An invalid IPv4 address raises a ValueError."""
        with self.assertRaises(ValueError):
            Bluefors_DilutionRefrigerator(self.context, "bf", "not.an.ip")

    def test_open_close(self):
        """Opening and closing toggles the open state."""
        instr = Bluefors_DilutionRefrigerator(self.context, "bf", IP)
        instr.open()
        self.assertTrue(instr.is_open())
        instr.close()
        self.assertFalse(instr.is_open())


class QueryTestCase(BlueforsTestCaseBase):
    """Tests for the query (getter) methods."""

    def test_get_idn(self):
        """The identification contains the system version."""
        self.server.raw["/system/"] = json.dumps({"data": {"system_version": "2.2.1"}}).encode()
        idn = self.instr.get_idn()
        self.assertEqual("Bluefors", idn.vendor)
        self.assertEqual("Dilution Refrigerator", idn.model)
        self.assertEqual("2.2.1", idn.version)

    def test_get_layout(self):
        """The layout is returned as a parsed XML element."""
        self.server.raw["/resources/layout.xml"] = b"<layout><item name='a'/></layout>"
        layout = self.instr.get_layout()
        self.assertIsInstance(layout, ElementTree.Element)
        self.assertEqual("layout", layout.tag)
        self.assertEqual("a", layout[0].get("name"))

    def test_get_flowmeter_value(self):
        """The flow is returned as a float."""
        self.server.set_value("mapper.bf.flow", "0.123")
        self.assertEqual(0.123, self.instr.get_flowmeter_value())
        self.assertEqual(f"{BASE_URL}/values/mapper/bf/flow?", self.server.requests[-1].full_url)
        self.assertEqual("GET", self.server.requests[-1].get_method())

    def test_get_valve(self):
        """Valve states are translated into State values."""
        self.server.set_value("mapper.bf.valves.v5", "1")
        self.assertEqual(State.ON, self.instr.get_valve(5))
        self.server.set_value("mapper.bf.valves.v5", "0")
        self.assertEqual(State.OFF, self.instr.get_valve(5))

    def test_get_valve_out_of_range(self):
        """Valve numbers outside 1-23 raise without querying the device."""
        for valve in (0, 24):
            with self.assertRaises(QMI_UsageException):
                self.instr.get_valve(valve)

        self.urlopen.assert_not_called()

    def test_get_states(self):
        """Heater state getters translate values into State values."""
        cases = [
            ("mapper.bf.heaters.heater", self.instr.get_4k_heater_state),
            ("mapper.temperature_control.heaters.sample.enabled", self.instr.get_mxc_heater_state),
            ("mapper.temperature_control.heaters.still.enabled", self.instr.get_still_heater_state),
        ]
        for key, getter in cases:
            with self.subTest(key=key):
                self.server.set_value(key, "1")
                self.assertEqual(State.ON, getter())
                self.server.set_value(key, "0")
                self.assertEqual(State.OFF, getter())

    def test_get_temperatures(self):
        """Temperature getters return floats, or None for an empty value."""
        cases = [
            ("mapper.bf.temperatures.t4k", self.instr.get_4k_flange_temperature),
            ("mapper.bf.temperatures.t50k", self.instr.get_50k_flange_temperature),
            ("mapper.bf.temperatures.tmagnet", self.instr.get_magnet_temperature),
            ("mapper.bf.temperatures.tstill", self.instr.get_still_flange_temperature),
            ("mapper.bf.temperatures.tmixing", self.instr.get_mxc_flange_temperature),
            ("mapper.bf.temperatures.tfse", self.instr.get_fse_temperature),
            ("mapper.bflegacy.double.cpatempwo", self.instr.get_cpa_temperature_water_out),
            ("mapper.bflegacy.double.cpatempwi", self.instr.get_cpa_temperature_water_in),
            ("mapper.bflegacy.double.cpatempo", self.instr.get_cpa_temperature_oil),
            ("mapper.bflegacy.double.cpatemph", self.instr.get_cpa_temperature_helium),
        ]
        for key, getter in cases:
            with self.subTest(key=key):
                self.server.set_value(key, "3.5")
                self.assertEqual(3.5, getter())
                self.server.set_value(key, "")
                self.assertIsNone(getter())

    def test_get_unavailable_device_returns_nan(self):
        """A device that is not present (type null) returns NaN for float values."""
        self.server.set_unavailable("mapper.bf.temperatures.t4k")
        self.assertTrue(math.isnan(self.instr.get_4k_flange_temperature()))

    def test_get_heater_powers(self):
        """Heater power getters return floats."""
        self.server.set_value("mapper.temperature_control.heaters.sample.power", "1e-6")
        self.assertEqual(1e-6, self.instr.get_mxc_heater_power())
        self.server.set_value("mapper.temperature_control.heaters.still.power", "2e-3")
        self.assertEqual(2e-3, self.instr.get_still_heater_power())

    def test_get_pressures(self):
        """Pressures are converted from bar to mbar when the gauge is on, None otherwise."""
        getters = [
            self.instr.get_p1_pressure,
            self.instr.get_p2_pressure,
            self.instr.get_p3_pressure,
            self.instr.get_p4_pressure,
            self.instr.get_p5_pressure,
            self.instr.get_p6_pressure,
        ]
        for number, getter in enumerate(getters, start=1):
            with self.subTest(gauge=number):
                key = f"mapper.bf.pressures.p{number}"
                self.server.set_value(key, "0.5")
                self.server.set_value(f"{key}_on", "1")
                self.assertAlmostEqual(500.0, getter())
                # Empty pressure value.
                self.server.set_value(key, "")
                self.assertIsNone(getter())
                # Gauge is off; pressure is not queried.
                self.server.set_value(key, "0.5")
                self.server.set_value(f"{key}_on", "0")
                n_requests = len(self.server.requests)
                self.assertIsNone(getter())
                self.assertEqual(n_requests + 1, len(self.server.requests))
                # Empty gauge status.
                self.server.set_value(f"{key}_on", "")
                self.assertIsNone(getter())

    def test_get_cpa_pressures(self):
        """CPA pressures are converted from psi to bar."""
        self.server.set_value("mapper.bflegacy.double.cpahpa", "100")
        self.assertAlmostEqual(6.89475729, self.instr.get_cpa_average_high_side_pressure())
        self.server.set_value("mapper.bflegacy.double.cpalpa", "")
        self.assertIsNone(self.instr.get_cpa_average_low_side_pressure())
        self.server.set_value("mapper.bflegacy.double.cpalpa", "10")
        self.assertAlmostEqual(0.689475729, self.instr.get_cpa_average_low_side_pressure())

    def test_value_exception_raises(self):
        """A value reporting an exception raises an instrument exception."""
        self.server.set_value("mapper.bf.flow", "0", exception="sensor broken")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_flowmeter_value()

    def test_http_error_raises(self):
        """An HTTP error is translated into an instrument exception."""
        self.urlopen.side_effect = urllib.error.HTTPError(BASE_URL, 404, "Not found", MagicMock(), None)
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_flowmeter_value()

    def test_access_key_in_url(self):
        """The access key is added to the URL as a query parameter."""
        instr = Bluefors_DilutionRefrigerator(self.context, "bf2", IP, access_key="se cret")
        instr.open()
        self.server.set_value("mapper.bf.flow", "1.0")
        instr.get_flowmeter_value()
        self.assertEqual(f"{BASE_URL}/values/mapper/bf/flow?key=se%20cret", self.server.requests[-1].full_url)
        instr.set_still_heater_power(1.0)
        self.assertEqual(
            f"{BASE_URL}/values/?fields=name;value;status&key=se%20cret", self.server.requests[-1].full_url
        )
        self.server.raw["/resources/layout.xml"] = b"<layout/>"
        instr.get_layout()
        self.assertEqual(f"{BASE_URL}/resources/layout.xml?key=se%20cret", self.server.requests[-1].full_url)
        instr.close()

    def test_url_error_raises(self):
        """Network errors (e.g. connection refused) are translated into an instrument exception."""
        self.urlopen.side_effect = urllib.error.URLError("Connection refused")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_4k_flange_temperature()

    def test_timeout_raises(self):
        """A timeout is translated into an instrument exception."""
        self.urlopen.side_effect = TimeoutError("timed out")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_4k_flange_temperature()

    def test_invalid_json_raises(self):
        """A response which is not valid JSON raises an instrument exception."""
        self.server.raw["/values/mapper/bf/flow"] = b"<html>error</html>"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_flowmeter_value()

    def test_missing_value_raises(self):
        """A response without the requested value raises an instrument exception."""
        self.server.raw["/values/mapper/bf/flow"] = b'{"data": {}}'
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_flowmeter_value()

    def test_invalid_layout_raises(self):
        """An invalid layout XML raises an instrument exception."""
        self.server.raw["/resources/layout.xml"] = b"<layout>"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_layout()

    def test_unavailable_state_raises(self):
        """A state of a device that is not present raises an instrument exception."""
        self.server.set_unavailable("mapper.bf.heaters.heater")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_4k_heater_state()

    def test_empty_float_value_raises(self):
        """An empty value for a non-optional float raises an instrument exception."""
        self.server.set_value("mapper.bf.flow", "")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_flowmeter_value()

    def test_unavailable_pressure_gauge_raises(self):
        """A pressure gauge status of a device that is not present raises an instrument exception."""
        self.server.set_unavailable("mapper.bf.pressures.p1_on")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_p1_pressure()

    def test_not_open_raises(self):
        """Communicating with a closed instrument raises an exception without a request."""
        self.instr.close()
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.get_flowmeter_value()
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.set_still_heater_power(1.0)

        self.urlopen.assert_not_called()


class CommandTestCase(BlueforsTestCaseBase):
    """Tests for the setter methods."""

    def assert_posted(self, name: str, value: Any) -> None:
        request = self.server.requests[-1]
        self.assertEqual("POST", request.get_method())
        self.assertTrue(request.full_url.startswith(f"{BASE_URL}/values/?fields=name;value;status"))
        self.assertEqual("application/json", request.get_header("Content-type"))
        self.assertEqual({"data": {name: {"content": {"value": value}}}}, json.loads(request.data))

    def test_set_heater_states(self):
        """Heater states can be set with 'ON' and 'OFF' strings, in any case, or with State values."""
        cases = [
            ("mapper.temperature_control.heaters.sample.enabled", self.instr.set_mxc_heater_state),
            ("mapper.temperature_control.heaters.still.enabled", self.instr.set_still_heater_state),
        ]
        for name, setter in cases:
            with self.subTest(name=name):
                setter("ON")
                self.assert_posted(name, 1)
                setter("off")
                self.assert_posted(name, 0)
                setter(State.ON)
                self.assert_posted(name, 1)
                setter(State.OFF)
                self.assert_posted(name, 0)

    def test_set_negative_heater_power_raises(self):
        """A negative heater power raises without posting."""
        with self.assertRaises(QMI_UsageException):
            self.instr.set_mxc_heater_power(-1e-6)
        with self.assertRaises(QMI_UsageException):
            self.instr.set_still_heater_power(-1e-3)

        self.urlopen.assert_not_called()

    def test_set_malformed_response_raises(self):
        """A post response without the status of the posted value raises an instrument exception."""
        self.server.raw["/values/?fields"] = b'{"data": {}}'
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_mxc_heater_power(1e-6)

    def test_set_heater_state_invalid(self):
        """An invalid heater state string raises without posting."""
        with self.assertRaises(QMI_UsageException):
            self.instr.set_mxc_heater_state("maybe")
        with self.assertRaises(QMI_UsageException):
            self.instr.set_still_heater_state("maybe")

        self.urlopen.assert_not_called()

    def test_set_heater_powers(self):
        """Heater powers are posted as given."""
        self.instr.set_mxc_heater_power(1e-6)
        self.assert_posted("mapper.temperature_control.heaters.sample.power", 1e-6)
        self.instr.set_still_heater_power(2e-3)
        self.assert_posted("mapper.temperature_control.heaters.still.power", 2e-3)

    def test_set_unsuccessful_raises(self):
        """A post reporting an INVALID or DISCONNECTED status raises an instrument exception."""
        for status in ("INVALID", "DISCONNECTED"):
            with self.subTest(status=status):
                self.server.post_status = status
                with self.assertRaises(QMI_InstrumentException):
                    self.instr.set_mxc_heater_power(1e-6)

    def test_set_http_error_raises(self):
        """An HTTP error while posting is translated into an instrument exception."""
        self.urlopen.side_effect = urllib.error.HTTPError(BASE_URL, 500, "Error", MagicMock(), None)
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_still_heater_power(1e-3)

    def test_disabled_commands_raise(self):
        """Potentially damaging commands are disabled by default."""
        with self.assertRaises(QMI_UsageException):
            self.instr.set_valve(1, State.ON)
        with self.assertRaises(QMI_UsageException):
            self.instr.set_4k_heater_state(State.ON)

        self.urlopen.assert_not_called()

    def test_enabled_commands_post(self):
        """With the safety flag lifted, valve and 4K heater commands are posted."""
        self.instr.DISABLED = False
        self.instr.set_valve(3, State.ON)
        self.assert_posted("mapper.bf.v3", 1)
        self.instr.set_4k_heater_state(State.OFF)
        self.assert_posted("mapper.bf.heaters.heater", 0)
        with self.assertRaises(QMI_UsageException):
            self.instr.set_valve(24, State.ON)


if __name__ == "__main__":
    unittest.main()
