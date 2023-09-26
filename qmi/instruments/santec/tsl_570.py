"""
Instrument driver for the Santec TSL 570 laser.
"""

import logging
from dataclasses import dataclass
from typing import List, Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class _WavelengthRange:
    """Dataclass for wavelength instrument range."""

    min: float
    max: float


@dataclass
class _FrequencyRange:
    """Dataclass for frequency instrument range."""

    min: float
    max: float


@dataclass
class _PowerLevelRange:
    """Dataclass for power level instrument range."""

    min: float
    max: float


class Santec_Tsl570(QMI_Instrument):
    """Instrument driver for the Santec TSL 570 laser.

    The driver is currently based on running at "Legacy" communication, which is also based on
    SCPI protocol, but perhaps not fully complying to it.
    """

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # power level range in dBm and mW
    POWER_LEVEL_RANGE = {"dBm": (-15.0, 13.0), "mW": (0.04, 20.00)}

    # Valid speeds
    VALID_SPEED_VALUES = [1, 2, 5, 10, 20, 50, 100, 200]

    # System errors
    ERRORS_TABLE = {
        0: "No error",
        -102: "Syntax error",
        -103: "Invalid separator",
        -108: "Parameter not allowed",
        -109: "Missing parameter",
        -113: "Undefined header",
        -148: "Character data not allowed",
        -200: "Execution error",
        -222: "Data out of range",
        -410: "Query INTERRUPTED",
    }

    # System alerts
    ALERTS_TABLE = {
        "No00.": "Power supply Error1",
        "No02.": "Power supply Error2",
        "No03.": "Power supply Error3",
        "No05.": "Wavelength Error",
        "No06.": "Power setting Error",
        "No07.": "Inter lock detection",
        "No20.": "Temperature control Error1",
        "No21.": "Temperature control Error2",
        "No22.": "Temperature control Error3",
        "No23.": "Ongoing Warm up",
        "No25.": "Shutter Error",
        "No26.": "Sensor Error",
        "No27.": "Connection Error",
        "No28.": "Exhaust Fan Error",
    }

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            context:    The QMI context for running the driver in.
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport)
        self._scpi_protocol = ScpiProtocol(
            self._transport,
            command_terminator="\r",
            response_terminator="\r",
            default_timeout=self.DEFAULT_RESPONSE_TIMEOUT,
        )
        # Instrument ranges for values
        self._wavelength_range = _WavelengthRange
        self._frequency_range = _FrequencyRange
        self._power_level_range = _PowerLevelRange

    def _check_error(self) -> List[str]:
        """Read the instrument error queue and raise an exception if there is an error.

        Returns:
            errors + alerts: Listed error and alert response strings.
        """
        errors = []
        # When there are no errors, the response is '0,"No error"'.
        while (error := self._scpi_protocol.ask(":SYST:ERR?")) != '0,"No error"':
            errors.append(self.ERRORS_TABLE[int(error.split(",")[0])])

        alerts = []
        # When there are no alerts, the response is "No alerts.".
        while (alert := self._scpi_protocol.ask(":SYST:ALER?")) != "No alerts.":
            alerts.append(self.ALERTS_TABLE[alert.split(",")[0]])

        return errors + alerts

    def _write_and_check_errors(self, cmd: str) -> None:
        """Write a command to the instrument and check if any errors or alerts were raised.

        Parameters:
            cmd: The input command to send.

        Raises:
            QMI_InstrumentException: If there were errors, errors described in the exception message.
        """
        self._scpi_protocol.write(cmd)
        errors = self._check_error()
        if errors:
            _logger.error("[%s] command [%s] resulted in errors: %s", self._name, cmd, errors)
            raise QMI_InstrumentException(f"Command {cmd} resulted in errors: {errors}")

    def _ask_int(self, cmd: str) -> int:
        """Send a query and return a floating point response."""
        resp = self._scpi_protocol.ask(cmd)
        try:
            return int(resp)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}") from exc

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating point response."""
        resp = self._scpi_protocol.ask(cmd)
        try:
            return float(resp)
        except ValueError as exc:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}") from exc

    def _ask_bool(self, cmd: str) -> bool:
        """Send a query and return a boolean response."""
        resp = self._scpi_protocol.ask(cmd)
        value = resp.strip().upper()
        if value in ("1", "ON"):
            return True
        elif value in ("0", "OFF"):
            return False
        else:
            raise QMI_InstrumentException(f"Unexpected response to command {cmd!r}: {resp!r}")

    def _set_wavelength_unit(self, terahertz: int) -> None:
        """Set the wavelength unit to terahertz or to nanometers.

        Parameters:
            terahertz: Integer to set wavelength unit to terahertz (1) or to nanometer (0)
        """
        self._write_and_check_errors(f":WAV:UNIT {terahertz}")

    def _set_power_level_unit(self, milliwatts: int) -> None:
        """Set the power_level unit to milliwatts or to decibel-milliwatts. Update the minimum and maximum values
        consequently.

        Parameters:
            milliwatts: Integer to set power level unit to milliwatts (1) or to decibel-milliwatts (0)
        """
        self._write_and_check_errors(f":POW:UNIT {milliwatts}")
        # Then update the minimum and maximum values of the instruments to apply for the changed units.
        unit = "mW" if milliwatts else "dBm"
        self._power_level_range.min = self.POWER_LEVEL_RANGE[unit][0]
        self._power_level_range.max = self.POWER_LEVEL_RANGE[unit][1]

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()
        # Then update the minimum and maximum values of the instrument ranges
        self._wavelength_range.min = self.get_minimum_wavelength()
        self._wavelength_range.max = self.get_maximum_wavelength()
        self._frequency_range.min = self.get_minimum_frequency()
        self._frequency_range.max = self.get_maximum_frequency()
        power_unit = self.get_power_level_unit()
        self._power_level_range.min = self.POWER_LEVEL_RANGE[power_unit][0]
        self._power_level_range.max = self.POWER_LEVEL_RANGE[power_unit][1]

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        self._check_is_open()
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument info and return QMI_InstrumentIdentification instance.

        Returns:
            QMI_InstrumentIdentification: Data with e.g. idn.vendor = SANTEC, idn.model = TSL-570,
            idn.serial = 21020001, idn.version = 0001.000.0001 (firmware version).
        """
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(resp))
        return QMI_InstrumentIdentification(
            vendor=words[0].strip(), model=words[1].strip(), serial=words[2].strip(), version=words[3].strip()
        )

    @rpc_method
    def reset(self) -> None:
        """Device reset. Aborts standby operation and clears the command input and error queues."""
        _logger.info("[%s] Resetting instrument", self._name)
        self._write_and_check_errors("*RST")

    @rpc_method
    def clear(self) -> None:
        """Clear Status. Clears all event registers and queues and reflects the summary in the Status Byte Register.
        Clears the following items.
        ・Status Byte Register
        ・Standard Event Status Register
        ・Error Queue
        """
        _logger.info("[%s] Clearing instrument event registers and queues", self._name)
        self._write_and_check_errors("*CLS")

    @rpc_method
    def operation_complete(self) -> bool:
        """Check if the previous operation is completed.

        Returns:
            response: True for yes, False for no.
        """
        response = self._ask_bool("*OPC?")
        return response

    @rpc_method
    def get_errors(self) -> List[str]:
        """Query all errors and alerts.

        Returns:
            errors_and_alerts: A list of all error and alert descriptions.
        """
        return self._check_error()

    @rpc_method
    def set_wavelength(self, wavelength: float) -> None:
        """Set the output wavelength in nanometers.

        Parameters:
            wavelength: The target wavelength in nanometers up to 0.1 pm resolution.

        Raises:
            QMI_InstrumentException: If the wavelength is not in the instrument range.
        """
        unit = "nm"
        dec = 4  # 0.1 pm resolution
        if wavelength < self._wavelength_range.min or wavelength > self._wavelength_range.max:
            raise ValueError(
                f"Wavelength {wavelength:.{dec}f}{unit} out of instrument range "
                f"({self._wavelength_range.min}{unit} - {self._wavelength_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV {wavelength:.{dec}f}")

    @rpc_method
    def get_wavelength(self) -> float:
        """Get the output wavelength. Default unit is nanometers.

        Returns:
            wavelength: The instrument wavelength in nanometers.
        """
        wavelength = self._ask_float(":WAV?")
        return wavelength

    @rpc_method
    def get_minimum_wavelength(self) -> float:
        """Get the minimum wavelength.

        Returns:
            wavelength: The instrument wavelength minimum in nanometers.
        """
        wavelength = self._ask_float(":WAV:MIN?")
        return wavelength

    @rpc_method
    def get_maximum_wavelength(self) -> float:
        """Get the maximum wavelength.

        Returns:
            wavelength: The instrument wavelength maximum in nanometers.
        """
        wavelength = self._ask_float(":WAV:MAX?")
        return wavelength

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """Set the output frequency in terahertz.

        Parameters:
            frequency: The target frequency in terahertz up to 10 MHz resolution.

        Raises:
            QMI_InstrumentException: If the frequency is not in the instrument range.
        """
        unit = "THz"
        dec = 5  # 10 MHz resolution
        if frequency < self._frequency_range.min or frequency > self._frequency_range.max:
            raise ValueError(
                f"frequency {frequency:.{dec}f}{unit} out of instrument range "
                f"({self._frequency_range.min}{unit} - {self._frequency_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV:FREQ {frequency:.{dec}f}")

    @rpc_method
    def get_frequency(self) -> float:
        """Get the output frequency. Unit depends on unit setting.

        Returns:
            frequency: The instrument frequency in terahertz.
        """
        frequency = self._ask_float(":WAV:FREQ?")
        return frequency

    @rpc_method
    def get_minimum_frequency(self) -> float:
        """Get the minimum frequency.

        Returns:
            frequency: The instrument frequency minimum in terahertz.
        """
        frequency = self._ask_float(":WAV:FREQ:MIN?")
        return frequency

    @rpc_method
    def get_maximum_frequency(self) -> float:
        """Get the maximum frequency.

        Returns:
            frequency: The instrument frequency maximum in terahertz.
        """
        frequency = self._ask_float(":WAV:FREQ:MAX?")
        return frequency

    @rpc_method
    def set_wavelength_unit_to_nm(self) -> None:
        """Set the wavelength unit to nanometers."""
        self._set_wavelength_unit(0)

    @rpc_method
    def set_wavelength_unit_to_thz(self) -> None:
        """Set the wavelength unit to terahertz."""
        self._set_wavelength_unit(1)

    @rpc_method
    def get_wavelength_unit(self) -> str:
        """Get the wavelength unit displayed.

        Returns:
            wl_unit: The wavelength unit as either "THz" or "nm".
        """
        wl_unit = self._ask_bool(":WAV:UNIT?")
        return "THz" if wl_unit else "nm"

    @rpc_method
    def set_wavelength_fine(self, value: float) -> None:
        """Set the wavelength fine-tuning value.

        Parameters:
            value: The fine-tuning value in range -100.00 - +100.00 and maximal resolution of 0.01.

        Raises:
            ValueError: If value is not in the correct range.
        """
        if value < -100.0 or value > 100.0:
            raise ValueError(f"Input value {value} not in valid range [-100...+100].")

        rounded_value = round(value, 2)  # Step resolution is 0.01
        self._write_and_check_errors(f":WAV:FIN {rounded_value:.2f}")

    @rpc_method
    def get_wavelength_fine(self) -> float:
        """Get the wavelength fine-tuning value.

        Returns:
            value: The fine-tuning value in range -100.00 - +100.00 and maximal resolution of 0.01.
        """
        return self._ask_float("WAV:FIN?")

    @rpc_method
    def disable_finetuning_operation(self) -> None:
        """Terminate Fine-Tuning operation."""
        self._write_and_check_errors(":WAV:FIN:DIS")

    @rpc_method
    def set_coherence_control_status(self, status: Union[bool, str]) -> None:
        """Set the Coherence control status.

        Parameters:
            status: New status as either True or "ON", or False or "OFF", to set control ON and OFF, respectively.

        Raises:
            AssertionError: If input parameter is a string but neither "ON" or "OFF".
        """
        if isinstance(status, bool):
            i_status = int(status)

        else:
            assert status.upper() in ("ON", "OFF")
            i_status = 0 if status.upper() == "OFF" else 1

        self._write_and_check_errors(f":COHC {i_status}")

    @rpc_method
    def get_coherence_control_status(self) -> str:
        """Get the Coherence control status.

        Returns:
            status: New status as either "ON", or "OFF".
        """
        status = self._ask_int(":COHC?")
        return "ON" if status else "OFF"

    @rpc_method
    def set_optical_output_status(self, status: Union[bool, str]) -> None:
        """Set the optical output status.

        Parameters:
            status: New status as either True or "ON", or False or "OFF", to set control ON and OFF, respectively.

        Raises:
            AssertionError: If input parameter is a string but neither "ON" or "OFF".
        """
        if isinstance(status, bool):
            i_status = int(status)

        else:
            assert status.upper() in ("ON", "OFF")
            i_status = 0 if status.upper() == "OFF" else 1

        self._write_and_check_errors(f":POW:STAT {i_status}")

    @rpc_method
    def get_optical_output_status(self) -> str:
        """Get the optical output status.

        Returns:
            status: New status as either "ON", or "OFF".
        """
        status = self._ask_int(":POW:STAT?")
        return "ON" if status else "OFF"

    @rpc_method
    def set_power_level(self, power_level: float) -> None:
        """Set optical output power level between -15dBm (~0.03mW) and peak power. Typical peak power from the
        datasheet https://santec.imgix.net/TSL-570-Datasheet.pdf is 13dBm (~20.00mW).

        Parameters:
            power_level: power level in decibel-milliwatts or milliwatts.
        """
        unit = self.get_power_level_unit()
        if power_level < self._power_level_range.min or power_level > self._power_level_range.max:
            raise ValueError(
                f"Power level {power_level:.2f}{unit} out of instrument range "
                f"({self._power_level_range.min}{unit} - {self._power_level_range.max}{unit})"
            )

        self._write_and_check_errors(f":POW {power_level:.2f}")

    @rpc_method
    def get_power_level(self) -> float:
        """Get the output power level setting. Unit depends on unit setting.

        Returns:
            power_level: The instrument power level in decibel-milliwatts or milliwatts.
        """
        power_level = self._ask_float(":POW?")
        return round(power_level, 2)

    @rpc_method
    def get_actual_power(self) -> float:
        """Get the monitored optical power. Unit depends on unit setting.

        Returns:
            power_level: The instrument power level in decibel-milliwatts or milliwatts.
        """
        power_level = self._ask_float(":POW:ACT?")
        return round(power_level, 2)

    @rpc_method
    def get_minimum_power_level(self) -> float:
        """Get the minimum power level.

        Returns:
            power level: The instrument power level minimum in decibel-milliwatts or milliwatts.
        """
        return round(self._power_level_range.min, 2)

    @rpc_method
    def get_maximum_power_level(self) -> float:
        """Get the maximum power level.

        Returns:
            power level: The instrument power level maximum in decibel-milliwatts or milliwatts.
        """
        return round(self._power_level_range.max, 2)

    @rpc_method
    def set_power_level_unit_to_mw(self) -> None:
        """Set the power_level unit to milliwatts."""
        self._set_power_level_unit(1)

    @rpc_method
    def set_power_level_unit_to_dbm(self) -> None:
        """Set the power_level unit to decibel-milliwatts."""
        self._set_power_level_unit(0)

    @rpc_method
    def get_power_level_unit(self) -> str:
        """Get the power_level unit displayed.

        Returns:
            wl_unit: The power_level unit as either "dBm" or "mW".
        """
        wl_unit = self._ask_bool(":POW:UNIT?")
        return "mW" if wl_unit else "dBm"

    @rpc_method
    def set_sweep_start_wavelength(self, wavelength: float) -> None:
        """Set the start wavelength for a sweep.

        Parameters:
            wavelength: wavelength in nanometers.
        """
        unit = "nm"
        dec = 4  # 0.1 pm resolution
        if wavelength < self._wavelength_range.min or wavelength > self._wavelength_range.max:
            raise ValueError(
                f"Wavelength {wavelength:.{dec}f}{unit} out of instrument range "
                f"({self._wavelength_range.min}{unit} - {self._wavelength_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV:SWE:STAR {wavelength}")

    @rpc_method
    def get_sweep_start_wavelength(self) -> float:
        """Get the sweep start wavelength. Default unit is nanometers.

        Returns:
            wavelength: The instrument wavelength in nanometers.
        """
        wavelength = self._ask_float(":WAV:SWE:STAR?")
        return wavelength

    @rpc_method
    def set_sweep_stop_wavelength(self, wavelength: float) -> None:
        """Set the stop wavelength for a sweep.

        Parameters:
            wavelength: wavelength in nanometers.
        """
        unit = "nm"
        dec = 4  # 0.1 pm resolution
        if wavelength < self._wavelength_range.min or wavelength > self._wavelength_range.max:
            raise ValueError(
                f"Wavelength {wavelength:.{dec}f}{unit} out of instrument range "
                f"({self._wavelength_range.min}{unit} - {self._wavelength_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV:SWE:STOP {wavelength}")

    @rpc_method
    def get_sweep_stop_wavelength(self) -> float:
        """Get the sweep stop wavelength. Default unit is nanometers.

        Returns:
            wavelength: The instrument wavelength in nanometers.
        """
        wavelength = self._ask_float(":WAV:SWE:STOP?")
        return wavelength

    @rpc_method
    def set_sweep_start_frequency(self, frequency: float) -> None:
        """Set the start frequency for a sweep.

        Parameters:
            frequency: frequency in terahertz.
        """
        unit = "THz"
        dec = 4  # 10 MHz resolution
        if frequency < self._frequency_range.min or frequency > self._frequency_range.max:
            raise ValueError(
                f"Wavelength {frequency:.{dec}f}{unit} out of instrument range "
                f"({self._frequency_range.min}{unit} - {self._frequency_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV:FREQ:SWE:STAR {frequency}")

    @rpc_method
    def get_sweep_start_frequency(self) -> float:
        """Get the sweep start frequency. Default unit is terahertz.

        Returns:
            frequency: The instrument frequency in nanometers.
        """
        frequency = self._ask_float(":WAV:FREQ:SWE:STAR?")
        return frequency

    @rpc_method
    def set_sweep_stop_frequency(self, frequency: float) -> None:
        """Set the stop frequency for a sweep.

        Parameters:
            frequency: frequency in terahertz.
        """
        unit = "THz"
        dec = 4  # 10 MHz resolution
        if frequency < self._frequency_range.min or frequency > self._frequency_range.max:
            raise ValueError(
                f"Wavelength {frequency:.{dec}f}{unit} out of instrument range "
                f"({self._frequency_range.min}{unit} - {self._frequency_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV:FREQ:SWE:STOP {frequency}")

    @rpc_method
    def get_sweep_stop_frequency(self) -> float:
        """Get the sweep stop frequency. Default unit is terahertz.

        Returns:
            frequency: The instrument frequency in nanometers.
        """
        frequency = self._ask_float(":WAV:FREQ:SWE:STOP?")
        return frequency

    @rpc_method
    def set_sweep_mode(self, mode: int) -> None:
        """Set sweep mode. Possible modes are:
        0 - Step sweep mode and One way
        1 - Continuous sweep mode and One way
        2 - Step sweep mode and Two way
        3 - Continuous sweep mode and Two way

        Parameters:
            mode: Integer in range [0, 3].
        """
        if mode not in range(4):
            raise ValueError(f"Sweep mode value {mode} not in valid modes range [0-3].")

        self._write_and_check_errors(f":WAV:SWE:MOD {mode}")

    @rpc_method
    def get_sweep_mode(self) -> int:
        """Get sweep mode.

        Returns:
            mode: Integer in range [0, 3].
        """
        return self._ask_int(":WAV:SWE:MOD?")

    @rpc_method
    def set_sweep_speed(self, speed: int) -> None:
        """Set sweep speed. Possible speed values are 1,2,5,10,20,50,100,200nm/s.

        Parameters:
            speed: speed in nm/s.
        """
        if speed not in self.VALID_SPEED_VALUES:
            raise ValueError(f"Sweep speed {speed} not in valid values {self.VALID_SPEED_VALUES}nm/s.")

        self._write_and_check_errors(f":WAV:SWE:SPE {speed}")

    @rpc_method
    def get_sweep_speed(self) -> float:
        """Get sweep speed.

        Returns:
            speed: Speed in range [1, 200]nm/s.
        """
        return self._ask_float(":WAV:SWE:SPE?")

    @rpc_method
    def set_sweep_dwell(self, dwell: float) -> None:
        """Set _stepped_ sweep dwell. Possible dwell range is 0-999.9s in 0.1nm steps. It does not take into account
        delay in one-way sweeps to return to the start frequency.

        Parameters:
            dwell: Dwell between sweep steps in range [0, 1000[s.
        """
        dec = 1
        if dwell < 0.0 or dwell >= 1000.0:
            raise ValueError(f"Sweep dwell {dwell} not in valid range [0-1000[s.")

        self._write_and_check_errors(f":WAV:SWE:DWEL {dwell:.{dec}f}")

    @rpc_method
    def get_sweep_dwell(self) -> float:
        """Get dwell between sweep steps.

        Returns:
            dwell: dwell in range [0, 1000[s.
        """
        return self._ask_float(":WAV:SWE:DWEL?")

    @rpc_method
    def set_sweep_delay(self, delay: float) -> None:
        """Set _continuous_ sweep delay. Possible delay range is 0-999.9s in 0.1nm steps. It does not take into account
        delay in one-way sweeps to return to the start frequency.

        Parameters:
            delay: Delay between sweeps in range [0, 1000[s.
        """
        dec = 1
        if delay < 0.0 or delay >= 1000.0:
            raise ValueError(f"Sweep delay {delay} not in valid range [0-1000[s.")

        self._write_and_check_errors(f":WAV:SWE:DEL {delay:.{dec}f}")

    @rpc_method
    def get_sweep_delay(self) -> float:
        """Get delay between sweeps.

        Returns:
            delay: delay in range [0, 1000[s.
        """
        return self._ask_float(":WAV:SWE:DEL?")

    @rpc_method
    def set_sweep_cycles(self, cycles: int) -> None:
        """Set sweep repetition times. Possible number of repetitions are in range [0, 999].

        Parameters:
            cycles: Integer in range [0, 999].
        """
        if cycles not in range(1000):
            raise ValueError(f"Sweep cycles {cycles} not in valid cycles range [0-999].")

        self._write_and_check_errors(f":WAV:SWE:CYCL {cycles}")

    @rpc_method
    def get_sweep_cycles(self) -> int:
        """Get sweep repetition times.

        Returns:
            cycles: Integer in range [0, 999].
        """
        return self._ask_int(":WAV:SWE:CYCL?")

    @rpc_method
    def set_sweep_state(self, state: int) -> None:
        """Set sweep state. Possible states are:
        0 - Stop
        1 - Start

        Parameters:
            state: Integer in range [0, 1].
        """
        if state not in [0, 1]:
            raise ValueError(f"Sweep state value {state} not in valid states range [0-1].")

        self._write_and_check_errors(f":WAV:SWE:STAT {state}")

    @rpc_method
    def start_repeating_sweep(self) -> None:
        """Start a repeating sweep."""
        self._write_and_check_errors(":WAV:SWE:STAT:REP")

    @rpc_method
    def get_sweep_state(self) -> int:
        """Get sweep state. Possible states are:
        0 - Stopped
        1 - Running
        3 - Standing by trigger
        4 - Preparation for sweep start

        Returns:
            state: Integer in range [0, 4].
        """
        return self._ask_int(":WAV:SWE:STAT?")

    @rpc_method
    def set_trigger_output_timing_mode(self, mode: int) -> None:
        """Set trigger output timing mode. Possible modes are:
        0 - None
        1 - Stop
        2 - Start
        3 - Step

        Parameters:
            mode: Integer in range [0, 3].
        """
        if mode not in range(4):
            raise ValueError(f"Trigger output timing mode {mode} not in valid modes range [0-3].")

        self._write_and_check_errors(f":TRIG:OUTP {mode}")

    @rpc_method
    def get_trigger_output_timing_mode(self) -> int:
        """Get trigger output timing mode.

        Returns:
            mode: Integer in range [0, 3].
        """
        return self._ask_int(":TRIG:OUTP?")

    @rpc_method
    def set_trigger_output_period_mode(self, mode: int) -> None:
        """Set trigger output period mode. Possible modes are:
        0 - Sets the output trigger to be periodic in time.
        1 - Sets the output trigger to be periodic in wavelength.

        Parameters:
            mode: Integer in range [0, 1].
        """
        if mode not in [0, 1]:
            raise ValueError(f"Trigger output period mode {mode} not in valid modes [0-1].")

        self._write_and_check_errors(f":TRIG:OUTP:SETT {mode}")

    @rpc_method
    def get_trigger_output_period_mode(self) -> int:
        """Get trigger output period mode.

        Returns:
            mode: Integer in range [0, 1].
        """
        return self._ask_int(":TRIG:OUTP:SETT?")

    @rpc_method
    def set_trigger_output_step(self, step: float) -> None:
        """Set trigger output step. Possible step range is from 0.0001 to ~ maximum specified wavelength
        range in 0.0001nm steps.

        Parameters:
            step: Interval of the trigger signal output [0.0001, max wavelength] in nanometers.
        """
        dec = 4
        max_wl_range = self.get_sweep_stop_wavelength() - self.get_sweep_start_wavelength()
        if step < 0.0001 or step > max_wl_range:
            raise ValueError(f"Trigger output step {step} not in valid range [0.0001-{max_wl_range}]nm.")

        self._write_and_check_errors(f":TRIG:OUTP:STEP {step:.{dec}f}")

    @rpc_method
    def get_trigger_output_step(self) -> float:
        """Get trigger output step.

        Returns:
            step: step in range [0.0001, max wavelength]nm.
        """
        return self._ask_float(":TRIG:OUTP:STEP?")

    @rpc_method
    def issue_soft_trigger(self) -> None:
        """Issues a soft trigger, executing sweep from trigger standby mode."""
        self._write_and_check_errors(":TRIG:INP:SOFT")

    @rpc_method
    def readout_points(self) -> int:
        """reads the number of logging data available.

        Returns:
            The number of logging data available.
        """
        return int(self._scpi_protocol.ask(":READ:POIN?"))

    @rpc_method
    def readout_data(self) -> List[float]:
        """Read out wavelength logging data and convert it into floating point values. According to the manual
        the data points are returned in units of 0.1pm. Thus, value 0x0040F844 (little Endian order) = 4520000
        corresponds to 452.0000nm.

        Returns:
            data: Data points list converted into nanometers.
        """
        data_binary_size = 4  # In Legacy mode
        self._scpi_protocol.write(":READout:DATa?")
        binary_data = self._scpi_protocol.read_binary_data(read_terminator_flag=False)
        hex_data = [binary_data[p : p + data_binary_size] for p in range(0, len(binary_data), data_binary_size)]

        return [int.from_bytes(h_d, byteorder="little") * 1e-4 for h_d in hex_data]

    @rpc_method
    def shutdown(self) -> None:
        """Shut down the device. Breaks also communication with the device."""
        self._write_and_check_errors(":SPEC:SHUT")

    @rpc_method
    def reboot(self) -> None:
        """Restarts the device. This takes about 60 seconds. Note that the communication to the
        device also resets, so continuing with the same proxy is not possible, but a new one needs
        to be made.
        """
        self._write_and_check_errors(":SPECial:REBoot")
