"""
Base class for the instrument drivers for the Rohde&Schwarz Signal Generators
"""

import logging
import re
import time
from typing import List, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class RohdeSchwarz_Base(QMI_Instrument):
    """Base class for the instrument driver for the Rohde&Schwarz Signal Generators."""

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 max_continuous_power: Optional[float] = None
                 ) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:                   Name for this instrument instance.
            transport:              QMI transport descriptor to connect to the instrument.
            max_continuous_power:   Maximum allowable continuous RF power. The RF output power can be set higher than
                                    this value only when pulse modulation is enabled. Set to `None` to disable the
                                    limit (allow any output power).
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._calibrating = False
        self._calibration_result = None  # type: Optional[int]
        self._calibration_error = None  # type: Optional[str]
        self._max_continuous_power = max_continuous_power
        self._transport = create_transport(transport, default_attributes={"port": 5025})
        self._scpi_protocol = ScpiProtocol(self._transport,
                                           command_terminator="\r\n",
                                           response_terminator="\n",
                                           default_timeout=self._timeout)

    def _is_valid_param(self, inp: str, params: List[str]) -> str:
        """
        Checks if input is a valid parameter.
        """
        if inp.upper() in params:
            return inp.upper()
        else:
            raise ValueError('Values that can be set are %s' % ','.join(params))

    @rpc_method
    def open(self) -> None:
        """Open connection to the instrument."""
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        self._calibrating = False
        self._calibration_result = None
        self._calibration_error = None
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close connection to the instrument."""
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _ask_float(self, cmd: str) -> float:
        """Send a query and return a floating point response."""
        resp = self._scpi_protocol.ask(cmd)
        try:
            return float(resp)
        except ValueError as exc:
            raise QMI_InstrumentException("Unexpected response to command {!r}: {!r}".format(cmd, resp)) from exc

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

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        resp = self._scpi_protocol.ask("SYST:ERR:ALL?")
        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*0\s*,", resp):
            # Some error occurred.
            raise QMI_InstrumentException("Instrument returned error: {}".format(resp))

    def _internal_poll_calibration_finished(self) -> bool:
        """Check for ongoing calibration; returns True if the calibration is finished."""
        assert self._calibrating
        assert self._transport is not None

        # Poll to see if the instrument sent a response to the calibration command.
        try:
            resp = self._transport.read_until(message_terminator=b"\n", timeout=0.001)
        except QMI_TimeoutException:
            # No response received; calibration still not finished.
            return False

        # Got response to calibration query.
        # Store it for future reference.
        self._calibrating = False
        self._calibration_result = None
        self._calibration_error = "Unexpected response to calibration command"
        resp = resp.rstrip(b"\r\n")
        try:
            self._calibration_result = int(resp)
            self._calibration_error = None
        except ValueError:
            _logger.warning("Unexpected response to calibration command: %r", resp)
            self._calibration_error = "Unexpected response to calibration command: {!r}".format(resp)
            return True

        _logger.info("Internal adjustments finished with status %d", self._calibration_result)

        # Read error queue to see if calibration produced an error.
        calibration_resp = self._scpi_protocol.ask("SYST:ERR:ALL?")

        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*0\s*,", calibration_resp):
            # Some error occurred.
            _logger.warning("Calibration failed with error: %s", calibration_resp)
            self._calibration_error = "Instrument returned error: {}".format(calibration_resp)

        # Calibration finished.
        return True

    def _check_calibrating(self) -> None:
        """Raise an exception if a calibration is still running."""
        self._check_is_open()
        if self._calibrating:
            # Calibration started and result not yet received.
            # Poll to see if there is a result now.
            if not self._internal_poll_calibration_finished():
                # Calibration still not finished.
                raise QMI_InstrumentException("Calibration in progress") from None
            assert not self._calibrating

    def _get_external_reference_frequency(self) -> str:
        """Return the currently configured external reference input frequency.
        """
        self._check_calibrating()
        return self._scpi_protocol.ask(":ROSC:EXT:FREQ?").strip()

    def _set_external_reference_frequency(self, frequency: str, options: List[str]) -> None:
        """Configure the external reference input frequency.

        Parameters:
            frequency:  desired frequency.
            options:    allowed frequencies.
        """
        frequency = self._is_valid_param(frequency, options)
        self._check_calibrating()
        self._scpi_protocol.write(":ROSC:EXT:FREQ {}".format(frequency))
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_calibrating()
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(resp))
        return QMI_InstrumentIdentification(vendor=words[0].strip(),
                                            model=words[1].strip(),
                                            serial=words[2].strip(),
                                            version=words[3].strip())

    @rpc_method
    def poll_calibration(self) -> Optional[int]:
        """Check whether an ongoing calibration is finished.

        If calibration is not yet finished, this function returns None.

        If calibration is finished, this function returns a status code:
          0 if calibration was successful;
          1 if calibration failed.
        """
        self._check_is_open()
        if self._calibrating:
            if not self._internal_poll_calibration_finished():
                # Still calibrating.
                return None
        assert not self._calibrating

        if self._calibration_error is not None:
            # Report calibration error.
            errmsg = self._calibration_error
            self._calibration_result = None
            self._calibration_error = None
            raise QMI_InstrumentException(errmsg)

        if self._calibration_result is not None:
            # Return calibration result.
            ret = self._calibration_result
            self._calibration_result = None
            return ret

        # No calibration active, no result, no error.
        raise QMI_InstrumentException("No calibration active")

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        # Unfortunately RST does not cancel ongoing calibration.
        self._check_calibrating()
        self._scpi_protocol.write("*CLS")  # clear error queue
        self._scpi_protocol.write("*RST")
        time.sleep(0.1)
        self._check_error()

    @rpc_method
    def get_phase(self) -> float:
        """Return the current phase delta in degrees."""
        self._check_calibrating()
        return self._ask_float(":PHAS?")

    @rpc_method
    def set_phase(self, phase: float) -> None:
        """Set the current phase delta.

        Parameters:
            phase:  target phase delta in degrees.
        """
        self._check_calibrating()
        self._scpi_protocol.write(":PHAS {}".format(phase))
        self._check_error()

    @rpc_method
    def get_reference_source(self) -> str:
        """Return the current reference source.

        Possible values:
          "INT" if the internal 10 MHz reference source is used;
          "EXT" if an external reference source is used.
        """
        self._check_calibrating()
        return self._scpi_protocol.ask(":ROSC:SOUR?").strip().upper()

    @rpc_method
    def set_reference_source(self, source: str) -> None:
        """Set the reference source.

        Parameters:
            source: desired reference source (accepted values: "INT", "EXT"); see also get_reference_source().
        """
        source = source.upper()
        if source not in ("INT", "EXT"):
            raise ValueError("Unknown value {}".format(source))
        self._check_calibrating()
        self._scpi_protocol.write(":ROSC:SOUR {}".format(source))
        self._check_error()

    @rpc_method
    def get_frequency(self) -> float:
        """Return the current RF frequency in Hz."""
        self._check_calibrating()
        return self._ask_float(":FREQ?")

    @rpc_method
    def set_frequency(self, frequency: float) -> None:
        """Set the RF frequency.

        Parameters:
            frequency:  target frequency in Hertz.
        """
        self._check_calibrating()
        self._scpi_protocol.write(":FREQ {}".format(frequency))
        self._check_error()

    @rpc_method
    def get_pulsemod_ext_source(self) -> bool:
        """Return True if pulse modulation uses an external source."""
        self._check_calibrating()
        source = self._scpi_protocol.ask(":PULM:SOUR?").strip().upper()
        if source.startswith("EXT"):
            return True
        elif source.startswith("INT"):
            return False
        raise QMI_InstrumentException("Unexpected response {!r} to command :PULM:SOUR?".format(source))

    @rpc_method
    def set_pulsemod_ext_source(self, ext: bool) -> None:
        """Enable or disable the external pulse modulation source.

        When set to True, pulse modulation is controlled by an external
        pulse generator connected to the TRIG port of the instrument.
        When set to False, pulse modulation is controlled by an internal
        pulse generator.

        The nominal threshold of the TRIG input signal is +1 Volt.
        The signal on the TRIG input must not exceed 5 Volt.

        Parameters:
            ext:    Boolean flag indicating if external modulation must be enabled.
        """
        source = "EXT" if ext else "INT"
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and (not ext):
            if self.get_power() > self._max_continuous_power:
                raise QMI_InstrumentException(
                    "Power limited to {} dBm unless external pulse modulation source is selected".format(
                        self._max_continuous_power))

        self._scpi_protocol.write(":PULM:SOUR {}".format(source))
        self._check_error()

    @rpc_method
    def get_power_on_output_policy(self) -> str:
        """Return instrument power-on policy for setting the RF output state.

        Possible values:
          "OFF" if the instrument starts with RF output disabled;
          "UNCH" if the instrument starts with RF output state the same as before power down.
        """
        self._check_calibrating()
        return self._scpi_protocol.ask(":OUTP:PON?").strip().upper()

    @rpc_method
    def set_power_on_output_policy(self, policy: str) -> None:
        """Set the instrument power-on policy for setting the RF output state.

        Parameters:
            policy: desired policy (accepted values: "OFF", "UNCH"); see also get_power_on_output_policy().
        """
        policy = policy.upper()
        if policy not in ("OFF", "UNCH"):
            raise ValueError("Unknown value {}".format(policy))
        self._check_calibrating()
        self._scpi_protocol.write(":OUTP:PON {}".format(policy))
        self._check_error()

    @rpc_method
    def get_pulsemod_polarity(self) -> bool:
        """Return True if the external pulse modulation polarity is inverted; False if it is normal."""
        self._check_calibrating()
        resp = self._scpi_protocol.ask(":PULM:POL?").strip().upper()
        if resp.startswith("INV"):
            return True
        elif resp.startswith("NORM"):
            return False
        raise QMI_InstrumentException("Unexpected response {!r} ot command :PULM:POL?".format(resp))

    @rpc_method
    def set_pulsemod_polarity(self, inverted: bool) -> None:
        """Enable or disable inverted polarity for external modulation.

        Parameters:
            inverted:   Boolean flag indicating if external modulation should be inverted.
                        For normal polarity (False), the RF signal is suppressed when the TRIG pulse is low.
                        For inverted polarity (True), the RF signal is suppressed when the TRIG pulse is high.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and inverted:
            if self.get_power() > self._max_continuous_power:
                raise QMI_InstrumentException(
                    "Power limited to {} dBm unless pulse modulation source is non-inverted".format(
                        self._max_continuous_power))

        self._scpi_protocol.write(":PULM:POL {}".format("INV" if inverted else "NORM"))
        self._check_error()

    @rpc_method
    def get_power(self) -> float:
        """Return the current RF output power in dBm."""
        self._check_calibrating()
        return self._ask_float(":POW?")

    @rpc_method
    def set_power(self, power: float) -> None:
        """Set the RF output power in dBm.

        Parameters:
            power:  target output power in dBm.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and (power > self._max_continuous_power):
            if not self.get_pulsemod_enabled():
                raise QMI_InstrumentException(
                    "Power limited to {} dBm unless pulse modulation is enabled".format(self._max_continuous_power))
            if not self.get_pulsemod_ext_source():
                raise QMI_InstrumentException(
                    "Power limited to {} dBm unless external pulse modulation source is selected".format(
                        self._max_continuous_power))
            if self.get_pulsemod_polarity():
                raise QMI_InstrumentException(
                    "Power limited to {} dBm unless external pulse source polarity is non-inverted".format(
                        self._max_continuous_power))

        self._scpi_protocol.write(":POW {}".format(power))
        self._check_error()

    @rpc_method
    def get_output_state(self) -> bool:
        """Return True if RF output is enabled, False if RF output is disabled."""
        self._check_calibrating()
        return self._ask_bool(":OUTP?")

    @rpc_method
    def set_output_state(self, enable: bool) -> None:
        """Enable or disable RF output.

        Parameters:
            enable: target enabled state.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and enable:
            if self.get_power() > self._max_continuous_power:
                if not self.get_pulsemod_enabled():
                    raise QMI_InstrumentException(
                        "Power limited to {} dBm unless pulse modulation is enabled".format(
                            self._max_continuous_power
                        ))
                if not self.get_pulsemod_ext_source():
                    raise QMI_InstrumentException(
                        "Power limited to {} dBm unless external pulse modulation source is selected".format(
                            self._max_continuous_power
                        ))
                if self.get_pulsemod_polarity():
                    raise QMI_InstrumentException(
                        "Power limited to {} dBm unless external pulse source polarity is non-inverted".format(
                            self._max_continuous_power
                        ))

        self._scpi_protocol.write(":OUTP {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_pulsemod_enabled(self) -> bool:
        """Return True if pulse modulation is enabled, False if disabled."""
        self._check_calibrating()
        return self._ask_bool(":PULM:STAT?")

    @rpc_method
    def set_pulsemod_enabled(self, enable: bool) -> None:
        """Enable or disable pulse modulation.

        Parameters:
            enable: target enabled state.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and (not enable):
            if self.get_power() > self._max_continuous_power:
                raise QMI_InstrumentException(
                    "Pulse modulation cannot be enabled as power is set to {} dBm which is higher than the maximum {} dBm".format(
                        self.get_power(), self._max_continuous_power))

        self._scpi_protocol.write(":PULM:STAT {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_iq_enabled(self) -> bool:
        """Return True if IQ modulation is enabled, False if disabled."""
        self._check_calibrating()
        return self._ask_bool(":IQ:STAT?")

    @rpc_method
    def set_iq_enabled(self, enable: bool) -> None:
        """Enable or disable IQ modulation.

        Parameters:
            enable: target enabled state.
        """
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:STAT {}".format(1 if enable else 0))
        self._check_error()

    @rpc_method
    def get_errors(self) -> None:
        """
        Queries the error/event queue for all unread items and
        removes them from the queue.
        """
        return self._check_error()

    @rpc_method
    def get_error_queue_length(self) -> int:
        """
        Queries the number of entries in the error queue.
        """
        return int(self._scpi_protocol.ask('SYST:ERR:COUN?'))