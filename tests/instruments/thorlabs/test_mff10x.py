import struct
import unittest, unittest.mock

from qmi.instruments.thorlabs import Thorlabs_Mff10X

import qmi.core.exceptions
from qmi.core.context import QMI_Context


class TestParsingAndFormatFunctions(unittest.TestCase):

    def test_format_msg_hw_req_info(self):
        # arrange
        dest = 0x1
        source = 0x2
        expected = bytes([0x05, 0x00, 0x00, 0x00, dest, source])
        # act
        msg = qmi.instruments.thorlabs.mff10x._format_msg_hw_req_info(dest, source)
        # assert
        self.assertEqual(msg, expected)

    def test_format_msg_mot_req_statusbits(self):
        # arrange
        chan_iden = 0x3
        dest = 0x1
        source = 0x2
        expected = bytes([0x29, 0x04, chan_iden, 0x00, dest, source])
        # act
        msg = qmi.instruments.thorlabs.mff10x._format_msg_mot_req_statusbits(chan_iden, dest, source)
        # assert
        self.assertEqual(msg, expected)

    def test_format_msg_mot_move_jog(self):
        # arrange
        chan_iden = 0x3
        direction = 0x4
        dest = 0x1
        source = 0x2
        expected = bytes([0x6A, 0x04, chan_iden, direction, dest, source])
        # act
        msg = qmi.instruments.thorlabs.mff10x._format_msg_mot_move_jog(chan_iden, direction, dest, source)
        # assert
        self.assertEqual(msg, expected)

    def test_parse_msg_hw_get_info(self):
        """Test that parsing works as expected to extract hardware info"""
        # arrange
        serial_number = "\x01\x02\x03\x04"  # bits 6:10
        model_number = "5678901\x00"  # bits 10:18
        hw_type = "\x01\x00"  # bits 18-19
        fw_version = "\x02\x03\x04"  # bits 22, 21, 20)
        hw_version, mod_state, num_channels = "\x05\x00", "\x06\x00", "\x07\x00"  # bits 84-85, 86-87, 88-89
        fill_in_middle = "\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04" + \
            "\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08" + \
            "\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03"
        end_fill = "\x00"  # bit 90
        input_string = "\x06\x00\x5a\x00\x81" + serial_number + model_number + hw_type + fw_version +\
            fill_in_middle + hw_version + mod_state + num_channels + end_fill
        input_msg = bytearray(input_string.encode())

        expected_serial_number = struct.unpack('<I', bytearray(serial_number.encode()))[0]
        expected_model_number = model_number.rstrip("\x00")
        expected_hw_type = struct.unpack('<H', bytearray(hw_type.encode()))[0]
        expected_fw_version = (ord(str(fw_version[2])), ord(str(fw_version[1])), ord(str(fw_version[0])))
        expected_hw_version = struct.unpack('<H', bytearray(hw_version.encode()))[0]
        expected_mod_state = struct.unpack('<H', bytearray(mod_state.encode()))[0]
        expected_num_channels = struct.unpack('<H', bytearray(num_channels.encode()))[0]
        # act
        hwinfo = qmi.instruments.thorlabs.mff10x._parse_msg_hw_get_info(input_msg)
        # assert
        self.assertEqual(hwinfo.serial_number, expected_serial_number)
        self.assertEqual(hwinfo.model_number, expected_model_number)
        self.assertEqual(hwinfo.hw_type, expected_hw_type)
        self.assertTupleEqual(hwinfo.fw_version, expected_fw_version)
        self.assertEqual(hwinfo.hw_version, expected_hw_version)
        self.assertEqual(hwinfo.mod_state, expected_mod_state)
        self.assertEqual(hwinfo.num_channels, expected_num_channels)

    def test_parse_msg_hw_get_info_raises_exceptions(self):
        """Test that parsing message checks works as expected to raise exceptions"""
        # arrange
        input_string_1 = "\x64\x04\x5a\x00\x81\x00"
        expected_message_1 = "Got message ID {:04x} while expecting MSG_HW_GET_INFO".format(
            struct.unpack('<H', bytearray(input_string_1[:2].encode()))[0]
            )
        input_string_2 = "\x06\x00\x5a\x00\x81\x00"
        expected_message_2 = "Got {} bytes while expecting 90 bytes MSG_HW_GET_INFO".format(len(input_string_2) + 1)
        # act
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc_1:
            qmi.instruments.thorlabs.mff10x._parse_msg_hw_get_info(bytearray(input_string_1.encode()))

        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc_2:
            qmi.instruments.thorlabs.mff10x._parse_msg_hw_get_info(bytearray(input_string_2.encode()))

        # assert
        self.assertEqual(exc_1.exception.args[0], expected_message_1)
        self.assertEqual(exc_2.exception.args[0], expected_message_2)

    def test_parse_msg_mot_get_statusbits(self):
        """Test getting status bits works"""
        # arrange
        status_bits = "\x00\x00\x01\x02\x03\x04"
        input_string = "\x2A\x04\x5a\x00\x81" + status_bits
        expected = struct.unpack('<I', bytearray(status_bits[-4:].encode()))[0]
        # act
        res = qmi.instruments.thorlabs.mff10x._parse_msg_mot_get_statusbits(bytearray(input_string.encode()))
        # assert
        self.assertEqual(res, expected)

    def test_parse_msg_mot_get_statusbits_raises_exceptions(self):
        """Test getting status bits raises exceptions"""
        # arrange
        input_string_1 = "\x04\x2A\x5a\x00\x81"
        expected_message_1 = "Got message ID {:04x} while expecting MSG_MOT_GET_STATUSBITS".format(
            struct.unpack('<H', bytearray(input_string_1[:2].encode()))[0]
            )
        input_string_2 = "\x2A\x04\x5a\x00\x81"
        expected_message_2 = "Got {} bytes while expecting 12 bytes MSG_MOT_GET_STATUSBITS".format(
            len(input_string_2) + 1)
        # act
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc_1:
            qmi.instruments.thorlabs.mff10x._parse_msg_mot_get_statusbits(bytearray(input_string_1.encode()))

        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc_2:
            qmi.instruments.thorlabs.mff10x._parse_msg_mot_get_statusbits(bytearray(input_string_2.encode()))

        # assert
        self.assertEqual(exc_1.exception.args[0], expected_message_1)
        self.assertEqual(exc_2.exception.args[0], expected_message_2)

    def test_parse_msg_mot_move_completed(self):
        """Test that correct move response raises no exception"""
        input_string = "\x64\x04\x5a\x00\x81\x00"
        qmi.instruments.thorlabs.mff10x._parse_msg_mot_move_completed(bytearray(input_string.encode()))

    def test_parse_msg_mot_move_completed_raises_exception(self):
        """Test that wrong move response raises an exception"""
        input_string = "\x04\x64\x5a\x00\x81\x00"
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            qmi.instruments.thorlabs.mff10x._parse_msg_mot_move_completed(bytearray(input_string.encode()))


class TestThorlabsMFF10x(unittest.TestCase):

    def setUp(self) -> None:
        unittest.mock.patch("qmi.core.transport.QMI_SerialTransport._validate_device_name")
        qmi_context = unittest.mock.MagicMock(spec=QMI_Context)
        qmi_context.name = "mockyflop"
        self.ser_address = "COM100"
        self.baudrate = 115200
        transport_id = "serial:{}:baudrate={}".format(self.ser_address, self.baudrate)
        self.thorlabs = Thorlabs_Mff10X(qmi_context, "flippy", transport_id)

    def test_open_close(self):
        with unittest.mock.patch("serial.Serial") as ser:
            self.thorlabs.open()
            self.thorlabs.close()

            ser.assert_called_once_with(
                self.ser_address,
                baudrate=self.baudrate,  # The rest are defaults
                bytesize=8,
                parity='N',
                rtscts=True,
                stopbits=1.0,
                timeout=0.04
                )

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_read_message(self, mock_read):
        """See that the _read_message method reads only the expected 6 bits. Fill the buffer with `random` bits"""
        mock_read.return_value = bytearray("blablabla".encode())  # returns 9 bits
        expected = bytearray("blabla".encode())  # but the regular return with extra data is of expected length of 6.
        self.thorlabs._transport.read.side_effect = [expected[:6], expected[6:22]]
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            msg = self.thorlabs._read_message(None)
            self.thorlabs.close()

        self.assertEqual(msg, expected)

    def test_read_message_with_data(self):
        """6-bit input `00x10x00x81a` should trigger extra data read of 16 bits in _read_buffer call."""
        # 5th bit 0x81 indicates that extra data is present in buffer, and 3rd bit 0x10 that it is 16 bits of length.
        expected = bytearray("00\x10\x00\x81abfdaj;jb;aj;lf;jl".encode())  # Total length of 24 bits
        self.thorlabs._transport.read = unittest.mock.MagicMock(self.thorlabs._transport.read)
        self.thorlabs._transport.read.side_effect = [expected[:6], expected[6:22]]
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            msg = self.thorlabs._read_message(None)
            self.thorlabs.close()

        self.assertEqual(msg, expected[:(6+16)])  # We should see total of 22 bits read

    def test_read_message_with_data_invalid_length(self):
        """"An error should be raised if the extra data present is not of expected length"""
        expected = bytearray("blab\x81a123456.7".encode())  # bit 3 'a' indicates 97 extra data bits, but we have only 8
        self.thorlabs._transport.read = unittest.mock.MagicMock(self.thorlabs._transport.read)
        self.thorlabs._transport.read.side_effect = [expected[:6], expected[6:]]
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs._read_message(None)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_get_idn(self, mock_read):
        # arrange
        serial_number = "\x01\x02\x03\x04"  # bits 6:10
        model_number = "5678901\x00"  # bits 10:18
        hw_type = "\x01\x00"  # bits 18-19
        fw_version = "\x02\x03\x04"  # bits 22, 21, 20)
        hw_version, mod_state, num_channels = "\x05\x00", "\x06\x00", "\x07\x00"  # bits 84-85, 86-87, 88-89
        fill_in_middle = "\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04" + \
                         "\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06" + \
                         "\x07\x08\x09\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x00\x01\x02\x03"
        end_fill = "\x00"  # bit 90
        input_string = "\x06\x00\x5a\x00\x81" + serial_number + model_number + hw_type + fw_version + \
                       fill_in_middle + hw_version + mod_state + num_channels + end_fill

        expected = 'QMI_InstrumentIdentification(vendor=\'Thorlabs\', model=\'{}\', serial=\'{}\', version=\'{}.{}.{}\')'.format(
            model_number.rstrip("\x00"), struct.unpack('<I', bytearray(serial_number.encode()))[0],
                ord(str(fw_version[2])), ord(str(fw_version[1])), ord(str(fw_version[0])))
        mock_read.return_value = bytearray(input_string.encode())
        # act
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            idn = self.thorlabs.get_idn()
            self.thorlabs.close()

        # assert
        self.assertEqual(str(idn), expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_get_position(self, mock_read):
        """Test that get_position() returns a set of random status bits for position."""
        # arrange
        status_bits = "\x00\x00\x01\x02\x03\x04"  # Some random bits to represent the "status" reply
        input_string = "\x2A\x04\x5a\x00\x81" + status_bits  # 0x2A + 0x04 = 0x042A is the expected return code,
        # 0x81 indicates extra data present. The first two following are skipped (apparently)
        expected = struct.unpack('<I', bytearray(status_bits[-4:].encode()))[0] & 3
        mock_read.return_value = bytearray(input_string.encode())
        # act
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            pos = self.thorlabs.get_position()
            self.thorlabs.close()

        # assert
        self.assertEqual(pos, expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_move_mount_wait_complete(self, mock_read):
        """Test that move_mount() returns. A set of random status bits needed for the get_position() call within."""
        # arrange
        status_bits = "\x00\x00\x01\x02\x03\x04"  # Some random bits to represent the "status" reply, except for 0x01
        # that tells we are going into direction 1
        input_string = "\x2A\x04\x5a\x00\x81" + status_bits  # 0x2A + 0x04 = 0x042A is the expected return code
        mock_read.return_value = bytearray(input_string.encode())
        # act
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            self.thorlabs.move_mount(1, True)  # using max timeout
            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_move_mount_wait_complete_timeout(self, mock_read):
        """Test that get_position() time-outs, when no extra data is returned within time-out."""
        # arrange
        input_string = "\x2A\x04\x5a\x00\x81"  # 0x2A + 0x04 = 0x042A is the expected return code
        mock_read.return_value = bytearray(input_string.encode())
        # act and assert
        with self.assertRaises(qmi.core.exceptions.QMI_TimeoutException), unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            self.thorlabs.move_mount(1, True, 0.1)

        self.thorlabs.close()

    def test_move_mount_invalid_direction(self):
        """Test that ValueError is raised when calling 'move_mount' with invalid direction number."""
        # arrange, act and assert
        with self.assertRaises(ValueError), unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            self.thorlabs.move_mount(3, True)

        self.thorlabs.close()


if __name__ == '__main__':
    unittest.main()
