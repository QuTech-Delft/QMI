import unittest, unittest.mock
import struct

from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs import Thorlabs_K10Cr2
from qmi.instruments.thorlabs.apt_packets import _AptMsgHwGetInfo

from tests.patcher import PatcherQmiContext

Thorlabs_K10Cr2.RESPONSE_TIMEOUT = 0.01
# Number of microsteps per degree of rotation.
MICROSTEPS_PER_DEGREE = 409600.0 / 3.0
# Internal velocity setting for 1 degree/second.
VELOCITY_FACTOR = 7329109.0
# Internal accleration setting for 1 degree/second/second.
ACCELERATION_FACTOR = 1502.0


class TestThorlabsK10cr2(unittest.TestCase):

    def setUp(self):
        self._pack = "<l"
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._transport_mock._safe_serial.in_waiting = 0
        self._transport_mock._safe_serial.out_waiting = 0
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.k10crx.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_K10Cr2 = Thorlabs_K10Cr2(PatcherQmiContext(), "instr", "transport_descriptor")

    def tearDown(self):
        self._transport_mock.reset_mock()

    def test_init(self):
        """Check the __init__ attributes."""
        # Arrange
        expected_max_velocity = 20
        expected_apt_device_address = 0x50
        expected_apt_host_address = 0x01
        expected_apt_timeout = Thorlabs_K10Cr2.RESPONSE_TIMEOUT
        # Assert
        self.assertEqual(expected_max_velocity, self.instr.MAX_VELOCITY)
        self.assertEqual(self.instr._transport, self._transport_mock)
        self.assertEqual(expected_apt_device_address, self.instr._apt_protocol._apt_device_address)
        self.assertEqual(expected_apt_host_address, self.instr._apt_protocol._host_address)
        self.assertEqual(expected_apt_timeout, self.instr._apt_protocol._timeout)

    def test_open_close(self):
        """Test opening and closing the instrument"""
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, 0x0005) + b"P\x01"  # This is 5001 == 0x1389
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack(self._pack, 0x0006) + b"\x00" * 2 + b"CR2\0K10" * 12
        # The request+data has to be 90 bytes long and should include string "K10CR2" at right spot.
        self._transport_mock.read.return_value = expected_read
        self.instr.open()
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)
        self.assertTrue(self.instr.is_open())

        self.instr.close()
        self.assertFalse(self.instr.is_open())

    def test_open_close_expects_with_timeout_when_correct_message_type_not_received(self):
        """Test opening the instrument fails if we give wrong (but otherwise valid) message id to the call"""
        expected_exception = "Expected message type {} not received.".format(_AptMsgHwGetInfo)
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo) but we give 0x0412
        expected_read = struct.pack(self._pack, 0x0412) + b"\x00\x00"
        self._transport_mock.read.return_value = expected_read + b"K10CR2"
        with self.assertRaises(QMI_TimeoutException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected_exception)

    def test_open_excepts_with_too_small_buffer(self):
        """Test opening the instrument time-outs"""
        # No response now to force exception
        self._transport_mock.read.return_value = b""
        with self.assertRaises(ValueError):
            self.instr.open()

    def test_open_excepts_with_timeout(self):
        """Test opening the instrument time-outs and raises QMI_InstrumentException"""
        # Long APT messages start with 0x80. Give unknown message ID 0x8080
        long_apt_msg = struct.pack(self._pack, 0x0006) + b"\x81\x5A"
        expected_exception = "Received partial message (message_id=0x{:04x}, data_length=0, data=b'')".format(0x0006)
        # Make a long APT message to go into the loop where more data should be read, and cause timeout
        self._transport_mock.read.side_effect = [long_apt_msg, QMI_TimeoutException]
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_open_with_no_pending_message(self):
        """Test opening the instrument and no pending message in buffer."""
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, 0x0005) + b"P\x01"  # This is 5001 == 0x1389
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack(self._pack, 0x0006) + b"\x81\x5A"
        # The request+data has to be 90 bytes long and should include string "K10CR2" at right spot.
        self._transport_mock.read.side_effect = [expected_read, b"CR2\0K10" * 12]
        self.instr.open()
        self.instr.close()
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_open_with_wrong_controller_excepts(self):
        """Test opening the instrument where a wrong model type is returned."""
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack("<l", 0x0005) + b"P\x01"  # This is 5001 == 0x1389
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack("<l", 0x0006) + b"\x81\x5A"
        # We expect wrong model message to be
        exception = "Driver only supports K10CR2 but instrument identifies as 'T10FN2'"
        # The request+data has to be 90 bytes long and should include model type string at right spot.
        self._transport_mock.read.side_effect = [expected_read, b"FN2\0T10" * 12]
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.open()

        # Assert
        self._transport_mock.write.assert_called_with(expected_write)
        self.assertEqual(exception, str(exc.exception))

    def test_open_excepts_with_unknown_message_id(self):
        """Test opening with unknown message ID fails"""
        expected_exception = "Received unknown message id 0x{:04x} from instrument".format(0x8080)
        # Make unexpected response MESSAGE_ID
        expected_read = struct.pack("l", 0x8080) + b"\x00\x00"
        self._transport_mock.read.return_value = expected_read
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_open_excepts_with_wrong_data_length(self):
        """Test opening the instrument excepts when wrong data length is received in _check_k10cr2."""
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack("<l", 0x0006) + b"\x81\x5A"
        expected_exception = ("Received partial message (message_id=0x{:04x}, ".format(0x0006) +
                             "data_length=0, data=b'')")
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [expected_read, b"\x01\x02", QMI_TimeoutException]
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(expected_exception, str(exc.exception))


class TestThorlabsK10cr2Methods(unittest.TestCase):

    def setUp(self):
        self._pack = "<l"
        self._empty = b"\x00" * 2
        self._displacement = 1 / MICROSTEPS_PER_DEGREE
        self._vel_scaling = VELOCITY_FACTOR
        self._acc_scaling = ACCELERATION_FACTOR
        self._max_vel = 20
        self._max_acc = 20
        # Mock serial transport
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._transport_mock._safe_serial.in_waiting = 0
        self._transport_mock._safe_serial.out_waiting = 0
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.k10crx.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_K10Cr2 = Thorlabs_K10Cr2(PatcherQmiContext(), "instr", "transport_descriptor")

        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo) to 'open'
        expected_read = struct.pack("<l", 0x0006)
        # The request+data has to be 90 bytes long and should include string "K10CR2" at right spot.
        self._transport_mock.read.return_value = expected_read + self._empty + b"CR2\0K10" * 12
        self.instr.open()
        # Clean up the mock for the tests.
        self._transport_mock.reset_mock()

    def tearDown(self):
        self.instr.close()

    def test_get_idn(self):
        """Test the get_idn method."""
        # First two values are hardcoded, and the two latter are based on the standard return value for read in `setUp`
        expected_idn = ["Thorlabs", "K10CR2", 3297859, "9.2.3"]
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, 0x0005) + b"P\x01"  # This is 5001 == 0x1389

        idn = self.instr.get_idn()
        self.assertEqual(expected_idn[0], idn.vendor)
        self.assertEqual(expected_idn[1], idn.model)
        self.assertEqual(expected_idn[2], idn.serial)
        self.assertEqual(expected_idn[3], idn.version)

        self._transport_mock.write.assert_called_with(expected_write)

    def test_set_velocity(self):
        """Test set_velocity can be used to set velocity."""
        # Value to set
        velocity = 1.2345
        # "previous values"
        old_vel = 2.3145
        old_accel = 5.4321
        # The method first calls to get current values with
        # _AptMsgReqVelParams 0x0414
        expected_write = [unittest.mock.call(struct.pack(self._pack, 0x10414) + b"P\x01")]  # This is 5001 == 0x1389
        # _AptMsgGetVelParams 0x0415
        # Define the bit strings
        max_vel = struct.pack(self._pack, int(round(old_vel * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(old_accel * ACCELERATION_FACTOR)))
        read_side_effect = [(
            struct.pack(self._pack, 0x0415) +
            struct.pack("<h", 0) +
            struct.pack("<h", 1) +  # chan ident
            struct.pack(self._pack, 0) +  # min velocity, always 0
            accel +
            max_vel
        )]
        # Then we expect to write _AptMsgSetVelParams 0x0413. "e" after x below tells the data follows in 14 bits.
        data_def_bits = b"\xd0\x01\x01\x00"
        read_side_effect.append(struct.pack(self._pack, 0xe0413) + data_def_bits + self._empty)
        # Add velocity and acceleration
        max_vel = struct.pack(self._pack, int(round(velocity * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(old_accel * ACCELERATION_FACTOR)))
        expected_write.append(unittest.mock.call(read_side_effect[1] + self._empty + accel + max_vel))
        self._transport_mock.read.side_effect = read_side_effect
        # Act
        self.instr.set_velocity(velocity)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_write)

    def test_set_velocity_already_set(self):
        """Test set_velocity does not try to set velocity when value is already set."""
        # Value to set
        velocity = 1.2345
        # "previous values"
        old_vel = velocity
        old_accel = 5.4321
        # The method first calls to get current values with
        # _AptMsgReqVelParams 0x0414
        expected_write = struct.pack(self._pack, 0x10414) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetVelParams 0x0415
        # Define the bit strings
        max_vel = struct.pack(self._pack, int(round(old_vel * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(old_accel * ACCELERATION_FACTOR)))
        read_side_effect = [(
            struct.pack(self._pack, 0x0415) +
            struct.pack("<h", 0) +
            struct.pack("<h", 1) +  # chan ident
            struct.pack(self._pack, 0) +  # min velocity, always 0
            accel +
            max_vel
        )]
        self._transport_mock.read.side_effect = read_side_effect
        # Act
        self.instr.set_velocity(velocity)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_set_velocity_params(self):
        """Test set_velocity_params can be used to set velocity and acceleration."""
        # Values to set
        velocity = 1.2345
        acceleration = 5.4321
        # We expect to write _AptMsgSetVelParams 0x0413. "e" after x below tells the data follows in 14 bits.
        data_def_bits = b"\xd0\x01\x01\x00"
        expected_read = struct.pack(self._pack, 0xe0413) + data_def_bits
        # velocity and acceleration get turned into ints in the command. Do the same here.
        # Add velocity and acceleration
        max_vel = struct.pack(self._pack, int(round(velocity * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(acceleration * ACCELERATION_FACTOR)))
        expected_write = expected_read + b"\x00\x00\x00\x00" + accel + max_vel
        self._transport_mock.read.return_value = expected_read + self._empty
        # Act
        self.instr.set_velocity_params(velocity, acceleration)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_set_velocity_value_out_of_range(self):
        """Test set_velocity raises exceptions at invalid values."""
        invalid_velocities = [0, self._max_vel + 0.1]
        for max_velocity in invalid_velocities:
            expected = f"Invalid value for {max_velocity=}"
            with self.assertRaises(ValueError) as exc:
                self.instr.set_velocity(max_velocity)

            self.assertEqual(expected, str(exc.exception))

    def test_set_velocity_params_values_out_of_range(self):
        """Test set_velocity_params raises exceptions at invalid values."""
        invalid_velocities = [0, Thorlabs_K10Cr2.MAX_VELOCITY + 0.1]
        invalid_accelerations = [0, Thorlabs_K10Cr2.MAX_ACCELERATION + 0.1]
        for max_velocity in invalid_velocities:
            expected1 = f"Invalid value for {max_velocity=}"
            with self.assertRaises(ValueError) as exc1:
                self.instr.set_velocity_params(max_velocity, 0.0)

            self.assertEqual(expected1, str(exc1.exception))

        valid_velocity = 1.2345
        for acceleration in invalid_accelerations:
            expected2 = f"Invalid value for {acceleration=}"
            with self.assertRaises(ValueError) as exc2:
                self.instr.set_velocity_params(valid_velocity, acceleration)

            self.assertEqual(expected2, str(exc2.exception))


if __name__ == '__main__':
    unittest.main()
