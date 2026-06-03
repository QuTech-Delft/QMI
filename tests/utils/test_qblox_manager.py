import logging
import unittest
import unittest.mock
from copy import deepcopy
from unittest.mock import create_autospec

from qmi.instruments.qblox.cluster import (
    SEQUENCERS_IN_MODULE,
    AI_IN_MODULE,
    AO_IN_MODULE,
    DIGITAL_MARKERS_IN_MODULE,
    _QbloxModule,
    NativeCluster,
    ScpiCluster,
    Qblox_NativeCluster,
    # Qblox_QcodesCluster    
)
from qmi.utils.qblox_manager import (
    QbloxIOManager,
    QbloxManager,
    _QbloxChannel,
    _QbloxAdcChannel,
    _QbloxDacChannel,
    _QbloxIOChannel,
    _QbloxMarkerChannel,
)
from tests.patcher import PatcherQmiContext as QMI_Context

logging.getLogger("qmi.utils.qblox_manager").setLevel(logging.CRITICAL)
# Some default sequencer settings
AWG = [
    {
        "cont_mode": {"en_path": [False, False], "wave_idx_path": [0, 0]},
        "gain_path": [1.0, 1.0],
        "marker_ovr": {"en": False, "val": 0},
        "mixer": {"corr_gain_ratio": 1.0, "corr_phase_offset_degree": -0.0, "en": False},
        "nco": {"delay_comp": 0, "delay_comp_en": False, "freq_hz": 0.0, "po": 0.0},
        "offs_path": [0.0, 0.0],
        "upsample_rate_path": [0, 0],
    }
]
SEQ_PROC = {
    "sync_en": False,
    "trg": [
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
        {"count_threshold": 1, "threshold_invert": False},
    ],
}
ACQ = [
    {
        "demod": {"en": False},
        "th_acq": {
            "discr_threshold": 0.0,
            "non_weighed_integration_len": 1024,
            "rotation_matrix_a11": 1.0,
            "rotation_matrix_a12": 0.0,
        },
        "th_acq_mrk_map": {"addr": 1, "en": False, "inv": False},
        "th_acq_trg_map": {"addr": 1, "en": False, "inv": False},
        "ttl": {"auto_bin_incr_en": False, "in": False, "threshold": 0.0},
    }
]
ACQ_SCOPE = {
    "avg_en_path": [False, False],
    "sel_acq": 0,
    "trig": {"lvl_path": [0.0, 0.0], "mode_path": [False, False]},
}
IO_CHANNEL = {
    "binned_acq_on_invalid_time_delta": "error",
    "binned_acq_threshold_source": "thresh0",
    "binned_acq_time_ref": "start",
    "binned_acq_time_source": "first",
    "in_counter_mode": "sequencer",
    "in_threshold_primary": 1.0,
    "in_trigger_address": 1,
    "in_trigger_en": False,
    "in_trigger_mode": "rising",
    "out_mode": "disabled",
    "scope_mode": "scope",
    "scope_trigger_level": "any",
    "scope_trigger_mode": "sequencer",
    "thresholded_acq_trigger_address_high": 0,
    "thresholded_acq_trigger_address_invalid": 0,
    "thresholded_acq_trigger_address_low": 0,
    "thresholded_acq_trigger_address_mid": 0,
    "thresholded_acq_trigger_en": False,
}


def _mock_channels(module_type, channel_type, fill_in=False):
    channels = {}
    sequencers_in_mod = SEQUENCERS_IN_MODULE[module_type]
    if channel_type == "adc":
        channels_in_mod = AI_IN_MODULE[module_type]
        for channel in range(channels_in_mod):
            if "RF" in module_type:
                id = "acq_IQ"

            else:
                id = "acq_I" if channel % 2 else "acq_Q"

            for sequencer in range(sequencers_in_mod):
                channels[f"{channel_type}{channel}_{id}{sequencer}"] = {}

    elif channel_type == "dac":
        channels_in_mod = AO_IN_MODULE[module_type]
        for channel in range(channels_in_mod):
            id = "I" if channel % 2 else "Q"
            for sequencer in range(sequencers_in_mod):
                channels[f"{channel_type}{channel}_{id}{sequencer}"] = {}

    elif channel_type == "marker":
        channels_in_mod = DIGITAL_MARKERS_IN_MODULE[module_type]
        for channel in range(channels_in_mod):
            for sequencer in range(sequencers_in_mod):
                channels[f"DO{channel}_{sequencer}"] = {}

    elif channel_type == "IO":
        for sequencer in range(sequencers_in_mod):
            if fill_in:
                channels[f"IO{sequencer}"] = IO_CHANNEL
            else:
                channels[f"IO{sequencer}"] = {}

    return channels


class ChannelTypeStub:
    ACQ = 1
    AWG = 0


class QbloxNativeManagerClassTestCase(unittest.TestCase):
    """Test 'base', a.k.a. 'cluster', class manager creation."""

    def setUp(self) -> None:
        self.qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        self.qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        self.qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        self.qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        self.qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        # Cluster module has no channels nor sequencers
        self.qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=({}, {}))
        self._ctx = QMI_Context("scpi_manager_class_test")

    def test_qblox_manager_init(self):
        """Test initialization and basic method calls"""
        # Arrange
        name_cluster_module = "MM"
        slot_cluster_module = 0
        # Act
        cluster_manager = QbloxManager(self._ctx, name_cluster_module, self.qblox_cluster, "MM", 0)
        # Assert
        self.assertEqual(name_cluster_module, cluster_manager.managed_module)
        self.assertEqual(slot_cluster_module, cluster_manager.managed_slot)
        self.assertDictEqual({}, cluster_manager._module_channels)
        self.assertDictEqual({}, cluster_manager._module_sequencers)
        self.qblox_cluster.get_module_func_refs.assert_called_once_with(name_cluster_module, slot_cluster_module)
        self.qblox_cluster.get_module_channels.assert_not_called()


class QbloxNativeManagerMethodTestCase(unittest.TestCase):
    """Test 'base', a.k.a. 'cluster', class manager methods."""

    def setUp(self) -> None:
        # self.qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        self.qblox_cluster = create_autospec(spec=Qblox_NativeCluster, instance=True)
        self.qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        self.qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        self.qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        self.qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        # Cluster module has no channels nor sequencers
        # self.qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=({}, {}))
        # self.qblox_cluster.get_module_func_refs = unittest.mock.Mock(return_value={})
        self.cluster_manager = QbloxManager(QMI_Context("native"), "cluster", self.qblox_cluster, "MM", 0)

    def test_cluster_manager_get_sequencer(self):
        """Test get_sequencer call. Should fail as no sequencers present at 'MM' module"""
        # Assert
        with self.assertRaises(KeyError):
            self.cluster_manager.get_sequencer(0)  # Cluster has no sequencers

    def test_cluster_manager_get_adc_channel(self):
        """Test get_adc_channel call. Should fail as no channels present at 'MM' module"""
        with self.assertRaises(NotImplementedError):
            self.cluster_manager.get_adc_channel(0)  # Cluster has no ADC channels

    def test_cluster_manager_get_dac_channel(self):
        """Test get_dac_channel call. Should fail as no channels present at 'MM' module"""
        with self.assertRaises(NotImplementedError):
            self.cluster_manager.get_dac_channel(0)  # Cluster has no DAC channels

    def test_cluster_manager_get_marker_channel(self):
        """Test get_marker_channel call. Should fail as no channels present at 'MM' module"""
        with self.assertRaises(NotImplementedError):
            self.cluster_manager.get_marker_channel(0)  # Cluster has no marker channels

    def test_start_sequencers(self):
        """Test start_sequencers call. These calls would fail with real hardware, but here they pass as mocked calls."""
        # Arrange
        expected_call_start_module_sequencers = "SLOT0:SEQuencer"
        expected_call_start_all_sequencers = "SLOT:SEQuencer"
        self.qblox_cluster.reset_mock()
        # Act
        self.cluster_manager.start_sequencers()
        # Assert
        self.qblox_cluster.get_module_func_refs("MM").__getitem__().assert_called_with(
            expected_call_start_module_sequencers
        )
        # Act 2
        self.cluster_manager.start_sequencers(start_all=True)
        # Assert 2
        self.qblox_cluster.get_module_func_refs("MM").__getitem__().assert_called_with(
            expected_call_start_all_sequencers
        )

    def test_stop_sequencers(self):
        """Test stop_sequencers call. These calls would fail with real hardware, but here they pass as mocked calls."""
        # Arrange
        expected_call_stop_module_sequencers = "SLOT0:SEQuencer"
        expected_call_stop_all_sequencers = "SLOT:SEQuencer"
        self.qblox_cluster.reset_mock()
        # Act
        self.cluster_manager.stop_sequencers()
        # Assert
        self.qblox_cluster.get_module_func_refs("MM").__getitem__().assert_called_with(expected_call_stop_module_sequencers)
        # Act 2
        self.cluster_manager.stop_sequencers(stop_all=True)
        # Assert 2
        self.qblox_cluster.get_module_func_refs("MM").__getitem__().assert_called_with(expected_call_stop_all_sequencers)


class QbloxNativeQrmManagerClassTestCase(unittest.TestCase):
    """Test I/O class manager creation with QRM module."""

    def setUp(self) -> None:
        self.module = "QRM"
        self.slot = 2
        self.qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        self.qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        self.qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        self.qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        self.qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        self.qblox_cluster.cluster = unittest.mock.Mock(spec=NativeCluster)
        self.qblox_cluster.cluster_funcs = unittest.mock.Mock(spec=_QbloxModule)

        channels = {}
        channels.update(_mock_channels(self.module, "adc"))
        channels.update(_mock_channels(self.module, "dac"))
        channels.update(_mock_channels(self.module, "marker"))
        # There are no 'io' channels in QRM
        sequencers = {
            f"sequencer{k}": {"awg": {}, "acq": {}} for k in range(SEQUENCERS_IN_MODULE[self.module])
        }
        # Create module channels and sequencers
        self.qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=(channels, sequencers))

    def test_qblox_io_manager_init(self):
        """Test initialization and basic method calls"""
        # Arrange
        sequencers_in_mod = SEQUENCERS_IN_MODULE[self.module]
        ai_channels_in_mod = AI_IN_MODULE[self.module]
        ao_channels_in_mod = AO_IN_MODULE[self.module]
        mrk_channels_in_mod = DIGITAL_MARKERS_IN_MODULE[self.module]
        expected_sequencers = {f"sequencer{i}": {"awg": {}, "acq": {}} for i in range(sequencers_in_mod)}
        exp_no_of_adc_channels = sequencers_in_mod * ai_channels_in_mod
        exp_no_of_dac_channels = sequencers_in_mod * ao_channels_in_mod
        exp_no_of_mrk_channels = sequencers_in_mod * mrk_channels_in_mod
        exp_no_of_io_channels = 0
        exp_total_no_of_channels = (
            exp_no_of_io_channels + exp_no_of_mrk_channels + exp_no_of_dac_channels + exp_no_of_adc_channels
        )
        # Act
        qrm_manager = QbloxIOManager(QMI_Context("qrm_test"), "qrm_manager", self.qblox_cluster, self.module, self.slot)
        # Assert
        self.assertEqual(self.module, qrm_manager.managed_module)
        self.assertEqual(self.slot, qrm_manager.managed_slot)
        self.assertEqual(exp_total_no_of_channels, len(qrm_manager._module_channels))
        self.assertEqual(exp_no_of_adc_channels, len(qrm_manager._adc_channels))
        self.assertEqual(exp_no_of_dac_channels, len(qrm_manager._dac_channels))
        self.assertEqual(exp_no_of_mrk_channels, len(qrm_manager._do_channels))
        self.assertEqual(exp_no_of_io_channels, len(qrm_manager._io_channels))
        self.assertDictEqual(expected_sequencers, qrm_manager._module_sequencers)
        self.qblox_cluster.get_module_func_refs.assert_called_once_with(self.module, self.slot)
        self.qblox_cluster.get_module_channels.assert_called_once_with(self.module, self.slot)
        self.qblox_cluster.get_module_channel_map_cache.assert_called_once_with(self.module, self.slot)

    def test_qblox_io_manager_get_channels(self):
        """Test initialization and basic method calls"""
        # Arrange
        channel = 0
        channel_map = [[0], [1]]  # For QRM
        qrm_manager = QbloxIOManager(QMI_Context("qrm_test"), "qrm_manager", self.qblox_cluster, self.module, self.slot)
        qrm_manager.module_func_refs = {}
        qrm_manager.module_func_refs["_set_io_channel_config"] = unittest.mock.Mock()
        qrm_manager.module_func_refs["_set_sequencer_config"] = unittest.mock.Mock()
        qrm_manager.module_func_refs["_get_sequencer_channel_map"] = unittest.mock.Mock(return_value=channel_map)
        qrm_manager.module_func_refs["_get_sequencer_acq_channel_map"] = unittest.mock.Mock(return_value=channel_map)
        qrm_manager.module_func_refs["is_qcm_type"] = lambda: False
        qrm_manager.module_func_refs["is_qrm_type"] = lambda: True
        qrm_manager.module_func_refs["is_rf_type"] = lambda: False
        qrm_manager.module_func_refs["is_qtm_type"] = lambda: False
        expected_call = [unittest.mock.call(channel, {"awg": {}, "acq": {}})]
        # Act
        with unittest.mock.patch("qmi.utils.qblox_manager.ChannelType", ChannelTypeStub):
            adc_channel = qrm_manager.get_adc_channel(channel)
            dac_channel = qrm_manager.get_dac_channel(channel)
            mrk_channel = qrm_manager.get_marker_channel(channel)

        # Assert
        self.assertIsInstance(adc_channel, _QbloxAdcChannel)
        self.assertIsInstance(dac_channel, _QbloxDacChannel)
        self.assertIsInstance(mrk_channel, _QbloxMarkerChannel)
        self.qblox_cluster.get_module_func_refs.assert_called_once_with(self.module, self.slot)
        self.qblox_cluster.get_module_channels.assert_called_once_with(self.module, self.slot)
        qrm_manager.module_func_refs["_set_io_channel_config"].assert_not_called()
        qrm_manager.module_func_refs["_set_sequencer_config"].assert_has_calls(expected_call)


class QbloxQcmDacMarkerClassTestCase(unittest.TestCase):
    """Test DAC and marker classes created from QCM module I/O class manager."""

    def _sequencer_config_val_setter(self, s, d, v):
        if d[0] == "awg":
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][0][d[1]].update({d[2]: v})
            else:
                old_val = self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
                new_val = [old_val[0], v] if d[2] else [v, old_val[1]]
                self.sequencers[f"sequencer{s}"][d[0]][0].update({d[1]: new_val})
        else:
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][d[1]][d[2]].update({d[3]: v})
            else:
                self.sequencers[f"sequencer{s}"][d[0]][d[1]][d[2]][d[3]] = v

    def _sequencer_config_val_getter(self, s, d):
        return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]][d[2]]

    @unittest.mock.patch("qmi.utils.qblox_manager.ChannelType", ChannelTypeStub)
    def setUp(self) -> None:
        self.module = "QCM"
        self.slot = 1
        self.channel = 2
        channel_map = [[0, 2], [1, 3]]  # For QCM
        self.sequencers = {
            f"sequencer{k}": {"awg": deepcopy(AWG), "seq_proc": deepcopy(SEQ_PROC)}
            for k in range(SEQUENCERS_IN_MODULE[self.module])
        }
        # Make more realistic function references and module type check responses
        func_refs = _QbloxModule(self.module, {})
        func_refs.QCM["is_qcm_type"] = lambda: "QCM" in self.module
        func_refs.QCM["is_qrm_type"] = lambda: "QRM" in self.module
        func_refs.QCM["is_qtm_type"] = lambda: "QTM" in self.module
        func_refs.QCM["is_rf_type"] = lambda: "-RF" in self.module
        self._mrk_inv_en = unittest.mock.Mock(return_value=False)
        for x in range(4):
            if x < 2:
                func_refs.QCM.update({f"_get_in_amp_gain_{x}": lambda: 0.0})
                func_refs.QCM.update({f"_set_in_amp_gain_{x}": lambda val: None})
            func_refs.QCM.update({f"_get_mrk_inv_en_{x}": lambda: self._mrk_inv_en()})
            func_refs.QCM.update({f"_get_dac_offset_{x}": lambda: 0.0})
            func_refs.QCM.update({f"_set_mrk_inv_en_{x}": lambda val: None})
            func_refs.QCM.update({f"_set_dac_offset_{x}": lambda val: None})

        # Mock cluster level
        qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        qblox_cluster.cluster = unittest.mock.Mock(spec=NativeCluster)
        # Mock extra module-level scpi call returns
        func_refs.QCM.update({"_get_sequencer_config": lambda s: self.sequencers[f"sequencer{s}"]})
        func_refs.QCM.update({"_get_sequencer_config_val": lambda s, d: self._sequencer_config_val_getter(s, d)})
        func_refs.QCM.update({"_set_sequencer_config": lambda s, d: self.sequencers[f"sequencer{s}"].update(d)})
        func_refs.QCM.update({"_set_sequencer_config_val": lambda s, d, v: self._sequencer_config_val_setter(s, d, v)})
        func_refs.QCM.update({"_get_sequencer_channel_map": unittest.mock.Mock(return_value=channel_map)})
        func_refs.QCM.update({"_set_sequencer_channel_map": lambda _, __: None})
        func_refs.QCM.update({"_get_sequencer_connect_out": unittest.mock.Mock(side_effect=["I", "Q"] * 2)})
        func_refs.QCM.update({"_set_sequencer_connect_out": lambda _, __, ___: None})
        # Create mock channel dicts
        channels = {}
        channels.update(_mock_channels(self.module, "adc"))
        channels.update(_mock_channels(self.module, "dac"))
        channels.update(_mock_channels(self.module, "marker"))
        # There are no 'io' channels in QCM
        # Create module channels and sequencers
        qblox_cluster.get_module_func_refs = unittest.mock.Mock(return_value=func_refs.QCM)
        qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=(channels, self.sequencers))
        # Create manager
        self.qcm_manager = QbloxIOManager(
            QMI_Context("qcm_test"), "qcm_manager", qblox_cluster, self.module, self.slot
        )
        # Mock-up sequencer calls and get channels
        self.dac_channel = self.qcm_manager.get_dac_channel(self.channel)
        self.dac_channel._is_rf_type = False
        self.mrk_channel = self.qcm_manager.get_marker_channel(self.channel)
        self.mrk_channel._channel_cfg = self.sequencers[f"sequencer{self.channel}"]

    def tearDown(self) -> None:
        self.dac_channel._channel_cfg = None

    def test_dac_channel_properties(self):
        """Test that _QbloxDacChannel instance was created with expected properties."""
        expected_voltage_range = _QbloxDacChannel.OUTPUT_VOLTAGE_RANGE[self.module]

        self.assertListEqual(expected_voltage_range, self.dac_channel.voltage_range)

    def test_marker_channel_properties(self):
        """Test that _QbloxMarkerChannel instance was created with expected properties."""
        expected_marker_direction = "awg"
        expected_voltage_range = _QbloxDacChannel.OUTPUT_VOLTAGE_RANGE["MRK"]

        self.assertEqual(expected_marker_direction, self.mrk_channel._marker_direction)
        self.assertListEqual(expected_voltage_range, self.mrk_channel.voltage_range)

    def test_dac_channel_configure(self):
        """Test _QbloxDacChannel class configure method call"""
        # Arrange
        output_path = 0
        default_gains = [1.0, 1.0]
        default_nco_freq = 0.0
        default_mod_en = False
        expected_gains = [-1.0, 0.0]
        expected_nco_freq = 200e6
        expected_mod_en = True

        # Check before configuring that the to-be-configured values are at defaults
        dict_awg = self.dac_channel._channel_cfg["awg"][0]
        self.assertListEqual(default_gains, dict_awg["gain_path"])
        self.assertEqual(default_nco_freq, dict_awg["nco"]["freq_hz"])
        self.assertEqual(default_mod_en, dict_awg["mixer"]["en"])
        self.dac_channel.configure(output_path, expected_gains, expected_nco_freq, expected_mod_en)

        # Check values changes after configuring
        dict_awg = self.dac_channel._channel_cfg["awg"][0]
        # dict_awg = self.sequencers["sequencer0"]["awg"][self.channel]
        self.assertListEqual(expected_gains, dict_awg["gain_path"])
        self.assertEqual(expected_nco_freq, dict_awg["nco"]["freq_hz"])
        self.assertEqual(expected_mod_en, dict_awg["mixer"]["en"])

    def test_dac_set_offset_and_is_set(self):
        """Test we can check if output is set and that we can set it"""
        default_voltage = 0.0
        new_voltage = 0.5

        # Check before setting that the to-be-set voltage is at default
        dict_awg_b4 = self.dac_channel.get_channel_config()["awg"][0]
        self.assertEqual(default_voltage, dict_awg_b4["offs_path"][self.dac_channel._channel % 2])
        self.assertFalse(self.dac_channel.is_set())

        # Set voltage and test
        self.dac_channel.set_offset(new_voltage)
        dict_awg_after = self.dac_channel.get_channel_config()["awg"][0]
        self.assertEqual(new_voltage, dict_awg_after["offs_path"][self.dac_channel._channel % 2])
        self.assertEqual(new_voltage, self.dac_channel.get_offset())

    def test_dac_set_output_level(self):
        """Test we can set output level with integer values"""
        i_range = _QbloxDacChannel.CHANNEL_LEVEL_RANGE
        v_range = _QbloxDacChannel.OUTPUT_VOLTAGE_RANGE[self.module]
        default_voltage = 0.0
        new_voltage = 0.5
        default_level = int((default_voltage - v_range[0]) / (v_range[1] - v_range[0]) * i_range)
        new_level = int((new_voltage - v_range[0]) / (v_range[1] - v_range[0]) * i_range)

        # Check before setting that the to-be-set voltage is at default
        dict_awg = self.dac_channel.get_channel_config()["awg"][0]
        offset = dict_awg["offs_path"][self.dac_channel._channel % 2]
        self.assertEqual(default_voltage, offset)
        self.assertEqual(default_level, int((offset - v_range[0]) / (v_range[1] - v_range[0]) * i_range))

        # Set voltage and test
        self.dac_channel.set_output_channel_level(new_level)
        new_output = self.dac_channel._set_output_voltage

        self.assertEqual(new_voltage, new_output)
        self.assertEqual(new_level, int((new_output - v_range[0]) / (v_range[1] - v_range[0]) * i_range))
        self.assertEqual(new_voltage, self.dac_channel._set_output_voltage)

    def test_connect_channel_to_output(self):
        """Test the connect_channel_to_output method."""
        channel = self.dac_channel._channel
        expected_state_output_0 = "I"
        expected_state_output_1 = "Q"
        self.dac_channel.connect_channel_to_output(True, 0)
        self.dac_channel.connect_channel_to_output(True, 1)

        state_output_0 = self.dac_channel.get_channel_connected_to_output()
        state_output_1 = self.dac_channel.get_channel_connected_to_output(channel + 1)

        self.assertEqual(expected_state_output_0, state_output_0)
        self.assertEqual(expected_state_output_1, state_output_1)

        # And then test disable
        expected_state_outputs = ["I", "Q"]

        self.dac_channel.connect_channel_to_output(False, 0)
        self.dac_channel.connect_channel_to_output(False, 1)

        state_output_0 = self.dac_channel.get_channel_connected_to_output()
        state_output_1 = self.dac_channel.get_channel_connected_to_output(channel + 1)
        self.assertEqual(expected_state_outputs[0], state_output_0)
        self.assertEqual(expected_state_outputs[1], state_output_1)

    def test_set_nco_propagation_delay_compensation(self):
        """Test setting NCO propagation delay compensation."""
        # Arrange
        expected_delay_compensation = -40
        # Act
        self.dac_channel.set_nco_propagation_delay_compensation(True, expected_delay_compensation)
        first_state, first_delay = self.dac_channel.get_nco_propagation_delay_compensation()
        self.dac_channel.set_nco_propagation_delay_compensation(False, 40)
        second_state, second_delay = self.dac_channel.get_nco_propagation_delay_compensation()
        # Assert
        self.assertTrue(first_state)
        self.assertEqual(expected_delay_compensation, first_delay)
        self.assertFalse(second_state)
        # The second value should be the same as first as the first argument was 'False'
        self.assertEqual(expected_delay_compensation, second_delay)

    def test_set_nco_propagation_delay_compensation_excepts(self):
        """Test setting NCO propagation delay compensation raises ValueError on invalid inputs."""
        # Exception tests
        invalid = [-60, 5.5, "5"]
        for inv in invalid:
            with self.assertRaises(ValueError):
                self.dac_channel.set_nco_propagation_delay_compensation(True, inv)

    def test_get_nco_propagation_delay_compensation(self):
        """Test getting NCO propagation delay compensation."""
        expected_defaults = (False, 0)
        defaults = self.dac_channel.get_nco_propagation_delay_compensation()
        self.assertTupleEqual(expected_defaults, defaults)

    def test_set_marker_channel_level_and_insert_and_is_set(self):
        """Test setting marker channel level and is_set check."""
        # By default the level should be low and no inversion.
        self.assertFalse(self.mrk_channel.is_set())
        # Set inversion on and see that the channel is 'set'
        self.mrk_channel.set_marker_channel_invert(True)
        self._mrk_inv_en.return_value = True

        self.assertTrue(self.mrk_channel.is_set())
        # Then set channel to high and see that the channel is not 'set'
        self.mrk_channel.set_marker_channel_level(True)

        self.assertFalse(self.mrk_channel.is_set())
        # And then set inversion back to normal and see that the channel is now 'set'
        self.mrk_channel.set_marker_channel_invert(False)
        self._mrk_inv_en.return_value = False

        self.assertTrue(self.mrk_channel.is_set())

    def test_set_trigger_count_threshold_and_invert(self):
        """Test that we can set trigger count thresholds and their inversion."""
        default_threshold = 1
        new_threshold = 50
        trigger_idx = 7
        dict_trig = self.mrk_channel.get_channel_config()["seq_proc"]["trg"][trigger_idx - 1]
        self.assertEqual(default_threshold, dict_trig["count_threshold"])
        self.assertFalse(dict_trig["threshold_invert"])

        # Set new threshold and test
        self.mrk_channel.set_trigger_count_threshold_and_invert(trigger_idx, new_threshold)
        dict_trig = self.mrk_channel.get_channel_config()["seq_proc"]["trg"][trigger_idx - 1]
        self.assertEqual(new_threshold, dict_trig["count_threshold"])
        self.assertFalse(dict_trig["threshold_invert"])

        # Set with inversion also and test
        self.mrk_channel.set_trigger_count_threshold_and_invert(trigger_idx, new_threshold, True)
        dict_trig = self.mrk_channel.get_channel_config()["seq_proc"]["trg"][trigger_idx - 1]
        self.assertEqual(new_threshold, dict_trig["count_threshold"])
        self.assertTrue(dict_trig["threshold_invert"])


class QbloxQcmRfDacClassTestCase(unittest.TestCase):
    """Test DAC class created from QCM-RF module I/O class manager."""

    def _sequencer_config_val_setter(self, s, d, v):
        if d[0] == "awg":
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][0][d[1]].update({d[2]: v})
            else:
                old_val = self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
                new_val = [old_val[0], v] if d[2] else [v, old_val[1]]
                self.sequencers[f"sequencer{s}"][d[0]][0].update({d[1]: new_val})
        else:
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][d[1]][d[2]].update({d[3]: v})
            else:
                self.sequencers[f"sequencer{s}"][d[0]][d[1]][d[2]][d[3]] = v

    def _sequencer_config_val_getter(self, s, d):
        if len(d) == 2:
            return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
        if len(d) == 3:
            return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]][d[2]]
        return None

    def _set_output(self, val):
        self.output = val

    @unittest.mock.patch("qmi.utils.qblox_manager.ChannelType", ChannelTypeStub)
    def setUp(self) -> None:
        module = "QCM-RF"
        slot = 2
        self.module_v_range = _QbloxChannel.OUTPUT_VOLTAGE_RANGE[module]
        channel = 1
        channel_map = [[0, 2], [1, 3]]  # For QCM-RF
        self.output = 0.0
        self.sequencers = {
            f"sequencer{k}": {"awg": deepcopy(AWG), "seq_proc": deepcopy(SEQ_PROC)}
            for k in range(SEQUENCERS_IN_MODULE[module])
        }
        # Make more realistic function references and module type check responses
        func_refs = _QbloxModule(module, {})
        func_refs.QCM_RF["is_qcm_type"] = lambda: "QCM" in module
        func_refs.QCM_RF["is_qrm_type"] = lambda: "QRM" in module
        func_refs.QCM_RF["is_qtm_type"] = lambda: "QTM" in module
        func_refs.QCM_RF["is_rf_type"] = lambda: "-RF" in module
        func_refs.QCM_RF["_get_sequencer_channel_map"] = unittest.mock.Mock(return_value=channel_map)
        for x in range(4):
            if x < 2:
                func_refs.QCM_RF.update({f"_get_in_amp_gain_{x}": lambda: 0.0})
                func_refs.QCM_RF.update({f"_set_in_amp_gain_{x}": lambda val: None})
                func_refs.QCM_RF.update({f"_get_lo_enable_{x}": lambda: "True"})
                func_refs.QCM_RF.update({f"_set_lo_enable_{x}": lambda val: None})
                func_refs.QCM_RF.update({f"_get_lo_freq_{x}": lambda: 15e9})
                func_refs.QCM_RF.update({f"_get_lo_freq_{x}": lambda val: None})
                func_refs.QCM_RF.update({f"_get_lo_pwr_{x}": lambda: 0.0})
                func_refs.QCM_RF.update({f"_get_lo_pwr_{x}": lambda val: None})
            func_refs.QCM_RF.update({f"_get_out_amp_offset_{x}": lambda: self.output})
            func_refs.QCM_RF.update({f"_set_out_amp_offset_{x}": lambda val: self._set_output(val)})
            func_refs.QCM_RF.update({f"_get_dac_offset_{x}": lambda: self.output})
            func_refs.QCM_RF.update({f"_set_dac_offset_{x}": lambda val: self._set_output(val)})

        # Mock cluster level
        qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        qblox_cluster.cluster = unittest.mock.Mock(spec=ScpiCluster)
        qblox_cluster.cluster_funcs = {}
        # Mock extra module-level scpi call returns
        func_refs.QCM_RF.update({"_get_sequencer_config": lambda s: self.sequencers[f"sequencer{s}"]})
        func_refs.QCM_RF.update({"_get_sequencer_config_val": lambda s, d: self._sequencer_config_val_getter(s, d)})
        func_refs.QCM_RF.update({"_set_sequencer_config": lambda s, d: self.sequencers[f"sequencer{s}"].update(d)})
        func_refs.QCM_RF.update({"_set_sequencer_config_val": lambda s, d, v: self._sequencer_config_val_setter(s, d, v)})
        func_refs.QCM_RF.update({"_get_sequencer_connect_out": unittest.mock.Mock(side_effect=["IQ"] * 4)})
        func_refs.QCM_RF.update({"_set_sequencer_connect_out": lambda _, __, ___: None})
        # Create mock channel dicts
        channels = {}
        channels.update(_mock_channels(module, "adc"))
        channels.update(_mock_channels(module, "dac"))
        channels.update(_mock_channels(module, "marker"))
        # There are no 'io' channels in QCM-RF
        # Create module channels and sequencers
        qblox_cluster.get_module_func_refs = unittest.mock.Mock(return_value=func_refs.QCM_RF)
        qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=(channels, self.sequencers))
        # Create manager
        self.rf_manager = QbloxIOManager(QMI_Context("qcm-rf"), "rf_mgr", qblox_cluster, module, slot)
        # Mock-up sequencer calls and get channels
        self.dac_channel = self.rf_manager.get_dac_channel(channel)

    def tearDown(self) -> None:
        self.dac_channel._channel_cfg = None

    def test_dac_channel_properties(self):
        """Test that _QbloxDacChannel instance was created with expected properties."""
        self.assertListEqual(self.module_v_range, self.dac_channel.voltage_range)

    def test_dac_channel_configure(self):
        """Test _QbloxDacChannel class configure method call"""
        # Arrange
        output_path = 0
        default_gains = [1.0, 1.0]
        default_nco_freq = 0.0
        default_mod_en = False
        expected_gains = [-1, 0]
        expected_nco_freq = 200e6
        expected_mod_en = True

        # Check before configuring that the to-be-configured values are at defaults
        dict_awg = self.dac_channel._channel_cfg["awg"][0]
        self.assertListEqual(default_gains, dict_awg["gain_path"])
        self.assertEqual(default_nco_freq, dict_awg["nco"]["freq_hz"])
        self.assertEqual(default_mod_en, dict_awg["mixer"]["en"])

        # Act
        self.dac_channel.configure(output_path, expected_gains, expected_nco_freq, expected_mod_en)

        # Check values changes after configuring
        dict_awg = self.dac_channel.get_channel_config()["awg"][0]
        self.assertListEqual(expected_gains, dict_awg["gain_path"])
        self.assertEqual(expected_nco_freq, dict_awg["nco"]["freq_hz"])
        self.assertEqual(expected_mod_en, dict_awg["mixer"]["en"])

    def test_dac_channel_configure_rf(self):
        """Test _QbloxDacChannel class configure method call"""
        # Arrange
        default_phase_error = 0.0
        default_offset_i = 0.0
        default_offset_q = 0.0
        default_gain_ratio = 1.0
        phase_error = 2.0
        offset_i = 3.0
        offset_q = -1.0
        gain_ratio = 0.88
        mod_en = True

        # Check before configuring that the to-be-configured values are at defaults
        rf_config = self.dac_channel.get_rf_configuration()
        self.assertEqual(default_phase_error, rf_config[0])
        self.assertEqual(default_offset_i, rf_config[1])
        self.assertEqual(default_offset_q, rf_config[2])
        self.assertEqual(default_gain_ratio, rf_config[3])
        self.assertFalse(rf_config[4])

        # Configure RF
        self.dac_channel.configure_rf(phase_error, offset_i, offset_q, gain_ratio, mod_en)

        # Check values changes after configuring
        rf_config = self.dac_channel.get_rf_configuration()
        self.assertEqual(phase_error, rf_config[0])
        # Cannot check offset_i and offset_q as the mock lambda function always returns 0.0
        self.assertEqual(gain_ratio, rf_config[3])
        self.assertTrue(rf_config[4])

    def test_dac_set_output_and_is_set(self):
        """Test we can check if output is set and that we can set it"""
        default_voltage = 0.0
        new_voltage = 0.5

        # Check before setting that the to-be-set voltage is at default
        dict_awg_b4 = self.dac_channel.get_channel_config()["awg"][0]
        self.assertEqual(default_voltage, dict_awg_b4["offs_path"][self.dac_channel._channel % 2])
        self.assertFalse(self.dac_channel.is_set())

        # Set voltage and test
        self.dac_channel.set_output(new_voltage)
        self.assertTrue(self.dac_channel.is_set())
        self.assertEqual(new_voltage, self.dac_channel._set_output_voltage)

    def test_dac_set_output_level(self):
        """Test we can set output level with integer values"""
        i_range = _QbloxDacChannel.CHANNEL_LEVEL_RANGE
        v_range = self.module_v_range
        default_voltage = 0.0
        new_voltage = 0.5
        default_level = int((default_voltage - v_range[0]) / (v_range[1] - v_range[0]) * i_range)
        new_level = int((new_voltage - v_range[0]) / (v_range[1] - v_range[0]) * i_range)

        # Check before setting that the to-be-set voltage is at default
        dict_awg = self.dac_channel.get_channel_config()["awg"][0]
        offset = dict_awg["offs_path"][self.dac_channel._channel % 2]
        self.assertEqual(default_voltage, offset)
        self.assertEqual(default_level, int((offset - v_range[0]) / (v_range[1] - v_range[0]) * i_range))

        # Set voltage and test
        self.dac_channel.set_output_channel_level(new_level)
        new_output = self.dac_channel._set_output_voltage

        self.assertAlmostEqual(new_voltage, new_output, 4)
        self.assertEqual(new_level, int((new_output - v_range[0]) / (v_range[1] - v_range[0]) * i_range))
        self.assertAlmostEqual(new_voltage, self.dac_channel._set_output_voltage, 4)

    def test_connect_channel_to_output(self):
        """Test the connect_channel_to_output method."""
        channel = self.dac_channel._channel
        expected_state_output_0 = "IQ"
        expected_state_output_1 = "IQ"
        self.dac_channel.connect_channel_to_output(True, 0)
        self.dac_channel.connect_channel_to_output(True, 1)

        state_output_0 = self.dac_channel.get_channel_connected_to_output(0)
        state_output_1 = self.dac_channel.get_channel_connected_to_output(1)

        self.assertEqual(expected_state_output_0, state_output_0)
        self.assertEqual(expected_state_output_1, state_output_1)

        # And then test disable
        expected_state_outputs = ["IQ", "IQ"]

        self.dac_channel.connect_channel_to_output(False, 0)
        self.dac_channel.connect_channel_to_output(False, 1)

        state_output_0 = self.dac_channel.get_channel_connected_to_output(0)
        state_output_1 = self.dac_channel.get_channel_connected_to_output(1)
        self.assertEqual(expected_state_outputs[0], state_output_0)
        self.assertEqual(expected_state_outputs[1], state_output_1)

    def test_set_lo_enable_state(self):
        """Test LO enable state setter."""
        self.dac_channel.set_lo_enable_state(True)
        self.assertTrue(self.dac_channel.get_lo_enable_state())


class QbloxQrmAdcClassTestCase(unittest.TestCase):
    """Test ADC class created from QRM module I/O class manager.

    As most of the DAC and marker related methods are already tested, we look only in ADC.
    """

    def _sequencer_config_val_setter(self, s, d, v):
        if d[0] == "awg":
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][0][d[1]].update({d[2]: v})
            else:
                old_val = self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
                new_val = [old_val[0], v] if d[2] else [v, old_val[1]]
                self.sequencers[f"sequencer{s}"][d[0]][0].update({d[1]: new_val})
        else:
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][0][d[1]].update({d[2]: v})
            else:
                self.sequencers[f"sequencer{s}"][d[0]][0][d[1]][d[2]] = v

    def _sequencer_config_val_getter(self, s, d):
        if len(d) == 2:
            return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
        if len(d) == 3:
            return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]][d[2]]
        return None

    def _amp_in_gain(self, in_gain):
        self._in_gain = in_gain

    def _mrk_inv_en(self, en):
        self._inv_en = en

    @unittest.mock.patch("qmi.utils.qblox_manager.ChannelType", ChannelTypeStub)
    def setUp(self) -> None:
        self.channel = 1
        self.module = "QRM"
        self.slot = 3
        self.counts = [0.0, 1.0, 2.0]
        self.data = {"data": {
            "acquisition": {
                "bins": {"avg_cnt": self.counts},
                "scope": {f"path{self.channel % 2}": "data"}
            }
        }}
        self._in_gain = 0.0
        self._inv_en = False

        channel_map = [[0], [1]]  # For QRM analog input
        self.sequencers = {
            f"sequencer{k}": {"acq": deepcopy(ACQ), "awg": deepcopy(AWG), "seq_proc": deepcopy(SEQ_PROC)}
            for k in range(SEQUENCERS_IN_MODULE[self.module])
        }
        # Make more realistic function references and module type check responses
        func_refs = _QbloxModule(self.module, {})
        # Need to register these calls as well
        func_refs.QRM["is_qcm_type"] = lambda: "QCM" in self.module
        func_refs.QRM["is_qrm_type"] = lambda: "QRM" in self.module
        func_refs.QRM["is_qtm_type"] = lambda: "QTM" in self.module
        func_refs.QRM["is_rf_type"] = lambda: "-RF" in self.module
        for x in range(4):
            if x < 2:
                func_refs.QRM.update({f"_get_in_amp_gain_{x}": lambda: self._in_gain})
                func_refs.QRM.update({f"_set_in_amp_gain_{x}": lambda val: self._amp_in_gain(val)})
            func_refs.QRM.update({f"_get_mrk_inv_en_{x}": lambda: self._inv_en})
            func_refs.QRM.update({f"_set_mrk_inv_en_{x}": lambda val: self._mrk_inv_en(val)})

        # Mock cluster level
        qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        # Mock extra module-level scpi call returns
        func_refs.QRM.update({"arm_sequencer": lambda _: None})
        func_refs.QRM.update({"start_sequencer": lambda _: None})
        func_refs.QRM.update({"get_acquisitions": lambda _: self.data})
        func_refs.QRM.update({"get_acquisition_status": lambda _, timeout=None, timeout_poll_res=1e-4, check_seq_state=False: True})
        func_refs.QRM.update({"delete_acquisition_data": lambda _, __, ___: None})
        func_refs.QRM.update({"store_scope_acquisitions": lambda _, __: None})
        func_refs.QRM.update({"_get_sequencer_config": lambda s: self.sequencers[f"sequencer{s}"]})
        func_refs.QRM.update({"_get_sequencer_config_val": lambda s, d: self._sequencer_config_val_getter(s, d)})
        func_refs.QRM.update({"_set_sequencer_config": lambda s, d: self.sequencers[f"sequencer{s}"].update(d)})
        func_refs.QRM.update({"_set_sequencer_config_val": lambda s, d, v: self._sequencer_config_val_setter(s, d, v)})
        func_refs.QRM.update({"_get_acq_scope_config": lambda _: ACQ_SCOPE})
        func_refs.QRM.update({"_set_acq_scope_config": lambda _, __: None})
        func_refs.QRM.update({"_get_acq_scope_config_val": lambda _: self.sequencers[f"sequencer{self.channel}"]["acq"][0][_]})
        func_refs.QRM.update({"_set_acq_scope_config_val": lambda _, __: None})
        func_refs.QRM.update({"_get_sequencer_connect_out": unittest.mock.Mock(side_effect=["IQ"] * 2)})
        func_refs.QRM.update({"_set_sequencer_connect_out": lambda _, __, ___: None})
        setattr(func_refs, "_write", lambda _: None)
        setattr(func_refs, "_get_sequencer_acq_channel_map", unittest.mock.Mock(return_value=channel_map))
        setattr(func_refs, "_set_sequencer_acq_channel_map", lambda _, __: None)
        setattr(func_refs, "_get_sequencer_state", lambda _: "OKAY;STOPPED;ACQ_BINNING_DONE,;;;;")
        setattr(func_refs, "_delete_acq_acquisition_data", lambda _, __: None)
        setattr(func_refs, "_set_acq_acquisition_data", lambda _, __: None)
        setattr(func_refs, "_get_acq_acquisitions", lambda _: bytes([1, 0, 0, 0]))
        setattr(func_refs, "_get_acq_data_and_convert", lambda _: [2, 0, 0, 0])
        setattr(func_refs, "_read_bin", lambda _, __: b"data")
        func_refs._instrument = qblox_cluster
        # Create mock channel dicts
        channels = {}
        channels.update(_mock_channels(self.module, "adc"))
        channels.update(_mock_channels(self.module, "dac"))
        channels.update(_mock_channels(self.module, "marker"))
        # There are no 'io' channels in QRM
        # Create module channels and sequencers
        qblox_cluster.get_module_func_refs = unittest.mock.Mock(return_value=func_refs.QRM)
        qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=(channels, self.sequencers))
        # Create manager
        self.qrm_manager = QbloxIOManager(QMI_Context("qrm_mgr"), "qrm_mgr", qblox_cluster, self.module, self.slot)
        # Mock-up sequencer calls and get channels
        self.qrm_manager.module_func_refs["_get_sequencer_acq_channel_map"] = unittest.mock.Mock(return_value=channel_map)
        self.adc_channel = self.qrm_manager.get_adc_channel(self.channel)
        self.mrk_channel = self.qrm_manager.get_marker_channel(self.channel)

    def tearDown(self) -> None:
        self.adc_channel._channel_cfg = None

    def test_adc_channel_properties(self):
        """Test that _QbloxAdcChannel instance was created with expected properties."""
        expected_voltage_range = _QbloxAdcChannel.OUTPUT_VOLTAGE_RANGE[self.module]

        self.assertListEqual(expected_voltage_range, self.adc_channel.voltage_range)

    def test_marker_channel_properties(self):
        """Test that _QbloxMarkerChannel instance was created with expected properties."""
        expected_marker_direction = "acq"
        expected_voltage_range = _QbloxAdcChannel.OUTPUT_VOLTAGE_RANGE["MRK"]

        self.assertEqual(expected_marker_direction, self.mrk_channel._marker_direction)
        self.assertListEqual(expected_voltage_range, self.mrk_channel.voltage_range)

    def test_adc_channel_configure(self):
        """Test _QbloxAdcChannel class configure method call"""
        # Arrange
        input_channel = 0
        default_gain = 0.0
        default_threshold = 0.0
        default_bin_range_adj = False
        expected_gain = 3.0
        expected_demod = True
        expected_threshold = 0.55
        expected_bin_range_adj = True

        # Check before configuring that the to-be-configured values are at defaults
        dict_acq = self.adc_channel._channel_cfg["acq"][0]
        self.assertEqual(default_gain, self.adc_channel.get_input_path_gains()[input_channel])
        self.assertEqual(default_threshold, dict_acq["ttl"]["threshold"])
        self.assertEqual(default_bin_range_adj, dict_acq["ttl"]["auto_bin_incr_en"])
        self.adc_channel.configure(expected_threshold, expected_bin_range_adj, expected_demod, expected_gain)

        # Check values changes after configuring
        dict_new = self.adc_channel.get_channel_config()["acq"][0]
        self.assertEqual(expected_gain, self.adc_channel.get_input_path_gains()[input_channel])
        self.assertEqual(expected_demod, dict_new["demod"]["en"])
        self.assertEqual(expected_threshold, dict_new["ttl"]["threshold"])
        self.assertEqual(expected_bin_range_adj, dict_new["ttl"]["auto_bin_incr_en"])

    def test_prepare_acquisition_sequence(self):
        """Test prepare_acquisition_sequence command.
        Basically this just calls (ATM!) to delete existing acquisition data.
        """
        self.adc_channel.prepare_acquisition_sequence()
        # With name "all" all acquisition data should be erased
        self.adc_channel.prepare_acquisition_sequence("all")
        # TODO: Figure out how to test this. Now just makes a 'happy flow'

    def test_get_acquisition_status(self):
        """Test getting acquisition status."""
        status = self.adc_channel.get_acquisition_completed(timeout=0)
        self.assertTrue(status)  # based on flag being set-up as "ACQ_BINNING_DONE"
        # TODO: would like to test also 'False', but it looks like the lambda can be set in setUp only
        # self.io_channel._module_func_refs._funcs["_get_sequencer_state"] = lambda _: "OKAY;IDLE;DISARMED,;;;;"
        # status = self.io_channel.get_acquisition_status(timeout=0)
        # self.assertTrue(status)  # based on state being set-up as "IDLE"

    def test_run_acquisition_sequence(self):
        """Test running acquisition sequences."""
        self.adc_channel.run_acquisition_sequence()
        # self.assertEqual(2, self.adc_channel._module_func_refs["_check_error_queue"].call_count)
        self.adc_channel.run_acquisition_sequence("all")
        # self.assertEqual(4, self.adc_channel._module_func_refs["_check_error_queue"].call_count)

    def test_get_acquisitions(self):
        """Test getting acquisition data."""
        reply = self.adc_channel.get_acquisitions("data")
        self.assertDictEqual(self.data["data"]["acquisition"], reply)

    def test_get_scope_data(self):
        """Test getting scope acquisition data."""
        reply = self.adc_channel.get_scope_data("data")
        self.assertEqual(self.data["data"]["acquisition"]["scope"][f"path{self.channel % 2}"], reply)

    def test_get_bin_data(self):
        """Test getting bin acquisition data."""
        reply = self.adc_channel.get_bin_data("data")
        self.assertDictEqual(self.data["data"]["acquisition"]["bins"], reply)

    def test_get_counts(self):
        """Test getting counts data."""
        reply = self.adc_channel.get_counts("data")
        self.assertListEqual(self.counts, reply)


class QbloxQtmIOClassTestCase(unittest.TestCase):
    """Test IO class created from QTM module I/O class manager."""

    def _sequencer_config_val_setter(self, s, d, v):
        if d[0] == "awg":
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][0][d[1]].update({d[2]: v})
            else:
                old_val = self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
                new_val = [old_val[0], v] if d[2] else [v, old_val[1]]
                self.sequencers[f"sequencer{s}"][d[0]][0].update({d[1]: new_val})
        else:
            if isinstance(d[2], str):
                self.sequencers[f"sequencer{s}"][d[0]][d[1]][d[2]].update({d[3]: v})
            else:
                self.sequencers[f"sequencer{s}"][d[0]][d[1]][d[2]][d[3]] = v

    def _sequencer_config_val_getter(self, s, d):
        if len(d) == 2:
            return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]]
        if len(d) == 3:
            return self.sequencers[f"sequencer{s}"][d[0]][0][d[1]][d[2]]
        return None

    def _sequencer_io_val_setter(self, s, d, v):
        self.io_channels[f"IO{s}"][d] = v

    def _sequencer_io_val_getter(self, s, d):
        return self.io_channels[f"IO{s}"][d]

    def setUp(self) -> None:
        self.module = "QTM"
        self.slot = 5
        channel = 7
        self.sequencers = {
            f"sequencer{k}": {"seq_proc": SEQ_PROC} for k in range(SEQUENCERS_IN_MODULE[self.module])
        }
        self.io_channels = {
            f"IO{k}": IO_CHANNEL for k in range(SEQUENCERS_IN_MODULE[self.module])
        }
        # Make more realistic function references and module type check responses
        func_refs = _QbloxModule(self.module, {})
        # Need to register these calls as well
        func_refs.QTM["is_qcm_type"] = lambda: "QCM" in self.module
        func_refs.QTM["is_qrm_type"] = lambda: "QRM" in self.module
        func_refs.QTM["is_qtm_type"] = lambda: "QTM" in self.module
        func_refs.QTM["is_rf_type"] = lambda: "-RF" in self.module
        func_refs.QTM["arm_sequencer"] = lambda _: None
        func_refs.QTM["start_sequencer"] = lambda _: None
        func_refs.QTM["get_acquisitions"] = lambda _: {"data": {"acquisition": {"": "data"}}}
        func_refs.QTM["get_acquisition_status"] =  lambda _, timeout=None, timeout_poll_res=1e-4, check_seq_state=False: True
        func_refs.QTM["delete_acquisition_data"] = lambda _, __, ___: None
        func_refs.QTM["store_scope_acquisition"] = lambda _, __: None
        func_refs.QTM["_get_io_channel_config"] = lambda s: self.io_channels[f"IO{s}"]
        func_refs.QTM["_set_io_channel_config"] = lambda s, d: self.io_channels[f"IO{s}"].update(d)
        func_refs.QTM["_get_sequencer_config"] = lambda s: self.sequencers[f"sequencer{s}"]
        func_refs.QTM["_set_sequencer_config"] = lambda s, d: self.sequencers[f"sequencer{s}"].update(d)
        func_refs.QTM.update({"_get_io_channel_config_val": lambda s, d: self._sequencer_io_val_getter(s, d)})
        func_refs.QTM.update({"_set_io_channel_config_val": lambda s, d, v: self._sequencer_io_val_setter(s, d, v)})
        func_refs.QTM.update({"_get_sequencer_config_val": lambda s, d: self._sequencer_config_val_getter(s, d)})
        func_refs.QTM.update({"_set_sequencer_config_val": lambda s, d, v: self._sequencer_config_val_setter(s, d, v)})

        # Mock cluster level
        qblox_cluster = unittest.mock.Mock(spec=Qblox_NativeCluster)
        qblox_cluster.SEQUENCERS_IN_MODULE = SEQUENCERS_IN_MODULE
        qblox_cluster.AI_IN_MODULE = AI_IN_MODULE
        qblox_cluster.AO_IN_MODULE = AO_IN_MODULE
        qblox_cluster.DIGITAL_MARKERS_IN_MODULE = DIGITAL_MARKERS_IN_MODULE
        # mock some key SCPI call functions with lambda functions
        setattr(func_refs, "_write", lambda _: None)
        setattr(func_refs, "_get_sequencer_state", lambda _: "OKAY;STOPPED;ACQ_BINNING_DONE,;;;;")
        setattr(func_refs, "_delete_acq_acquisition_data", lambda _, __: None)
        setattr(func_refs, "_set_acq_acquisition_data", lambda _, __: None)
        setattr(func_refs, "_get_acq_acquisitions", lambda _: bytes([1, 0, 0, 0]))
        setattr(func_refs, "_get_acq_data_and_convert", lambda _: [2, 0, 0, 0])
        setattr(func_refs, "_read_bin", lambda _, __: b"data")
        func_refs._instrument = qblox_cluster
        # Create mock channel dicts
        channels = {}
        channels.update(_mock_channels(self.module, "marker"))
        channels.update(_mock_channels(self.module, "IO", fill_in=True))
        # There are no 'adc' nor 'dac' channels in QTM
        # Create module channels and sequencers
        qblox_cluster.get_module_func_refs = unittest.mock.Mock(return_value=func_refs.QTM)
        qblox_cluster.get_module_channels = unittest.mock.Mock(return_value=(channels, self.sequencers))
        # Create manager
        self.qtm_manager = QbloxIOManager(QMI_Context("qtm_mgr"), "qtm_mgr", qblox_cluster, self.module, self.slot)
        # Mock-up sequencer calls and get channels
        self.io_channel = self.qtm_manager.get_io_channel(channel)

    def tearDown(self) -> None:
        self.io_channel._channel_cfg = None

    def test_io_channel_properties(self):
        """Test that _QbloxIOChannel instance was created with expected properties."""
        expected_voltage_range = _QbloxIOChannel.OUTPUT_VOLTAGE_RANGE[self.module]

        self.assertListEqual(expected_voltage_range, self.io_channel.voltage_range)
        dict_seq = self.io_channel._sequencer_cfg
        dict_chn = self.io_channel._channel_cfg

        seq_config = self.io_channel.get_sequencer_config()
        chn_config = self.io_channel.get_channel_config()

        self.assertDictEqual(dict_seq, seq_config)
        self.assertDictEqual(dict_chn, chn_config)

    def test_configure_binned_acquisition(self):
        """Test _QbloxIOChannel class binned acquisition configure method call"""
        # Arrange
        default_threshold_voltage = 1.0
        default_time_ref = "start"
        default_time_source = "first"
        default_invalid_time_delta = "error"
        expected_threshold_voltage = 0.1
        expected_time_ref = "end"
        expected_time_source = "last"
        expected_invalid_time_delta = "record_0"

        # Check before configuring that the to-be-configured values are at defaults
        channel_cfg = self.io_channel.get_channel_config()
        self.assertEqual(default_threshold_voltage, channel_cfg["in_threshold_primary"])
        self.assertEqual(default_time_ref, channel_cfg["binned_acq_time_ref"])
        self.assertEqual(default_time_source, channel_cfg["binned_acq_time_source"])
        self.assertEqual(default_invalid_time_delta, channel_cfg["binned_acq_on_invalid_time_delta"])
        # Configure with new values
        self.io_channel.configure_binned_acquisition(
            expected_threshold_voltage, expected_time_source, expected_time_ref, expected_invalid_time_delta
        )
        # Check values changes after configuring
        channel_cfg_2 = self.io_channel.get_channel_config()
        self.assertEqual(expected_threshold_voltage, channel_cfg_2["in_threshold_primary"])
        self.assertEqual(expected_time_ref, channel_cfg_2["binned_acq_time_ref"])
        self.assertEqual(expected_time_source, channel_cfg_2["binned_acq_time_source"])
        self.assertEqual(expected_invalid_time_delta, channel_cfg_2["binned_acq_on_invalid_time_delta"])

    def test_set_trigger_count_threshold_and_invert(self):
        """Test that we can set trigger count thresholds and their inversion."""
        default_threshold = 1
        new_threshold = 50
        trigger_idx = 14
        dict_trig = self.io_channel.get_sequencer_config()["seq_proc"]["trg"][trigger_idx - 1]
        self.assertEqual(default_threshold, dict_trig["count_threshold"])
        self.assertFalse(dict_trig["threshold_invert"])

        # Set new threshold and test
        self.io_channel.set_trigger_count_threshold_and_invert(trigger_idx, new_threshold)
        dict_trig = self.io_channel.get_sequencer_config()["seq_proc"]["trg"][trigger_idx - 1]
        self.assertEqual(new_threshold, dict_trig["count_threshold"])
        self.assertFalse(dict_trig["threshold_invert"])

        # Set with inversion also and test
        self.io_channel.set_trigger_count_threshold_and_invert(trigger_idx, new_threshold, True)
        dict_trig = self.io_channel.get_sequencer_config()["seq_proc"]["trg"][trigger_idx - 1]
        self.assertEqual(new_threshold, dict_trig["count_threshold"])
        self.assertTrue(dict_trig["threshold_invert"])

    def test_get_acquisition_completed(self):
        """Test getting acquisition status."""
        status = self.io_channel.get_acquisition_completed(timeout=0)
        self.assertTrue(status)  # based on flag being set-up as "ACQ_BINNING_DONE"
        # TODO: would like to test also 'False', but it looks like the lambda can be set in setUp only
        # self.io_channel._module_func_refs._funcs["_get_sequencer_state"] = lambda _: "OKAY;IDLE;DISARMED,;;;;"
        # status = self.io_channel.get_acquisition_status(timeout=0)
        # self.assertTrue(status)  # based on state being set-up as "IDLE"

    def test_get_acquisitions(self):
        """Test getting acquisition data."""
        data = {"": "data"}
        reply = self.io_channel.get_acquisitions("data")
        self.assertDictEqual(data, reply)
