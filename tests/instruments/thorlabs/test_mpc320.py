import random
import unittest
import unittest.mock
import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs import Thorlabs_Mpc320
from qmi.instruments.thorlabs.apt_protocol import AptChannelState


class TestThorlabsMPC320(unittest.TestCase):
    def setUp(self):
        # Patch QMI context and make instrument
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        qmi.start(self._ctx_qmi_id)
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        with unittest.mock.patch(
            "qmi.instruments.thorlabs.mpc320.create_transport",
            return_value=self._transport_mock,
        ):
            self._instr: Thorlabs_Mpc320 = qmi.make_instrument(
                "test_mpc320", Thorlabs_Mpc320, "serial:transport_str"
            )
        self._instr.open()

    def tearDown(self):
        self._instr.close()
        qmi.stop()

    def test_get_idn_sends_command_and_returns_identification_info(self):
        """Test get_idn method and returns identification info."""
        # Arrange
        expected_idn = ["Thorlabs", b"MPC320 ", 94000009, 3735810]
        # \x89\x53\x9a\x05 is 94000009
        # \x4d\x50\x43\x33\x32\x30\x0a is MPC320
        # x2c\x00 is Brushless DC controller card
        # \x02\x01\x39\x00 is 3735810
        self._transport_mock.read.side_effect = [
            b"\x06\x00\x54\x00\x00\x81",
            b"\x89\x53\x9a\x05\x4d\x50\x43\x33\x32\x30\x20\x00\x2c\x00\x02\x01\x39\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
        ]

        # Act
        idn = self._instr.get_idn()

        # Assert
        self.assertEqual(idn.vendor, expected_idn[0])
        self.assertEqual(idn.model, expected_idn[1])
        self.assertEqual(idn.serial, expected_idn[2])
        self.assertEqual(idn.version, expected_idn[3])

        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x05\x00\x00\x00P\x01")
        )
        self._transport_mock.read.assert_has_calls(
            [
                unittest.mock.call(nbytes=6, timeout=1.0),
                unittest.mock.call(nbytes=84, timeout=1.0),
            ]
        )

    def test_identify_sends_command(self):
        """Test identify method and send relevant command."""
        # Arrange

        # Act
        self._instr.identify()

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x23\x02\x01\x00\x50\x01")
        )

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

        # Act
        self._instr.enable_channels([1])

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x10\x02\x01\x01\x50\x01")
        )

    def test_enable_channels_enable_one_and_three_sends_command(self):
        """Test enable channels 1 and 3, sends command to enable channels 1 and 3."""
        # Arrange

        # Act
        self._instr.enable_channels([1, 3])

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x10\x02\x05\x01\x50\x01")
        )

    def test_disable_all_channels_sends_command(self):
        """Test disable all channels, sends command to disable all channels."""
        # Arrange

        # Act
        self._instr.disable_all_channels()

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x10\x02\x00\x01\x50\x01")
        )

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
        self._transport_mock.read.return_value = b"\x12\x02\x01\x00\x00\x81"

        # Act
        state = self._instr.get_channel_state(1)

        # Assert
        self.assertEqual(state, AptChannelState.DISABLE)
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x11\x02\x01\x00\x50\x01")
        )

    def test_get_channel_state_for_enabled_channel_1_sends_command_and_returns_enabled_value(
        self,
    ):
        """Test get state of enabled channel 1, sends command to get state."""
        # Arrange
        self._transport_mock.read.return_value = b"\x12\x02\x01\x01\x00\x81"

        # Act
        state = self._instr.get_channel_state(1)

        # Assert
        self.assertEqual(state, AptChannelState.ENABLE)
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x11\x02\x01\x00\x50\x01")
        )

    def test_get_channel_state_for_disabled_channel_2_sends_command_and_returns_disabled_value(
        self,
    ):
        """Test get state of disabled channel 2, sends command to get state.
        This test checks that if anything but 0x01 is received then the channel is disabled."""
        # Arrange
        self._transport_mock.read.return_value = b"\x12\x02\x01\x03\x00\x81"

        # Act
        state = self._instr.get_channel_state(1)

        # Assert
        self.assertEqual(state, AptChannelState.DISABLE)
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x11\x02\x01\x00\x50\x01")
        )

    def test_start_auto_status_update_sends_command(self):
        """Test start automatic status updates, sends command"""
        # Arrange

        # Act
        self._instr.start_auto_status_update()

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x11\x00\x00\x00\x50\x01")
        )

    def test_stop_auto_status_update_sends_command(self):
        """Test stop automatic status updates, sends command"""
        # Arrange

        # Act
        self._instr.stop_auto_status_update()

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x12\x00\x00\x00\x50\x01")
        )

    def test_home_channel_3_sends_command(self):
        """Test home channel 3, sends command"""
        # Arrange

        # Act
        self._instr.home_channel(3)

        # Assert
        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x43\x04\x04\x00\x50\x01")
        )

    def test_is_channel_1_homed_when_channel_homed_sends_command_returns_status(self):
        """Test is_channel_homed for channel 1 when channel is homed, send command and return homed value."""
        # Arrange
        # first 2 binary strings are responses from the status update command
        # last string is the homed response
        self._transport_mock.read.side_effect = [
            b"\x91\x04\x0e\x00\x00\x81",
            b"\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            b"\x44\x04\x01\x00\x00\x81",
        ]

        # Act
        state = self._instr.is_channel_homed(1)

        # Assert
        self.assertTrue(state)
        self._transport_mock.write.assert_not_called()
        self._transport_mock.read.assert_has_calls(
            [
                unittest.mock.call(nbytes=6, timeout=1.0),
                unittest.mock.call(nbytes=14, timeout=1.0),
                unittest.mock.call(nbytes=6, timeout=1.0),
            ]
        )


if __name__ == "__main__":
    unittest.main()
