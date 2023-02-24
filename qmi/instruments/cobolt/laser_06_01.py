"""Instrument driver for the Cobolt CW Laser
"""

import logging

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Cobolt_Laser_06_01(QMI_Instrument):
    """Instrument driver for the Cobolt 06-01 series diode laser."""

    _rpc_constants = ["FAULT_CODES", "OPERATING_MODES"]

    # Fault codes returned by get_operating_fault().
    FAULT_CODES = {
        0: "no errors",
        1: "temperature error",
        3: "interlock error",
        4: "constant power time out"
    }

    # Operating modes returned by get_operating_mode().
    OPERATING_MODES = {
        0: "Off",
        1: "Waiting for key",
        2: "Continuous",
        3: "On/Off Modulation",
        4: "Modulation",
        5: "Fault",
        6: "Aborted"
    }

    # Instrument should respond within 2 seconds.
    RESPONSE_TIMEOUT = 2.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200})

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
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        _logger.info("Resetting %s", self._name)
        self._write("@cob1")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        serial = self._ask("gsn?")
        return QMI_InstrumentIdentification(vendor="Cobolt",
                                            model="06-01",
                                            serial=serial,
                                            version=None)

    def _write(self, cmd: str) -> None:
        """Send command to instrument and check instrument responds with "OK"."""

        self._check_is_open()

        # Avoid reading stale response from instrument.
        self._transport.discard_read()

        # Send command.
        self._transport.write(cmd.encode('ascii') + b"\r")

        # Read response.
        # NOTE: Manual says response is terminated by "\r",
        # but actual device terminates with "\r\n".
        resp = self._transport.read_until(message_terminator=b"\n",
                                          timeout=self.RESPONSE_TIMEOUT)
        if resp.rstrip() != b"OK":
            raise QMI_InstrumentException(
                "Expecting 'OK' response to command {!r} but got {!r}".format(cmd, resp))

    def _ask(self, cmd: str) -> str:
        """Send command to instrument and return response from instrument."""

        self._check_is_open()

        # Avoid reading stale response from instrument.
        self._transport.discard_read()

        # Send command.
        self._transport.write(cmd.encode('ascii') + b"\r")

        # Read response.
        resp = self._transport.read_until(message_terminator=b"\n",
                                          timeout=self.RESPONSE_TIMEOUT)

        return resp.rstrip().decode('ascii', errors='replace')

    @staticmethod
    def _parse_int(s: str) -> int:
        """Parse integer response from laser.

        Return integer value or raise QMI_InstrumentException.
        """
        try:
            return int(s)
        except ValueError:
            raise QMI_InstrumentException("Expecting integer from instrument but got {!r}".format(s))

    @staticmethod
    def _parse_float(s: str) -> float:
        """Parse floating point response from laser.

        Return float value or raise QMI_InstrumentException.
        """
        try:
            return float(s)
        except ValueError:
            raise QMI_InstrumentException("Expecting float from instrument but got {!r}".format(s))

    @staticmethod
    def _parse_bool(s: str) -> bool:
        """Parse boolean response from laser.

        Return response mapped to boolean value (0=False, 1=True) or raise QMI_InstrumentException.
        """
        try:
            v = int(s)
            if v == 0:
                return False
            elif v == 1:
                return True
        except ValueError:
            # error will be handled below
            pass
        raise QMI_InstrumentException("Expecting 0 or 1 from instrument but got {!r}".format(s))

    @rpc_method
    def get_laser_on_state(self) -> bool:
        """Return True if the laser is on, False if it is off."""
        resp = self._ask("l?")
        return self._parse_bool(resp)

    @rpc_method
    def set_laser_on_state(self, value: bool) -> None:
        """Set the laser on or off."""
        if value:
            _logger.info("Setting laser ON")
            cmd = "l1"
        else:
            _logger.info("Setting laser OFF")
            cmd = "l0"
        self._write(cmd)

    @rpc_method
    def get_operating_hours(self) -> float:
        """Get number of hours the laser head has operated."""
        resp = self._ask("hrs?")
        return self._parse_float(resp)

    @rpc_method
    def get_interlock_state(self) -> bool:
        """Return True if interlock is open, False if interlock allow laser on."""
        resp = self._ask("ilk?")
        return self._parse_bool(resp)

    @rpc_method
    def get_output_power_setpoint(self) -> float:
        """Get power set point [W]."""
        resp = self._ask("p?")
        return self._parse_float(resp)

    @rpc_method
    def set_output_power_setpoint(self, value: float) -> None:
        """ Set laser output power [W]."""
        self._write("p {:.6f}".format(value))

    @rpc_method
    def get_output_power(self) -> float:
        """Get actual laser output power [W]."""
        resp = self._ask("pa?")
        return self._parse_float(resp)

    @rpc_method
    def get_drive_current(self) -> float:
        """Get laser drive current [mA]"""
        resp = self._ask("i?")
        return self._parse_float(resp)

    @rpc_method
    def set_drive_current(self, value: float) -> None:
        """Set laser drive current [mA]."""
        self._write("slc {:.6f}".format(value))

    @rpc_method
    def set_constant_power_mode(self) -> None:
        """Enter constant power mode."""
        self._write("cp")

    @rpc_method
    def set_constant_current_mode(self) -> None:
        """Enter constant current mode."""
        self._write("ci")

    @rpc_method
    def get_fault(self) -> int:
        """Get operating fault state.

        See Cobolt_Laser_06_01.FAULT_CODES for the meaning of return codes.
        """
        resp = self._ask("f?")
        return self._parse_int(resp)

    @rpc_method
    def clear_fault(self) -> None:
        """Clear laser fault."""
        self._write("cf")

    @rpc_method
    def set_modulation_mode(self) -> None:
        """Enter modulatuion mode."""
        self._write("em")

    @rpc_method
    def get_digital_modulation_state(self) -> bool:
        """Return True if digital modulation is enabled."""
        resp = self._ask("gdmes?")
        return self._parse_bool(resp)

    @rpc_method
    def set_digital_modulation_state(self, value: bool) -> None:
        """Set digital modulation enable state."""
        v = 1 if value else 0
        self._write("sdmes {}".format(v))

    @rpc_method
    def get_analog_modulation_state(self) -> bool:
        """Get analog modulation enable state."""
        resp = self._ask("games?")
        return self._parse_bool(resp)

    @rpc_method
    def set_analog_modulation_state(self, value: bool) -> None:
        """Set analog modulation enable state."""
        v = 1 if value else 0
        self._write("sames {}".format(v))

    @rpc_method
    def get_operating_mode(self) -> int:
        """Get current operating mode.

        See Cobolt_Laser_06_01.OPERATING_MODES for the meaning of return codes.
        """
        resp = self._ask("gom?")
        return self._parse_int(resp)

    @rpc_method
    def get_analog_low_impedance_state(self) -> bool:
        """Return True if analog low impedance (50 Ohm) state is enabled."""
        resp = self._ask("galis?")
        return self._parse_bool(resp)

    @rpc_method
    def set_analog_low_impedance_state(self, value: bool) -> None:
        """Enable or disable analog low impedance (50 Ohm) state."""
        v = 1 if value else 0
        self._write("salis {}".format(v))

    @rpc_method
    def get_autostart_state(self) -> bool:
        """Return True if autostart is enabled.

        NOTE: This command is not in the manual. Private communication with Cobolt.
        """
        resp = self._ask("@cobas?")
        return self._parse_bool(resp)

    @rpc_method
    def set_autostart_state(self, value: bool) -> None:
        """Enable or disable autostart mode.

        NOTE: This command is not in the manual. Private communication with Cobolt.
        """
        v = 1 if value else 0
        self._write("@cobas {}".format(v))
