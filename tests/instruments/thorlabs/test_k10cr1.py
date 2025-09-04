import unittest, unittest.mock
import struct
import binascii

from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs import Thorlabs_K10Cr1
from qmi.instruments.thorlabs.apt_packets import _AptMsgHwGetInfo, AptMessageId
from qmi.instruments.thorlabs.apt_protocol import AptChannelHomeDirection, AptChannelHomeLimitSwitch, AptChannelState

from tests.patcher import PatcherQmiContext

Thorlabs_K10Cr1.RESPONSE_TIMEOUT = 0.01
# Number of microsteps per degree of rotation.
MICROSTEPS_PER_DEGREE = 409600.0 / 3.0
# Internal velocity setting for 1 degree/second.
VELOCITY_FACTOR = 7329109.0
# Internal accleration setting for 1 degree/second/second.
ACCELERATION_FACTOR = 1502.0


class TestThorlabsK10cr1(unittest.TestCase):

    def setUp(self):
        self._pack = "<l"
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._transport_mock._safe_serial.in_waiting = 0
        self._transport_mock._safe_serial.out_waiting = 0
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.k10cr1.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_K10Cr1 = Thorlabs_K10Cr1(PatcherQmiContext(), "instr", "transport_descriptor")

    def tearDown(self):
        self._transport_mock.reset_mock()

    def test_open_close(self):
        """Test opening and closing the instrument"""
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, 0x0005) + b"P\x01"  # This is 5001 == 0x1389
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack(self._pack, 0x0006) + b"\x00" * 2 + b"CR1\0K10" * 12
        # The request+data has to be 90 bytes long and should include string "K10CR1" at right spot.
        self._transport_mock.read.return_value = expected_read
        self.instr.open()
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

        self.instr.close()

    def test_open_close_expects_with_timeout_when_correct_message_type_not_received(self):
        """Test opening the instrument fails if we give wrong (but otherwise valid) message id to the call"""
        expected_exception = "Expected message type {} not received.".format(_AptMsgHwGetInfo)
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo) but we give 0x0412
        expected_read = struct.pack(self._pack, 0x0412) + b"\x00\x00"
        self._transport_mock.read.return_value = expected_read + b"K10CR1"
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
        # The request+data has to be 90 bytes long and should include string "K10CR1" at right spot.
        self._transport_mock.read.side_effect = [expected_read, b"CR1\0K10" * 12]
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
        exception = "Driver only supports K10CR1 but instrument identifies as 'T10FN2'"
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
        """Test opening the instrument excepts when wrong data length is received in _check_k10cr1."""
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack("<l", 0x0006) + b"\x81\x5A"
        expected_exception = ("Received partial message (message_id=0x{:04x}, ".format(0x0006) +
                             "data_length=0, data=b'')")
        self._transport_mock.reset_mock()
        self._transport_mock.read.side_effect = [expected_read, b"\x01\x02", QMI_TimeoutException]
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(expected_exception, str(exc.exception))


class TestThorlabsK10cr1Methods(unittest.TestCase):

    def setUp(self):
        self._pack = "<l"
        self._empty = b"\x00" * 2
        self._displacement = 1 / 409600.0 * 3.0
        self._vel_scaling = 7329109.0
        self._acc_scaling = 1502.0
        self._max_vel = 10
        self._max_acc = 20
        # Mock serial transport
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._transport_mock._safe_serial.in_waiting = 0
        self._transport_mock._safe_serial.out_waiting = 0
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.k10cr1.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_K10Cr1 = Thorlabs_K10Cr1(PatcherQmiContext(), "instr", "transport_descriptor")

        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo) to 'open'
        expected_read = struct.pack("<l", 0x0006)
        # The request+data has to be 90 bytes long and should include string "K10CR1" at right spot.
        self._transport_mock.read.return_value = expected_read + self._empty + b"CR1\0K10" * 12
        self.instr.open()
        # Clean up the mock for the tests.
        self._transport_mock.reset_mock()

    def tearDown(self):
        self.instr.close()

    def test_get_idn(self):
        """Test the get_idn method."""
        # First two values are hardcoded, and the two latter are based on the standard return value for read in `setUp`
        expected_idn = ["Thorlabs", "K10CR1", 3232323, "3.2.3"]
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, 0x0005) + b"P\x01"  # This is 5001 == 0x1389

        idn = self.instr.get_idn()
        self.assertEqual(expected_idn[0], idn.vendor)
        self.assertEqual(expected_idn[1], idn.model)
        self.assertEqual(expected_idn[2], idn.serial)
        self.assertEqual(expected_idn[3], idn.version)

        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_motor_status(self):
        """Test the get_motor_status method. Test returning all statuses as 'True', and as 'False'"""
        # We expect to write MESSAGE_ID 0x0429 (_AptMsgReqStatusBits).
        # Bit 1 after x below is to identify as "Get" command.
        expected_write = struct.pack(self._pack, 0x10429) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x042A)
        # Let's get all expected values as "True". The bit order is in reverse pairs.
        self._transport_mock.read.return_value = expected_read + b"\x50\x01" + b"\xff" * 32 + b"\x00\x81"

        motor_status = self.instr.get_motor_status()

        self.assertTrue(all(list(motor_status.__dict__.values())))  # Check all statuses are "true"
        self._transport_mock.write.assert_called_with(expected_write)

        # Let's get all expected values as "False"
        self._transport_mock.read.reset_mock()
        self._transport_mock.read.return_value = expected_read + b"\x00" * 36

        motor_status = self.instr.get_motor_status()

        self.assertFalse(all(list(motor_status.__dict__.values())))  # Check all statuses are "false"
        self._transport_mock.write.assert_called_with(expected_write)

    def test_identify(self):
        """Test the identify method"""
        # We expect to write MESSAGE_ID 0x0223 (_AptMsgIdentify).
        expected_write = struct.pack(self._pack, 0x10223) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x0223)
        # We have no other requirements from the read than the start being the same as the write
        self._transport_mock.read.return_value = expected_read + self._empty

        self.instr.identify()

        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_chan_enable_state_enabled(self):
        """Test get_chan_enable_state method returns channel enabled state."""
        # _AptMsgReqChanEnableState 0x0211
        expected_write = struct.pack(self._pack, 0x10211) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetChanEnableState 0x0212
        expected_read = struct.pack(self._pack, 0x1000000 + 0x0212)
        self._transport_mock.read.return_value = expected_read + b"00"

        state = self.instr.get_chan_enable_state()

        self.assertTrue(state)
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_chan_enable_state_disabled(self):
        """Test get_chan_enable_state method returns channel enabled state."""
        # _AptMsgReqChanEnableState 0x0211
        expected_write = struct.pack(self._pack, 0x10211) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetChanEnableState 0x0212
        expected_read = struct.pack(self._pack, 0x2000000 + 0x0212)
        self._transport_mock.read.return_value = expected_read + b"00"

        state = self.instr.get_chan_enable_state()

        self.assertFalse(state)
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_chan_enable_state_invalid_response(self):
        """Test get_chan_enable_state method raises an error by invalid channel enabled state."""
        # _AptMsgReqChanEnableState 0x0211
        expected_write = struct.pack(self._pack, 0x10211) + b"P\x01"  # This is 5001 == 0x1389
        invalid_states = [0, 4]
        for invalid_state in invalid_states:
            expected_error = f"{invalid_state} is not a valid channel enable state."
            # _AptMsgGetChanEnableState 0x0212
            invalid_read = struct.pack(self._pack, (invalid_state << 24) + 0x0212)
            self._transport_mock.read.return_value = invalid_read + b"00"

            # As invalid enabled state raises an error, we need to assert it:
            with self.assertRaises(ValueError) as v_err:
                self.instr.get_chan_enable_state()

            self.assertEqual(expected_error, str(v_err.exception))
            self._transport_mock.write.assert_called_with(expected_write)
            self._transport_mock.reset_mock()

    def test_get_absolute_position(self):
        """Test get_absolute_position method returns expected position."""
        expected = 123.45
        # _AptMsgReqPosCounter 0x0411
        expected_write = struct.pack(self._pack, 0x10411) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetPosCounter 0x0412
        expected_read = struct.pack(self._pack, 0x0412)
        # Add the position value at the end
        position_bs = struct.pack(self._pack, int(round(expected * Thorlabs_K10Cr1.MICROSTEPS_PER_DEGREE)))
        self._transport_mock.read.return_value = expected_read + b"0000" + position_bs

        position = self.instr.get_absolute_position()

        self.assertEqual(round(position, 2), expected)
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_velocity(self):
        """Test get_velocity returns velocity."""
        expected_max_vel = 123.45
        # _AptMsgReqVelParams 0x0414
        expected_write = struct.pack(self._pack, 0x10414) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetVelParams 0x0415
        # Define the bit strings
        max_vel = struct.pack(self._pack, int(round(expected_max_vel * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(543.21 * ACCELERATION_FACTOR)))
        self._transport_mock.read.return_value = (
            struct.pack(self._pack, 0x0415) +
            struct.pack("<h", 0) +
            struct.pack("<h", 1) +  # chan ident
            struct.pack(self._pack, 0) +  # min velocity, always 0
            accel +
            max_vel
        )

        velocity = self.instr.get_velocity()

        self.assertEqual(expected_max_vel, round(velocity, 2))
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_acceleration(self):
        """Test get_acceleration returns acceleration."""
        expected_accel = 543.21
        # _AptMsgReqVelParams 0x0414
        expected_write = struct.pack(self._pack, 0x10414) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetVelParams 0x0415
        # Define the bit strings
        max_vel = struct.pack(self._pack, int(round(123.45 * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(expected_accel * ACCELERATION_FACTOR)))
        self._transport_mock.read.return_value = (
            struct.pack(self._pack, 0x0415) +
            struct.pack("<h", 0) +
            struct.pack("<h", 1) +  # chan ident
            struct.pack(self._pack, 0) +  # min velocity, always 0
            accel +
            max_vel
        )

        acceleration = self.instr.get_acceleration()

        self.assertEqual(expected_accel, round(acceleration, 2))
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_velocity_params(self):
        """Test get_velocity_params returns velocity and acceleration."""
        expected_max_vel = 123.45
        expected_accel = 543.21
        # _AptMsgReqVelParams 0x0414
        expected_write = struct.pack(self._pack, 0x10414) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetVelParams 0x0415
        # Define the bit strings
        max_vel = struct.pack(self._pack, int(round(expected_max_vel * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(expected_accel * ACCELERATION_FACTOR)))
        self._transport_mock.read.return_value = (
            struct.pack(self._pack, 0x0415) +
            struct.pack("<h", 0) +
            struct.pack("<h", 1) +  # chan ident
            struct.pack(self._pack, 0) +  # min velocity, always 0
            accel +
            max_vel
        )

        velocity_params = self.instr.get_velocity_params()

        self.assertEqual(expected_max_vel, round(velocity_params.max_velocity, 2))
        self.assertEqual(expected_accel, round(velocity_params.acceleration, 2))
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_backlash_distance(self):
        """Test get_backlash_distance method returns expected value."""
        expected = 123.45
        # _AptMsgReqGenMoveParams 0x043B
        expected_write = struct.pack(self._pack, 0x1043B) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetPosCounter 0x043C
        # We cannot change the enabled state so we content to having it as false
        self._transport_mock.read.return_value = (
            struct.pack(self._pack, 0x043C) +
            struct.pack("<h", 0) +
            struct.pack("<h", 1) +  # chan ident
            struct.pack(self._pack, int(round(expected * MICROSTEPS_PER_DEGREE)))
        )
        distance = self.instr.get_backlash_distance()

        self.assertEqual(expected, round(distance, 2))
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_home_params(self):
        """Test get_home_params returns velocity and acceleration."""
        expected_home_dir = AptChannelHomeDirection.FORWARD
        expected_limit_switch = AptChannelHomeLimitSwitch.FORWARD
        expected_velocity = 123.45
        expected_offset = 543.21
        # _AptMsgReqHomeParams 0x0441
        expected_write = struct.pack(self._pack, 0x10441) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetHomeParams 0x0442
        expected_read = struct.pack(self._pack, 0x0442) + b"\x00\x00\x00\x00"
        # manually define the bit strings
        home_dir = binascii.unhexlify(f"000{expected_home_dir.value}")
        limit_switch = binascii.unhexlify(f"000{expected_limit_switch.value}")
        # Add the velocity value
        home_vel = struct.pack(self._pack, int(round(expected_velocity * VELOCITY_FACTOR)))
        # Add the position value at the end
        offset = struct.pack(self._pack, int(round(expected_offset * MICROSTEPS_PER_DEGREE)))
        self._transport_mock.read.return_value = expected_read + home_dir[::-1] + limit_switch[::-1] + home_vel + offset

        home_params = self.instr.get_home_params()

        self._transport_mock.write.assert_called_with(expected_write)
        self.assertEqual(home_params.home_direction, expected_home_dir)
        self.assertEqual(home_params.limit_switch, expected_limit_switch)
        self.assertEqual(round(home_params.home_velocity, 2), expected_velocity)
        self.assertEqual(round(home_params.offset_distance, 2), expected_offset)

    def test_set_chan_enable_state(self):
        """Test set_chan_enable_state can be used to set state to True and False."""
        # We expect to write MESSAGE_ID 0x0210 (_AptMsgSetChanEnableState). Don't know why need to add 101 after x.
        msg_id = AptMessageId.MOD_SET_CHANENABLESTATE.value
        expected_write = struct.pack(self._pack, 0x1010000 + msg_id) + b"P\x01"  # This is 5001 == 0x1389
        # expected_write = struct.pack(self._pack, 0x1010210) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x0210)
        # We have no other requirements from the read than the start being the same as the write
        self._transport_mock.read.return_value = expected_read + self._empty

        self.instr.set_chan_enable_state(True)

        self._transport_mock.write.assert_called_with(expected_write)

        # Let's try setting it as False as well. Note the different start now in 'expected_write'
        expected_write = struct.pack(self._pack, 0x2010210) + b"P\x01"  # This is 5001 == 0x1389

        self.instr.set_chan_enable_state(False)

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

    def test_set_acceleration(self):
        """Test set_acceleration can be used to set acceleration."""
        # Values to set
        acceleration = 5.4321
        # "previous values"
        old_vel = 2.3145
        old_accel = 3.5421
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
        # velocity and acceleration get turned into ints in the command. Do the same here.
        # Add velocity and acceleration
        max_vel = struct.pack(self._pack, int(round(old_vel * VELOCITY_FACTOR)))
        accel = struct.pack(self._pack, int(round(acceleration * ACCELERATION_FACTOR)))
        expected_write.append(unittest.mock.call(read_side_effect[1] + self._empty + accel + max_vel))
        self._transport_mock.read.side_effect = read_side_effect
        # Act
        self.instr.set_acceleration(acceleration)
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

    def test_set_acceleration_already_set(self):
        """Test set_acceleration will not set acceleration if the value is already set."""
        # Values to set
        acceleration = 5.4321
        # "previous values"
        old_vel = 2.3145
        old_accel = acceleration
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
        self.instr.set_acceleration(acceleration)
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

    def test_set_acceleration_value_out_of_range(self):
        """Test set_acceleration raises exceptions at invalid values."""
        invalid_accelerations = [0, self._max_acc + 0.1]
        for acceleration in invalid_accelerations:
            expected = f"Invalid value for {acceleration=}"
            with self.assertRaises(ValueError) as exc:
                self.instr.set_acceleration(acceleration)

            self.assertEqual(expected, str(exc.exception))

    def test_set_velocity_params_values_out_of_range(self):
        """Test set_velocity_params raises exceptions at invalid values."""
        invalid_velocities = [0, Thorlabs_K10Cr1.MAX_VELOCITY + 0.1]
        invalid_accelerations = [0, Thorlabs_K10Cr1.MAX_ACCELERATION + 0.1]
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

    def test_set_backlash_distance(self):
        """Test setting a backlash distance."""
        # Values to set
        distance = MICROSTEPS_PER_DEGREE / 20.0
        # We expect to write _AptMsgSetGenMoveParams 0x043A. "6" after x below tells the data follows in 6 bits.
        data_def_bits = b"\xd0\x01"
        expected_read = struct.pack(self._pack, 0x6043A) + data_def_bits
        # velocity and acceleration get turned into ints in the command. Do the same here.
        dist_int = int(round(distance * MICROSTEPS_PER_DEGREE))
        # Then the command values are based on these ints. The length must be filled up to four bits.
        dist_int_hex = binascii.a2b_hex((hex(dist_int))[2:])
        dist_bs = b"\x00" * (4 - len(dist_int_hex)) + dist_int_hex
        # Now we create the full expected write, with noting that the order is Little Endian (hence [::-1])
        expected_write = expected_read + b"\x01\x00" + dist_bs[::-1]
        self._transport_mock.read.return_value = expected_read
        # Act
        self.instr.set_backlash_distance(distance)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_set_backlash_distance_out_of_range(self):
        """Test that the backlash distance excepts if not within uint32 range."""
        too_far_distances = [-2**31 / MICROSTEPS_PER_DEGREE, 2**31 / MICROSTEPS_PER_DEGREE]
        for distance in too_far_distances:
            with self.assertRaises(ValueError):
                self.instr.set_backlash_distance(distance)

    def test_set_home_params(self):
        """Test set_home_params can be used to set direction, limit switch, velocity and offset distance."""
        # Values to set
        home_dir = AptChannelHomeDirection.REVERSE
        limit_switch = AptChannelHomeLimitSwitch.REVERSE
        velocity = 1.2345
        offset_dist = 5.4321
        # We expect to write _AptMsgSetHomeParams 0x0440. "e" after x below tells the data follows in 14 bits.
        data_def_bits = b"\xd0\x01\x01\x00"
        expected_read = struct.pack(self._pack, 0xe0440) + data_def_bits
        # velocity and offset get turned into ints in the command. Do the same here.
        vel_int = int(round(velocity * VELOCITY_FACTOR))
        # Then the command values are based on these ints. The length must be filled up to four bits.
        home_vel_hex = binascii.a2b_hex(hex(vel_int)[2:])
        home_vel = b"\x00" * (4 - len(home_vel_hex)) + home_vel_hex
        offset = b"\x00\x0b\x51\x1f"
        home_dir_bs = binascii.unhexlify(f"000{home_dir.value}")
        limit_switch_bs = binascii.unhexlify(f"000{limit_switch.value}")
        # Now we create the full expected write, with noting that the order is Little Endian (hence [::-1])
        expected_write = expected_read + home_dir_bs[::-1] + limit_switch_bs[::-1] + home_vel[::-1] + offset[::-1]
        self._transport_mock.read.return_value = expected_read + self._empty
        # Act
        self.instr.set_home_params(home_dir, limit_switch, velocity, offset_dist)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_set_home_params_excepts_with_values_out_of_range(self):
        """Test set_home_params excepts with invalid direction, limit switch, velocity and offset distance."""
        # Values to set
        home_dir_ok = AptChannelHomeDirection.REVERSE
        limit_switch_ok = AptChannelHomeLimitSwitch.REVERSE
        velocity_ok = 1.2345
        offset_dist_ok = 5.4321
        home_dir_nok = AptChannelHomeDirection.FORWARD
        limit_switch_nok = AptChannelHomeLimitSwitch.FORWARD
        home_velocity_noks = [0, 6]
        offset_noks = [-2**31 / MICROSTEPS_PER_DEGREE, 2**31 / MICROSTEPS_PER_DEGREE]
        # Test home_direction
        with self.assertRaises(ValueError):
            self.instr.set_home_params(home_dir_nok, limit_switch_ok, velocity_ok, offset_dist_ok)

        # Test limit_switch
        with self.assertRaises(ValueError):
            self.instr.set_home_params(home_dir_ok, limit_switch_nok, velocity_ok, offset_dist_ok)

        # Test home_velocity
        for home_vel in home_velocity_noks:
            with self.assertRaises(ValueError):
                self.instr.set_home_params(home_dir_ok, limit_switch_ok, home_vel, offset_dist_ok)

        # Test offset_distance
        for offset in offset_noks:
            with self.assertRaises(ValueError):
                self.instr.set_home_params(home_dir_ok, limit_switch_ok, velocity_ok, offset)

    def test_move_stop(self):
        """Test the move_stop method without immediate stop"""
        # We expect to write _AptMsgMoveStop 0x0465.
        expected_write = struct.pack(self._pack, 0x2010465) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x0465)
        # We have no other requirements from the read than the start being the same as the write
        self._transport_mock.read.return_value = expected_read + self._empty

        self.instr.move_stop()

        self._transport_mock.write.assert_called_with(expected_write)

    def test_move_stop_immediate(self):
        """Test the move_stop method with immediate stop"""
        # We expect to write _AptMsgMoveStop 0x0465.
        expected_write = struct.pack(self._pack, 0x1010465) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x0465)
        # We have no other requirements from the read than the start being the same as the write
        self._transport_mock.read.return_value = expected_read + self._empty

        self.instr.move_stop(True)

        self._transport_mock.write.assert_called_with(expected_write)

    def test_move_home(self):
        """Test the move_home method."""
        # We expect to write _AptMsgMoveHome 0x0443.
        expected_write = struct.pack(self._pack, 0x10443) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x0443)
        # We have no other requirements from the read than the start being the same as the write
        self._transport_mock.read.return_value = expected_read + self._empty

        self.instr.move_home()

        self._transport_mock.write.assert_called_with(expected_write)

    def test_move_relative(self):
        """Test moving a relative distance."""
        # Values to set
        distance = MICROSTEPS_PER_DEGREE / 20.0
        # We expect to write _AptMsgMoveRelative 0x0448. "6" after x below tells the data follows in 6 bits.
        data_def_bits = b"\xd0\x01"
        expected_read = struct.pack(self._pack, 0x60448) + data_def_bits
        # velocity and acceleration get turned into ints in the command. Do the same here.
        dist_int = int(round(distance * MICROSTEPS_PER_DEGREE))
        # Then the command values are based on these ints. The length must be filled up to four bits.
        dist_int_hex = binascii.a2b_hex((hex(dist_int))[2:])
        dist_bs = b"\x00" * (4 - len(dist_int_hex)) + dist_int_hex
        # Now we create the full expected write, with noting that the order is Little Endian (hence [::-1])
        expected_write = expected_read + b"\x01\x00" + dist_bs[::-1]
        self._transport_mock.read.return_value = expected_read
        # Act
        self.instr.move_relative(distance)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_move_relative_out_of_range(self):
        """Test that the move_relative excepts if not within uint32 range."""
        too_far_distances = [-2**31 / MICROSTEPS_PER_DEGREE, 2**31 / MICROSTEPS_PER_DEGREE]
        exception = "Relative distance out of valid range"
        for distance in too_far_distances:
            with self.assertRaises(ValueError) as exc:
                self.instr.move_relative(distance)

            self.assertEqual(exception, str(exc.exception))

    def test_move_absolute(self):
        """Test moving a relative distance."""
        # Values to set
        distance = MICROSTEPS_PER_DEGREE / 20.0
        # We expect to write _AptMsgMoveAbsolute 0x0453. "6" after x below tells the data follows in 6 bits.
        data_def_bits = b"\xd0\x01"
        expected_read = struct.pack(self._pack, 0x60453) + data_def_bits
        # velocity and acceleration get turned into ints in the command. Do the same here.
        dist_int = int(round(distance * MICROSTEPS_PER_DEGREE))
        # Then the command values are based on these ints. The length must be filled up to four bits.
        dist_int_hex = binascii.a2b_hex((hex(dist_int))[2:])
        dist_bs = b"\x00" * (4 - len(dist_int_hex)) + dist_int_hex
        # Now we create the full expected write, with noting that the order is Little Endian (hence [::-1])
        expected_write = expected_read + b"\x01\x00" + dist_bs[::-1]
        self._transport_mock.read.return_value = expected_read
        # Act
        self.instr.move_absolute(distance)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_move_absolute_out_of_range(self):
        """Test that the move_absolute excepts if not within uint32 range."""
        too_far_distances = [-2**31 / MICROSTEPS_PER_DEGREE, 2**31 / MICROSTEPS_PER_DEGREE]
        exception = "Absolute position out of valid range"
        for distance in too_far_distances:
            with self.assertRaises(ValueError) as exc:
                self.instr.move_absolute(distance)

            self.assertEqual(exception, str(exc.exception))

    def test_wait_move_complete(self):
        """See that a move is completed. We need to get False for all motor moves values."""
        # We expect to write MESSAGE_ID 0x0429 (_AptMsgReqStatusBits).
        # Bit 1 after x below is to identify as "Get" command.
        expected_write = struct.pack(self._pack, 0x10429) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x042A)
        # Let's get all expected values as "False"
        self._transport_mock.read.return_value = expected_read + b"\x00\x00\x00\x00\x00\x00\x00\x00"

        self.instr.wait_move_complete(0.0)

        self._transport_mock.write.assert_called_with(expected_write)

    def test_wait_move_complete_excepts_with_timeout(self):
        """See that a move is completed. We need to get True for all motor moves values."""
        expected_exception = "Timeout while waiting for end of move"
        # We expect to write MESSAGE_ID 0x0429 (_AptMsgReqStatusBits).
        # Bit 1 after x below is to identify as "Get" command.
        expected_write = struct.pack(self._pack, 0x10429) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x042A)
        # Let's get all expected values as "True". The bit order is in reverse pairs.
        self._transport_mock.read.return_value = expected_read + b"\x00\x00\x00\x00\xfb\xff\x00\x81"

        with self.assertRaises(QMI_TimeoutException) as exc:
            self.instr.wait_move_complete(0.0)

        self._transport_mock.write.assert_called_with(expected_write)
        self.assertEqual(str(exc.exception), expected_exception)

    def test_wait_move_complete_excepts_with_timeout_2(self):
        """See that a move is completed. We need to suppress motor giving a response."""
        # We expect to write MESSAGE_ID 0x0429 (_AptMsgReqStatusBits).
        # Bit 1 after x below is to identify as "Get" command.
        expected_write = struct.pack(self._pack, 0x10429) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x042A) + b"\x81\x00"
        unexpected_read = struct.pack(self._pack, 0x0429) + self._empty
        # Let's get all expected values as "False"
        self._transport_mock.read.side_effect = [unexpected_read, expected_read, b"\x00\x00\x00\x00\x00\x00\x00\x00"]

        with self.assertRaises(QMI_TimeoutException):
            self.instr.wait_move_complete(1.0)

        self._transport_mock.write.assert_called_with(expected_write)
        self._transport_mock.read.assert_called_once_with(nbytes=6, timeout=Thorlabs_K10Cr1.RESPONSE_TIMEOUT)


if __name__ == '__main__':
    unittest.main()
