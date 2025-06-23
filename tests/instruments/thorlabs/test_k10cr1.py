import unittest, unittest.mock
import struct
import binascii
from typing import cast

from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs import Thorlabs_K10Cr1
from qmi.instruments.thorlabs.apt_packets import _AptMsgHwGetInfo, AptMessageId
import qmi.core.exceptions
from qmi.instruments.thorlabs.apt_protocol import AptChannelHomeDirection, AptChannelHomeLimitSwitch, AptChannelState

# Number of microsteps per degree of rotation.
MICROSTEPS_PER_DEGREE = 409600.0 / 3.0
# Internal velocity setting for 1 degree/second.
VELOCITY_FACTOR = 7329109.0
# Internal accleration setting for 1 degree/second/second.
ACCELERATION_FACTOR = 1502.0


class TestThorlabsK10cr1(unittest.TestCase):
    def setUp(self):
        qmi.start("TestK10cr1OpenClose")
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.k10cr1.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_K10Cr1 = qmi.make_instrument("instr", Thorlabs_K10Cr1, "transport_descriptor")
            self.instr = cast(Thorlabs_K10Cr1, self.instr)

    def tearDown(self):
        self._transport_mock.reset_mock()
        qmi.stop()

    def test_open_close(self):
        """Test opening and closing the instrument"""
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack("<l", 0x0005) + b"P\x01"  # This is 5001 == 0x1389
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack("<l", 0x0006)
        # The request+data has to be 90 bytes long and should include string "K10CR1" at right spot.
        self._transport_mock.read.return_value = expected_read + b"\x00" * 2 + b"CR1\0K10" * 12
        self.instr.open()
        self.instr.close()
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_open_close_expects_with_timeout_when_correct_message_type_not_received(self):
        """Test opening the instrument fails if we give wrong (but otherwise valid) message id to the call"""
        expected_exception = "Expected message type {} not received.".format(_AptMsgHwGetInfo)
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo) but we give 0x0412
        expected_read = struct.pack("<l", 0x0412) + b"\x00\x00"
        self._transport_mock.read.return_value = expected_read + b"K10CR1"
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException) as exc:
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
        # Long APT messages start with 0x80
        long_apt_msg = b"\x80" * 6
        expected_exception = "Received partial message (message_id=0x{:04x}, data_length={})".format(0x8080, 32896)
        # Make a long APT message to go into the loop where more data should be read, and cause timeout
        self._transport_mock.read.side_effect = [long_apt_msg, qmi.core.exceptions.QMI_TimeoutException]
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected_exception)

    def test_open_with_no_pending_message(self):
        """Test opening the instrument and no pending message in buffer."""
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack("<l", 0x0005) + b"P\x01"  # This is 5001 == 0x1389
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack("<l", 0x0006) + b"\x00" * 2 + b"CR1\0K10" * 12
        # The request+data has to be 90 bytes long and should include string "K10CR1" at right spot.
        self._transport_mock.read.side_effect = [qmi.core.exceptions.QMI_TimeoutException, expected_read]
        self.instr.open()
        self.instr.close()
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_open_excepts_with_unknown_message_id(self):
        """Test opening with unknown message ID fails"""
        expected_exception = "Received unknown message id 0x{:04x} from instrument".format(0x8080)
        # Make unexpected response MESSAGE_ID
        expected_read = struct.pack("l", 0x8080) + b"\x00\x00"
        self._transport_mock.read.return_value = expected_read
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected_exception)

    def test_open_excepts_with_wrong_data_length(self):
        """Test opening and closing the instrument"""
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack("l", 0x0006) + b"\x00\x00"
        expected_exception = "Received incorrect message length for message id 0x{:04x} ".format(0x0006) +\
                             "(got {} bytes while expecting {} bytes)".format(len(expected_read), 90)
        # The data should include string "K10CR1" at right spot.
        self._transport_mock.read.return_value = expected_read
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected_exception)


class TestThorlabsK10cr1Methods(unittest.TestCase):

    def setUp(self):
        self._pack = "<l"
        self._empty = b"\x00" * 2
        qmi.start("TestK10cr1Context")
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.k10cr1.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_K10Cr1 = qmi.make_instrument("instr", Thorlabs_K10Cr1, "transport_descriptor")
            self.instr = cast(Thorlabs_K10Cr1, self.instr)

        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo) to 'open'
        expected_read = struct.pack("<l", 0x0006)
        # The request+data has to be 90 bytes long and should include string "K10CR1" at right spot.
        self._transport_mock.read.return_value = expected_read + self._empty + b"CR1\0K10" * 12
        self.instr.open()
        # Clean up the mock for the tests.
        self._transport_mock.reset_mock()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_get_idn(self):
        """Test the get_idn method."""
        # First two values are hardcoded, and the two latter are based on the standard return value for read in `setUp`
        expected_idn = ["Thorlabs", "K10CR1", 3232323, "49.82.67"]
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, 0x0005) + b"P\x01"  # This is 5001 == 0x1389

        idn = self.instr.get_idn()
        self.assertEqual(idn.vendor, expected_idn[0])
        self.assertEqual(idn.model, expected_idn[1])
        self.assertEqual(idn.serial, expected_idn[2])
        self.assertEqual(idn.version, expected_idn[3])

        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_motor_status(self):
        """Test the get_motor_status method. Test returning all statuses as 'True', and as 'False'"""
        # We expect to write MESSAGE_ID 0x0429 (_AptMsgReqStatusBits).
        # Bit 1 after x below is to identify as "Get" command.
        expected_write = struct.pack(self._pack, 0x10429) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x042A)
        # Let's get all expected values as "True". The bit order is in reverse pairs.
        self._transport_mock.read.return_value = expected_read + self._empty + b"\x00\x00\xfb\xff\x00\x81"

        motor_status = self.instr.get_motor_status()

        self.assertTrue(all(list(motor_status.__dict__.values())))  # Check all statuses are "true"
        self._transport_mock.write.assert_called_with(expected_write)

        # Let's get all expected values as "False"
        self._transport_mock.read.reset_mock()
        self._transport_mock.read.return_value = expected_read + b"\x00\x00\x00\x00\x00\x00\x00\x00"

        motor_status = self.instr.get_motor_status()

        self.assertFalse(any(list(motor_status.__dict__.values())))  # Check all statuses are "false"
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
        position_bs = b"\x00\x30\x01\x01"
        self._transport_mock.read.return_value = expected_read + b"0000" + position_bs

        position = self.instr.get_absolute_position()

        self.assertEqual(round(position, 2), expected)
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_velocity_params(self):
        """Test get_velocity_params returns velocity and acceleration."""
        expected_max_vel = 123.45
        expected_accel = 543.21
        # _AptMsgReqVelParams 0x0414
        expected_write = struct.pack(self._pack, 0x10414) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetVelParams 0x0415
        expected_read = struct.pack(self._pack, 0x0415)
        # Manually define the bit strings
        max_vel = struct.pack("<f", expected_max_vel)  # b"\x0a\xd3\xed\x35"
        accel = struct.pack("<f", expected_accel)  # b"\x1d\x73\x0c\x00"
        self._transport_mock.read.return_value = expected_read + b"\x00\x00\x00\x00\x00\x00\x00\x00" + accel + max_vel

        velocity_params = self.instr.get_velocity_params()

        self.assertEqual(round(velocity_params.max_velocity, 2), expected_max_vel)
        self.assertEqual(round(velocity_params.acceleration, 2), expected_accel)
        self._transport_mock.write.assert_called_with(expected_write)

    def test_get_backlash_distance(self):
        """Test get_backlash_distance method returns expected value."""
        expected = 123.45
        # _AptMsgReqGenMoveParams 0x043B
        expected_write = struct.pack(self._pack, 0x1043B) + b"P\x01"  # This is 5001 == 0x1389
        # _AptMsgGetPosCounter 0x043C
        expected_read = struct.pack(self._pack, 0x043C)
        # We cannot change the enabled state so we content to having it as false
        self._transport_mock.read.return_value = expected_read + b"\x00\x00\x00\x00\x00\x30\x01\x01"

        distance = self.instr.get_backlash_distance()

        self.assertEqual(round(distance, 2), expected)
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
        home_vel = b"\x00\xd3\xed\x35"
        offset = b"\x00\xb0\x6b\x04"
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

    def test_set_velocity_params(self):
        """Test set_velocity_params can be used to set velocity and acceleration."""
        # Values to set
        velocity = 1.2345
        acceleration = 5.4321
        # We expect to write _AptMsgSetVelParams 0x0413. "e" after x below tells the data follows in 14 bits.
        data_def_bits = b"\xd0\x01\x01\x00"
        expected_read = struct.pack(self._pack, 0xe0413) + data_def_bits
        # velocity and acceleration get turned into ints in the command. Do the same here.
        vel_int = int(round(velocity * VELOCITY_FACTOR))
        acc_int = int(round(acceleration * ACCELERATION_FACTOR))
        # Then the command values are based on these ints. The length must be filled up to four bits.
        max_vel_hex = binascii.a2b_hex(hex(vel_int)[2:])
        accel_hex = binascii.a2b_hex(hex(acc_int)[2:])
        max_vel = b"\x00" * (4 - len(max_vel_hex)) + max_vel_hex
        accel = b"\x00" * (4 - len(accel_hex)) + accel_hex
        # Now we create the full expected write, with noting that the order is Little Endian (hence [::-1])
        expected_write = expected_read + b"\x00\x00\x00\x00" + accel[::-1] + max_vel[::-1]
        self._transport_mock.read.return_value = expected_read + self._empty
        # Act
        self.instr.set_velocity_params(velocity, acceleration)
        # Assert
        self._transport_mock.write.assert_called_with(expected_write)

    def test_set_velocity_params_values_out_of_range(self):
        """Test set_velocity_params raises exceptions at invalid values."""
        expected1 = "Invalid range for max_velocity"
        expected2 = "Invalid range for acceleration"

        velocity = 12.345
        acceleration = -43.210
        with self.assertRaises(ValueError) as exc1:
            self.instr.set_velocity_params(velocity, acceleration)

        valid_velocity = 1.2345
        with self.assertRaises(ValueError) as exc2:
            self.instr.set_velocity_params(valid_velocity, acceleration)

        self.assertEqual(str(exc1.exception), expected1)
        self.assertEqual(str(exc2.exception), expected2)

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
        home_dir_ok = 2
        limit_switch_ok = 1
        velocity_ok = 1.2345
        offset_dist_ok = 5.4321
        home_dir_nok = 0
        limit_switch_nok = 10
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
        for distance in too_far_distances:
            with self.assertRaises(ValueError):
                self.instr.move_relative(distance)

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
        for distance in too_far_distances:
            with self.assertRaises(ValueError):
                self.instr.move_absolute(distance)

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

        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException) as exc:
            self.instr.wait_move_complete(0.0)

        self._transport_mock.write.assert_called_with(expected_write)
        self.assertEqual(str(exc.exception), expected_exception)

    def test_wait_move_complete_excepts_with_timeout_2(self):
        """See that a move is completed. We need to suppress motor giving a response."""
        expected_read_calls = 2
        # We expect to write MESSAGE_ID 0x0429 (_AptMsgReqStatusBits).
        # Bit 1 after x below is to identify as "Get" command.
        expected_write = struct.pack(self._pack, 0x10429) + b"P\x01"  # This is 5001 == 0x1389
        expected_read = struct.pack(self._pack, 0x042A)
        unexpected_read = struct.pack(self._pack, 0x0429) + self._empty
        # Let's get all expected values as "False"
        self._transport_mock.read.side_effect = [unexpected_read, expected_read + b"\x00\x00\x00\x00\x00\x00\x00\x00"]

        self.instr.wait_move_complete(0.0)

        self._transport_mock.write.assert_called_with(expected_write)
        self.assertEqual(self._transport_mock.read.call_count, expected_read_calls)


if __name__ == '__main__':
    unittest.main()
