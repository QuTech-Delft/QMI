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
    """
    Instrument driver for the Santec TSL 570 laser. This driver currently supports only frequency units
    nm and THz, and power units dBm and mW.

    NOTES: Contrary to the manual, the queries seem to return frequency and power values in current set units,
    not in m, Hz, Watts as default. Also, the frequency min/max query is not as described in the manual.
    """

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # power level range in dBm and mW
    POWER_LEVEL_RANGE = {"dBm": (-15.0, 13.0), "mW": (0.04, 20.00)}

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
            context: The QMI context for running the driver in.
            name: Name for this instrument instance.
            transport: QMI transport descriptor to connect to the instrument.
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
        """Read the instrument error queue and raise an exception if there is an error."""
        errors = []
        # When there are no errors, the response is '0,"No error"'.
        while (error := self._scpi_protocol.ask(":SYST:ERR?")) != '0,"No error"':
            errors.append(self.ERRORS_TABLE[int(error.split(",")[0])])

        alerts = []
        # When there are no alerts, the response is "No alerts.".
        while (alert := self._scpi_protocol.ask(":SYST:ALER?")) != "No alerts.":
            alerts.append(self.ALERTS_TABLE[alert.split(",")[0]])

        return errors + alerts

    def _write_and_check_errors(self, cmd: str):
        """Write a command to the instrument and check if any errors or alerts were raised.

        Parameters:
            cmd: The input command to send.

        Raises:
            QMI_InstrumentException: If there were errors, errors described in the exception message.
        """
        self._scpi_protocol.write(cmd)
        errors = self._check_error()
        if len(errors):
            _logger.error("[%s] command [%s] resulted in errors: %s", self._name, cmd, errors)
            raise QMI_InstrumentException(f"Command {cmd} resulted in errors: {errors}")

    def _ask_int(self, cmd: str) -> int:
        """Send a query and return a floating point response."""
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

    def _ask_bool(self, cmd: str) -> bool:
        """Send a query and return a boolean response."""
        resp = self._scpi_protocol.ask(cmd)
        value = resp.strip().upper()
        if value in ("1", "ON"):
            return True
        elif value in ("0", "OFF"):
            return False
        else:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

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

        Returns: QMI_InstrumentIdentification with data e.g. idn.vendor = SANTEC, idn.model = TSL-570,
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
        """Query if the previous operation is completed.

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
        """Get the output wavelength. Default unit is nm.

        Returns:
            wavelength: The instrument wavelength in nanometers.
        """
        wavelength = self._ask_float(":WAV?")
        return wavelength

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """Set the output frequency in teraherz.

        Parameters:
            frequency: The target frequency in teraherz up to 10 MHz resolution.

        Raises:
            QMI_InstrumentException: If the frequency is not in the instrument range.
        """
        unit = "THz"
        dec = 5  # 10 MHz resolution
        if frequency < self._wavelength_range.min or frequency > self._wavelength_range.max:
            raise ValueError(
                f"frequency {frequency:.{dec}f}{unit} out of instrument range "
                f"({self._wavelength_range.min}{unit} - {self._wavelength_range.max}{unit})"
            )

        self._write_and_check_errors(f":WAV:FREQ {frequency:.{dec}f}")

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
    def get_frequency(self) -> float:
        """Get the output frequency. Unit depends on unit setting.

        Returns:
            frequency: The instrument frequency in teraherz.
        """
        frequency = self._ask_float(":WAV:FREQ?")
        return frequency

    @rpc_method
    def get_minimum_frequency(self) -> float:
        """Get the minimum frequency.

        Returns:
            frequency: The instrument frequency minimum in teraherz.
        """
        frequency = self._ask_float(":WAV:FREQ:MIN?")
        return frequency

    @rpc_method
    def get_maximum_frequency(self) -> float:
        """Get the maximum frequency.

        Returns:
            frequency: The instrument frequency maximum in teraherz.
        """
        frequency = self._ask_float(":WAV:FREQ:MAX?")
        return frequency

    @rpc_method
    def set_wavelength_unit(self, teraherz: bool) -> None:
        """Set the wavelength unit to teraherz or to nm. Update the minimum and maximum values consequently.

        Parameters:
            teraherz: Boolean to set wavelength unit to teraherz (True) or to nanometer (False)
        """
        self._write_and_check_errors(f":WAV:UNIT {int(teraherz)}")

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
            i_status = 0 if status.upper() == "ON" else 1

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
            i_status = 0 if status.upper() == "ON" else 1

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
        """Set optical output power level between -15dBm (~0.03mW) and peak power. Typical peak power from the datasheet
        https://santec.imgix.net/TSL-570-Datasheet.pdf is 13dBm (~20.00mW).

        Parameters:
            power_level: power level in decibel meters or milli Watts.
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
            power_level: The instrument power level in decibel meters or milli Watts.
        """
        power_level = self._ask_float(":POW?")
        return round(power_level, 2)

    @rpc_method
    def get_actual_power(self) -> float:
        """Get the monitored optical power. Unit depends on unit setting.

        Returns:
            power_level: The instrument power level in decibel meters or milli Watts.
        """
        power_level = self._ask_float(":POW:ACT?")
        return round(power_level, 2)

    @rpc_method
    def get_minimum_power_level(self) -> float:
        """Get the minimum power level.

        Returns:
            power level: The instrument power level minimum in decibel meters or milli Watts.
        """
        return round(self._power_level_range.min, 2)

    @rpc_method
    def get_maximum_power_level(self) -> float:
        """Get the maximum power level.

        Returns:
            power level: The instrument power level maximum in decibel meters or milli Watts.
        """
        return round(self._power_level_range.max, 2)

    @rpc_method
    def set_power_level_unit(self, milliwatts: bool) -> None:
        """Set the power_level unit to milli Watts or to decibel meters. Update the minimum and maximum values
        consequently.

        Parameters:
            milliwatts: Boolean to set power level unit to milli Watts (True) or to decibel meters (False)
        """
        self._write_and_check_errors(f":POW:UNIT {int(milliwatts)}")
        # Then update the minimum and maximum values of the instruments to apply for the changed units.
        unit = "mW" if milliwatts else "dBm"
        self._power_level_range.min = self.POWER_LEVEL_RANGE[unit][0]
        self._power_level_range.max = self.POWER_LEVEL_RANGE[unit][1]

    @rpc_method
    def get_power_level_unit(self) -> str:
        """Get the power_level unit displayed.

        Returns:
            wl_unit: The power_level unit as either "dBm" or "mW".
        """
        wl_unit = self._ask_bool(":POW:UNIT?")
        return "mW" if wl_unit else "dBm"

    @rpc_method
    def shutdown(self):
        """Shut down the device. Breaks also communication with the device."""
        self._write_and_check_errors(":SPEC:SHUT")

    @rpc_method
    def reboot(self):
        """Restarts the device. This takes about 60 seconds. Note that the communication to the
        device also resets, so continuing with the same proxy is not possible, but a new one needs
        to be made.
        """
        self._write_and_check_errors(":SPECial:REBoot")
