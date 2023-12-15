"""Instrument driver for the Alice Pulse generator"""

import logging
import re
from time import sleep
from typing import Any, Dict, List, Optional, Union, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Tenma72_Base(QMI_Instrument):
    """The base class for all Tenma model 72 power supplies.

    Attributes:
        DEFAULT_BAUDRATE: The default baudrate in case of serial connection is used (Baud).
        MAX_VOLTAGE:      The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT:      The maximum current that can be set with the PSU (Amperes).
    """
    DEFAULT_BAUDRATE = 0
    MAX_VOLTAGE = 0
    MAX_CURRENT = 0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": self.DEFAULT_BAUDRATE}
        )

    def _send(self, cmd: str) -> None:
        """Writes a command to the Tenma, just an ascii string

        Parameters:
            cmd:    The command to write to the device.
        """
        self._transport.write(bytes(cmd, "ascii"))
        sleep(.02)  # Sleep some bits to let the message arrive

    def _read(self, timeout: float = 0.2) -> str:
        """Read the response from the device, try until response received or time-out.

        Parameters:
            timeout: The time-out value for reading. Default is 200ms.

        Returns:
            response: Decoded response string.
        """
        response = self._transport.read_until_timeout(50, timeout)
        return response.decode('ascii')

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
        self._send("*IDN?")  # TODO: For 13350-13360 models it reads: MTTTH*DIN? Test!
        idn = self._read()
        # Find all relevant info from response. Should be of format TENMA 72-2535 SN:1231345 V2.0
        pattern = re.compile(r"(\A[^\W\d_]+) ([0-9-]+) SN:([\d]+) V([0-9.]+)")
        vendor, model, serial, version = pattern.findall(idn)[0]
        return QMI_InstrumentIdentification(
            vendor=vendor,
            model=model,
            serial=serial,
            version=version
        )

    @rpc_method
    def get_status(self) -> Dict[str, Any]:
        """This method needs to be implemented in the inheriting classes."""
        raise NotImplementedError()

    @rpc_method
    def read_current(self, output_channel: Optional[int] = None) -> float:
        """Read the current setting.

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
    def set_current(self, current: float, output_channel: Optional[int] = None) -> None:
        """Sets the current setting.

        Parameters:
            current: Current for the channel in Amperes.
            output_channel: The channel to send the inquiry to.

        Raises:
            ValueError: If the current setting is not between 0 and self.MAX_CURRENT.
        """
        if not 0 < current < self.MAX_CURRENT:
            raise ValueError(f"Invalid current setting {current}, not between 0 and 5 A")

        ch = output_channel or ""
        command = f"ISET{ch}:{current:.3f}"
        self._send(command)

    @rpc_method
    def read_voltage(self, output_channel: Optional[int] = None) -> float:
        """Reads the voltage setting.

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
    def set_voltage(self, voltage: float, output_channel: Optional[int] = None) -> None:
        """Sets the voltage setting.

        Parameters:
            voltage: Voltage setting for the channel in Volts.
            output_channel: The channel to send the inquiry to.

        Raises:
            ValueError: If the input voltage setting is not between 0 and self.MAX_VOLTAGE
        """
        if not 0 < voltage < self.MAX_VOLTAGE:
            raise ValueError(f"Invalid current setting {voltage}, not between 0 and {self.MAX_VOLTAGE} V")

        ch = output_channel or ""
        command = f"VSET{ch}:{voltage:.3f}"
        self._send(command)

    @rpc_method
    def enable_output(self, output: bool) -> None:
        """
        Parameters:
            output_channel: The channel to send the inquiry to.

                current: Current for the channel in Amps as a float
        """
        val = 1 if output else 0
        command = f"OUT:{val}"
        self._send(command)
        status = self.get_status()
        if status["OutputEnabled"] is not output:
            raise QMI_InstrumentException("Setting output failed for an unknown reason")


class Tenma72_2550(Tenma72_Base):
    """Instrument driver for the Tenma 72-2550. The driver is tested with this model, but the respective
    manual is also for models 72-2535, 72-2540, 72-2545, 72-2925, 72-2930, 72-2935, 72-2940 & 72-10480.

    Attributes:
        DEFAULT_BAUDRATE: The default baudrate in case of serial connection is used (Baud).
        MAX_VOLTAGE:      The maximum voltage that can be set with the PSU (Volts).
        MAX_CURRENT:      The maximum current that can be set with the PSU (Amperes).
    """
    DEFAULT_BAUDRATE = 9600
    MAX_VOLTAGE = 60
    MAX_CURRENT = 3

    def get_status(self) -> Dict[str, Any]:
        """Get the power supply status as a dictionary of status values.

        Dictionary composition is:
            Ch1Mode: "C.V" | "C.C"
            Ch2Mode: "C.V" | "C.C"
            Tracking: xx, where xx is byte
                * 00 = Independent
                * 01 = Tracking series
                * 10 = Tracking parallel
            OutputEnabled: True | False
        
        Returns: 
            Dictionary of status values.
        """
        self._send("STATUS?")
        statusByte = ord(self._transport.read(1, 1))  # Read response byte
        ch1mode = (statusByte & 0x01)
        ch2mode = (statusByte & 0x02)
        tracking = (statusByte & 0x0C) >> 2
        output_enabled = (statusByte & 0x40)

        if tracking == 0:
            tracking = "Independent"
        elif tracking == 1:
            tracking = "Tracking Series"
        elif tracking == 2:
            tracking = "Tracking Parallel"
        else:
            tracking = "Unknown"
        return {
            "Ch1Mode": "C.V" if ch1mode else "C.C",
            "Ch2Mode": "C.V" if ch2mode else "C.C",
            "Tracking": tracking,
            "OutputEnabled": bool(output_enabled),
        }


class Tenma72_2535(Tenma72_2550):
    MAX_VOLTAGE = 30
    MAX_CURRENT = 3


class Tenma72_2540(Tenma72_2550):
    MAX_VOLTAGE = 30
    MAX_CURRENT = 5


class Tenma72_2545(Tenma72_2550):
    MAX_VOLTAGE = 60
    MAX_CURRENT = 2


class Tenma72_2925(Tenma72_2550):
    MAX_VOLTAGE = 30
    MAX_CURRENT = 5


class Tenma72_2930(Tenma72_2550):
    MAX_VOLTAGE = 30
    MAX_CURRENT = 10


class Tenma72_2935(Tenma72_2550):
    MAX_VOLTAGE = 60
    MAX_CURRENT = 5


class Tenma72_2940(Tenma72_2550):
    DEFAULT_BAUDRATE = 9600
    MAX_VOLTAGE = 60
    MAX_CURRENT = 5


class Tenma72_10480(Tenma72_2550):
    MAX_VOLTAGE = 30
    MAX_CURRENT = 3


class Tenma72_13350(Tenma72_Base):
    """Instrument driver for the Tenma 72-13350. The driver is tested with this model, but manual is
    also for the model 72-13360.
    """
    MAX_VOLTAGE = 30
    MAX_CURRENT = 30
    DEFAULT_BAUDRATE = 115200

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name, transport)

    def get_status(self) -> Dict[str, Any]:
        """Get the power supply status as a dictionary of status values.

        Dictionary composition is:
            "ChannelMode ": "C.V" | "C.C",
            "OutputEnabled": True | False,
            "V/C priority ": "Current priority" | "Voltage priority",
            "Beep ": True | False,
            "Lock ": True | False,

        Returns: 
            Dictionary of status values.
        """
        self._send("STATUS?")
        statusBytes = self._transport.read(2, 2)  # Read response byte
        # 72-13350 sends two bytes back, the second being '\n'
        status = statusBytes[0]

        ch1mode = (status & 0b00000001)
        output_enabled = bool(status & 0b00000010)
        current_priority = (status & 0b00000100)
        beep = bool(status & 0b00010000)
        lock = bool(status & 0b00100000)

        return {
            "ChannelMode": "C.V" if ch1mode else "C.C",
            "OutputEnabled": output_enabled,
            "V/C priority ": "Current priority" if current_priority else "Voltage priority",
            "Beep": beep,
            "Lock": lock,
        }


class Tenma72_13360(Tenma72_13350):
    MAX_VOLTAGE = 60
    MAX_CURRENT = 15
