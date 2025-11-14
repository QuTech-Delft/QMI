import random
import struct
import unittest
import unittest.mock

from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs import Thorlabs_Mpc320
from qmi.instruments.thorlabs.apt_protocol import AptChannelJogDirection, AptChannelState
from qmi.instruments.thorlabs.apt_packets import AptMessageId, _AptMsgHwGetInfo

from tests.patcher import PatcherQmiContext

Thorlabs_Mpc320.DEFAULT_RESPONSE_TIMEOUT = 0.01


class TestThorlabsMPC320(unittest.TestCase):
    position_conversion = 1370 / 170

    def setUp(self):
        self._pack = "<l"
        self._empty = b"\x00" * 2
        self.dest = 0x50 | 0x80
        self.source = 0x01
        # Patch QMI context and make instrument
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        self._transport_mock._safe_serial.in_waiting = 0
        self._transport_mock._safe_serial.out_waiting = 0
        with unittest.mock.patch(
            "qmi.instruments.thorlabs.mpc320.create_transport",
            return_value=self._transport_mock,
        ):
            self._instr = Thorlabs_Mpc320(PatcherQmiContext(), "test_mpc320", "serial:transport_str")
        self._instr.open()

    def tearDown(self):
        self._instr.close()

    def test_get_idn_sends_command_and_returns_identification_info(self):
        """Test get_idn method and returns identification info."""
        # Arrange
        expected_idn = ["Thorlabs", b"MPC320", 94000009, 3735810]
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, AptMessageId.HW_REQ_INFO.value) + b"P\x01"
        # We expect as response MESSAGE_ID 0x0006 (_AptMsgHwGetInfo)
        expected_read = struct.pack(self._pack, 0x540000 + AptMessageId.HW_GET_INFO.value)
        # The request+data has to be 90 bytes long and should include string "MPC320" at right spot.
        serial_bytes = expected_idn[2].to_bytes(4, byteorder="little")
        version_bytes = expected_idn[3].to_bytes(4, byteorder="little")
        self._transport_mock.read.return_value = (
            expected_read + self._empty + serial_bytes + b"MPC320\0" + b"000" + version_bytes + b"0" * 66
        )
        # Act
        idn = self._instr.get_idn()

        # Assert
        self.assertEqual(expected_idn[0], idn.vendor)
        self.assertEqual(expected_idn[1], idn.model)
        self.assertEqual(expected_idn[2], idn.serial)
        self.assertEqual(expected_idn[3], idn.version)

        self._transport_mock.write.assert_called_once_with(expected_write)
        self._transport_mock.read.assert_called_once()

    def test_get_idn_with_wrong_returned_msg_id_throws_error(self):
        """Test get_idn method with wrong message ID and see that it excepts."""
        # Arrange
        expected_error = (f"Expected message type {_AptMsgHwGetInfo} not received.")
        # We expect to write MESSAGE_ID 0x0005 (_AptMsgHwReqInfo)
        expected_write = struct.pack(self._pack, AptMessageId.HW_REQ_INFO.value) + b"P\x01"
        # As response we get unexpectedly MESSAGE_ID 0x0412 (_AptMsgGetPosCounter)
        unexpected_read = struct.pack(self._pack, AptMessageId.MOT_GET_POS_COUNTER.value)
        # The request+data has to be 90 bytes long and should include string "MPC320" at right spot.
        self._transport_mock.read.side_effect = [unexpected_read + b"\x81\x00", b"320\0MPC" * 12]

        # Act
        with self.assertRaises(QMI_TimeoutException) as exc:
            _ = self._instr.get_idn()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))
        self._transport_mock.write.assert_called_once_with(expected_write)
        self._transport_mock.read.assert_has_calls([
            unittest.mock.call(nbytes=6, timeout=Thorlabs_Mpc320.DEFAULT_RESPONSE_TIMEOUT),
            unittest.mock.call(nbytes=0, timeout=0.050)
        ])

    def test_identify_sends_command(self):
        """Test identify method and send relevant command."""
        # Arrange
        expected_write = struct.pack(self._pack, 0x10000 + AptMessageId.MOD_IDENTIFY.value) + b"P\x01"

        # Act
        self._instr.identify()

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_enable_channels_enable_four_throws_exception(self):
        """Test enable channel 4, throws exception."""
        # Arrange

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.enable_channels([4])

    def test_enable_channels_enable_one_sends_command(self):
        """Test enable channel 1, send command to enable channel 1."""
        # Arrange
        channel = 2
        enable = 1
        msg_id = AptMessageId.MOD_SET_CHANENABLESTATE.value
        expected_write = struct.pack(self._pack, (channel << 16) + (enable << 24) + msg_id) + b"P\x01"

        # Act
        self._instr.enable_channels([channel])

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_enable_channels_enable_one_and_three_sends_command(self):
        """Test enable channels 1 and 3, sends command to enable channels 1 and 3."""
        # Arrange
        channel = 0x1 ^ 0x4  # channel 1 = 0x1, channel 2 = 0x2, channel 3 = 0x4
        enable = 1
        msg_id = AptMessageId.MOD_SET_CHANENABLESTATE.value
        expected_write = struct.pack(self._pack, (channel << 16) + (enable << 24) + msg_id) + b"P\x01"

        # Act
        self._instr.enable_channels([1, 3])

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_disable_all_channels_sends_command(self):
        """Test disable all channels, sends command to disable all channels."""
        # Arrange
        expected_write = struct.pack(self._pack, 0x1000000 + AptMessageId.MOD_SET_CHANENABLESTATE.value) + b"P\x01"

        # Act
        self._instr.disable_all_channels()

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_channel_state_for_channel_four_throws_exception(self):
        """Test get state of channel 4, throws exception."""
        # Arrange
        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.get_channel_state(4)

    def test_get_channel_state_for_disabled_channel_1_sends_command_and_returns_disable_value(
        self,
    ):
        """Test get state of disabled channel 1, sends command to get state."""
        # Arrange
        channel = 1
        expected_state = AptChannelState.DISABLE
        req_params = AptMessageId.MOD_REQ_CHANENABLESTATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOD_GET_CHANENABLESTATE
        expected_read = struct.pack(self._pack, get_params.value)
        # The request+data has to be 6 bytes long and should include return values at the right spots.
        self._transport_mock.read.return_value = (
            expected_read[:-1] + struct.pack("<b", expected_state.value) + b"81"
        )
        # Act
        state = self._instr.get_channel_state(channel)

        # Assert
        self.assertEqual(expected_state, state)
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_channel_state_for_enabled_channel_1_sends_command_and_returns_enabled_value(
        self,
    ):
        """Test get state of enabled channel 1, sends command to get state."""
        # Arrange
        channel = 1
        expected_state = AptChannelState.ENABLE
        req_params = AptMessageId.MOD_REQ_CHANENABLESTATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOD_GET_CHANENABLESTATE
        expected_read = struct.pack(self._pack, get_params.value)
        self._transport_mock.read.return_value = (
            expected_read[:-1] + struct.pack("<b", expected_state.value) + b"81"
        )
        # Act
        state = self._instr.get_channel_state(channel)

        # Assert
        self.assertEqual(expected_state, state)
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_channel_state_for_disabled_channel_2_sends_command_and_returns_disabled_value(
        self,
    ):
        """Test get state of disabled channel 2, sends command to get state.
        This test checks that if anything but 0x01 is received then the channel is disabled."""
        # Arrange
        channel = 2
        expected_state = AptChannelState.DISABLE
        req_params = AptMessageId.MOD_REQ_CHANENABLESTATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOD_GET_CHANENABLESTATE
        expected_read = struct.pack(self._pack, get_params.value)
        self._transport_mock.read.return_value = (
            expected_read[:-1] + struct.pack("<b", expected_state.value) + b"81"
        )
        # Act
        state = self._instr.get_channel_state(channel)

        # Assert
        self.assertEqual(expected_state, state)
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_channel_state_for_enabled_channel_3_sends_command_and_returns_enabled_value(
        self,
    ):
        """Test get state of enabled channel 3, sends command to get state."""
        # Arrange
        channel = 3
        channel_3_hex = 0x04
        expected_state = AptChannelState.ENABLE
        req_params = AptMessageId.MOD_REQ_CHANENABLESTATE
        expected_write = struct.pack(self._pack, (channel_3_hex << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOD_GET_CHANENABLESTATE
        expected_read = struct.pack(self._pack, get_params.value)
        self._transport_mock.read.return_value = (
            expected_read[:-1] + struct.pack("<b", expected_state.value) + b"81"
        )
        # Act
        state = self._instr.get_channel_state(channel)

        # Assert
        self.assertEqual(state, AptChannelState.ENABLE)
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_start_auto_status_update_sends_command(self):
        """Test start automatic status updates, sends command"""
        # Arrange
        cmd_param = AptMessageId.HW_START_UPDATEMSGS
        expected_write = struct.pack(self._pack, cmd_param.value) + b"P\x01"
        # Act
        self._instr.start_auto_status_update()

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_stop_auto_status_update_sends_command(self):
        """Test stop automatic status updates, sends command"""
        # Arrange
        cmd_param = AptMessageId.HW_STOP_UPDATEMSGS
        expected_write = struct.pack(self._pack, cmd_param.value) + b"P\x01"

        # Act
        self._instr.stop_auto_status_update()

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_home_channel_3_sends_command(self):
        """Test home channel 3, sends command"""
        # Arrange
        channel = 3
        channel_3_hex = 0x04
        set_params = AptMessageId.MOT_MOVE_HOME
        expected_write = struct.pack(self._pack, (channel_3_hex << 16) + set_params.value) + b"P\x01"

        # Act
        self._instr.home_channel(channel)

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_is_channel_1_homed_when_channel_homed_sends_command_returns_status(self):
        """Test is_channel_homed for channel 1 when channel is homed, send command and return homed value."""
        # Arrange
        # first 2 binary strings are responses from the status update command
        channel = 1
        expected_position = 10000
        expected_velocity = 7
        expected_motor_current = -1
        status_bits = 0
        req_params = AptMessageId.MOT_REQ_USTATUSUPDATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOT_GET_USTATUSUPDATE
        self._transport_mock.read.return_value = (
            struct.pack(self._pack, get_params.value) +
            struct.pack("<h", 0) +
            struct.pack("<h", channel) +
            struct.pack("<L", expected_position) +
            struct.pack("<h", expected_velocity) +
            struct.pack("<h", expected_motor_current) +
            struct.pack("<L", status_bits)  # Status bits, we don't check those
        )
        # Act
        state = self._instr.is_channel_homed(channel)

        # Assert
        self.assertTrue(state)
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(2, self._transport_mock.read.call_count)

    def test_is_channel_2_homed_with_read_timing_out_sends_command_returns_status(self):
        """Test is_channel_homed for channel 1 when read times out, send command and returns not homed."""
        # Arrange
        # first 2 binary strings are responses from the status update command
        channel = 2
        expected_position = 10000
        expected_velocity = 7
        expected_motor_current = 15
        status_bits = 0
        req_params = AptMessageId.MOT_REQ_USTATUSUPDATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOT_GET_USTATUSUPDATE
        # last string is the homed response
        self._transport_mock.read.side_effect = [
            struct.pack(self._pack, get_params.value) +
            struct.pack("<h", 0) +
            struct.pack("<h", channel) +
            struct.pack("<L", expected_position) +
            struct.pack("<h", expected_velocity) +
            struct.pack("<h", expected_motor_current) +
            struct.pack("<L", status_bits),  # Status bits, we don't check those
            QMI_TimeoutException
        ]
        # Act
        state = self._instr.is_channel_homed(channel)

        # Assert
        self.assertFalse(state)
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(2, self._transport_mock.read.call_count)

    def test_move_absolute_sends_move_command(self):
        """Test move channel 3, sends move command."""
        # Arrange
        channel = 3
        channel_3_hex = 0x04
        expected_position = 10
        cmd_params = AptMessageId.MOT_MOVE_ABSOLUTE
        expected_write = (
            struct.pack(self._pack, 0x60000 + cmd_params.value) +
            self.dest.to_bytes(1, byteorder="little") +
            self.source.to_bytes(1, byteorder="little") +
            struct.pack("<h", channel_3_hex) +
            struct.pack("<L", int(round(expected_position / Thorlabs_Mpc320.ENCODER_CONVERSION_UNIT)))
        )

        # Act
        self._instr.move_absolute(channel, expected_position)

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_move_absolute_outside_range_throws_error(self):
        """Test move channel 1 outside valid range, throws error."""
        # Arrange
        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.move_absolute(1, 20000)

    def test_is_channel_1_move_completed_when_channel_move_completed_sends_command_returns_status(
        self,
    ):
        """Test is_move_completed for channel 1 when channel is moved, send command and return move completed value."""
        # Arrange
        # first 2 binary strings are responses from the status update command
        # last string is the homed response
        channel = 1
        expected_position = 10000
        expected_velocity = 7
        expected_motor_current = 15
        status_bits = 0
        req_params = AptMessageId.MOT_REQ_USTATUSUPDATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOT_GET_USTATUSUPDATE
        self._transport_mock.read.return_value = (
            struct.pack(self._pack, get_params.value) +
            struct.pack("<h", 0) +
            struct.pack("<h", channel) +
            struct.pack("<L", expected_position) +
            struct.pack("<h", expected_velocity) +
            struct.pack("<h", expected_motor_current) +
            struct.pack("<L", status_bits)  # Status bits, we don't check those
        )
        # Act
        state = self._instr.is_move_completed(channel)

        # Assert
        self.assertTrue(state)
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(2, self._transport_mock.read.call_count)

    def test_is_channel_1_move_completed_with_read_timing_out(self):
        """Test is_move_completed for channel 1 after read times out, sends command and returns move not completed.
        For the second request the move is finished.
        """
        # Arrange
        channel = 1
        expected_position = 10000
        expected_velocity = 7
        expected_motor_current = 15
        status_bits = 0
        req_params = AptMessageId.MOT_REQ_USTATUSUPDATE
        expected_write = struct.pack(self._pack, (channel << 16) + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOT_GET_USTATUSUPDATE
        expected_read = struct.pack(self._pack, get_params.value)
        self._transport_mock.read.side_effect = [
            expected_read +\
            struct.pack("<h", 0) +\
            struct.pack("<h", channel) +\
            struct.pack("<L", expected_position ) +\
            struct.pack("<h", expected_velocity) +\
            struct.pack("<h", expected_motor_current) +\
            struct.pack("<L", status_bits),
            QMI_TimeoutException,
            expected_read + \
            struct.pack("<h", 0) + \
            struct.pack("<h", channel) + \
            struct.pack("<L", expected_position) + \
            struct.pack("<h", 0) + \
            struct.pack("<h", 0) + \
            struct.pack("<L", status_bits),
        ]

        # Act
        state0 = self._instr.is_move_completed(channel)
        state1 = self._instr.is_move_completed(channel)

        # Assert
        self.assertFalse(state0)
        self.assertTrue(state1)
        self._transport_mock.write.assert_has_calls([
            unittest.mock.call(expected_write),
            unittest.mock.call(expected_write)
        ])
        self.assertEqual(3, self._transport_mock.read.call_count)

    def test_save_parameter_settings_for_given_command_sends_command(self):
        """Test save_parameter_settings for channel 1 for a specific command, send command."""
        # Arrange
        channel = 1
        req_params = AptMessageId.MOT_SET_EEPROMPARAMS
        parameters_set = 0x04b6
        expected_write = (
                struct.pack(self._pack, 0x40000 + req_params.value) +
                self.dest.to_bytes(1, byteorder="little") +
                self.source.to_bytes(1, byteorder="little") +
                channel.to_bytes(2, byteorder="little") +
                parameters_set.to_bytes(2, byteorder="little")
        )
        # Act
        self._instr.save_parameter_settings(channel, parameters_set)

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_status_updated_of_channel_1_sends_command_returns_status(
        self,
    ):
        """Test get_status_update for channel 1, send command and return status."""
        # Arrange
        expected_channel = 1
        expected_position = 10000
        expected_velocity = 7
        expected_motor_current = -1
        status_bits = 0
        req_params = AptMessageId.MOT_REQ_USTATUSUPDATE
        expected_write = struct.pack(self._pack, 0x10000 + req_params.value) + b"P\x01"
        get_params = AptMessageId.MOT_GET_USTATUSUPDATE
        # The request+data has to be 6 bytes long and should include return values at the right spots.
        self._transport_mock.read.return_value = \
            struct.pack(self._pack, get_params.value) +\
            struct.pack("<h", 0) +\
            struct.pack("<h", expected_channel) +\
            struct.pack("<L", expected_position) +\
            struct.pack("<h", expected_velocity) +\
            struct.pack("<h", expected_motor_current) +\
            struct.pack("<L", status_bits)  # Status bits, we don't check those

        # Act
        status = self._instr.get_status_update(expected_channel)

        # Assert
        self.assertEqual(expected_channel, status.channel)
        self.assertEqual(expected_position, status.position * self.position_conversion)
        self.assertEqual(expected_velocity, status.velocity)
        self.assertEqual(expected_motor_current, status.motor_current)
        self._transport_mock.write.assert_called_once_with(expected_write)
        self._transport_mock.read.assert_called_once()

    def test_jog_forward_sends_command(self):
        """Test jog forward for channel 1, sends command."""
        # Arrange
        channel = 1
        direction = AptChannelJogDirection.FORWARD
        cmd_params = AptMessageId.MOT_MOVE_JOG
        expected_write = (
            struct.pack(self._pack, (channel << 16) + (direction.value << 24) + cmd_params.value) + b"P\x01"
        )

        # Act
        self._instr.jog(channel, direction)

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_jog_backward_sends_command(self):
        """Test jog backward for channel 1, sends command."""
        # Arrange
        channel = 2
        direction = AptChannelJogDirection.BACKWARD
        cmd_params = AptMessageId.MOT_MOVE_JOG
        expected_write = (
            struct.pack(self._pack, (channel << 16) + (direction.value << 24) + cmd_params.value) + b"P\x01"
        )
        # Act
        self._instr.jog(channel, direction)

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_polarisation_parameters_sends_command(self):
        """Test set_polarisation_parameters, sends command."""
        # Arrange
        not_used = 0
        vel = 50
        home_pos = 85
        jog_step_1 = 0
        jog_step_2 = 17
        jog_step_3 = 34
        converted_home_pos = int(round(home_pos / Thorlabs_Mpc320.ENCODER_CONVERSION_UNIT))
        converted_js1 = int(round(jog_step_1 / Thorlabs_Mpc320.ENCODER_CONVERSION_UNIT))
        converted_js2 = int(round(jog_step_2 / Thorlabs_Mpc320.ENCODER_CONVERSION_UNIT))
        converted_js3 = int(round(jog_step_3 / Thorlabs_Mpc320.ENCODER_CONVERSION_UNIT))
        set_params = AptMessageId.POL_SET_PARAMS
        expected_write = struct.pack(self._pack, 0xC0000 + set_params.value)
        # The request+data has to be 18 bytes long and should include return values at the right spots.
        expected_write = expected_write + \
            self.dest.to_bytes(1, byteorder="little") +\
            self.source.to_bytes(1, byteorder="little") +\
            struct.pack("<h", not_used) +\
            struct.pack("<h", vel) + \
            struct.pack("<h", converted_home_pos) +\
            struct.pack("<h", converted_js1) +\
            struct.pack("<h", converted_js2) +\
            struct.pack("<h", converted_js3)

        # Act
        self._instr.set_polarisation_parameters(
            vel,
            home_pos,
            jog_step_1,
            jog_step_2,
            jog_step_3,
        )

        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_polarisation_parameters_with_invalid_velocity_throws_error(self):
        """Test set_polarisation_parameters with invalid velocity, throws error."""
        # Arrange
        vel = 120
        home_pos = 85
        jog_step1 = 0
        jog_step2 = 17
        jog_step3 = 34

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.set_polarisation_parameters(
                vel,
                home_pos,
                jog_step1,
                jog_step2,
                jog_step3,
            )

    def test_set_polarisation_parameters_with_invalid_home_position_throws_error(self):
        """Test set_polarisation_parameters with invalid home position, throws error."""
        # Arrange
        vel = 50
        home_pos = 200
        jog_step1 = 0
        jog_step2 = 17
        jog_step3 = 34

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.set_polarisation_parameters(
                vel,
                home_pos,
                jog_step1,
                jog_step2,
                jog_step3,
            )

    def test_set_polarisation_parameters_with_invalid_jog_step_1_throws_error(self):
        """Test set_polarisation_parameters with invalid jog step 1, throws error."""
        # Arrange
        vel = 50
        home_pos = 85
        jog_step1 = 300
        jog_step2 = 17
        jog_step3 = 34

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.set_polarisation_parameters(
                vel,
                home_pos,
                jog_step1,
                jog_step2,
                jog_step3,
            )

    def test_set_polarisation_parameters_with_invalid_jog_step_2_throws_error(self):
        """Test set_polarisation_parameters with invalid jog step 2, throws error."""
        # Arrange
        vel = 50
        home_pos = 85
        jog_step1 = 0
        jog_step2 = 240
        jog_step3 = 34

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.set_polarisation_parameters(
                vel,
                home_pos,
                jog_step1,
                jog_step2,
                jog_step3,
            )

    def test_set_polarisation_parameters_with_invalid_jog_step_3_throws_error(self):
        """Test set_polarisation_parameters with invalid jog step 3, throws error."""
        # Arrange
        vel = 50
        home_pos = 85
        jog_step1 = 0
        jog_step2 = 17
        jog_step3 = 310

        # Act
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            self._instr.set_polarisation_parameters(
                vel,
                home_pos,
                jog_step1,
                jog_step2,
                jog_step3,
            )

    def test_get_polarisation_parameters_sends_command_returns_parameters(
        self,
    ):
        """Test get_polarisation_parameters, sends command and returns parameters."""
        # Arrange
        not_used = 0
        expected_velocity = 50
        expected_home_position = 85
        expected_jog_step_1 = 0
        expected_jog_step_2 = 17
        expected_jog_step_3 = 34
        req_params = AptMessageId.POL_REQ_PARAMS
        expected_write = struct.pack(self._pack, req_params.value) + b"P\x01"
        get_params = AptMessageId.POL_GET_PARAMS
        # The request+data has to be 18 bytes long and should include return values at the right spots.
        self._transport_mock.read.return_value = \
            struct.pack(self._pack, get_params.value) + \
            struct.pack("<h", 0) +\
            struct.pack("<h", not_used) +\
            struct.pack("<h", expected_velocity) +\
            struct.pack("<h", expected_home_position) +\
            struct.pack("<h", expected_jog_step_1) +\
            struct.pack("<h", expected_jog_step_2) +\
            struct.pack("<h", expected_jog_step_3)

        # Act
        params = self._instr.get_polarisation_parameters()

        # Assert
        self.assertEqual(expected_velocity, params.velocity)
        self.assertEqual(expected_home_position, params.home_position * self.position_conversion)
        self.assertEqual(expected_jog_step_1, params.jog_step1 * self.position_conversion)
        self.assertEqual(expected_jog_step_2, params.jog_step2 * self.position_conversion)
        self.assertEqual(expected_jog_step_3, params.jog_step3 * self.position_conversion)
        self._transport_mock.write.assert_called_once_with(expected_write)
        self._transport_mock.read.assert_called_once()


if __name__ == "__main__":
    unittest.main()
