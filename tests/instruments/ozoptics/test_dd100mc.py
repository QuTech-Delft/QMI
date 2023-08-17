"""Test for the Ozoptics DD100MC driver."""

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast

from dataclasses import dataclass


from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_Transport
from qmi.instruments.ozoptics.dd100mc import OZOptics_DD100MC


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    transport_str: MagicMock
    name: MagicMock
    super: MagicMock
    instr: OZOptics_DD100MC


class TestOZOptics_DD100MC(TestCase):
    """Testcase for the OZOptics_DD100MC class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.ozoptics.dd100mc.create_transport",
            return_value=mock_transport,
        ):
            instr = OZOptics_DD100MC(MagicMock(), mock_name, mock_transport_str)

        self._patcher_super = patch(
            "qmi.instruments.ozoptics.dd100mc.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(OZOptics_DD100MC, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """OZOptics_DD100MC.__init__(), happy flow."""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)

    def test_open(self):
        """OZOptics_DD100MC.open(), happy flow."""
        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.transport.discard_read.assert_called_once_with()
        self._meta.super().open.assert_called_once_with()

    def test_close(self):
        """OZOptics_DD100MC.close(), happy flow."""
        self._meta.instr.close()
        self._meta.transport.close.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_read_response(self):
        """OZOptics_DD100MC._read_response(), happy flow."""
        mock_timeout = MagicMock()
        mock_resp = [i.encode("ascii") for i in ["RESPONSE\r\n", "Done\r\n", "\r\n"]]

        self._meta.instr._check_is_open = MagicMock()
        self._meta.transport.read_until = MagicMock(side_effect=mock_resp)

        rt_val = self._meta.instr._read_response(mock_timeout)

        self.assertEqual(rt_val[0], "RESPONSE")
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.transport.read_until.assert_has_calls(
            [
                call(b"\r\n", mock_timeout),
            ]
            * 3
        )

    def test_execute_command(self):
        """OZOptics_DD100MC._execute_command(), happy flow."""
        mock_cmd = "CD"
        mock_timeout = MagicMock()

        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._read_response = MagicMock()

        rt_val = self._meta.instr._execute_command(mock_cmd, mock_timeout)
        self._meta.transport.write.assert_called_once_with(
            (mock_cmd + "\r").encode("ascii")
        )
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.instr._read_response.assert_called_once_with(mock_timeout)
        self.assertEqual(rt_val, self._meta.instr._read_response())

    def test_get_configuration_display(self):
        """OZOptics_DD100MC.get_configuration_display(), happy flow."""

        self._meta.instr._execute_command = MagicMock()
        rt_val = self._meta.instr.get_configuration_display()

        self._meta.instr._execute_command.assert_called_once_with(
            "CD", self._meta.instr.RESPONSE_TIMEOUT
        )
        self.assertEqual(rt_val, self._meta.instr._execute_command())

    def test_home(self):
        """OZOptics_DD100MC.home(), happy flow."""

        self._meta.instr._execute_command = MagicMock()
        self._meta.instr.home()

        self._meta.instr._execute_command.assert_called_once_with(
            "H", self._meta.instr.RESPONSE_TIMEOUT_HOME_COMMAND
        )

    def test_get_position(self):
        """OZOptics_DD100MC.get_position(), happy flow."""
        mock_steps = 10000
        mock_atten = 0.0001
        mock_resp = [f"DPos:{mock_steps}", f"ATTEN:{mock_atten}"]
        self._meta.instr._execute_command = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_position()

        self._meta.instr._execute_command.assert_called_once_with(
            "D", self._meta.instr.RESPONSE_TIMEOUT
        )
        self.assertEqual(rt_val.steps, mock_steps)
        self.assertEqual(rt_val.attenuation, mock_atten)

    def test_get_position_invalid_response(self):
        """OZOptics_DD100MC.get_position(), invalid response handling."""

        def test_response(response):
            self._meta.instr._execute_command = MagicMock(return_value=response)
            with self.assertRaises(QMI_InstrumentException):
                self._meta.instr.get_position()

        test_response("")
        test_response(["DPos:10000", ""])
        test_response(["", "ATTEN:0.0001"])

    def test_set_attenuation(self):
        """OZOptics_DD100MC.set_attenuation(), happy flow."""

        mock_value = 0.01
        mock_pos = 200
        mock_resp = [f"Pos:{mock_pos}"]
        self._meta.instr._execute_command = MagicMock(return_value=mock_resp)

        rt_val = self._meta.instr.set_attenuation(mock_value)

        self._meta.instr._execute_command.assert_called_once_with(
            f"A{mock_value:.2f}", self._meta.instr.RESPONSE_TIMEOUT
        )
        self.assertEqual(rt_val, mock_pos)

    def test_set_attenuation_invalid_response(self):
        """OZOptics_DD100MC.set_attenuation(), invalid response handling."""

        def test_response(response):
            self._meta.instr._execute_command = MagicMock(return_value=response)
            with self.assertRaises(QMI_InstrumentException):
                self._meta.instr.set_attenuation(0.01)

        test_response("")
        test_response([""])
