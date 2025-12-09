import unittest
import unittest.mock

import qmi.core.exceptions
from qmi.core.context import QMI_Context
from qmi.instruments.agiltron._ff_optical_switch import Agiltron_FfOpticalSwitch
from qmi.instruments.agiltron import Agiltron_Ff1x4, Agiltron_Ff1x8

from tests.patcher import PatcherQmiContext as QMI_Context


class TestAgiltronFfOpticalSwitch(unittest.TestCase):

    def setUp(self) -> None:
        unittest.mock.patch("qmi.core.transport.QMI_SerialTransport._validate_device_name")
        qmi_context = QMI_Context("mockers")
        self.ser_address = "COM100"
        self.baudrate = 9600
        self.timeout = 1
        transport_id = "serial:{}:baudrate={}".format(self.ser_address, self.baudrate)
        self.agiltron = Agiltron_FfOpticalSwitch(qmi_context, "switchy", transport_id)
        with unittest.mock.patch("serial.Serial") as self.ser:
            self.agiltron.open()

    def tearDown(self) -> None:
        self.agiltron.close()

    def test_open_close(self):
        self.ser.assert_called_once_with(
            self.ser_address,
            baudrate=self.baudrate,  # The rest are defaults
            bytesize=8,
            parity='N',
            rtscts=False,
            stopbits=1,
            timeout=0.04
            )

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_get_active_channel(self, mock_read):
        """See that the get_active_channel RPC method returns the expected channel number."""
        expected = 4
        mock_read.return_value = bytes([0x01, 0x02, 0x03, expected])
        channel = self.agiltron.get_active_channel()

        self.assertEqual(channel, expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_set_channel_active(self, mock_read):
        """See that the set_channel_active RPC method sets the expected channel active."""
        channel = 1
        expected = bytes([0x01, 0x12, 0x00, int(channel)])
        mock_read.return_value = expected
        self.agiltron.set_channel_active(channel)
        write_call_in_calls_index = ["().write" in call[0] for call in self.ser.mock_calls].index(True)
        self.assertTupleEqual(self.ser.mock_calls[write_call_in_calls_index][1], (expected,))

        self.agiltron._transport._serial.write.assert_called_once_with(expected)

    def test_set_channel_active_with_wrong_channel_number(self):
        """ Test that the channel number checking in set_channel_active works as expected"""
        channels = [0, self.agiltron.CHANNELS + 1]
        for channel in channels:
            with self.assertRaises(ValueError):
                self.agiltron.set_channel_active(channel)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_set_channel_active_with_erroneous_reply(self, mock_read):
        """See that exceptions are raised with wrong return data """
        channel = 1
        request = [0x01, 0x12, 0x00]
        side_effect = [bytes(request + [int(channel), 0x05]),  # Test 1
                       bytes(request + [int(channel + 1)]),  # Test 2
                       bytes(request)]  # Test 3
        exp_req = request + [channel]
        expected_exception_1 = f"The reply {side_effect[0]} does not match request {exp_req}. Correct channel not set."
        expected_exception_2 = f"The reply {side_effect[1]} does not match request {exp_req}. Correct channel not set."
        expected_exception_3 = f"The reply {side_effect[2]} does not match request {exp_req}. Correct channel not set."
        mock_read.side_effect = side_effect
        # Test 1: too many bytes returned
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc, unittest.mock.patch("serial.Serial"):
            self.agiltron.set_channel_active(channel)

        self.assertEqual(expected_exception_1, str(exc.exception))

        # Test 2: correct number of bytes but wrong value
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc, unittest.mock.patch("serial.Serial"):
            self.agiltron.set_channel_active(channel)

        self.assertEqual(expected_exception_2, str(exc.exception))

        # Test 3: too few bytes returned
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc, unittest.mock.patch("serial.Serial"):
            self.agiltron.set_channel_active(channel)

        self.assertEqual(expected_exception_3, str(exc.exception))


class TestAgiltronFf1x4(unittest.TestCase):

    def setUp(self) -> None:
        unittest.mock.patch("qmi.core.transport.QMI_SerialTransport._validate_device_name")
        qmi_context = QMI_Context("mockers")
        self.ser_address = "COM100"
        self.baudrate = 9600
        self.timeout = 1
        transport_id = "serial:{}:baudrate={}".format(self.ser_address, self.baudrate)
        self.agiltron = Agiltron_Ff1x4(qmi_context, "switchy", transport_id)
        with unittest.mock.patch("serial.Serial") as self.ser:
            self.agiltron.open()

    def tearDown(self) -> None:
        self.agiltron.close()

    def test_no_of_channels(self):
        """Test that we have expected number of channels."""
        channels_expected = 4
        self.assertEqual(channels_expected, self.agiltron.CHANNELS)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_set_channel_active(self, mock_read):
        """See that the set_channel_active RPC method sets the expected channel active."""
        for channel in range(1, 5):
            expected = bytes([0x01, 0x12, 0x00, int(channel)])
            mock_read.return_value = expected
            self.agiltron.set_channel_active(channel)
            write_call_in_calls_index = ["().write" in call[0] for call in self.ser.mock_calls].index(True)
            self.assertTupleEqual(self.ser.mock_calls[write_call_in_calls_index][1], (expected,))

            self.agiltron._transport._serial.write.assert_called_once_with(expected)
            self.ser.reset_mock()

    def test_set_channel_active_with_wrong_channel_number(self):
        """ Test that the channel number checking in set_channel_active works as expected"""
        channels = [0, 5]
        with unittest.mock.patch("serial.Serial"):
            for channel in channels:
                with self.assertRaises(ValueError):
                    self.agiltron.set_channel_active(channel)


class TestAgiltronFf1x8(unittest.TestCase):

    def setUp(self) -> None:
        unittest.mock.patch("qmi.core.transport.QMI_SerialTransport._validate_device_name")
        qmi_context = QMI_Context("mockers")
        self.ser_address = "COM100"
        self.baudrate = 9600
        self.timeout = 1
        transport_id = "serial:{}:baudrate={}".format(self.ser_address, self.baudrate)
        self.agiltron = Agiltron_Ff1x8(qmi_context, "switchy", transport_id)
        with unittest.mock.patch("serial.Serial") as self.ser:
            self.agiltron.open()

    def tearDown(self) -> None:
        self.agiltron.close()

    def test_no_of_channels(self):
        """Test that we have expected number of channels."""
        channels_expected = 8
        self.assertEqual(channels_expected, self.agiltron.CHANNELS)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_set_channel_active(self, mock_read):
        """See that the set_channel_active RPC method sets the expected channel active."""
        for channel in range(1, 9):
            expected = bytes([0x01, 0x12, 0x00, int(channel)])
            mock_read.return_value = expected
            self.agiltron.set_channel_active(channel)
            write_call_in_calls_index = ["().write" in call[0] for call in self.ser.mock_calls].index(True)
            self.assertTupleEqual(self.ser.mock_calls[write_call_in_calls_index][1], (expected,))

            self.agiltron._transport._serial.write.assert_called_once_with(expected)
            self.ser.reset_mock()

    def test_set_channel_active_with_wrong_channel_number(self):
        """ Test that the channel number checking in set_channel_active works as expected"""
        channels = [0, 9]
        with unittest.mock.patch("serial.Serial"):
            for channel in channels:
                with self.assertRaises(ValueError):
                    self.agiltron.set_channel_active(channel)


if __name__ == '__main__':
    unittest.main()
