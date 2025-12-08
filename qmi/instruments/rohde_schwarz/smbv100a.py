"""
Instrument driver for the Rohde&Schwarz SMBV100A RF Signal Generator.
"""

import logging
from typing import Union
import numpy as np

from qmi.core.rpc import rpc_method
from qmi.instruments.rohde_schwarz.rs_base_signal_gen import RohdeSchwarz_Base

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def _create_list(start: Union[float, int], stop: Union[float, int], unit: str, number_of_steps: int) -> str:
    """Create a list of values given the start, stop and step values.
    Append the unit to the values in the list.

    Parameters:
        start:             The starting value of the list.
        stop:              The ending value of the list.
        unit:              The unit of the values.
        number_of_steps:   The number of steps in the list.
    """
    array: np.ndarray = np.linspace(start, stop, number_of_steps)
    return ",".join(map(lambda l: str(l) + unit, list(array)))


class RohdeSchwarz_SMBV100A(RohdeSchwarz_Base):
    """Instrument driver for the Rohde&Schwarz SMBV100A RF Signal Generator."""

    def _set_sig_for_iq_mod(self, sig: str) -> None:
        """Sets the input signal for I/Q modulation.

        This private version of the method does not perform any calibration or error checks,
        since it is used by the calibration method.

        Parameters:
            sig: "bas", "anal" or "diff".
        """
        options = ["BAS", "ANAL", "DIFF"]
        sig = self._is_valid_param(sig, options)
        _logger.info(__name__ + " : setting input signal for IQ modulation to '%s'" % sig)
        self._scpi_protocol.write(f":IQ:SOUR {sig}")

    @rpc_method
    def set_sig_for_iq_mod(self, sig: str) -> None:
        """Sets the input signal for I/Q modulation.

        Parameters:
            sig: "bas", "anal" or "diff".
        """
        self._check_calibrating()
        self._set_sig_for_iq_mod(sig)
        self._check_error()

    @rpc_method
    def get_external_reference_frequency(self) -> str:
        """Return the currently configured external reference input frequency.

        Possible values: "5MHZ", "10MHZ".
        """
        return self._get_external_reference_frequency()

    @rpc_method
    def set_external_reference_frequency(self, frequency: str) -> None:
        """Configure the external reference input frequency.

        Parameters:
            frequency: Desired frequency (accepted values: "5MHZ", "10MHZ");
                       see also get_external_reference_frequency().
        """
        freq_options = ["5MHZ", "10MHZ"]
        self._set_external_reference_frequency(frequency, freq_options)

    def _set_iq(self, toggle: bool) -> None:
        """Activates external I/Q modulation with analog signal.

        This private version of the method does not perform any calibration or error checks,
        since it is used by the calibration method.

        Parameters:
            toggle: Boolean flag to turn IQ modulation on/off.
        """
        iq = "ON" if toggle else "OFF"
        _logger.info(__name__ + " : setting external IQ modulation to '%s'" % iq)
        self._set_sig_for_iq_mod("ANAL")
        self._scpi_protocol.write(f":IQ:STAT {1 if toggle else 0}")

    @rpc_method
    def set_iq(self, toggle: bool) -> None:
        """Activates external I/Q modulation with analog signal.

        Parameters:
            toggle: boolean flag to turn IQ modulation on/off.
        """
        self._set_iq(toggle)

    @rpc_method
    def set_freq_mode(self, mode: str) -> None:
        """Sets RF frequency mode to list, sweep or fixed. CW and FIX are the same.

        Parameters:
            mode: "fix", "list", "swe" or "cw"
        """
        options = ["FIX", "LIST", "SWE", "CW"]
        mode = self._is_valid_param(mode, options)
        self._check_calibrating()
        _logger.info(__name__ + " : setting RF frequency mode to '%s'" % mode)
        self._scpi_protocol.write(f"SOUR:FREQ:MODE {mode}")
        self._check_error()

    @rpc_method
    def set_sweep_frequency_start(self, frequency: float) -> None:
        """Set start frequency of sweep.

        Parameters:
            frequency: Frequency in Hz.
        """
        self._check_calibrating()
        _logger.info(__name__ + " : setting sweep frequency start to %s Hz" % frequency)
        self._scpi_protocol.write(f"FREQ:STAR {frequency} Hz")
        self._check_error()

    @rpc_method
    def set_sweep_frequency_stop(self, frequency: float) -> None:
        """Set stop frequency of sweep.

        Parameters:
            frequency: Frequency in Hz.
        """
        self._check_calibrating()
        _logger.info(__name__ + " : setting sweep frequency stop to %s Hz" % frequency)
        self._scpi_protocol.write(f"FREQ:STOP {frequency} Hz")
        self._check_error()

    @rpc_method
    def set_sweep_frequency_step(self, frequency: float) -> None:
        """Set step frequency of sweep.

        Parameters:
            frequency: Frequency in Hz.
        """
        self._check_calibrating()
        _logger.info(__name__ + " : setting sweep frequency step to %s Hz" % frequency)
        self._scpi_protocol.write(f"SWE:STEP:LIN {frequency} Hz")
        self._check_error()

    @rpc_method
    def start_calibration(self, all: bool = False, cal_iqm: bool = True) -> None:
        """Start a calibration of the device. This method can be used to calibrate all internal adjustments,
        or to select a partial device calibration. This method does not use external measurement equipment.

        Parameters:
            all:     Boolean to select if to calibrate everything.
            cal_iqm: Boolean to select if to calibrate IQ modulator. Has effect only if 'all' is False.
        """
        super().start_calibration()
        if all:
            self._scpi_protocol.write("CAL:ALL:MEAS?")

        else:
            self._scpi_protocol.write("CAL:FREQ:MEAS?")
            _logger.info("Frequency calibrated")
            self._scpi_protocol.write("CAL:LEV:MEAS?")
            _logger.info("Level calibrated")
            if cal_iqm:
                self._set_iq(True)
                self._scpi_protocol.write("CAL:IQM:LOC?")
                _logger.info("IQ modulator calibrated")

    @rpc_method
    def enable_list_mode(self) -> None:
        """Convenience function to set RF frequency to list mode."""
        self.set_freq_mode("LIST")

    @rpc_method
    def set_list_processing_mode(self, mode: str) -> None:
        """Selects how the list is to be processed.

        Parameters:
            mode: "auto" or "step".
        """
        options = ["AUTO", "STEP"]
        mode = self._is_valid_param(mode, options)
        self._check_calibrating()
        _logger.info(__name__ + " : setting list processing mode to '%s'" % mode)
        self._scpi_protocol.write(f"LIST:MODE {mode}")
        self._check_error()

    @rpc_method
    def enable_list_step_mode(self):
        """Convenience function to select step-by-step processing of the list."""
        self.set_list_processing_mode("STEP")

    @rpc_method
    def set_trigger_source_processing_lists(self, mode: str) -> None:
        """Sets the trigger source processing lists.

        Parameters:
            mode: "auto", "imm", "sing" or "ext".
        """
        options = ["AUTO", "IMM", "SING", "EXT"]
        mode = self._is_valid_param(mode, options)
        self._check_calibrating()
        _logger.info(__name__ + " : setting trigger source processing list to '%s'" % mode)
        self._scpi_protocol.write(f"LIST:TRIG:SOUR {mode}")
        self._check_error()

    @rpc_method
    def set_list_ext_trigger_source(self):
        """Selects triggering by means of the external trigger."""
        self.set_trigger_source_processing_lists("EXT")

    @rpc_method
    def set_freq_sweep_mode(self, mode: str):
        """Selects the frequency sweep mode.

        Parameters:
            mode: "auto" or "step".
        """
        options = ["STEP", "AUTO"]
        mode = self._is_valid_param(mode, options)
        self._check_calibrating()
        _logger.info(__name__ + " : setting frequency sweep mode to '%s'" % mode)
        self._scpi_protocol.write(f"SOUR:SWE:FREQ:MODE {mode}")
        self._check_error()

    @rpc_method
    def set_freq_sweep_spacing_mode(self, mode: str):
        """Selects the frequency sweep spacing mode.

        Parameters:
            mode: "log" or "lin".
        """
        options = ["LIN", "LOG"]
        mode = self._is_valid_param(mode, options)
        self._check_calibrating()
        _logger.info(__name__ + " : setting frequency sweep spacing mode to '%s'" % mode)
        self._scpi_protocol.write(f"SOUR:SWE:FREQ:SPAC {mode}")
        self._check_error()

    @rpc_method
    def set_trig_source_freq_sweep(self, mode: str):
        """Sets the trigger source for the RF frequency sweep.

        Parameters:
            mode: "auto", "sing", "ext" or "eaut".
        """
        options = ["AUTO", "SING", "EXT", "EAUT"]
        mode = self._is_valid_param(mode, options)
        self._check_calibrating()
        _logger.info(__name__ + " : setting trigger source for frequency sweep to '%s'" % mode)
        self._scpi_protocol.write(f"TRIG:FSW:SOUR {mode}")
        self._check_error()

    @rpc_method
    def enable_ext_freq_sweep_mode(self):
        """Convenience function to generate sweep signal step-by-step, manually triggered.
        To trigger a sweep step, apply an external trigger signal. The step width corresponds
        to the step width set for the rotary knob.
        """
        self.set_freq_sweep_mode("STEP")
        self.set_freq_sweep_spacing_mode("LIN")
        self.set_trig_source_freq_sweep("EXT")
        self.set_freq_mode("SWE")

    @rpc_method
    def reset_sweep(self):
        """Resets all active sweeps to the starting points."""
        self._check_calibrating()
        _logger.info(__name__ + " : resetting all active sweeps to the starting points.")
        self._scpi_protocol.write("SOUR:SWE:RES:ALL")
        self._check_error()

    @rpc_method
    def reset_list_mode(self):
        """Resets the list to the starting point."""
        self._check_calibrating()
        _logger.info(__name__ + " : resetting the list to the starting point")
        self._scpi_protocol.write("SOUR:LIST:RES")
        self._check_error()

    @rpc_method
    def learn_list(self):
        """Learns the selected list to determine the hardware setting for all list entries.
        The results are saved with the list. When the list is activated the first time,
        these settings are calculated automatically.
        """
        self._check_calibrating()
        _logger.info(__name__ + " : learning the list")
        self._scpi_protocol.write("SOUR:LIST:LEAR")
        self._check_error()

    # TODO: find documentation for this
    @rpc_method
    def reset_list(self):
        self._check_calibrating()
        self._scpi_protocol.write("ABOR:LIST")
        self._check_error()

    @rpc_method
    def load_fplist(
        self,
        fstart: float,
        fstop: float,
        funit: str,
        number_of_steps: int,
        pstart: float,
        pstop: float,
        punit: str
    ):
        """Loads a frequency and power list.

        Parameters:
            fstart:             The starting frequency of the list.
            fstop:              The ending frequency of the list.
            funit:              The unit of the frequency.
            number_of_steps:    The number of steps in the list.
            pstart:             The starting power of the list.
            pstop:              The ending power of the list.
            punit:              The unit of the power.
        """
        self._check_calibrating()
        # create new list
        self._scpi_protocol.write(f"SOUR:LIST:SEL 'list_{fstart}_{fstop}_{number_of_steps}'")

        # create both frequency and power lists and format as comma separated values
        flist = _create_list(fstart, fstop, funit, number_of_steps)
        plist = _create_list(pstart, pstop, punit, number_of_steps)

        # write the lists to the instrument
        self._scpi_protocol.write("SOUR:LIST:FREQ " + flist)
        self._scpi_protocol.write("SOUR:LIST:POW " + plist)
        self._check_error()
