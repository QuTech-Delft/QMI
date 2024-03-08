"""
Instrument driver for TeraXion TFN.
"""

import binascii
from dataclasses import dataclass
from enum import Enum
import logging
import struct
import time
from typing import Optional
from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Teraxion_TFNElement(Enum):
    """
    TeraXion TFN elements.
    """

    RTD1 = 0
    RTD2 = 1
    RTD3 = 2
    RTD4 = 3
    CASE = 4


@dataclass
class Teraxion_TFNStatus:
    """
    Status of TFN.
    """

    busy_error: bool
    overrun_error: bool
    command_error: bool
    tfn_active: bool
    tfn_ready: bool
    invalid_eeprom_error: bool
    tec_4_temp_limit: bool
    tec_3_temp_limit: bool
    tec_2_temp_limit: bool
    tec_1_temp_limit: bool
    tec_4_in_range: bool
    tec_3_in_range: bool
    tec_2_in_range: bool
    tec_1_in_range: bool

@dataclass
class Teraxion_TFNSettings:
    """
    Settings of TFN.

    Attributes:
        frequency:  The current frequency in GHz.
        dispersion: The dispersion in ps/nm.
    """

    frequency: float
    dispersion: float


@dataclass
class Teraxion_TFNCommand:
    """
    Base class for Teraxion TFN commands.
    """

    command_id: int
    num_received_bytes: Optional[int]
    num_sent_bytes: Optional[int]
    module_address: int = 0x30


class Teraxion_TFNCommand_GetStatus(Teraxion_TFNCommand):
    """
    Command to get the status of the TFN.
    """

    command_id = 0x00
    num_received_bytes = 4


class Teraxion_TFNCommand_Reset(Teraxion_TFNCommand):
    """
    Command to software reset the TFN.
    """

    command_id = 0x28


class Teraxion_TFNCommand_GetFrequency(Teraxion_TFNCommand):
    """
    Command to get the frequency.
    """

    command_id = 0x2F
    num_received_bytes = 8


class Teraxion_TFNCommand_SetFrequency(Teraxion_TFNCommand):
    """
    Command to set the frequency.
    """

    command_id = 0x2E
    num_received_bytes = 8


class Teraxion_TFNCommand_GetRTDTemperature(Teraxion_TFNCommand):
    """
    Command to get the RTD temperature.
    """

    command_id = 0x17
    num_received_bytes = 6

class Teraxion_TFNCommand_EnableDevice(Teraxion_TFNCommand):
    """
    Command to enable the TFN.
    """

    command_id = 0x1E
    num_received_bytes = 4

class Teraxion_TFNCommand_DisableDevice(Teraxion_TFNCommand):
    """
    Command to disable the TFN.
    """

    command_id = 0x1F
    num_received_bytes = 4

class Teraxion_TFNCommand_GetStartupByte(Teraxion_TFNCommand):
    """
    Command to set teh startup byte of the TFN.
    """

    command_id = 0x35
    num_received_bytes = 5

class Teraxion_TFNCommand_GetFirmwareVersion(Teraxion_TFNCommand):
    """
    Command to get the firmware version.
    """

    command_id = 0x0F
    num_received_bytes = 6

class Teraxion_TFNCommand_GetManufacturerName(Teraxion_TFNCommand):
    """
    Command to get the manufacturer name.
    """

    command_id = 0x0E
    num_received_bytes = 13

class Teraxion_TFNCommand_GetModelNumber(Teraxion_TFNCommand):
    """
    Command to get the model number.
    """

    command_id = 0x27
    num_received_bytes = 13

class Teraxion_TFNCommand_GetSerialNumber(Teraxion_TFNCommand):
    """
    Command to get the serial number.
    """

    command_id = 0x29
    num_received_bytes = 13

class Teraxion_TFNCommand_GetManufacturingDate(Teraxion_TFNCommand):
    """
    Command to get the manufacturing date.
    """

    command_id = 0x2B
    num_received_bytes = 13

class Teraxion_TFNCommand_GetNominalSettings(Teraxion_TFNCommand):
    """
    Command to get the nominal settings.
    """

    command_id = 0x37
    num_received_bytes = 12


class Teraxion_TFN(QMI_Instrument):
    """
    Instrument driver for TeraXion TFN. It uses serial communication.
    """

    DEFAULT_READ_TIMEOUT = 10  # default read timeout in seconds.

    # the start and stop conditions for the ascii commands.
    CMD_START_CONDITION = "S"
    CMD_STOP_CONDTION = "P"

    LEN_STATUS_BYTES = 4  # len of the status bytes.

    READ_WRITE_DELAY = 0x000A  # 10ms delay value between a write and read command in hex.

    SOFTWARE_RESET_DELAY = 0.25  # delay after a software reset command in seconds.

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": 57600}
        )
        self._scpi_protocol = ScpiProtocol(self._transport, command_terminator="")

    def _send(
        self,
        cmd: Teraxion_TFNCommand,
        value: Optional[bytes] = None,
        timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> Optional[bytes]:
        """
        Helper method to create a command and send it. If a response is provided then it is returned.
        This is usually for the read commands.

        Parameters:
            cmd:        A Teraxion_TFNCommand.
            value:      The optional value to write in bytes.
            timeout:    The timeout for the read commands.
        """
        # convert the value to its hex representation
        hex_val = binascii.hexlify(value).decode() if value else ""
        # shift module address by one and set the write bit
        module_write_mode = int(cmd.module_address) << 1
        # make write command
        wc = f"{self.CMD_START_CONDITION}{module_write_mode:02x}{cmd.command_id:02x}{hex_val}{self.CMD_STOP_CONDTION}"

        # shift module address by one and set the read bit
        module_read_mode = cmd.module_address << 1 ^ 1
        # make read command
        rc = f"{self.CMD_START_CONDITION}{module_read_mode:02x}{cmd.num_received_bytes:02d}{self.CMD_STOP_CONDTION}"

        if cmd.num_received_bytes:
            # send the 2 commands and return the response
            resp = self._scpi_protocol.ask(f"{wc} {rc}", timeout=timeout)
            # convert to hex reprensation
            return bytes.fromhex(resp)
        else:
            return self._scpi_protocol.write(f"{wc} L{self.READ_WRITE_DELAY:02x} {rc}")

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        self._check_is_open()
        self._transport.close()
        super().close()

    @rpc_method
    def get_firmware_version(self) -> str:
        """
        Get firmware version of the TFN.

        Returns:
            the firmware version.
        """
        _logger.info("[%s] Getting firmware version of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetFirmwareVersion)
        # get the data after the status bytes and ignore the null bytes
        firmware_version = resp[self.LEN_STATUS_BYTES :]
        major_version = struct.unpack(">B", firmware_version[:1])[0]
        minor_version = struct.unpack(">B", firmware_version[1:])[0]
        return f"{major_version}.{minor_version}"

    @rpc_method
    def get_manufacturer_name(self) -> str:
        """
        Get manufacturer name of the TFN.

        Returns:
            the name of the manufacturer.
        """
        _logger.info("[%s] Getting manufacturer name of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetManufacturerName)
        # get the data after the status bytes and ignore the null bytes
        manufacturer_name = resp[self.LEN_STATUS_BYTES:]
        print(manufacturer_name)
        return manufacturer_name.decode("ascii")[:manufacturer_name.find(b"\x00")]

    @rpc_method
    def get_model_number(self) -> str:
        """
        Get model number of the TFN.

        Returns:
            the model number.
        """
        _logger.info("[%s] Getting model number of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetModelNumber)
        # get the data after the status bytes and ignore the null bytes
        model_number = resp[self.LEN_STATUS_BYTES:]
        return model_number.decode("ascii")[:model_number.find(b"\x00")]

    @rpc_method
    def get_serial_number(self) -> str:
        """
        Get serial number of the TFN.

        Returns:
            the serial number.
        """
        _logger.info("[%s] Getting serial number of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetSerialNumber)
        # get the data after the status bytes and ignore the null bytes
        serial_number = resp[self.LEN_STATUS_BYTES:]
        return serial_number.decode("ascii")[:serial_number.find(b"\x00")]

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """
        Get instrument identification of the TFN.
        
        Returns:
            an instance of QMI_InstrumentIdentification.
        """
        _logger.info("[%s] Getting instrument identitification of instrument", self._name)
        self._check_is_open()
        return QMI_InstrumentIdentification(vendor=self.get_manufacturer_name(),
                                            model=self.get_model_number(),
                                            serial=self.get_serial_number(),
                                            version=self.get_firmware_version())

    @rpc_method
    def get_manufacturing_date(self) -> str:
        """
        Get manufacturing date of the TFN.

        Returns:
            the manufacturing date.
        """
        _logger.info("[%s] Getting manufacturing date of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetManufacturingDate)
        # get the data after the status bytes and ignore the null bytes
        date = resp[self.LEN_STATUS_BYTES:]
        return date.decode("ascii")[:date.find(b"\x00")]

    @rpc_method
    def get_status(self) -> str:
        """
        Get status of the TFN.

        Returns:
            an instance of Teraxion_TFNStatus.
        """
        _logger.info("[%s] Getting status of instrument", self._name)
        self._check_is_open()
        # get response
        resp = struct.unpack(">L", self._send(Teraxion_TFNCommand_GetStatus))[0]

        return Teraxion_TFNStatus(busy_error=           bool(resp & 0b00000000100000000000000000000000),
                                  overrun_error=        bool(resp & 0b00000000010000000000000000000000),
                                  command_error=        bool(resp & 0b00000000001000000000000000000000),
                                  tfn_active=           bool(resp & 0b00000000000100000000000000000000),
                                  tfn_ready=            bool(resp & 0b00000000000010000000000000000000),
                                  invalid_eeprom_error= bool(resp & 0b00000000000001000000000000000000),
                                  tec_4_temp_limit=     bool(resp & 0b00000000000000000000000010000000),
                                  tec_3_temp_limit=     bool(resp & 0b00000000000000000000000001000000),
                                  tec_2_temp_limit=     bool(resp & 0b00000000000000000000000000100000),
                                  tec_1_temp_limit=     bool(resp & 0b00000000000000000000000000010000),
                                  tec_4_in_range=       bool(resp & 0b00000000000000000000000000001000),
                                  tec_3_in_range=       bool(resp & 0b00000000000000000000000000000100),
                                  tec_2_in_range=       bool(resp & 0b00000000000000000000000000000010),
                                  tec_1_in_range=       bool(resp & 0b00000000000000000000000000000001))

    @rpc_method
    def reset(self) -> None:
        """
        Perform a software reset.
        """
        _logger.info("[%s] Software resetting instrument", self._name)
        cmd = Teraxion_TFNCommand_Reset
        # shift module address by one and set the write bit
        module_write_mode = int(cmd.module_address) << 1
        # make write command and send
        wc = f"{self.CMD_START_CONDITION}{module_write_mode:02x}{cmd.command_id:02x}{self.CMD_STOP_CONDTION}"
        self._scpi_protocol.write(f"{wc}")
        # sleep before exiting so new commands can be sent
        time.sleep(self.SOFTWARE_RESET_DELAY)

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """
        Set frequency setpoint of the TFN.

        Parameters:
            frequency:  The frequency setpoint in GHz.
        """
        _logger.info("[%s] Setting frequency of instrument to [%f]", self._name, frequency)
        self._check_is_open()
        # pack the frequency to a byte array
        freq = struct.pack(">f", frequency)
        # send command
        self._send(Teraxion_TFNCommand_SetFrequency, freq)

    @rpc_method
    def get_frequency(self) -> float:
        """
        Get frequency setpoint of the TFN.

        Returns:
            the frequency setpoint in GHz.
        """
        _logger.info("Getting frequency of instrument [%s]", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetFrequency)
        # unpack the frequency and return
        return struct.unpack(">f", resp[self.LEN_STATUS_BYTES :])[0]

    @rpc_method
    def get_rtd_temperature(self, element: Teraxion_TFNElement) -> int:
        """
        Get the RTD temperature of the provided element.

        Parameters:
            element: The element to get the temperature for.

        Returns:
            RTD temperature in hundreths of a degree Celcius.
        """
        _logger.info("[%s] Getting RTD temperature of %s", self._name, element.name)
        self._check_is_open()
        # pack the element to a byte array
        el = struct.pack(">B", element.value)
        # get response
        resp = self._send(Teraxion_TFNCommand_GetRTDTemperature, el)
        # unpack the temperature and return
        return struct.unpack(">H", resp[self.LEN_STATUS_BYTES :])[0]

    @rpc_method
    def enable_device(self) -> None:
        """
        Enable the device and turn on TEC control.
        """
        _logger.info("[%s] Enabling instrument", self._name)
        self._check_is_open()
        # send command
        self._send(Teraxion_TFNCommand_EnableDevice)

    @rpc_method
    def disable_device(self) -> None:
        """
        Disable the device and turn off TEC control.
        """
        _logger.info("[%s] Disabling instrument", self._name)
        self._check_is_open()
        # send command
        self._send(Teraxion_TFNCommand_DisableDevice)

    @rpc_method
    def get_startup_byte(self) -> bytes:
        """
        Get the startup byte of the TFN.

        Returns:
            the startup byte.
        """
        _logger.info("Getting startup byte of instrument [%s]", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetStartupByte)
        # unpack the startup byte and return
        return resp[self.LEN_STATUS_BYTES :]

    @rpc_method
    def get_nominal_settings(self) -> Teraxion_TFNSettings:
        """
        Get nomial settings of the TFN.

        Returns:
            an instance of Teraxion_TFNSettings.
        """
        _logger.info("Getting frequency of instrument [%s]", self._name)
        self._check_is_open()
        # get response
        resp = self._send(Teraxion_TFNCommand_GetNominalSettings)
        # unpack the frequency and dispersion
        freq = struct.unpack(">f", resp[self.LEN_STATUS_BYTES :self.LEN_STATUS_BYTES + 4])[0]
        disp = struct.unpack(">f", resp[self.LEN_STATUS_BYTES + 4 + 4 :self.LEN_STATUS_BYTES + 4 + 4 + 4])[0]
        return Teraxion_TFNSettings(freq, disp)