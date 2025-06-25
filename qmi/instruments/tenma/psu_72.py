"""Instrument driver for the Tenma 72-series power supply units.

Two main model groups in this series are the models similar to 2550 (selected as one base class) and
models similar to 13350 (selected also as a base class). Both groups work with USB-to-serial communication
but the second group has also possibility to use UDP communication. For that IP LAN communication protocol
with related functionalities is present, which can be used either through USB or UDP connection.

Some differences are present, even though the basis is the same, as implemented in the Tenma72_Base class:
- The group based on 13350 model require an EOL character (`\n`, `\r`) to finish the commands while group
  based on 2550 model doesn't.
- The group based on 13350 model does not work when providing the channel number to the serial command, while
  the commands in group based on 2550 model they do.
- For example, a command "ISET1:3.0" works for 2550 group, while "ISET:3.0\n" works for 13350 group.
"""
from dataclasses import dataclass
from enum import Enum
import logging
import re
from time import sleep
from typing import Any

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class TenmaChannelMode:
    value: bool
    name: str = "C.C"

    def __post_init__(self):
        if self.value:
            self.name = "C.V"


class TrackingState(Enum):
    INDEPENDENT = 0
    TRACKING_SERIES = 1
    TRACKING_PARALLEL = 2
    UNKNOWN = 99999

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


class Tenma72_Base(QMI_Instrument):
    """The base class for all Tenma model 72 power supply units.

    Attributes:
        BUFFER_SIZE:      The default buffer size for 'read'
        DEFAULT_BAUDRATE: The default baudrate in case of serial connection is used (Baud).
        MAX_VOLTAGE:      The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT:      The maximum current that can be set with the PSU (Amperes).
        SEND_SLEEP_TIME:  A default sleep time for sending data.
        READ_TIMEOUT:     A default timeout for reading data.
    """
    BUFFER_SIZE = 50
    DEFAULT_BAUDRATE = 0
    MAX_VOLTAGE = 0
    MAX_CURRENT = 0
    SEND_SLEEP_TIME = 0.02
    READ_TIMEOUT = 0.2

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        if transport.startswith("serial"):
            self._transport = create_transport(
                transport, default_attributes={"baudrate": self.DEFAULT_BAUDRATE}
            )
        elif transport.startswith("udp"):
            self._transport = create_transport(transport)
        else:
            raise QMI_InstrumentException(f"Transport type {transport} not valid!")

    def _send(self, cmd: str) -> None:
        """Writes a command to the Tenma, just an ascii string

        Parameters:
            cmd: The command to write to the device.
        """
        _logger.info("[%s] Sending message %s", self._name, cmd)
        self._transport.write(bytes(cmd, "ascii"))
        sleep(self.SEND_SLEEP_TIME)  # Sleep some bits to let the message arrive

    def _read(self) -> str:
        """Read the response from the device, try until response received or time-out.

        Returns:
            response: Decoded response string.
        """
        response = self._transport.read_until_timeout(self.BUFFER_SIZE, self.READ_TIMEOUT)
        _logger.info("[%s] Read message %s", self._name, response)
        return response.decode('ascii')

    def _enable_output(self, output: bool, command: str) -> None:
        """Internal function to further communicate the output state to instrument.

        Parameters:
            output:  The expected output state.
            command: The enable command string.
        """
        self._send(command)
        status = self.get_status()
        if status["OutputEnabled"] is not output:
            _logger.exception(
                "[%s] Tried to set output with %s but got %s", self._name, command, status["OutputEnabled"]
            )
            raise QMI_InstrumentException("Setting output failed for an unknown reason")

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Get instrument identification info.

        Returns:
            QMI_InstrumentIdentification: NamedTuple with vendor, model, serial number and SW version info.
        """
        self._send("*IDN?")
        idn = self._read()
        # Find all relevant info from response. Should be of format TENMA 72-2535 SN:1231345 V2.0
        pattern = re.compile(r'(\b\w+\b[^ ]*|\b72[^ ]*|V[^ ]*|SN:[^ ]*)')

        # Find all matches in the input string
        matches = pattern.findall(idn)

        # Extract the relevant parts from the matches
        vendor = matches[0] if matches else None
        model = next((match for match in matches[1:] if match.startswith('72')), None)
        version = next((match for match in matches[1:] if match.startswith('V')), None)
        serial = next((match for match in matches[1:] if match.startswith('SN:')), None)

        if None in (vendor, model, version, serial):
            _logger.debug("[%s] *IDN? returned %s and matching failed", self._name, idn)
            raise QMI_InstrumentException("(Full) instrument identification failed!")

        assert serial is not None  # For satisfying a mypy check
        return QMI_InstrumentIdentification(
            vendor=vendor,
            model=model,
            serial=serial.strip()[3:],
            version=version
        )

    @rpc_method
    def get_status(self) -> dict[str, Any]:
        """This method needs to be implemented in the inheriting classes."""
        raise NotImplementedError()

    @rpc_method
    def get_current(self, output_channel: int | None = None) -> float:
        """Get the current setting.

        Parameters:
            output_channel: The channel to send the inquiry to.

        Returns:
            Current setting of the channel in Amperes.
        """
        ch = output_channel or ""
        command = f"ISET{ch}?"
        self._send(command)
        # Response has appended sixth byte from *IDN? to voltage reading due to a firmware bug
        return float(self._read()[:5])

    @rpc_method
    def set_current(self, current: float, output_channel: int | None = None) -> None:
        """Set the current setting.

        Parameters:
            current:        Current for the channel in Amperes.
            output_channel: The channel to send the inquiry to.

        Raises:
            ValueError:     If the current setting is not between 0 and self.MAX_CURRENT.
        """
        if not 0 <= current <= self.MAX_CURRENT:
            raise ValueError(f"Invalid current setting {current}, not between 0 and {self.MAX_CURRENT} A")

        ch = output_channel or ""
        command = f"ISET{ch}:{current:.3f}"
        self._send(command)

    @rpc_method
    def get_voltage(self, output_channel: int | None = None) -> float:
        """Get the voltage setting.

        Parameters:
            output_channel: The channel to send the inquiry to.

        Returns:
            Voltage setting of the channel in Volts.
        """
        ch = output_channel or ""
        command = f"VSET{ch}?"
        self._send(command)
        return float(self._read())

    @rpc_method
    def set_voltage(self, voltage: float, output_channel: int | None = None) -> None:
        """Set the voltage setting.

        Parameters:
            voltage:        Voltage setting for the channel in Volts.
            output_channel: The channel to send the inquiry to.

        Raises:
            ValueError:     If the input voltage setting is not between 0 and self.MAX_VOLTAGE.
        """
        if not 0 <= voltage <= self.MAX_VOLTAGE:
            raise ValueError(f"Invalid current setting {voltage}, not between 0 and {self.MAX_VOLTAGE} V")

        ch = output_channel or ""
        command = f"VSET{ch}:{voltage:.3f}"
        self._send(command)

    @rpc_method
    def enable_output(self, output: bool) -> None:
        """Enable or disable output from the PSU.

        Parameters:
            output: Boolean value to either set output ON (True) or OFF (False).
        """
        raise NotImplementedError()


class Tenma72_2550(Tenma72_Base):
    """Instrument driver for the Tenma 72-2550. The driver is tested with this model, but the respective
    manual is also for models 72-2535, 72-2540, 72-2545, 72-2925, 72-2930, 72-2935, 72-2940 & 72-10480.

    This driver can be used only with (USB-to-)serial communications.

    Attributes:
        DEFAULT_BAUDRATE: The default baudrate in case of serial connection is used (Baud).
        MAX_VOLTAGE:      The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT:      The maximum current that can be set with the PSU (Amperes).
    """
    DEFAULT_BAUDRATE = 9600
    MAX_VOLTAGE = 60
    MAX_CURRENT = 3

    @rpc_method
    def get_status(self) -> dict[str, Any]:
        """Get the power supply status as a dictionary of status values.

        Dictionary composition is:
            Ch1Mode:       "C.V" | "C.C"
            Ch2Mode:       "C.V" | "C.C"
            Tracking:      xx, where xx is byte
                             * 00 = Independent
                             * 01 = Tracking series
                             * 10 = Tracking parallel
            OutputEnabled: True | False
        
        Returns: 
            Dictionary of status values.
        """
        self._send("STATUS?")
        statusByte = ord(self._transport.read(1, 1))  # Read response byte
        ch1mode = bool(statusByte & 0x01)
        ch2mode = bool(statusByte & 0x02)
        tracking = TrackingState((statusByte & 0x0C) >> 2)
        output_enabled = statusByte & 0x40

        return {
            "Ch1Mode": TenmaChannelMode(ch1mode).name,
            "Ch2Mode": TenmaChannelMode(ch2mode).name,
            "Tracking": tracking.name.replace("_", " ").title(),
            "OutputEnabled": bool(output_enabled),
        }

    @rpc_method
    def enable_output(self, output: bool) -> None:
        command = f"OUT{int(output)}"
        self._enable_output(output, command)


class Tenma72_2535(Tenma72_2550):
    """Instrument driver for the Tenma 72-2535, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 3


class Tenma72_2540(Tenma72_2550):
    """Instrument driver for the Tenma 72-2540, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 5


class Tenma72_2545(Tenma72_2550):
    """Instrument driver for the Tenma 72-2545, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 60
    MAX_CURRENT = 2


class Tenma72_2925(Tenma72_2550):
    """Instrument driver for the Tenma 72-2925, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 5


class Tenma72_2930(Tenma72_2550):
    """Instrument driver for the Tenma 72-2930, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 10


class Tenma72_2935(Tenma72_2550):
    """Instrument driver for the Tenma 72-2935, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 60
    MAX_CURRENT = 5


class Tenma72_2940(Tenma72_2550):
    """Instrument driver for the Tenma 72-2940, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 60
    MAX_CURRENT = 5


class Tenma72_10480(Tenma72_2550):
    """Instrument driver for the Tenma 72-10480, child of 72-2550.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 3


class Tenma72_13350(Tenma72_Base):
    """Instrument driver for the Tenma 72-13350. The driver is tested with this model, but manual is
    also for the model 72-13360.

    This driver can be used with (USB-to-)serial and UDP communications.

    Note that this model has extra functionalities related to the IP LAN Communication Protocol.
    Also note that this model does not work with channel number input, like 2550 model-based PSUs.
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 30
    DEFAULT_BAUDRATE = 115200

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name, transport)
        self.serial_eol = "\n"

    def _send(self, cmd: str) -> None:
        cmd = cmd + self.serial_eol
        return super()._send(cmd)

    @rpc_method
    def get_status(self) -> dict[str, Any]:
        """Get the power supply status as a dictionary of status values.

        Dictionary composition is:
            "ChannelMode ":  "C.V" | "C.C"
            "OutputEnabled": True | False
            "V/C priority ": "Current priority" | "Voltage priority"
            "Beep":          True | False
            "Lock":          True | False

        Returns:
            Dictionary of status values.
        """
        self._send("STATUS?")
        status_bytes = self._transport.read(2, 2)  # Read response byte
        # 72-13350 sends two bytes back, the second being '\n'
        status = status_bytes[0]

        ch1mode = bool(status & 0x01)
        output_enabled = bool(status & 0x02)
        current_priority = status & 0x04
        beep = bool(status & 0x10)
        lock = bool(status & 0x20)

        return {
            "ChannelMode": TenmaChannelMode(ch1mode).name,
            "OutputEnabled": output_enabled,
            "V/C priority": "Current priority" if current_priority else "Voltage priority",
            "Beep": beep,
            "Lock": lock,
        }

    @rpc_method
    def enable_output(self, output: bool) -> None:
        command = f"OUT:{int(output)}"
        self._enable_output(output, command)

    @rpc_method
    def get_dhcp(self) -> int:
        """Use the IP LAN command to see if DHCP is enabled.

        Returns:
            dhcp: The current DHCP enabled state.
        """
        cmd = ":SYST:DHCP?"
        self._send(cmd)
        dhcp = self._read()
        return int(dhcp)

    @rpc_method
    def set_dhcp(self, dhcp: int) -> None:
        """Use the IP LAN command to set a DHCP enabled state.

        Parameters:
            dhcp: New DHCP state. 0 is disabled, 1 is enabled.
        """
        cmd = f":SYST:DHCP {dhcp}"
        self._send(cmd)

    @rpc_method
    def get_ip_address(self) -> str:
        """Use the IP LAN command to get the current IP address of the device.

        Returns:
            ip_address: The current IP address of the device.
        """
        cmd = ":SYST:IPAD?"
        self._send(cmd)
        ip_address = self._read()
        return ip_address

    @rpc_method
    def set_ip_address(self, ip_address) -> None:
        """Use the IP LAN command to set a new IP address for the device.

        Parameters:
            ip_address: A new static IP address for the device.
        """
        cmd = f":SYST:IPAD {ip_address}"
        self._send(cmd)

    @rpc_method
    def get_subnet_mask(self) -> str:
        """Use the IP LAN command to get the current subnet mask address of the device.

        Returns:
            subnet_mask: The current subnet mask address of the device.
        """
        cmd = ":SYST:SMASK?"
        self._send(cmd)
        subnet_mask = self._read()
        return subnet_mask

    @rpc_method
    def set_subnet_mask(self, subnet_mask) -> None:
        """Use the IP LAN command to set a new subnet mask address for the device.

        Parameters:
            subnet_mask: A new subnet mask address for the device.
        """
        cmd = f":SYST:SMASK {subnet_mask}"
        self._send(cmd)

    @rpc_method
    def get_gateway_address(self) -> str:
        """Use the IP LAN command to get the current gateway address of the device.

        Returns:
            gateway: The current static gateway address of the device.
        """
        cmd = ":SYST:GATE?"
        self._send(cmd)
        gateway = self._read()
        return gateway

    @rpc_method
    def set_gateway_address(self, gateway) -> None:
        """Use the IP LAN command to set a new gateway address for the device.

        Parameters:
            gateway: A new static gateway address for the device.
        """
        cmd = f":SYST:GATE {gateway}"
        self._send(cmd)

    @rpc_method
    def get_ip_port(self) -> int:
        """Use the IP LAN command to get the current IP port number of the device.

        Returns:
            ip_port: The current IP port number of the device.
        """
        cmd = ":SYST:PORT?"
        self._send(cmd)
        ip_port = self._read()
        return int(ip_port)

    @rpc_method
    def set_ip_port(self, ip_port: int) -> None:
        """Use the IP LAN command to set a new IP port number for the device.

        Parameters:
            ip_port: A new static IP port number for the device.
        """
        cmd = f":SYST:PORT {ip_port}"
        self._send(cmd)


class Tenma72_13360(Tenma72_13350):
    """Instrument driver for the Tenma 72-13360, child of 72-13350.

    Attributes:
        MAX_VOLTAGE: The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT: The maximum current that can be set with the PSU (Amperes).
    """
    MAX_VOLTAGE = 60
    MAX_CURRENT = 15
