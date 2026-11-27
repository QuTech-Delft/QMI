"""Instrument driver for the NKT Photonics Katana 05 HP laser source. The controller is connected
via USB using a serial port. The code is very similar to the NKT Photonics Fianium supercontinuum laser.
Commands can be found in the Katana HP Operation manual.

Written by Julius Fischer (julius.fischer@tudelft.nl).
"""

import logging

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class NKT_Katana(QMI_Instrument):
    """Instrument driver for the NKT Photonics Katana 05 HP laser."""

    # Instrument should respond within 0.5 seconds.
    RESPONSE_TIMEOUT = 0.5

    # Line feed (LF) code. Commands should be sent as ASCII strings terminated by this. The laser replies are in the
    # same format.
    CR_CODE = "\n"

    # Valid trigger sources for `set_trigger_source`.
    TRIGGER_SOURCES = (0, 1, 2)

    # External trigger input level range in volts.
    TRIGGER_INPUT_LEVEL_RANGE = (-5.0, 5.0)

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """The class constructor.

        Parameters:
            context:   The QMI context this driver is running in.
            name:      Name for the instrument driver for the context registration.
            transport: QMI transport descriptor string for the serial connection, e.g. "serial:COM1".
        """
        super().__init__(context, name)
        self._transport = create_transport(
            transport,
            default_attributes={"baudrate": 38400, "bytesize": 8, "parity": "N", "stopbits": 1.0},
        )

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

    def _read_line(self) -> str:
        """Read one response line from the instrument and return it without the trailing line terminator."""
        resp = self._transport.read_until(message_terminator=str.encode(self.CR_CODE), timeout=self.RESPONSE_TIMEOUT)
        return resp.rstrip().decode("ascii")

    def _ask(self, cmd: str) -> str:
        """Send command to instrument and return the first response line from instrument.

        Parameters:
            cmd: The command string, without the line feed terminator.

        Returns:
            The first response line, without the trailing line terminator.
        """

        self._check_is_open()

        # Avoid reading stale response from instrument.
        self._transport.discard_read()

        # Send command.
        self._transport.write((cmd + "\n").encode("ascii"))

        # Read response.
        return self._read_line()

    def _query_version(self) -> tuple[str, str, str]:
        """Send the "version?" command and read all three lines of the response.

        Returns:
            The firmware version line, the model line and the date line, without line terminators.
        """
        firmware_version = self._ask("version?")
        model = self._read_line()
        date = self._read_line()
        return firmware_version, model, date

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument model and firmware version and return QMI_InstrumentIdentification instance.

        The laser does not report a serial number, so the `serial` field is None.
        """
        firmware_version, model, _ = self._query_version()
        # The model line starts with a label, e.g. "Model:", which is not part of the model name.
        model = model.split(":", 1)[-1].strip()
        return QMI_InstrumentIdentification(vendor="NKT", model=model, serial=None, version=firmware_version)

    @rpc_method
    def get_emission_status(self) -> str:
        """Get laser emission status."""
        return self._ask("le?")

    @rpc_method
    def set_emission_on(self) -> str:
        """Turn on laser emission."""
        return self._ask("le=1")

    @rpc_method
    def set_emission_off(self) -> str:
        """Turn off laser emission."""
        return self._ask("le=0")

    @rpc_method
    def set_trigger_input_level(self, voltage: float) -> str:
        """Set the external trigger input level.

        Parameters:
            voltage: The trigger input level in volts, between -5 and 5.

        Raises:
            ValueError: If the voltage is outside the range [-5, 5] V.
        """
        low, high = self.TRIGGER_INPUT_LEVEL_RANGE
        if not low <= voltage <= high:
            raise ValueError(f"Trigger input level {voltage} V is outside the range [{low}, {high}] V.")

        return self._ask("ltll=" + f"{voltage:.2f}".zfill(5))

    @rpc_method
    def get_trigger_input_level(self) -> str:
        """Get external trigger input level."""
        return self._ask("ltll?")

    @rpc_method
    def set_trigger_source(self, mode: int) -> str:
        """Set the trigger source.

        Parameters:
            mode: Internal trigger (0), external trigger Tr-1 In (1) or external trigger Tr-2 In (2).

        Raises:
            ValueError: If the mode is not 0, 1 or 2.
        """
        if mode not in self.TRIGGER_SOURCES:
            raise ValueError(f"Invalid trigger source {mode}, must be one of {self.TRIGGER_SOURCES}.")

        return self._ask(f"lts={int(mode)}")

    @rpc_method
    def get_trigger_source(self) -> str:
        """Get trigger source."""
        return self._ask("lts?")

    @rpc_method
    def set_laser_power_mode(self) -> str:
        """Set the laser to power mode, where the output power setpoint controls the laser."""
        return self._ask("lip=0")

    @rpc_method
    def set_laser_current_mode(self) -> str:
        """Set the laser to current mode, where the pump current setpoint controls the laser."""
        return self._ask("lip=1")

    @rpc_method
    def set_laser_output_power(self, power: float) -> str:
        """Set the laser output power.

        Parameters:
            power: The output power in mW, between 0 and 4.1.
        """
        return self._ask("lp=" + f"{power:.2f}".zfill(5))

    @rpc_method
    def get_laser_output_power(self) -> str:
        """Get laser output power."""
        return self._ask("lp?")

    @rpc_method
    def set_laser_pump_current(self, current: float) -> str:
        """Set the laser pump current.

        Parameters:
            current: The pump current, between 0 and 12.
        """
        return self._ask("li=" + f"{current:.2f}".zfill(5))

    @rpc_method
    def get_laser_pump_current(self) -> str:
        """Get laser pump current."""
        return self._ask("li?")

    @rpc_method
    def set_initial_power_level(self, power: float) -> str:
        """Set the laser initial power level.

        Parameters:
            power: The initial power level, between 0 and 1.6.
        """
        return self._ask("lx_ips=" + f"{power:.3f}")

    @rpc_method
    def get_initial_power_level(self) -> str:
        """Get laser initial power level."""
        return self._ask("lx_ips?")

    @rpc_method
    def set_frequency(self, frequency: int) -> str:
        """Set the laser repetition frequency.

        Parameters:
            frequency: The repetition frequency in Hz.
        """
        return self._ask(f"lx_freq={frequency}")

    @rpc_method
    def get_frequency(self) -> str:
        """Get laser repetition frequency."""
        return self._ask("lx_freq?")

    @rpc_method
    def get_firmware_version(self) -> str:
        """Get the firmware version.

        The "version?" command replies with three lines; all of them are read so that none is left in the input
        buffer, and the first line, holding the firmware version, is returned.
        """
        firmware_version, _, _ = self._query_version()
        return firmware_version

    @rpc_method
    def get_last_response(self) -> str:
        """Read the next pending response line from the instrument without sending a command, for debugging."""
        self._check_is_open()
        return self._read_line()
