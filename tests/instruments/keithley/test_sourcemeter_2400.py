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
    transport_str: MagicMock
    name: MagicMock
    scpi: MagicMock
    super: MagicMock
    instr: Keithley_Sourcemeter2400


class TestKeithleySourcemeter2400(TestCase):
    """Testcase for the Keithley_Sourcemeter2400 class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_scpi = MagicMock(spec=ScpiProtocol)
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.keithley.sourcemeter_2400.create_transport",
            return_value=mock_transport,
        ), patch(
            "qmi.instruments.keithley.sourcemeter_2400.ScpiProtocol", mock_scpi
        ):
            instr = Keithley_Sourcemeter2400(MagicMock(), mock_name, mock_transport_str)

        self._patcher_super = patch(
            "qmi.instruments.keithley.sourcemeter_2400.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(Keithley_Sourcemeter2400, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            scpi=mock_scpi(mock_transport),
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """Keithley_Sourcemeter2400.__init__(), happy flow."""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)
        self.assertEqual(self._meta.instr._scpi_protocol, self._meta.scpi)

    def test_open(self):
        """Keithley_Sourcemeter2400.open(), happy flow."""
        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.scpi.write.assert_called_once_with(":FORM:ELEM VOLT")
        self._meta.super().open.assert_called_once_with()

    def test_open_exception(self):
        """Keithley_Sourcemeter2400.open(), exception on write."""
        self._meta.scpi.write = MagicMock(side_effect=Exception)
        with self.assertRaises(Exception):
            self._meta.instr.open()
        self._meta.transport.close.assert_called_once_with()

    def test_close(self):
        """Keithley_Sourcemeter2400.close(), happy flow."""
        self._meta.instr.close()
        self._meta.transport.close.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_check_error(self):
        """Keithley_Sourcemeter2400._check_error(), happy flow."""
        self._meta.scpi.ask = MagicMock(return_value='0,"No error"')
        self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with(":SYST:ERR?")

    def test_check_error_raises(self):
        """Keithley_Sourcemeter2400._check_error(), error handling."""
        self._meta.scpi.ask = MagicMock(return_value='-222,"Data out of range"')
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with(":SYST:ERR?")

    def test_check_error_invalid_response(self):
        """Keithley_Sourcemeter2400._check_error(), invalid response handling."""
        self._meta.scpi.ask = MagicMock(return_value="notacode")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error(MagicMock())
        self._meta.scpi.ask.assert_called_once_with(":SYST:ERR?")

    def test_set_command(self):
        """Keithley_Sourcemeter2400._set_command(), happy flow."""
        mock_cmd = MagicMock()
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr._set_command(mock_cmd)
        self._meta.scpi.write.assert_called_once_with(mock_cmd)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.instr._check_error.assert_called_once_with(mock_cmd)

    def test_ask_float(self):
        """Keithley_Sourcemeter2400._ask_float(), happy flow."""
        mock_cmd = MagicMock()
        mock_resp = "0.012500"
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._ask_float(mock_cmd)
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
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
        self._meta.scpi.ask.assert_called_once_with(mock_cmd)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_reset(self):
        """Keithley_Sourcemeter2400.reset(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.reset()
        self._meta.scpi.write.assert_called_once_with("*RST")
        self._meta.scpi.ask.assert_called_once_with("*OPC?", timeout=self._meta.instr.RESET_RESPONSE_TIMEOUT)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.instr._check_error.assert_called_once_with("*RST")

    def test_get_idn(self):
        """Keithley_Sourcemeter2400.get_idn(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        mock_idn = "KEITHLEY INSTRUMENTS INC.,MODEL 2400,1234567,C32 Mar 17 2006 09:58:53/A02"
        self._meta.scpi.ask = MagicMock(return_value=mock_idn)
        rt_val = self._meta.instr.get_idn()
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")
        self.assertEqual(rt_val.vendor, "KEITHLEY INSTRUMENTS INC.")
        self.assertEqual(rt_val.model, "MODEL 2400")
        self.assertEqual(rt_val.serial, "1234567")
        self.assertEqual(rt_val.version, "C32 Mar 17 2006 09:58:53/A02")

    def test_get_idn_invalid_response(self):
        """Keithley_Sourcemeter2400.get_idn(), invalid response handling."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_idn()
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")

    def test_set_source_function(self):
        """Keithley_Sourcemeter2400.set_source_function(), happy flow."""
        for function in SourceFunction:
            self._meta.instr._set_command = MagicMock()
            self._meta.instr.set_source_function(function)
            self._meta.instr._set_command.assert_called_once_with(f":SOUR:FUNC:MODE {function.value}")

    def test_get_source_function(self):
        """Keithley_Sourcemeter2400.get_source_function(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        for function in SourceFunction:
            self._meta.scpi.ask = MagicMock(return_value=function.value)
            rt_val = self._meta.instr.get_source_function()
            self._meta.scpi.ask.assert_called_once_with(":SOUR:FUNC:MODE?")
            self.assertEqual(rt_val, function)

    def test_get_source_function_invalid_response(self):
        """Keithley_Sourcemeter2400.get_source_function(), invalid response handling."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value="BOGUS")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_source_function()

    def test_set_source_voltage(self):
        """Keithley_Sourcemeter2400.set_source_voltage(), happy flow."""
        mock_voltage = 1.5
        self._meta.instr._set_command = MagicMock()
        self._meta.instr.set_source_voltage(mock_voltage)
        self._meta.instr._set_command.assert_called_once_with(f":SOUR:VOLT:LEV {mock_voltage:.6g}")

    def test_get_source_voltage(self):
        """Keithley_Sourcemeter2400.get_source_voltage(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_source_voltage()
        self._meta.instr._ask_float.assert_called_once_with(":SOUR:VOLT:LEV?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_source_current(self):
        """Keithley_Sourcemeter2400.set_source_current(), happy flow."""
        mock_current = 0.01
        self._meta.instr._set_command = MagicMock()
        self._meta.instr.set_source_current(mock_current)
        self._meta.instr._set_command.assert_called_once_with(f":SOUR:CURR:LEV {mock_current:.6g}")

    def test_get_source_current(self):
        """Keithley_Sourcemeter2400.get_source_current(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_source_current()
        self._meta.instr._ask_float.assert_called_once_with(":SOUR:CURR:LEV?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_sense_function(self):
        """Keithley_Sourcemeter2400.set_sense_function(), happy flow."""
        for function in SenseFunction:
            self._meta.instr._set_command = MagicMock()
            self._meta.instr.set_sense_function(function)
            self._meta.instr._set_command.assert_called_once_with(f':SENS:FUNC:ON "{function.value}"')

    def test_get_sense_function(self):
        """Keithley_Sourcemeter2400.get_sense_function(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        for function in SenseFunction:
            self._meta.scpi.ask = MagicMock(return_value=f'"{function.value}"')
            rt_val = self._meta.instr.get_sense_function()
            self._meta.scpi.ask.assert_called_once_with(":SENS:FUNC:ON?")
            self.assertEqual(rt_val, function)

    def test_get_sense_function_multiple(self):
        """Keithley_Sourcemeter2400.get_sense_function(), multiple enabled functions, first one is returned."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value='"VOLT:DC","CURR:DC"')
        rt_val = self._meta.instr.get_sense_function()
        self.assertEqual(rt_val, SenseFunction.VOLTAGE)

    def test_get_sense_function_invalid_response(self):
        """Keithley_Sourcemeter2400.get_sense_function(), invalid response handling."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value='"BOGUS"')
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_sense_function()

    def test_measure_voltage(self):
        """Keithley_Sourcemeter2400.measure_voltage(), happy flow."""
        mock_resp = MagicMock()
        self._meta.instr._ask_float = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.measure_voltage()
        self._meta.instr._ask_float.assert_called_once_with(":READ?")
        self.assertEqual(rt_val, mock_resp)

    def test_set_output_enabled(self):
        """Keithley_Sourcemeter2400.set_output_enabled(), happy flow."""
        for enable in (True, False):
            self._meta.instr._set_command = MagicMock()
            self._meta.instr.set_output_enabled(enable)
            self._meta.instr._set_command.assert_called_once_with(f":OUTP {int(enable)}")

    def test_get_output_enabled(self):
        """Keithley_Sourcemeter2400.get_output_enabled(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        for resp, expected in (("1", True), ("ON", True), ("0", False), ("OFF", False)):
            self._meta.scpi.ask = MagicMock(return_value=resp)
            rt_val = self._meta.instr.get_output_enabled()
            self._meta.scpi.ask.assert_called_once_with(":OUTP?")
            self.assertEqual(rt_val, expected)
