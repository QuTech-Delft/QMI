import unittest
from unittest.mock import Mock, patch, call
import logging

from qmi.core.transport import QMI_SerialTransport
from qmi.core.exceptions import QMI_InstrumentException

with patch("qmi.instruments.pololu.maestro.TYPE_CHECKING", True):
    from qmi.instruments.pololu import Pololu_Maestro

from tests.patcher import PatcherQmiContext as QMI_Context


class PololuMaestroUartOpenCloseTestCase(unittest.TestCase):
    board_mock = Mock()
    board_mock.TX = 2
    board_mock.RX = 3
    busio_mock = Mock()
    uart_mock = Mock()
    uart_ports_mock = Mock()

    def setUp(self) -> None:
        self.busio_mock.UART = Mock(return_value=None)
        self.baudrate = 115200
        self._cmd_lead = chr(0xAA) + chr(0x0C)
        ctx = QMI_Context("pololu_unit_test")
        transport = f"uart:COM1:baudrate={self.baudrate}"
        with patch.dict("sys.modules", {
            "qmi.instruments.pololu.qmi_uart": self.uart_mock,
            "board": self.board_mock, "busio": self.busio_mock,
            "machine": Mock(), "microcontroller.pin": self.uart_ports_mock
        }) as self.sys_patch:
            self.uart_ports_mock.uartPorts = ([[10, 2, 3]])
            self.instr = Pololu_Maestro(ctx, "Pololu", transport)

    def test_open_close(self):
        """Test opening and closing the instrument"""
        self.instr.open()
        self.assertTrue(self.instr.is_open())
        self.instr.close()
        self.assertFalse(self.instr.is_open())

    def test_write_with_set_target_value(self):
        """Test writing by setting a target value."""
        # Arrange
        target, channel = 5000, 1
        lsb = target & 0x7F  # 7 bits for least significant byte
        msb = (target >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self.instr._transport.read_until_timeout.side_effect = [b'\x00\x00'] * 2
        expected_write_calls = [
            call(expected_command), call(bytes(self._cmd_lead + '!', "latin-1"))
        ]
        expected_read_call = [call(nbytes=2, timeout=Pololu_Maestro.RESPONSE_TIMEOUT)]

        # Act
        self.instr.open()
        self.instr.set_target(channel, target)

        # Assert
        self.instr._transport.write.assert_has_calls(expected_write_calls)
        self.instr._transport.read_until_timeout.assert_has_calls(expected_read_call)

    def test_read_with_get_position(self):
        """Test get position returns expected value."""
        # Arrange
        expected, channel = 5000, 0
        cmd = chr(0x10) + chr(channel)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        low_bit, high_bit = expected - (expected // 256 * 256), expected // 256
        self.instr._transport.read_until_timeout.side_effect = [
            chr(low_bit),
            chr(high_bit),
            b'\x00\x00',
        ]
        expected_write_calls = [
            call(expected_command), call(bytes(self._cmd_lead + '!', "latin-1"))
        ]
        expected_read_calls = [
            call(nbytes=1, timeout=Pololu_Maestro.RESPONSE_TIMEOUT),
            call(nbytes=1, timeout=Pololu_Maestro.RESPONSE_TIMEOUT),
            call(nbytes=2, timeout=Pololu_Maestro.RESPONSE_TIMEOUT),
        ]

        # Act
        self.instr.open()
        result = self.instr.get_position(channel)

        # Assert
        self.instr._transport.write.assert_has_calls(expected_write_calls)
        self.instr._transport.read_until_timeout.assert_has_calls(expected_read_calls)
        self.assertEqual(expected, result)


class PololuMaestroSerialOpenCloseTestCase(unittest.TestCase):

    def setUp(self) -> None:
        ctx = QMI_Context("pololu_unit_test")
        transport = "serial:COM1"
        self.instr = Pololu_Maestro(ctx, "Pololu", transport)

    def test_open_close(self):
        """Test opening and closing the instrument"""
        with patch("serial.Serial") as ser:
            self.instr.open()
            self.assertTrue(self.instr.is_open())
            self.instr.close()
            self.assertFalse(self.instr.is_open())
            ser.assert_called_once_with(
                "COM1",
                baudrate=9600,  # The rest are defaults
                bytesize=8,
                parity='N',
                rtscts=False,
                stopbits=1.0,
                timeout=0.04
            )


class PololuMaestroMinMaxTargetsConfigTestCase(unittest.TestCase):

    TRANSPORT_STR = "serial:/dev/ttyS1"
    CHANNEL1_MIN = 9000
    CHANNEL1_MAX = 9300
    CHANNEL3_MIN = 8000
    CHANNEL3_MAX = 9100

    def setUp(self) -> None:
        # suppress logging
        logging.getLogger("qmi.instruments.pololu.maestro").setLevel(
            logging.CRITICAL)
        self._cmd_lead = chr(0xAA) + chr(0x0C)
        self._error_check_cmd = bytes(self._cmd_lead + chr(0x21), "latin-1")
        ctx = QMI_Context("pololu_unit_test")
        patcher = patch(
            'qmi.instruments.pololu.maestro.create_transport', spec=QMI_SerialTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.instr: Pololu_Maestro = Pololu_Maestro(
            ctx, "Pololu", self.TRANSPORT_STR,
            channels_min_max_targets={1: (self.CHANNEL1_MIN, self.CHANNEL1_MAX),
                                      3: (self.CHANNEL3_MIN, self.CHANNEL3_MAX)})
        self.instr.open()

    def tearDown(self) -> None:
        self.instr.close()

    def test_setting_channel_min_and_max_targets(self):
        """Test setting the min and max targets of channels."""
        # Arrange
        channel = 1

        # Act
        actual_min = self.instr.get_min_target(channel)
        actual_max = self.instr.get_max_target(channel)

        # Assert
        self.assertEqual(actual_min, self.CHANNEL1_MIN)
        self.assertEqual(actual_max, self.CHANNEL1_MAX)

        # Arrange
        channel = 3

        # Act
        actual_min = self.instr.get_min_target(channel)
        actual_max = self.instr.get_max_target(channel)

        # Assert
        self.assertEqual(actual_min, self.CHANNEL3_MIN)
        self.assertEqual(actual_max, self.CHANNEL3_MAX)


class PololuMaestroMinMaxSpeedsConfigTestCase(unittest.TestCase):

    TRANSPORT_STR = "serial:/dev/ttyS1"
    CHANNEL1_MIN = 88
    CHANNEL1_MAX = 99

    def setUp(self) -> None:
        # suppress logging
        logging.getLogger("qmi.instruments.pololu.maestro").setLevel(
            logging.CRITICAL)
        self._cmd_lead = chr(0xAA) + chr(0x0C)
        self._error_check_cmd = bytes(self._cmd_lead + chr(0x21), "latin-1")
        ctx = QMI_Context("pololu_unit_test")
        patcher = patch(
            'qmi.instruments.pololu.maestro.create_transport', spec=QMI_SerialTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.instr: Pololu_Maestro = Pololu_Maestro(
            ctx, "Pololu", self.TRANSPORT_STR,
            channels_min_max_speeds={1: (self.CHANNEL1_MIN, self.CHANNEL1_MAX)})
        self.instr.open()

    def tearDown(self) -> None:
        self.instr.close()

    def test_setting_channel_min_and_max_speed(self):
        """Test setting the min and max speeds of channels."""
        # Arrange
        channel = 1

        # Act and Assert
        with self.assertRaises(ValueError):
            self.instr.set_speed(channel, 9000)


class PololuMaestroMinMaxAccelerationsConfigTestCase(unittest.TestCase):

    TRANSPORT_STR = "serial:/dev/ttyS1"
    CHANNEL1_MIN = 88
    CHANNEL1_MAX = 99

    def setUp(self) -> None:
        # suppress logging
        logging.getLogger("qmi.instruments.pololu.maestro").setLevel(
            logging.CRITICAL)
        self._cmd_lead = chr(0xAA) + chr(0x0C)
        self._error_check_cmd = bytes(self._cmd_lead + chr(0x21), "latin-1")
        ctx = QMI_Context("pololu_unit_test")
        patcher = patch(
            'qmi.instruments.pololu.maestro.create_transport', spec=QMI_SerialTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.instr: Pololu_Maestro = Pololu_Maestro(
            ctx, "Pololu", self.TRANSPORT_STR,
            channels_min_max_accelerations={1: (self.CHANNEL1_MIN, self.CHANNEL1_MAX)})
        self.instr.open()

    def tearDown(self) -> None:
        self.instr.close()

    def test_setting_channel_min_and_max_acceleration(self):
        """Test setting the min and max accelerations of channels."""
        # Arrange
        channel = 1

        # Act and Assert
        with self.assertRaises(ValueError):
            self.instr.set_acceleration(channel, 9000)


class PololuMaestroCommandsTestCase(unittest.TestCase):

    TRANSPORT_STR = "serial:/dev/ttyS1"

    def setUp(self) -> None:
        # suppress logging
        logging.getLogger("qmi.instruments.pololu.maestro").setLevel(
            logging.CRITICAL)
        self._cmd_lead = chr(0xAA) + chr(0x0C)
        self._error_check_cmd = bytes(self._cmd_lead + chr(0x21), "latin-1")
        ctx = QMI_Context("pololu_unit_test")
        patcher = patch(
            'qmi.instruments.pololu.maestro.create_transport', spec=QMI_SerialTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.instr: Pololu_Maestro = Pololu_Maestro(ctx, "Pololu", self.TRANSPORT_STR)
        self.instr.open()

    def tearDown(self) -> None:
        self.instr.close()

    def test_get_idn(self):
        """Test getting the QMI instrument ID."""
        # Arrange
        expected_vendor = "Pololu"
        expected_model = "Maestro Micro Servo Controller"

        # Act
        idn = self.instr.get_idn()

        # Assert
        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertIsNone(idn.serial)
        self.assertIsNone(idn.version)

    def test_set_target_value(self):
        """Test setting the target value."""
        # Arrange
        target, channel = 5000, 1
        lsb = target & 0x7F  # 7 bits for least significant byte
        msb = (target >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x04) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self._transport_mock.read.return_value = b'\x00\x00'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        self.instr.set_target(channel, target)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_target_enforces_min_values(self):
        """Test setting the target value below the minimum allowed value.
        The set value will be ignored and the target will be set to the minimum."""
        # Arrange
        target, channel = -20, 1
        cmd = chr(0x04) + chr(channel) + chr(0x00) + chr(0x00)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self._transport_mock.read.return_value = b'\x00\x00'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        self.instr.set_target(channel, target)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_target_enforces_max_values(self):
        """Test setting the target value above the maximum allowed value.
        The set value will be ignored and the target will be set to the maximum."""
        # Arrange
        target, channel = 10000000, 1
        lsb = Pololu_Maestro.DEFAULT_MAX_VALUE & 0x7F
        msb = (Pololu_Maestro.DEFAULT_MAX_VALUE >> 7) & 0x7F
        cmd = chr(0x04) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self._transport_mock.read.return_value = b'\x00\x00'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        self.instr.set_target(channel, target)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_get_target_values(self):
        """Test get target values return expected values."""
        # Arrange
        expected_initial = [0] * Pololu_Maestro.DEFAULT_NUM_CHANNELS

        # Act
        initial = self.instr.get_targets()

        # Assert
        self.assertListEqual(expected_initial, initial)

    def test_get_position(self):
        """Test get position returns expected value."""
        # Arrange
        expected, channel = 5000, 0
        cmd = chr(0x10) + chr(channel)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        low_bit, high_bit = expected - (expected // 256 * 256), expected // 256
        self._transport_mock.read_until_timeout.side_effect = [
            chr(low_bit),
            chr(high_bit),
            b'\x00\x00'
        ]
        expected_write_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        result = self.instr.get_position(channel)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_write_calls)
        self.assertEqual(result, expected)

    def test_set_speed(self):
        """Test setting a new speed for a channel."""
        # Arrange
        speed, channel = 500, 1
        lsb = speed & 0x7F  # 7 bits for least significant byte
        msb = (speed >> 7) & 0x7F  # shift 7 and take next 7 bits for msb
        cmd = chr(0x07) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self._transport_mock.read.return_value = b'\x00\x00'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        self.instr.set_speed(channel, speed)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_speed_raises_exception(self):
        """Test setting an invalid speed for a channel raises an exception."""
        # Arrange
        speed, channel = 10000000, 1

        # Act and assert
        with self.assertRaises(ValueError):
            self.instr.set_speed(channel, speed)

    def test_set_acceleration(self):
        """Test setting a new acceleration for a channel."""
        # Arrange
        acceleration, channel = 50, 1
        lsb = acceleration & 0x7F  # 7 bits for least significant byte
        # shift 7 and take next 7 bits for msb
        msb = (acceleration >> 7) & 0x7F
        cmd = chr(0x09) + chr(channel) + chr(lsb) + chr(msb)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self._transport_mock.read.return_value = b'\x00\x00'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        self.instr.set_acceleration(channel, acceleration)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_acceleration_raises_exception(self):
        """Test setting an invalid acceleration for a channel raises an exception."""
        acceleration, channel = 500, 1
        with self.assertRaises(ValueError):
            self.instr.set_acceleration(channel, acceleration)

    def test_go_home(self):
        """Test homing."""
        # Arrange
        expected_command = bytes(self._cmd_lead + chr(0x22), "latin-1")
        self._transport_mock.read.return_value = b'\x00\x00'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        self.instr.go_home()

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_get_set_max_target(self):
        """Test setting new maximum value on a channel."""
        # Arrange
        expected = 6100
        channel = 2

        # Act
        self.instr.set_max_target(channel, expected)

        # Assert
        actual = self.instr.get_max_target(channel)
        self.assertEqual(expected, actual)

    def test_set_max_target_excepts(self):
        """Test that setting new maximum value outside valid range excepts."""
        invalid_maxes = [1100020394, -999]
        channel = 4

        for m in invalid_maxes:
            with self.assertRaises(ValueError):
                self.instr.set_max_target(channel, m)

    def test_get_set_min_target(self):
        """Test setting new minimum value on a channel."""
        # Arrange
        expected = 7
        channel = 2

        # Act
        self.instr.set_min_target(channel, expected)

        # Assert
        actual = self.instr.get_min_target(channel)
        self.assertEqual(expected, actual)

    def test_set_min_target_excepts(self):
        """Test that setting new minimum value outside valid range excepts."""
        invalid_maxes = [1100020394, -999]
        channel = 4

        for m in invalid_maxes:
            with self.assertRaises(ValueError):
                self.instr.set_min_target(channel, m)

    def test_command_error_check_excepts(self):
        """Make a command's error check to except"""
        # Arrange
        cmd = chr(0x22)
        expected_command = bytes(self._cmd_lead + cmd, "latin-1")
        self._transport_mock.read_until_timeout.return_value = b'\x00\xF0'
        expected_calls = [
            call(expected_command),
            call(self._error_check_cmd)
        ]

        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.instr.go_home()

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_wrong_channel_excepts(self):
        """Test a set command with wrong channel numbers and see that it excepts"""
        wrong_channels = (-1, Pololu_Maestro.DEFAULT_NUM_CHANNELS)
        for ch in wrong_channels:
            with self.assertRaises(ValueError):
                self.instr.set_target(ch, 0)


if __name__ == '__main__':
    unittest.main()
