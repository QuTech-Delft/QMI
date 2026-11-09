from dataclasses import dataclass
from typing import cast
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import QMI_Transport
from qmi.instruments.keithley.sourcemeter_2400 import Keithley_Sourcemeter2400, SenseFunction, SourceFunction


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    name: MagicMock
    scpi: MagicMock
    super: MagicMock
    instr: Keithley_Sourcemeter2400


class TestKeithleySourcemeter2400(TestCase):
    """Testcase for the Keithley_Sourcemeter2400 class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_scpi = MagicMock(spec=ScpiProtocol)
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.keithley.sourcemeter_2400.create_transport",
            return_value=mock_transport,
        ), patch(
            "qmi.instruments.keithley.sourcemeter_2400.ScpiProtocol", mock_scpi
        ):
            instr = Keithley_Sourcemeter2400(MagicMock(), mock_name, "serial:/dev/ttyUSB0")

        self._patcher_super = patch(
            "qmi.instruments.keithley.sourcemeter_2400.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(Keithley_Sourcemeter2400, instr),
            name=mock_name,
            scpi=mock_scpi(mock_transport),
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        try:
            self._patcher_super.stop()
        except RuntimeError:
            pass

    def test_init_gpib(self):
        """Keithley_Sourcemeter2400.__init__(), GPIB transport, happy flow."""
        self._patcher_super.stop()
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_scpi = MagicMock(spec=ScpiProtocol)
        with patch(
            "qmi.instruments.keithley.sourcemeter_2400.create_transport", return_value=mock_transport
        ) as mock_create_transport, patch(
            "qmi.instruments.keithley.sourcemeter_2400.ScpiProtocol", mock_scpi
        ):
            instr = Keithley_Sourcemeter2400(MagicMock(), MagicMock(), "gpib:board=0:24")
        mock_create_transport.assert_called_once_with(
            "gpib:board=0:24",
            default_attributes={"primary_addr": Keithley_Sourcemeter2400.GPIB_DEFAULT_ADDR},
        )
        mock_scpi.assert_called_once_with(mock_transport, command_terminator="\n", response_terminator="\n")
        self.assertEqual(instr._transport, mock_transport)
        self.assertEqual(instr._scpi_protocol, mock_scpi(mock_transport))

    def test_init_serial(self):
        """Keithley_Sourcemeter2400.__init__(), RS-232 transport, happy flow."""
        self._patcher_super.stop()
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_scpi = MagicMock(spec=ScpiProtocol)
        with patch(
            "qmi.instruments.keithley.sourcemeter_2400.create_transport", return_value=mock_transport
        ) as mock_create_transport, patch(
            "qmi.instruments.keithley.sourcemeter_2400.ScpiProtocol", mock_scpi
        ):
            instr = Keithley_Sourcemeter2400(
                MagicMock(), MagicMock(), "serial:COM3:baudrate=19200", serial_terminator="\n"
            )
        mock_create_transport.assert_called_once_with(
            "serial:COM3:baudrate=19200",
            default_attributes=Keithley_Sourcemeter2400.SERIAL_DEFAULT_ATTRIBUTES,
        )
        mock_scpi.assert_called_once_with(mock_transport, command_terminator="\n", response_terminator="\n")
        self.assertEqual(instr._transport, mock_transport)

    def test_init_serial_default_terminator(self):
        """Keithley_Sourcemeter2400.__init__(), RS-232 transport, default terminator."""
        self._patcher_super.stop()
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_scpi = MagicMock(spec=ScpiProtocol)
        with patch(
            "qmi.instruments.keithley.sourcemeter_2400.create_transport", return_value=mock_transport
        ), patch(
            "qmi.instruments.keithley.sourcemeter_2400.ScpiProtocol", mock_scpi
        ):
            Keithley_Sourcemeter2400(MagicMock(), MagicMock(), "serial:COM3")
        mock_scpi.assert_called_once_with(mock_transport, command_terminator="\r", response_terminator="\r")

    def test_init_invalid_transport(self):
        """Keithley_Sourcemeter2400.__init__(), invalid transport type raises ValueError."""
        self._patcher_super.stop()
        with self.assertRaises(ValueError):
            Keithley_Sourcemeter2400(MagicMock(), MagicMock(), "usbtmc:0x1234:0x5678:SN1")

    def test_open(self):
        """Keithley_Sourcemeter2400.open(), happy flow."""
        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.super().open.assert_called_once_with()

    def test_close(self):
        """Keithley_Sourcemeter2400.close(), happy flow."""
        self._meta.instr.close()
        self._meta.transport.close.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_validate_function(self):
        """Keithley_Sourcemeter2400._validate_function(), happy flow."""
        for function in SourceFunction:
            self.assertEqual(Keithley_Sourcemeter2400._validate_function(function), function)
            self.assertEqual(Keithley_Sourcemeter2400._validate_function(function.value), function)

    def test_validate_function_invalid(self):
        """Keithley_Sourcemeter2400._validate_function(), invalid value handling."""
        with self.assertRaises(ValueError):
            Keithley_Sourcemeter2400._validate_function("BOGUS")

    def test_ask(self):
        """Keithley_Sourcemeter2400._ask(), happy flow."""
        mock_cmd = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd, timeout=self._meta.instr.DEFAULT_RESPONSE_TIMEOUT)
        self._meta.instr._check_is_open.assert_called_once_with()
        self.assertEqual(rt_val, mock_resp)

    def test_ask_float(self):
        """Keithley_Sourcemeter2400._ask_float(), happy flow."""
        mock_cmd = MagicMock()
        mock_resp = "0.012500"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd, timeout=self._meta.instr.DEFAULT_RESPONSE_TIMEOUT)
        self._meta.instr._check_is_open.assert_called_once_with()
        self.assertEqual(rt_val, float(mock_resp))

    def test_ask_float_value_error(self):
        """Keithley_Sourcemeter2400._ask_float(), value error handling."""
        mock_cmd = MagicMock()
        mock_resp = "notafloat"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd, timeout=self._meta.instr.DEFAULT_RESPONSE_TIMEOUT)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_reset(self):
        """Keithley_Sourcemeter2400.reset(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr.reset()
        self._meta.scpi.write.assert_called_once_with("*RST")
        self._meta.scpi.ask.assert_called_once_with("*OPC?", timeout=self._meta.instr.RESET_RESPONSE_TIMEOUT)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_idn(self):
        """Keithley_Sourcemeter2400.get_idn(), happy flow."""
        mock_idn = "KEITHLEY INSTRUMENTS INC.,MODEL 2400,1234567,C32 Mar 17 2006 09:58:53/A02"
        self._meta.instr._ask = MagicMock(return_value=mock_idn)
        rt_val = self._meta.instr.get_idn()
        self._meta.instr._ask.assert_called_once_with("*IDN?")
        self.assertEqual(rt_val.vendor, "KEITHLEY INSTRUMENTS INC.")
        self.assertEqual(rt_val.model, "MODEL 2400")
        self.assertEqual(rt_val.serial, "1234567")
        self.assertEqual(rt_val.version, "C32 Mar 17 2006 09:58:53/A02")

    def test_get_idn_invalid_response(self):
        """Keithley_Sourcemeter2400.get_idn(), invalid response handling."""
        self._meta.instr._ask = MagicMock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_idn()
        self._meta.instr._ask.assert_called_once_with("*IDN?")

    def test_set_source_function(self):
        """Keithley_Sourcemeter2400.set_source_function(), happy flow."""
        for function in SourceFunction:
            self._meta.instr._check_is_open = MagicMock()
            self._meta.scpi.write = MagicMock()
            self._meta.instr.set_source_function(function)
            self._meta.scpi.write.assert_called_once_with(f":SOUR:FUNC:MODE {function.value}")
            self._meta.instr._check_is_open.assert_called_once_with()

    def test_set_source_function_from_string(self):
        """Keithley_Sourcemeter2400.set_source_function(), string input happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr.set_source_function("VOLT")
        self._meta.scpi.write.assert_called_once_with(":SOUR:FUNC:MODE VOLT")

    def test_set_source_function_invalid(self):
        """Keithley_Sourcemeter2400.set_source_function(), invalid value handling."""
        with self.assertRaises(ValueError):
            self._meta.instr.set_source_function("BOGUS")

    def test_get_source_function(self):
        """Keithley_Sourcemeter2400.get_source_function(), happy flow."""
        for function in SourceFunction:
            self._meta.instr._ask = MagicMock(return_value=function.value)
            rt_val = self._meta.instr.get_source_function()
            self._meta.instr._ask.assert_called_once_with(":SOUR:FUNC:MODE?")
            self.assertEqual(rt_val, function.value)

    def test_get_source_function_invalid_response(self):
        """Keithley_Sourcemeter2400.get_source_function(), invalid response handling."""
        self._meta.instr._ask = MagicMock(return_value="BOGUS")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_source_function()

    def test_set_fixed_mode(self):
        """Keithley_Sourcemeter2400.set_fixed_mode(), happy flow."""
        for function in SourceFunction:
            self._meta.instr._check_is_open = MagicMock()
            self._meta.scpi.write = MagicMock()
            self._meta.instr.set_fixed_mode(function)
            self._meta.scpi.write.assert_called_once_with(f":SOUR:{function.value}:MODE FIXED")
            self._meta.instr._check_is_open.assert_called_once_with()

    def test_set_fixed_mode_from_string(self):
        """Keithley_Sourcemeter2400.set_fixed_mode(), string input happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr.set_fixed_mode("CURR")
        self._meta.scpi.write.assert_called_once_with(":SOUR:CURR:MODE FIXED")

    def test_get_function_mode(self):
        """Keithley_Sourcemeter2400.get_function_mode(), happy flow."""
        for function in SourceFunction:
            self._meta.instr._check_is_open = MagicMock()
            self._meta.instr._ask = MagicMock(return_value="FIXED")
            rt_val = self._meta.instr.get_function_mode(function)
            self._meta.instr._ask.assert_called_once_with(f":SOUR:{function.value}:MODE?")
            self._meta.instr._check_is_open.assert_called_once_with()
            self.assertEqual(rt_val, "FIXED")

    def test_set_source_voltage(self):
        """Keithley_Sourcemeter2400.set_source_voltage(), happy flow."""
        mock_voltage = 1.5
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr.set_source_voltage(mock_voltage)
        self._meta.scpi.write.assert_called_once_with(f":SOUR:VOLT {mock_voltage:.6g}")
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_source_voltage(self):
        """Keithley_Sourcemeter2400.get_source_voltage(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_source_voltage()
        self._meta.instr._ask_float.assert_called_once_with(":SOUR:VOLT?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_source_current(self):
        """Keithley_Sourcemeter2400.set_source_current(), happy flow."""
        mock_current = 0.01
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr.set_source_current(mock_current)
        self._meta.scpi.write.assert_called_once_with(f":SOUR:CURR {mock_current:.6g}")
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_source_current(self):
        """Keithley_Sourcemeter2400.get_source_current(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_source_current()
        self._meta.instr._ask_float.assert_called_once_with(":SOUR:CURR?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_sense_function(self):
        """Keithley_Sourcemeter2400.set_sense_function(), happy flow."""
        for function in SenseFunction:
            self._meta.instr._check_is_open = MagicMock()
            self._meta.scpi.write = MagicMock()
            self._meta.instr.set_sense_function(function)
            self._meta.scpi.write.assert_called_once_with(f":SENS:FUNC '{function.value}'")
            self._meta.instr._check_is_open.assert_called_once_with()

    def test_set_sense_function_from_string(self):
        """Keithley_Sourcemeter2400.set_sense_function(), string input happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr.set_sense_function("VOLT")
        self._meta.scpi.write.assert_called_once_with(":SENS:FUNC 'VOLT'")

    def test_set_sense_function_invalid(self):
        """Keithley_Sourcemeter2400.set_sense_function(), invalid value handling."""
        with self.assertRaises(ValueError):
            self._meta.instr.set_sense_function("BOGUS")

    def test_get_sense_function(self):
        """Keithley_Sourcemeter2400.get_sense_function(), happy flow."""
        for function in SenseFunction:
            self._meta.instr._ask = MagicMock(return_value=f'"{function.value}"')
            rt_val = self._meta.instr.get_sense_function()
            self._meta.instr._ask.assert_called_once_with(":SENS:FUNC?")
            self.assertEqual(rt_val, function)

    def test_get_sense_function_dc_suffix(self):
        """Keithley_Sourcemeter2400.get_sense_function(), response with ':DC' suffix is accepted."""
        for function in SenseFunction:
            self._meta.instr._ask = MagicMock(return_value=f'"{function.value}:DC"')
            rt_val = self._meta.instr.get_sense_function()
            self.assertEqual(rt_val, function)

    def test_get_sense_function_multiple(self):
        """Keithley_Sourcemeter2400.get_sense_function(), multiple enabled functions, first one is returned."""
        self._meta.instr._ask = MagicMock(return_value='"VOLT:DC","CURR:DC"')
        rt_val = self._meta.instr.get_sense_function()
        self.assertEqual(rt_val, SenseFunction.VOLTAGE)

    def test_get_sense_function_invalid_response(self):
        """Keithley_Sourcemeter2400.get_sense_function(), invalid response handling."""
        self._meta.instr._ask = MagicMock(return_value='"BOGUS"')
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_sense_function()

    def test_get_measured_voltage(self):
        """Keithley_Sourcemeter2400.get_measured_voltage(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.write = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_measured_voltage()
        self._meta.scpi.write.assert_called_once_with(":FORM:ELEM VOLT")
        self._meta.instr._ask_float.assert_called_once_with(":READ?")
        self._meta.instr._check_is_open.assert_called_once_with()
        self.assertEqual(rt_val, mock_resp)

    def test_set_output_state(self):
        """Keithley_Sourcemeter2400.set_output_state(), happy flow."""
        for enable, expected in ((True, "ON"), (False, "OFF")):
            self._meta.instr._check_is_open = MagicMock()
            self._meta.scpi.write = MagicMock()
            self._meta.instr.set_output_state(enable)
            self._meta.scpi.write.assert_called_once_with(f":OUTP {expected}")
            self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_output_state(self):
        """Keithley_Sourcemeter2400.get_output_state(), happy flow."""
        for resp, expected in (("1", True), ("0", False)):
            self._meta.instr._check_is_open = MagicMock()
            self._meta.instr._ask = MagicMock(return_value=resp)
            rt_val = self._meta.instr.get_output_state()
            self._meta.instr._ask.assert_called_once_with(":OUTP?")
            self.assertEqual(rt_val, expected)

    def test_get_output_state_invalid_response(self):
        """Keithley_Sourcemeter2400.get_output_state(), invalid response handling."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._ask = MagicMock(return_value="BOGUS")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_output_state()
