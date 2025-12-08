"""
Instrument driver for the Rohde&Schwarz SGS100A RF Signal Generator.
"""

import logging

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
            frequency: Desired frequency (accepted values: "10MHZ", "100MHZ", "1000MHZ"); see also
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
            bandwidth: Desired bandwidth (accepted values: "NARR", "WIDE");
                       see also get_external_reference_bandwidth().
        """
        options = ["NARR", "WIDE"]
        bandwidth = self._is_valid_param(bandwidth, options)

        self._check_calibrating()
        self._scpi_protocol.write(f":ROSC:EXT:SBAN {bandwidth}")
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
            impedance: Desired input impedance (accepted values: "G50", "G10K"); see also get_trigger_impedance().
        """
        options = ["G50", "G10K"]
        impedance = self._is_valid_param(impedance, options)

        self._check_calibrating()
        self._scpi_protocol.write(f":PULM:TRIG:EXT:IMP {impedance}")
        self._check_error()

    @rpc_method
    def start_calibration(self) -> None:
        super().start_calibration()
        self._scpi_protocol.write(":CAL:ALL?")

    @rpc_method
    def get_iq_correction_enabled(self) -> bool:
        """Return True if IQ modulation corrections (impairment) are enabled, False if disabled."""
        self._check_calibrating()
        return self._ask_bool(":IQ:IMP:STAT?")

    @rpc_method
    def set_iq_correction_enabled(self, enable: bool) -> None:
        """Activate/deactivate the three correction values for the I/Q modulator.

        Parameters:
            enable: Target IQ corrections (impairment) state. True for enabled, False for disabled.
        """
        self._check_calibrating()
        self._scpi_protocol.write(f":IQ:IMP:STAT {1 if enable else 0}")
        self._check_error()
