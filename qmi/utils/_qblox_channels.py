"""QBlox channel classes for controlling Qblox module (D|A)I/O channels per module (ADC, DAC, marker, IO).
These classes have been tested with QCM, QRM, -RF and QTM. For QTM mainly the data acquisition has been developed,
ADC control is still TBD.

The channel classes still contains several TODO:s. Please report any issues in QMI Github at
https://github.com/QuTech-Delft/QMI/issues
"""
import logging
from typing import Callable, Any

from qmi.instruments.qblox.cluster import EXT_TRIGGERS_IN_CLUSTER

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class _QbloxChannel:
    """Base class for ADC, DAC, IO and marker channels in Qblox modules.

    Attributes:
        CHANNEL_LEVEL_RANGE:  The valid range for setting channel level or threshold in bits.
        OUTPUT_VOLTAGE_RANGE: Allowed voltage range on DAC, marker or QTM digital output channel. In Volts.
        INPUT_VOLTAGE_RANGE:  Allowed voltage range on ADC or QTM digital input channel. In Volts.
    """

    CHANNEL_LEVEL_RANGE: int = 2**16 - 1
    # Marker channel is LVTTL for 50Ohm. QTM input threshold V is in 11 bit range. DACs are 50Ohm, terminated at 1GBps.
    OUTPUT_VOLTAGE_RANGE: dict[str, list[float]] = {
        "QRM": [-0.5, 0.5],
        "QCM": [-2.5, 2.5],
        "QRM-RF": [-2.5, 2.5],
        "QCM-RF": [-0.5, 0.5],
        "MRK": [0, 3.3],
        "QTM": [0, 3.3],
    }
    INPUT_VOLTAGE_RANGE: dict[str, list[float]] = {"QRM": [-1.0, 1.0], "QRM-RF": [-1.0, 1.0], "QTM": [0, 5]}

    def __init__(self, module_func_refs: dict[str, Callable], slot: int, sequencer: int, channel_no: int) -> None:
        """Initialise a Qblox ADC, DAC or Marker channel instance with respective sequencer configuration.

        Parameters:
            module_func_refs:      Function references callable at a module.
            slot:                  The slot number of the module.
            sequencer:             The sequencer number assigned to channel.
            channel_no:            The channel number.
        """
        _logger.info(
            f"Creating a QbloxChannel instance for module in slot {slot} with channel number {channel_no}"
            + f" and sequencer_number {sequencer}"
        )
        self._module_func_refs = module_func_refs
        self._sequencer = sequencer
        self._channel = channel_no
        self._channel_cfg: dict = {}
        # Some SCPI commands need a prefix
        self.scpi_cmd_prefix = f"SLOT{slot}:SEQuencer{self._sequencer}"
        self._is_qcm_type = module_func_refs["is_qcm_type"]()
        self._is_qrm_type = module_func_refs["is_qrm_type"]()
        self._is_qtm_type = module_func_refs["is_qtm_type"]()
        self._is_rf_type = module_func_refs["is_rf_type"]()
        self._name = ""
        if self._is_rf_type:
            if self._is_qcm_type:
                self._voltage_range = self.OUTPUT_VOLTAGE_RANGE["QCM-RF"]
                self._name = f"QCM-RF_{channel_no}"
            elif self._is_qrm_type:
                self._voltage_range = self.OUTPUT_VOLTAGE_RANGE["QRM-RF"]
                self._name = f"QRM-RF_{channel_no}"
            else:
                raise RuntimeError(f"Invalid RF-type module for slot {slot}")

        elif self._is_qcm_type:
            self._voltage_range = self.OUTPUT_VOLTAGE_RANGE["QCM"]
            self._name = f"QCM_{channel_no}"
        elif self._is_qrm_type:
            self._voltage_range = self.OUTPUT_VOLTAGE_RANGE["QRM"]
            self._name = f"QRM_{channel_no}"
        elif self._is_qtm_type:
            self._voltage_range = self.OUTPUT_VOLTAGE_RANGE["QTM"]
            self._name = f"QTM_{channel_no}"
        else:
            self._voltage_range = [-1.0, 1.0]

    @property
    def channel(self) -> int:
        return self._channel

    @property
    def sequencer(self) -> int:
        return self._sequencer

    @property
    def voltage_range(self) -> list[float]:
        return self._voltage_range

    @voltage_range.setter
    def voltage_range(self, new_range: list[float]) -> None:
        """A property setter for setting custom voltage ranges.

        Use with care! Can be used also to expand range beyond hardware limits.

        Parameters:
            new_range:  A new voltage range given by a 2-item list.

        Raises:
            ValueError: If the new range is not a 2-item list or range is not valid.
        """
        if len(new_range) != 2 or new_range[0] >= new_range[1]:
            raise ValueError(f"Invalid voltage range{new_range}")

        self._voltage_range = new_range

    def _check_path(self, path: int | None) -> int:
        """Small helper function to check optional 'path' input in function.

        Parameters:
            path:       Input 'path' number or None to use 'self.channel % 2'

        Raises:
            ValueError: If input was not 'None' and also not 0 or 1.

        Returns:
            path:       The checked 'path' number, now either 0 or 1.
        """
        if path is None:
            path = self.channel % 2
        elif path not in [0, 1]:
            raise ValueError(f"Path can only be 0 or 1, not {path}")
        return path

    def get_channel_config(self) -> dict:
        """Query the sequencer configuration connected to the channel for QCM and QRM.
        For QTM module there is separately a channel configuration.

        Returns:
            channel_cfg: A dictionary holding the configuration parameters for the sequencer or channel.
        """
        if self._module_func_refs["is_qtm_type"]():
            channel_cfg = self._module_func_refs["_get_io_channel_config"](self._channel)
        else:
            channel_cfg = self._module_func_refs["_get_sequencer_config"](self._sequencer)

        self._channel_cfg = channel_cfg
        return channel_cfg

    def set_channel_config(self, channel_cfg: dict) -> None:
        """Configure the sequencer connected to the channel for QCM and QRM.
        For the QTM there is a separate channel configuration.

        Parameters:
            channel_cfg: A dictionary holding the configuration parameters for the sequencer.
        """
        if self._module_func_refs["is_qtm_type"]():
            self._module_func_refs["_set_io_channel_config"](self._channel, channel_cfg)
        else:
            self._module_func_refs["_set_sequencer_config"](self._sequencer, channel_cfg)

        self._channel_cfg = channel_cfg

    def enable_sync(self):
        """Enable synchronization of the channel."""
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["seq_proc", "sync_en"], True)

    def disable_sync(self):
        """Disable synchronization of the channel."""
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["seq_proc", "sync_en"], False)

    def upload_sequence(self, sequence: str | dict[str, Any], enable_sync: bool = True):
        """Disable sync and upload sequence. (Re-)enable sync after upload.
        The sequence dictionary is of form:
        {'waveforms': {<wf_name>: {...}, ...}
         'weights': {...},
         'acquisitions': {<acq_name>: {...}, ...},
         'program': <program_string>
        }

        Parameters:
            sequence:    A sequence to upload to the sequencer.
            enable_sync: Extra parameter to choose if sync is enabled after uploading of sequencer. Default is True.
        """
        self.disable_sync()
        self._module_func_refs["_set_sequence"](self._sequencer, sequence)
        _logger.debug("Uploaded to sequencer %i new sequence %s", self._sequencer, sequence)
        if enable_sync:
            self.enable_sync()

    def arm_sequencer(self) -> None:
        """Arms the sequencer."""
        self._module_func_refs["arm_sequencer"](self.scpi_cmd_prefix)

    def start_sequencer(self) -> None:
        """Start the sequencer."""
        self._module_func_refs["start_sequencer"](self.scpi_cmd_prefix)

    def stop_sequencer(self) -> None:
        """Stop the sequencer."""
        self._module_func_refs["stop_sequencer"](self.scpi_cmd_prefix)

    def get_sequencer_state(self, timeout: int = 0) -> str:
        """Get channel's sequencer state. Possible states are:
        IDLE = "Sequencer waiting to be armed and started."
        ARMED = "Sequencer is armed and ready to start."
        RUNNING = "Sequencer is running."
        Q1_STOPPED = "Classical part of the sequencer has stopped; waiting for real-time part to stop."
        STOPPED = "Sequencer has completely stopped."

        Returns:
            state.name: The sequencer state name.
        """
        try:
            full_reply = self._module_func_refs["get_sequencer_status"](self._sequencer, timeout)
        except TimeoutError as terr:
            _logger.debug(
                f"Sequencer status with prefix {self.scpi_cmd_prefix} on channel {self._channel} returned with: {terr}"
            )
            raise RuntimeError(f"Error with {self.scpi_cmd_prefix} on channel {self._channel}") from terr

        _logger.debug(f"Sequencer status: {full_reply}")
        return full_reply.state.name

    def set_trigger_count_threshold_and_invert(self, trigger_index: int, threshold: int, invert: bool = False) -> None:
        """A function to set count threshold and comparison result inversion for a specific trigger address.

        Parameters:
            trigger_index: The trigger address number to set the values for.
            threshold:     Threshold for counter. Must be in range [0, 65535].
            invert:        If comparison result inversion is to be used. Can be True or False (default).

        Raises:
            ValueError:    If trigger index is not valid.
            ValueError:    If trigger threshold value for counter is not valid.
        """
        if trigger_index not in range(1, EXT_TRIGGERS_IN_CLUSTER + 1):
            raise ValueError(f"Trigger index {trigger_index} not in valid range [1-{EXT_TRIGGERS_IN_CLUSTER}]")

        if threshold < 0 or threshold > self.CHANNEL_LEVEL_RANGE:
            raise ValueError(f"Trigger count threshold {threshold} not in valid range [0-{self.CHANNEL_LEVEL_RANGE}]")

        list_index = trigger_index - 1  # The list index does start from 0
        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["seq_proc", "trg", list_index, "count_threshold"], threshold
        )
        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["seq_proc", "trg", list_index, "threshold_invert"], invert
        )


class QbloxAdcChannel(_QbloxChannel):
    """Class object for instantiating ADC channels on Qblox modules.

    Attributes:
        GAIN_RANGE:           Allowed input gain range. In dB.
    """

    GAIN_RANGE = (-6, 26)

    def __init__(
        self,
        module_func_refs: dict[str, Callable],
        slot: int,
        sequencer: int,
        channel_no: int,
        channel_sequencer_config: dict,
    ) -> None:
        """Initialise a Qblox ADC channel instance with respective sequencer configuration.

        Parameters:
            module_func_refs:         Function references callable at a module.
            slot:                     The slot number of the module
            sequencer:                The sequencer number assigned to channel.
            channel_no:               The channel number.
            channel_sequencer_config: Sequencer configuration for the channel.
        """
        super().__init__(module_func_refs, slot, sequencer, channel_no)
        self.set_channel_config(channel_sequencer_config)
        # Acquisition can have a specific name.
        self._acq_name = ""
        # Input channel path for data. Set as modulo 2 of 'channel_no' as default. Can be only 0 or 1.
        self._input_path = channel_no % 2

    @property
    def acq_name(self) -> str:
        """Make this as property for allowing to check for special name 'all'.

        Returns:
            self._acq_name: The current acquisition name.
        """
        return self._acq_name

    @acq_name.setter
    def acq_name(self, acquisition_name: str) -> None:
        """Setter for self._acq_name.

        Parameters:
            acquisition_name: A new acquisition name.
        """
        if acquisition_name == "all":
            _logger.warning("Cannot set acquisition name to 'all' as it has special meaning. Using empty string.")
            acquisition_name = ""

        self._acq_name = acquisition_name

    def set_demodulation_enable(self, enable: bool):
        """Set sequencer demodulation enable state for acquisition.

        Parameters:
            enable: True to enable demodulation for acquisition, False to disable.
        """
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "demod", "en"], enable)

    def get_demodulation_enable(self) -> bool:
        """Get sequencer demodulation for acquisition enable state.

        Returns:
            enable: True if demodulation for acquisition is enabled, False if disabled.
        """
        return bool(self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["acq", "demod", "en"]))

    def configure(
        self, threshold: float, auto_bin_increment=True, enable_demodulation: bool = False, gain: int = 0
    ) -> None:
        """Configure some things on the connected channel and sequencer.

        1. Selects the sequencer for acquiring data.
        2. Sets the input channel path as channel % 2.
        3. Set automatic bin index increment. 'False' also resets the bin index.
        4. Set threshold value.
        5. Sets the input channel demodulation enable state.
        6. Set gain on input channel.

        Parameters:
            threshold:           Voltage threshold for counting a trigger.
            auto_bin_increment:  Set automatic bin index increment as enabled (True, default) or disabled (False).
            enable_demodulation: True to enable demodulation of the input channel, False to disable (default).
            gain:                Amplification of voltage (signal) factor of `input_channel`.

        Raises:
            ValueError:          At invalid gain input value.
        """
        gain = int(gain)  # in case it was given as a float
        if gain < self.GAIN_RANGE[0] or gain > self.GAIN_RANGE[1]:
            raise ValueError(f"Gain {gain}dB out of valid range of {self.GAIN_RANGE}dB.")

        # Acquisition sequencer and input channel configuration
        self._module_func_refs["_set_acq_scope_config_val"]("sel_acq", self._sequencer)
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "ttl", "in"], self._input_path)
        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["acq", "ttl", "auto_bin_incr_en"], auto_bin_increment
        )
        # Threshold configuration
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "ttl", "threshold"], threshold)
        # Demodulation and gain
        self.set_demodulation_enable(enable_demodulation)
        self._module_func_refs[f"_set_in_amp_gain_{self._input_path}"](gain)

    def get_input_path_gains(self) -> tuple[float, float]:
        """Get input path gain values.

        Returns:
            gain0, gain1: Gain values for path0 (I) and path1 (Q).
        """
        gain0 = self._module_func_refs["_get_in_amp_gain_0"]()
        gain1 = self._module_func_refs["_get_in_amp_gain_1"]()

        return gain0, gain1

    def set_input_path_gains(self, gain0: float | None = None, gain1: float | None = None) -> None:
        """Set input gains on an ADC channel path.

        Parameters:
            gain0: Input gain for path 0 (I).
            gain1: Input gain for path 1 (Q).
        """
        gain = [gain0, gain1]
        if any(g < self.GAIN_RANGE[0] or g > self.GAIN_RANGE[1] for g in gain if g is not None):
            raise ValueError(f"Gain {gain}dB out of valid range of {self.GAIN_RANGE}dB.")

        for n, g in enumerate(gain):
            if g is not None:
                self._module_func_refs[f"_set_in_amp_gain_{n}"](g)

    def prepare_acquisition_sequence(self, acquisition_name: str = "") -> None:
        """Prepare an acquisition sequencer. It deletes any data with the given name.

        Parameters:
            acquisition_name: Optional acquisition name input. Set as 'all' to delete all acquisition data.
        """
        delete_all = True if acquisition_name.lower() == "all" else False
        self.acq_name = acquisition_name if acquisition_name.lower() != "all" else ""
        try:
            self._module_func_refs["delete_acquisition_data"](self._sequencer, acquisition_name, delete_all)
        except RuntimeError as rtexc:
            if "Unknown acquisition" in repr(rtexc):
                pass
            else:
                raise rtexc

    def get_acquisition_completed(self, timeout=1, timeout_poll_res=0.001) -> bool:
        """Get acquisition binning completion state of the indexed sequencer. The function will return either if
        binning was completed or if the given timeout period is elapsed.

        Parameters:
            timeout:          Wait timeout in minutes.
            timeout_poll_res: Polling resolution, i.o.w. wait time between status checks, in seconds.

        Returns:
            acquisition_status: True if binning was completed within timeout period, False if not.
        """
        return bool(self._module_func_refs["get_acquisition_status"](self._sequencer, timeout, timeout_poll_res))

    def run_acquisition_sequence(self, acquisition_name: str = "") -> bool:
        """Run a sequence of steps before obtaining and returning data.

        Steps taken:
            1.    Delete data from an acquisition, optionally specified by name.
            2.    Prepare the indexed sequencer to start by putting it in the armed state.
            3.    Start the indexed sequencer, thereby putting it in the running state.
            4.    Get acquisition binning completion state of the indexed sequencer. Wait until timeout for completion.

        Returns:
            acquisition_status: True if binning is completed, False if not.
        """
        self.prepare_acquisition_sequence(acquisition_name)
        self.arm_sequencer()
        self.start_sequencer()
        return self.get_acquisition_completed(timeout=1)

    def get_acquisitions(self, acquisition_name: str | None = None, timeout: int | None = 1) -> dict[str, dict]:
        """Get data from the QRM(-RF) module ADC channel.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            acquired_data: Data dictionary with acquisition name and data in dictionary entries.
        """
        acquisition_name = acquisition_name or self.acq_name
        _ = self._module_func_refs["get_acquisition_status"](
            self._sequencer, timeout=timeout, timeout_poll_res=1e-4, check_seq_state=False
        )
        self._module_func_refs["store_scope_acquisitions"](self._sequencer, acquisition_name)
        data = self._module_func_refs["get_acquisitions"](self._sequencer)
        acq_data = data[acquisition_name]

        return acq_data["acquisition"]

    def get_scope_data(self, acquisition_name: str | None = None, timeout: int | None = 1) -> dict[str, dict]:
        """Get specifically scope data.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            'data':         List of data values.
            'out_of_range': Boolean indicating if data was out-of-range.
            'avg_cnt':      Averaged count or list of counts from data.
        """
        data = self.get_acquisitions(acquisition_name, timeout)
        return data["scope"][f"path{self._channel % 2}"]

    def get_bin_data(
        self, acquisition_name: str | None = None, timeout: int | None = 1
    ) -> dict[str, dict | list | int | float]:
        """Get specifically bin data. Note that 'avg_count' has different meaning depending on type of acquisition.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            'integration': dictionary with data per path.
            'threshold':   A threshold or list of thresholds.
            'valid':       A list of valid indications per bin.
            'avg_cnt':     Averaged counts per bin or count of integrations above threshold.
        """
        data = self.get_acquisitions(acquisition_name, timeout)
        return data["bins"]

    def get_counts(self, acquisition_name: str | None = None, timeout: int | None = 1) -> dict | list | int | float:
        """Get the averaged count or pulse count. For 'binned' acquisition ('acquisition' command in a Q1ASM program),
        the return values are the counts of times the sequencer has written in the bin. For 'TTL' acquisition
        ('acquisition_ttl' command in a Q1ASM program), the return value is the count of integrations above
        threshold.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            avg_cnt: Averaged counts per bin or count of integrations above threshold.
        """
        return self.get_bin_data(acquisition_name, timeout)["avg_cnt"]

    def set_thresholded_acq_trigger_address(self, trigger_index: int, inverse: bool = False) -> None:
        """Set the trigger address to which the thresholded acquisition result is mapped to the trigger network.

        Parameters:
            trigger_index: Trigger address to which the thresholded acquisition result is mapped to in
                           the trigger network (T1 to T15).
            inverse:       If the acquisition result trigger should be inverted. Default is False.
        """
        if 0 > trigger_index > 15:
            raise ValueError(f"Trigger address value {trigger_index} is invalid. Should be within [1, 15].")

        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["acq", "th_acq_trg_map", "addr"], trigger_index
        )
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "th_acq_trg_map", "inv"], inverse)

    def enable_thresholded_acquisition_result(self):
        """Enables mapping of thresholded acquisition result to trigger network."""
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "th_acq_trg_map", "en"], True)

    def disable_thresholded_acquisition_result(self):
        """Disables mapping of thresholded acquisition result to trigger network."""
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "th_acq_trg_map", "en"], False)

    def set_thresholded_acq_marker_channel(self, marker_mask: int, inverse: bool = False) -> None:
        """Set the marker channel to which the thresholded acquisition result is mapped to in the module.

        Parameters:
            marker_mask: Marker channel mask to which the thresholded acquisition result is mapped to in
                         the markers of the module (M1 up to M4).
            inverse:     If the acquisition result marker should be inverted. Default is False.
        """
        if self._module_func_refs["is_rf_type"]() and 0 > marker_mask > 3:
            raise ValueError(
                f"Marker mask value {marker_mask} for module {self._name} is invalid. Should be within [0, 3]."
            )

        elif 0 > marker_mask > 15:
            raise ValueError(
                f"Marker mask value {marker_mask} for module {self._name} is invalid. Should be within [0, 15]."
            )

        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["acq", "th_acq_mrk_map", "addr"], marker_mask
        )
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "th_acq_mrk_map", "inv"], inverse)

    def enable_thresholded_acquisition_marker(self):
        """Enables mapping of thresholded acquisition result to a marker in module."""
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "th_acq_mrk_map", "en"], True)

    def disable_thresholded_acquisition_marker(self):
        """Disables mapping of thresholded acquisition result to a marker in module."""
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "th_acq_mrk_map", "en"], False)


class QbloxDacChannel(_QbloxChannel):
    """Class object for instantiating DAC channels on Qblox modules.

    Attributes:
        GAIN_RANGE:           Allowed digital gain range.
        RF_FREQUENCY_RANGE:   Allowed RF-frequency range for RF modules
        RF_POWER_RANGE:       Allowed RF module power range in dBm.
    """

    GAIN_RANGE = (-1.0, 1.0)
    RF_FREQUENCY_RANGE = [2e9, 18.5e9]  # Hz
    RF_POWER_RANGE = [-55, 5]  # dBm. Note, up to +10 dBm in QCM-RF II if freq < 8GHz!

    def __init__(
        self,
        module_func_refs: dict[str, Callable],
        slot: int,
        sequencer: int,
        channel_no: int,
        channel_sequencer_config,
    ) -> None:
        """Initialise a Qblox DAC channel instance with respective sequencer configuration.

        Parameters:
            module_func_refs:         The module function references.
            slot:                     The slot number of the module.
            sequencer:                The sequencer number assigned to channel.
            channel_no:               The channel number.
            channel_sequencer_config: Sequencer configuration for the channel.
        """
        super().__init__(module_func_refs, slot, sequencer, channel_no)
        self.set_channel_config(channel_sequencer_config)
        # Keep track of the latest set output voltage value
        self._set_output_voltage: float | None = None

    def configure(
        self,
        output_channel: int,
        gain: list[float | None] | None = None,
        nco_freq: float | None = None,
        enable_modulation: bool = False,
    ) -> None:
        """Configure the connected channel and sequencer.

        1. Connects the output channel.
        2. Enable/disable modulation.
        Optionally:
            3. Set NCO frequency.
            4. Set gain on output channel paths 0 and|or 1.

        Parameters:
            output_channel:     The channel number where the output is going to (a QRM, QRM-RF input channel).
            gain:               Optional amplification of voltage (signal) factor of gain path 0 (I) and 1 (Q).
            nco_freq:           Optional Numerically Controlled Oscillator (NCO) frequency (Hz).
            enable_modulation:  Boolean to enable (True) or disable (False, default) modulation on channel.

        Raises:
            ValueError:         At invalid gain input value.
        """
        if gain is not None:
            if any(g < self.GAIN_RANGE[0] or g > self.GAIN_RANGE[1] for g in gain if g is not None):
                raise ValueError(f"AWG gain {gain}dB out of valid range of {self.GAIN_RANGE}dB.")

        # Sequencer and output configuration
        self.connect_channel_to_output(True, output_channel)
        # Set modulation
        self.set_modulation_enable(enable_modulation)
        # Frequency
        if nco_freq is not None:
            self._module_func_refs["_set_sequencer_config_val"](
                self._sequencer, ["awg", "nco", "freq_hz"], float(nco_freq)
            )

        # Gain
        if gain is not None:
            for n, g in enumerate(gain):
                if g is not None:
                    self._module_func_refs["_set_sequencer_config_val"](
                        self._sequencer, ["awg", "gain_path", n], float(g)
                    )

    def is_set(self) -> bool:
        """Check if the output level has been set. We could compare a readout value with the latest
        set output value. Due to read value not being exact, we limit the check to 4 decimals.

        Returns:
            True:  If the output level is at requested level.
            False: If the output level was not as requested or has not been set yet.
        """
        if self._set_output_voltage is None:
            return False

        if self._is_rf_type:
            # TODO: is order important or could we simply just do first 0 then 1? RF module has only two channels
            output_voltage = self._module_func_refs[f"_get_dac_offset_{self._channel % 2}"]()

        else:
            output_voltage = self._module_func_refs[f"_get_dac_offset_{self._channel}"]()

        return round(output_voltage, 3) == round(self._set_output_voltage, 3)

    def set_gain(self, gain0: float | None = None, gain1: float | None = None) -> None:
        """Set static digital AWG path gains on a dac channel.

        Parameters:
            gain0: Input gain for path 0 (I).
            gain1: Input gain for path 1 (Q).
        """
        gain = [gain0, gain1]
        if any(g < self.GAIN_RANGE[0] or g > self.GAIN_RANGE[1] for g in gain if g is not None):
            raise ValueError(f"Gain {gain}dB out of valid range of {self.GAIN_RANGE}dB.")

        for n, g in enumerate(gain):
            if g is not None:
                self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "gain_path", n], float(g))

    def get_gain(self) -> tuple[float, float]:
        """Set static digital AWG path gains of the DAC channel. This has no effect on the DAC channel self, but possibly on a connected
        ADC input channel.

        Returns:
            gain0: Input gain of path 0 (I).
            gain1: Input gain of path 1 (Q).
        """
        gain0 = self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "gain_path", 0])
        gain1 = self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "gain_path", 1])

        return gain0, gain1

    def set_offset(self, voltage: float) -> None:
        """Set a new voltage offset on a DAC channel.

        Parameters:
            voltage: The new offset voltage for the DAC.
        """
        voltage = float(voltage)  # in case input was an int
        if not self.voltage_range[0] <= voltage <= self.voltage_range[1]:
            raise ValueError(f"Voltage {voltage}V not in valid range {self.voltage_range}V.")

        if self._is_rf_type:
            self._module_func_refs["_set_sequencer_config_val"](
                self._sequencer, ["awg", "offs_path", (self._channel + 1) % 2], voltage
            )
        else:
            self._module_func_refs["_set_sequencer_config_val"](
                self._sequencer, ["awg", "offs_path", self._channel % 2], voltage
            )

    def get_offset(self) -> float:
        """Get the voltage offset of a DAC channel.

        Returns:
            voltage: The offset voltage of the DAC.
        """
        if self._is_rf_type:
            voltage = self._module_func_refs["_get_sequencer_config_val"](
                self._sequencer, ["awg", "offs_path", (self._channel + 1) % 2]
            )
        else:
            voltage = self._module_func_refs["_get_sequencer_config_val"](
                self._sequencer, ["awg", "offs_path", self._channel % 2]
            )
        return voltage

    def set_output(self, voltage: float) -> None:
        """Set a new output voltage on a DAC channel.

        Parameters:
            voltage: The new output voltage for the DAC.
        """
        voltage = float(voltage)  # in case input was an int
        if not self.voltage_range[0] <= voltage <= self.voltage_range[1]:
            raise ValueError(f"Voltage {voltage}V not in valid range {self.voltage_range}V.")

        if self._is_rf_type:
            # TODO: is order important or could we simply just do first 0 then 1? RF module has only two channels
            self._module_func_refs[f"_set_dac_offset_{self._channel % 2}"](voltage)
            self._module_func_refs[f"_set_dac_offset_{(self._channel + 1) % 2}"](voltage)

        else:
            self._module_func_refs[f"_set_dac_offset_{self._channel}"](voltage)

        self._set_output_voltage = voltage

    def set_output_channel_level(self, dac_channel_level: int) -> None:
        """Set the output level of the DAC channel to requested level in bits.

        Parameters:
            dac_channel_level: DAC channel level in bits. Possible value range is [0 - 2^16-1].
        """
        if not 0 <= dac_channel_level <= self.CHANNEL_LEVEL_RANGE:
            raise ValueError(
                f"DAC channel level {dac_channel_level} not in valid range [0-{self.CHANNEL_LEVEL_RANGE}]"
            )

        # The level in bits has to be translated into Volts in the valid range
        voltage_pp = self.voltage_range[1] - self.voltage_range[0]
        voltage = dac_channel_level * voltage_pp / self.CHANNEL_LEVEL_RANGE + self.voltage_range[0]
        self.set_output(voltage)

    def get_channel_connected_to_output(self, output: int | None = None) -> str:
        """Get the output channel's output connection state.

        Parameters:
            output:  The output channel number.

        Returns:
            state:   The output channel's connection state string: "off", "I", "Q" or "IQ".
        """
        if output is None:
            output = self.channel

        return self._module_func_refs["_get_sequencer_connect_out"](self._sequencer, output)

    def connect_channel_to_output(self, enable: bool, output: int | None = None) -> None:
        """Enable or disable output channel connection to path.

        If the 'enable' option is set as False, output channel(s) will be disconnected from both paths.
        If 'enable' is True, and the control module is of 'RF' type, both channels (I, Q) will be connected to paths.
        If 'enable' is True, on non-'RF' type module:
          - Channel is "I" type (channels 0, 2):
            - Path 0 will be connected to channel 0 or 2, and path 1 will be disconnected from channel 1 or 3.
          - Channel is "Q" type (channels 1, 3):
            - Path 0 will be disconnected from channel 0 or 2, and path 1 will be connected to channel 1 or 3.

        Parameters:
            enable:  True for enabling connections, False for disabling.
            output:  The output channel number.
        """
        if output is None:
            output = self.channel

        if not enable:
            self._module_func_refs["_set_sequencer_connect_out"](self._sequencer, output, "off")
        else:
            if self._is_rf_type:
                # The last input as 'True' is interpreted the same as it being "IQ" state for RF-modules.
                self._module_func_refs["_set_sequencer_connect_out"](self._sequencer, output, enable)
            else:
                sequencer_channel_map = self._module_func_refs["_get_sequencer_channel_map"](self._sequencer)
                # Channels in first list item are "I" and in second item are "Q"
                state = "I" if output in sequencer_channel_map[0] else "Q"
                self._module_func_refs["_set_sequencer_connect_out"](self._sequencer, output, state)

    def get_sequencer_continuous_waveform_mode_enable(self, path: int | None = None) -> bool:
        """Get current continuous waveform mode state of a given AWG path.

        Parameters:
            path:       Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Returns:
            state:      The AWG path state.
        """
        path = self._check_path(path)

        return bool(
            self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "cont_mode", "en_path", path])
        )

    def set_sequencer_continuous_waveform_mode_enable(self, state: bool, path: int | None = None) -> None:
        """Set current continuous waveform mode state for a given AWG path.

        Parameters:
            state:      True for enabling the continuous waveform for AWG path, False for disabling it.
            path:       Optional path number to set the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.
        """
        path = self._check_path(path)

        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["awg", "cont_mode", "en_path", path], state
        )

    def get_sequencer_continuous_waveform_index(self, path: int | None = None) -> int:
        """Get current continuous waveform index of a given AWG path.

        Parameters:
            path:       Optional path number to get the index for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Returns:
            index:      The AWG path's waveform index.
        """
        path = self._check_path(path)

        return int(
            self._module_func_refs["_get_sequencer_config_val"](
                self._sequencer, ["awg", "cont_mode", "wave_idx_path", path]
            )
        )

    def set_sequencer_continuous_waveform_index(self, index: int, path: int | None = None) -> None:
        """Set current continuous waveform index for a given AWG path.

        Parameters:
            index:      Continuous waveform index number.
            path:       Optional path number to set the index for. Must be 0 or 1. Otherwise, self.channel % 2 is used.
        """
        path = self._check_path(path)

        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["awg", "cont_mode", "wave_idx_path", path], index
        )

    def set_nco_phase_offset(self, phase_offset: float) -> None:
        """Sets NCO phase offset to given value. The resolution is 3.6e-7 degrees.

        Parameters:
            phase_offset: A degree in range [0, 360].

        Raises:
            ValueError:   If input was not in correct range.
        """
        if not 0 <= phase_offset <= 360:
            raise ValueError("Phase offset must be a value in range [0, 360](degrees).")

        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "nco", "po"], float(phase_offset))

    def get_nco_phase_offset(self) -> float:
        """Gets NCO phase offset value.

        Returns:
            phase_offset: A degree in range [0, 360].
        """
        return self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "nco", "po"])

    def set_nco_propagation_delay_compensation(self, state: bool, delay: int | None = None) -> None:
        """Enables and sets NCO propagation delay compensation to given value or disables it. For further explanation
        and an example use, see
        https://docs.qblox.com/en/main/tutorials/q1asm_tutorials/QRM/nco_control.html#NCO-input-delay-compensation
        https://docs.qblox.com/en/main/applications/quantify/transmon/tuning_transmon_coupled_pair.html#Activate-NCO-delay-compensation

        Parameters:
            state: True for enabling, False for disabling.
            delay: If enabling, the delay value to be used, within range -50 to 109 ns.

        Raises:
            ValueError: If delay input was not an integer or not in correct range.
        """
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "nco", "delay_comp_en"], state)
        if state and delay is not None:
            # Check and set also delay value
            if not isinstance(delay, int) or not -50 <= delay <= 109:
                raise ValueError("Delay value must be an integer in range [-50, 109](ns).")

            self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "nco", "delay_comp"], delay)

    def get_nco_propagation_delay_compensation(self) -> tuple[bool, int]:
        """Gets NCO propagation delay compensation value and enabled state.

        Returns:
            state: True if enabled, False if disabled.
            delay: The delay value set, within range -50 to 50 ns.
        """
        state = self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "nco", "delay_comp_en"])
        delay = self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "nco", "delay_comp"])

        return state, delay

    def set_dc_mixer_offset_i(self, offset_i: float) -> None:
        """Set AWG sequencer I offset, for path 0.

        Parameters:
            offset_i: The I offset in Volts.
        """
        self._module_func_refs["_set_out_amp_offset_0"](offset_i)

    def get_dc_mixer_offset_i(self) -> float:
        """Get AWG sequencer I offset, of path 0.

        Returns:
            offset_i: The I offset in Volts.
        """
        return self._module_func_refs["_get_out_amp_offset_0"]()

    def set_dc_mixer_offset_q(self, offset_q: float) -> None:
        """Set AWG sequencer Q offset, for path 1.

        Parameters:
            offset_q: The Q offset in Volts.
        """
        self._module_func_refs["_set_out_amp_offset_1"](offset_q)

    def get_dc_mixer_offset_q(self) -> float:
        """Get AWG sequencer Q offset, of path 1.

        Returns:
            offset_q: The Q offset in Volts.
        """
        return self._module_func_refs["_get_out_amp_offset_1"]()

    def set_dc_mixer_correction_gain_ratio(self, mixer_amp_ratio: float) -> None:
        """Set gain imbalance correction ratio for AWG path amplitudes. The ratio is Q:I (i.e. path1:path0).

        Parameters:
            mixer_amp_ratio: Correction ratio Q:I for gains. Allowed range is [0.5, 2.0].

        Raises:
            ValueError:      If gain correction ratio is not within allowed range.
        """
        if not 0.5 <= mixer_amp_ratio <= 2.0:
            raise ValueError("Mixer gain correction ratio must be in range [0.5, 2.0]")

        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer, ["awg", "mixer", "corr_gain_ratio"], mixer_amp_ratio
        )

    def get_dc_mixer_correction_gain_ratio(self) -> float:
        """Get gain imbalance correction ratio of AWG path amplitudes.

        Returns:
            mixer_amp_ratio: Correction ratio Q:I of respective gains.
        """
        return self._module_func_refs["_get_sequencer_config_val"](
            self._sequencer, ["awg", "mixer", "corr_gain_ratio"]
        )

    def set_dc_mixer_phase_offset(self, mixer_phase_error_deg: float) -> None:
        """Set phase imbalance correction degree for AWG.

        Parameters:
            mixer_phase_error_deg: The phase correction in degrees, within range [-45, 45].
        """
        self._module_func_refs["_set_sequencer_config_val"](
            self._sequencer,
            ["awg", "mixer", "corr_phase_offset_degree"],
            mixer_phase_error_deg,
        )

    def get_dc_mixer_phase_offset(self) -> float:
        """Get phase imbalance correction degree of AWG.

        Returns:
            mixer_phase_error_deg: The phase correction in degrees.
        """
        return self._module_func_refs["_get_sequencer_config_val"](
            self._sequencer, ["awg", "mixer", "corr_phase_offset_degree"]
        )

    def set_modulation_enable(self, enable: bool) -> None:
        """Set sequencer modulation enable state for AWG.

        Parameters:
            enable: True to enable modulation for AWG, False to disable.
        """
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "mixer", "en"], enable)

    def get_modulation_enable(self) -> bool:
        """Get sequencer modulation for AWG enable state.

        Returns:
            enable: True if modulation for AWG is enabled, False if disabled.
        """
        if self._is_qcm_type or self._is_qrm_type:
            return bool(self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "mixer", "en"]))

        return False

    def calibrate_lo_leakage(self, path: int | None = None):
        """Calls for the calibration of Local Oscillator leakage for the output.

        Parameters:
            path:         Optional path number to calibrate the LO leakage for. Must be 0 or 1.
                          Otherwise, self.channel % 2 is used.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot calibrate LO leakage for non-RF type modules!")

        path = self._check_path(path)
        self._module_func_refs["_run_mixer_lo_calib"](path)

    def calibrate_sidebands(self):
        """Calls for the calibration of the sidebands for the sequencer.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot calibrate sidebands for non-RF type modules!")

        self._module_func_refs["_run_mixer_sidebands_calib"](self._sequencer)

    def set_demodulation_enable(self, enable: bool) -> None:
        """Set sequencer demodulation enable state for acquisition. Works only on modules with sequencers that
        have both acquisition and AWG parameters.

        Parameters:
            enable: True to enable demodulation for acquisition, False to disable.
        """
        # TODO: These are implemented in the ADC channel as well. Is this double implementation?
        if "acq" in self._channel_cfg.keys():
            self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["acq", "demod", "en"], enable)

    def get_demodulation_enable(self) -> bool | None:
        """Get sequencer demodulation for acquisition enable state. Works only on modules with sequencers that
        have both acquisition and AWG parameters.

        Returns:
            enable: True if demodulation for acquisition is enabled, False if disabled.
        """
        if "acq" in self._channel_cfg.keys():
            return bool(self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["acq", "demod", "en"]))

        return None

    def configure_rf(
        self,
        mixer_phase_error: float | None = None,
        mixer_offset_i: float | None = None,
        mixer_offset_q: float | None = None,
        mixer_amp_ratio: float | None = None,
        enable_modulation: bool = True,
    ) -> None:
        """Configure the connected RF module channel and sequencer.

        Does the following steps:
        1. Sets the mixer phase error - a.k.a mw_source_iq_quadrature_offset.
        2. Sets DC mixer I and Q offsets - a.k.a mw_source_leakage_i/q; convert % to V.
        3. Set mixer amplification ratio - a.k.a. mw_source_iq_gain_imbalance; convert dB_20 -> ratio.
        And always:
        4. Enable modulation. This is the default behaviour, but can also optionally be disabled.

        Parameters:
            mixer_phase_error:    Mixer phase error in degrees.
            mixer_offset_i:       DC mixer I phase offset in Volts.
            mixer_offset_q:       DC mixer Q phase offset in Volts.
            mixer_amp_ratio:      Mixer I/Q amplification ratio.
            enable_modulation:    Boolean to enable (True, default) or disable (False) modulation on channel.

        Raises:
            ValueError:           At invalid gain input value.
        """
        if mixer_phase_error is not None:
            self.set_dc_mixer_phase_offset(mixer_phase_error)
        if mixer_offset_i is not None:
            self.set_dc_mixer_offset_i(mixer_offset_i)
        if mixer_offset_q is not None:
            self.set_dc_mixer_offset_q(mixer_offset_q)
        if mixer_amp_ratio is not None:
            self.set_dc_mixer_correction_gain_ratio(mixer_amp_ratio)

        self.set_modulation_enable(enable_modulation)

    def get_rf_configuration(self) -> tuple[float, float, float, float, bool]:
        """Get the connected RF module channel's RF configuration.

        Returns:
            mixer_phase_error:    Mixer phase error in degrees.
            mixer_offset_i:       DC mixer I phase offset in Volts.
            mixer_offset_q:       DC mixer Q phase offset in Volts.
            mixer_amp_ratio:      Mixer I/Q amplification ratio.
            enable_modulation:    Boolean to indicate modulation on channel is enabled.
        """
        mixer_phase_error = self.get_dc_mixer_phase_offset()
        mixer_offset_i = self.get_dc_mixer_offset_i()
        mixer_offset_q = self.get_dc_mixer_offset_q()
        mixer_amp_ratio = self.get_dc_mixer_correction_gain_ratio()
        modulation_enabled = self.get_modulation_enable()

        return mixer_phase_error, mixer_offset_i, mixer_offset_q, mixer_amp_ratio, modulation_enabled

    def set_lo_enable_state(self, enable: bool, path: int | None = None) -> None:
        """Set channel path's local oscillator state.

        Parameters:
            enable:     True if the LO should be enabled, False if disabled.
            path:       Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot enable LO for non-RF type modules!")

        if self._is_qcm_type:
            path = self._check_path(path)
            self._module_func_refs[f"_set_lo_enable_{path}"](enable)

        elif self._is_qrm_type:
            self._module_func_refs["_set_lo_enable_1"](enable)

    def get_lo_enable_state(self, path: int | None = None) -> bool:
        """Get channel path's local oscillator state.

        Parameters:
            path:       Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Returns:
            enable:     True if the LO is enabled, False if disabled.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot get LO enable state for non-RF type modules!")

        path = self._check_path(path)

        return bool(self._module_func_refs[f"_get_lo_enable_{path}"]())

    def set_lo_frequency(self, frequency: float, path: int | None = None) -> None:
        """Set channel path's local oscillator frequency.

        Parameters:
            frequency:  The frequency to be set. In Hz.
            path:       Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Raises:
            RuntimeError: This command is meant only for RF modules.
            ValueError:   By out-of-range frequency value.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot set LO frequency for non-RF type modules!")

        if not self.RF_FREQUENCY_RANGE[0] <= frequency <= self.RF_FREQUENCY_RANGE[1]:
            raise ValueError(f"Frequency ({frequency}) must be in correct range {self.RF_FREQUENCY_RANGE}!")

        path = self._check_path(path)

        # TODO: Check if this is valid for both QCM-RF and QRM-RF. Namely, in QCodes the following check is made:
        # if parent.is_qrm_type:
        #     parent.add_parameter(
        #         "out0_in0_lo_freq",
        #         ...
        #         set_cmd=parent._set_lo_freq_1,
        #         get_cmd=parent._get_lo_freq_1,
        #     )
        # else:
        #     parent.add_parameter(
        #         "out0_lo_freq",
        #         ...
        #         set_cmd=parent._set_lo_freq_0,
        #         get_cmd=parent._get_lo_freq_0,
        #     )
        self._module_func_refs[f"_set_lo_freq_{path}"](int(frequency))

    def get_lo_frequency(self, path: int | None = None) -> float:
        """Get channel path's local oscillator frequency.

        Returns:
            frequency:    The current LO frequency. In Hz.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot get LO frequency for non-RF type modules!")

        path = self._check_path(path)

        return self._module_func_refs[f"_get_lo_freq_{path}"]()

    def set_lo_power(self, power: int, path: int | None = None) -> None:
        """Set channel path's local oscillator power. ATTENTION: The LO power only has 8 setpoints,
        and for more control the output attenuation, which has a resolution of 2 dBm, should be used.
        Also, this feature can possibly be changed without prior warning.

        Parameters:
            power:        The power to be set. In dBm.
            path:         Optional path number to set the power for. Must be 0 or 1. Default is self.channel % 2.

        Raises:
            RuntimeError: This command is meant only for RF modules.
            ValueError:   By out-of-range power value.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot set LO power for non-RF type modules!")

        if not self.RF_POWER_RANGE[0] <= power <= self.RF_POWER_RANGE[1]:
            raise ValueError(f"Power must be in correct range {self.RF_POWER_RANGE}!")

        path = self._check_path(path)

        # TODO: Check if this is valid for both QCM-RF and QRM-RF. Do we need to do for both I & Q?
        self._module_func_refs[f"_set_lo_pwr_{path}"](power)

    def get_lo_power(self, path: int | None = None) -> int:
        """Get channel path's local oscillator power.
        ATTENTION: This feature can possibly be changed without prior warning.

        Parameters:
            path:         Optional path number to get the state for. Must be 0 or 1. Default is self.channel % 2.

        Returns:
            power:        The current LO power. In dBm.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot set LO power for non-RF type modules!")

        path = self._check_path(path)

        # TODO: Check if this is valid for both QCM-RF and QRM-RF.
        return self._module_func_refs[f"_get_lo_pwr_{path}"]()

    def set_lo_attenuation(self, attenuation: int, path: int | None = None) -> None:
        """Set channel path's local oscillator output attenuation. The resolution is about 2dB, which
        from testing on hardware shows that values 0-1 do not change the power, values 2-3 _reduce_ the
        power by ~2dB, 4-5 by ~4dB etc. Note that this is a relative scale and also the exact reduction
        depends on frequency.

        Parameters:
            attenuation: The attenuation to be set. In dB.
            path:        Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Raises:
            RuntimeError: This command is meant only for RF modules.
            ValueError:   By out-of-range attenuation value.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot set LO attenuation for non-RF type modules!")

        max_att = self.get_max_lo_attenuation()
        if not 0 <= attenuation <= max_att:
            raise ValueError(f"Attenuation {attenuation} must be in correct range {[0, max_att]}!")

        path = self._check_path(path)

        # TODO: Check if this is valid for both QCM-RF and QRM-RF (II).
        self._module_func_refs[f"_set_out_att_{path}"](attenuation)

    def get_lo_attenuation(self, path: int | None = None) -> int:
        """Get channel path's local oscillator attenuation.

        Parameters:
            path:       Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Returns:
            attenuation:  The current LO attenuation. In dB.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot set LO attenuation for non-RF type modules!")

        path = self._check_path(path)

        # TODO: Check if this is valid for both QCM-RF and QRM-RF (II).
        return self._module_func_refs[f"_get_out_att_{path}"]()

    def get_max_lo_attenuation(self, path: int | None = None) -> int:
        """Get channel path's maximum local oscillator attenuation.

        Parameters:
            path: Optional path number to get the state for. Must be 0 or 1. Otherwise, self.channel % 2 is used.

        Returns:
            attenuation: The maximum LO attenuation. In dB.

        Raises:
            RuntimeError: This command is meant only for RF modules.
        """
        if not self._is_rf_type:
            raise RuntimeError("Cannot set LO attenuation for non-RF type modules!")

        path = self._check_path(path)

        # TODO: Check if this is valid for both QCM-RF and QRM-RF (II).
        return self._module_func_refs[f"_get_max_out_att_{path}"]()

    def _rf_channel_output(self, level: bool):
        """A function dedicated for setting RF-module outputs on and off using markers, with using an override.
        The levels are always set for all channels using a 4-bit setter value. Each bit represents a marker or an
        output channel on a module.
        For QCM-RF the bit order is M1M2O2O1 and for QRM-RF module the order is M2M1O1I1.

        Note that the changes might not take an effect without running a sequence.

        Parameters:
            level: True sets the channel output ON, False sets it OFF.
        """
        # First enable the override for the marker.
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "marker_ovr", "en"], level)
        # We need to check first the current 4-bit value int to see how all the channels are currently set
        current_int = self._module_func_refs["_get_sequencer_config_val"](
            self._sequencer, ["awg", "marker_ovr", "val"]
        )
        if self._is_qrm_type:
            channel_bit = 1
        else:
            channel_bit = self.channel

        # We want to set only the current channel bit, so we do
        if level:
            ovr_value = current_int | (1 << channel_bit)
        else:
            ovr_value = current_int & ~(1 << channel_bit)

        # Then override value with new value.
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "marker_ovr", "val"], ovr_value)
        # Disable the override
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "marker_ovr", "en"], False)

    def enable_rf_channel_output(self) -> None:
        """Enable the output channel of an RF-module DAC channel instance."""
        self.set_lo_enable_state(True)

    def disable_rf_channel_output(self) -> None:
        """Enable the output channel of an RF-module DAC channel instance."""
        self.set_lo_enable_state(False)


class QbloxIOChannel(_QbloxChannel):
    """Class object for instantiating IO channels on Qblox QTM module."""

    def __init__(
        self,
        module_func_refs: dict[str, Callable],
        slot: int,
        sequencer: int,
        channel_no: int,
        channel_config: dict,
        sequencer_config: dict[str, Any],
    ) -> None:
        """Initialise a Qblox IO channel instance with respective channel and sequencer configurations.
        Note that for QTM these are two separate entities, contrary to other channels.

        Parameters:
            module_func_refs:         Function references callable at a module.
            slot:                     The slot number of the module
            sequencer:                The number of sequencers in the module. NOTE: unlike ADC/DAC channels!
            channel_no:               The channel number.
            channel_config:           Channel configuration for the channel.
            sequencer_config:         Sequencer configuration for the channel.
        """
        self._sequencer_cfg: dict[str, Any] = dict()
        self._sequencers = sequencer
        super().__init__(module_func_refs, slot, channel_no, channel_no)
        if not self._is_qtm_type:
            raise RuntimeError("The '_QbloxIOChannel' class is for QTM modules only!")

        self.set_channel_config(channel_config)
        self.set_sequencer_config(sequencer_config)
        # Acquisition can have a specific name.
        self._acq_name = ""

    @property
    def acq_name(self) -> str:
        """Make this as property for allowing to check for special name 'all'.

        Returns:
            self._name: The current acquisition name.
        """
        return self._acq_name

    @acq_name.setter
    def acq_name(self, acquisition_name: str) -> None:
        """Setter for self._name.

        Parameters:
            acquisition_name: A new acquisition name.
        """
        if acquisition_name == "all":
            _logger.warning("Cannot set acquisition name to 'all' as it has special meaning. Using empty string.")
            acquisition_name = ""

        self._acq_name = acquisition_name

    @property
    def sequencer_cfg(self) -> dict[str, Any]:
        """Property holding the latest set/get sequencer configuration.

        Raises:
            AssertionError: If the class sequencer configuration dictionary is empty.

        Returns:
            self._sequencer_cfg: The latest sequencer dictionary.
        """
        assert self._sequencer_cfg, "Error: No sequencer configuration has been set!"
        return self._sequencer_cfg

    @sequencer_cfg.setter
    def sequencer_cfg(self, sequencer_cfg: dict[str, Any]) -> None:
        """Setter for property holding the latest set/get sequencer configuration.

        Raises:
            AssertionError: If the sequencer configuration dictionary to be set is empty.

        Parameters:
            sequencer_cfg: New sequencer dictionary to set.
        """
        assert sequencer_cfg, "Error: Trying to set an empty sequencer configuration!"
        self._sequencer_cfg = sequencer_cfg

    def get_sequencer_config(self) -> dict[str, Any]:
        """Query the sequencer configuration connected to the channel.

        Returns:
            sequencer_cfg: A dictionary holding the configuration parameters for the sequencer.
        """
        sequencer_cfg = self._module_func_refs["_get_sequencer_config"](self._sequencer)

        self.sequencer_cfg = sequencer_cfg
        return sequencer_cfg

    def set_sequencer_config(self, sequencer_cfg: dict[str, Any]) -> None:
        """Configure the sequencer connected to the channel.

        Parameters:
            sequencer_cfg: A dictionary holding the configuration parameters for the sequencer.
        """
        self._module_func_refs["_set_sequencer_config"](self._sequencer, sequencer_cfg)
        self.sequencer_cfg = sequencer_cfg

    def set_io_channel_out_mode(self, mode: str) -> None:
        """Sets 'out mode' for an IO channel. Can be used to disable the output channel, or to use it like an analog
        marker channel. By setting it "low", the channel 'outputs' low-impedance 0V. By setting it "high", it outputs
        low-impedance 3.3V. The option "sequencer" means that the value can be set in a sequencer program using
        command 'set_digital <enable>,<mask>,<fine_delay>', where mask = 1.

        Parameters:
            mode:       The new out mode. Must be one of ["disabled", "low", "high", "sequencer"].

        Raises:
            ValueError: If an invalid new out mode was given.
        """
        valid_out_modes = ["disabled", "low", "high", "sequencer"]
        mode = mode.lower()
        if mode not in valid_out_modes:
            raise ValueError(f"Out mode {mode} is not valid. Must be one of {valid_out_modes}.")

        self._module_func_refs["_set_io_channel_config_val"](self._channel, "out_mode", mode)

    def set_io_channel_threshold_voltage(self, voltage: float) -> None:
        """Sets threshold voltage for an IO channel.

        Parameters:
            voltage:    The new voltage. Must be in range of the QTM input channel [0, 5]V.

        Raises:
            ValueError: If the voltage is not in valid range.
        """
        if not self.voltage_range[0] <= voltage <= self.voltage_range[1]:
            raise ValueError(f"Threshold voltage {voltage}V is not valid. Must be in range {self.voltage_range}V.")

        self._module_func_refs["_set_io_channel_config_val"](self._channel, "in_threshold_primary", voltage)

    def set_binned_acquisition_threshold_source(self, source: int) -> None:
        """Set the source for recording data with 'acquire_timetags' command in Q1ASM program.

        Parameters:
            source: Data source for 'acquire_timetags'. Either 0 or 1 for 'thresh0' or 'thresh1'.
                    * thresh0: The value is taken directly from the comparison with the first (i.e. 'low') counter
                               threshold associated with the primary analog threshold.
                    * thresh1: The value is taken directly from the comparison with the second (i.e. 'high') counter
                               threshold associated with the primary analog threshold.
        """
        if source not in [0, 1]:
            _logger.debug(f"Used threshold source {source} for set_binned_acquisition_threshold! Must be 0 or 1.")
            raise ValueError("The possible binned acquisition threshold sources are 0 or 1.")

        threshold_src = f"thresh{source}"
        self._module_func_refs["_set_io_channel_config_val"](
            self._channel, "binned_acq_threshold_source", threshold_src
        )

    def configure(
        self, threshold: float, auto_bin_increment=True, enable_demodulation: bool = False, gain: int = 0
    ) -> None:
        """Configure to use primary channel acquisition threshold only. This is added for compatibility with
        `_QbloxAdcChannel.configure` call to behave similarly. For exact behaviour see the docstring of
        `configure_primary_threshold_only` function.

        Parameters:
            threshold:           Voltage threshold for counting a trigger.
            auto_bin_increment:  Ignored for QTM.
            enable_demodulation: Ignored for QTM.
            gain:                Ignored for QTM.

        Raises:
            ValueError:          At invalid gain input value.
        """
        self.configure_primary_threshold_only(threshold)

    def configure_primary_threshold_only(
        self, threshold: float, enable_trigger=True, trigger_address: int = 1
    ) -> None:
        """Configure to use primary channel acquisition threshold only. This is added for compatibility with
        _QbloxAdcChannel.configure call to behave similarly.

        1. Disable thresholded trigger acquisition by counts.
        2. Disable output mode.
        3. Set primary threshold voltage used for digitization of the input signal for the given channel.
        4. Configure to use binned acquisition with timetagging. The relation is set to the first timetag, in the
           first data source, and to always record the data even if no event occurred.
        5. Enable or disable the given trigger address.

        Parameters:
            threshold:           Primary voltage threshold for counting a trigger.
            enable_trigger:      Enable (True, default) or disable (False) trigger.
            trigger_address:     Address of the trigger.

        Raises:
            ValueError:          At invalid trigger address input value.
        """
        if trigger_address not in range(1, EXT_TRIGGERS_IN_CLUSTER):
            raise ValueError(f"Invalid trigger address {trigger_address}!")

        self.configure_thresholded_acquisition(False)  # Don't use thresholding with the simple configuration
        self.set_io_channel_out_mode("disabled")
        self.configure_binned_acquisition(threshold, "first", "start", "record_0")
        self.configure_input_trigger(trigger_address, enable=enable_trigger)

    def configure_scope_acquisition(self, mode: str, edge: str = "any", trigger_mode: str = "sequencer") -> None:
        """Configure scope mode acquisition. Set what type of data is traced when the scope/trace unit for this
        channel is triggered, what kind of trigger edge is applied for triggering and from which source the channel
        is triggered.

        Parameters:
            mode:         Set the tracing to "scope", "timetags" or "timetags-windowed" data type.
            edge:         Set the trigger edge to "any" (default), "low", "high", "rising" or "falling".
            trigger_mode: Set the source of the trigger signal. Either "sequencer" (default) or "external".

        Raises:
            ValueError:   If invalid input options are given.
        """
        if mode not in ["scope", "timetags", "timetags-windowed"]:
            raise ValueError("Valid scope acquisition modes are 'scope', 'timetags' or 'timetags-windowed'")

        if edge not in ["any", "low", "high", "rising", "falling"]:
            raise ValueError("Valid scope acquisition modes are 'any', 'low', 'high', 'rising' or 'falling'")

        if trigger_mode not in ["sequencer", "external"]:
            raise ValueError("Valid scope acquisition modes are 'sequencer' or 'external'")

        self._module_func_refs["_set_io_channel_config_val"](self._channel, "scope_mode", mode)
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "scope_trigger_level", edge)
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "scope_trigger_mode", trigger_mode)

    def configure_binned_acquisition(
        self, threshold: float, data_source: str, reference: str, behaviour: str, source: None | int = None
    ) -> None:
        """Configure the timetag binned acquisition. In this function the timetag data source for acquisitions
        is defined, to which timetag the data is recorded in relation to, and the binning logic behaviour defined
        in case of no valid time delta available.

        Parameters:
            threshold:   Primary voltage threshold for counting a trigger.
            data_source: Timetag data source instruction. One of ["first", "second", "last"] detection.
            reference:   Time reference point for timetags recorded. Like "start", "end", "first" or "sequencer".
                         "sequencer" option means that the time reference will be configured through Q1ASM instruction
                         'set_time_ref'.
            behaviour:   Averaging and binning logic behaviour if no valid time delta is available.
                         One of ["error", "record_0", "discard"].
            source:      0 for threshold 0 or 1 for threshold 1. Default is `None` which does not try to set a new source.

        Raises:
            ValueError: One of the input values was not valid.
        """
        if source is not None:
            self.set_binned_acquisition_threshold_source(source)

        # First check input values
        valid_sources = ["first", "second", "last"]
        valid_references = ["start", "end", "first", "sequencer"] + [f"first{x}" for x in range(self._sequencers)]
        valid_behaviour = ["error", "record_0", "discard"]
        if data_source not in valid_sources or reference not in valid_references or behaviour not in valid_behaviour:
            raise ValueError("Invalid input parameter[s] for configuring binned acquisition for an IO channel.")

        self.set_io_channel_threshold_voltage(threshold)
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "binned_acq_time_ref", reference)
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "binned_acq_time_source", data_source)
        self._module_func_refs["_set_io_channel_config_val"](
            self._channel, "binned_acq_on_invalid_time_delta", behaviour
        )

    def configure_thresholded_acquisition(
        self, state: bool, low: int | None = None, mid: int | None = None, high: int | None = None
    ) -> None:
        """Maps the thresholded acquisition result to the trigger network for feedback purposes and sets the trigger's
        address (1...15). Can be set also as 0 for unused. The mapped thresholded result are based on the
        primary acquisition threshold source, which has been set with "threshold_0" or "threshold_1" levels
        (aka "thresh0" and "thresh1").

        Note that the result is sent only to the trigger network and not saved in acquisition data.

        Parameters:
            state:      True for enabling trigger, False for disabling.
            low:        Use for setting the 'low' trigger address for cases where acquire_timetags counts < threshold_0.
            mid:        Use for setting the 'mid' trigger address for cases where acquire_timetags
                        threshold_0 <= counts < threshold_1.
            high:       Use for setting the 'high' trigger address for cases where counts >= threshold_1.

        Raises:
            ValueError: If address level is not in range [0, 15].
        """
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "thresholded_acq_trigger_en", state)
        if state:
            valid_address_range = range(0, EXT_TRIGGERS_IN_CLUSTER + 1)
            for level, address in zip(["low", "mid", "high"], [low, mid, high]):
                if address is not None and address in valid_address_range:
                    self._module_func_refs["_set_io_channel_config_val"](
                        self._channel, f"thresholded_acq_trigger_address_{level}", address
                    )

                elif address is not None and address not in valid_address_range:
                    raise ValueError(f"Invalid address {address} for trigger level {level}!")

    def configure_input_trigger(self, address: int, enable: bool = True, mode: str = "rising") -> None:
        """Configure a trigger on the trigger network that uses the primary input threshold value.
        Sends triggers within any part of sequencer program, thus not confined within acquire_xxx commands.

        Parameters:
            address: The trigger address number in range [1, 15].
            enable:  If sending triggers to the trigger network automatically should be
                     enabled (True, default) or disabled (False).
            mode:    The trigger edge mode. Options are "rising" (default), "falling", "sampled-high", "sampled-low".
        """
        if 0 > address > 15:
            raise ValueError("Trigger address must be in range [1, 15].")

        if mode not in ["rising", "falling", "sampled-high", "sampled-low"]:
            raise ValueError(f"trigger edge mode {mode} is not valid.")

        self._module_func_refs["_set_io_channel_config_val"](self._channel, "in_trigger_address", address)
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "in_trigger_en", enable)
        self._module_func_refs["_set_io_channel_config_val"](self._channel, "in_trigger_mode", mode)

    def prepare_acquisition_sequence(self, acquisition_name: str = "") -> None:
        """Prepare an acquisition sequencer. It deletes any data with the given name.

        Parameters:
            acquisition_name: Optional acquisition name input. Set as 'all' to delete all acquisition data.
        """
        delete_all = True if acquisition_name.lower() == "all" else False
        self.acq_name = acquisition_name if acquisition_name.lower() != "all" else ""
        try:
            self._module_func_refs["delete_acquisition_data"](self._sequencer, acquisition_name, delete_all)
        except RuntimeError as rtexc:
            if "Unknown acquisition" in repr(rtexc):
                pass
            else:
                raise rtexc

    def get_acquisition_completed(self, timeout=1, timeout_poll_res=0.001) -> bool:
        """Get acquisition binning completion state of the indexed sequencer. The function will return either if
        binning was completed or if the given timeout period is elapsed.

        Parameters:
            timeout:            Wait timeout in minutes.
            timeout_poll_res:   Polling resolution, i.o.w. wait time between status checks, in seconds.

        Returns:
            acquisition_status: True if binning is completed within timeout, False if not.
        """
        return bool(self._module_func_refs["get_acquisition_status"](self._channel, timeout, timeout_poll_res))

    def get_acquisitions(self, acquisition_name: str | None = None, timeout: int | None = 1) -> dict[str, dict]:
        """Get data from the QTM module IO channel.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            acquired_data:    Data dictionary with acquisition name and data in dictionary entries.
        """
        acquisition_name = acquisition_name or self.acq_name
        _ = self._module_func_refs["get_acquisition_status"](
            self._channel, timeout=timeout, timeout_poll_res=1e-4, check_seq_state=False
        )
        _logger.debug(f"{acquisition_name}: {_}")
        self._module_func_refs["store_scope_acquisition"](self._channel, acquisition_name)
        data = self._module_func_refs["get_acquisitions"](self._channel)
        acq_data = data[acquisition_name]

        return acq_data["acquisition"]

    def get_scope_data(self, acquisition_name: str | None = None, timeout: int | None = 1) -> dict[str, dict]:
        """Get specifically scope data.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            'data':           List of data values.
            'out_of_range':   Boolean indicating if data was out-of-range.
            'avg_cnt':        Number of averages.
        """
        data = self.get_acquisitions(acquisition_name, timeout)
        return data["scope"][f"path{self._channel % 2}"]

    def get_bin_data(
        self, acquisition_name: str | None = None, timeout: int | None = 1
    ) -> dict[str, dict | list | int | float]:
        """Get specifically bin data. Note that 'avg_count' has different meaning depending on type of acquisition.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            'count':      Dictionary with data per path.
            'timedelta':  Time difference of the count with respect to configured start time.
            'threshold':  A list of thresholds.
            'avg_cnt':    A list of number of averages per bin.
        """
        data = self.get_acquisitions(acquisition_name, timeout)
        return data["bins"]

    def get_counts(
        self, acquisition_name: str | None = None, avg: bool = False, timeout: int | None = 1
    ) -> dict | list | int | float:
        """Get the averaged count or pulse count. For 'binned' acquisition ('acquisition' command in a Q1ASM program),
        the return values are the counts of times the sequencer has written in the bin. For 'TTL' acquisition
        ('acquisition_ttl' command in a Q1ASM program), the return value is the count of integrations above
        threshold.

        Parameters:
            acquisition_name: Optional name for data to acquire. If not given, self.name is used.
            avg:              Boolean to select if to take the 'avg_cnt' (True) or raw 'count' (False, default).
            timeout:          Optional timeout in _minutes_ for getting acquisition status. Default is 1 minute.

        Returns:
            count:            Averaged counts per bin or count of integrations above threshold.
        """
        if avg:
            return self.get_bin_data(acquisition_name, timeout)["avg_cnt"]

        return self.get_bin_data(acquisition_name, timeout)["count"]


class QbloxMarkerChannel(_QbloxChannel):
    """A class for making a Qblox marker 'channel' control object. Markers are quite different from the ADC and
    DAC channels. A marker instance should only be used for setting marker-specific values such
    as setting them high or low or setting trigger count thresholds and inversion.

    This object and the contained sequencer will not be used to set channel connections or synchronization with
    ADC or DAC channels, but these connections should be made from instances of those. The given sequencer can be
    the same as for related ADC or DAC channel.
    """

    def __init__(
        self,
        module_func_refs: dict[str, Callable],
        slot: int,
        sequencer: int,
        channel_no: int,
        channel_sequencer_config,
    ) -> None:
        """Initialise a Qblox marker channel instance with respective sequencer configuration.

        Parameters:
            module_func_refs:         The module function references.
            slot:                     The slot number of the module
            sequencer:                The sequencer number assigned to channel.
            channel_no:               The channel number.
            channel_sequencer_config: Sequencer configuration for the channel.
        """
        super().__init__(module_func_refs, slot, sequencer, channel_no)
        # Adjust the channel voltage range for marker channels
        self.voltage_range = self.OUTPUT_VOLTAGE_RANGE["MRK"]  # V TTL
        # Get first the direction for the marker from the sequencer
        self._marker_direction = list(channel_sequencer_config.keys())[0]
        self._bit_number = self._define_marker_channel_bit_number()
        # Define the bit number for this marker channel
        # Keep track of the latest set output level and inversion
        self._set_output_level: float | None = None
        self._inverted: bool | None = None

    @property
    def bit_number(self) -> int:
        return self._bit_number

    def _define_marker_channel_bit_number(self) -> int:
        if self._module_func_refs["is_rf_type"]():
            if self._module_func_refs["is_qcm_type"]():
                bit_number = 3 - self._channel  # channel 2 is M2, channel 3 is M1
            elif self._module_func_refs["is_qrm_type"]():
                bit_number = self._channel + 2  # channel 2 is M1, channel 3 is M2
            else:
                # TODO: should raise an exception as currently no other RF modules?
                bit_number = self._channel  # channel 0 is M1, channel 1 is M2, ...

        else:
            bit_number = self._channel

        return bit_number

    def is_set(self) -> bool:
        """Check if the output level has been set as high, or is inverted and is set as low.
        We return the answer based on latest set value and inversion.

        Returns:
            True:  The output level is high and channel is not inverted, or channel is inverted and output level is low.
            False: The output level is low and channel is not inverted, or channel is inverted and output level is high.
        """
        inverted = self._module_func_refs[f"_get_mrk_inv_en_{self._channel}"]()
        current_int = self._module_func_refs["_get_sequencer_config_val"](
            self._sequencer, ["awg", "marker_ovr", "val"]
        )
        level = (current_int >> self._bit_number) & 1

        return inverted != level

    def get_new_channel_override_value(self, current_int: int, level: bool) -> int:
        """Checks which new channel override value must be set to set the marker channel to
        target level on basis of the current override value integer.

        Parameters:
            current_int: The current override value integer.
            level:       The level to set the channel in. False for 'low' and True for 'high'.

        Returns:
            new_int:     New channel override value integer.
        """
        if level:
            return current_int | (1 << self._bit_number)
        else:
            return current_int & ~(1 << self._bit_number)

    def set_marker_channel_override(self, enable: bool) -> None:
        """Enable or disable marker channel override.

        Parameters:
            enable: True to enable override, False to disable override.
        """
        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "marker_ovr", "en"], enable)

    def get_marker_channel_override_value(self) -> int:
        """Get the override value of the marker channel. The levels are always 4-bit values. Each bit represents a
        (marker) channel on a module. For QCM, the bit order is M4M3M2M1 (MX = marker X), while for QCM-RF the order
        is M1M2O2O1 and for QRM-RF module the order is M2M1O1I1.

        Returns:
            ovr_value: The channel's override value in bits.
        """
        ovr_value = self._module_func_refs["_get_sequencer_config_val"](self._sequencer, ["awg", "marker_ovr", "val"])
        return int(ovr_value)

    def set_marker_channel_override_value(self, ovr_value: int) -> None:
        """Set marker channel override value. The override values are 4-bit values. Each bit represents a (marker)
        channel on a module. For QCM, the bit order is M4M3M2M1 (MX = marker X), while for QCM-RF the order is
        M1M2O2O1 and for QRM-RF module the order is M2M1O1I1.

        So, for example, for QCM module to set marker 3 high, we need to have a 4-bit value where the 3rd bit from
        right is '1'. This can be any combination of 'd1ba' where d, b and a are either 0 or 1. This could be any
        integer in range 4-7 and 12-15.
        For QCM-RF, setting marker 1 low would require one of possible 4-bit values in '0cba' which could be any
        integer in range 0-7. For QRM-RF module the same would be one of possible 4-bit values 'd0ba', where any
        integer in range 0-3 and 8-11 would do.

        Parameters:
            ovr_value: The new marker override value.
        """
        if 0 > ovr_value > 15:
            raise ValueError(f"The marker override value can only be in range of 0-15! Input was {ovr_value}")

        self._module_func_refs["_set_sequencer_config_val"](self._sequencer, ["awg", "marker_ovr", "val"], ovr_value)

    def set_marker_channel_invert(self, invert: bool) -> None:
        """Enable or disable marker channel inversion.

        Parameters:
            invert:        If the channel should be inverted, i.e. with True 1 is 'low' and 0 is 'high'.
        """
        self._module_func_refs[f"_set_mrk_inv_en_{self._channel}"](invert)

    def set_marker_channel_level(self, level: bool, invert: bool | None = None) -> None:
        """Set the output level of the marker channel to requested level, using an override. The levels are always
        set for all channels using a 4-bit setter value. Each bit represents a (marker) channel on a module.
        For QCM, the bit order is M4M3M2M1 (MX = marker X), while for QCM-RF the order is M1M2O2O1 and
        for QRM-RF module the order is M2M1O1I1.

        So, for example, for QCM module to set marker 3 high, we need to have a 4-bit value where the 3rd bit from
        right is '1'. This can be any combination of 'd1ba' where d, b and a are either 0 or 1. This could be any
        integer in range 4-7 and 12-15.
        For QCM-RF, setting marker 1 low would require one of possible 4-bit values in '0cba' which could be any
        integer in range 0-7. For QRM-RF module the same would be one of possible 4-bit values 'd0ba', where any
        integer in range 0-3 and 8-11 would do.

        But we need to keep the current settings for other channels, so we need to check which value
        in the range will be the correct one.

        Parameters:
            level:  The level to set the channel in. False for 'low' and True for 'high'.
            invert: Set this to True if the channel level definition should be inverted.
                    Set it to False if channel level definition should be normal.
        """

        def _bit_is_set(val, bit):
            return (val >> bit) & 1

        def _get_value(val):
            return _bit_is_set(val, self._bit_number) == level

        # Fetch the possible bit values we can give, as integers
        possible_ints = list(filter(_get_value, range(16)))
        # We need to check first the current 4-bit value int to see how all the channels are currently set
        current_int = self.get_marker_channel_override_value()
        if current_int in possible_ints:
            # We do not need to set the level as the marker bit is already set.
            _logger.debug("Marker value %i is already set. Bit number is %i", current_int, self._bit_number)
            # Finally invert if requested.
            if invert is not None:
                self.set_marker_channel_override(True)
                self.set_marker_channel_invert(invert)

            return

        # Otherwise, find out the new int value to set.
        new_int = self.get_new_channel_override_value(current_int, level)
        # First enable the override for the marker.
        self.set_marker_channel_override(True)
        # Then override value with new value.
        self.set_marker_channel_override_value(new_int)
        # Finally invert if requested.
        if invert is not None:
            self.set_marker_channel_invert(invert)
