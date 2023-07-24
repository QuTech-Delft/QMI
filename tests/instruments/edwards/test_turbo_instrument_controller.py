"""Unit test for Edwards Turbo Instrument Controller."""

import logging
import unittest
from unittest.mock import Mock, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.edwards import EdwardsVacuum_TIC


class TestTurboInstrumentController(unittest.TestCase):

    def setUp(self):
        qmi.start("TestTICContext")
        # Add patches
        patcher = patch('qmi.instruments.edwards.turbo_instrument_controller.create_transport', spec=QMI_TcpTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.edwards.turbo_instrument_controller.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUTs
        self.instr: EdwardsVacuum_TIC = qmi.make_instrument(
            "test_instr", EdwardsVacuum_TIC, "transport_str")

    def tearDown(self):
        qmi.stop()

    def test_open_close(self):
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_get_idn(self):
        self.instr.open()

        actual_model = "model1"
        actual_version = "version2"
        actual_serial = "serial3"

        cmd = "?S902"

        self._scpi_mock.ask.return_value = f"=S902 {actual_model};{actual_version};{actual_serial}"
        instr_info = self.instr.get_idn()
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(instr_info.vendor, "Edwards")
        self.assertEqual(instr_info.model, actual_model)
        self.assertEqual(instr_info.version, actual_version)
        self.assertEqual(instr_info.serial, actual_serial)

        self.instr.close()

    def test_get_response_not_matching_valid_responses(self):
        self.instr.open()

        cmd = "?S902"

        self._scpi_mock.ask.return_value = f"=A902 0;0;0"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()
            self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_get_tic_status(self):
        self.instr.open()

        actual_turbo_pump_state = "Stopped"
        actual_backing_pump_state = "Accelerating"
        actual_gauge_state = "Zeroing"
        actual_alert = "Filament Fail"
        actual_priority = "warning"

        cmd = "?V902"

        self._scpi_mock.ask.return_value = "=V902 0;5;9;15;1"
        status = self.instr.get_tic_status()
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(status["Turbo pump state"], actual_turbo_pump_state)
        self.assertEqual(status["Backing pump state"], actual_backing_pump_state)
        self.assertEqual(status["Gauge 2"], actual_gauge_state)
        self.assertEqual(status["Alert"], actual_alert)
        self.assertEqual(status["Priority"], actual_priority)

        self.instr.close()

    def test_turbo_pump_status(self):
        self.instr.open()

        actual_turbo_pump_state = "Stopping Normal Delay"
        actual_alert = "New ID"
        actual_priority = "OK"

        cmd = "?V904"

        self._scpi_mock.ask.return_value = "=V904 3;9;0"
        status = self.instr.get_turbo_pump_status()
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(status["Pump state"], actual_turbo_pump_state)
        self.assertEqual(status["Alert"], actual_alert)
        self.assertEqual(status["Priority"], actual_priority)

        self.instr.close()

    def test_backing_pump_status(self):
        self.instr.open()

        actual_turbo_pump_state = "Fault Braking"
        actual_alert = "Over Pressure"
        actual_priority = "OK"

        cmd = "?V910"

        self._scpi_mock.ask.return_value = "=V910 6;23;0"
        status = self.instr.get_backing_pump_status()
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(status["Pump state"], actual_turbo_pump_state)
        self.assertEqual(status["Alert"], actual_alert)
        self.assertEqual(status["Priority"], actual_priority)

        self.instr.close()

    def test_turn_on_turbo_pump(self):
        self.instr.open()

        cmd = "!C904 1"

        self._scpi_mock.ask.return_value = "*C904 0"
        self.instr.turn_on_turbo_pump()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_on_turbo_pump_with_error(self):
        self.instr.open()

        cmd = "!C904 1"

        self._scpi_mock.ask.return_value = "*C904 5"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.turn_on_turbo_pump()
            self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_off_turbo_pump(self):
        self.instr.open()

        cmd = "!C904 0"

        self._scpi_mock.ask.return_value = "*C904 0"
        self.instr.turn_off_turbo_pump()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_off_turbo_pump_with_error(self):
        self.instr.open()

        cmd = "!C904 0"

        self._scpi_mock.ask.return_value = "*C904 2"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.turn_off_turbo_pump()
            self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_on_backing_pump(self):
        self.instr.open()

        cmd = "!C910 1"

        self._scpi_mock.ask.return_value = "*C910 0"
        self.instr.turn_on_backing_pump()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_on_backing_pump_with_error(self):
        self.instr.open()

        cmd = "!C910 1"

        self._scpi_mock.ask.return_value = "*C910 5"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.turn_on_backing_pump()
            self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_off_backing_pump(self):
        self.instr.open()

        cmd = "!C910 0"

        self._scpi_mock.ask.return_value = "*C910 0"
        self.instr.turn_off_backing_pump()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_turn_off_backing_pump_with_error(self):
        self.instr.open()

        cmd = "!C910 0"

        self._scpi_mock.ask.return_value = "*C910 2"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.turn_off_backing_pump()
            self._scpi_mock.ask.assert_called_once_with(cmd)

        self.instr.close()

    def test_get_turbo_pump_speed(self):
        self.instr.open()

        actual_turbo_pump_speed = "55.9"
        actual_alert = "ADC Fault"
        actual_priority = "OK"

        cmd = "?V905"

        self._scpi_mock.ask.return_value = f"=V905 {actual_turbo_pump_speed};1;0"
        speed = self.instr.get_turbo_pump_speed()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed["Pump speed"], actual_turbo_pump_speed)
        self.assertEqual(speed["Alert"], actual_alert)
        self.assertEqual(speed["Priority"], actual_priority)

        self.instr.close()

    def test_get_backing_pump_speed(self):
        self.instr.open()

        actual_backing_pump_speed = "15.2"
        actual_alert = "DX Fault"
        actual_priority = "OK"

        cmd = "?V911"

        self._scpi_mock.ask.return_value = f"=V911 {actual_backing_pump_speed};32;0"
        speed = self.instr.get_backing_pump_speed()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed["Pump speed"], actual_backing_pump_speed)
        self.assertEqual(speed["Alert"], actual_alert)
        self.assertEqual(speed["Priority"], actual_priority)

        self.instr.close()

    def test_get_turbo_pump_power(self):
        self.instr.open()

        actual_turbo_pump_power = "10"
        actual_alert = "ADC Fault"
        actual_priority = "OK"

        cmd = "?V906"

        self._scpi_mock.ask.return_value = f"=V906 {actual_turbo_pump_power};1;0"
        speed = self.instr.get_turbo_pump_power()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed["Pump power"], actual_turbo_pump_power)
        self.assertEqual(speed["Alert"], actual_alert)
        self.assertEqual(speed["Priority"], actual_priority)

        self.instr.close()

    def test_get_backing_pump_power(self):
        self.instr.open()

        actual_backing_pump_power = "20"
        actual_alert = "ADC Fault"
        actual_priority = "OK"

        cmd = "?V912"

        self._scpi_mock.ask.return_value = f"=V912 {actual_backing_pump_power};1;0"
        speed = self.instr.get_backing_pump_power()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed["Pump power"], actual_backing_pump_power)
        self.assertEqual(speed["Alert"], actual_alert)
        self.assertEqual(speed["Priority"], actual_priority)

        self.instr.close()

    def test_get_pressure_gauge_1(self):
        self.instr.open()

        actual_pressure = "5"
        actual_unit = "V"
        actual_gauge_state = "Striking"
        actual_alert = "ADC Fault"
        actual_priority = "OK"

        cmd = "?V913"

        self._scpi_mock.ask.return_value = f"=V913 {actual_pressure};66;6;1;0"
        pressure = self.instr.get_pressure_gauge_1()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(pressure["Pressure"], actual_pressure)
        self.assertEqual(pressure["Unit"], actual_unit)
        self.assertEqual(pressure["State"], actual_gauge_state)
        self.assertEqual(pressure["Alert"], actual_alert)
        self.assertEqual(pressure["Priority"], actual_priority)

        self.instr.close()

    def test_get_pressure_gauge_2(self):
        self.instr.open()

        actual_pressure = "20"
        actual_unit = "Pa"
        actual_gauge_state = "Striking"
        actual_alert = "ADC Fault"
        actual_priority = "OK"

        cmd = "?V914"

        self._scpi_mock.ask.return_value = f"=V914 {actual_pressure};59;6;1;0"
        pressure = self.instr.get_pressure_gauge_2()
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(pressure["Pressure"], actual_pressure)
        self.assertEqual(pressure["Unit"], actual_unit)
        self.assertEqual(pressure["State"], actual_gauge_state)
        self.assertEqual(pressure["Alert"], actual_alert)
        self.assertEqual(pressure["Priority"], actual_priority)

        self.instr.close()


if __name__ == '__main__':
    unittest.main()
