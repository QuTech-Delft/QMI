import sys

import unittest, unittest.mock
import struct
import binascii


class UsbErrorMock(Exception):
    """Stand-in for `usb.core.USBError`."""


class EndpointMock:
    """Mock values from usb.util module. See inline comments for attribute name."""
    bmAttributes: int = 0x03  # ENDPOINT_TYPE_INTR
    bEndpointAddress_in = 0x80  # ENDPOINT_IN
    bEndpointAddress_out = 0x00  # ENDPOINT_OUT

    def __init__(self, endpoint=True):
        if endpoint:
            self.bEndpointAddress = self.bEndpointAddress_in
        else:
            self.bEndpointAddress = self.bEndpointAddress_out


class InterfaceClassMock:
    """Mock endpoints of an active device"""
    bInterfaceClass: int = 3
    index = 0

    def __init__(self, endpoint_in, endpoint_out):
        self._endpoint_in = endpoint_in
        self._endpoint_out = endpoint_out

    def endpoints(self):
        mock_in = EndpointMock(self._endpoint_in)
        mock_out = EndpointMock(not self._endpoint_out)

        return [mock_in, mock_out]


class InterfaceMock:
    """Mock active configuration interfaces of a device"""
    def __init__(self, no_active_config=False, endpoint_in=True, endpoint_out=True):
        self._no_active_config = no_active_config
        self._endpoint_in = endpoint_in
        self._endpoint_out = endpoint_out

    def interfaces(self):
        if self._no_active_config:
            return []

        return [InterfaceClassMock(self._endpoint_in, self._endpoint_out)]


class DevMock:
    """Mock active configuration call."""
    def __init__(self, no_active_config=False, endpoint_in=True, endpoint_out=True):
        """
        Parameters:
            no_active_config: get_active_configuration will return an empty list if True.
            endpoint_in: By setting this as False the returned interface has wrong in endpoint value.
            endpoint_out: By setting this as False the returned interface has wrong out endpoint value.
        """
        self._no_active_config = no_active_config
        self._endpoint_in = endpoint_in
        self._endpoint_out = endpoint_out

    def get_active_configuration(self):
        """Return an active configuration."""
        return InterfaceMock(self._no_active_config, self._endpoint_in, self._endpoint_out)

    def is_kernel_driver_active(self, index):
        """Mock detach of kernel driver"""
        if index == 0:
            return False  # No detaching
        else:
            return True  # Detaching

    def ctrl_transfer(self, *args):
        return

    def read(self, *args):
        raise UsbErrorMock


from qmi.instruments.thorlabs import Thorlabs_Tsp01b
import qmi.core.exceptions
from qmi.utils.context_managers import open_close
from tests.patcher import PatcherQmiContext

ENDPOINT_TYPE_INTR: int = 0x03
ENDPOINT_IN: int = 0x80
ENDPOINT_OUT: int = 0x00


# Mock functions
def endpoint_type(attribute):
    """Mock usb.util.endpoint_type call"""
    return ENDPOINT_TYPE_INTR


def endpoint_direction(direction: int):
    """Mock usb.util.endpoint_direction call"""
    if direction == EndpointMock.bEndpointAddress_in:
        return EndpointMock.bEndpointAddress_in

    elif direction == EndpointMock.bEndpointAddress_out:
        return EndpointMock.bEndpointAddress_out


def patch_usb(test_case: unittest.TestCase) -> unittest.mock.MagicMock:
    """Replace the `usb`, `usb.core` and `usb.util` modules by mocks for the duration of a test.

    The driver imports these modules inside its methods, so patching `sys.modules` is sufficient.
    """
    usb_mock = unittest.mock.MagicMock()
    usb_mock.CLASS_HID = InterfaceClassMock.bInterfaceClass
    usb_mock.core.USBError = UsbErrorMock
    usb_mock.util.ENDPOINT_TYPE_INTR = ENDPOINT_TYPE_INTR
    usb_mock.util.ENDPOINT_IN = ENDPOINT_IN
    usb_mock.util.ENDPOINT_OUT = ENDPOINT_OUT
    usb_mock.util.endpoint_type = endpoint_type
    usb_mock.util.endpoint_direction = endpoint_direction
    patcher = unittest.mock.patch.dict(
        sys.modules, {"usb": usb_mock, "usb.core": usb_mock.core, "usb.util": usb_mock.util}
    )
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return usb_mock


class TestThorlabsTsp01b(unittest.TestCase):
    def setUp(self):
        self._dev = DevMock()
        self._dev.write = unittest.mock.Mock()
        self._usb = patch_usb(self)
        self._usb.core.find.return_value = self._dev
        self.qmi_patcher = PatcherQmiContext()
        self.qmi_patcher.start("TestTsp01bContext")
        self.addCleanup(self.qmi_patcher.stop)
        self._serial = "123456"
        self.instr: Thorlabs_Tsp01b = qmi.make_instrument("instr", Thorlabs_Tsp01b, self._serial)

    def test_open_close(self):
        """Test opening and closing the instrument"""
        self.instr.open()
        self.instr.close()

        self._usb.core.find.assert_called_with(
            find_all=False, idVendor=0x1313, idProduct=0x80fa, serial_number=self._serial)

    def test_open_close_except_with_no_serial_number(self):
        """Test opening the instrument with no serial number excepts"""
        self._usb.core.find.return_value = None
        expected = f"Instrument with serial number {self._serial} not found (check device permission)"
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected)

    def test_open_close_except_with_no_HID_interface(self):
        """Test opening the instrument with no active config excepts"""
        self._usb.core.find.return_value = DevMock(True)
        expected = "Instrument does not have a HID interface"
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected)

    def test_open_close_except_with_no_IN_endpoint(self):
        """Test opening the instrument excepts if IN endpoint is not correctly defined."""
        self._usb.core.find.return_value = DevMock(False, False, True)
        expected = "Instrument does not have Interrupt IN endpoint"
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected)

    def test_open_close_except_with_no_OUT_endpoint(self):
        """Test opening the instrument excepts if OUT endpoint is not correctly defined."""
        self._usb.core.find.return_value = DevMock(False, True, False)
        expected = "Instrument does not have Interrupt OUT endpoint"
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.open()

        self.assertEqual(str(exc.exception), expected)


class TestThorlabsTsp01bMethods(unittest.TestCase):

    def _create_byte_string(self, code, data, cmd=None):
        # Packet format (32 bytes length):
        #   byte 0: fixed byte 0xF0
        #   byte 1: data length
        #   byte 2: fixed byte 0x00
        #   byte 3: fixed byte 0x01
        #   byte 4: reply/command code
        #   byte 5: CRC-8 over first 5 bytes
        #   byte 6: fixed byte 0xF1
        #   starting at byte 7: variable length data (may be empty)
        #   following data: 4 bytes CRC-32 over data (excluding the 0xF1 marker)
        #   padding with 0x00 until total length 32 bytes

        # bytes 0-4
        if cmd:
            # Data length is 0
            byte_string = bytes([0xf0, 0x00, 0x00, 0x01, code])
            # In the write call the command byte gets replaced with the ASCII version
            crc8_byte = cmd

        else:
            byte_string = bytes([0xf0, len(data), 0x00, 0x01, code])
            # I use the same static method for the CRC-8-AUTOSAR calculation from the code
            crc8_byte = bytes([Thorlabs_Tsp01b._crc8(byte_string)])

        # bytes 5-6
        byte_string += crc8_byte + bytes([0xf1])
        if cmd:
            # We do not CRC-check commands. So, just put zeroes
            data_crc = b"\x00" * 4

        else:
            # Calculate CRC-32 over data.
            data_crc = struct.pack("<I", binascii.crc32(data))

        # Add zero-padding until 32 bytes total length.
        padding = bytes((21 - len(data)) * [0x00])
        # Format final packet.
        byte_string = byte_string + data + data_crc + padding
        return byte_string

    def setUp(self):
        self._dev = DevMock()
        self._dev.write = unittest.mock.Mock()
        self._usb = patch_usb(self)
        self._usb.core.find.return_value = self._dev
        self.qmi_patcher = PatcherQmiContext()
        self.qmi_patcher.start("TestTsp01bContext")
        self.addCleanup(self.qmi_patcher.stop)
        self._serial = "123456"
        self.instr: Thorlabs_Tsp01b = qmi.make_instrument("instr", Thorlabs_Tsp01b, self._serial)

    def test_reset(self):
        """Test the reset method."""
        command_string = self._create_byte_string(0x01, bytes([0x00]), bytes([189]))
        reply_string = self._create_byte_string(0x04, bytes([0x00]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr):
            self.instr.reset()

        self._dev.write.assert_called_with(0, command_string, 2000)

    def test_unexpected_reply_to_reset(self):
        """Test the reset method raises exception."""
        expected = "Unexpected reply to reset command (01, 00)"
        # Now we return wrong reply parameter
        reply_string = self._create_byte_string(0x01, bytes([0x00]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.reset()

        self.assertEqual(str(exc.exception), expected)

    def test_get_idn(self):
        """Test the get_idn method."""
        expected_idn = []
        command_strings, reply_strings = [], []
        for i in [3, 2, 4, 1]:
            expected_idn.append(i)
            command_strings.append(
                self._create_byte_string(0x01, bytes([0x00]), bytes([189]))
            )
            reply_strings.append(
                self._create_byte_string(0x04, bytes([0x00 + i, 0x00 + i]))
            )
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock] + reply_strings
        with open_close(self.instr):
            idn = self.instr.get_idn()

        for i in range(4):
            self._dev.write.assert_called_with(0, command_strings[i], 2000)

        self.assertEqual(ord(idn.vendor), expected_idn[0])
        self.assertEqual(ord(idn.model), expected_idn[1])
        self.assertEqual(ord(idn.serial), expected_idn[2])
        self.assertEqual(ord(idn.version), expected_idn[3])

    def test_unexpected_reply_to_device_info_query(self):
        """Test the get_idn raises an exception."""
        expected = "Unexpected reply to device info query (01, 00)"
        # Now we return wrong reply parameter
        reply_string = self._create_byte_string(0x01, bytes([0x00]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.get_idn()

        self.assertEqual(str(exc.exception), expected)

    def test_get_internal_temperature(self):
        """Test get_internal_temperature method returns temperature value."""
        expected_t = -273.0  # Quite cold!
        command_string = self._create_byte_string(0x01, bytes([0x00]), bytes([189]))
        # Now length of reply data should be 5 and start with channel number, see driver.
        reply_string = self._create_byte_string(0x07, b"\x00\x00\x80\x88\xc3")
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr):
            temp_int = self.instr.get_internal_temperature()

        self._dev.write.assert_called_with(0, command_string, 2000)
        self.assertEqual(temp_int, expected_t)

    def test_sensor_not_connected(self):
        """Test get_internal_temperature method raises exception."""
        expected = "Sensor not connected"
        # Reply parameter 0x13 indicates sensor is not connected, with specific byte string
        reply_string = self._create_byte_string(0x13, b"\x03\x02\x24\x00")
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.get_internal_temperature()

        self.assertEqual(str(exc.exception), expected)

    def test_unexpected_reply_to_measurement_query(self):
        """Test get_internal_temperature method raises exception."""
        expected = "Unexpected reply to measurement query (07, 00 00 00 00)"
        # Reply data misses one byte, the channel number
        reply_string = self._create_byte_string(0x07, b"\x00\x00\x00\x00")
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.get_internal_temperature()

        self.assertEqual(str(exc.exception), expected)

    def test_get_external_temperature(self):
        """Test get_internal_temperature method returns temperature value."""
        expected_t = 273.0  # Quite warm!
        channels = [1, 2]
        command_string = self._create_byte_string(0x01, bytes([0x00]), bytes([189]))
        # Now length of reply data should be 5 and start with channel number, see driver.
        reply_string = self._create_byte_string(0x07, b"\x02\x00\x80\x88\x43")
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string, reply_string]
        with open_close(self.instr):
            for channel in channels:
                temp_int = self.instr.get_external_temperature(channel)
                self.assertEqual(temp_int, expected_t)

        self._dev.write.assert_called_with(0, command_string, 2000)

    def test_get_external_temperature_wrong_channel_number(self):
        """See that the call excepts on wrong channel number"""
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock]
        with open_close(self.instr), self.assertRaises(ValueError):
            self.instr.get_external_temperature(0)

    def test_get_humidity(self):
        """Test get_internal_temperature method returns temperature value."""
        expected_h2o = 0.0  # Dry
        command_string = self._create_byte_string(0x01, bytes([0x00]), bytes([189]))
        # Now length of reply data should be 5 and start with channel number, see driver.
        reply_string = self._create_byte_string(0x07, b"\x01\x00\x00\x00\x00")
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr):
            humidity = self.instr.get_humidity()

        self._dev.write.assert_called_with(0, command_string, 2000)
        self.assertEqual(humidity, expected_h2o)

    def test_packet_too_short_exception(self):
        """See that an exception is raised if the packet is too short."""
        expected = "Received short packet from instrument"
        reply_string = self._create_byte_string(0x00, bytes([0x00]), bytes([189]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string[:10]]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.reset()

        self.assertEqual(str(exc.exception)[:len(expected)], expected)

    def test_packet_has_wrong_fixed_values(self):
        """See that an exception is raised if the packet has a wrong fixed value."""
        expected = "Received invalid packet from instrument"
        reply_string = self._create_byte_string(0x00, bytes([0x00]), bytes([189]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string[1:]]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.reset()

        self.assertEqual(str(exc.exception)[:len(expected)], expected)

    def test_packet_except_on_bad_crc_check_value(self):
        """See that an exception is raised if the CRC8 check value does not match."""
        expected = "Received bad header CRC from instrument"
        reply_string = self._create_byte_string(0x00, bytes([0x00]), bytes([189]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.reset()

        self.assertEqual(str(exc.exception)[:len(expected)], expected)

    def test_inconsistent_data_length_raises_exception(self):
        """See that an exception is raised if data length is inconsistent with the packet length."""
        expected = "Received invalid packet from instrument"
        reply_string = self._create_byte_string(0x04, bytes([0x00]))
        self._dev.read = unittest.mock.Mock()
        self._dev.read.side_effect = [UsbErrorMock, reply_string[:11]]
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.instr.reset()

        self.assertEqual(str(exc.exception)[:len(expected)], expected)


if __name__ == '__main__':
    unittest.main()
