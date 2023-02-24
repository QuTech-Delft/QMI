import unittest
from unittest.mock import patch, call
import logging

import qmi
from qmi.instruments.pololu.maestro import Pololu_Maestro
from qmi.core.exceptions import QMI_InstrumentException


class PololuMaestroOpenCloseTestCase(unittest.TestCase):

    def setUp(self) -> None:
        qmi.start("pololu_unit_test")
        transport = "serial:COM1"
        self.pololu = qmi.make_instrument("Pololu", Pololu_Maestro, transport)

    def tearDown(self) -> None:
        qmi.stop()

    def test_open_close(self):
        """Test opening and closing the instrument"""
        with patch("serial.Serial") as ser:
            self.pololu.open()
            self.assertTrue(self.pololu.is_open())
            self.pololu.close()
            self.assertFalse(self.pololu.is_open())
            ser.assert_called_once_with(
                "COM1",
                baudrate=9600,  # The rest are defaults
                bytesize=8,
                parity='N',
                rtscts=False,
                stopbits=1.0,
                timeout=0.04
                )


class PololuMaestroCommandsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        # suppress logging
        logging.getLogger("qmi.instruments.pololu.maestro").setLevel(logging.CRITICAL)
        self._cmd_lead = chr(0xAA) + chr(0x0C)
        self._error_check_cmd = bytes(self._cmd_lead + chr(0x21), "latin-1")
        qmi.start("pololu_unit_test")
        transport = "serial:/dev/ttyS1"
        self.patcher_open = patch("qmi.core.transport.QMI_Transport.open")
        self.patcher_discard = patch("qmi.core.transport.QMI_SerialTransport.discard_read")
        self.patcher_open.start()
        self.patcher_discard.start()
        self.pololu = qmi.make_instrument("Pololu", Pololu_Maestro, transport)
        self.pololu.open()

    def tearDown(self) -> None:
        self.patcher_open.stop()
        self.patcher_discard.stop()
        patcher_close = patch("qmi.core.transport.QMI_Transport.close")
        patcher_close.start()
        self.pololu.close()
        qmi.stop()
        patcher_close.stop()
        # restore logging
        logging.getLogger("qmi.instruments.pololu.maestro").setLevel(logging.NOTSET)

    def test_get_idn(self):
        """Test getting the QMI instrument ID."""
        expected_vendor = "Pololu"
        expected_model = "Maestro Micro Servo Controller"
        idn = self.pololu.get_idn()

        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertIsNone(idn.serial)
        self.assertIsNone(idn.version)

    def test_set_target_value(self):
        """Test setting the target value."""
        target, channel = 5000, 1
        lsb = target & 0x7F  # 7 bits for least significant byte
        msb = (target >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.set_target_value(channel, target)

            write.assert_called_with(self._error_check_cmd)
            write.assert_any_call(expected_command)

    def test_set_target_value_enforces_limits(self):
        """Test setting the target value."""
        expected_pos = [Pololu_Maestro.DEFAULT_MIN, Pololu_Maestro.DEFAULT_MAX]
        # 1. Test minimum value
        target_min, channel = 3000, 1
        lsb = expected_pos[0] & 0x7F  # 7 bits for least significant byte
        msb = (expected_pos[0] >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.set_target_value(channel, target_min)

            write.assert_called_with(self._error_check_cmd)
            write.assert_any_call(expected_command)

        # 2. Test maximum value
        target_max, channel = 6000, 1
        lsb = expected_pos[1] & 0x7F  # 7 bits for least significant byte
        msb = (expected_pos[1] >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.set_target_value(channel, target_max)

            write.assert_called_with(self._error_check_cmd)
            write.assert_any_call(expected_command)

    def test_get_target_values(self):
        """Test get target values return expected values."""
        target = 5000
        expected_initial = [0] * Pololu_Maestro.AVAILABLE_CHANNELS
        expected_after = [target + n for n in range(Pololu_Maestro.AVAILABLE_CHANNELS)]

        initial = self.pololu.get_target_values()
        # Assert
        self.assertListEqual(expected_initial, initial)

        # Then set all target values
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = (0, 0)
                for channel in range(Pololu_Maestro.AVAILABLE_CHANNELS):
                    self.pololu.set_target_value(channel, target + channel)

    def test_get_value(self):
        """Test get target value returns expected value."""
        expected, channel = 5000, 0
        cmd = chr(0x10) + chr(channel)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        low_bit, high_bit = expected - (expected // 256 * 256), expected // 256
        # Then set all target values
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0), chr(low_bit), chr(high_bit), (0, 0))
                result = self.pololu.get_value(channel)

            write.assert_called_with(self._error_check_cmd)
            write.assert_any_call(expected_command)

        self.assertEqual(result, expected)

    def test_set_speed(self):
        """Test setting a new speed for a channel."""
        speed, channel = 500, 1
        lsb = speed & 0x7F  # 7 bits for least significant byte
        msb = (speed >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x07) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.set_speed(channel, speed)

            write.assert_called_with(self._error_check_cmd)
            write.assert_any_call(expected_command)

    def test_set_speed_raises_exception(self):
        """Test setting an invalid speed for a channel raises an exception."""
        speed, channel = 5000, 1
        with self.assertRaises(ValueError):
            self.pololu.set_speed(channel, speed)

    def test_set_acceleration(self):
        """Test setting a new acceleration for a channel."""
        acceleration, channel = 50, 1
        lsb = acceleration & 0x7F  # 7 bits for least significant byte
        msb = (acceleration >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x09) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.set_acceleration(channel, acceleration)

            write.assert_any_call(expected_command)
            write.assert_called_with(self._error_check_cmd)

    def test_set_acceleration_raises_exception(self):
        """Test setting an invalid acceleration for a channel raises an exception."""
        acceleration, channel = 500, 1
        with self.assertRaises(ValueError):
            self.pololu.set_acceleration(channel, acceleration)

    def test_go_home(self):
        """Test go_home function."""
        expected_command = bytes(self._cmd_lead + chr(0x22), "latin-1")
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.go_home()

            write.assert_any_call(expected_command)
            write.assert_called_with(self._error_check_cmd)

    def test_move_up_moves_to_max(self):
        """Test that the move_up sets the target value to maximum."""
        channel = 2
        expected_targets = [0] * Pololu_Maestro.AVAILABLE_CHANNELS
        expected_targets[channel] = Pololu_Maestro.DEFAULT_MAX
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.move_up(channel)
                # Get the target values
                targets = self.pololu.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_move_down_moves_to_min(self):
        """Test that the move_down sets the target value to minimum."""
        channel = 3
        expected_targets = [0] * Pololu_Maestro.AVAILABLE_CHANNELS
        expected_targets[channel] = Pololu_Maestro.DEFAULT_MIN
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.move_down(channel)
                # Get the target values
                targets = self.pololu.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_is_moving(self):
        """Test that is_moving returns the correct value."""
        # 1. Not moving, i.o.w. "servo reached target"
        channel = 0
        cmd = chr(0x10) + chr(channel)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0), chr(0x0), chr(0x0), (0, 0))
                moving = self.pololu.is_moving(channel)

            write.assert_any_call(expected_command)
            write.assert_called_with(self._error_check_cmd)

        self.assertFalse(moving)

        # 2. Not moving, i.o.w. "servo blocked/stuck"
        channel = 0
        cmd = chr(0x10) + chr(channel)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0), chr(0x01), chr(0x01), (0, 0), (0, 0), chr(0x01), chr(0x01), (0, 0))
                moving = self.pololu.is_moving(channel)

            self.assertEqual(write.mock_calls.count(call(expected_command)), 2)
            self.assertEqual(write.mock_calls.count(call(self._error_check_cmd)), 4)

        self.assertFalse(moving)

        # 3. Moving
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0), chr(0x01), chr(0x00), (0, 0), (0, 0), chr(0x01), chr(0x01), (0, 0))
                moving = self.pololu.is_moving(channel)

            self.assertEqual(write.mock_calls.count(call(expected_command)), 2)
            self.assertEqual(write.mock_calls.count(call(self._error_check_cmd)), 4)

        self.assertTrue(moving)

    def test_set_max(self):
        """Test that setting new maximum value on a channels works."""
        new_max = 6100
        channel = 2
        expected_targets = [0] * Pololu_Maestro.AVAILABLE_CHANNELS
        expected_targets[channel] = new_max

        self.pololu.set_max(channel, new_max)
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.move_up(channel)
                # Get the target values
                targets = self.pololu.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_set_max_excepts(self):
        """Test that setting new maximum value outside valid range excepts."""
        invalid_maxes = [3999, 8001]
        channel = 4

        for new_max in invalid_maxes:
            with self.assertRaises(ValueError):
                self.pololu.set_max(channel, new_max)

    def test_set_min(self):
        """Test that setting new minimum value on a channels works."""
        new_min = 2912
        channel = 3
        expected_targets = [0] * Pololu_Maestro.AVAILABLE_CHANNELS
        expected_targets[channel] = new_min

        self.pololu.set_min(channel, new_min)
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((0, 0),)
                self.pololu.move_down(channel)
                # Get the target values
                targets = self.pololu.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_set_min_excepts(self):
        """Test that setting new minimum value outside valid range excepts."""
        invalid_mins = [-1, 5500]
        channel = 5

        for new_min in invalid_mins:
            with self.assertRaises(ValueError):
                self.pololu.set_min(channel, new_min)

    def test_command_error_check_excepts(self):
        """Make a command's error check to except"""
        cmd = chr(0x22)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.side_effect = ((16, 1),)
                with self.assertRaises(QMI_InstrumentException):
                    self.pololu.go_home()

            write.assert_called_with(self._error_check_cmd)
            write.assert_any_call(expected_command)

    def test_set_wrong_channel_excepts(self):
        """Test a set command with wrong channel numbers and see that it excepts"""
        wrong_channels = (-1, Pololu_Maestro.AVAILABLE_CHANNELS)
        for ch in wrong_channels:
            with self.assertRaises(ValueError):
                self.pololu.set_target_value(ch, 0)


if __name__ == '__main__':
    unittest.main()
