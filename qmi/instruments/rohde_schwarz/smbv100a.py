"""
Instrument driver for the Rohde&Schwarz SMBV100A RF Signal Generator
"""

import logging
from typing import Any, List
import numpy as np

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.rpc import rpc_method
from qmi.instruments.rohde_schwarz.rs_base_signal_gen import RohdeSchwarz_Base

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

class RohdeSchwarz_SMBV100A(RohdeSchwarz_Base):
    """Instrument driver for the Rohde&Schwarz SMBV100A RF Signal Generator."""

    def _create_list(self, start, stop, unit, number_of_steps) -> str:
        """
        Create a list of values given the start, stop and step values.
        Append the unit to the values in the list.

        Parameters:
            start:             The starting value of the list.
            stop:              The ending value of the list.
            unit:              The unit of the values.
            number_of_steps:   The number of steps in the list.
        """
        array: np.ndarray[Any, Any] = np.linspace(start, stop, number_of_steps)
        return ','.join(map(lambda l: str(l) + unit, list(array)))

    def _set_sig_for_iq_mod(self, sig: str) -> None:
        """
        Sets the input signal for I/Q modulation.
        This private version of the method does not perform any
        calibration or error checks, since it is used by the
        calibration method.

        Parameters:
            sig: 'bas', 'anal' or 'diff'
        """
        valid_params: List[str] = ['BAS', 'ANAL', 'DIFF']
        sig = self._is_valid_param(sig, valid_params)
        _logger.info(__name__ + ' : setting input signal for IQ modulation to "%s"' % sig)
        self._scpi_protocol.write('IQ:SOUR %s' % sig)

    @rpc_method
    def set_sig_for_iq_mod(self, sig: str) -> None:
        """
        Sets the input signal for I/Q modulation.

        Parameters:
            sig: 'bas', 'anal' or 'diff'
        """
        self._check_calibrating()
        valid_params: List[str] = ['BAS', 'ANAL', 'DIFF']
        sig = self._is_valid_param(sig, valid_params)
        _logger.info(__name__ + ' : setting input signal for IQ modulation to "%s"' % sig)
        self._scpi_protocol.write('IQ:SOUR %s' % sig)
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
            frequency: desired frequency (accepted values: "5MHZ", "10MHZ"); see also
                       get_external_reference_frequency().
        """
        freq_options = ["5MHZ", "10MHZ"]
        self._set_external_reference_frequency(frequency, freq_options)

    def _set_iq_mod(self, toggle: bool) -> None:
        """
        Turns on or off the I/Q modulation.
        This private version of the method does not perform any
        calibration or error checks, since it is used by the
        calibration method.

        Parameters:
            toggle: boolean flag to turn IQ modulation on/off
        """
        iq = 'ON' if toggle else 'OFF'
        _logger.info(__name__ + ' : turning "%s" IQ modulation' % iq)
        self._scpi_protocol.write('IQ:STAT %s' % iq)

    def _activate_iq_mod(self) -> None:
        """
        Activates the I/Q modulation.
        This private version of the method does not perform any
        calibration or error checks, since it is used by the
        calibration method.
        """
        self._set_iq_mod(True)

    def _deactivate_iq_mod(self) -> None:
        """
        Deactivates the I/Q modulation.
        This private version of the method does not perform any
        calibration or error checks, since it is used by the
        calibration method.
        """
        self._set_iq_mod(False)

    @rpc_method
    def set_iq_mod(self, toggle: bool) -> None:
        """
        Turns on or off the I/Q modulation.

        Parameters:
            toggle: boolean flag to turn IQ modulation on/off
        """
        self._check_calibrating()
        iq = 'ON' if toggle else 'OFF'
        _logger.info(__name__ + ' : turning "%s" IQ modulation' % iq)
        self._scpi_protocol.write('IQ:STAT %s' % iq)
        self._check_error()

    @rpc_method
    def activate_iq_mod(self) -> None:
        """
        Activates the I/Q modulation.
        """
        self.set_iq_mod(True)

    @rpc_method
    def deactivate_iq_mod(self) -> None:
        """
        Deactivates the I/Q modulation.
        """
        self.set_iq_mod(False)

    def _set_iq(self, toggle: bool) -> None:
        """
        Activates external I/Q modulation with analog signal.
        This private version of the method does not perform any
        calibration or error checks, since it is used by the
        calibration method.

        Parameters:
            toggle: boolean flag to turn IQ modulation on/off
        """
        iq = 'ON' if toggle else 'OFF'
        _logger.info(__name__ + ' : setting external IQ modulation to "%s"' % iq)
        self._set_sig_for_iq_mod('ANAL')
        self._activate_iq_mod() if toggle else self._deactivate_iq_mod()

    @rpc_method
    def set_iq(self, toggle: bool) -> None:
        """
        Activates external I/Q modulation with analog signal.

        Parameters:
            toggle: boolean flag to turn IQ modulation on/off
        """
        iq = 'ON' if toggle else 'OFF'
        _logger.info(__name__ + ' : setting external IQ modulation to "%s"' % iq)
        self.set_sig_for_iq_mod('ANAL')
        self.activate_iq_mod() if toggle else self.deactivate_iq_mod()

    @rpc_method
    def set_freq_mode(self, mode: str) -> None:
        """
        Sets RF frequency mode to list, sweep or fixed.
        CW and FIX are the same

        Parameters:
            mode: 'fix', 'list', 'swe' or 'cw'
        """
        valid_params: List[str] = ['FIX', 'LIST', 'SWE', 'CW']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting RF frequency mode to "%s"' % mode)
        self._scpi_protocol.write('SOUR:FREQ:MODE %s' % mode)
        self._check_error()

    @rpc_method
    def set_sweep_frequency_start(self, frequency: float) -> None:
        """
        Set start frequency of sweep.

        Input:
            frequency: frequency in Hz
        """
        self._check_calibrating()
        _logger.info(__name__ + ' : setting sweep frequency start to %s Hz' % frequency)
        self._scpi_protocol.write('FREQ:STAR %s Hz' % frequency)
        self._check_error()

    @rpc_method
    def set_sweep_frequency_stop(self, frequency: float) -> None:
        """
        Set stop frequency of sweep.

        Input:
            frequency: frequency in Hz
        """
        self._check_calibrating()
        _logger.info(__name__ + ' : setting sweep frequency stop to %s Hz' % frequency)
        self._scpi_protocol.write('FREQ:STOP %s Hz' % frequency)
        self._check_error()

    @rpc_method
    def set_sweep_frequency_step(self, frequency: float) -> None:
        """
        Set step frequency of sweep.

        Input:
            frequency: frequency in Hz
        """
        self._check_calibrating()
        _logger.info(__name__ + ' : setting sweep frequency step to %s Hz' % frequency)
        self._scpi_protocol.write('SWE:STEP:LIN %s Hz' % frequency)
        self._check_error()

    @rpc_method
    def start_calibration(self, all = False, cal_iqm = True) -> None:
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
        self._calibrating = True

    @rpc_method
    def enable_list_mode(self) -> None:
        """
        Enable list mode.
        """
        self.set_freq_mode('LIST')

    @rpc_method
    def set_list_processing_mode(self, mode: str) -> None:
        """
        Selects how the list is to be processed.

        Parameters:
            mode: 'auto' or 'step'
        """
        valid_params: List[str] = ['AUTO', 'STEP']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting list processing mode to "%s"' % mode)
        self._scpi_protocol.write('LIST:MODE %s' % mode)
        self._check_error()

    @rpc_method
    def enable_list_step_mode(self):
        """
        Selects step-by-step processing of the list.
        """
        self.set_list_processing_mode('STEP')

    @rpc_method
    def set_trigger_source_processing_lists(self, mode: str) -> None:
        """
        Sets the trigger source processing lists.

        Parameters:
            mode: 'auto', 'imm', 'sing' or 'ext'
        """
        valid_params: List[str] = ['AUTO', 'IMM', 'SING', 'EXT']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting trigger source processing list to "%s"' % mode)
        self._scpi_protocol.write('LIST:TRIG:SOUR %s' % mode)
        self._check_error()

    @rpc_method
    def set_list_ext_trigger_source(self):
        """
        Selects triggering by means of the external trigger.
        """
        self.set_trigger_source_processing_lists('EXT')

    @rpc_method
    def set_freq_sweep_mode(self, mode: str):
        """
        Selects the frequency sweep mode.

        Parameters:
            mode: 'auto' or 'step'
        """
        valid_params: List[str] = ['STEP', 'AUTO']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting frequency sweep mode to "%s"' % mode)
        self._scpi_protocol.write('SOUR:SWE:FREQ:MODE %s' % mode)
        self._check_error()

    @rpc_method
    def set_freq_sweep_spacing_mode(self, mode: str):
        """
        Selects the frequency sweep spacing mode.

        Parameters:
            mode: 'log' or 'lin'
        """
        valid_params: List[str] = ['LIN', 'LOG']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting frequency sweep spacing mode to "%s"' % mode)
        self._scpi_protocol.write('SOUR:SWE:FREQ:SPAC %s' % mode)
        self._check_error

    @rpc_method
    def set_trig_source_freq_sweep(self, mode: str):
        """
        Sets the trigger source for the RF frequency sweep.

        Parameters:
            mode: 'auto', 'sing', 'ext' or 'eaut'
        """
        valid_params: List[str] = ['AUTO', 'SING', 'EXT', 'EAUT']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting trigger source for frequency sweep to "%s"' % mode)
        self._scpi_protocol.write('TRIG:FSW:SOUR %s' % mode)
        self._check_error

    @rpc_method
    def set_freq_mode_sig_gen(self, mode: str):
        """
        Selects the frequency mode for generating the RF output signal.

        Parameters:
            mode: 'cw', 'fix', 'swe' or 'list'
        """
        valid_params: List[str] = ['CW', 'FIX', 'SWE', 'LIST']
        mode = self._is_valid_param(mode, valid_params)
        self._check_calibrating()
        _logger.info(__name__ + ' : setting frequency mode for generating output signal to "%s"' % mode)
        self._scpi_protocol.write('SOUR:FREQ:MODE %s' % mode)
        self._check_error

    @rpc_method
    def enable_ext_freq_sweep_mode(self):
        """
        Generates the sweep signal step-by-step, manually triggered.
        To trigger a sweep step, apply an external trigger signal. The step
        width corresponds to the step width set for the rotary knob.
        """
        self.set_freq_sweep_mode('STEP')
        self.set_freq_sweep_spacing_mode('LIN')
        self.set_trig_source_freq_sweep('EXT')
        self.set_freq_mode_sig_gen('SWE')

    @rpc_method
    def reset_sweep(self):
        """
        Resets all active sweeps to the starting points.
        """
        self._check_calibrating()
        _logger.info(__name__ + ' : resetting all active sweeps to the starting points.')
        self._scpi_protocol.write('SOUR:SWE:RES:ALL')
        self._check_error()

    @rpc_method
    def reset_list_mode(self):
        """
        Resets the list to the starting point.
        """
        self._check_calibrating()
        _logger.info(__name__ + ' : resetting the list to the starting point')
        self._scpi_protocol.write('SOUR:LIST:RES')
        self._check_error()

    @rpc_method
    def learn_list(self):
        """
        Learns the selected list to determine the hardware setting for
        all list entries. The results are saved with the list. When
        the list is activated the first time, these settings are
        calculated automatically.
        """
        self._check_calibrating()
        _logger.info(__name__ + ' : learning the list')
        self._scpi_protocol.write('SOUR:LIST:LEAR')
        self._check_error()

    # TODO: find documentation for this
    @rpc_method
    def reset_list(self):
        self._check_calibrating()
        self._scpi_protocol.write('ABOR:LIST')
        self._check_error()

    @rpc_method
    def load_fplist(
            self, fstart: str, fstop: str, funit: str, number_of_steps: str, pstart: str, pstop: str, punit: str
    ):
        """
        Loads a frequency and power list.

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
        self._scpi_protocol.write('SOUR:LIST:SEL "list_%s_%s_%s"'%(fstart, fstop, number_of_steps))

        # create both frequency and power lists and format as comma separated values
        flist = self._create_list(fstart, fstop, funit, number_of_steps)
        plist = self._create_list(pstart, pstop, punit, number_of_steps)

        # write the lists to the instrument
        self._scpi_protocol.write('SOUR:LIST:FREQ ' + flist)
        self._scpi_protocol.write('SOUR:LIST:POW ' + plist)
        self._check_error()