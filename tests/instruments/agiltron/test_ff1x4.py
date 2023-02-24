import unittest, unittest.mock

import qmi
from qmi.instruments.agiltron.ff1x4 import Agiltron_FF1x4

import qmi.core.exceptions
from qmi.core.context import QMI_Context


class TestAgiltronFF1x4(unittest.TestCase):

    def setUp(self) -> None:
        unittest.mock.patch("qmi.core.transport.QMI_SerialTransport._validate_device_name")
        qmi_context = unittest.mock.MagicMock(spec=QMI_Context)
        qmi_context.name = "mockers"
        self.ser_address = "COM100"
        self.baudrate = 9600
        self.timeout = 1
        transport_id = "serial:{}:baudrate={}".format(self.ser_address, self.baudrate)
        self.agiltron = Agiltron_FF1x4(qmi_context, "switchy", transport_id)

    def tearDown(self) -> None:
        self.agiltron.close()

    def test_open_close(self):
        with unittest.mock.patch("serial.Serial") as ser:
            self.agiltron.open()
            ser.assert_called_once_with(
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
        with unittest.mock.patch("serial.Serial"):
            self.agiltron.open()
            channel = self.agiltron.get_active_channel()

        self.assertEqual(channel, expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_set_channel_active(self, mock_read):
        """See that the set_channel_active RPC method sets the expected channel active."""
        channel = 3
        expected = bytes([0x01, 0x12, 0x00, int(channel)])
        mock_read.return_value = expected
        with unittest.mock.patch("serial.Serial") as ser:
            self.agiltron.open()
            self.agiltron.set_channel_active(channel)
            write_call_in_calls_index = ["().write" in call[0] for call in ser.mock_calls].index(True)
            self.assertTupleEqual(ser.mock_calls[write_call_in_calls_index][1], (expected,))

        self.agiltron._transport._serial.write.assert_called_once_with(expected)

    def test_set_channel_active_with_wrong_channel_number(self):
        """ Test that the channel number checking in set_channel_active works as expected"""
        channels = [0, self.agiltron.CHANNELS + 1]
        with unittest.mock.patch("serial.Serial"):
            self.agiltron.open()
            for channel in channels:
                with self.assertRaises(ValueError):
                    self.agiltron.set_channel_active(channel)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read")
    def test_set_channel_active_with_erroneous_reply(self, mock_read):
        """See that exceptions are raised with wrong return data """
        channel = 1
        mock_read.side_effect = [bytes([0x01, 0x12, 0x00, int(channel), 0x05]),  # Test 1
                                 bytes([0x01, 0x12, 0x00, int(channel + 1)]),  # Test 2
                                 bytes([0x01, 0x12, 0x00])]  # Test 3
        # Test 1: too many bytes returned
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException), unittest.mock.patch("serial.Serial"):
            self.agiltron.open()
            self.agiltron.set_channel_active(channel)

        self.agiltron.close()
        # Test 2: correct number of bytes but wrong value
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException), unittest.mock.patch("serial.Serial"):
            self.agiltron.open()
            self.agiltron.set_channel_active(channel)

        self.agiltron.close()
        # Test 3: too few bytes returned
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException), unittest.mock.patch("serial.Serial"):
            self.agiltron.open()
            self.agiltron.set_channel_active(channel + 1)


if __name__ == '__main__':
    unittest.main()
