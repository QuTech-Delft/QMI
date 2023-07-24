"""Unit test for the Cobolt 06-01 series diode laser."""

import unittest
from unittest.mock import MagicMock, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.cobolt import Hubner_Cobolt0601


class TestLaser_06_01(unittest.TestCase):

    def setUp(self):
        qmi.start("TestContext")
        self._transport_mock = MagicMock(spec=QMI_SerialTransport)
        with patch(
                'qmi.instruments.cobolt.laser_06_01.create_transport',
                return_value=self._transport_mock):
            self.instr = qmi.make_instrument("instr", Hubner_Cobolt0601, "transport_descriptor")

    def tearDown(self):
        qmi.stop()

    def test_open_close(self):
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_get_idn(self):
        self._transport_mock.read_until.return_value = b"12345\r\n"
        self.instr.open()
        idn = self.instr.get_idn()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"gsn?\r")
        self.assertEqual(idn.vendor, "Cobolt")
        self.assertEqual(idn.model, "06-01")
        self.assertEqual(idn.serial, "12345")

    def test_reset(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.reset()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"@cob1\r")

    def test_reset_fail(self):
        self._transport_mock.read_until.return_value = b"haha\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.reset()
        self.instr.close()

    def test_get_laser_on_state(self):
        self._transport_mock.read_until.return_value = b"1\r\n"
        self.instr.open()
        laser_on_state = self.instr.get_laser_on_state()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"l?\r")
        self.assertTrue(laser_on_state)

    def test_get_laser_on_state_fail(self):
        self._transport_mock.read_until.return_value = b"123\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            laser_on_state = self.instr.get_laser_on_state()
        self._transport_mock.read_until.return_value = b"LASER_ON\r\n"
        with self.assertRaises(QMI_InstrumentException):
            laser_on_state = self.instr.get_laser_on_state()
        self.instr.close()

    def test_set_laser_on_state(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_laser_on_state(True)
        self._transport_mock.write.assert_called_once_with(b"l1\r")
        self._transport_mock.write.reset_mock()
        self.instr.set_laser_on_state(False)
        self._transport_mock.write.assert_called_once_with(b"l0\r")
        self.instr.close()

    def test_get_operating_hours(self):
        self._transport_mock.read_until.return_value = b"123.4\r\n"
        self.instr.open()
        operating_hours = self.instr.get_operating_hours()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"hrs?\r")
        self.assertAlmostEqual(operating_hours, 123.4)

    def test_get_interlock_state(self):
        self._transport_mock.read_until.return_value = b"0\r\n"
        self.instr.open()
        interlock = self.instr.get_interlock_state()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"ilk?\r")
        self.assertFalse(interlock)

    def test_get_output_power_setpoint(self):
        self._transport_mock.read_until.return_value = b"0.001234\r\n"
        self.instr.open()
        power = self.instr.get_output_power_setpoint()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"p?\r")
        self.assertAlmostEqual(power, 0.001234, places=8)

    def test_get_output_power_setpoint_fail(self):
        self._transport_mock.read_until.return_value = b"overflow\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            power = self.instr.get_output_power_setpoint()
        self.instr.close()

    def test_set_output_power_setpoint(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_output_power_setpoint(0.0121)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"p 0.012100\r")

    def test_get_output_power(self):
        self._transport_mock.read_until.return_value = b"0.00345\r\n"
        self.instr.open()
        power = self.instr.get_output_power()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"pa?\r")
        self.assertAlmostEqual(power, 0.00345, places=8)

    def test_get_drive_current(self):
        self._transport_mock.read_until.return_value = b"50.67\r\n"
        self.instr.open()
        current = self.instr.get_drive_current()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"i?\r")
        self.assertAlmostEqual(current, 50.67)

    def test_set_drive_current(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_drive_current(60.1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"slc 60.100000\r")

    def test_set_constant_power_mode(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_constant_power_mode()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"cp\r")

    def test_set_constant_current_mode(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_constant_current_mode()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"ci\r")

    def test_get_fault(self):
        self._transport_mock.read_until.return_value = b"0\r\n"
        self.instr.open()
        fault = self.instr.get_fault()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"f?\r")
        self.assertEqual(fault, 0)

    def test_clear_fault(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.clear_fault()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"cf\r")

    def test_set_modulation_mode(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_modulation_mode()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"em\r")

    def test_get_digital_modulation_state(self):
        self._transport_mock.read_until.return_value = b"1\r\n"
        self.instr.open()
        modulation = self.instr.get_digital_modulation_state()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"gdmes?\r")
        self.assertTrue(modulation)

    def test_set_digital_modulation_state(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_digital_modulation_state(True)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"sdmes 1\r")

    def test_get_analog_modulation_state(self):
        self._transport_mock.read_until.return_value = b"0\r\n"
        self.instr.open()
        modulation = self.instr.get_analog_modulation_state()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"games?\r")
        self.assertFalse(modulation)

    def test_set_analog_modulation_state(self) -> None:
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_analog_modulation_state(False)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"sames 0\r")

    def test_get_operating_mode(self):
        self._transport_mock.read_until.return_value = b"2\r\n"
        self.instr.open()
        mode = self.instr.get_operating_mode()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"gom?\r")
        self.assertEqual(mode, 2)

    def test_get_operating_mode_fail(self):
        self._transport_mock.read_until.return_value = b"error\r\n"
        self.instr.open()
        with self.assertRaises(QMI_InstrumentException):
            mode = self.instr.get_operating_mode()
        self.instr.close()

    def test_get_analog_low_impedance_state(self):
        self._transport_mock.read_until.return_value = b"0\r\n"
        self.instr.open()
        impedance = self.instr.get_analog_low_impedance_state()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"galis?\r")
        self.assertFalse(impedance)

    def test_set_analog_low_impedance_state(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_analog_low_impedance_state(True)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"salis 1\r")

    def test_get_autostart_state(self):
        self._transport_mock.read_until.return_value = b"1\r\n"
        self.instr.open()
        autostart = self.instr.get_autostart_state()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"@cobas?\r")
        self.assertTrue(autostart)

    def test_set_autostart_state(self):
        self._transport_mock.read_until.return_value = b"OK\r\n"
        self.instr.open()
        self.instr.set_autostart_state(False)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"@cobas 0\r")


if __name__ == '__main__':
    unittest.main()
