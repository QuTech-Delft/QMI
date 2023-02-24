"""
Instrument driver for the Anapico APSIN Series signal generators.
"""

import logging
import re
import time

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Anapico_APSIN(QMI_Instrument):
    """Instrument driver for the Anapico APSIN Series signal generators.

    This driver has been developed for and tested with the Anapico APSIN2010,
    but is expected to also work with other APSIN models.

    A subset of the instrument functionality is supported.
    Continuous wave, pulse modulation, amplitude modulation and frequency modulation are supported.
    Triggering, sweeping and multipurpose output are not supported.
    """

    # Default response timeout in seconds.
    # The instrument responds to most queries in a fraction of a second,
    # however when modulation is enabled, the instrument takes up to 5 seconds
    # to respond to certain commands.
    DEFAULT_RESPONSE_TIMEOUT = 10.0

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialize the instrument driver.

        Parameters:
            name: Name for this instrument instance.
            transport: QMI transport descriptor to connect to the instrument.
                       For example "tcp:172.16.xx.yy:18".
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"port": 18})
        self._scpi_protocol = ScpiProtocol(self._transport, default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)
        self._power_unit_configured = False

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._power_unit_configured = False
        self._transport.open()
        try:
            # Discard pending errors.
            self._scpi_protocol.write("*CLS")
            self._scpi_protocol.ask("SYST:ERR:ALL?")
        except Exception:
            self._transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _ask(self, cmd: str) -> str:
        """Send a query and return a string response."""
        self._transport.discard_read()  # discard potential stale reply after timeout
        return self._scpi_protocol.ask(cmd)

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating point response."""
        self._transport.discard_read()
        resp = self._scpi_protocol.ask(cmd)
        try:
            return float(resp)
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    def _ask_bool(self, cmd: str) -> bool:
        """Send a query and return a boolean response."""
        self._transport.discard_read()
        resp = self._scpi_protocol.ask(cmd)
        value = resp.strip().upper()
        if value in ("1", "ON"):
            return True
        elif value in ("0", "OFF"):
            return False
        else:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp))

    def _ask_source_is_ext(self, cmd: str) -> bool:
        """Send a query and return True if the response is "EXT", False if it is "INT"."""
        self._transport.discard_read()
        source = self._scpi_protocol.ask(cmd).strip().upper()
        if source.startswith("EXT"):
            return True
        elif source.startswith("INT"):
            return False
        raise QMI_InstrumentException("Unexpected response {!r} to command {}".format(source, cmd))

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        resp = self._ask(":SYST:ERR:ALL?")
        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*[-+]?0\s*,", resp):
            # Some error occurred.
            raise QMI_InstrumentException("Instrument returned error: {}".format(resp))

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning most settings to their defaults."""
        self._transport.discard_read()
        self._scpi_protocol.write("*CLS")  # clear error status
        self._scpi_protocol.ask(":SYST:ERR:ALL?")  # clear error message queue
        self._scpi_protocol.write("*RST")  # reset instrument
        time.sleep(0.5)
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(resp))
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def get_output_enabled(self) -> bool:
        """Return True if the RF output is enabled, False if disabled."""
        return self._ask_bool(":OUTP?")

    @rpc_method
    def set_output_enabled(self, enable: bool) -> None:
        """Enable or disable the RF output."""
        self._scpi_protocol.write(":OUTP {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_frequency(self) -> float:
        """Return the current RF frequency in Hz."""
        return self._ask_float(":FREQ?")

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """Set the RF frequency in Hz.

        The instrument supports a limited frequency range.
        If the specified frequency is outside the supported range,
        the instrument will select the closest supported frequency.
        """
        self._scpi_protocol.write(":FREQ {}".format(frequency))
        self._check_error()

    @rpc_method
    def get_phase(self) -> float:
        """Return the current phase adjustment in radians."""
        return self._ask_float(":PHAS?")

    @rpc_method
    def set_phase(self, phase: float) -> None:
        """Set the current phase adjustment in radians."""
        self._scpi_protocol.write(":PHAS {}".format(phase))
        self._check_error()

    def _ensure_power_unit(self) -> None:
        """If the power unit is not yet configured, set it to dBm."""
        if not self._power_unit_configured:
            self._scpi_protocol.write(":UNIT:POW DBM")
            self._check_error()
            self._power_unit_configured = True

    @rpc_method
    def get_power(self) -> float:
        """Return the current RF output power in dBm."""
        self._ensure_power_unit()
        return self._ask_float(":POW?")

    @rpc_method
    def set_power(self, power: float) -> None:
        """Set the RF output power in dBm."""
        self._ensure_power_unit()
        self._scpi_protocol.write(":POW {}".format(power))
        self._check_error()

    @rpc_method
    def get_pulsemod_enabled(self) -> bool:
        """Return True if pulse modulation is enabled, False if disabled."""
        return self._ask_bool(":PULM:STAT?")

    @rpc_method
    def set_pulsemod_enabled(self, enable: bool) -> None:
        """Enable or disable pulse modulation."""
        self._scpi_protocol.write(":PULM:STAT {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_pulsemod_ext_source(self) -> bool:
        """Return True if pulse modulation uses an external source, False when using the internal source."""
        return self._ask_source_is_ext(":PULM:SOUR?")

    @rpc_method
    def set_pulsemod_ext_source(self, ext: bool) -> None:
        """Enable or disable the external pulse modulation source.

        When set to True, pulse modulation is controlled by an external
        pulse generator connected to the PULSE port of the instrument.
        When set to False, pulse modulation is controlled by an internal
        pulse generator.
        """
        source = "EXT" if ext else "INT"
        self._scpi_protocol.write(":PULM:SOUR {}".format(source))
        self._check_error()

    @rpc_method
    def get_pulsemod_polarity(self) -> bool:
        """Return True if the external pulse modulation polarity is inverted; False if it is normal."""
        resp = self._ask(":PULM:POL?").strip().upper()
        if resp.startswith("INV"):
            return True
        elif resp.startswith("NORM"):
            return False
        raise QMI_InstrumentException("Unexpected response {!r} ot command :PULM:POL?".format(resp))

    @rpc_method
    def set_pulsemod_polarity(self, inverted: bool) -> None:
        """Enable or disable inverted polarity for external modulation."""
        self._scpi_protocol.write(":PULM:POL {}".format("INV" if inverted else "NORM"))
        self._check_error()

    @rpc_method
    def get_am_enabled(self) -> bool:
        """Return True if amplitude modulation is enabled, False if disabled."""
        return self._ask_bool(":AM:STAT?")

    @rpc_method
    def set_am_enabled(self, enable: bool) -> None:
        """Enable or disable amplitude modulation."""
        self._scpi_protocol.write(":AM:STAT {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_am_ext_source(self) -> bool:
        """Return True if amplitude modulation uses an external source, False when using the internal source."""
        return self._ask_source_is_ext(":AM:SOUR?")

    @rpc_method
    def set_am_ext_source(self, ext: bool) -> None:
        """Enable or disable the external amplitude modulation source.

        When set to True, amplitude modulation is controlled by an external
        signal connected to the PULSE port of the instrument. Note the external
        amplitude modulation signal is AC coupled.

        When set to False, amplitude modulation is controlled by an internal signal.
        """
        source = "EXT" if ext else "INT"
        self._scpi_protocol.write(":AM:SOUR {}".format(source))
        self._check_error()

    @rpc_method
    def get_am_sensitivity(self) -> float:
        """Return the amplitude modulation sensitivity as a fraction of nominal amplitude per Volt."""
        return self._ask_float(":AM:SENS?")

    @rpc_method
    def set_am_sensitivity(self, sensitivity: float) -> None:
        """Set the sensitivity for external amplitude modulation.

        Parameters:
            sensitivity: Modulation sensitivity per Volt external input (range 0 ... 3).
        """
        self._scpi_protocol.write(":AM:SENS {}".format(sensitivity))
        self._check_error()

    @rpc_method
    def get_fm_enabled(self) -> bool:
        """Return True if frequency modulation is enabled, False if disabled."""
        return self._ask_bool(":FM:STAT?")

    @rpc_method
    def set_fm_enabled(self, enable: bool) -> None:
        """Enable or disable frequency modulation."""
        self._scpi_protocol.write(":FM:STAT {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_fm_ext_source(self) -> bool:
        """Return True if frequency modulation uses an external source, False when using the internal source."""
        return self._ask_source_is_ext(":FM:SOUR?")

    @rpc_method
    def set_fm_ext_source(self, ext: bool) -> None:
        """Enable or disable the external frequency modulation source.

        When set to True, frequency modulation is controlled by an external
        signal connected to the Phi-M port of the instrument.
        When set to False, frequency modulation is controlled by an internal signal.
        """
        source = "EXT" if ext else "INT"
        self._scpi_protocol.write(":FM:SOUR {}".format(source))
        self._check_error()

    @rpc_method
    def get_fm_sensitivity(self) -> float:
        """Return the frequency modulation sensitivity in Hz/Volt."""
        return self._ask_float(":FM:SENS?")

    @rpc_method
    def set_fm_sensitivity(self, sensitivity: float) -> None:
        """Set the sensitivity for external frequency modulation.

        Parameters:
            sensitivity: Frequency modulation deviation per one Volt peak amplitude of external input.
        """
        self._scpi_protocol.write(":FM:SENS {}".format(sensitivity))
        self._check_error()

    @rpc_method
    def get_fm_coupling(self) -> str:
        """Return the input coupling for external frequency modulation.

        Returns:
            Input coupling, either "AC" or "DC".
        """
        return self._ask(":FM:COUP?").strip().upper()

    @rpc_method
    def set_fm_coupling(self, coupling: str) -> None:
        """Select AC or DC coupling for the external frequency modulation input.

        Parameters:
            coupling: Input coupling, either "AC" or "DC".
        """
        coupling = coupling.upper()
        if coupling not in ("AC", "DC"):
            raise ValueError("Unknown value {}".format(coupling))
        self._scpi_protocol.write(":FM:COUP {}".format(coupling))
        self._check_error()

    @rpc_method
    def get_reference_source(self) -> str:
        """Return the current reference clock source.

        Returns:
            "INT" if the internal reference is used;
            "EXT" if the external reference is used.
        """
        return self._ask(":ROSC:SOUR?").strip().upper()

    @rpc_method
    def set_reference_source(self, source: str) -> None:
        """Set the reference clock source.

        Parameters:
            source: "INT" to select the internal reference; "EXT" to select the external reference.
        """
        source = source.upper()
        if source not in ("INT", "EXT"):
            raise ValueError("Unknown value {}".format(source))
        self._scpi_protocol.write(":ROSC:SOUR {}".format(source))
        self._check_error()

    @rpc_method
    def get_external_reference_frequency(self) -> float:
        """Return the configured external reference input frequency in Hz."""
        return self._ask_float(":ROSC:EXT:FREQ?")

    @rpc_method
    def set_external_reference_frequency(self, frequency: float) -> None:
        """Set the expected external reference input frequency in Hz.

        The instrument supports a limited range of reference frequencies.
        If the specified frequency is outside the supported range,
        the instrument will select the closest supported frequency.

        The instrument has a very narrow reference lock range. The external
        reference frequency must match the configured frequency within 1 ppm
        to ensure a proper lock.
        """
        self._scpi_protocol.write(":ROSC:EXT:FREQ {}".format(frequency))
        self._check_error()

    @rpc_method
    def get_reference_is_locked(self) -> bool:
        """Return True if the instrument is locked to the internal or external reference clock."""
        return self._ask_bool(":ROSC:LOCK?")

    @rpc_method
    def get_reference_output_enabled(self) -> bool:
        """Return True if the 10 MHz reference clock output is enabled, False if disabled."""
        return self._ask_bool(":ROSC:OUTP?")

    @rpc_method
    def set_reference_output_enabled(self, enable: bool) -> None:
        """Enable or disable the 10 MHz reference clock output signal."""
        self._scpi_protocol.write(":ROSC:OUTP {}".format(1 if enable else 0))
        self._check_error()
