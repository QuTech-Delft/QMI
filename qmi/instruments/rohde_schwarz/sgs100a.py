"""
Instrument driver for the Rohde&Schwarz SGS100A RF Signal Generator
"""

import logging

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.instruments.rohde_schwarz.rs_base_signal_gen import RohdeSchwarz_Base

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class RohdeSchwarz_SGS100A(RohdeSchwarz_Base):
    """Instrument driver for the Rohde&Schwarz SGS100A RF Signal Generator."""

    @rpc_method
    def get_external_reference_frequency(self) -> str:
        """Return the currently configured external reference input frequency.

        Possible values: "10MHZ", "100MHZ", "1000MHZ".
        """
        return self._get_external_reference_frequency()

    @rpc_method
    def set_external_reference_frequency(self, frequency: str) -> None:
        """Configure the external reference input frequency.

        Parameters:
            frequency: desired frequency (accepted values: "10MHZ", "100MHZ", "1000MHZ"); see also
                       get_external_reference_frequency().
        """
        freq_options = ["10MHZ", "100MHZ", "1000MHZ"]
        self._set_external_reference_frequency(frequency, freq_options)

    @rpc_method
    def get_external_reference_bandwidth(self) -> str:
        """Return the current external reference synchronization bandwidth.

        Possible values:
          "NARR" - approximately 40 Hz synchronization bandwidth;
          "WIDE" - approximately 250 Hz synchronization bandwidth - suitable for high quality reference source.
        """
        self._check_calibrating()
        return self._scpi_protocol.ask(":ROSC:EXT:SBAN?").strip().upper()

    @rpc_method
    def set_external_reference_bandwidth(self, bandwidth: str) -> None:
        """Set the external reference synchronization bandwidth.

        Parameters:
            bandwidth:  desired bandwith (accepted values: "NARR", "WIDE"); see also
                        get_external_reference_bandwidth().
        """
        bandwidth = bandwidth.upper()
        if bandwidth not in ("NARR", "WIDE"):
            raise ValueError("Unknown value {}".format(bandwidth))
        self._check_calibrating()
        self._scpi_protocol.write(":ROSC:EXT:SBAN {}".format(bandwidth))
        self._check_error()

    @rpc_method
    def get_trigger_impedance(self) -> str:
        """Return current input impedance of the TRIG port.

        Possible values:
          "G50"  - 50 Ohm input impedance (default)
          "G10K" - 10 kOhm input impedance
        """
        self._check_calibrating()
        return self._scpi_protocol.ask(":PULM:TRIG:EXT:IMP?").strip().upper()

    @rpc_method
    def set_trigger_impedance(self, impedance: str) -> None:
        """Set the input impedance of the TRIG port.

        Parameters:
            impedance:  desired input impedance (accepted values: "G50", "G10K"); see also get_trigger_impedance().
        """
        impedance = impedance.upper()
        if impedance not in ("G50", "G10K"):
            raise ValueError("Unknown value {}".format(impedance))
        self._check_calibrating()
        self._scpi_protocol.write(":PULM:TRIG:EXT:IMP {}".format(impedance))
        self._check_error()

    @rpc_method
    def start_calibration(self) -> None:
        """Start internal adjustments.

        This function returns immediately after starting the calibration.

        Calibration can take up to 10 minutes. Call poll_calibration() to see
        whether calibration is complete. No other commands can be processed
        while the instrument is calibrating.

        The instrument must be at stable temperature (30 minutes to warm up)
        before starting internal adjustments.
        """
        self._check_calibrating()
        if self._calibration_result is not None:
            raise QMI_InstrumentException("Result of previous calibration is still pending")
        _logger.info("Starting internal adjustments")
        self._scpi_protocol.write(":CAL:ALL?")
        self._calibrating = True

    @rpc_method
    def get_iq_wideband(self) -> bool:
        """Return True if wideband IQ modulation is enabled, False if disabled."""
        self._check_calibrating()
        return self._ask_bool(":IQ:WBST?")

    @rpc_method
    def set_iq_wideband(self, enable: bool) -> None:
        """Enable or disable wideband IQ modulation.

        Parameters:
            enable: target enabled state.
        """
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:WBST {}".format(1 if enable else 0))
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
            factor: crest factor in dB.
        """
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:CRES {}".format(factor))
        self._check_error()

    @rpc_method
    def get_iq_correction_enabled(self) -> bool:
        """Return True if IQ modulation corrections are enabled, False if disabled."""
        self._check_calibrating()
        return self._ask_bool(":IQ:IMP:STAT?")

    @rpc_method
    def set_iq_correction_enabled(self, enable: bool) -> None:
        """Activate/deactivate the three correction values for the I/Q modulator.

        Parameters:
            enable: target enabled state.
        """
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:IMP:STAT {}".format(1 if enable else 0))
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
            phase:  desired phase offset in degrees.
        """
        if not -8.0 <= phase <= 8.0:
            raise ValueError("Phase offset should be in [-8, 8].")
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:IMP:QUAD {:.2f}".format(phase))
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
        """
        if not -5.0 <= leakage <= 5.0:
            raise ValueError("Leakage offset should be in [-5, 5].")
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:IMP:LEAK:I {:.2f}".format(leakage))
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
            leakage:    leakage amplitude in percent.
        """
        if not -5.0 <= leakage <= 5.0:
            raise ValueError("Leakage offset should be in [-5, 5].")
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:IMP:LEAK:Q {:.2f}".format(leakage))
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
            gain:   desired gain in dB.
        """
        if not -1.0 <= gain <= 1.0:
            raise ValueError("Gain imabalance should be in [-1, 1].")
        self._check_calibrating()
        self._scpi_protocol.write(":IQ:IMP:IQR:MAGN {:.3f}".format(gain))
        self._check_error()