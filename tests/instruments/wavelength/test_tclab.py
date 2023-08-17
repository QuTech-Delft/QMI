"""Test for the Wavelength TC Lab driver."""

import logging

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast

from dataclasses import dataclass


from qmi.core.transport import QMI_Transport
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.instruments.wavelength import Wavelength_TcLab
from qmi.instruments.wavelength import AutotuneMode
from qmi.core.exceptions import QMI_InstrumentException


# Disable all logging
logging.disable(logging.CRITICAL)


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    transport_str: MagicMock
    name: MagicMock
    scpi: MagicMock
    super: MagicMock
    instr: Wavelength_TcLab


class TestParameters:
    """Test parameter data for UsbTmcTransportDescriptorParser."""

    def __init__(self, vendor_id, product_id):
        self.vendorid = vendor_id
        self.productid = product_id

    def get(self, str):
        return getattr(self, str)


class TestWavelengthTCLab(TestCase):
    """Testcase for the Wavelength_TcLab class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_scpi = MagicMock(spec=ScpiProtocol)
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.wavelength.tclab.create_transport",
            return_value=mock_transport,
        ), patch("qmi.instruments.wavelength.tclab.ScpiProtocol", mock_scpi):
            instr = Wavelength_TcLab(MagicMock(), mock_name, mock_transport_str)

        self._patcher_super = patch(
            "qmi.instruments.wavelength.tclab.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(Wavelength_TcLab, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            scpi=mock_scpi(mock_transport),
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_list_instruments(self):
        """Wavelength_TcLab.list_instruments(), happy flow."""
        map = [
            {"instr": MagicMock(), "param": TestParameters(0x1A45, 0x3101)},
            {"instr": MagicMock(), "param": TestParameters(0x0000, 0x3101)},
            {"instr": MagicMock(), "param": TestParameters(0x1A45, 0x0000)},
            {"instr": MagicMock(), "param": TestParameters(0x1A45, 0x3101)},
        ]
        mock_lister = MagicMock(return_value=[item["instr"] for item in map])

        def helper_parse(transport):
            for item in map:
                if item["instr"] == transport:
                    return item["param"]

        mock_parser = MagicMock()
        mock_parser.parse_parameter_strings = MagicMock(side_effect=helper_parse)

        with patch(
            "qmi.instruments.wavelength.tclab.list_usbtmc_transports", mock_lister
        ), patch(
            "qmi.instruments.wavelength.tclab.UsbTmcTransportDescriptorParser",
            mock_parser,
        ):
            rt_val = self._meta.instr.list_instruments()

        self.assertTrue(map[0]["instr"] in rt_val)
        self.assertTrue(map[3]["instr"] in rt_val)

    def test_init(self):
        """Wavelength_TcLab.__init__(), happy flow."""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)
        self.assertEqual(self._meta.instr._scpi_protocol, self._meta.scpi)

    def test_open_transport(self):
        """Wavelength_TcLab._open_transport(), happy flow."""
        self._meta.instr._open_transport()
        self._meta.transport.open.assert_called_once_with()

    def test_open_transport_retry_exceed(self):
        """Wavelength_TcLab._open_transport(), retry exceeded."""
        mock_open_max_retry = 3
        self._meta.instr.OPEN_MAX_RETRY = mock_open_max_retry
        self._meta.transport.open = MagicMock(side_effect=Exception)
        with patch("qmi.instruments.wavelength.tclab.time", MagicMock()):
            with self.assertRaises(Exception):
                self._meta.instr._open_transport()
        self._meta.transport.open.assert_has_calls([call()] * mock_open_max_retry)

    def test_open(self):
        """Wavelength_TcLab.open(), happy flow."""
        self._meta.instr._check_is_closed = MagicMock()
        self._meta.instr._open_transport = MagicMock()

        self._meta.instr.open()
        self._meta.scpi.write.assert_has_calls([call("*CLS"), call("RADIX DEC")])
        self._meta.scpi.ask.assert_called_once_with("ERRSTR?")
        self._meta.super().open.assert_called_once_with()
        self._meta.instr._check_is_closed.assert_called_once_with()
        self._meta.instr._open_transport.assert_called_once_with()

    def test_open_exception(self):
        """Wavelength_TcLab.open(), exception handling."""
        self._meta.instr._check_is_closed = MagicMock()
        self._meta.instr._open_transport = MagicMock()
        self._meta.scpi.write = MagicMock(side_effect=Exception)

        with self.assertRaises(Exception):
            self._meta.instr.open()

        self._meta.transport.close.assert_called_once_with()
        self._meta.instr._check_is_closed.assert_called_once_with()
        self._meta.instr._open_transport.assert_called_once_with()

    def test_close(self):
        """Wavelength_TcLab.close(), happy flow."""
        self._meta.instr.close()
        self._meta.super().close.assert_called_once_with()
        self._meta.transport.close.assert_called_once_with()

    def test_check_error(self):
        """Wavelength_TcLab._check_error(), happy flow."""
        mock_resp = "0,No error"
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        self._meta.instr._check_error()
        self._meta.scpi.ask.assert_called_once_with("ERRSTR?")

    def test_check_error_is_error(self):
        """Wavelength_TcLab._check_error(), is error."""
        mock_resp = "1,No error"
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error()
        self._meta.scpi.ask.assert_called_once_with("ERRSTR?")

    def test_ask_int(self):
        """Wavelength_TcLab._ask_int(), happy flow."""
        mock_resp = 18
        mock_cmd = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_int(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self.assertEqual(rt_val, mock_resp)

    def test_ask_int_exception(self):
        """Wavelength_TcLab._ask_int(), exception handling."""
        mock_resp = "notanint"
        mock_cmd = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._ask_int(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)

    def test_ask_float(self):
        """Wavelength_TcLab.ask_float(), happy flow."""
        mock_resp = 0.001
        mock_cmd = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self.assertEqual(rt_val, mock_resp)

    def test_ask_float_exception(self):
        """Wavelength_TcLab._ask_float(), exception handling."""
        mock_resp = "notafloat"
        mock_cmd = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)

    def test_reset(self):
        """Wavelength_TcLab.reset(), happy flow."""
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.reset()
        self._meta.scpi.write.assert_has_calls([call("*CLS"), call("*RST")])
        self._meta.scpi.ask.assert_called_once_with("*OPC?")
        self._meta.instr._check_error.assert_called_once_with()

    def test_get_idn(self):
        """Wavelength_TcLab.get_idn(), happy flow."""
        mock_resp = "VENDOR,MODEL,SERIAL,VERSION"
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_idn()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")
        self.assertEqual(rt_val.vendor, "VENDOR")
        self.assertEqual(rt_val.model, "MODEL")
        self.assertEqual(rt_val.serial, "SERIAL")
        self.assertEqual(rt_val.version, "VERSION")

    def test_get_idn_invalid_response(self):
        """Wavelength_TcLab.get_idn(), exception handling."""
        mock_resp = ""
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_idn()

    def test_get_power_on(self):
        """Wavelength_TcLab.get_power_on(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_int = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_power_on()
        self._meta.instr._ask_int.assert_called_once_with("PWR?")
        self.assertEqual(rt_val, bool(mock_resp))

    def _test_set_bool(self, function_name, expected_str):
        mock_power_on = [True, False]
        for item in mock_power_on:
            self._meta.scpi.write = MagicMock()
            self._meta.instr._check_error = MagicMock()
            getattr(self._meta.instr, function_name)(item)
            self._meta.scpi.write.assert_called_once_with(f"{expected_str} {int(item)}")
            self._meta.instr._check_error.assert_called_once_with()

    def test_set_power_on(self):
        """Wavelength_TcLab.set_power_on(), happy flow."""
        self._test_set_bool("set_power_on", "PWR")

    def test_set_output_enabled(self):
        """Wavelength_TcLab.set_output_enabled(), happy flow."""
        self._test_set_bool("set_output_enabled", "TEC:OUTPUT")

    def _test_get_float(self, function_name, expected_string):
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = getattr(self._meta.instr, function_name)()
        self._meta.instr._ask_float.assert_called_once_with(expected_string)
        self.assertEqual(rt_val, mock_resp)

    def test_get_temperature(self):
        """Wavelength_TcLab.get_temperature(), happy flow."""
        self._test_get_float("get_temperature", "TEC:ACT?")

    def test_get_setpoint(self):
        """Wavelength_TcLab.get_setpoint(), happy flow."""
        self._test_get_float("get_setpoint", "TEC:SET?")

    def test_get_tec_current(self):
        """Wavelength_TcLab.get_tec_current(), happy flow."""
        self._test_get_float("get_tec_current", "TEC:I?")

    def test_get_tec_voltage(self):
        """Wavelength_TcLab.get_tec_voltage(), happy flow."""
        self._test_get_float("get_tec_voltage", "TEC:V?")

    def test_get_tec_voltage_limit(self):
        """Wavelength_TcLab.get_tec_voltage_limit(), happy flow."""
        self._test_get_float("get_tec_voltage_limit", "TEC:VLIM?")

    def test_set_setpoint(self):
        """Wavelength_TcLab.set_setpoint(), happy flow."""
        mock_setpoint = 0.001
        self._meta.scpi.write = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.set_setpoint(mock_setpoint)
        self._meta.scpi.write.assert_called_once_with(
            "TEC:SET {:.6f}".format(mock_setpoint)
        )
        self._meta.instr._check_error.assert_called_once_with()

    def test_get_unit(self):
        """Wavelength_TcLab.get_unit(), happy flow."""
        mock_resp = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_unit()
        self._meta.scpi.ask.assert_called_once_with("TEC:UNITS?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_unit(self):
        """Wavelength_TcLab.set_unit(), happy flow."""
        mock_unit = "celsius"
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.set_unit(mock_unit)
        self._meta.scpi.write.assert_called_once_with("TEC:UNITS CELSIUS")
        self._meta.instr._check_error.assert_called_once_with()

    def test_set_unit_value_error(self):
        """Wavelength_TcLab.set_unit(), exception handling."""
        mock_unit = "INVALID"
        with self.assertRaises(ValueError):
            self._meta.instr.set_unit(mock_unit)

    def test_get_output_enabled(self):
        """Wavelength_TcLab.get_output_enabled(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_int = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_output_enabled()
        self._meta.instr._ask_int.assert_called_once_with("TEC:OUTPUT?")
        self.assertEqual(rt_val, bool(mock_resp))

    def test_get_condition_status(self):
        """Wavelength_TcLab.get_condition_status(), happy flow."""
        map = [
            {"name": "current_limit", "mask": 1},
            {"name": "sensor_limit", "mask": 4},
            {"name": "temperature_high", "mask": 8},
            {"name": "temperature_low", "mask": 16},
            {"name": "sensor_shorted", "mask": 32},
            {"name": "sensor_open", "mask": 64},
            {"name": "tec_open", "mask": 128},
            {"name": "in_tolerance", "mask": 512},
            {"name": "output_on", "mask": 1024},
            {"name": "laser_shutdown", "mask": 2048},
            {"name": "power_on", "mask": 32768},
        ]
        for item in map:
            self._meta.instr._ask_int = MagicMock(return_value=item["mask"])
            rt_val = self._meta.instr.get_condition_status()
            for item2 in map:
                val = getattr(rt_val, item2["name"])
                if item["name"] == item2["name"]:
                    self.assertEqual(
                        val,
                        True,
                        msg=f"{item['name']}, {item2['name']}, {item['mask']}, {rt_val}",
                    )
                else:
                    self.assertEqual(
                        val,
                        False,
                        msg=f"{item['name']}, {item2['name']}, {item['mask']}, {rt_val}",
                    )
            self._meta.instr._ask_int.assert_called_once_with("TEC:COND?")

    def test_get_pid_parameter(self):
        """Wavelength_TcLab.get_pid_parameter(), happy flow."""
        mock_resp = "0.01,0.02,0.03"
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val1, rt_val2, rt_val3 = self._meta.instr.get_pid_parameters()
        self._meta.scpi.ask.assert_called_once_with("TEC:PID?")
        self.assertEqual(rt_val1, 0.01)
        self.assertEqual(rt_val2, 0.02)
        self.assertEqual(rt_val3, 0.03)

    def test_get_pid_parameter_invalid_response(self):
        """Wavelength_TcLab.get_pid_parameter(), invalid response."""
        mock_resp = ""
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_pid_parameters()
        self._meta.scpi.ask.assert_called_once_with("TEC:PID?")

    def test_get_pid_parameter_invalid_value(self):
        """Wavelength_TcLab.get_pid_parameter(), invalid value."""
        mock_resp = "notvalid,notvalid,notvalid"
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_pid_parameters()
        self._meta.scpi.ask.assert_called_once_with("TEC:PID?")

    def test_set_pid_parameter(self):
        """Wavelength_TcLab.set_pid_parameter(), happy flow."""
        mock_p = 0.001
        mock_i = 0.002
        mock_d = 0.003
        self._meta.scpi.write = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.set_pid_parameters(mock_p, mock_i, mock_d)
        self._meta.scpi.write.assert_called_once_with("TEC:PID 0.0010,0.0020,0.0030")
        self._meta.instr._check_error.assert_called_once_with()

    def test_get_autotune_mode(self):
        """Wavelength_TcLab.get_autotune_mode(), happy flow."""
        map = [
            {"resp": 0, "expected_rt_val": AutotuneMode.MANUAL},
            {"resp": 1, "expected_rt_val": AutotuneMode.DISTURB_REJECT},
            {"resp": 2, "expected_rt_val": AutotuneMode.SETPOINT_RESPONSE},
        ]

        for item in map:
            self._meta.instr._ask_int = MagicMock(return_value=item["resp"])
            rt_val = self._meta.instr.get_autotune_mode()
            self.assertEqual(rt_val, item["expected_rt_val"])
            self._meta.instr._ask_int.assert_called_once_with("TEC:AUTOTUNE?")

    def test_set_autotune_mode(self):
        """Wavelength_TcLab.set_autotune_mode(), happy flow."""
        mock_mode = AutotuneMode.DISTURB_REJECT
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.set_autotune_mode(mock_mode)
        self._meta.scpi.write.assert_called_once_with(f"TEC:AUTOTUNE {mock_mode.value}")
        self._meta.instr._check_error.assert_called_once_with()

    def test_start_autotune(self):
        """Wavelength_TcLab.start_autotune(), happy flow."""
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.start_autotune()
        self._meta.scpi.write.assert_called_once_with("TEC:TUNESTART")
        self._meta.instr._check_error.assert_called_once_with()

    def test_abort_autotune(self):
        """Wavelength_TcLab.abort_autotune(), happy flow."""
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.abort_autotune()
        self._meta.scpi.write.assert_called_once_with("TEC:TUNEABORT")
        self._meta.instr._check_error.assert_called_once_with()

    def test_get_autotune_is_valid(self):
        """Wavelength_TcLab.get_autotune_is_valid(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_int = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_autotune_is_valid()
        self.assertEqual(rt_val, bool(mock_resp))
        self._meta.instr._ask_int.assert_called_once_with("TEC:VALID?")

    def _test_get_float_tuple(self, function_name, test_cmd_1, test_cmd_2):
        mock_resp_1 = MagicMock()
        mock_resp_2 = MagicMock()

        def se_ask_float(cmd):
            if cmd == test_cmd_1:
                return mock_resp_1
            elif cmd == test_cmd_2:
                return mock_resp_2

        self._meta.instr._ask_float = MagicMock(side_effect=se_ask_float)
        rt_val = getattr(self._meta.instr, function_name)()
        self.assertEqual(rt_val[0], mock_resp_1)
        self.assertEqual(rt_val[1], mock_resp_2)

    def test_get_temperature_limit(self):
        """Wavelength_TcLab.get_temperature_limit(), happy flow."""
        self._test_get_float_tuple(
            "get_temperature_limit", "TEC:LIM:TLO?", "TEC:LIM:THI?"
        )

    def test_get_tec_current_limit(self):
        """Wavelength_TcLab.get_tec_current_limit(), happy flow."""
        self._test_get_float_tuple(
            "get_tec_current_limit", "TEC:LIM:IPOS?", "TEC:LIM:INEG?"
        )

    def _test_set_scpi_tuple(self, function_name, test_cmd_1, test_cmd_2):
        mock_arg_1 = 0.001
        mock_arg_2 = 0.002

        self._meta.instr._check_error = MagicMock()
        self._meta.scpi.write = MagicMock()
        getattr(self._meta.instr, function_name)(mock_arg_1, mock_arg_2)
        self._meta.scpi.write.assert_has_calls(
            [
                call(f"{test_cmd_1} {mock_arg_1:.4f}"),
                call(f"{test_cmd_2} {mock_arg_2:.4f}"),
            ]
        )
        self._meta.instr._check_error.assert_called_once_with()

    def test_set_temperature_limit(self):
        """Wavelength_TcLab.set_temperature_limit(), happy flow."""
        self._test_set_scpi_tuple("set_temperature_limit", "TEC:LIM:TLO", "TEC:LIM:THI")

    def test_set_tec_current_limit(self):
        """Wavelength_TcLab.set_tec_current_limit(), happy flow."""
        self._test_set_scpi_tuple(
            "set_tec_current_limit", "TEC:LIM:IPOS", "TEC:LIM:INEG"
        )

    def test_set_tec_voltage_limit(self):
        """Wavelength_TcLab.set_tec_voltage_limit(), happy flow."""
        mock_vlim = 0.001
        self._meta.instr._check_error = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr.set_tec_voltage_limit(mock_vlim)
        self._meta.scpi.write.assert_called_once_with(f"TEC:VLIM {mock_vlim:.4f}")
        self._meta.instr._check_error.assert_called_once_with()
