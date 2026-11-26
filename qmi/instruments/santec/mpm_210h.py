"""Instrument driver for the Santec MPM-210H multi-port optical power and current meter."""

import ipaddress
import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from time import sleep

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import QMI_Transport, create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class _WavelengthRange:
    """Dataclass for the wavelength range in nanometers."""

    min: float = 1250.0
    max: float = 1630.0


@dataclass
class _StepRange:
    """Dataclass for the wavelength sweep step range in nanometers."""

    min: float = 0.001
    max: float = 10.0


@dataclass
class _SweepSpeedRange:
    """Dataclass for the sweep speed range in nanometers per second."""

    min: float = 0.001
    max: float = 200.0


@dataclass
class _AveragingTimeRange:
    """Dataclass for the averaging time range in milliseconds."""

    min: float = 0.01
    max: float = 10000.0


class _Mpm210hProtocol:
    """Implement the MPM-210H command protocol over a QMI transport.

    Commands and responses are ASCII on all interfaces. The MPM-210H terminates received commands at LF and ends
    its responses with CR+LF on TCP and RS-232, while GPIB messages are delimited by EOI. Only the LOGG? response
    contains binary data, which is framed in the same way on GPIB and TCP. LOGG? is not available on RS-232.
    """

    # The manual requires a wait of 10 ms after sending each command over TCP.
    TCP_COMMAND_WAIT_TIME = 0.01  # seconds

    def __init__(self, transport: QMI_Transport, transport_type: str) -> None:
        self._transport = transport
        self._terminator = b"" if transport_type == "gpib" else b"\n"
        self._sleep: Callable[[], None] = (
            partial(sleep, self.TCP_COMMAND_WAIT_TIME) if transport_type == "tcp" else lambda: None
        )
        # True when the MPM-210H echoes received commands back (RS-232 only).
        self.echo = False

    def write(self, command: str, timeout: float) -> None:
        """Send a command, using LF for serial and TCP transports.

        Over TCP, the required wait after the command is done here. When echo is enabled, the echoed command is
        read back and discarded.

        Parameters:
            command: The command string.
            timeout: Maximum time to wait for the echo in seconds.

        Raises:
            QMI_InstrumentException: If the echoed command does not match the sent command.
        """
        self._transport.write(command.encode("ascii") + self._terminator)
        self._sleep()
        if self.echo:
            echo = self._transport.read_until(self._terminator, timeout=timeout)
            if echo.decode("ascii", errors="replace").strip() != command:
                raise QMI_InstrumentException(f"Unexpected echo for command {command!r}: {echo!r}")

    def ask(self, command: str, timeout: float) -> str:
        """Send a query and return its ASCII response without its line ending.

        Parameters:
            command: The query string.
            timeout: Maximum time to wait for the echo and for the response in seconds.

        Raises:
            QMI_TimeoutException: If no response is received.
        """
        self.write(command, timeout)
        response = self._transport.read_until(self._terminator, timeout=timeout)
        if not response:
            raise QMI_TimeoutException(f"No response received to {command!r}.")

        return response.decode("ascii").rstrip("\r\n")


class Santec_Mpm210H(QMI_Instrument):
    """Driver for one measurement module in a Santec MPM-210H mainframe.

    A separate driver instance must be created for every module that is to be
    controlled. The ``slot`` constructor argument selects the module slot;
    channel methods then address individual ports in that module.

    The transport descriptor must use one of QMI's ``serial:``, ``tcp:``, or
    ``gpib:`` interfaces. For example, ``serial:COM3`` uses the MPM-210H's
    documented default serial settings.

    The default values are from MPM-210H-M-E-v1.0.pdf.
    """
    _rpc_constants = {"GPIB_DEFAULT_ADDR"}
    _rpc_properties = {"DEFAULT_RESPONSE_TIMEOUT", "ZEROING_WAIT_TIME"}

    DEFAULT_RESPONSE_TIMEOUT = 10.0
    ZEROING_WAIT_TIME = 3  # seconds
    # Time to wait for the echo of the ECHO command itself before discarding it.
    ECHO_SETTLE_TIME = 0.1  # seconds
    # Time to wait for a possible CR+LF after the binary LOGG? block over TCP.
    BLOCK_TRAILER_TIMEOUT = 0.1  # seconds

    SERIAL_DEFAULT_ATTRIBUTES = {
        "baudrate": 115200,
        "bytesize": 8,
        "parity": 'N',
        "stopbits": 1.0,
        "rtscts": False,
    }
    GPIB_DEFAULT_ADDR = 16
    TCP_DEFAULT_PORT = 5000
    VALID_MEASUREMENT_MODES = ('CONST1', 'SWEEP1', 'CONST2', 'SWEEP2', 'FREERUN')
    VALID_MODULES = range(5)
    # Number of measurement channels per module model. Models not listed have 4 channels.
    MODULE_CHANNEL_COUNTS = {"MPM-212": 2}
    ERRORS_TABLE = {
        0: "No error",
        -101: "Invalid character",
        -103: "Invalid separator",
        -104: "Data type error",
        -108: "Parameter not allowed",
        -109: "Missing parameter",
        -110: "Command header error",
        -113: "Undefined header",
        -221: "Setting conflict",
        -222: "Data out of range",
        -284: "Program currently running",
        -300: "Device-specific error",
        -301: "Not a measurement module",
        -350: "Queue overflow",
        -351: "Queue empty",
        101: "Module communication header error",
        103: "Module communication response number error",
        104: "Module communication module mismatch",
        110: "TCP/IP communication error",
        116: "GPIB transmission not completed",
        117: "GPIB transmission timer expired",
        120: "Measurement controller trigger error",
        210: "SEM does not exist",
    }

    def __init__(self, context: QMI_Context, name: str, transport: str, slot: int = 0) -> None:
        """Initialize a driver for one MPM-210H measurement module.

        Parameters:
            context:   The QMI context for running the driver in.
            name:      Name for this instrument instance.
            transport: QMI transport descriptor using serial, tcp, or gpib.
            slot:      Measurement module slot number, from 0 through 4.

        Raises:
            ValueError: If ``slot`` or the transport interface is invalid.
        """
        super().__init__(context, name)
        self._validate_slot(slot)
        self._transport_type = transport.partition(":")[0].lower()
        if self._transport_type == "tcp":
            self._transport = create_transport(transport, default_attributes={"port": self.TCP_DEFAULT_PORT})

        elif self._transport_type == "serial":
            self._transport = create_transport(transport, default_attributes=self.SERIAL_DEFAULT_ATTRIBUTES)

        elif self._transport_type == "gpib":
            self._transport = create_transport(transport, default_attributes={"primary_addr": self.GPIB_DEFAULT_ADDR})

        else:
            raise ValueError(f"Invalid transport string type {self._transport_type} for MPM-210H.")

        self._slot = slot
        self._protocol = _Mpm210hProtocol(self._transport, transport_type=self._transport_type)
        # We want to know the module model name, as some commands depend on the module model.
        self._module = ""
        self._channel_count = 4
        self._wavelength_range = _WavelengthRange()
        self._step_range = _StepRange()
        self._sweep_speed_range = _SweepSpeedRange()
        self._averaging_time_range = _AveragingTimeRange()

    @staticmethod
    def _is_int_in(value: int, valid: range) -> bool:
        """Return True when ``value`` is an integer (not a bool) within ``valid``."""
        return isinstance(value, int) and not isinstance(value, bool) and value in valid

    @staticmethod
    def _validate_slot(slot: int) -> None:
        """Validate a measurement module slot number.

        Raises:
            ValueError: If ``slot`` is not an installed-slot number from 0 through 4.
        """
        if not Santec_Mpm210H._is_int_in(slot, Santec_Mpm210H.VALID_MODULES):
            raise ValueError("Slot number must be an integer from 0 through 4.")

    def _validate_channel(self, channel: int) -> None:
        """Validate a measurement channel number against the channel count of the module.

        Raises:
            ValueError: If ``channel`` is not from 1 through the module's channel count.
        """
        if not self._is_int_in(channel, range(1, self._channel_count + 1)):
            raise ValueError(
                f"Channel must be an integer from 1 through {self._channel_count} for module {self._module}."
            )

    def _check_gain_supported(self) -> None:
        """Check that the module supports TIA gain settings.

        Raises:
            QMI_InstrumentException: If the module is an MPM-215.
        """
        if self._module == "MPM-215":
            raise QMI_InstrumentException("TIA gain is not available for the MPM-215 module.")

    def _validate_gain(self, gain: int) -> None:
        """Validate a TIA gain level for the module.

        Raises:
            QMI_InstrumentException: If the module is an MPM-215.
            ValueError:              If ``gain`` is not from 1 through 5 (1 through 4 for the MPM-213).
        """
        self._check_gain_supported()
        gain_range = range(1, 5) if self._module == "MPM-213" else range(1, 6)
        if not self._is_int_in(gain, gain_range):
            raise ValueError(
                f"Gain must be an integer from 1 through {gain_range[-1]} for module {self._module}."
            )

    @staticmethod
    def _validate_range(value: float, minimum: float, maximum: float, name: str) -> None:
        """Validate a real value against an inclusive range.

        Raises:
            ValueError: If ``value`` falls outside the supplied range.
        """
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be in the range from {minimum} to {maximum}.")

    @staticmethod
    def _parse_int(command: str, response: str) -> int:
        """Parse an integer response.

        Raises:
            QMI_InstrumentException: If the response is not an integer.
        """
        try:
            return int(response)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}") from exc

    @staticmethod
    def _parse_float(command: str, response: str) -> float:
        """Parse a real response.

        Raises:
            QMI_InstrumentException: If the response is not a real number.
        """
        try:
            return float(response)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}") from exc

    @staticmethod
    def _parse_int_list(command: str, response: str) -> list[int]:
        """Parse a comma-separated list of integer responses.

        Raises:
            QMI_InstrumentException: If any response item is not an integer.
        """
        try:
            return [int(value) for value in response.split(",")]
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}") from exc

    @staticmethod
    def _parse_float_list(command: str, response: str) -> list[float]:
        """Parse a comma-separated list of real responses.

        Raises:
            QMI_InstrumentException: If any response item is not a real number.
        """
        try:
            return [float(value) for value in response.split(",")]
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}") from exc

    @staticmethod
    def _parse_block_digits(prefix: bytes) -> int:
        """Parse the ``#<digits>`` prefix of a binary block and return the number of length digits.

        Raises:
            QMI_InstrumentException: If the prefix is malformed.
        """
        if len(prefix) != 2 or prefix[0:1] != b"#" or not prefix[1:2].isdigit():
            raise QMI_InstrumentException(f"Invalid LOGG? response header: {prefix!r}")

        return int(prefix[1:2])

    @staticmethod
    def _parse_block_length(field: bytes, digits: int) -> int:
        """Parse the length field of a binary block and return the payload length in bytes.

        Raises:
            QMI_InstrumentException: If the length field is malformed.
        """
        if len(field) != digits or not field.isdigit():
            raise QMI_InstrumentException(f"Invalid LOGG? response length: {field!r}")

        return int(field)

    def _read_error(self) -> tuple[int, str]:
        """Read and parse one entry from the MPM-210H error queue.

        Raises:
            QMI_InstrumentException: If the error response does not contain a code and message.
        """
        command = "ERR?"
        response = self._ask(command)
        code, separator, message = response.partition(",")
        if not separator:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}")
        return self._parse_int(command, code.strip()), message.strip().strip('"')

    def _check_errors(self, command: str) -> None:
        """Drain the error queue and raise if it contained errors caused by ``command``.

        Raises:
            QMI_InstrumentException: If the instrument reports one or more command errors.
        """
        errors = []
        while True:
            code, message = self._read_error()
            if code == 0:
                break
            errors.append(self.ERRORS_TABLE.get(code, f"Unknown error {code}: {message}"))

        if errors:
            _logger.error("[%s] Command [%s] resulted in errors: %s", self._name, command, errors)
            raise QMI_InstrumentException(f"Command {command} resulted in errors: {errors}")

    def _write(self, command: str) -> None:
        """Write an MPM-210H command and raise if it adds an error to the queue.

        Raises:
            QMI_InstrumentException: If the instrument reports one or more command errors.
        """
        self._check_is_open()
        self._protocol.write(command, self.DEFAULT_RESPONSE_TIMEOUT)
        self._check_errors(command)

    def _ask(self, command: str) -> str:
        """Send an MPM-210H query and return its response."""
        self._check_is_open()
        return self._protocol.ask(command, self.DEFAULT_RESPONSE_TIMEOUT)

    @staticmethod
    def _check_ip_address(address: str) -> None:
        """Validate an IPv4 address string.

        Raises:
            ValueError: If ``address`` is not a valid IPv4 address.
        """
        try:
            ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"Invalid IPv4 address: {address!r}") from exc

    @rpc_method
    def open(self) -> None:
        """Open the configured connection to the MPM-210H."""
        _logger.info("[%s] Opening connection to MPM-210H module %d", self._name, self._slot)
        self._transport.open()
        super().open()
        # Get module model name.
        try:
            mod_idn = self.get_idn()
            _logger.info("[%s] Opened communication to module %s", self._name, mod_idn._asdict())
            self._module = str(mod_idn.model).upper()
            self._channel_count = self.MODULE_CHANNEL_COUNTS.get(self._module, 4)

        except (QMI_InstrumentException, QMI_TimeoutException) as qmi_exc:
            self.close()
            _logger.exception(
                "[%s] Failed to obtain module identification for slot %d: %s", self._name, self._slot, str(qmi_exc)
            )
            raise QMI_InstrumentException(f"Failed to open connection to MPM-210H slot {self._slot}") from qmi_exc

    @rpc_method
    def close(self) -> None:
        """Close the connection to the MPM-210H."""
        _logger.info("[%s] Closing connection to MPM-210H module %s", self._name, self._module)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Return the identification information for this driver's measurement module.

        Return string example is Santec,MPM-211,00000000M211,Ver1.11.

        Raises:
            QMI_InstrumentException: If the response does not contain four fields.
        """
        command = f"MMVER? {self._slot}"
        response = self._ask(command)
        fields = [field.strip() for field in response.split(",")]
        if len(fields) != 4:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}.")

        return QMI_InstrumentIdentification(*fields)

    @rpc_method
    def get_mainframe_idn(self) -> QMI_InstrumentIdentification:
        """Return the mainframe identification information.

        Return string example is SANTEC,MPM-210H,00000000,Ver.2.0.

        Raises:
            QMI_InstrumentException: If the response does not contain four fields.
        """
        command = "*IDN?"
        response = self._ask(command)
        fields = [field.strip() for field in response.split(",")]
        if len(fields) != 4:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {response!r}")

        return QMI_InstrumentIdentification(*fields)

    @rpc_method
    def set_serial_echo(self, enabled: bool) -> None:
        """Enable or disable command echo for a serial connection.

        While echo is enabled, the driver reads back and discards the echo of every command.

        Raises:
            QMI_InstrumentException: If the selected transport is not serial, or the instrument reports an error.
        """
        if self._transport_type != 'serial':
            raise QMI_InstrumentException("ECHO is only available through a serial transport.")

        self._check_is_open()
        command = f"ECHO {int(enabled)}"
        # Whether the ECHO command itself is echoed depends on the old and new echo state. Discard whatever
        # comes back instead of relying on that, and only then switch the echo handling of the protocol.
        self._protocol.echo = False
        self._protocol.write(command, self.DEFAULT_RESPONSE_TIMEOUT)
        sleep(self.ECHO_SETTLE_TIME)
        self._transport.discard_read()
        self._protocol.echo = enabled
        self._check_errors(command)

    @rpc_method
    def get_error(self) -> tuple[int, str]:
        """Return and remove the next entry from the mainframe error queue.

        Raises:
            QMI_InstrumentException: If the response has an invalid error-code field.
        """
        return self._read_error()

    @rpc_method
    def get_module_recognition(self) -> list[bool]:
        """Return whether each of the five measurement modules are recognized."""
        command = "IDIS?"
        values = self._parse_int_list(command, self._ask(command))
        if len(values) != 5 or any(value not in (0, 1) for value in values):
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {values!r}")

        return [bool(value) for value in values]

    @rpc_method
    def set_gpib_address(self, address: int) -> None:
        """Set the mainframe GPIB address. WARNING: If using this with GPIB transport, the current
        transport will become invalid and no more ASCII commands can be sent nor received.
        To re-establish connection, a new driver instance has to be made.

        Raises:
            ValueError: If ``address`` is not from 1 through 31.
        """
        if not self._is_int_in(address, range(1, 32)):
            raise ValueError("GPIB address must be an integer from 1 through 31.")

        self._write(f"ADDR {address}")

    @rpc_method
    def get_gpib_address(self) -> int:
        """Return the mainframe GPIB address."""
        command = "ADDR?"
        return self._parse_int(command, self._ask(command))

    @rpc_method
    def set_gateway_address(self, address: str) -> None:
        """Set the mainframe IPv4 gateway address.

        Parameters:
            address: Gateway address as a string.
        """
        self._check_ip_address(address)
        self._write(f"GW {address}")

    @rpc_method
    def get_gateway_address(self) -> str:
        """Return the mainframe IPv4 gateway address."""
        return self._ask("GW?")

    @rpc_method
    def set_subnet_mask(self, mask: str) -> None:
        """Set the mainframe IPv4 subnet mask.

        Parameters:
            mask: Subnet mask as a string.
        """
        self._check_ip_address(mask)
        self._write(f"SUBNET {mask}")

    @rpc_method
    def get_subnet_mask(self) -> str:
        """Return the mainframe IPv4 subnet mask."""
        return self._ask("SUBNET?")

    @rpc_method
    def set_ip_address(self, address: str) -> None:
        """Set the mainframe IPv4 address.

        Parameters:
            address: IPv4 address as a string.
        """
        self._check_ip_address(address)
        self._write(f"IP {address}")

    @rpc_method
    def get_ip_address(self) -> str:
        """Return the mainframe IPv4 address."""
        return self._ask("IP?")

    @rpc_method
    def set_trigger_mode(self, external: bool) -> None:
        """Set the trigger mode.

        Parameters:
            external: Set to external when True, by False set to internal.
        """
        self._write(f"TRIG {int(external)}")

    @rpc_method
    def get_trigger_mode(self) -> bool:
        """Return True when the trigger mode is external. If it is internal, return False.

        Raises:
            QMI_InstrumentException: If the response is not 0 or 1.
        """
        command = "TRIG?"
        value = self._parse_int(command, self._ask(command))
        if value not in (0, 1):
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {value!r}.")

        return bool(value)

    @rpc_method
    def set_measurement_mode(self, mode: str) -> None:
        """Set the measurement mode.

        Parameters:
            mode: Measurement mode string. Valid modes are:
                  'CONST1', 'SWEEP1', 'CONST2', 'SWEEP2', 'FREERUN'

        Raises:
            ValueError: If ``mode`` is not supported by the MPM-210H protocol.
        """
        normalized_mode = mode.upper()
        if normalized_mode not in self.VALID_MEASUREMENT_MODES:
            raise ValueError(f"Measurement mode must be one of {self.VALID_MEASUREMENT_MODES}.")

        if self._module == "MPM-215" and normalized_mode not in ("CONST2", "SWEEP2"):
            raise ValueError("MPM-215 module supports only measurement modes 'CONST2' and 'SWEEP2'.")

        self._write(f"WMOD {normalized_mode}")

    @rpc_method
    def get_measurement_mode(self) -> str:
        """Return the active measurement mode."""
        return self._ask("WMOD?").upper()

    @rpc_method
    def set_wavelength(self, wavelength: float) -> None:
        """Set the constant-wavelength measurement wavelength in nanometers.

        Parameters:
            wavelength: Wavelength value in nanometers.

        Raises:
            ValueError: If ``wavelength`` is outside the supported range.
        """
        self._validate_range(
            wavelength, self._wavelength_range.min, self._wavelength_range.max, "Wavelength"
        )
        self._write(f"WAV {wavelength:.3f}")

    @rpc_method
    def get_wavelength(self) -> float:
        """Return the constant-wavelength measurement wavelength in nanometers."""
        command = "WAV?"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def set_channel_wavelength(self, channel: int, wavelength: float) -> None:
        """Set the constant-wavelength measurement wavelength for one channel.

        Parameters:
            channel:    Channel number.
            wavelength: Wavelength in nanometers.

        Raises:
            ValueError: If ``channel`` or ``wavelength`` is invalid.
        """
        self._validate_channel(channel)
        self._validate_range(
            wavelength, self._wavelength_range.min, self._wavelength_range.max, "Wavelength"
        )
        self._write(f"DWAV {self._slot},{channel},{wavelength:.3f}")

    @rpc_method
    def get_channel_wavelength(self, channel: int) -> float:
        """Return the constant-wavelength measurement wavelength for one channel.

        Parameters:
            channel:    Channel number.

        Raises:
            ValueError: If ``channel`` is invalid.
        """
        self._validate_channel(channel)
        command = f"DWAV? {self._slot},{channel}"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def set_sweep_wavelengths(self, start: float, stop: float, step: float) -> None:
        """Set the start, stop, and step wavelengths for a sweep in nanometers.

        Parameters:
            start: Start wavelength in nanometers.
            stop:  Stop wavelength in nanometers.
            step:  Step wavelength in nanometers.

        Raises:
            ValueError: If a wavelength or step is out of range, or stop precedes start + step.
        """
        self._validate_range(
            start, self._wavelength_range.min, self._wavelength_range.max, "Sweep start wavelength"
        )
        self._validate_range(
            stop, self._wavelength_range.min, self._wavelength_range.max, "Sweep stop wavelength"
        )
        self._validate_range(step, self._step_range.min, self._step_range.max, "Sweep wavelength step")
        if stop < (start + step):
            raise ValueError("Sweep stop wavelength must cover at least one step from start.")

        self._write(f"WSET {start:.3f},{stop:.3f},{step:.3f}")

    @rpc_method
    def get_sweep_wavelengths(self) -> tuple[float, float, float]:
        """Return the configured sweep start, stop, and step wavelengths.

        Raises:
            QMI_InstrumentException: If the response does not contain three values.
        """
        command = "WSET?"
        values = self._parse_float_list(command, self._ask(command))
        if len(values) != 3:
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {values!r}")

        return values[0], values[1], values[2]

    @rpc_method
    def set_sweep_speed(self, speed: float) -> None:
        """Set the sweep speed in nanometers per second.

        Parameters:
            speed: Speed in nanometers / second.

        Raises:
            ValueError: If ``speed`` is outside the supported range.
        """
        self._validate_range(speed, self._sweep_speed_range.min, self._sweep_speed_range.max, "Sweep speed")
        self._write(f"SPE {speed:.3f}")

    @rpc_method
    def get_sweep_speed(self) -> float:
        """Return the sweep speed in nanometers per second."""
        command = "SPE?"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def set_gain(self, gain: int) -> None:
        """Set the common TIA gain level.

        Parameters:
            gain: Gain level value.

        Raises:
            QMI_InstrumentException: If the module is an MPM-215.
            ValueError:              If ``gain`` is not from 1 through 5 (1 through 4 for the MPM-213).
        """
        self._validate_gain(gain)
        self._write(f"LEV {gain}")

    @rpc_method
    def get_gain(self) -> int:
        """Return the common TIA gain level.

        Raises:
            QMI_InstrumentException: If the module is an MPM-215.
        """
        self._check_gain_supported()
        command = "LEV?"
        return self._parse_int(command, self._ask(command))

    @rpc_method
    def set_channel_gain(self, channel: int, gain: int) -> None:
        """Set the TIA gain level for one channel.

        Parameters:
            channel: Channel number.
            gain:    Gain level value.

        Raises:
            QMI_InstrumentException: If the module is an MPM-215.
            ValueError:              If ``channel`` or ``gain`` is invalid.
        """
        self._validate_gain(gain)
        self._validate_channel(channel)
        self._write(f"DLEV {self._slot},{channel},{gain}")

    @rpc_method
    def get_channel_gain(self, channel: int) -> int:
        """Return the TIA gain level for one channel.

        Parameters:
            channel:    Channel number.

        Raises:
            QMI_InstrumentException: If the module is an MPM-215.
            ValueError:              If ``channel`` is invalid.
        """
        self._check_gain_supported()
        self._validate_channel(channel)
        command = f"DLEV? {self._slot},{channel}"
        return self._parse_int(command, self._ask(command))

    @rpc_method
    def set_averaging_time(self, avg_time: float) -> None:
        """Set the averaging time in milliseconds.

        Parameters:
            avg_time: Averaging time in milliseconds.

        Raises:
            ValueError: If ``avg_time`` is outside the supported range.
        """
        self._validate_range(
            avg_time, self._averaging_time_range.min, self._averaging_time_range.max, "Averaging time"
        )
        self._write(f"AVG {avg_time:.2f}")

    @rpc_method
    def get_averaging_time(self) -> float:
        """Return the averaging time in milliseconds."""
        command = "AVG?"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def set_fast_gain_switching_averaging_time(self, avg_time: float) -> None:
        """Set the fast-gain-switching averaging time in milliseconds.

        Parameters:
            avg_time: Averaging time in milliseconds.

        Raises:
            ValueError: If ``avg_time`` is outside the supported range.
        """
        self._validate_range(
            avg_time,
            self._averaging_time_range.min,
            self._averaging_time_range.max,
            "Fast gain switching averaging time",
        )
        self._write(f"FGSAVG {avg_time:.2f}")

    @rpc_method
    def get_fast_gain_switching_averaging_time(self) -> float:
        """Return the fast-gain-switching averaging time in milliseconds."""
        command = "FGSAVG?"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def set_measurement_unit_to_milliwatts(self) -> None:
        """Set the measurement unit to mW (mA for the MPM-213 current meter module)."""
        self._write("UNIT 1")

    @rpc_method
    def set_measurement_unit_to_dbm(self) -> None:
        """Set the measurement unit to dBm (dBmA for the MPM-213 current meter module)."""
        self._write("UNIT 0")

    @rpc_method
    def get_measurement_unit(self) -> str:
        """Return the selected measurement unit.

        Returns:
            "dBm" or "mW" for optical power modules, "dBmA" or "mA" for the MPM-213 current meter module.

        Raises:
            QMI_InstrumentException: If the response is not 0 or 1.
        """
        command = "UNIT?"
        value = self._parse_int(command, self._ask(command))
        if value not in (0, 1):
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {value!r}")

        if self._module == "MPM-213":
            return "mA" if value else "dBmA"

        return "mW" if value else "dBm"

    @rpc_method
    def set_power_range_to_manual(self) -> None:
        """Set the power range to manual."""
        self._write("AUTO 0")

    @rpc_method
    def set_power_range_to_auto(self) -> None:
        """Set the power range to automatic."""
        self._write("AUTO 1")

    @rpc_method
    def get_auto_power_range(self) -> bool:
        """Return True when common READ-query range selection is automatic, and
        False when it is manual.

        Raises:
            QMI_InstrumentException: If the response is not 0 or 1.
        """
        command = "AUTO?"
        value = self._parse_int(command, self._ask(command))
        if value not in (0, 1):
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {value!r}")

        return bool(value)

    @rpc_method
    def set_module_power_range_to_manual(self) -> None:
        """Set READ-query range selection for all channels in this module to manual."""
        self._write(f"DAUTO {self._slot},0")

    @rpc_method
    def set_module_power_range_to_auto(self) -> None:
        """Set READ-query range selection for all channels in this module to automatic."""
        self._write(f"DAUTO {self._slot},1")

    @rpc_method
    def get_module_auto_power_range(self) -> bool:
        """Return True when this module uses automatic READ-query range selection. By manual,
        return False.

        Raises:
            QMI_InstrumentException: If the response is not 0 or 1.
        """
        command = f"DAUTO? {self._slot}"
        value = self._parse_int(command, self._ask(command))
        if value not in (0, 1):
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {value!r}")

        return bool(value)

    @rpc_method
    def read_power(self) -> list[float]:
        """Measure and return the power or current from every channel in this module."""
        command = f"READ? {self._slot}"
        return self._parse_float_list(command, self._ask(command))

    @rpc_method
    def get_calibration_wavelength(self, index: int) -> float:
        """Return a calibration wavelength of given index in nanometers. The MPM-210H has 20 calibrated wavelengths,
        from 1250nm to 1630nm with 20nm space. Therefore indexes 1, 2, ..., 19, 20 refer to wavelengths
        1250nm, 1270nm, ..., 1610nm, 1630nm.

        Wavelength between each calibrated wavelength is calculated using 1st order linear interpolation:
            ``y = (y1-y0)/(x1-x0)*(x-x0) + y0``
        where x is wavelength, y is optical power offset.

        Parameters:
            index: Wavelength set order index.

        Raises:
            ValueError: If ``index`` is not from 1 through 20.
        """
        if not self._is_int_in(index, range(1, 21)):
            raise ValueError("Calibration wavelength index must be an integer from 1 through 20.")

        command = f"CWAV? {self._slot},{index}"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def get_channel_calibration_offset(self, channel: int, index: int) -> float:
        """Return one channel's power calibration offset in decibels.

        Parameters:
            channel: The module channel number to get the power calibration offset for.
            index:   Wavelength set order index.

        Raises:
            ValueError: If ``channel`` is invalid or ``index`` is not from 1 through 20.
        """
        self._validate_channel(channel)
        if not self._is_int_in(index, range(1, 21)):
            raise ValueError("Calibration wavelength index must be an integer from 1 through 20.")

        command = f"CWAVPO? {self._slot},{channel},{index}"
        return self._parse_float(command, self._ask(command))

    @rpc_method
    def start_measurement(self) -> None:
        """Start a logging measurement."""
        self._write("MEAS")

    @rpc_method
    def stop_measurement(self) -> None:
        """Stop the active logging measurement."""
        self._write("STOP")

    @rpc_method
    def get_measurement_status(self) -> tuple[int, int]:
        """Return the measurement status code and number of measured logging points.

        Raises:
            QMI_InstrumentException: If the response does not contain two integer values.
        """
        command = "STAT?"
        values = self._parse_int_list(command, self._ask(command))
        if len(values) != 2 or values[0] not in (-1, 0, 1):
            raise QMI_InstrumentException(f"Unexpected response to {command!r}: {values!r}")

        return values[0], values[1]

    @rpc_method
    def set_logging_points(self, points: int) -> None:
        """Set the number of logging points for CONST or FREERUN measurements.

        Parameters:
            points: Number of logging points.

        Raises:
            ValueError: If ``points`` is not from 1 through 1,000,000.
        """
        if not self._is_int_in(points, range(1, 1_000_001)):
            raise ValueError("Logging points must be an integer from 1 through 1000000.")
        self._write(f"LOGN {points}")

    @rpc_method
    def get_logging_points(self) -> int:
        """Return the configured number of logging points."""
        command = "LOGN?"
        return self._parse_int(command, self._ask(command))

    @rpc_method
    def get_logged_data(self, channel: int) -> list[float]:
        """Return binary logged measurement data for one channel.

        This operation is supported through TCP and GPIB, but not through the
        MPM-210H serial interface.

        Parameters:
            channel: The channel number to get the log data for.

        Raises:
            QMI_InstrumentException: If serial transport is selected or binary data is malformed.
            ValueError: If ``channel`` is invalid.
        """
        self._validate_channel(channel)
        if self._transport_type == 'serial':
            raise QMI_InstrumentException("LOGG? is not available through a serial transport.")

        self._check_is_open()
        command = f"LOGG? {self._slot},{channel}"
        self._protocol.write(command, self.DEFAULT_RESPONSE_TIMEOUT)
        if self._transport_type == 'gpib':
            # GPIB delivers the complete binary block as one EOI-delimited message.
            data = self._transport.read_until(b"", timeout=self.DEFAULT_RESPONSE_TIMEOUT)
            if not data:
                raise QMI_TimeoutException(f"No response received to {command!r}.")

            digits = self._parse_block_digits(data[:2])
            length = self._parse_block_length(data[2:2 + digits], digits)
            payload = data[2 + digits:2 + digits + length]
            trailer = data[2 + digits + length:]
        else:
            # TCP is a byte stream, so the header is read first to learn the payload length.
            digits = self._parse_block_digits(self._transport.read(2, timeout=self.DEFAULT_RESPONSE_TIMEOUT))
            length = self._parse_block_length(
                self._transport.read(digits, timeout=self.DEFAULT_RESPONSE_TIMEOUT), digits
            )
            payload = self._transport.read(length, timeout=self.DEFAULT_RESPONSE_TIMEOUT)
            # The manual does not document a terminator after the binary block. Consume a possible CR+LF, so that
            # it is not mistaken for the response to the next query.
            trailer = self._transport.read_until_timeout(2, timeout=self.BLOCK_TRAILER_TIMEOUT)

        if len(payload) != length or length % 4 != 0:
            raise QMI_InstrumentException(f"Invalid LOGG? payload length: {len(payload)}")

        if trailer.strip(b"\r\n"):
            raise QMI_InstrumentException(f"Unexpected data after LOGG? payload: {trailer!r}")

        return list(struct.unpack(f"<{length // 4}f", payload))

    @rpc_method
    def zero(self) -> None:
        """Start the module zeroing operation. This command action takes about 3 seconds.

        NOTE: The manufacturer recommends to remove the BNC cable from the MPM-213 during zeroing,
              when using the current meter module MPM-213.
        """
        self._write("ZERO")
        sleep(self.ZEROING_WAIT_TIME)
