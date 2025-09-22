import unittest
from unittest.mock import patch, MagicMock

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_Vxi11Transport
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.instruments.yokogawa import Yokogawa_Dlm4038

from tests.patcher import PatcherQmiContext as QMI_Context


class TestInstrumentInitCase(unittest.TestCase):

    @patch("qmi.core.transport.vxi11")
    def test_open_close(self, vxi11_patch):
        """Test that the class initializes and open and close functions work as expected."""
        # Arrange
        expected_path = "O:/"
        yokogawa = Yokogawa_Dlm4038(QMI_Context("yoko"), "gawa", "vxi11:123.45.67.89")
        # Act
        yokogawa.open()
        # Assert
        self.assertTrue(yokogawa.is_open())
        yokogawa.close()
        self.assertFalse(yokogawa.is_open())
        self.assertEqual(expected_path, yokogawa._directory_oscilloscope)

    @patch("qmi.core.transport.vxi11")
    def test_open_close_with_custom_path(self, vxi11_patch):
        """Test that the initialization with custom path gives the expected path."""
        # Arrange
        expected_path = "P:/other_path/than_default"
        # Act
        yokogawa = Yokogawa_Dlm4038(QMI_Context("yoko"), "gawa", "vxi11:123.45.67.89", expected_path)
        # Assert
        self.assertEqual(expected_path, yokogawa._directory_oscilloscope)

    def test_open_close_calls(self):
        """Test that the open and close functions include calls as expected."""
        # Arrange
        self._transport_mock = MagicMock(spec=QMI_Vxi11Transport)
        with patch(
                'qmi.instruments.yokogawa.dlm4038.create_transport',
                return_value=self._transport_mock):

            # Act
            self.yokogawa = Yokogawa_Dlm4038(QMI_Context("yoko"), "gawa", "vxi11:123.45.67.89")
            self.yokogawa.open()
            # Assert
            self._transport_mock.open.assert_called_once_with()
            self._transport_mock.open.reset_mock()
            self._transport_mock.write.reset_mock()
            self.yokogawa.close()
            self._transport_mock.close.assert_called_once_with()


class TestMethodsCase(unittest.TestCase):

    def setUp(self):
        self._transport_mock = MagicMock(spec=QMI_Vxi11Transport)
        self.def_path = "O:/"
        with patch(
                'qmi.instruments.yokogawa.dlm4038.create_transport',
                return_value=self._transport_mock):
            self.yokogawa = Yokogawa_Dlm4038(QMI_Context("yoko"), "gawa", "vxi11:123.45.67.89")
            self.yokogawa.open()

    def tearDown(self):
        self.yokogawa.close()

    def test_get_idn(self):
        """Test get_idn function."""
        # Arrange
        expected_write = b"*IDN?\n"
        expected_vendor = "Yokogawa"
        expected_model = "dlm4308"
        expected_serial = "S123456"
        expected_version = "1.23.4"
        expected_idn = QMI_InstrumentIdentification(
            expected_vendor, expected_model, expected_serial, expected_version
        )
        side_effect = ",".join([expected_vendor, expected_model, expected_serial, expected_version + "\n"])
        self._transport_mock.read_until.side_effect = [side_effect.encode()]
        # Act
        idn = self.yokogawa.get_idn()
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(expected_idn, idn)

    def test_get_idn_exception(self):
        """Test get_idn function excepts when too few or too many words are returned."""
        # Arrange
        expected_response = "Unexpected response to *IDN?, got {resp!r}"
        expected_write = b"*IDN?\n"
        side_effect = ["too,few,words\n".encode(), "too,many,words,than,expected\n".encode()]
        self._transport_mock.read_until.side_effect = side_effect
        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.yokogawa.get_idn()
            # Assert
            self._transport_mock.write.assert_called_once_with(expected_write)
            self.assertEqual(expected_response.format(side_effect[0].decode()), str(exc.exception))

        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.yokogawa.get_idn()
            # Assert
            self._transport_mock.write.assert_called_once_with(expected_write)
            self.assertEqual(expected_response.format(side_effect[1].decode()), str(exc.exception))

    def test_start(self):
        """Test start fun."""
        # Arrange
        expected_write = b":START\n"
        # Act
        self.yokogawa.start()
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_stop(self):
        """Test stop fun."""
        # Arrange
        expected_write = b":STOP\n"
        # Act
        self.yokogawa.stop()
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_time_division(self):
        """Test set_time_division method."""
        # Arrange
        time_div = 1E6
        expected_write = f":TIMEBASE:TDIV {time_div:.1f}\n".encode()
        # Act
        self.yokogawa.set_time_division(time_div)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_time_division(self):
        """Test get_time_division method."""
        # Arrange
        expected_time_div = 1E6
        expected_write = b":TIMEBASE:TDIV?\n"
        return_value = b"TIME:TDIV" + f"{expected_time_div:.1f}\n".encode()
        self._transport_mock.read_until.return_value = return_value
        # Act
        time_div = self.yokogawa.get_time_division()
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(expected_time_div, time_div)

    def test_set_high_resolution_on(self):
        """Test set_high_resolution method with "on"."""
        # Arrange
        high_res = True
        expected_write = f":ACQUIRE:RESOLUTION ON\n".encode()
        # Act
        self.yokogawa.set_high_resolution(high_res)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_high_resolution_off(self):
        """Test set_high_resolution method with "off"."""
        # Arrange
        high_res = False
        expected_write = f":ACQUIRE:RESOLUTION OFF\n".encode()
        # Act
        self.yokogawa.set_high_resolution(high_res)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_turn_channel_on(self):
        """Test turn_channel_on method with one channel."""
        # Arrange
        channel = 1
        state = "ON"
        expected_write = f":CHANnel{channel}:DISPlay {state}\n".encode()
        # Act
        self.yokogawa.turn_channel_on(channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_turn_channels_on_some(self):
        """Test turn_channel_on method with some channel."""
        # Arrange
        channels = [1, 3, 5, 7]
        state = "ON"
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:DISPlay {state}\n".encode()))

        # Act
        self.yokogawa.turn_channel_on(channels)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_turn_channels_on_all(self):
        """Test turn_channel_on method with all channels."""
        # Arrange
        channels = list(range(1, 9))
        state = "ON"
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:DISPlay {state}\n".encode()))

        # Act
        self.yokogawa.turn_channel_on("all")
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_turn_channel_off(self):
        """Test turn_channel_off method with one channel."""
        # Arrange
        channel = 1
        state = "OFF"
        expected_write = f":CHANnel{channel}:DISPlay {state}\n".encode()
        # Act
        self.yokogawa.turn_channel_off(channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_turn_channels_off_some(self):
        """Test turn_channel_off method with some channel."""
        # Arrange
        channels = [1, 3, 5, 7]
        state = "OFF"
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:DISPlay {state}\n".encode()))

        # Act
        self.yokogawa.turn_channel_off(channels)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_turn_channels_off_all(self):
        """Test turn_channel_off method with all channels."""
        # Arrange
        channels = list(range(1, 9))
        state = "OFF"
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:DISPlay {state}\n".encode()))

        # Act
        self.yokogawa.turn_channel_off("all")
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_set_voltage_offset(self):
        """Test set_voltage_offset method on one channel."""
        # Arrange
        channel = 2
        offset = 16.0
        expected_write = f":CHANnel{channel}:OFFset {offset:.1f}V\n".encode()
        # Act
        self.yokogawa.set_voltage_offset(channel, offset)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_voltage_offset_some(self):
        """Test set_voltage_offset method on multiple channels."""
        # Arrange
        channels = [2, 4, 6, 8]
        offset = 16.0
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:OFFset {offset:.1f}V\n".encode()))

        # Act
        self.yokogawa.set_voltage_offset(channels, offset)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_set_voltage_offset_all(self):
        """Test set_voltage_offset method on all channels."""
        # Arrange
        channels = list(range(1, 9))
        offset = 16.0
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:OFFset {offset:.1f}V\n".encode()))

        # Act
        self.yokogawa.set_voltage_offset("all", offset)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_get_voltage_offset(self):
        """Test get_voltage_offset method for one channel."""
        # Arrange
        channel = 3
        expected_offset = 16.0
        expected_write = f":CHANnel{channel}:OFFset?\n".encode()
        return_value = b"CHANnel:OFF" + f"{expected_offset:.1f}\n".encode()
        self._transport_mock.read_until.return_value = return_value
        # Act
        offset = self.yokogawa.get_voltage_offset(channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(expected_offset, offset)

    def test_get_voltage_offset_some(self):
        """Test get_voltage_offset method for multiple channels."""
        # Arrange
        channels = [1, 3, 5, 7]
        expected_offset = 16.0
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:OFFset?\n".encode()))
            side_effect.append(b"CHANnel:OFF" + f"{expected_offset:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        offsets = self.yokogawa.get_voltage_offset(channels)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(expected_offset, offsets[o])

    def test_get_voltage_offset_all(self):
        """Test get_voltage_offset method for all channels."""
        # Arrange
        channels = list(range(1, 9))
        expected_offset = 16.0
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:OFFset?\n".encode()))
            side_effect.append(b"CHANnel:OFF" + f"{expected_offset:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        offsets = self.yokogawa.get_voltage_offset("all")
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(expected_offset, offsets[o])

    def test_set_voltage_division(self):
        """Test set_voltage_division method on one channel."""
        # Arrange
        channel = 2
        division = 16.0
        expected_write = f":CHANnel{channel}:VDIV {division:.1f}V\n".encode()
        # Act
        self.yokogawa.set_voltage_division(channel, division)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_voltage_division_some(self):
        """Test set_voltage_division method on multiple channels."""
        # Arrange
        channels = [2, 4, 6, 8]
        division = 16.0
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:VDIV {division:.1f}V\n".encode()))

        # Act
        self.yokogawa.set_voltage_division(channels, division)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_set_voltage_division_all(self):
        """Test set_voltage_division method on all channels."""
        # Arrange
        channels = list(range(1, 9))
        division = 16.0
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:VDIV {division:.1f}V\n".encode()))

        # Act
        self.yokogawa.set_voltage_division("all", division)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_get_voltage_division(self):
        """Test get_voltage_division method for one channel."""
        # Arrange
        channel = 4
        expected_division = 1.6
        expected_write = f":CHANnel{channel}:VDIV?\n".encode()
        return_value = b"CHANnel:VDIV" + f"{expected_division:.1f}\n".encode()
        self._transport_mock.read_until.return_value = return_value
        # Act
        division = self.yokogawa.get_voltage_division(channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(expected_division, division)

    def test_get_voltage_division_some(self):
        """Test get_voltage_division method for multiple channels."""
        # Arrange
        channels = [2, 4, 6, 8]
        expected_division = 1.6
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:VDIV?\n".encode()))
            side_effect.append(b"CHANnel:VDIV" + f"{expected_division:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        divisions = self.yokogawa.get_voltage_division(channels)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(expected_division, divisions[o])

    def test_get_voltage_division_all(self):
        """Test get_voltage_division method for all channels."""
        # Arrange
        channels = list(range(1, 9))
        expected_division = 1.6
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:VDIV?\n".encode()))
            side_effect.append(b"CHANnel:VDIV" + f"{expected_division:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        divisions = self.yokogawa.get_voltage_division("all")
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(expected_division, divisions[o])

    def test_get_max_waveform(self):
        """Test get_max_waveform method for one channel."""
        # Arrange
        channel = 5
        expected_max_waveform = 0.16
        expected_write = f":MEASure:CHANnel{channel}:MAXimum:VALUE?\n".encode()
        return_value = b"CHANnel:MAXimum:VAL" + f"{expected_max_waveform:.1f}\n".encode()
        self._transport_mock.read_until.return_value = return_value
        # Act
        max_waveform = self.yokogawa.get_max_waveform(channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(round(expected_max_waveform, 1), max_waveform)

    def test_get_max_waveform_some(self):
        """Test get_max_waveform method for multiple channels."""
        # Arrange
        channels = [1, 3, 5, 7]
        expected_max_waveform = 0.16
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":MEASure:CHANnel{channel}:MAXimum:VALUE?\n".encode()))
            side_effect.append(b"CHANnel:MAXimum:VAL" + f"{expected_max_waveform:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        max_waveforms = self.yokogawa.get_max_waveform(channels)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(round(expected_max_waveform, 1), max_waveforms[o])

    def test_get_max_waveform_all(self):
        """Test get_max_waveform method for all channels."""
        # Arrange
        channels = list(range(1, 9))
        expected_max_waveform = 0.16
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":MEASure:CHANnel{channel}:MAXimum:VALUE?\n".encode()))
            side_effect.append(b"CHANnel:MAXimum:VAL" + f"{expected_max_waveform:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        max_waveforms = self.yokogawa.get_max_waveform("all")
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(round(expected_max_waveform, 1), max_waveforms[o])

    def test_set_channel_position(self):
        """Test set_channel_position method on one channel."""
        # Arrange
        channel = 2
        offset = 16.0
        expected_write = f":CHANnel{channel}:POSition {offset:.1f}\n".encode()
        # Act
        self.yokogawa.set_channel_position(channel, offset)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_channel_position_some(self):
        """Test set_channel_position method on multiple channels."""
        # Arrange
        channels = [2, 4, 6, 8]
        offset = 16.0
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:POSition {offset:.1f}\n".encode()))

        # Act
        self.yokogawa.set_channel_position(channels, offset)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_set_channel_position_all(self):
        """Test set_channel_position method on all channels."""
        # Arrange
        channels = list(range(1, 9))
        offset = 16.0
        expected_writes = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:POSition {offset:.1f}\n".encode()))

        # Act
        self.yokogawa.set_channel_position("all", offset)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_get_channel_position(self):
        """Test get_channel_position method for one channel."""
        # Arrange
        channel = 3
        expected_offset = 16.0
        expected_write = f":CHANnel{channel}:POSition?\n".encode()
        return_value = b"CHANnel:POS" + f"{expected_offset:.1f}\n".encode()
        self._transport_mock.read_until.return_value = return_value
        # Act
        offset = self.yokogawa.get_channel_position(channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(expected_offset, offset)

    def test_get_channel_position_some(self):
        """Test get_channel_position method for multiple channels."""
        # Arrange
        channels = [1, 3, 5, 7]
        expected_offset = 16.0
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:POSition?\n".encode()))
            side_effect.append(b"CHANnel:POS" + f"{expected_offset:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        offsets = self.yokogawa.get_channel_position(channels)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(expected_offset, offsets[o])

    def test_get_channel_position_all(self):
        """Test get_channel_position method for all channels."""
        # Arrange
        channels = list(range(1, 9))
        expected_offset = 16.0
        expected_writes = []
        side_effect = []
        for channel in channels:
            expected_writes.append(unittest.mock.call(f":CHANnel{channel}:POSition?\n".encode()))
            side_effect.append(b"CHANnel:POS" + f"{expected_offset:.1f}\n".encode())

        self._transport_mock.read_until.side_effect = side_effect
        # Act
        offsets = self.yokogawa.get_channel_position("all")
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)
        for o in range(len(channels)):
            self.assertEqual(expected_offset, offsets[o])

    def test_set_trigger_channel(self):
        """Test set_trigger_channel method."""
        # Arrange
        trigger_channel = 5
        expected_write = f":TRIGger:ATRigger:SIMPle:SOURce {trigger_channel}\n".encode()
        # Act
        self.yokogawa.set_trigger_channel(trigger_channel)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_trigger_level(self):
        """Test set_trigger_level method."""
        # Arrange
        trigger_level = 5.0
        expected_write = f":TRIGger:ATRigger:SIMPle:LEVel {trigger_level:.1f}V\n".encode()
        # Act
        self.yokogawa.set_trigger_level(trigger_level)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_set_number_data_points(self):
        """Test set_number_data_points method."""
        # Arrange
        ndp = 10500
        expected_write = f":ACQuire:RLENgth {ndp}\n".encode()
        # Act
        self.yokogawa.set_number_data_points(ndp)
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_get_number_data_points(self):
        """Test get_number_data_points method."""
        # Arrange
        expected_ndp = int(1.5E6)
        expected_write = b":WAVeform:LENGth?\n"
        return_value = b"WAVE:LENG:" + f"{expected_ndp}\n".encode()
        self._transport_mock.read_until.return_value = return_value
        # Act
        ndp = self.yokogawa.get_number_data_points()
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)
        self.assertEqual(expected_ndp, ndp)

    def test_set_average(self):
        """Test set_average method that first sets the mode to average, and then the average value."""
        # Arrange
        average = 2**5
        expected_write = [
            unittest.mock.call(f":ACQUIRE:MODE AVERAGE\n".encode()),
            unittest.mock.call(f":ACQUIRE:AVERAGE:COUNT {average}\n".encode())
        ]
        # Act
        self.yokogawa.set_average(average)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_write)

    def test_set_normal(self):
        """Test set_normal method."""
        # Arrange
        expected_write = f":ACQUIRE:MODE NORMAL\n".encode()
        # Act
        self.yokogawa.set_normal()
        # Assert
        self._transport_mock.write.assert_called_once_with(expected_write)

    def test_save_file(self):
        """Test save_file method using default binary 'type'."""
        # Arrange
        name = "no"
        expected_type = "BINary"
        waiting_time = 0.001  # shorten this, used only for 'time.sleep'.
        expected_writes = [
            unittest.mock.call(":STOP\n".encode()),
            unittest.mock.call(":WAV:FORM BYTE\n".encode()),
            unittest.mock.call(":WAVeform:LENGth?\n".encode()),
            unittest.mock.call(f":FILE:SAVE:NAME {name}\n".encode()),
            unittest.mock.call(f":FILE:SAVE:{expected_type}:EXECute\n".encode()),
            unittest.mock.call(":START\n".encode()),
        ]
        # Act
        self.yokogawa.save_file(name, waiting_time=waiting_time)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_save_file_ascii(self):
        """Test save_file method using ascii 'type'."""
        # Arrange
        name = "no"
        expected_type = "ASCii"
        waiting_time = 0.001  # shorten this, used only for 'time.sleep'.
        expected_writes = [
            unittest.mock.call(":STOP\n".encode()),
            unittest.mock.call(":WAV:FORM BYTE\n".encode()),
            unittest.mock.call(":WAVeform:LENGth?\n".encode()),
            unittest.mock.call(f":FILE:SAVE:NAME {name}\n".encode()),
            unittest.mock.call(f":FILE:SAVE:{expected_type}:EXECute\n".encode()),
            unittest.mock.call(":START\n".encode()),
        ]
        # Act
        self.yokogawa.save_file(name, data_type=expected_type.lower(), waiting_time=waiting_time)
        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_save_file_excepts(self):
        """Test the save_file method excepts at wrong file 'type'."""
        # Arrange
        name = "no"
        unexpected_type = "BINasc"
        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.yokogawa.save_file(name, unexpected_type)

        # Assert
        self._transport_mock.write.assert_not_called()

    def test_find_file_name(self):
        """Test find_file_name method using default 'last' file selection."""
        # Arrange
        name = "no"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        label = "007"
        expected_file_name = [name.upper() + label + ".csv"]
        # Act
        with patch("qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents):
            last_file = self.yokogawa.find_file_name(name)

        # Assert
        self.assertListEqual(expected_file_name, last_file)

    def test_find_file_name_all(self):
        """Test find_file_name method using 'all' files selection."""
        # Arrange
        name = "no"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        expected_file_names = contents
        # Act
        with patch("qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents):
            all_files = self.yokogawa.find_file_name(name, "all")

        # Assert
        self.assertListEqual(expected_file_names, all_files)

    def test_copy_file(self):
        """Test copy_file method using default 'last' file selection."""
        # Arrange
        name = "no"
        dest = "another_dir"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        label = "007"
        expected_file_name = name.upper() + label + ".csv"
        # Act
        with patch(
                "qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents
        ), patch("qmi.instruments.yokogawa.dlm4038.shutil.copy") as copy_patch:
            self.yokogawa.copy_file(name, dest)

        # Assert
        copy_patch.assert_called_once_with(f"{self.def_path}{expected_file_name}", dest)

    def test_copy_file_all(self):
        """Test find_file_name method using 'all' files selection."""
        # Arrange
        name = "no"
        dest = "another_dir"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        expected_calls = [
            unittest.mock.call(f"{self.def_path}{f}", dest) for f in contents
        ]
        # Act
        with patch(
                "qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents
        ), patch("qmi.instruments.yokogawa.dlm4038.shutil.copy") as copy_patch:
            self.yokogawa.copy_file(name, dest, "all")

        # Assert
        copy_patch.assert_has_calls(expected_calls)

    def test_delete_file(self):
        """Test delete_file method using default 'last' and 'binary' file selections."""
        # Arrange
        name = "no"
        ftype = "BINary"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        label = "007"
        file_name = name.upper() + label
        expected_writes = [
            unittest.mock.call(":STOP\n".encode()),
            unittest.mock.call(f':FILE:DELete:{ftype}:EXECute "{file_name}"\n'.encode()),
            unittest.mock.call(":START\n".encode()),
        ]
        # Act
        with patch("qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents):
            self.yokogawa.delete_file(name)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_delete_file_ascii(self):
        """Test delete_file method using default 'last' and 'ascii' file selections."""
        # Arrange
        name = "no"
        ftype = "ASCii"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        label = "007"
        file_name = name.upper() + label
        expected_writes = [
            unittest.mock.call(":STOP\n".encode()),
            unittest.mock.call(f':FILE:DELete:{ftype}:EXECute "{file_name}"\n'.encode()),
            unittest.mock.call(":START\n".encode()),
        ]
        # Act
        with patch("qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents):
            self.yokogawa.delete_file(name, data_type=ftype.lower())

        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_delete_file_all(self):
        """Test find_file_name method using 'all' files selection."""
        # Arrange
        name = "no"
        ftype = "BINary"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        file_names = [f"{name[:-4]}" for name in contents]
        expected_writes = [unittest.mock.call(":STOP\n".encode())]
        expected_writes += [
            unittest.mock.call(f':FILE:DELete:{ftype}:EXECute "{file_name}"\n'.encode()) for file_name in file_names
        ]
        expected_writes += [unittest.mock.call(":START\n".encode())]
        # Act
        with patch("qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents):
            self.yokogawa.delete_file(name, "all")

        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)

    def test_delete_file_all_ascii(self):
        """Test find_file_name method using 'all' and 'ascii' files selection."""
        # Arrange
        name = "no"
        ftype = "ASCii"
        contents = [f"{name.upper()}00{f}.csv" for f in range(8)]
        file_names = [f"{name[:-4]}" for name in contents]
        expected_writes = [unittest.mock.call(":STOP\n".encode())]
        expected_writes += [
            unittest.mock.call(f':FILE:DELete:{ftype}:EXECute "{file_name}"\n'.encode()) for file_name in file_names
        ]
        expected_writes += [unittest.mock.call(":START\n".encode())]
        # Act
        with patch("qmi.instruments.yokogawa.dlm4038.os.listdir", return_value=contents):
            self.yokogawa.delete_file(name, "all", ftype.lower())

        # Assert
        self._transport_mock.write.assert_has_calls(expected_writes)


if __name__ == '__main__':
    unittest.main()
