import unittest
from unittest.mock import MagicMock

from qmi.core.transport import QMI_Transport
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.exceptions import QMI_InstrumentException


class TestScpiProtocol(unittest.TestCase):

    def test_constructor(self):

        transport = MagicMock()

        ScpiProtocol(transport)
    
    def test_write(self):
        # arrange
        command = "test"
        expected_call = b"test\n"

        transport_mock = MagicMock(spec=QMI_Transport)
       
        # act
        scpi_protocol = ScpiProtocol(transport_mock)
        scpi_protocol.write(command)

        # assert
        transport_mock.write.assert_called_with(expected_call)

    def test_write_carrage_return(self):
        # arrange
        command = "test"
        command_terminator = "\r"
        expected_call = b"test\r"
        transport_mock = MagicMock(spec=QMI_Transport)

        # act
        scpi_protocol = ScpiProtocol(transport_mock, command_terminator)
        scpi_protocol.write(command)
        
        # assert
        transport_mock.write.assert_called_with(expected_call)

    def test_ask(self):
        # arrange
        command = "test"
        expected_call = b"test\n"
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read_until.return_value = b"intresting result\n"
       
        # act
        scpi_protocol = ScpiProtocol(transport_mock)
        response = scpi_protocol.ask(command)

        # assert
        transport_mock.write.assert_called_with(expected_call)
        transport_mock.discard_read.assert_not_called()
        transport_mock.read_until.assert_called_with(message_terminator=b'\n', timeout=None)
        self.assertEqual(response, "intresting result")

    def test_ask_discard(self):
        # arrange
        command = "test"
        expected_call = b"test\n"
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read_until.return_value = b"intresting result\n"
       
        # act
        scpi_protocol = ScpiProtocol(transport_mock)
        response = scpi_protocol.ask(command, discard=True)

        # assert
        transport_mock.write.assert_called_with(expected_call)
        transport_mock.discard_read.assert_called_once()
        transport_mock.read_until.assert_called_with(message_terminator=b'\n', timeout=None)
        self.assertEqual(response, "intresting result")

    def test_ask_raises_on_bad_response(self):
        # arrange
        command = "test"
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read_until.return_value = b"intresting result\r"
       
        # act
        # assert
        scpi_protocol = ScpiProtocol(transport_mock)
        with self.assertRaises(QMI_InstrumentException):
            scpi_protocol.ask(command)

    def test_read_binary_data(self):
        #arrange
        transport_mock = MagicMock(spec=QMI_Transport)
        expected_data = b"1234567890"
        transport_mock.read.side_effect = [b"#2", b"10", expected_data, b"\n"]

        #act
        scpi_protocol = ScpiProtocol(transport_mock)
        data = scpi_protocol.read_binary_data()

        #assert
        self.assertEqual(data, expected_data)

    def test_read_binary_data_raise_invalid_first_byte(self):
        #arrange
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read.side_effect = [b"-2"]

        #act
        #assert
        scpi_protocol = ScpiProtocol(transport_mock)
        with self.assertRaises(QMI_InstrumentException):
            scpi_protocol.read_binary_data()
       
    def test_read_binary_data_raise_invalid_second_byte(self):
        #arrange
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read.side_effect = [b"##"]

        #act
        #assert
        scpi_protocol = ScpiProtocol(transport_mock)
        with self.assertRaises(QMI_InstrumentException):
            scpi_protocol.read_binary_data()
       
    def test_read_binary_data_raise_when_second_byte_is_zero(self):
        #arrange
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read.side_effect = [b"#0"]

        #act
        #assert
        scpi_protocol = ScpiProtocol(transport_mock)
        with self.assertRaises(QMI_InstrumentException):
            scpi_protocol.read_binary_data()

    def test_read_binary_data_raise_size_not_digits(self):
        #arrange
        transport_mock = MagicMock(spec=QMI_Transport)
        transport_mock.read.side_effect = [b"#2", b"!@"]
   
        #act
        #assert
        scpi_protocol = ScpiProtocol(transport_mock)
        with self.assertRaises(QMI_InstrumentException):
            scpi_protocol.read_binary_data()

    def test_read_binary_data_raise_no_valid_response_terminator(self):
        #arrange
        transport_mock = MagicMock(spec=QMI_Transport)
        expected_data = b"1234567890"
        transport_mock.read.side_effect = [b"#2", b"10", expected_data, b"\b"]

        #act
        #assert
        scpi_protocol = ScpiProtocol(transport_mock)
        with self.assertRaises(QMI_InstrumentException):
            scpi_protocol.read_binary_data()

