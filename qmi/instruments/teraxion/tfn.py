"""
Instrument driver for TeraXion TFN.
"""

import binascii
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum
import logging
import struct
import time
from typing import Optional, Type, TypeVar
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
class Teraxion_TFNChannelPlan:
    """
    Channel plan of TFN.

    Attributes:
        first_frequency:    The first frequency in GHz.
        last_frequency:     The last frequency in GHz.
        num_cal_channels:   Number of calibrated channels.
    """

    first_frequency: float
    last_frequency: float
    num_cal_channels: int


@dataclass
class Teraxion_TFNCommand:
    """
    Base class for Teraxion TFN commands.
    """

    command_id: int
    num_received_bytes: Optional[int]
    module_address: int = 0x30


T = TypeVar('T', bound=Teraxion_TFNCommand)


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
    Command to get the startup byte of the TFN.
    """

    command_id = 0x35
    num_received_bytes = 5


class Teraxion_TFNCommand_SetStartupByte(Teraxion_TFNCommand):
    """
    Command to set the startup byte of the TFN.
    """

    command_id = 0x34
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
    num_received_bytes = 255


class Teraxion_TFNCommand_GetModelNumber(Teraxion_TFNCommand):
    """
    Command to get the model number.
    """

    command_id = 0x27
    num_received_bytes = 255


class Teraxion_TFNCommand_GetSerialNumber(Teraxion_TFNCommand):
    """
    Command to get the serial number.
    """

    command_id = 0x29
    num_received_bytes = 255


class Teraxion_TFNCommand_GetManufacturingDate(Teraxion_TFNCommand):
    """
    Command to get the manufacturing date.
    """

    command_id = 0x2B
    num_received_bytes = 255


class Teraxion_TFNCommand_GetNominalSettings(Teraxion_TFNCommand):
    """
    Command to get the nominal settings.
    """

    command_id = 0x37
    num_received_bytes = 12


class Teraxion_TFNCommand_SaveNominalSettings(Teraxion_TFNCommand):
    """
    Command to save the nominal settings.
    """

    command_id = 0x36
    num_received_bytes = 12


class Teraxion_TFNCommand_GetChannelPlan(Teraxion_TFNCommand):
    """
    Command to get the channel plan.
    """

    command_id = 0x3B
    num_received_bytes = 16


class Teraxion_TFNCommand_SetI2CAddress(Teraxion_TFNCommand):
    """
    Command to get the channel plan.
    """

    command_id = 0x42


class Teraxion_TFN(QMI_Instrument):
    """
    Instrument driver for TeraXion TFN. It uses serial communication.
    """

    DEFAULT_READ_TIMEOUT = 10  # default read timeout in seconds.

    # the start and stop conditions for the ascii commands.
    CMD_START_CONDITION = "S"
    CMD_STOP_CONDTION = "P"

    LEN_STATUS_BYTES = 4  # len of the status bytes.

    READ_WRITE_DELAY = 0x000A  # 10ms delay value between write and read command in hex.

    SOFTWARE_RESET_DELAY = 0.25  # delay after a software reset command in seconds.
    GET_PROCESS_TIME = 0.01  # GET requests usually have a process time of 10ms
    SET_PROCESS_TIME = 0.02  # SET requests usually have a process time of 20ms
    GET_LONG_PROCESS_TIME = 0.05  # Long GET requests that return 255 bytes of data usually have a process time of 50ms.

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 57600})
        self._scpi_protocol = ScpiProtocol(self._transport, command_terminator="")

    def _make_write_command(
        self,
        cmd: Type[T],
        value: Optional[bytes] = None
    ) -> str:
        """
        Helper method to make the write command.

        Parameters:
            cmd:        A Teraxion_TFNCommand.
            value:      The optional value to write in bytes.
        """
        # convert the value to its hex representation
        hex_val = binascii.hexlify(value).decode() if value else ""
        # shift module address by one and set the write bit
        write_mode = int(cmd.module_address) << 1
        # make write command and return
        return f"{self.CMD_START_CONDITION}{write_mode:02x}{cmd.command_id:02x}{hex_val}{self.CMD_STOP_CONDTION}"

    def _make_read_command(
        self,
        cmd: Type[T],
    ) -> str:
        """
        Helper method to make the read command.

        Parameters:
            cmd:        A Teraxion_TFNCommand.
        """
        # shift module address by one and set the read bit
        read_mode = cmd.module_address << 1 ^ 1
        # make read command and return
        return f"{self.CMD_START_CONDITION}{read_mode:02x}{cmd.num_received_bytes:02x}{self.CMD_STOP_CONDTION}"

    def _write(
        self,
        cmd: Type[T],
        value: Optional[bytes] = None,
        timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> None:
        """
        Helper method to send a wrie command.

        Parameters:
            cmd:    A Teraxion_TFNCommand.
            value:  The optional value to write in bytes.
            timeout:    The timeout for the command.
        """
        wc = self._make_write_command(cmd, value)
        rc = self._make_read_command(cmd)
        # ask for the reponse to clear the buffer
        _ = self._scpi_protocol.ask(f"{wc} L{self.READ_WRITE_DELAY:04x} {rc}", timeout=timeout)

    def _read(
        self,
        cmd: Type[T],
        value: Optional[bytes] = None,
        timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> bytes:
        """
        Helper method to send a read command.

        Parameters:
            cmd:        A Teraxion_TFNCommand.
            value:      The optional value to write in bytes.
            timeout:    The timeout for the command.
        """
        wc = self._make_write_command(cmd, value)
        rc = self._make_read_command(cmd)
        resp = self._scpi_protocol.ask(f"{wc} {rc}", timeout=timeout)
        # convert to hex representation
        return bytes.fromhex(resp)

    def _set_startup_byte(self, tec_status: bool) -> None:
        """
        Set the startup byte of the TFN.

        Parameters:
            tec_status: The status of the TECs on startup. True for all enable and False for all disabled.
        """
        _logger.info("Setting startup byte of instrument [%s]", self._name)
        self._check_is_open()
        # pack the element to a byte array
        val = struct.pack(">B", int(tec_status))
        # send command
        self._write(Teraxion_TFNCommand_SetStartupByte, val)
        time.sleep(self.SET_PROCESS_TIME)

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
        resp = self._read(Teraxion_TFNCommand_GetFirmwareVersion)
        time.sleep(self.GET_PROCESS_TIME)
        # get the data after the status bytes
        _, major_version, minor_version = struct.unpack(">IBB", resp)
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
        resp = self._read(Teraxion_TFNCommand_GetManufacturerName)
        time.sleep(self.GET_LONG_PROCESS_TIME)
        # get the data after the status bytes and ignore the null bytes
        manufacturer_name = resp[self.LEN_STATUS_BYTES:]
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
        resp = self._read(Teraxion_TFNCommand_GetModelNumber)
        time.sleep(self.GET_LONG_PROCESS_TIME)
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
        resp = self._read(Teraxion_TFNCommand_GetSerialNumber)
        time.sleep(self.GET_LONG_PROCESS_TIME)
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
    def get_manufacturing_date(self) -> date:
        """
        Get manufacturing date of the TFN.

        Returns:
            the manufacturing date.
        """
        _logger.info("[%s] Getting manufacturing date of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._read(Teraxion_TFNCommand_GetManufacturingDate)
        time.sleep(self.GET_LONG_PROCESS_TIME)
        # get the data after the status bytes and ignore the null bytes
        manufacturing_date = resp[self.LEN_STATUS_BYTES:]
        date_decoded = manufacturing_date.decode("ascii")[:manufacturing_date.find(b"\x00")]
        return datetime.strptime(date_decoded, "%Y%m%d").date()

    @rpc_method
    def get_status(self) -> Teraxion_TFNStatus:
        """
        Get status of the TFN.

        Returns:
            an instance of Teraxion_TFNStatus.
        """
        _logger.info("[%s] Getting status of instrument", self._name)
        self._check_is_open()
        # get response
        status = self._read(Teraxion_TFNCommand_GetStatus)
        time.sleep(self.GET_PROCESS_TIME)
        resp = struct.unpack(">L", status)[0]

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
        self._check_is_open()
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
        # pack the frequency to a byte array of 4 bytes
        freq = struct.pack(">f", frequency)
        # send command
        self._write(Teraxion_TFNCommand_SetFrequency, freq)
        time.sleep(self.GET_PROCESS_TIME)

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
        resp = self._read(Teraxion_TFNCommand_GetFrequency)
        time.sleep(self.GET_PROCESS_TIME)
        # unpack the frequency and return
        _, freq = struct.unpack(">If", resp)
        return freq

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
        # pack the element to a byte array of size 1
        el = struct.pack(">B", element.value)
        # get response
        resp = self._read(Teraxion_TFNCommand_GetRTDTemperature, el)
        # unpack the temperature and return
        _, temp = struct.unpack(">IH", resp)
        return temp

    @rpc_method
    def enable_device(self) -> None:
        """
        Enable the device and turn on TEC control.
        """
        _logger.info("[%s] Enabling instrument", self._name)
        self._check_is_open()
        # send command
        self._write(Teraxion_TFNCommand_EnableDevice)
        time.sleep(self.GET_PROCESS_TIME)

    @rpc_method
    def disable_device(self) -> None:
        """
        Disable the device and turn off TEC control.
        """
        _logger.info("[%s] Disabling instrument", self._name)
        self._check_is_open()
        # send command
        self._write(Teraxion_TFNCommand_DisableDevice)
        time.sleep(self.GET_PROCESS_TIME)

    @rpc_method
    def get_startup_byte(self) -> bool:
        """
        Get the startup byte of the TFN.

        Returns:
            The status of the TECs on startup. True for all enable and False for all disabled.
        """
        _logger.info("Getting startup byte of instrument [%s]", self._name)
        self._check_is_open()
        # get response
        resp = self._read(Teraxion_TFNCommand_GetStartupByte)
        time.sleep(self.GET_PROCESS_TIME)
        # unpack the startup byte and return
        _, startup_byte = struct.unpack(">IB", resp)
        return bool(startup_byte)

    @rpc_method
    def enable_tecs_on_startup(self) -> None:
        """
        Enable TECs on startup of TFN.
        """
        self._set_startup_byte(True)

    @rpc_method
    def disable_tecs_on_startup(self) -> None:
        """
        Disable TECs on startup of TFN.
        """
        self._set_startup_byte(False)

    @rpc_method
    def get_nominal_settings(self) -> Teraxion_TFNSettings:
        """
        Get nominal settings of the TFN.

        Returns:
            an instance of Teraxion_TFNSettings.
        """
        _logger.info("Getting frequency of instrument [%s]", self._name)
        self._check_is_open()
        # get response
        resp = self._read(Teraxion_TFNCommand_GetNominalSettings)
        time.sleep(self.GET_PROCESS_TIME)
        # unpack the frequency and dispersion
        _, freq, disp = struct.unpack(">Iff", resp)
        return Teraxion_TFNSettings(freq, disp)

    @rpc_method
    def save_nominal_settings(self) -> None:
        """
        Save nominal settings of the TFN. These settings are the current frequency and dispersion values.
        """
        _logger.info("[%s] Saving nominal settings of instrument", self._name)
        self._check_is_open()
        # send command
        self._write(Teraxion_TFNCommand_SaveNominalSettings)
        time.sleep(self.SET_PROCESS_TIME)

    @rpc_method
    def get_channel_plan(self) -> Teraxion_TFNChannelPlan:
        """
        Get channel plan for specified grid.

        Returns:
            an instance of Teraxion_TFNChannelPlan.
        """
        _logger.info("Getting channel plan of instrument [%s]", self._name)
        self._check_is_open()
        # get response
        resp = self._read(Teraxion_TFNCommand_GetChannelPlan)
        time.sleep(self.GET_PROCESS_TIME)
        # unpack the frequencies and number of calibrated channels
        _, first_freq, last_freq, num_cal_channels = struct.unpack(">IffL", resp)
        return Teraxion_TFNChannelPlan(first_freq, last_freq, num_cal_channels)

    @rpc_method
    def set_i2c_address(self, address: int) -> None:
        """
        Set the I2C address of the TFN module. This all will need a power cycle to take effect.
        
        Parameters:
            address:    New I2C address for module.
        """
        _logger.info("Setting I2C address of instrument [%s]", self._name)
        self._check_is_open()
        cmd = Teraxion_TFNCommand_SetI2CAddress
        # shift module address by one and set write bit
        write_mode = int(cmd.module_address) << 1
        # make write command and send
        wc = f"{self.CMD_START_CONDITION}{write_mode:02x}{cmd.command_id:02x}{address:04x}{self.CMD_STOP_CONDTION}"
        self._scpi_protocol.write(f"{wc}")
