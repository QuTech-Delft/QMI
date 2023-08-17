"""Instrument driver for the OZ Optics 100MC attenuator.
"""

import logging
from typing import Optional, List, NamedTuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class OZO_AttenuatorPosition(NamedTuple):
    """Representation of attenuator setpoint.

    Attributes:
        steps:       Piezo position.
        attenuation: Realized attenuation in decibels.
    """
    steps: int
    attenuation: float


class OZOptics_DD100MC(QMI_Instrument):
    """Instrument driver for the OzOptics DD-100-MC attenuator.

    NOTE: the device expects commands ending with a Carriage Return character ('\r') and responds
    with lines ending in CR/LF ('\r\n').
    """
    # Instrument should respond within 5 seconds.
    RESPONSE_TIMEOUT = 5.0
    RESPONSE_TIMEOUT_HOME_COMMAND = 30.0  # HOME command may take longer.

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 9600})

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

    def _read_response(self, timeout: Optional[float]) -> List[str]:
        """Reads a response from instrument. The response consists of multiple 'lines' ending
        with CR\LF, where the last two 'lines' are "Done\r\n" and an empty line "\r\n".

        Returns:
            response: A list of ASCII strings with the last two 'lines' removed.
        """
        self._check_is_open()
        response = []
        while True:
            line_bytes = self._transport.read_until(b"\r\n", timeout)
            line = line_bytes[:-2].decode("ascii")
            response.append(line)
            if len(response) >= 2 and response[-2] == "Done" and response[-1] == "":
                break

        response = response[:-2]  # Remove the last 2 lines.
        return response

    def _execute_command(self, command: str, timeout: Optional[float]) -> List[str]:
        """Executes a command and reads the instrument response to the command."""
        self._check_is_open()
        command_bytes = (command + "\r").encode("ascii")
        self._transport.write(command_bytes)
        return self._read_response(timeout)

    @rpc_method
    def get_configuration_display(self) -> List[str]:
        """Get display configuration string.

        Returns:
            response: A list of strings showing current display configuration.
        """
        command = "CD"
        response = self._execute_command(command, self.RESPONSE_TIMEOUT)
        return response  # Don't even try to parse the result.

    @rpc_method
    def home(self) -> None:
        """Move attenuator to home position. Using extra long timeout."""
        command = "H"
        self._execute_command(command, self.RESPONSE_TIMEOUT_HOME_COMMAND)

    @rpc_method
    def get_position(self) -> OZO_AttenuatorPosition:
        """Get current attenuator position.

        Raises:
            QMI_InstrumentException: On bad response to query command.

        Returns:
            response: Piezo position in steps and realized attenuation in decibel.
        """
        command = "D"
        response = self._execute_command(command, self.RESPONSE_TIMEOUT)

        response_ok = (len(response) == 2) and response[0].startswith("DPos:") and response[1].startswith("ATTEN:")
        if not response_ok:
            raise QMI_InstrumentException("Bad response: {!r}".format(response))

        steps = int(response[0][5:])
        attenuation = float(response[1][6:])

        return OZO_AttenuatorPosition(steps, attenuation)

    @rpc_method
    def set_attenuation(self, value: float) -> int:
        """Set new target attenuation value in Decibel.

        Parameters:
            value: The target attenuation.

        Raises:
            QMI_InstrumentException: On bad response to command.

        Returns:
            Attenuator state (0 = IDLE).
        """
        command = "A{:.2f}".format(value)
        response = self._execute_command(command, self.RESPONSE_TIMEOUT)
        response_ok = (len(response) >= 1) and response[-1].startswith("Pos:")
        if not response_ok:
            raise QMI_InstrumentException("Bad response: {!r}".format(response))

        return int(response[-1][4:])
