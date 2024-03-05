"""
Instrument driver for TeraXion TFN.
"""
import binascii
from dataclasses import dataclass
import logging
import struct
from typing import Optional
from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


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
class Teraxion_TFNCommand:
    """
    Base class for Teraxion TFN commands.
    """
    command_id: int
    num_received_bytes: int
    num_sent_bytes: Optional[int]
    module_address: int = 0x30


class Teraxion_TFNCommand_GetStatus(Teraxion_TFNCommand):
    """
    Command to get the status of the TFN.
    """
    command_id = 0x00
    num_received_bytes = 4


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


class Teraxion_TFNCommand_GetManufacturerName(Teraxion_TFNCommand):
    """
    Command to get the manufacturer name.
    """
    command_id = 0x0E
    num_received_bytes = 13


class Teraxion_TFN(QMI_Instrument):
    """
    Instrument driver for TeraXion TFN. It uses serial communication.
    """
    DEFAULT_READ_TIMEOUT = 10  # default read timeout in seconds

    # the start and stop conditions for the ascii commands.
    CMD_START_CONDITION = "S"
    CMD_STOP_CONDTION = "P"

    LEN_STATUS_BYTES = 4  # len of the status bytes

    READ_WRITE_DELAY = 0x000A  # 10 msdelay value between a write and read command in hex

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": 57600})
        self._scpi_protocol = ScpiProtocol(
            self._transport, command_terminator="")

    def _hex_to_str(self, hex_val: int) -> str:
        """
        Helper method to convert a hex value into string. This is a not a conversion from hex to int to string,
        rather a conversion from hex to string. For example 0x60 is converter to '60' and not '96' which is the
        integer representatin of 0x60.

        Parameters:
            hex_val:    The hexadecimal value to convert to a string.

        Returns:
            The string representation of the hex value.
        """
        return f"{hex_val:02x}"

    def _read(self, cmd: Teraxion_TFNCommand, timeout: float = DEFAULT_READ_TIMEOUT) -> bytes:
        """
        Helper method to create a read command and send it and then retrieve the result.

        Parameters:
            cmd: A Teraxion_TFNCommand.
        """
        # shift module address by one and set the write bit
        module_write_mode = int(cmd.module_address) << 1
        # make write command
        write_command = f"{self.CMD_START_CONDITION}{self._hex_to_str(module_write_mode)}{self._hex_to_str(cmd.command_id)}{self.CMD_STOP_CONDTION}"

        # shift module address by one and set the read bit
        module_read_mode = cmd.module_address << 1 ^ 1
        # make read command
        read_command = f"{self.CMD_START_CONDITION}{self._hex_to_str(module_read_mode)}{cmd.num_received_bytes:02d}{self.CMD_STOP_CONDTION}"

        # send the 2 commands and return the response
        resp = self._scpi_protocol.ask(
            f"{write_command} {read_command}", timeout=timeout)

        # convert to hex reprensation
        return bytes.fromhex(resp)

    def _write(self, cmd: Teraxion_TFNCommand, value: bytes) -> None:
        """
        Helper method to create a write command and send it.

        Parameters:
            cmd:    A Teraxion_TFNCommand.
            value:  The value to write in bytes.
        """
        # convert the value to its hex representation
        hex_val = binascii.hexlify(value).decode()
        # shift module address by one and set the write bit
        module_write_mode = int(cmd.module_address) << 1
        # make write command
        write_command = f"{self.CMD_START_CONDITION}{self._hex_to_str(module_write_mode)}{self._hex_to_str(cmd.command_id)}{hex_val}{self.CMD_STOP_CONDTION}"

        # shift module address by one and set the read bit
        module_read_mode = cmd.module_address << 1 ^ 1
        # make read command
        read_command = f"{self.CMD_START_CONDITION}{self._hex_to_str(module_read_mode)}{cmd.num_received_bytes:02d}{self.CMD_STOP_CONDTION}"

        self._scpi_protocol.write(
            f"{write_command} L{self._hex_to_str(self.READ_WRITE_DELAY)} {read_command}")

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
    def get_status(self) -> str:
        """
        Get status of the TFN.

        Returns:
            an instance of Teraxion_TFNStatus.
        """
        _logger.info("[%s] Getting status of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._read(Teraxion_TFNCommand_GetStatus)
        # get binary string
        resp_bin = ''.join(format(b, '08b') for b in resp)
        return resp_bin

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """
        Set frequency setpoint of the TFN.

        Parameters:
            frequency:  The frequency setpoint in GHz.
        """
        _logger.info(
            "[%s] Setting frequency of instrument to [%f]", self._name, frequency)
        self._check_is_open()
        # pack the frequency to a byte array
        freq = struct.pack('>f', frequency)
        # send command
        self._write(Teraxion_TFNCommand_SetFrequency, freq)

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
        # unpack the frequency and return
        freq = struct.unpack('>f', resp[self.LEN_STATUS_BYTES:])[0]
        return freq

    @rpc_method
    def get_manufacturer_name(self) -> str:
        """
        Get manufacturer name of the TFN.

        Returns:
            the name of the manufacturer.
        """
        _logger.info(
            "[%s] Getting manufacturer name of instrument", self._name)
        self._check_is_open()
        # get response
        resp = self._read(Teraxion_TFNCommand_GetManufacturerName)
        # get the data after the status bytes and ignore the null bytes
        manufacturer_name = resp[self.LEN_STATUS_BYTES:]
        return manufacturer_name.decode('ascii')[:manufacturer_name.find(b'\x00')]
