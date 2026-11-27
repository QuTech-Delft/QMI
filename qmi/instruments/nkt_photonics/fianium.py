"""Instrument driver for the NKT Photonics Fianium (FemtoPower 1060) supercontinuum laser source. The controller is
connected via USB using a serial port.
Commands can be found in the FemtoPower1060 Supercontinuum Laser Source manual.

Written by Yanik Herrmann (y.s.herrmann@tudelft.nl).
"""

import logging
import time

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class NKT_Fianium(QMI_Instrument):
    """Instrument driver for the NKT Photonics Fianium (FemtoPower 1060) supercontinuum laser source.

    Attributes:
        RESPONSE_TIMEOUT:     Instrument should respond within 0.5 seconds.
        LINE_END:             Line feed and carriage return (LF CR) sequence. Commands are sent as ASCII strings
                               terminated by a line feed, and the laser replies are ASCII strings terminated by this
                               sequence.
        CONTROL_MODES:        Valid laser control modes for `set_control_mode`.
        STATUS_DISPLAY_MODES: Valid status display modes for `set_status_display_mode`.
    """

    _rpc_properties = {"RESPONSE_TIMEOUT"}

    RESPONSE_TIMEOUT = 0.5

    LINE_END = "\n\r"

    CONTROL_MODES = (0, 1, 2)

    STATUS_DISPLAY_MODES = (0, 1, 2)

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """The class constructor.

        Parameters:
            context:   The QMI context this driver is running in.
            name:      Name for the instrument driver for the context registration.
            transport: QMI transport descriptor string for the serial connection, e.g. "serial:COM1".
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 19200})

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        self._transport.discard_read()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance.

        Raises:
            QMI_InstrumentException: If the serial number response does not end in an integer.
        """
        serRaw = self._ask("J?")
        time.sleep(0.1)
        verRaw = self._ask("V?")
        try:
            serial = int(serRaw.split(" ")[-1])
            return QMI_InstrumentIdentification(
                vendor="NKT",
                model="Femtopower_1060_Supercontinuum_Laser_Source",
                serial=str(serial),
                version=verRaw,
            )
        except ValueError as err:
            raise QMI_InstrumentException(f"Expecting serial number from instrument but got {serRaw!r}") from err

    def _ask(self, cmd: str) -> str:
        """Send command to instrument and return response from instrument.

        Parameters:
            cmd: The command string, without the line feed terminator.

        Returns:
            The response string, without the trailing terminator.
        """

        self._check_is_open()

        # Avoid reading stale response from instrument.
        self._transport.discard_read()

        # Send command.
        self._transport.write((cmd + "\n").encode("ascii"))

        # Read response. Reading stops at the first terminator, so a "Command>" prompt that may follow the
        # response is left in the input buffer and discarded before the next command.
        resp = self._transport.read_until(message_terminator=str.encode(self.LINE_END), timeout=self.RESPONSE_TIMEOUT)

        # Return the answer without the trailing terminator.
        return resp.rstrip().decode("ascii")

    @rpc_method
    def get_alarms(self) -> str:
        """Get potential alarms from the laser (command "A?")."""
        return self._ask("A?")

    @rpc_method
    def clear_all_alarms(self) -> str:
        """Clear all alarms of the laser (command "A=0")."""
        return self._ask("A=0")

    @rpc_method
    def get_back_refl_pd(self) -> str:
        """Get the back reflection photodiode reading (command "B?")."""
        return self._ask("B?")

    @rpc_method
    def display_command_list(self) -> str:
        """Get the first line of the command list of the laser (command "H?").

        Note that only the first line of the reply is returned. The remaining lines are discarded before the next
        command is sent.
        """
        return self._ask("H?")

    @rpc_method
    def get_status_display_interval(self) -> str:
        """Get the status display interval (command "I?")."""
        return self._ask("I?")

    @rpc_method
    def set_status_display_interval(self) -> str:
        """Set the status display interval to 1 by sending the command "I=1".

        The value 1 is hard-coded; this method takes no argument. See the FemtoPower1060 manual for the meaning,
        unit and allowed range of the interval value.
        """
        return self._ask("I=1")

    @rpc_method
    def get_control_mode(self) -> str:
        """Get the laser control mode (command "M?"). See `set_control_mode` for the mode numbers."""
        return self._ask("M?")

    @rpc_method
    def set_control_mode(self, mode: int) -> str:
        """Set the laser control mode.

        Parameters:
            mode: The control mode number:
                  0: potentiometer controlled open loop mode; the potentiometer on the front panel sets the output
                     power.
                  1: USB controlled open loop mode; the Q command is used to set the output power.
                  2: external voltage controlled open loop mode; a voltage in the range 0 V to +5 V DC sets the
                     output power.

        Raises:
            ValueError: If the mode is not 0, 1 or 2.
        """
        if mode not in self.CONTROL_MODES:
            raise ValueError(f"Invalid control mode {mode}, must be one of {self.CONTROL_MODES}.")

        return self._ask(f"M={mode}")

    @rpc_method
    def get_preamp_pd(self) -> str:
        """Get the pre-amplifier photodiode reading (command "P?")."""
        return self._ask("P?")

    @rpc_method
    def get_q(self) -> str:
        """Get the amplifier current control setting for the output power (command "Q?")."""
        return self._ask("Q?")

    @rpc_method
    def set_q(self, q: int) -> str:
        """Set the output power by the amplifier current control.

        The controller should be in the USB controlled mode, see `set_control_mode`. Before setting, the method
        checks that the laser temperature is ready.

        Parameters:
            q: The amplifier current control setting.

        Raises:
            QMI_InstrumentException: If the laser temperature is not ready.
        """
        ans = self.get_heater_countdown()
        if ans == "Laser Temperature ready":
            return self._ask(f"Q={q}")
        else:
            raise QMI_InstrumentException(f"Laser temperature is not ready: {ans}")

    @rpc_method
    def get_heater_countdown(self) -> str:
        """Get the heater countdown (command "O?"). Returns "Laser Temperature ready" when the laser is warm."""
        return self._ask("O?")

    @rpc_method
    def get_operation_time(self) -> str:
        """Get the operation time of the laser (command "W?")."""
        return self._ask("W?")

    @rpc_method
    def get_status_display_mode(self) -> str:
        """Get the status display mode (command "X?"). See `set_status_display_mode` for the mode numbers."""
        return self._ask("X?")

    @rpc_method
    def set_status_display_mode(self, mode: int) -> str:
        """Set the status display mode.

        Parameters:
            mode: Scrolling mode (0), normal mode (1) or system integration mode (2).

        Raises:
            ValueError: If the mode is not 0, 1 or 2.
        """
        if mode not in self.STATUS_DISPLAY_MODES:
            raise ValueError(f"Invalid status display mode {mode}, must be one of {self.STATUS_DISPLAY_MODES}.")

        return self._ask(f"X={mode}")

    @rpc_method
    def get_temp(self) -> str:
        """Get the laser temperature (command "T?")."""
        return self._ask("T?")
