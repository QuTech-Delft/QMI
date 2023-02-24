"""
Instrument driver for the Thorlabs TSP01 RevB temperature/humidity sensor.

The Thorlabs TSP01 RevB is not compatible with the original Thorlabs TSP01.
The two instruments have different USB IDs and use different protocols.

This driver supports only the TSP01 RevB (also called TSP01B).
New devices sold by Thorlabs after 2018 are RevB devices.

The TSP01 RevB uses a binary protocol on top of USB-HID.
This driver is based on partial reverse-engineering of the binary protocol.

This driver uses PyUSB and libusb to access the instrument,
and is therefore expected to work only under Linux.
"""

import binascii
import logging
import struct
from typing import List, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class _Thorlabs_TSP01B_libusb:
    """Exchange binary data packets with the TSP01 RevB sensor via USB HID."""

    # USB vendor ID and product ID of the TSP01 RevB sensor.
    VENDOR_ID = 0x1313
    PRODUCT_ID = 0x80fa

    # Always send/receive packets of 32 bytes.
    PACKET_SIZE = 32

    # Default request timeout (seconds).
    DEFAULT_TIMEOUT = 2.0

    @classmethod
    def list_instruments(cls) -> List[str]:
        """Return serial numbers of attached TSP01 RevB sensors."""

        import usb.core

        instruments = []
        devs = usb.core.find(find_all=True, idVendor=cls.VENDOR_ID, idProduct=cls.PRODUCT_ID)
        for dev in devs:
            try:
                if (dev.manufacturer == "Thorlabs") and (dev.product == "TSP01B"):
                    instruments.append(dev.serial_number)
            except Exception:
                # This happens if the user does not have permission
                # to open the USB device node /dev/usb/<bus>/<addr>.
                _logger.warning("Warning: Can not read USB serial_number")
                continue

        return instruments

    def __init__(self, serial_number: str) -> None:
        """Connect to the instrument.

        Read/write permission to the USB device node is required
        to access the instrument. This is typically accomplished on Linux
        by adding a suitable rule in ``/etc/udev/rules.d``.

        Parameters:
            serial_number: USB serial number of the device to open.

        Raises:
            QMI_InstrumentException: When the specified instrument is not found.
            USBError: If an error occurs at the USB level.
        """

        import usb.core
        import usb.util

        self.timeout = self.DEFAULT_TIMEOUT

        self._dev = usb.core.find(find_all=False,
                                  idVendor=self.VENDOR_ID,
                                  idProduct=self.PRODUCT_ID,
                                  serial_number=serial_number)
        if self._dev is None:
            raise QMI_InstrumentException("Instrument with serial number {} not found (check device permission)"
                                          .format(serial_number))

        # Read current configuration.
        cfg = self._dev.get_active_configuration()

        # Find the HID interface.
        hid_interface = None
        for interface in cfg.interfaces():
            if interface.bInterfaceClass == usb.CLASS_HID:
                hid_interface = interface
                break
        if hid_interface is None:
            raise QMI_InstrumentException("Instrument does not have a HID interface")
        self._hid_interface = hid_interface.index

        # Find the interrupt endpoints.
        endpoint_in = None
        endpoint_out = None
        for endpoint in hid_interface.endpoints():
            if usb.util.endpoint_type(endpoint.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR:
                if ((endpoint_in is None)
                        and (usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN)):
                    endpoint_in = endpoint.bEndpointAddress
                if ((endpoint_out is None)
                        and (usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_OUT)):
                    endpoint_out = endpoint.bEndpointAddress
        if endpoint_in is None:
            raise QMI_InstrumentException("Instrument does not have Interrupt IN endpoint")
        if endpoint_out is None:
            raise QMI_InstrumentException("Instrument does not have Interrupt OUT endpoint")
        self._endpoint_in = endpoint_in
        self._endpoint_out = endpoint_out

        # Detach kernel driver.
        driver_active = self._dev.is_kernel_driver_active(hid_interface.index)
        if driver_active:
            self._dev.detach_kernel_driver(hid_interface.index)

        # Claim the interface.
        usb.util.claim_interface(self._dev, hid_interface.index)

    def close(self) -> None:
        """Release the USB device.

        This object instance must not be used after calling ``close()``.
        """

        import usb.util

        if self._dev is not None:
            usb.util.dispose_resources(self._dev)
        self._dev = None

    def get_feature_report(self) -> bytes:
        """Send USB HID Get Feature Report request and return binary response data."""
        bmRequestType = 0xa1    # interface request
        bRequest = 0x01         # Get Report
        wValue = 0x0300         # Feature Report
        wIndex = self._hid_interface
        wLength = 32
        timeout = int(1000 * self.timeout)
        data = self._dev.ctrl_transfer(bmRequestType,
                                       bRequest,
                                       wValue,
                                       wIndex,
                                       wLength,
                                       timeout)
        return data

    def write_data(self, data: bytes) -> None:
        """Send binary data to the device via USB HID.

        Parameters:
            data: Data to send. This must be a packet of 32 raw bytes.
        """
        timeout = int(1000 * self.timeout)
        self._dev.write(self._endpoint_out, data, timeout)

    def read_data(self) -> bytes:
        """Read binary data from the instrument via USB HID.

        Returns:
            Raw bytes received from the instrument.
        """
        timeout = int(1000 * self.timeout)
        data = self._dev.read(self._endpoint_in, self.PACKET_SIZE, timeout)
        return bytes(data)

    def flush_read(self) -> None:
        """Read any old (pending) replies from the instrument."""

        import usb.core

        # Read until timeout.
        flush_timeout = 0.5
        while True:
            try:
                timeout = int(1000 * flush_timeout)
                _data = self._dev.read(self._endpoint_in, self.PACKET_SIZE, timeout)
            except usb.core.USBError:
                break


class Thorlabs_TSP01B(QMI_Instrument):
    """Instrument driver for the Thorlabs TSP01 RevB temperature/humidity sensor.

    The TSP01 RevB measures temperature and humidity.
    Up to two external temperature probes can be connected to the instrument
    to measure two additional temperature channels.

    The Thorlabs TSP01 RevB is not compatible with the original Thorlabs TSP01.
    This driver supports only the TSP01 RevB (also called TSP01B).
    """

    # Constants for internal use.
    _CHANNEL_TEMPERATURE = 0x00
    _CHANNEL_HUMIDITY = 0x01
    _CHANNEL_EXTERNAL = 0x02

    @staticmethod
    def list_instruments() -> List[str]:
        """Return a list of serial numbers of attached TSP01 RevB instruments."""
        return _Thorlabs_TSP01B_libusb.list_instruments()

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 serial_number: str
                 ) -> None:
        """Initialize the instrument driver.

        Read/write permission to the USB device node is required
        to access the instrument. This is typically accomplished on Linux
        by adding a suitable rule in ``/etc/udev/rules.d``.

        Parameters:
            name: Name for this instrument instance.
            serial_number: USB serial number of the instrument.
        """
        super().__init__(context, name)
        self._serial_number = serial_number
        self._instr: Optional[_Thorlabs_TSP01B_libusb] = None

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        instr = _Thorlabs_TSP01B_libusb(self._serial_number)
        try:
            instr.get_feature_report()
            instr.flush_read()
        except Exception:
            instr.close()
            raise
        self._instr = instr
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        self._check_is_open()
        assert self._instr is not None
        self._instr.close()
        self._instr = None
        super().close()

    @staticmethod
    def _bytes_to_hex(data: bytes) -> str:
        """Convert a byte string to hexadecimal representation.

        This is used to report error messages in case of protocol errors.
        """
        return " ".join(["{:02x}".format(b) for b in data])

    @staticmethod
    def _crc8(data: bytes) -> int:
        """Calculate an 8-bit CRC as used by the TSP01B binary protocol."""
        polynomial = 0x2F
        crc = 0x00
        for b in data:
            crc ^= b
            for i in range(8):
                if crc & 0x80:
                    crc = ((crc & 0x7f) << 1) ^ polynomial
                else:
                    crc = (crc << 1)
        return crc

    @classmethod
    def _format_packet(cls, par1: int, data: bytes) -> bytes:
        """Prepare a binary packet to send to the TSP01B.

        Parameters:
            par1: Command byte.
            data: Optional payload bytes.

        Returns:
            Binary packet of length 32 bytes.
        """

        # Packet format (32 bytes length):
        #   byte 0: fixed byte 0xF0
        #   byte 1: data length
        #   byte 2: fixed byte 0x00
        #   byte 3: fixed byte 0x01
        #   byte 4: command code
        #   byte 5: CRC-8 over first 5 bytes
        #   byte 6: fixed byte 0xF1
        #   starting at byte 7: variable length data (may be empty)
        #   following data: 4 bytes CRC-32 over data (excluding the 0xF1 marker)
        #   padding with 0x00 until total length 32 bytes

        packet_size = 32
        assert 11 + len(data) <= packet_size

        # Prepare header and CRC-8.
        header = bytes([0xF0, len(data), 0x00, 0x01, par1])
        header_crc = cls._crc8(header)

        # Calculate CRC-32 over data.
        data_crc = struct.pack("<I", binascii.crc32(data))

        # Add zero-padding until 32 bytes total length.
        padding = bytes((packet_size - 11 - len(data)) * [0x00])

        # Format final packet.
        packet = header + bytes([header_crc, 0xF1]) + data + data_crc + padding
        return packet

    @classmethod
    def _parse_packet(cls, packet: bytes) -> Tuple[int, bytes]:
        """Decode a binary packet received from the TSP01B.

        Parameters:
            packet: Binary data received from TSP01B.

        Returns:
            Tuple (reply_code, reply_payload).
        """

        # Packet format (32 bytes length):
        #   byte 0: fixed byte 0xF0
        #   byte 1: data length
        #   byte 2: fixed byte 0x00
        #   byte 3: fixed byte 0x01
        #   byte 4: reply code
        #   byte 5: CRC-8 over first 5 bytes
        #   byte 6: fixed byte 0xF1
        #   starting at byte 7: variable length data (may be empty)
        #   following data: 4 bytes CRC-32 over data (excluding the 0xF1 marker)
        #   padding with 0x00 until total length 32 bytes

        # Check minimum packet length.
        if len(packet) < 11:
            raise QMI_InstrumentException(
                "Received short packet from instrument ({})".format(cls._bytes_to_hex(packet)))

        # Check the fixed byte values.
        if (packet[0] != 0xF0) or (packet[6] != 0xF1):
            raise QMI_InstrumentException(
                "Received invalid packet from instrument ({})".format(cls._bytes_to_hex(packet)))

        # Verify the header CRC.
        header_crc = cls._crc8(packet[:5])
        if packet[5] != header_crc:
            raise QMI_InstrumentException(
                "Received bad header CRC from instrument ({})".format(cls._bytes_to_hex(packet)))

        # Check that the data length is consistent with the packet length.
        data_len = packet[1]
        if len(packet) < 11 + data_len:
            raise QMI_InstrumentException(
                "Received invalid packet from instrument ({})".format(cls._bytes_to_hex(packet)))

        # Extract reply code and payload data.
        par1 = packet[4]
        data = packet[7:7+data_len]

        # Verify the data CRC.
        data_crc = struct.pack("<I", binascii.crc32(data))
        if packet[7+data_len:11+data_len] != data_crc:
            raise QMI_InstrumentException(
                "Received bad data CRC from instrument ({})".format(cls._bytes_to_hex(packet)))

        return (par1, data)

    def _query_instrument(self, par1: int, data: bytes) -> Tuple[int, bytes]:
        """Send a query to the instrument and return the response data.

        Parameters:
            par1: Command byte.
            data: Optional payload bytes.

        Returns:
            Tuple (reply_code, reply_payload).
        """
        assert self._instr is not None

        # Send query.
        query_packet = self._format_packet(par1, data)
        self._instr.write_data(query_packet)

        # Receive reply.
        # Typically the instrument sends one dummy reply before sending
        # the actual reply to the command. Dummy replies can be recognized
        # by reply code 0x01 and empty data.
        while True:
            reply = self._instr.read_data()
            (reply_par, reply_data) = self._parse_packet(reply)
            # Skip dummy replies until we receive a non-dummy reply.
            if (reply_par != 0x01) or (len(reply_data) != 0):
                break

        # Send dummy command.
        # The purpose of this dummy command is not known.
        dummy_packet = self._format_packet(0x01, bytes())
        self._instr.write_data(dummy_packet)

        return (reply_par, reply_data)

    def _query_device_info(self, info_type: int) -> str:
        """Query device information.

        Parameters:
            info_type: Device information type code.

        Returns:
            Information string returned by instrument.
        """

        # Send query: command = 0x04, payload data = 1 byte [info_type].
        (reply_par, reply_data) = self._query_instrument(0x04, bytes([info_type]))

        # Expect reply code 0x04, payload data = [info_type] followed by string data.
        if (reply_par != 0x04) or (len(reply_data) < 1) or (reply_data[0] != info_type):
            raise QMI_InstrumentException("Unexpected reply to device info query ({:02x}, {})"
                                          .format(reply_par, self._bytes_to_hex(reply_data)))

        # Find end of string data.
        endpos = reply_data.find(0, 1)
        if endpos <= 0:
            endpos = len(reply_data)
        info_bytes = reply_data[1:endpos]

        # Convert ASCII bytes to string.
        return info_bytes.decode("latin1")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        device_info_manufacturer_name = 0x03
        device_info_product_name = 0x02
        device_info_serial_number = 0x04
        device_info_firmware_revision = 0x01
        vendor = self._query_device_info(device_info_manufacturer_name)
        model = self._query_device_info(device_info_product_name)
        serial = self._query_device_info(device_info_serial_number)
        version = self._query_device_info(device_info_firmware_revision)
        return QMI_InstrumentIdentification(vendor, model, serial, version)

    @rpc_method
    def reset(self):
        """Reset the instrument."""
        self._check_is_open()
        (reply_par, reply_data) = self._query_instrument(0x04, bytes([0x00]))
        if (reply_par != 0x04) or (reply_data != bytes([0x00])):
            raise QMI_InstrumentException("Unexpected reply to reset command ({:02x}, {})"
                                          .format(reply_par, self._bytes_to_hex(reply_data)))

    def _query_measurement(self, channel: int, ext_channel: int = 0) -> float:
        """Send a measurement query and return the measured value.

        Parameters:
            channel: Channel to measure (one of the `_CHANNEL_xxx` constants).
            ext_channel: Optional external channel selection in case of `_CHANNEL_EXTERNAL` (value 0 or 1).

        Returns:
            Measured value.

        Raises:
            QMI_InstrumentException: If the selected external sensor is not connected.
        """
        assert channel in (self._CHANNEL_TEMPERATURE,
                           self._CHANNEL_HUMIDITY,
                           self._CHANNEL_EXTERNAL)

        # Send query.
        if channel == self._CHANNEL_EXTERNAL:
            query_data = bytes([channel, ext_channel])
        else:
            query_data = bytes([channel])
        (reply_par, reply_data) = self._query_instrument(0x07, query_data)

        # The instrument returns the result as a 32-bit, little-endian floating point number.
        # A specific error code is returned if the external sensor is not connected.
        if (reply_par == 0x13) and (reply_data == bytes([0x03, 0x02, 0x24, 0x00])):
            raise QMI_InstrumentException("Sensor not connected")
        if (reply_par != 0x07) or (len(reply_data) != 5) or (reply_data[0] != channel):
            raise QMI_InstrumentException("Unexpected reply to measurement query ({:02x}, {})"
                                          .format(reply_par, self._bytes_to_hex(reply_data)))
        (value,) = struct.unpack("<f", reply_data[1:5])
        return value

    @rpc_method
    def get_humidity(self) -> float:
        """Perform a humidity measurement.

        Returns:
            Relative humidity as a percentage (range 0 to 100).
        """
        self._check_is_open()
        return self._query_measurement(self._CHANNEL_HUMIDITY)

    @rpc_method
    def get_internal_temperature(self) -> float:
        """Measure the temperature of the internal sensor.

        Returns:
            Temperature in Celsius.
        """
        self._check_is_open()
        return self._query_measurement(self._CHANNEL_TEMPERATURE)

    @rpc_method
    def get_external_temperature(self, ext_channel: int) -> float:
        """Measure the temperature of an external sensor.

        Parameters:
            ext_channel: External sensor channel number (1 or 2).

        Returns:
            Temperature in Celsius.
        """
        if ext_channel not in (1, 2):
            raise ValueError("Unsupported external channel number")
        self._check_is_open()
        return self._query_measurement(self._CHANNEL_EXTERNAL, ext_channel - 1)
