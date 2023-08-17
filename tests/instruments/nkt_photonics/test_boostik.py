"""Test for the NKT Photonics boostik driver."""

import logging

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast

from dataclasses import dataclass


from qmi.core.transport import QMI_Transport
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.instruments.nkt_photonics.boostik import KoherasBoostikLaserAmplifier
from qmi.core.exceptions import QMI_InstrumentException


# Disable all logging
logging.disable(logging.CRITICAL)


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    transport_str: MagicMock
    name: MagicMock
    super: MagicMock
    instr: KoherasBoostikLaserAmplifier


class TestKoherasBoostikLaserAmplifier(TestCase):
    """Testcase for the KoherasBoostikLaserAmplifier class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.nkt_photonics.boostik.create_transport",
            return_value=mock_transport,
        ):
            instr = KoherasBoostikLaserAmplifier(
                MagicMock(), mock_name, mock_transport_str
            )

        self._patcher_super = patch(
            "qmi.instruments.nkt_photonics.boostik.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(KoherasBoostikLaserAmplifier, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """KoherasBoostikLaserAmplifier.__init__(), happy flow."""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)

    def test_open(self):
        """KoherasBoostikLaserAmplifier.open(), happy flow."""

        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.transport.discard_read.assert_called_once_with()
        self._meta.super().open.assert_called_once_with()

    def test_close(self):
        """KoherasBoostikLaserAmplifier.close(), happy flow."""

        self._meta.instr.close()
        self._meta.transport.close.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_send_command(self):
        """KoherasBoostikLaserAmplifier._send_command(), happy flow."""

        mock_cmd = MagicMock()
        self._meta.instr._send_command(mock_cmd)
        self._meta.transport.write.assert_called_once_with(
            (mock_cmd + "\r\n").encode("ascii")
        )

    def test_get_string(self):
        """KoherasBoostikLaserAmplifier._get_string(), happy flow."""

        mock_cmd = MagicMock()
        mock_resp = "RESPONSE\r\n".encode("ascii")

        self._meta.instr._send_command = MagicMock()
        self._meta.transport.read_until = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._get_string(mock_cmd)

        self._meta.instr._send_command.assert_called_once_with(mock_cmd)
        self.assertEqual(rt_val, "RESPONSE")

    def _test_get_string_conversion(self, function_name, resp):
        mock_cmd = MagicMock()
        mock_resp = resp

        self._meta.instr._get_string = MagicMock(return_value=mock_resp)
        rt_val = getattr(self._meta.instr, function_name)(mock_cmd)
        self.assertEqual(rt_val, mock_resp)

    def test_get_float(self):
        """KoherasBoostikLaserAmplifier._get_float(), happy flow."""
        self._test_get_string_conversion("_get_float", 0.005)

    def test_get_integer(self):
        """KoherasBoostikLaserAmplifier._get_integer(), happy flow."""
        self._test_get_string_conversion("_get_integer", 5)

    def test_get_bool(self):
        """KoherasBoostikLaserAmplifier._get_boolean(), happy flow."""
        self._test_get_string_conversion("_get_boolean", True)

    def _test_get_function(self, function_name, get_function_name, cmd):
        mock_resp = MagicMock()
        setattr(self._meta.instr, get_function_name, MagicMock(return_value=mock_resp))
        rt_val = getattr(self._meta.instr, function_name)()
        self.assertEqual(rt_val, mock_resp)
        getattr(self._meta.instr, get_function_name).assert_called_once_with(cmd)

    def test_get_current_setpoint(self):
        """KoherasBoostikLaserAmplifier.get_current_setpoint(), happy flow."""
        self._test_get_function("get_current_setpoint", "_get_float", "ACC")

    def test_get_actual_current(self):
        """KoherasBoostikLaserAmplifier.get_actual_current(), happy flow."""
        self._test_get_function("get_actual_current", "_get_float", "AMC")

    def test_get_diode_booster_temperature(self):
        """KoherasBoostikLaserAmplifier.get_diode_booster_temperature(), happy flow."""
        self._test_get_function("get_diode_booster_temperature", "_get_float", "AMT 1")

    def test_get_ambient_temperature(self):
        """KoherasBoostikLaserAmplifier.get_ambient_temperature(), happy flow."""
        self._test_get_function("get_ambient_temperature", "_get_float", "CMA")

    def test_get_input_power(self):
        """KoherasBoostikLaserAmplifier.get_input_power(), happy flow."""
        self._test_get_function("get_input_power", "_get_float", "CMP 1")

    def test_get_amplifier_enabled(self):
        """KoherasBoostikLaserAmplifier.get_amplifier_enabled(), happy flow."""
        self._test_get_function("get_amplifier_enabled", "_get_boolean", "CDO")

    def test_get_amplifier_information(self):
        """KoherasBoostikLaserAmplifier.get_amplifier_information(), happy flow."""
        self._test_get_function("get_amplifier_information", "_get_string", "CDI")

    def test_set_current_setpoint(self):
        """KoherasBoostikLaserAmplifier.set_current_setpoint(), happy flow."""
        mock_value = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr._get_float = MagicMock(return_value=mock_resp)

        rt_val = self._meta.instr.set_current_setpoint(mock_value)
        self.assertEqual(rt_val, mock_resp)
        self._meta.instr._get_float.assert_called_once_with(f"ACC {mock_value}")

    def test_set_amplifier_enabled(self):
        """KoherasBoostikLaserAmplifier.set_amplifier_enabled(), happy flow."""
        mock_value = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr._get_boolean = MagicMock(return_value=mock_resp)

        rt_val = self._meta.instr.set_amplifier_enabled(mock_value)
        self.assertEqual(rt_val, mock_resp)
        self._meta.instr._get_boolean.assert_called_once_with(
            f"CDO {int(bool(mock_value))}"
        )
