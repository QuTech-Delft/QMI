import unittest
from unittest.mock import patch
import logging
import struct

import qmi
from qmi.instruments.parallax import Parallax_UsbPropeller


class ParallaxUsbPropellerOpenCloseTestCase(unittest.TestCase):

    def setUp(self) -> None:
        qmi.start("parallax_unit_test")
        transport = "serial:COM1"
        self.parallax = qmi.make_instrument("Parallax", Parallax_UsbPropeller, transport)

    def tearDown(self) -> None:
        qmi.stop()

    def test_open_close(self):
        """Test opening and closing the instrument"""
        with patch("serial.Serial") as ser:
            self.parallax.open()
            self.assertTrue(self.parallax.is_open())
            self.parallax.close()
            self.assertFalse(self.parallax.is_open())
            ser.assert_called_once_with(
                "COM1",  # The rest are defaults
                baudrate=2400,
                bytesize=8,
                parity='N',
                rtscts=False,
                stopbits=1.0,
                timeout=0.04
                )


class ParallaxUsbPropellerCommandsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        # suppress logging
        logging.getLogger("qmi.instruments.parallax.usb_propeller").setLevel(logging.CRITICAL)
        self._lead_in = b"!", b"S", b"C"
        self._endline = b"\r"
        qmi.start("parallax_unit_test")
        transport = "serial:/dev/ttyS1"
        self.patcher_open = patch("qmi.core.transport.QMI_Transport.open")
        self.patcher_discard = patch("qmi.core.transport.QMI_SerialTransport.discard_read")
        self.patcher_open.start()
        self.patcher_discard.start()
        self.parallax = qmi.make_instrument("Parallax", Parallax_UsbPropeller, transport)
        self.parallax.open()

    def tearDown(self) -> None:
        self.patcher_open.stop()
        self.patcher_discard.stop()
        patcher_close = patch("qmi.core.transport.QMI_Transport.close")
        patcher_close.start()
        self.parallax.close()
        qmi.stop()
        patcher_close.stop()
        # restore logging
        logging.getLogger("qmi.instruments.parallax.usb_propeller").setLevel(logging.NOTSET)

    def test_get_idn(self):
        """Test getting the QMI instrument ID."""
        expected_vendor = "Parallax"
        expected_model = "USB Propeller"
        expected_version = "1.0"
        expected_command = struct.pack(
                "cccccccc", b"!", b"S", b"C", b"V", b"E", b"R", b"?", self._endline
            )
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("BBB", 49, 46, 48)  # "1", ".", "0"
                idn = self.parallax.get_idn()

            write.assert_called_with(expected_command)

        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertIsNone(idn.serial)
        self.assertEqual(expected_version, idn.version)

    def test_set_target_value_with_speed(self):
        """Test setting the target value."""
        target, ramp_speed, channel = 500, 10, 1
        lsb = target & 0xFF  # 7 bits for least significant byte
        msb = target >> 8 & 0xFF  # shift 8 and take next 8 bits for msb
        expected_command = struct.pack(
                "cccBBBBc", b"!", b"S", b"C", channel, ramp_speed, lsb, msb, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.set_speed(channel, ramp_speed)
            self.parallax.set_target_value(channel, target)
            write.assert_any_call(expected_command)

    def test_set_target_value_enforces_limits(self):
        """Test setting the target value."""
        expected_pos = [Parallax_UsbPropeller.DEFAULT_MIN, Parallax_UsbPropeller.DEFAULT_MAX]
        # 1. Test minimum value
        target_min, ramp_speed, channel = 300, 10, 1
        lsb = expected_pos[0] & 0xFF  # 7 bits for least significant byte
        msb = expected_pos[0] >> 8 & 0xFF  # shift 8 and take next 8 bits for msb
        expected_command = struct.pack(
                "cccBBBBc", b"!", b"S", b"C", channel, ramp_speed, lsb, msb, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.set_speed(channel, ramp_speed)
            self.parallax.set_target_value(channel, target_min)
            write.assert_any_call(expected_command)

        # 2. Test maximum value
        target_max, ramp_speed, channel = 1000, 10, 1
        lsb = expected_pos[1] & 0xFF  # 7 bits for least significant byte
        msb = expected_pos[1] >> 8 & 0xFF  # shift 8 and take next 8 bits for msb
        expected_command = struct.pack(
                "cccBBBBc", b"!", b"S", b"C", channel, ramp_speed, lsb, msb, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.set_speed(channel, ramp_speed)
            self.parallax.set_target_value(channel, target_max)
            write.assert_any_call(expected_command)

    def test_set_default_move(self):
        """Test setting the default move."""
        target, channel = 555, 10
        lsb = target & 0xFF  # 7 bits for least significant byte
        msb = target >> 8 & 0xFF  # shift 8 and take next 8 bits for msb
        expected_command = struct.pack(
                "ccccBBBc", b"!", b"S", b"C", b"D", channel, lsb, msb, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.set_default_move(channel, target)
            write.assert_any_call(expected_command)

    def test_set_default_move_invalid_values(self):
        """Test setting the default move with invalid values."""
        targets, channel = [0, Parallax_UsbPropeller.MAX_PULSE_WIDTH + 1], 10
        for target in targets:
            with self.assertRaises(ValueError):
                self.parallax.set_default_move(channel, target)

    def test_get_target_values(self):
        """Test get target values return expected values."""
        target = 500
        expected_initial = [0] * Parallax_UsbPropeller.AVAILABLE_CHANNELS
        expected_after = [target + n for n in range(Parallax_UsbPropeller.AVAILABLE_CHANNELS)]

        initial = self.parallax.get_target_values()
        # Assert
        self.assertListEqual(expected_initial, initial)

        # Then set all target values
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            for channel in range(Parallax_UsbPropeller.AVAILABLE_CHANNELS):
                self.parallax.set_target_value(channel, target + channel)

        after = self.parallax.get_target_values()
        # Assert
        self.assertListEqual(expected_after, after)

    def test_get_value(self):
        """Test get target value returns expected value."""
        expected, channel = 500, 0
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"R", b"S", b"P", channel, self._endline
            )
        low_bit, high_bit = expected - (expected // 256 * 256), expected // 256
        # Then set all target values
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("BBB", channel, high_bit, low_bit)
                result = self.parallax.get_value(channel)

            write.assert_called_with(expected_command)

        self.assertEqual(result, expected)

    def test_set_baud_rate(self):
        """Test setting a new baud rate speed."""
        speed = 38400
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"S", b"B", b"R", 1, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("ccB", b"B", b"R", 1)
                self.parallax.set_baud_rate(speed)

            write.assert_called_with(expected_command)

    def test_set_baud_rate_raises_exception_invalid_speed(self):
        """Test setting an invalid baud rate speed raises an exception."""
        invalid_speeds = (4800, 9600, 19200, 2)
        for speed in invalid_speeds:
            with self.assertRaises(ValueError):
                self.parallax.set_baud_rate(speed)

    def test_set_baud_rate_not_successful_raises_exception(self):
        """Test setting a baud rate speed that was not successful raises an exception."""
        speeds = (1, 0)
        for speed in speeds:
            with patch("qmi.core.transport.QMI_SerialTransport.write"):
                with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                    read.return_value = struct.pack("ccB", b"B", b"R", int(not speed))
                    with self.assertRaises(AssertionError):
                        self.parallax.set_baud_rate(speed)

    def test_set_software_port_range(self):
        """Test setting a new software port range."""
        port_range = 1
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"P", b"S", b"S", port_range, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("ccB", b"P", b"M", port_range)
                self.parallax.set_software_port_range(port_range)

            write.assert_called_with(expected_command)

    def test_set_software_port_range_raises_exception_invalid_range(self):
        """Test setting an invalid port range raises an exception."""
        invalid_range = 2
        with self.assertRaises(ValueError):
            self.parallax.set_software_port_range(invalid_range)

    def test_set_software_port_range_not_successful_raises_exception(self):
        """Test setting a software port range that was not successful raises an exception."""
        port_ranges = (1, 0)
        for port_range in port_ranges:
            with patch("qmi.core.transport.QMI_SerialTransport.write"):
                with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                    read.return_value = struct.pack("ccB", b"P", b"M", int(not port_range))
                    with self.assertRaises(AssertionError):
                        self.parallax.set_software_port_range(port_range)

    def test_disable_servo_channel(self):
        """Test disable servo channel function."""
        channel = 12
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"P", b"S", b"D", channel, self._endline
            )
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.disable_servo_channel(channel)
            write.assert_called_once_with(expected_command)

    def test_enable_servo_channel(self):
        """Test enable servo channel function."""
        channel = 11
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"P", b"S", b"E", channel, self._endline
            )
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.enable_servo_channel(channel)
            write.assert_called_once_with(expected_command)

    def test_set_startup_servo_mode(self):
        """Test setting a new startup servo mode."""
        servo_mode = 1
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"E", b"D", b"D", servo_mode, self._endline
            )

        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("ccB", b"D", b"L", servo_mode)
                self.parallax.set_startup_servo_mode(servo_mode)

            write.assert_called_with(expected_command)

    def test_set_startup_servo_mode_raises_exception_invalid_range(self):
        """Test setting an invalid servo mode raises an exception."""
        invalid_mode = 2
        with self.assertRaises(ValueError):
            self.parallax.set_startup_servo_mode(invalid_mode)

    def test_set_startup_servo_mode_not_successful_raises_exception(self):
        """Test setting a startup servo mode that was not successful raises an exception."""
        servo_modes = (1, 0)
        for servo_mode in servo_modes:
            with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
                with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                    read.return_value = struct.pack("ccB", b"D", b"L", int(not servo_mode))
                    with self.assertRaises(AssertionError):
                        self.parallax.set_startup_servo_mode(servo_mode)

    def test_clear(self):
        """Test clear a channel function."""
        expected_command = struct.pack(
                "cccccccc", b"!", b"S", b"C", b"L", b"E", b"A", b"R", self._endline
            )
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("ccc", b"C", b"L", b"R")
                self.parallax.clear()

            write.assert_called_once_with(expected_command)

    def test_clear_assertion_error(self):
        """Test clear a channel function with erroneous response."""
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("ccc", b"1", b".", b"0")
                with self.assertRaises(AssertionError):
                    self.parallax.clear()

    def test_move_up_moves_to_max(self):
        """Test that the move_up sets the target value to maximum."""
        channel = 2
        expected_targets = [0] * Parallax_UsbPropeller.AVAILABLE_CHANNELS
        expected_targets[channel] = Parallax_UsbPropeller.DEFAULT_MAX
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.parallax.move_up(channel)
            # Get the target values
            targets = self.parallax.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_move_down_moves_to_min(self):
        """Test that the move_down sets the target value to minimum."""
        channel = 3
        expected_targets = [0] * Parallax_UsbPropeller.AVAILABLE_CHANNELS
        expected_targets[channel] = Parallax_UsbPropeller.DEFAULT_MIN
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.parallax.move_down(channel)
            # Get the target values
            targets = self.parallax.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_is_moving(self):
        """Test that is_moving returns the correct value."""
        # 1. Not moving, i.o.w. "servo reached target"
        expected, channel = 500, 0
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"R", b"S", b"P", channel, self._endline
            )
        high_bit, low_bit = expected - (expected // 256 * 256), expected // 256
        # Then set all target values
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.set_target_value(channel, expected)
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("BBB", channel, low_bit, high_bit)
                moving = self.parallax.is_moving(channel)

            write.assert_called_with(expected_command)

        self.assertFalse(moving)

        # 2. Moving
        channel = 1
        expected_command = struct.pack(
                "ccccccBc", b"!", b"S", b"C", b"R", b"S", b"P", channel, self._endline
            )
        not_expected = expected + 1
        high_bit, low_bit = not_expected - (not_expected // 256 * 256), not_expected // 256
        with patch("qmi.core.transport.QMI_SerialTransport.write") as write:
            self.parallax.set_target_value(channel, expected)
            with patch("qmi.core.transport.QMI_SerialTransport.read") as read:
                read.return_value = struct.pack("BBB", channel, low_bit, high_bit)
                moving = self.parallax.is_moving(channel)

            write.assert_called_with(expected_command)

        self.assertTrue(moving)

    def test_set_max(self):
        """Test that setting new maximum value on a channels works."""
        new_max = 1000
        channel = 2
        expected_targets = [0] * Parallax_UsbPropeller.AVAILABLE_CHANNELS
        expected_targets[channel] = new_max

        self.parallax.set_max(channel, new_max)
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.parallax.move_up(channel)
            # Get the target values
            targets = self.parallax.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_set_max_excepts(self):
        """Test that setting new maximum value outside valid range excepts."""
        invalid_maxes = [100, 1050]
        channel = 4

        for new_max in invalid_maxes:
            with self.assertRaises(ValueError):
                self.parallax.set_max(channel, new_max)

    def test_set_min(self):
        """Test that setting new minimum value on a channels works."""
        new_min = 100
        channel = 3
        expected_targets = [0] * Parallax_UsbPropeller.AVAILABLE_CHANNELS
        expected_targets[channel] = new_min

        self.parallax.set_min(channel, new_min)
        with patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.parallax.move_down(channel)
            # Get the target values
            targets = self.parallax.get_target_values()

        self.assertListEqual(expected_targets, targets)

    def test_set_min_excepts(self):
        """Test that setting new minimum value outside valid range excepts."""
        invalid_mins = [-1, 1000]
        channel = 5

        for new_min in invalid_mins:
            with self.assertRaises(ValueError):
                self.parallax.set_min(channel, new_min)

    def test_set_wrong_channel_excepts(self):
        """Test a set command with wrong channel numbers and see that it excepts"""
        wrong_channels = (-1, Parallax_UsbPropeller.AVAILABLE_CHANNELS)
        for ch in wrong_channels:
            with self.assertRaises(ValueError):
                self.parallax.set_target_value(ch, 0)


if __name__ == '__main__':
    unittest.main()
