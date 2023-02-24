"""
Instrument driver for the Wavelength Electronics TC Lab temperature controller.
"""

import enum
import logging
import re
import time
from typing import List, NamedTuple, Set, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport, list_usbtmc_transports, UsbTmcTransportDescriptorParser


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class AutotuneMode(enum.IntEnum):
    """Autotune modes."""
    MANUAL = 0
    DISTURB_REJECT = 1
    SETPOINT_RESPONSE = 2


class TemperatureControllerCondition(NamedTuple):
    """Condition status register of the temperature controller."""
    current_limit:      bool
    sensor_limit:       bool
    temperature_high:   bool
    temperature_low:    bool
    sensor_shorted:     bool
    sensor_open:        bool
    tec_open:           bool
    in_tolerance:       bool
    output_on:          bool
    laser_shutdown:     bool
    power_on:           bool


class Wavelength_TC_Lab(QMI_Instrument):
    """Instrument driver for the Wavelength Electronics TC Lab temperature controller.

    A subset of the instrument functionality is supported.
    Configuring temperature sensors and sensor parameters is not supported.
    The auxiliary temperature sensor is not supported.
    """

    USB_VENDOR_ID = 0x1a45
    USB_PRODUCT_ID = 0x3101

    # Response timeout for normal commands.
    COMMAND_RESPONSE_TIMEOUT = 2.0

    # The instrument sometimes refuses to report its own USB serial number.
    # As a result, the instrument is not recognized by this driver (about 10%
    # of the attempts to open it).
    # As a workaround we retry opening the instrument a few times.
    OPEN_MAX_RETRY = 5

    @staticmethod
    def list_instruments() -> List[str]:
        """Return a list of QMI transport descriptors for attached instruments."""
        instruments: Set[str] = set()
        for _i in range(Wavelength_TC_Lab.OPEN_MAX_RETRY):
            for transport in list_usbtmc_transports():
                parameters = UsbTmcTransportDescriptorParser.parse_parameter_strings(transport)
                if ((parameters.get("vendorid") == Wavelength_TC_Lab.USB_VENDOR_ID)
                        and (parameters.get("productid") == Wavelength_TC_Lab.USB_PRODUCT_ID)):
                    instruments.add(transport)
        return list(instruments)

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
                        The transport descriptor will typically specify a USBTMC instrument,
                        for example "usbtmc:vendorid=0x1a45:productid=0x3103:serialnr=xxx".
        """
        super().__init__(context, name)
        self._transport = create_transport(transport)
        self._scpi_protocol = ScpiProtocol(self._transport, default_timeout=self.COMMAND_RESPONSE_TIMEOUT)

    def _open_transport(self) -> None:
        """Open transport to the instrument and retry if necessary."""

        # The instrument sometimes refuses to report its own USB serial number.
        # In this case, libusb will not recognize the instrument when we specify
        # it by serial number.
        # As a workaround we retry opening the instrument a few times.
        retry = 0
        while True:
            try:
                self._transport.open()
                return
            except Exception:
                if retry >= self.OPEN_MAX_RETRY:
                    raise
                if retry == 0:
                    _logger.warning("[%s] Failed to open instrument, retrying", self._name)
            time.sleep(0.01)
            retry += 1

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._open_transport()
        try:
            # Discard pending errors.
            self._scpi_protocol.write("*CLS")
            self._scpi_protocol.ask("ERRSTR?")
            # Switch instrument to decimal mode (avoid hex mode).
            self._scpi_protocol.write("RADIX DEC")
        except Exception:
            self._transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        resp = self._scpi_protocol.ask("ERRSTR?")
        # When there are no errors, the response is '0,No error'.
        if not re.match(r"^\s*([-+]\s*)?0\s*,", resp):
            # Some error occurred.
            raise QMI_InstrumentException("Instrument returned error: {}".format(resp))

    def _ask_int(self, cmd: str) -> int:
        """Send a query and return an integer response."""
        resp = self._scpi_protocol.ask(cmd)
        try:
            return int(resp)
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating point response."""
        resp = self._scpi_protocol.ask(cmd)
        try:
            return float(resp)
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    @rpc_method
    def reset(self) -> None:
        """Reset instrument to factory default settings."""
        self._scpi_protocol.write("*CLS")  # clear error queue
        self._scpi_protocol.write("*RST")  # factory reset
        self._scpi_protocol.ask("*OPC?")  # wait until reset complete
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(resp))
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def get_power_on(self) -> bool:
        """Return True if the device is powered on, False when in standby."""
        return bool(self._ask_int("PWR?"))

    @rpc_method
    def set_power_on(self, power_on: bool) -> None:
        """Switch between power-on and standby mode.

        This corresponds to pressing the "power" button on the front panel.
        While the device is in standby mode, it responds to remote commands
        but many commands will cause the instrument to report error code 992.

        When switching power on, this function returns immediately but it can
        take a few seconds before the instrument is ready to respond to commands.

        Parameters:
            power_on: True to switch to power-on mode, False to switch to standby mode.
        """
        self._scpi_protocol.write("PWR {}".format(1 if power_on else 0))
        self._check_error()

    @rpc_method
    def get_temperature(self) -> float:
        """Read the actual temperature.

        Returns:
            Actual sensor temperature expressed in the selected unit of temperature (see `set_unit()`).
        """
        return self._ask_float("TEC:ACT?")

    @rpc_method
    def get_setpoint(self) -> float:
        """Return the actual temperature setpoint.

        Returns:
            Actual temperature setpoint expressed in the selected unit of temperature (see `set_unit()`).
        """
        return self._ask_float("TEC:SET?")

    @rpc_method
    def set_setpoint(self, setpoint: float) -> None:
        """Change the temperature setpoint.

        It is not possible to set the setpoint outside the temperature limit range (see `set_temperature_limit()`).

        Parameters:
            setpoint: New temperature setpoint expressed in the selected unit of temperature (see `set_unit()`).
        """
        self._scpi_protocol.write("TEC:SET {:.6f}".format(setpoint))
        self._check_error()

    @rpc_method
    def get_unit(self) -> str:
        """Return the selected physical unit of temperature.

        The selected unit is used to report the actual temperature and to set or report the temperature setpoint.

        Returns:
            Unit, either "CELSIUS", "KELVIN", "FAHRENHEIT" or "RAW".
        """
        return self._scpi_protocol.ask("TEC:UNITS?")

    @rpc_method
    def set_unit(self, unit: str) -> None:
        """Change the select physical unit of temperature.

        The selected unit is used to report the actual temperature and to set or report the temperature setpoint.
        The default setting is "CELSIUS".

        Parameters:
            unit: Selected unit, either "CELSIUS", "KELVIN", "FAHRENHEIT" or "RAW".
        """
        unit_str = unit.upper()
        if unit_str not in ("CELSIUS", "KELVIN", "FAHRENHEIT", "RAW"):
            raise ValueError("Unsupported temperature unit")
        self._scpi_protocol.write("TEC:UNITS {}".format(unit_str))
        self._check_error()

    @rpc_method
    def get_tec_current(self) -> float:
        """Read the actual current through the thermoelectric element in Ampere."""
        return self._ask_float("TEC:I?")

    @rpc_method
    def get_tec_voltage(self) -> float:
        """Read the actual voltage on the thermoelectric element in Volt."""
        return self._ask_float("TEC:V?")

    @rpc_method
    def get_output_enabled(self) -> bool:
        """Return True if the controller output is enabled, False if disabled."""
        return bool(self._ask_int("TEC:OUTPUT?"))

    @rpc_method
    def set_output_enabled(self, enable: bool) -> None:
        """Enable or disable the controller output."""
        self._scpi_protocol.write("TEC:OUTPUT {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_condition_status(self) -> TemperatureControllerCondition:
        """Read the current condition of the instrument."""
        v = self._ask_int("TEC:COND?")
        return TemperatureControllerCondition(
            current_limit=((v & 1) != 0),
            sensor_limit=((v & 4) != 0),
            temperature_high=((v & 8) != 0),
            temperature_low=((v & 16) != 0),
            sensor_shorted=((v & 32) != 0),
            sensor_open=((v & 64) != 0),
            tec_open=((v & 128) != 0),
            in_tolerance=((v & 512) != 0),
            output_on=((v & 1024) != 0),
            laser_shutdown=((v & 2048) != 0),
            power_on=((v & 32768) != 0))

    @rpc_method
    def get_pid_parameters(self) -> Tuple[float, float, float]:
        """Return the actual PID control parameters.

        Returns:
            Tuple (p, i, d) of PID parameters.
        """
        cmd = "TEC:PID?"
        resp = self._scpi_protocol.ask(cmd)
        fields = resp.split(",")
        if len(fields) != 3:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))
        try:
            return (float(fields[0]), float(fields[1]), float(fields[2]))
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    @rpc_method
    def set_pid_parameters(self, p: float, i: float, d: float) -> None:
        """Change the PID control parameters.

        Parameters:
            p: Proportional control parameter, range 0.1 ... 1000.
            i: Integral control parameter, range 0 ... 200.
            d: Derivative control parameter, range 0 ... 100.
        """
        self._scpi_protocol.write("TEC:PID {:.4f},{:.4f},{:.4f}".format(p, i, d))
        self._check_error()

    @rpc_method
    def get_autotune_mode(self) -> AutotuneMode:
        """Read the actual autotune mode."""
        mode = self._ask_int("TEC:AUTOTUNE?")
        return AutotuneMode(mode)

    @rpc_method
    def set_autotune_mode(self, mode: AutotuneMode) -> None:
        """Change the autotune mode.

        In *manual* mode, the PID parameters must be specified explicitly.
        In *disturbance rejection* and *setpoint response* modes, the instrument
        automatically adjusts the PID parameters to match the actual setpoint.

        A one-time characterization scan must be performed before autotune mode
        can be used, see `start_autotune()`.

        Even in autotune mode, the operator can choose to use a derivative
        control parameter (D) or to force it to zero. Call `set_pid_parameters()`
        to set the D parameter either to zero or to any non-zero value,
        the call `set_autotune_mode()` to set the corresponding autotuned parameters.

        Parameters:
            mode: The new autotune mode (one of the `AutotuneMode` constants).
        """
        mode = AutotuneMode(mode)
        self._scpi_protocol.write("TEC:AUTOTUNE {}".format(mode.value))
        self._check_error()

    @rpc_method
    def start_autotune(self) -> None:
        """Start an autotuning characterization scan.

        Before calling this function, first turn off the controller output,
        select one of the autotune modes, and change the setpoint to approximately
        5 degrees away from the ambient temperature. For example::

            instr.set_output_enabled(False)
            instr.set_autotune_mode(AutotuneMode.DISTURB_REJECT)
            instr.set_setpoint(ambient_temp + 5.0)
            instr.start_autotune()

        The characterization scan may take several minutes.
        Once characterization is complete, `get_autotune_valid()` will return True.
        Call `abort_autotune()` to stop the characterization scan and go back to previous settings.
        Do not otherwise interact with the instrument while characterization is in progress.
        """
        self._scpi_protocol.write("TEC:TUNESTART")
        self._check_error()

    @rpc_method
    def abort_autotune(self) -> None:
        """Stop the current autotune characterization scan."""
        self._scpi_protocol.write("TEC:TUNEABORT")
        self._check_error()

    @rpc_method
    def get_autotune_is_valid(self) -> bool:
        """Return True if the instrument has valid autotuning characterization data for the current sensor.

        This variable becomes True after a successful autotuning characterization scan,
        and typically stays True until the sensor type is reconfigured.
        """
        return bool(self._ask_int("TEC:VALID?"))

    @rpc_method
    def get_temperature_limit(self) -> Tuple[float, float]:
        """Return the temperature limits.

        Returns:
            Tuple (temp_low, temp_high) representing the temperature limits
            of the sensor, expressed in the selected unit of temperature
            (see `set_unit()`).
        """
        temp_low = self._ask_float("TEC:LIM:TLO?")
        temp_high = self._ask_float("TEC:LIM:THI?")
        return (temp_low, temp_high)

    @rpc_method
    def set_temperature_limit(self, temp_low: float, temp_high: float) -> None:
        """Configure the temperature limits.

        When the actual temperature exceeds these limits, the controller output is disabled.

        The temperature setpoint is restricted to these limits.

        Parameters:
            temp_low: Low temperature limit, expressed in the selected unit of temperature.
            temp_high: High temperature limit, expressed in th selected unit of temperature.
        """
        self._scpi_protocol.write("TEC:LIM:TLO {:.4f}".format(temp_low))
        self._scpi_protocol.write("TEC:LIM:THI {:.4f}".format(temp_high))
        self._check_error()

    @rpc_method
    def get_tec_current_limit(self) -> Tuple[float, float]:
        """Read the current limits for the thermoelectric element.

        Returns:
            Tuple (lim_pos, lim_neg) representing the maximum positive
            and negative current in Ampere. The maximum negative current
            is reported as a positive number.
        """
        lim_pos = self._ask_float("TEC:LIM:IPOS?")
        lim_neg = self._ask_float("TEC:LIM:INEG?")
        return (lim_pos, lim_neg)

    @rpc_method
    def set_tec_current_limit(self, lim_pos: float, lim_neg: float) -> None:
        """Configure the current limits for the thermoelectric element.

        **Warning:** Setting incorrect current limits can damage the thermoelectric element
        and cause safety hazards.

        The valid range for these settings is from 0 to the maximum current capability of the instrument,
        i.e. 5 A for TC5 LAB, etc.

        To operate a resistive heater, set one of these limits to zero.

        Parameters:
            lim_pos: Maximum positive current in Ampere.
            lim_neg: Maximum negative current in Ampere, represented as a positive number.
        """
        self._scpi_protocol.write("TEC:LIM:IPOS {:.4f}".format(lim_pos))
        self._scpi_protocol.write("TEC:LIM:INEG {:.4f}".format(lim_neg))
        self._check_error()

    @rpc_method
    def get_tec_voltage_limit(self) -> float:
        """Read the actual voltage limit for the thermoelectric element in Volt."""
        return self._ask_float("TEC:VLIM?")

    @rpc_method
    def set_tec_voltage_limit(self, vlim: float) -> None:
        """Set the voltage limit for the thermoelectric element.

        The autotuning process determines an optimal setting for this parameter.

        Parameters:
            vlim: New voltage limit in Volt
                  (valid range 9 ... 18 for TC5 LAB, TC10 LAB, 10 ... 26 for TC15 LAB).
        """
        self._scpi_protocol.write("TEC:VLIM {:.4f}".format(vlim))
        self._check_error()
