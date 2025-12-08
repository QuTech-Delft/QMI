"""
Base class for the instrument drivers for the Rohde&Schwarz Signal Generators
"""

import logging
import re
import time

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
    _rpc_constants = ["DEFAULT_RESPONSE_TIMEOUT"]
    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        transport: str,
        max_continuous_power: float | None = None
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
        self._calibration_result: int | None = None
        self._calibration_error: str | None = None
        self._max_continuous_power = max_continuous_power
        self._transport = create_transport(transport, default_attributes={"port": 5025})
        self._scpi_protocol = ScpiProtocol(
            self._transport,
            command_terminator="\r\n",
            response_terminator="\n",
            default_timeout=self._timeout
        )

    def _is_valid_param(self, inp: str, params: list[str]) -> str:
        """ Checks if input string is a valid parameter string.

        Parameters:
            inp:    String parameter to be checked.
            params: Allowed parameter strings as a list

        Raises:
            ValueError: If the input value is not in the allowed parameters list.

        Returns:
            inp: The input string in upper case.
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

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        resp = self._scpi_protocol.ask("SYST:ERR:ALL?")
        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*0\s*,", resp):
            # Some error occurred.
            raise QMI_InstrumentException(f"Instrument returned error: {resp}")

    def _internal_poll_calibration_finished(self) -> bool:
        """Check for ongoing calibration.

        Attributes:
            self._calibrating:        Set to `False` if response is received from instrument.
            self._calibration_result: Integer result from the response or `None`.
            self._calibration_error:  String describing the erroneous response or `None`.

        Return:
            True if the calibration is finished (with or without error), else False.
        """
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
        self._calibration_error = None
        resp = resp.rstrip(b"\r\n")
        try:
            self._calibration_result = int(resp)
        except ValueError:
            _logger.warning("Unexpected response to calibration command: %r", resp)
            self._calibration_error = f"Unexpected response to calibration command: {resp!r}"
            return True

        _logger.info("Internal adjustments finished with status %d", self._calibration_result)

        # Read error queue to see if calibration produced an error.
        calibration_resp = self._scpi_protocol.ask("SYST:ERR:ALL?")

        # When there are no errors, the response is '0,"No error"'.
        if not re.match(r"^\s*0\s*,", calibration_resp):
            # Some error occurred.
            _logger.warning("Calibration failed with error: %s", calibration_resp)
            self._calibration_error = f"Instrument returned error: {calibration_resp}"

        # Calibration finished.
        return True

    def _check_calibrating(self) -> None:
        """Check if a calibration is still running.

        Raises:
            QMI_InstrumentException: If the calibration is still in progress.
        """
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

    def _set_external_reference_frequency(self, frequency: str, options: list[str]) -> None:
        """Configure the external reference input frequency.

        Parameters:
            frequency:  Desired frequency.
            options:    Allowed frequencies.
        """
        frequency = self._is_valid_param(frequency, options)
        self._check_calibrating()
        self._scpi_protocol.write(f":ROSC:EXT:FREQ {frequency}")
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance.

        Raises:
            QMI_InstrumentException: on unexpected response to query.

        Returns:
            QMI_InstrumentIdentification: Instance of the instrument.
        """
        self._check_calibrating()
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")

        return QMI_InstrumentIdentification(
            vendor=words[0].strip(),
            model=words[1].strip(),
            serial=words[2].strip(),
            version=words[3].strip()
        )

    @rpc_method
    def start_calibration(self) -> None:
        """Start internal adjustments. Needs to be implemented further in the deriving classes.

        This function returns immediately after starting the calibration.

        Calibration can take up to 10 minutes. Call poll_calibration() to see
        whether calibration is complete. No other commands can be processed
        while the instrument is calibrating.

        The instrument must be at stable temperature (30 minutes to warm up)
        before starting internal adjustments.

        Attributes:
            self._calibrating: Set to `True` if starting the calibration succeeded.

        Raises:
            QMI_InstrumentException: If the result of previous calibration is still pending
        """
        self._check_calibrating()
        if self._calibration_result is not None:
            raise QMI_InstrumentException("Result of previous calibration is still pending")

        _logger.info("Starting internal adjustments")
        self._calibrating = True

    @rpc_method
    def poll_calibration(self) -> None | int:
        """Check whether an ongoing calibration is finished. If calibration is finished, this function returns a
        status code.

        Raises:
            QMI_InstrumentException: On calibration error or no calibration active.

        Returns:
            status_code: 0 - If calibration was successful.
                         1 - If calibration failed.
            None:        If calibration is not yet finished.
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
        """Reset the instrument, returning (most) settings to their defaults.

        Note that RST does not cancel an ongoing calibration.
        """
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
        self._scpi_protocol.write(f":PHAS {phase}")
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
            source: Desired reference source (accepted values: "INT", "EXT"); see also get_reference_source().
        """
        options = ["INT", "EXT"]
        source = self._is_valid_param(source, options)
        self._check_calibrating()
        self._scpi_protocol.write(f":ROSC:SOUR {source}")
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
            frequency: Target frequency in Hertz.
        """
        self._check_calibrating()
        self._scpi_protocol.write(f":FREQ {frequency}")
        self._check_error()

    @rpc_method
    def get_pulsemod_ext_source(self) -> bool:
        """Check pulse modulation source.

        Returns:
            boolean: True if pulse modulation uses an external source, else False.

        Raises:
            QMI_InstrumentException: On unexpected response.
        """
        self._check_calibrating()
        source = self._scpi_protocol.ask(":PULM:SOUR?").strip().upper()
        if source.startswith("EXT"):
            return True
        elif source.startswith("INT"):
            return False

        raise QMI_InstrumentException(f"Unexpected response {source!r} to command :PULM:SOUR?")

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

        Raises:
            QMI_InstrumentException: If using internal source and power above max power limit.
        """
        source = "EXT" if ext else "INT"
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and (not ext):
            if self.get_power() > self._max_continuous_power:
                raise QMI_InstrumentException(
                    f"Power limited to {self._max_continuous_power} dBm " +
                    "unless external pulse modulation source is selected"
                )

        self._scpi_protocol.write(f":PULM:SOUR {source}")
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
        options = ["OFF", "UNCH"]
        policy = self._is_valid_param(policy, options)
        self._check_calibrating()
        self._scpi_protocol.write(f":OUTP:PON {policy}")
        self._check_error()

    @rpc_method
    def get_pulsemod_polarity(self) -> bool:
        """Get pulse modulation polarity.

        Raises:
            QMI_InstrumentException: On unexpected response.

        Return:
             True if the external pulse modulation polarity is inverted; False if it is normal.
        """
        self._check_calibrating()
        resp = self._scpi_protocol.ask(":PULM:POL?").strip().upper()
        if resp.startswith("INV"):
            return True
        elif resp.startswith("NORM"):
            return False
        raise QMI_InstrumentException(f"Unexpected response {resp!r} ot command :PULM:POL?")

    @rpc_method
    def set_pulsemod_polarity(self, inverted: bool) -> None:
        """Enable or disable inverted polarity for external modulation.

        Parameters:
            inverted:   Boolean flag indicating if external modulation should be inverted.
                        For normal polarity (False), the RF signal is suppressed when the TRIG pulse is low.
                        For inverted polarity (True), the RF signal is suppressed when the TRIG pulse is high.

        Raises:
            QMI_InstrumentException: On using power beyond the max power limit.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and inverted:
            if self.get_power() > self._max_continuous_power:
                raise QMI_InstrumentException(
                    "Power limited to {} dBm unless pulse modulation source is non-inverted".format(
                        self._max_continuous_power))

        self._scpi_protocol.write(f":PULM:POL {'INV' if inverted else 'NORM'}")
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
            power: Target output power in dBm.

        Raises:
            QMI_InstrumentException: On power exceeding the power limit.
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

        self._scpi_protocol.write(f":POW {power}")
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
            enable: Target output state. True for enabled, False for disabled.

        Raises:
            QMI_InstrumentException: On power exceeding the power limit due to disable pulse modulation, using internal
                                     pulse modulation source or inverted external pulse source polarity.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and enable:
            if self.get_power() > self._max_continuous_power:
                if not self.get_pulsemod_enabled():
                    raise QMI_InstrumentException(
                        "Power limited to {} dBm unless pulse modulation is enabled".format(self._max_continuous_power)
                    )
                if not self.get_pulsemod_ext_source():
                    raise QMI_InstrumentException(
                        "Power limited to {} dBm unless external pulse modulation source is selected".format(
                            self._max_continuous_power
                        )
                    )
                if self.get_pulsemod_polarity():
                    raise QMI_InstrumentException(
                        "Power limited to {} dBm unless external pulse source polarity is non-inverted".format(
                            self._max_continuous_power
                        )
                    )

        self._scpi_protocol.write(f":OUTP {1 if enable else 0}")
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
            enable: Target pulse modulation state. True for enabled, False for disabled.

        Raises:
            QMI_InstrumentException: On power exceeding the power limit.
        """
        self._check_calibrating()

        # Safety check to prevent sample overheating.
        if (self._max_continuous_power is not None) and (not enable):
            if self.get_power() > self._max_continuous_power:
                raise QMI_InstrumentException(
                    "Pulse modulation cannot be enabled as power is set to {} dBm which is higher than the maximum {} dBm".format(
                        self.get_power(), self._max_continuous_power))

        self._scpi_protocol.write(f":PULM:STAT {1 if enable else 0}")
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
            enable: Target IQ modulation state. True for enabled, False for disabled.
        """
        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:STAT {1 if enable else 0}")
        self._check_error()

    @rpc_method
    def get_iq_wideband(self) -> bool:
        """Return True if wideband IQ modulation is enabled, False if disabled."""
        self._check_calibrating()
        return self._ask_bool(":IQ:WBST?")

    @rpc_method
    def set_iq_wideband(self, enable: bool) -> None:
        """Enable or disable wideband IQ modulation.

        Parameters:
            enable: Target wideband IQ modulation state. True for enabled, False for disabled.
        """
        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:WBST {1 if enable else 0}")
        self._check_error()

    @rpc_method
    def get_iq_quadrature_offset(self) -> float:
        """Return the current IQ quadrature offset."""
        self._check_calibrating()
        return self._ask_float(":IQ:IMP:QUAD?")

    @rpc_method
    def set_iq_quadrature_offset(self, phase: float) -> None:
        """Set the IQ quadrature offset between -8 and 8 degrees in increments of 0.01.

        Parameters:
            phase: Desired phase offset in degrees.

        Raises:
            ValueError: If phase offset not within -8 - 8 degrees.
        """
        if not -8.0 <= phase <= 8.0:
            raise ValueError("Phase offset should be in [-8, 8].")

        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:IMP:QUAD {phase:.2f}")
        self._check_error()

    @rpc_method
    def get_iq_leakage_i(self) -> float:
        """Return the current I leakage amplitude (percent)."""
        self._check_calibrating()
        return self._ask_float(":IQ:IMP:LEAK:I?")

    @rpc_method
    def set_iq_leakage_i(self, leakage: float) -> None:
        """Set the I leakage amplitude between -5 and 5 (percent), in increments of 0.01.

        Parameters:
            leakage:    leakage amplitude in percent.

        Raises:
            ValueError: If leakage amplitude not within -5 - 5 percent.
        """
        if not -5.0 <= leakage <= 5.0:
            raise ValueError("Leakage offset should be in [-5, 5].")
        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:IMP:LEAK:I {leakage:.2f}")
        self._check_error()

    @rpc_method
    def get_iq_leakage_q(self) -> float:
        """Return the current Q leakage amplitude (percent)."""
        self._check_calibrating()
        return self._ask_float(":IQ:IMP:LEAK:Q?")

    @rpc_method
    def set_iq_leakage_q(self, leakage: float) -> None:
        """Set the Q leakage amplitude between -5 and 5 (percent), in increments of 0.01.

        Parameters:
            leakage: Leakage amplitude in percent.

        Raises:
            ValueError: If leakage amplitude not within -5 - 5 percent.
        """
        if not -5.0 <= leakage <= 5.0:
            raise ValueError("Leakage offset should be in [-5, 5].")

        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:IMP:LEAK:Q {leakage:.2f}")
        self._check_error()

    @rpc_method
    def get_iq_gain_imbalance(self) -> float:
        """Return the current IQ gain imbalance (dB)."""
        self._check_calibrating()
        return self._ask_float(":IQ:IMP:IQR:MAGN?")

    @rpc_method
    def set_iq_gain_imbalance(self, gain: float) -> None:
        """Set the IQ gain imbalance in dB in range -1 to 1, increments of 0.001.

        Parameters:
            gain: Desired gain in dB.

        Raises:
            ValueError: If gain imbalance not within -1 - 1 dB.
        """
        if not -1.0 <= gain <= 1.0:
            raise ValueError("Gain imbalance should be in [-1, 1].")

        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:IMP:IQR:MAGN {gain:.3f}")
        self._check_error()

    @rpc_method
    def get_iq_crest_factor(self) -> float:
        """Return the current IQ crest factor compensation in dB."""
        self._check_calibrating()
        return self._ask_float(":IQ:CRES?")

    @rpc_method
    def set_iq_crest_factor(self, factor: float) -> None:
        """Set the IQ crest factor compensation in dB.

        Parameters:
            factor: Crest factor in dB.
        """
        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:CRES {factor}")
        self._check_error()

    @rpc_method
    def get_errors(self) -> None:
        """Queries the error/event queue for all unread items and removes them from the queue."""
        return self._check_error()

    @rpc_method
    def get_error_queue_length(self) -> int:
        """Queries the number of entries in the error queue."""
        return int(self._scpi_protocol.ask('SYST:ERR:COUN?'))
