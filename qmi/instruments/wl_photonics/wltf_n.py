"""
Instrument driver for the WL Photonics tunable narrowband wavelength filter (WLTF-N).
"""

import logging
from dataclasses import dataclass
from re import search
from time import sleep

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class _WavelengthRange:
    """Dataclass for wavelength instrument range."""

    min: float
    max: float


@dataclass
class _StepsRange:
    """Dataclass for frequency instrument range."""

    min: int
    max: int


class WlPhotonics_WltfN(QMI_Instrument):
    """Instrument driver for the WL Photonics tunable narrowband wavelength filter.

    The instrument moves at limited speed.
    At power-up the instrument might start from motor position being 0, meaning that at this initial position
    the motor will be outside the (calibrated) wavelength range and reading the wavelength simply returns
    'Wavelength:Unknown'. Similarly, going to zero position will move the motor outside the wavelength range.
    Note that the wavelength and step ranges are inverse: Min steps value is max wavelength and vice versa.
    
    The default baudrate is 115200 for serial connections.

    Attributes:
        DEFAULT_RESPONSE_TIMEOUT:   Timeout value for waiting responses.
        ZEROING_WAIT:               Time to wait for the motor to go to zero.
        CMD_TERMINATOR:             The terminator added for sending commands.
        RESPONSE_TERMINATOR:        The terminator expected for end of one response.
    """
    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0
    ZEROING_WAIT = 3.0  # In seconds
    
    # Command and response terminator characters
    CMD_TERMINATOR = "\r\n"
    RESPONSE_TERMINATOR = b"OK\r\n"
    ENCODING = "ascii"

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            context:    The QMI context for running the driver in.
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport)

        # Instrument ranges for values. Will be updated in `open()`
        self._wavelength_range = _WavelengthRange
        self._steps_range = _StepsRange

        # Current motor position step value. Initialize with 0, it will be updated in `open()`
        self._motor_position = 0

        # For convenience
        self.response_terminator = self.RESPONSE_TERMINATOR.decode(self.ENCODING)

    def _write(self, cmd: str) -> None:
        """Write a command to the instrument and check if any errors or alerts were raised.

        Parameters:
            cmd: The input command to send.
        """
        self._check_is_open()
        cmd = cmd + self.CMD_TERMINATOR
        self._transport.write(cmd.encode(self.ENCODING))

    def _read(self) -> str:
        """Read data from the instrument buffer.

        Returns:
            response: Decoded response string.
        """
        self._check_is_open()
        response = self._transport.read_until(self.RESPONSE_TERMINATOR, timeout=self.DEFAULT_RESPONSE_TIMEOUT)
        return response.decode(self.ENCODING)

    def _clear_ok(self, cmd: str) -> None:
        """Clear response 'OK' from the instrument buffer. If the returned value was something else than "OK",
        the clear method will raise an exception.

        Parameters:
            cmd: The command that was sent in.

        Raises:
            QMI_InstrumentException: If the instrument returned another response than "OK".
        """
        response = self._read()
        # Check that we got 'OK' as second item in response. The first is the echo of the command sent.
        if response.split(self.response_terminator)[1] == "":
            return

        raise QMI_InstrumentException(f"Command {cmd} returned {response} instead of OK")

    def _ask_int(self, cmd: str) -> int:
        """Send a query and return an integer number response.

        Parameters:
            cmd:    The query command string.

        Raises:
            ValueError: If the response string was not an integer value or an empty string.
            TypeError: If there was no match for the response string to find numbers, giving `None`.

        Returns:
            response: The query response as integer.
        """
        self._write(cmd)
        full_response = self._read().split("\n")  # First item should be the response, the second "OK".
        try:
            return int(search(r"[-\d.]+", full_response[0])[0])  # type: ignore
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {full_response!r}") from exc
        except TypeError as exc:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {full_response!r}") from exc

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating point response.

        Parameters:
            cmd:    The query command string.

        Raises:
            ValueError: If the response string was not a floating point value or an empty string.
            TypeError: If there was no match for the response string to find numbers, giving `None`.

        Returns:
            response: The query response as a floating point.
        """
        self._write(cmd)
        full_response = self._read().split("\n")  # First item should be the response, the second "OK".
        if "Unknown" in full_response[0]:
            # The wavelength has not been set or calibrated yet
            _logger.warning(f"Trying to set a value with command {cmd}, but the parameter is not yet set or calibrated")
            return 0.0
        try:
            return float(search(r"[\d.]+", full_response[0])[0])  # type: ignore
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {full_response!r}") from exc
        except TypeError as exc:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {full_response!r}") from exc

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()
        # Check the ID to update the ranges and log
        _logger.info("Found instrument %s", self.get_idn())
        # Check the current motor step position
        self.get_motor_position()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        self._check_is_open()
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument info and return QMI_InstrumentIdentification instance. The instrument returns several
        lines of data, example from the documentation:
        'WL200: SN(201307374), MD(2018-11-23)\r\n',
        'WL Range: 1021.509~1072.505nm(Step: 4654~556)\r\n',
        'OK\r\n'.
        This is processed to create the QMI_InstrumentIdentification object and also to update the wavelength and
        step range class attributes:
        - self._wavelength_range: Updates the instrument wavelength range min and max.
        - self._steps_range: Updates the instrument step range min and max.

        Returns:
            QMI_InstrumentIdentification: Data with e.g. idn.vendor = WL Photonics, idn.model = WL200,
            idn.serial = 201307374, idn.version = 2018-11-23.
        """
        self._write("dev?")
        resp = self._read()
        words = resp.rstrip().split("\r\n")
        if len(words) != 3:
            raise QMI_InstrumentException(f"Unexpected response to dev?, got {resp!r}")

        model = words[0].split(":")[0]
        serial = search(r"SN\([\d]+\)", words[0])[0].strip("SN()")  # type: ignore
        version = search(r"MD\([ \d-]+\)", words[0])[0].strip("MD()")  # type: ignore
        # Update the wavelength and step ranges on-the-go
        wl_range = words[1].split(":")[1].split("nm")[0].strip().split("~")
        self._wavelength_range.min = float(wl_range[0])
        self._wavelength_range.max = float(wl_range[1])
        step_range = words[1].split(":")[2].rstrip(f"){self.response_terminator}").lstrip().split("~")
        self._steps_range.max = int(step_range[0])  # NOTE: The range is inverse to the wavelength:
        self._steps_range.min = int(step_range[1])  # Minimum step value is maximum wavelength and vice versa.

        return QMI_InstrumentIdentification(vendor="WL Photonics", model=model, serial=serial, version=version)

    @rpc_method
    def set_center_wavelength(self, wavelength: float) -> None:
        """Set the center wavelength in nanometers.

        Parameters:
            wavelength: The target wavelength in nanometers.

        Raises:
            QMI_InstrumentException: If the wavelength is not in the instrument range.
        """
        unit = "nm"
        decimals = 3
        if wavelength < self._wavelength_range.min or wavelength > self._wavelength_range.max:
            raise ValueError(
                f"Wavelength {wavelength}{unit} out of instrument range "
                f"({self._wavelength_range.min}{unit} - {self._wavelength_range.max}{unit})"
            )

        cmd = f"wl{wavelength:.{decimals}f}"
        self._write(cmd)
        self._clear_ok(cmd)

    @rpc_method
    def get_center_wavelength(self) -> float:
        """Get the center wavelength. Default unit is nanometers.

        Returns:
            wavelength: The instrument wavelength in nanometers.
        """
        wavelength = self._ask_float("wl?")
        return wavelength

    @rpc_method
    def get_minimum_wavelength(self) -> float:
        """Get the minimum wavelength.

        Returns:
            self._wavelength_range.min: The instrument wavelength minimum in nanometers.
        """
        return self._wavelength_range.min

    @rpc_method
    def get_maximum_wavelength(self) -> float:
        """Get the maximum wavelength.

        Returns:
            self._wavelength_range.max: The instrument wavelength maximum in nanometers.
        """
        return self._wavelength_range.max

    @rpc_method
    def reverse_motor(self, steps: int) -> None:
        """Reverse the motor by input steps. This can be used to fine-tune the center wavelength.

        Parameters:
            steps: Number of steps the motor should reverse.

        Raises:
            ValueError: If calculated new motor position is not in the correct range.
        """
        new_position = self._motor_position - steps
        if new_position < self._steps_range.min:
            raise ValueError(
                f"Input value {steps} moves motor beyond minimum range {self._wavelength_range.min}. "
                f"The new motor position would have been {new_position}."
            )

        cmd = f"sb{steps}"
        self._write(cmd)
        self._clear_ok(cmd)

    @rpc_method
    def forward_motor(self, steps: int) -> None:
        """Move the motor forward by input steps. This can be used to fine-tune the center wavelength.

        Parameters:
            steps: Number of steps the motor should move forward.

        Raises:
            ValueError: If calculated new motor position is not in the correct range.
        """
        new_position = self._motor_position + steps
        if new_position > self._steps_range.max:
            raise ValueError(
                f"Input value {steps} moves motor beyond minimum range {self._wavelength_range.max}. "
                f"The new motor position would have been {new_position}."
            )

        cmd = f"sf{steps}"
        self._write(cmd)
        self._clear_ok(cmd)

    @rpc_method
    def get_motor_position(self) -> int:
        """Get the current step motor position.

        Attributes:
            self._motor_position: Updates the current motor position step value.

        Returns:
            self._motor_position: The current motor position step value.
        """
        self._motor_position = self._ask_int("s?")
        return self._motor_position

    @rpc_method
    def get_minimum_steps(self) -> int:
        """Get the minimum steps.

        Returns:
            self._steps_range.min: The instrument steps minimum.
        """
        return self._steps_range.min

    @rpc_method
    def get_maximum_steps(self) -> int:
        """Get the maximum steps.

        Returns:
            self._steps_range.max: The instrument steps maximum.
        """
        return self._steps_range.max

    @rpc_method
    def go_to_zero(self):
        """Move the motor to 'zero' position. This can take up to 3 seconds.

        The motor moves to zero, where the wavelength value cannot be read anymore as the motor position
        is outside the instrument's wavelength range. Reading the wavelength here gives "wavelength:Unknown" as
        response. This probably can be used as a calibration step for checking drift on absolute wavelength.
        """
        cmd = "z"
        self._write(cmd)
        self._clear_ok(cmd)
        # Wait for zeroing and then update the latest position
        sleep(self.ZEROING_WAIT)
        self.get_motor_position()
