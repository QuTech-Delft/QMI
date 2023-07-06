from unittest import TestCase
from unittest.mock import patch
from unittest.mock import MagicMock
from unittest.mock import call


from dataclasses import dataclass

from typing import cast

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import QMI_Transport
from qmi.instruments.stanford_research_systems.dc205 import SRS_DC205


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    transport_str: MagicMock
    name: MagicMock
    scpi: MagicMock
    super: MagicMock
    instr: SRS_DC205


class TestDC205(TestCase):
    """Testcase for the SRS_DC205 class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_scpi = MagicMock(spec=ScpiProtocol)
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.stanford_research_systems.dc205.create_transport",
            return_value=mock_transport,
        ), patch(
            "qmi.instruments.stanford_research_systems.dc205.ScpiProtocol", mock_scpi
        ):
            instr = SRS_DC205(MagicMock(), mock_name, mock_transport_str)

        self._patcher_super = patch(
            "qmi.instruments.stanford_research_systems.dc205.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(SRS_DC205, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            scpi=mock_scpi(mock_transport),
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """SRS_DC205.__init__(), happy flow."""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)
        self.assertEqual(self._meta.instr._scpi_protocol, self._meta.scpi)

    def test_open(self):
        """SRS_DC205.open(), happy flow."""
        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.transport.write.assert_called_once_with(b"\nTERM LF\n")
        self._meta.super().open.assert_called_once_with()

    def test_open_exception(self):
        """SRS_DC205.open(), exception on write."""
        self._meta.transport.write = MagicMock(side_effect=Exception)
        with self.assertRaises(Exception):
            self._meta.instr.open()
        self._meta.transport.close.assert_called_once_with()

    def test_close(self):
        """SRS_DC205.close(), happy flow."""
        self._meta.instr.close()
        self._meta.transport.close.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_check_error(self):
        """SRS_DC205._check_error(), happy flow."""
        self._meta.scpi.ask = MagicMock(return_value="0;0")
        self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with("LEXE?; LCME?")

    def test_check_error_execution_error(self):
        """SRS_DC205._check_error(), execution error handling."""
        self._meta.scpi.ask = MagicMock(return_value="1;0")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with("LEXE?; LCME?")

    def test_check_error_command_error(self):
        """SRS_DC205._check_error(), command error handling."""
        self._meta.scpi.ask = MagicMock(return_value="0;1")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with("LEXE?; LCME?")

    def test_check_error_invalid_response(self):
        """SRS_DC205._check_error(), invalid response handling."""
        self._meta.scpi.ask = MagicMock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with("LEXE?; LCME?")

    def test_set_command(self):
        """SRS_DC205._set_command(), happy flow."""
        mock_cmd = MagicMock()
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr._set_command(mock_cmd)
        self._meta.scpi.write.assert_called_once_with(mock_cmd)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.instr._check_error.assert_called_once_with(mock_cmd)

    def test_ask_float(self):
        """SRS_DC205._ask_float(), happy flow."""
        mock_cmd = MagicMock()
        mock_resp = "0.01"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self._meta.instr._check_is_open.assert_called_once_with()
        self.assertEqual(rt_val, float(mock_resp))

    def test_ask_float_value_error(self):
        """SRS_DC205._ask_float(), value error handling."""
        mock_cmd = MagicMock()
        mock_resp = "notafloat"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_ask_token(self):
        """SRS_DC205._ask_token(), happy flow, token."""
        mock_cmd = MagicMock()
        mock_tokens = [MagicMock(), MagicMock()]
        mock_resp = "1"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_token(mock_cmd, mock_tokens)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self.assertEqual(rt_val, int(mock_resp))

    def test_ask_token_in_tokens(self):
        """SRS_DC205._ask_token(), happy flow, index of token."""
        mock_cmd = MagicMock()
        mock_resp = "1"
        mock_index = 3
        mock_tokens = [MagicMock()] * (mock_index * 2)
        mock_tokens[mock_index] = mock_resp
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_token(mock_cmd, mock_tokens)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self.assertEqual(
            rt_val, mock_index
        )  # rt_val is the index of the token in mock_tokens

    def test_ask_token_no_int(self):
        """SRS_DC205._ask_token(), response is not an int handling."""
        mock_cmd = MagicMock()
        mock_tokens = [MagicMock(), MagicMock()]
        mock_resp = "notaint"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._ask_token(mock_cmd, mock_tokens)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)

    def test_ask_token_invalid_response(self):
        """SRS_DC205._ask_token(), invalid response handling."""
        mock_cmd = MagicMock()
        mock_tokens = []
        mock_resp = "5"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._ask_token(mock_cmd, mock_tokens)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)

    def test_reset(self):
        """SRS_DC205.reset(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.reset()
        self._meta.scpi.ask.assert_has_calls(
            [
                call("LEXE?; LCME?", timeout=self._meta.instr.RESET_RESPONSE_TIMEOUT),
                call("*OPC?", timeout=self._meta.instr.RESET_RESPONSE_TIMEOUT),
            ]
        )
        self._meta.scpi.write.assert_called_once_with("*RST")
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.instr._check_error.assert_called_once_with("*RST")

    def test_get_idn(self):
        """SRS_DC205.get_idn(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value="VENDOR,MODEL,SERIAL,VERSION")
        rt_val = self._meta.instr.get_idn()
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")
        self.assertEqual(rt_val.vendor, "VENDOR")
        self.assertEqual(rt_val.model, "MODEL")
        self.assertEqual(rt_val.serial, "SERIAL")
        self.assertEqual(rt_val.version, "VERSION")

    def test_get_idn_invalid_response(self):
        """SRS_DC205.get_idn(), invalid response handling."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_idn()
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")

    def test_get_range(self):
        """SRS_DC205.get_range(), happy flow."""
        map_resp = [
            {"index": 0, "value": 1},
            {"index": 1, "value": 10},
            {"index": 2, "value": 100},
        ]
        for item in map_resp:
            self._meta.instr._ask_token = MagicMock(return_value=item["index"])
            rt_val = self._meta.instr.get_range()
            self._meta.instr._ask_token.assert_called_once_with(
                cmd="RNGE?", tokens=["RANGE1", "RANGE10", "RANGE100"]
            )
            self.assertEqual(rt_val, item["value"])

    def test_set_range(self):
        """SRS_DC205.set_range(), happy flow."""
        mock_volt_range = [1, 10, 100]
        for item in mock_volt_range:
            self._meta.instr._set_command = MagicMock()
            self._meta.instr.set_range(item)
            self._meta.instr._set_command.assert_called_once_with(f"RNGE RANGE{item}")

    def test_set_range_invalid_range(self):
        """SRS_DC205.set_range(), invalid range handling."""
        mock_volt_range = MagicMock()
        self._meta.instr._set_command = MagicMock()
        with self.assertRaises(ValueError):
            self._meta.instr.set_range(mock_volt_range)

    def test_get_output_enabled(self):
        """SRS_DC205.get_output_enabled(), happy flow."""
        mock_resp = [0, 1]
        for item in mock_resp:
            self._meta.instr._ask_token = MagicMock(return_value=item)
            rt_val = self._meta.instr.get_output_enabled()
            self._meta.instr._ask_token.assert_called_once_with(
                cmd="SOUT?", tokens=["OFF", "ON"]
            )
            self.assertEqual(rt_val, bool(item))

    def test_set_output_enabled(self):
        """SRS_DC205.set_output_enabled(), happy flow."""
        mock_enable = True
        self._meta.instr._set_command = MagicMock()
        self._meta.instr.set_output_enabled(mock_enable)
        self._meta.instr._set_command.assert_called_once_with(
            "SOUT {}".format(int(mock_enable))
        )

    def test_get_voltage(self):
        """SRS_DC205.get_voltage(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_voltage()
        self._meta.instr._ask_float.assert_called_once_with("VOLT?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_voltage(self):
        """SRS_DC205.set_voltage(), happy flow."""
        mock_voltage = 0.01
        self._meta.instr._set_command = MagicMock()
        self._meta.instr.set_voltage(mock_voltage)
        self._meta.instr._set_command.assert_called_once_with(
            "VOLT {:.6f}".format(mock_voltage)
        )

    def test_get_output_floating(self):
        """SRS_DC205.get_output_floating(), happy flow."""
        mock_resp = [0, 1]
        for item in mock_resp:
            self._meta.instr._ask_token = MagicMock(return_value=item)
            rt_val = self._meta.instr.get_output_floating()
            self._meta.instr._ask_token.assert_called_once_with(
                cmd="ISOL?", tokens=["GROUND", "FLOAT"]
            )
            self.assertEqual(rt_val, bool(item))

    def test_set_output_floating(self):
        """SRS_DC205.set_output_floating(), happy flow."""
        mock_enable = True
        self._meta.instr._set_command = MagicMock()
        self._meta.instr.set_output_floating(mock_enable)
        self._meta.instr._set_command.assert_called_once_with(
            "ISOL {}".format(int(mock_enable))
        )

    def test_get_sensing_enabled(self):
        """SRS_DC205.get_sensing_enabled(), happy flow."""
        mock_resp = [0, 1]
        for item in mock_resp:
            self._meta.instr._ask_token = MagicMock(return_value=item)
            rt_val = self._meta.instr.get_sensing_enabled()
            self._meta.instr._ask_token.assert_called_once_with(
                cmd="SENS?", tokens=["TWOWIRE", "FOURWIRE"]
            )
            self.assertEqual(rt_val, bool(item))

    def test_set_sensing_enabled(self):
        """SRS_DC205.set_sensing_enabled(), happy flow."""
        mock_enable = True
        self._meta.instr._set_command = MagicMock()
        self._meta.instr.set_sensing_enabled(mock_enable)
        self._meta.instr._set_command.assert_called_once_with(
            "SENS {}".format(int(mock_enable))
        )

    def test_get_interlock_status(self):
        """SRS_DC205.get_interlock_status(), happy flow."""
        mock_resp = [0, 1]
        for item in mock_resp:
            self._meta.instr._ask_token = MagicMock(return_value=item)
            rt_val = self._meta.instr.get_interlock_status()
            self._meta.instr._ask_token.assert_called_once_with(
                cmd="ILOC?", tokens=["OPEN", "CLOSED"]
            )
            self.assertEqual(rt_val, bool(item))

    def test_get_overloaded(self):
        """SRS_DC205.get_overloaded(), happy flow."""
        mock_resp = [0, 1]
        for item in mock_resp:
            self._meta.instr._ask_token = MagicMock(return_value=item)
            rt_val = self._meta.instr.get_overloaded()
            self._meta.instr._ask_token.assert_called_once_with(
                cmd="OVLD?", tokens=["OKAY", "OVLD"]
            )
            self.assertEqual(rt_val, bool(item))
