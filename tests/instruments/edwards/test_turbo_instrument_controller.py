"""Unit tests for Edwards Turbo Instrument Controller."""
import logging
from typing import cast
import unittest
from unittest.mock import Mock, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.edwards import EdwardsVacuum_TIC, EdwardsVacuum_TIC_AlertId,\
    EdwardsVacuum_TIC_GaugeState, EdwardsVacuum_TIC_Priority,\
    EdwardsVacuum_TIC_PumpState, EdwardsVacuum_TIC_State


class TestTurboInstrumentControllerOpenClose(unittest.TestCase):
    """
    Open close test for Edwards TIC.
    """

    def setUp(self):
        qmi.start("test-tic-context")
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
        self.instr = cast(EdwardsVacuum_TIC, self.instr)

    def tearDown(self):
        qmi.stop()
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_open_close_opens_and_closes(self):
        """Open and close instrument."""
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()


class TestTurboInstrumentController(unittest.TestCase):
    """
    Unit tests for Edwards TIC
    """

    def setUp(self):
        qmi.start("test-tic-context")
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
        self.instr = cast(EdwardsVacuum_TIC, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_get_idn_gets_idn(self):
        """Get idn of device."""
        # Arrange
        actual_model = "model1"
        actual_version = "version2"
        actual_serial = "serial3"

        cmd = "?S902"

        self._scpi_mock.ask.return_value = f"=S902 {actual_model};{actual_version};{actual_serial}"
        # Act
        instr_info = self.instr.get_idn()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(instr_info.vendor, "Edwards")
        self.assertEqual(instr_info.model, actual_model)
        self.assertEqual(instr_info.version, actual_version)
        self.assertEqual(instr_info.serial, actual_serial)

    def test_get_response_with_invalid_responses_throws_instrument_exception(self):
        """Get response with invalid reponse, throws an instrument exception."""
        # Arrange
        cmd = "?S902"

        self._scpi_mock.ask.return_value = "=A902 0;0;0"

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()
            self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_get_tic_status_gets_status(self):
        """Get the status of the instrument."""
        # Arrange
        actual_turbo_pump_state = EdwardsVacuum_TIC_PumpState.STOPPED
        actual_backing_pump_state = EdwardsVacuum_TIC_PumpState.ACCELERATING
        actual_gauge1_state = EdwardsVacuum_TIC_GaugeState.ZEROING
        actual_relay1_state = EdwardsVacuum_TIC_State.ON
        actual_alert = EdwardsVacuum_TIC_AlertId.FILAMENT_FAIL
        actual_priority = EdwardsVacuum_TIC_Priority.WARNING

        cmd = "?V902"

        self._scpi_mock.ask.return_value = "=V902 0;5;9;0;0;4;2;3;15;1"

        # Act
        status = self.instr.get_tic_status()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(status.turbo_pump_state, actual_turbo_pump_state)
        self.assertEqual(status.backing_pump_state, actual_backing_pump_state)
        self.assertEqual(status.gauge_1_state, actual_gauge1_state)
        self.assertEqual(status.relay_1_state, actual_relay1_state)
        self.assertEqual(status.alert, actual_alert)
        self.assertEqual(status.priority, actual_priority)

    def test_get_turbo_pump_state_gets_state(self):
        """Get state of turbo pump."""
        # Arrange
        actual_turbo_pump_state = EdwardsVacuum_TIC_PumpState.STOPPING_NORMAL_DELAY
        actual_alert = EdwardsVacuum_TIC_AlertId.NEW_ID
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V904"

        self._scpi_mock.ask.return_value = "=V904 3;9;0"

        # Act
        status = self.instr.get_turbo_pump_state()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(status.state, actual_turbo_pump_state)
        self.assertEqual(status.alert, actual_alert)
        self.assertEqual(status.priority, actual_priority)

    def test_get_backing_pump_state_gets_state(self):
        """Get state of backing pump."""
        # Arrange
        actual_turbo_pump_state = EdwardsVacuum_TIC_PumpState.FAULT_BRAKING
        actual_alert = EdwardsVacuum_TIC_AlertId.OVER_PRESSURE
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V910"

        self._scpi_mock.ask.return_value = "=V910 6;23;0"

        # Act
        status = self.instr.get_backing_pump_state()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)
        self.assertEqual(status.state, actual_turbo_pump_state)
        self.assertEqual(status.alert, actual_alert)
        self.assertEqual(status.priority, actual_priority)

    def test_turn_on_turbo_pump_turns_on_pump(self):
        """Turn on turbo pump."""
        # Arrange
        cmd = "!C904 1"

        self._scpi_mock.ask.return_value = "*C904 1"

        # Act
        self.instr.turn_on_turbo_pump()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_turn_on_turbo_pump_with_error_throws_instrument_exception(self):
        """Turn on turbo pump with error, throws instrument exception."""
        # Arrange
        cmd = "!C904 1"

        self._scpi_mock.ask.return_value = "*C904 5"

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self.instr.turn_on_turbo_pump()
            self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_turn_off_turbo_pump_turns_off_pump(self):
        """Turn off turbo pump."""
        # Arrange
        cmd = "!C904 0"

        self._scpi_mock.ask.return_value = "*C904 0"

        # Act
        self.instr.turn_off_turbo_pump()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_turn_on_backing_pump_turns_on_pump(self):
        """Turn on backing pump."""
        # Arrange
        cmd = "!C910 1"

        self._scpi_mock.ask.return_value = "*C910 1"

        # Act
        self.instr.turn_on_backing_pump()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_turn_off_backing_pump_turns_off_pump(self):
        """Turn off backing pump."""
        # Arrange
        cmd = "!C910 0"

        self._scpi_mock.ask.return_value = "*C910 0"

        # Act
        self.instr.turn_off_backing_pump()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_get_turbo_pump_speed_gets_speed(self):
        """Get the speed of the turbo pump."""
        # Arrange
        actual_turbo_pump_speed = 55.9
        actual_alert = EdwardsVacuum_TIC_AlertId.ADC_FAULT
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V905"

        self._scpi_mock.ask.return_value = f"=V905 {actual_turbo_pump_speed};1;0"

        # Act
        speed = self.instr.get_turbo_pump_speed()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed.speed, actual_turbo_pump_speed)
        self.assertEqual(speed.alert, actual_alert)
        self.assertEqual(speed.priority, actual_priority)

    def test_get_backing_pump_speed_gets_speed(self):
        """Get the speed of the backing pump."""
        # Arrange
        actual_backing_pump_speed = 15.2
        actual_alert = EdwardsVacuum_TIC_AlertId.DX_FAULT
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V911"

        self._scpi_mock.ask.return_value = f"=V911 {actual_backing_pump_speed};32;0"

        # Act
        speed = self.instr.get_backing_pump_speed()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed.speed, actual_backing_pump_speed)
        self.assertEqual(speed.alert, actual_alert)
        self.assertEqual(speed.priority, actual_priority)

    def test_get_turbo_pump_power_gets_power(self):
        """Get power of turbo pump."""
        # Arrange
        actual_turbo_pump_power = 10
        actual_alert = EdwardsVacuum_TIC_AlertId.ADC_FAULT
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V906"

        self._scpi_mock.ask.return_value = f"=V906 {actual_turbo_pump_power};1;0"

        # Act
        speed = self.instr.get_turbo_pump_power()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed.power, actual_turbo_pump_power)
        self.assertEqual(speed.alert, actual_alert)
        self.assertEqual(speed.priority, actual_priority)

    def test_get_backing_pump_power_gets_power(self):
        """Get power of backing pump."""
        # Arrange
        actual_backing_pump_power = 20
        actual_alert = EdwardsVacuum_TIC_AlertId.ADC_FAULT
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V912"

        self._scpi_mock.ask.return_value = f"=V912 {actual_backing_pump_power};1;0"

        # Act
        speed = self.instr.get_backing_pump_power()

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(speed.power, actual_backing_pump_power)
        self.assertEqual(speed.alert, actual_alert)
        self.assertEqual(speed.priority, actual_priority)

    def test_get_pressure_gauge_1_gets_pressure(self):
        """Get pressure of gauge 1."""
        # Arrange
        actual_pressure = 5
        actual_unit = "V"
        actual_gauge_state = EdwardsVacuum_TIC_GaugeState.STRIKING
        actual_alert = EdwardsVacuum_TIC_AlertId.ADC_FAULT
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V913"

        self._scpi_mock.ask.return_value = f"=V913 {actual_pressure};66;6;1;0"

        # Act
        pressure = self.instr.get_pressure(1)

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(pressure.pressure, actual_pressure)
        self.assertEqual(pressure.unit, actual_unit)
        self.assertEqual(pressure.state, actual_gauge_state)
        self.assertEqual(pressure.alert, actual_alert)
        self.assertEqual(pressure.priority, actual_priority)

    def test_get_relay_state_3_gets_state(self):
        """Get state of 3."""
        # Arrange
        actual_state = EdwardsVacuum_TIC_State.OFF_GOING_ON
        actual_alert = EdwardsVacuum_TIC_AlertId.ADC_FAULT
        actual_priority = EdwardsVacuum_TIC_Priority.OK

        cmd = "?V918"

        self._scpi_mock.ask.return_value = "=V918 1;1;0"

        # Act
        state = self.instr.get_relay_state(3)

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

        self.assertEqual(state.state, actual_state)
        self.assertEqual(state.alert, actual_alert)
        self.assertEqual(state.priority, actual_priority)

    def test_turn_on_relay_1_turns_on_relay(self):
        """Turn on relay 1."""
        # Arrange
        cmd = "!C917 1"

        self._scpi_mock.ask.return_value = "*C917 1"

        # Act
        self.instr.turn_on_relay(2)

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)

    def test_turn_off_relay_1_turns_off_relay(self):
        """Turn off relay 1."""
        # Arrange
        cmd = "!C916 0"

        self._scpi_mock.ask.return_value = "*C916 0"

        # Act
        self.instr.turn_off_relay(1)

        # Assert
        self._scpi_mock.ask.assert_called_once_with(cmd)


if __name__ == '__main__':
    unittest.main()
