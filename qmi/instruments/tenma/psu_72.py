"""Instrument driver for the Alice Pulse generator"""

import logging
import struct
from time import sleep
from typing import List, Optional, Union, Tuple
from dataclasses import dataclass

from qmi.core.context import QMI_Context
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


class Tenma72_2550(Tenma72_Base):
    """Instrument driver for the Tenma72_2550"""
    DEFAULT_BAUDRATE = 9600
    MAX_VOLTAGE = 30  # V
    MAX_CURRENT = 5  # A

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": self.DEFAULT_BAUDRATE}
        )
        self._enabled = False
        self._status = {}

    def _sendCommand(self, cmd: str) -> None:
        """Writes a command to the Tenma, just an ascii string

        Parameters:
            cmd:        The string to write.
        """
        self._transport.write(bytes(cmd, "ascii"))
        sleep(.2)  # Sleep some bits to let the message arrive

    def _getStatus(self):
        """
            Returns the power supply status as a dictionary of values

            * ch1Mode: "C.V | C.C"
            * ch2Mode: "C.V | C.C"
            * tracking:
                * 00=Independent
                * 01=Tracking series
                * 10=Tracking parallel
            * outEnabled: True | False
            :return: Dictionary of status values
        """
        self._sendCommand("STATUS?")
        statusByte = ord(self._transport.read(1, 1))  # Read response byte
        ch1mode = (statusByte & 0x01)
        ch2mode = (statusByte & 0x02)
        tracking = (statusByte & 0x0C) >> 2
        out = (statusByte & 0x40)

        if tracking == 0:
            tracking = "Independent"
        elif tracking == 1:
            tracking = "Tracking Series"
        elif tracking == 2:
            tracking = "Tracking Parallel"
        else:
            tracking = "Unknown"
        return {
            "ch1Mode": "C.V" if ch1mode else "C.C",
            "ch2Mode": "C.V" if ch2mode else "C.C",
            "Tracking": tracking,
            "outEnabled": bool(out),
        }

    def _read_str(self, timeout=0.2) -> str:
        byte_stream = self._transport.read_until_timeout(50, timeout)
        return byte_stream.decode('ascii')

    def _initialize(self):
        ## Read status
        self._status = self._getStatus()
        _logger.info(str(self._status))
        self._enabled = self._status['outEnabled']

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        # Initialize
        super().open()
        self._initialize()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        return QMI_InstrumentIdentification(vendor="Qutech", model="Alice pulse generation", serial=None, version=1)

    @rpc_method
    def readCurrent(self) -> float:
        """
            Reads the current setting
            :return: Current for the channel in Amps as a float
        """
        commandCheck = "ISET1?"
        self._sendCommand(commandCheck)
        # 72-2550 appends sixth byte from *IDN? to current reading due to firmware bug
        return float(self._read_str()[:5])

    @rpc_method
    def setCurrent(self, current: float) -> float:
        """
            Sets the current setting, note the maximal accuracy is milliamps
            Parameters:
                current: Current for the channel in Amps as a float
        """
        if not 0 < current < self.MAX_CURRENT:
            raise ValueError(f"Invalid current setting {current}, not between 0 and 5 A")

        commandCheck = f"ISET1:{current:.3f}"
        self._sendCommand(commandCheck)
        return self.readCurrent()

    @rpc_method
    def readVoltage(self) -> float:
        """
            Reads the current setting
            :return: Current for the channel in Amps as a float
        """
        commandCheck = "VSET1?"
        self._sendCommand(commandCheck)
        # 72-2550 appends sixth byte from *IDN? to current reading due to firmware bug
        return float(self._read_str())

    @rpc_method
    def setVoltage(self, voltage: float) -> float:
        """
            Sets the current setting, note the maximal accuracy is milliamps
            Parameters:
                current: Current for the channel in Amps as a float
        """
        if not 0 < voltage < self.MAX_VOLTAGE:
            raise ValueError(f"Invalid current setting {voltage}, not between 0 and 30 V")

        commandCheck = f"VSET1:{voltage:.3f}"
        self._sendCommand(commandCheck)
        return self.readVoltage()

    @rpc_method
    def setOuput(self, output: bool) -> None:
        """
            Sets the current setting, note the maximal accuracy is milliamps
            Parameters:
                current: Current for the channel in Amps as a float
        """
        val = 1 if output else 0
        commandCheck = f"OUT{val}"
        self._sendCommand(commandCheck)
        self._getStatus()
        if self._enabled is not output:
            raise QMI_InstrumentException("Setting output failed for an unknown reason")


class Tenma72_13360(Tenma72_Base):
    """Instrument driver for the Tenma72_13360"""
    MAX_VOLTAGE = 30  # V
    MAX_CURRENT = 5  # A
    DEFAULT_BAUDRATE = 115200

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(
            transport, default_attributes={"baudrate": self.DEFAULT_BAUDRATE}
        )
        self._enabled = False
        self._status = {}

    def _sendCommand(self, cmd: str) -> None:
        """Writes a command to the Tenma, just an ascii string

        Parameters:
            cmd:        The string to write.
        """
        self._transport.write(bytes(cmd + '\n', "ascii"))
        sleep(.2)  # Sleep some bits to let the message arrive

    def _getStatus(self):
        """
            Returns the power supply status as a dictionary of values

            "channelMode ": "C.V" or "C.C",
            "output ": "ON" or "OFF",
            "V/C priority ": "Current priority" or "Voltage priority",
            "beep ": "ON" or "OFF",
            "lock ": "ON" or "OFF",

            :return: Dictionary of status values
        """
        self._sendCommand("STATUS?")
        statusBytes = self._transport.read(2, 2)  # Read response byte
        # 72-13360 sends two bytes back, the second being '\n'
        status = statusBytes[0]

        ch1mode = (status & 0b00000001)
        output = bool(status & 0b00000010)
        current_priority = (status & 0b00000100)
        beep = bool(status & 0b00010000)
        lock = bool(status & 0b00100000)

        return {
            "channelMode": "C.V" if ch1mode else "C.C",
            "output": output,
            "V/C priority ": "Current priority" if current_priority else "Voltage priority",
            "beep": beep,
            "lock": lock,
        }

    def _read_str(self, timeout=0.2) -> str:
        byte_stream = self._transport.read_until_timeout(50, timeout)
        return byte_stream.decode('ascii')

    def _initialize(self):
        ## Read status
        self._status = self._getStatus()
        _logger.info(str(self._status))
        self._enabled = self._status['output']

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        # Initialize
        super().open()
        self._initialize()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        return QMI_InstrumentIdentification(vendor="Tenma", model="72-13360", serial=None, version=1)

    @rpc_method
    def readCurrent(self) -> float:
        """
            Reads the current setting
            :return: Current for the channel in Amps as a float
        """
        commandCheck = "ISET?"
        self._sendCommand(commandCheck)
        return float(self._read_str()[:5])

    @rpc_method
    def setCurrent(self, current: float) -> float:
        """
            Sets the current setting, note the maximal accuracy is milliamps
            Parameters:
                current: Current for the channel in Amps as a float
        """
        if not 0 < current < self.MAX_CURRENT:
            raise ValueError(f"Invalid current setting {current}, not between 0 and 5 A")

        commandCheck = f"ISET:{current:.3f}"
        self._sendCommand(commandCheck)
        return self.readCurrent()

    @rpc_method
    def readVoltage(self) -> float:
        """
            Reads the current setting
            :return: Current for the channel in Amps as a float
        """
        commandCheck = "VSET?"
        self._sendCommand(commandCheck)
        return float(self._read_str())

    @rpc_method
    def setVoltage(self, voltage: float) -> float:
        """
            Sets the current setting, note the maximal accuracy is milliamps
            Parameters:
                current: Current for the channel in Amps as a float
        """
        if not 0 < voltage < self.MAX_VOLTAGE:
            raise ValueError(f"Invalid current setting {voltage}, not between 0 and 30 V")

        commandCheck = f"VSET:{voltage:.3f}"
        self._sendCommand(commandCheck)
        return self.readVoltage()

    @rpc_method
    def setOuput(self, output: bool) -> None:
        """
            Sets the current setting, note the maximal accuracy is milliamps
            Parameters:
                current: Current for the channel in Amps as a float
        """
        val = 1 if output else 0
        commandCheck = f"OUT:{val}"
        self._sendCommand(commandCheck)
        self._status = self._getStatus()
        _logger.info(str(self._status))
        self._enabled = self._status['output']
        if self._enabled is not output:
            raise QMI_InstrumentException("Setting output failed for an unknown reason")