import copy
import json
import logging
import unittest
from unittest.mock import call, patch

import qmi.instruments.qblox.cluster
from qmi.instruments.qblox import (
    Qblox_NativeCluster, Qblox_QcodesCluster, SEQUENCERS_IN_MODULE, AI_IN_MODULE, AO_IN_MODULE, DIGITAL_MARKERS_IN_MODULE
)
from qmi.instruments.qblox.cluster import _QbloxModule
from tests.patcher import PatcherQmiContext as QMI_Context

# Suppress logging
logging.getLogger("resolver").setLevel(logging.CRITICAL)
logging.getLogger("lib.instrument_maker").setLevel(logging.CRITICAL)

qmi.instruments.qblox.cluster.DEBUG_LEVEL = 1
BUILD_INFO = (
    "fwVersion=0.6.0 fwBuild=10/07/2023-22:06:19 fwHash=0x586B0909 fwDirty=0 "
    + "kmodVersion=0.6.0 kmodBuild=10/07/2023-22:06:19 kmodHash=0x586B0909 kmodDirty=0 "
    + "swVersion=0.6.0 swBuild=10/07/2023-22:06:19 swHash=0x586B0909 swDirty=0 cfgManVersion=0.3.0 "
    + "cfgManBuild=10/07/2023-22:06:19 cfgManHash=0x586B0909 cfgManDirty=0"
)
mock_cluster_layout = {
    "MM 0": {"IDN": "a,Cluster MM,b," + BUILD_INFO},
    "QCM 1": {"IDN": "a,Cluster QCM,b," + BUILD_INFO},
    "QCM-RF 2": {"IDN": "a,Cluster QCM,b," + BUILD_INFO},
    "QRM 3": {"IDN": "a,Cluster QRM,b," + BUILD_INFO},
    "QRM-RF 4": {"IDN": "a,Cluster QRM,b," + BUILD_INFO},
    "QTM 5": {"IDN": "a,Cluster QTM,b," + BUILD_INFO},
}

MOCK_CLUSTER_LAYOUT = json.dumps(mock_cluster_layout).encode("utf-8")
modules = {
        "0": {"model": "CLUSTER MM", "is_rf": False},
        "1": {"model": "CLUSTER QCM", "is_rf": False},
        "2": {"model": "CLUSTER QCM", "is_rf": True},
        "3": {"model": "CLUSTER QRM", "is_rf": False},
        "4": {"model": "CLUSTER QRM", "is_rf": True},
        "5": {"model": "CLUSTER QTM", "is_rf": False},
    }
JSON_DESCR_MODULES = json.dumps({"modules": modules}).encode("utf-8")
DO_DICT = {
    'sync_en': False, 'trg': [{'count_threshold': 1, 'threshold_invert': False}] * 15
}
ADC_DICT = [
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
DAC_DICT = [
    {'cont_mode': {'en_path': [False, False], 'wave_idx_path': [0, 0]}, 'gain_path': [1.0, 1.0],
     'marker_ovr': {'en': False, 'val': 0},
     'mixer': {'corr_gain_ratio': 1.0, 'corr_phase_offset_degree': -0.0, 'en': False},
     'nco': {'delay_comp': 0, 'delay_comp_en': False, 'freq_hz': 0.0, 'po': 0.0},
     'offs_path': [0.0, 0.0], 'upsample_rate_path': [0, 0]}
]
QCM_SEQUENCER_CONFIG = {
    "awg": DAC_DICT,
    "seq_proc": DO_DICT
}
QRM_SEQUENCER_CONFIG = copy.deepcopy(QCM_SEQUENCER_CONFIG)
QRM_SEQUENCER_CONFIG.update(dict(acq=ADC_DICT))
QTM_SEQUENCER_CONFIG = {
    "seq_proc": DO_DICT
}
IO_CHANNEL_CONFIG = {
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


class TypeHandle_QbloxModule(_QbloxModule):
    """Extended class for more complex module function handles.
    
    Made compatible for both Native and QCodes cluster versions.
    """

    class InstrumentType:
        def __init__(self, instr_type: str) -> None:
            self.value = instr_type

    class ModuleType:
        def __init__(self, module_type: str, is_rf: bool) -> None:
            self.value = module_type

    class InstrumentClass:
        def __init__(self, instr_type: str) -> None:
            self.value = "Cluster" if "MM" in instr_type else "Module"

    def __init__(self, module: str, is_rf: bool, slot: str) -> None:
        self.name = module  # Qcodes only
        self.instrument_type = self.InstrumentType(module)
        self.module_type = self.ModuleType(module, is_rf)
        self.instrument_class = self.InstrumentClass(module)
        self.is_rf_type = is_rf
        self.slot_idx = int(slot)  # Qcodes only
        super().__init__(module, {})

    def present(self) -> bool:
        return True  # Qcodes only
    
    def _get_sequencer_config(self, slot: int, sequencer: int) -> dict:
        if "QCM" in modules[str(slot)]["model"]:
            return QCM_SEQUENCER_CONFIG
        if "QRM" in modules[str(slot)]["model"]:
            return QRM_SEQUENCER_CONFIG
        if "QTM" in modules[str(slot)]["model"]:
            return QTM_SEQUENCER_CONFIG
        return {}  # MM

    def _get_io_channel_config(self) -> dict:
        return IO_CHANNEL_CONFIG

    def _get_sequencer_channel_map(self, slot: int, sequencer: int) -> tuple:
        if "QRM" in modules[str(slot)]["model"]:
            return ([0], [1])
        
        return ([0, 2], [1, 3])
    
    def _get_sequencer_acq_channel_map(self, slot: int, sequencer: int) -> tuple:
        return ([0], [1])
    

class ScpiClusterStub:
    """Mock the ScpiCluster class"""
    def __init__(self): ...
    def _arm_sequencer(self): ...
    def _start_sequencer(self): ...
    def _stop_sequencer(self): ...
    def _write(self, arg): ...
    def _read_bin(self): ...
    def _flush_line_end(self): ...


class CreateClusterTestCase(unittest.TestCase):
    """Test creating cluster instances and see that they are initialized as expected."""

    def _add_is_functions_to_module(self, mod, mod_e):
        types = ["mm", "qcm", "qrm", "qtm", "rf"]
        for mod_type in types:
            setattr(mod, f"is_{mod_type}_type", lambda: mod_type.upper() in mod_e)

        return mod

    def setUp(self) -> None:
        self._ctx = QMI_Context("cluster_test")
        self._qblox_instruments_patch = patch("qmi.instruments.qblox.cluster.qblox_instruments", unittest.mock.Mock())
        self._qblox_instruments_patch.start()
        self.addCleanup(self._qblox_instruments_patch.stop)
        self._scpi_cluster_patch = patch("qmi.instruments.qblox.cluster.ScpiCluster", ScpiClusterStub)
        self._scpi_cluster_patch.start()
        self.addCleanup(self._scpi_cluster_patch.stop)
        self._attr_names_patch = patch("qmi.instruments.qblox.cluster._get_required_qrm_qcm_attr_names", return_value=[])
        self._qtm_attr_names_patch = patch("qmi.instruments.qblox.cluster._get_required_qtm_attr_names", return_value=[])
        self._attr_names_patch.start()
        self._qtm_attr_names_patch.start()
        self.addCleanup(self._attr_names_patch.stop)
        self.addCleanup(self._qtm_attr_names_patch.stop)
        self._mod_handles = {}
        for slot, module in modules.items():
            module_name = module["model"][8:]
            is_rf = module["is_rf"]
            type_handle = TypeHandle_QbloxModule(module_name, is_rf, slot)
            self._mod_handles[slot] = {"type_handle": type_handle}

    def test_create_native_cluster(self):
        with patch("qmi.instruments.qblox.cluster.NativeCluster") as cluster_patch:
            side_effect = ["qblox,Cluster_MM,b," + BUILD_INFO, "0"]
            cluster_patch().instrument_type = self._mod_handles["0"]["type_handle"].instrument_type
            cluster_patch()._get_idn = unittest.mock.Mock(side_effect=side_effect)
            cluster_patch()._mod_handles = self._mod_handles
            cluster_patch()._type_handle = self._mod_handles["0"]["type_handle"]
            name, ip = "native", "123.45.67.89"
            cluster = Qblox_NativeCluster(self._ctx, name, ip)
            cluster.open()

        self.assertEqual(name, cluster._name)
        self.assertEqual("MM", cluster._instrument_type)
        cluster.close()
        cluster_patch.assert_has_calls([
            call(identifier=ip, port=None, debug=None, dummy_cfg=None),
            call()._get_idn(),
            call().stop_sequencer(),
            call().clear_sequencer_flags()
        ], any_order=True)

    def test_create_qcodes_cluster(self):
        # Arrange
        status = unittest.mock.Mock()
        status.status = "OKAY;NO;PROBLEMS"
        with patch("qmi.instruments.qblox.cluster.Cluster") as cluster_patch:
            cluster_patch().instrument_type = self._mod_handles["0"]["type_handle"].instrument_type
            cluster_patch()._type_handle = self._mod_handles["0"]["type_handle"]
            cluster_patch().modules = [v["type_handle"] for _, v in self._mod_handles.items()]
            name, ip = "qcoodes", "123.45.67.89"
            # Act
            cluster = Qblox_QcodesCluster(self._ctx, name, ip)
            cluster.open()

        # Assert
        self.assertEqual(name, cluster._name)
        self.assertEqual("MM", cluster._instrument_type)
        cluster.close()
        cluster_patch.assert_has_calls([
            call(name=name, identifier=ip, port=None, debug=None, dummy_cfg=None),
            call().stop_sequencer(),
            call().clear_sequencer_flags()
        ])

    def test_base_cluster_helpers(self):
        cluster = qmi.instruments.qblox.cluster.Qblox_ClusterBase(
            self._ctx, "base", "123.45.67.89", port=5025, dummy_cfg={"1": "QCM"}
        )
        cluster._cluster = unittest.mock.Mock()
        cluster.cluster_funcs["do_work"] = unittest.mock.Mock()
        status = unittest.mock.Mock()
        status.status.name = "OKAY"
        cluster.cluster.get_system_status.return_value = status
        cluster.cluster.get_trigger_monitor_count.return_value = 7
        cluster.cluster.get_trigger_monitor_latest.return_value = 3

        self.assertEqual("base", cluster.get_name())
        self.assertIs(cluster.cluster_funcs, cluster.get_funcs())
        self.assertEqual("OKAY", cluster.get_system_state())
        cluster.reset_cluster()
        cluster.cluster._reset.assert_called_once_with()
        cluster.reset_trigger_monitor_count(1)
        cluster.cluster.reset_trigger_monitor_count.assert_called_once_with(1)
        self.assertEqual(7, cluster.get_trigger_monitor_count(2))
        cluster.cluster.get_trigger_monitor_count.assert_called_once_with(2)
        self.assertEqual(3, cluster.get_trigger_monitor_latest())

        with self.assertRaises(ValueError):
            cluster.reset_trigger_monitor_count(0)
        with self.assertRaises(ValueError):
            cluster.get_trigger_monitor_count(16)
        with self.assertRaises(NotImplementedError):
            cluster.reset_module(1)
        with self.assertRaises(NotImplementedError):
            cluster.get_module("QCM")
        with self.assertRaises(NotImplementedError):
            cluster.get_module_func_refs("QCM")
        with self.assertRaises(NotImplementedError):
            cluster.get_module_channels("QCM")

    def test_test_helpers_cover_default_paths(self):
        mm_handle = TypeHandle_QbloxModule("MM", False, 0)
        qcm_handle = TypeHandle_QbloxModule("QCM", False, 1)
        qrm_handle = TypeHandle_QbloxModule("QRM", False, 3)

        self.assertTrue(mm_handle.present())
        self.assertEqual({}, mm_handle._get_sequencer_config(0, 0))
        self.assertIs(qcm_handle._get_io_channel_config(), IO_CHANNEL_CONFIG)
        self.assertIs(qcm_handle._get_sequencer_config(1, 0), QCM_SEQUENCER_CONFIG)
        self.assertIs(qrm_handle._get_sequencer_config(3, 0), QRM_SEQUENCER_CONFIG)
        self.assertEqual(([0, 2], [1, 3]), qcm_handle._get_sequencer_channel_map(1, 0))
        self.assertEqual(([0], [1]), qrm_handle._get_sequencer_channel_map(3, 0))
        self.assertEqual(([0], [1]), qcm_handle._get_sequencer_acq_channel_map(1, 0))

        scpi_stub = ScpiClusterStub()
        self.assertIsNone(scpi_stub._arm_sequencer())
        self.assertIsNone(scpi_stub._start_sequencer())
        self.assertIsNone(scpi_stub._stop_sequencer())
        self.assertIsNone(scpi_stub._write("cmd"))
        self.assertIsNone(scpi_stub._read_bin())
        self.assertIsNone(scpi_stub._flush_line_end())

        module = unittest.mock.Mock()
        returned_module = self._add_is_functions_to_module(module, "QCM-RF")
        self.assertIs(returned_module, module)
        self.assertTrue(hasattr(module, "is_qcm_type"))


class NativeClusterTestCase(unittest.TestCase):
    """Test native cluster instance methods."""
    EXTRA_ATTRS = ["_get_sequencer_config"]

    def setUp(self) -> None:
        _mod_handles = {}
        for slot, module in modules.items():
            module_name = module["model"][8:]
            is_rf = module["is_rf"]
            type_handle = TypeHandle_QbloxModule(module_name, is_rf, slot)
            type_handle._is_mm_type = "MM" in module_name
            type_handle._is_qcm_type = "QCM" in module_name
            type_handle._is_qrm_type = "QRM" in module_name
            type_handle._is_qtm_type = "QTM" in module_name
            type_handle._is_rf_type = is_rf
            _mod_handles[slot] = {
                "type_handle": type_handle,
                "_get_sequencer_channel_map": TypeHandle_QbloxModule._get_sequencer_channel_map,
                "_get_io_channel_config": TypeHandle_QbloxModule._get_io_channel_config
            }

        self._qblox_instruments_patch = patch("qmi.instruments.qblox.cluster.qblox_instruments", unittest.mock.Mock())
        self._qblox_instruments_patch.start()
        self.addCleanup(self._qblox_instruments_patch.stop)
        self._scpi_cluster_patch = patch("qmi.instruments.qblox.cluster.ScpiCluster", ScpiClusterStub)
        self._scpi_cluster_patch.start()
        self.addCleanup(self._scpi_cluster_patch.stop)
        self._attr_names_patch = patch("qmi.instruments.qblox.cluster._get_required_qrm_qcm_attr_names", return_value=self.EXTRA_ATTRS)
        self._qtm_attr_names_patch = patch("qmi.instruments.qblox.cluster._get_required_qtm_attr_names", return_value=self.EXTRA_ATTRS)
        self._attr_names_patch.start()
        self._qtm_attr_names_patch.start()
        self.addCleanup(self._attr_names_patch.stop)
        self.addCleanup(self._qtm_attr_names_patch.stop)
        with patch("qmi.instruments.qblox.cluster.NativeCluster") as cluster_patch:
            cluster_patch._get_sequencer_config = TypeHandle_QbloxModule._get_sequencer_config
            cluster_patch._get_io_channel_config = TypeHandle_QbloxModule._get_io_channel_config
            cluster_patch._get_sequencer_channel_map = TypeHandle_QbloxModule._get_sequencer_channel_map
            cluster_patch._get_sequencer_acq_channel_map = TypeHandle_QbloxModule._get_sequencer_acq_channel_map
            side_effect = ["qblox,Cluster_MM,b," + BUILD_INFO] * 2
            cluster_patch().instrument_type = _mod_handles["0"]["type_handle"].instrument_type
            cluster_patch().instrument_class = _mod_handles["0"]["type_handle"].instrument_class
            cluster_patch()._get_idn = unittest.mock.Mock(side_effect=side_effect)
            cluster_patch()._mod_handles = _mod_handles
            cluster_patch()._type_handle = _mod_handles["0"]["type_handle"]
            name, ip = "native", "123.45.67.89"
            qmi.instruments.qblox.cluster.DEBUG_LEVEL = 2  # Set to 2 to avoid useless error checks
            _ctx = QMI_Context("cluster_test")
            self.cluster = Qblox_NativeCluster(_ctx, name, ip)
            self.cluster.open()

    def tearDown(self) -> None:
        self.cluster.close()

    def test_get_module(self):
        mm = self.cluster.get_module("MM")
        self.assertEqual("Cluster", mm.instrument_class.value)
        self.assertEqual("MM", mm.instrument_type.value)

        qcm = self.cluster.get_module("QCM")
        self.assertTrue(qcm.is_qcm_type())
        self.assertFalse(qcm.is_qrm_type())
        self.assertFalse(qcm.is_qrc_type())
        self.assertFalse(qcm.is_qtm_type())
        self.assertFalse(qcm.is_rf_type())

        qcm_rf = self.cluster.get_module("QCM-RF")
        self.assertTrue(qcm_rf.is_qcm_type())
        self.assertFalse(qcm_rf.is_qrm_type())
        self.assertFalse(qcm.is_qrc_type())
        self.assertFalse(qcm_rf.is_qtm_type())
        self.assertTrue(qcm_rf.is_rf_type())

        qrm = self.cluster.get_module("QRM")
        self.assertFalse(qrm.is_qcm_type())
        self.assertTrue(qrm.is_qrm_type())
        self.assertFalse(qcm.is_qrc_type())
        self.assertFalse(qrm.is_qtm_type())
        self.assertFalse(qrm.is_rf_type())

        qrm_rf = self.cluster.get_module("QRM-RF")
        self.assertFalse(qrm_rf.is_qcm_type())
        self.assertTrue(qrm_rf.is_qrm_type())
        self.assertFalse(qcm.is_qrc_type())
        self.assertFalse(qrm_rf.is_qtm_type())
        self.assertTrue(qrm_rf.is_rf_type())

        qtm = self.cluster.get_module("QTM")
        self.assertFalse(qtm.is_qcm_type())
        self.assertFalse(qtm.is_qrm_type())
        self.assertFalse(qcm.is_qrc_type())
        self.assertTrue(qtm.is_qtm_type())
        self.assertFalse(qtm.is_rf_type())

    def test_get_module_func_refs(self):
        qcm = self.cluster.get_module_func_refs("QCM")
        self.assertTrue(qcm["is_qcm_type"]())
        self.assertFalse(qcm["is_qrm_type"]())
        self.assertFalse(qcm["is_qtm_type"]())
        self.assertFalse(qcm["is_rf_type"]())

        qcm_rf = self.cluster.get_module_func_refs("QCM-RF")
        self.assertTrue(qcm_rf["is_qcm_type"]())
        self.assertFalse(qcm_rf["is_qrm_type"]())
        self.assertFalse(qcm_rf["is_qtm_type"]())
        self.assertTrue(qcm_rf["is_rf_type"]())

        qrm = self.cluster.get_module_func_refs("QRM")
        self.assertFalse(qrm["is_qcm_type"]())
        self.assertTrue(qrm["is_qrm_type"]())
        self.assertFalse(qrm["is_qtm_type"]())
        self.assertFalse(qrm["is_rf_type"]())

        qrm_rf = self.cluster.get_module_func_refs("QRM-RF")
        self.assertFalse(qrm_rf["is_qcm_type"]())
        self.assertTrue(qrm_rf["is_qrm_type"]())
        self.assertFalse(qrm_rf["is_qtm_type"]())
        self.assertTrue(qrm_rf["is_rf_type"]())

        qtm = self.cluster.get_module_func_refs("QTM")
        self.assertFalse(qtm["is_qcm_type"]())
        self.assertFalse(qtm["is_qrm_type"]())
        self.assertTrue(qtm["is_qtm_type"]())
        self.assertFalse(qtm["is_rf_type"]())

    def test_get_module_with_slot_and_errors(self):
        self.assertIs(self.cluster.cluster, self.cluster.get_module("MM", slot_no=0))
        self.assertEqual("QCM", str(self.cluster.get_module("QCM", slot_no=1)))
        self.assertEqual("QRM-RF", str(self.cluster.get_module("QRM-RF", slot_no=4)))

        with self.assertRaisesRegex(ValueError, "management module"):
            self.cluster.get_module("MM", slot_no=1)
        with self.assertRaisesRegex(ValueError, "slot position 2"):
            self.cluster.get_module("QCM", slot_no=2)
        with self.assertRaisesRegex(ValueError, "Module QRC not found"):
            self.cluster.get_module("QRC")

    def test_get_module_func_refs_for_cluster_and_slot(self):
        cluster_funcs = self.cluster.get_module_func_refs("MM")
        self.assertIn("get_trigger_monitor_count", cluster_funcs)
        self.assertTrue(cluster_funcs["is_mm_type"]())

        qcm_refs = self.cluster.get_module_func_refs("QCM", slot_no=1)
        self.assertTrue(qcm_refs["is_qcm_type"]())
        self.assertIn("_get_sequencer_config", qcm_refs)

    def test_native_channel_filters_and_channel_map_cache(self):
        adc_channels, sequencers = self.cluster.get_module_channels("QRM", slot_no=3, channel_type=1)
        self.assertEqual(2 * SEQUENCERS_IN_MODULE["QRM"], len(adc_channels))
        self.assertEqual(SEQUENCERS_IN_MODULE["QRM"], len(sequencers))
        self.assertTrue(all(name.startswith("adc") for name in adc_channels))

        dac_channels, _ = self.cluster.get_module_channels("QCM", slot_no=1, channel_type=2)
        self.assertEqual(4 * SEQUENCERS_IN_MODULE["QCM"], len(dac_channels))
        self.assertTrue(all(name.startswith("dac") for name in dac_channels))

        marker_channels, _ = self.cluster.get_module_channels("QCM", slot_no=1, channel_type=3)
        self.assertEqual(DIGITAL_MARKERS_IN_MODULE["QCM"] * SEQUENCERS_IN_MODULE["QCM"], len(marker_channels))
        self.assertTrue(all(name.startswith("DO") for name in marker_channels))

        io_channels, _ = self.cluster.get_module_channels("QTM", slot_no=5, channel_type=4)
        self.assertEqual(SEQUENCERS_IN_MODULE["QTM"], len(io_channels))
        self.assertTrue(all(name.startswith("IO") for name in io_channels))

        with patch("qmi.instruments.qblox.cluster.ChannelMapCache", return_value="cache") as cache_patch:
            cache = self.cluster.get_module_channel_map_cache("QCM", slot_no=1)

        self.assertEqual("cache", cache)
        cache_patch.assert_called_once()

    def test_reset_module_calls_native_slot_reset(self):
        self.cluster.reset_module(1)
        self.cluster.cluster._slot_reset.assert_called_once_with()

    def test_get_channels(self):
        """Test getting all channels and sequencers out from the modules"""
        for module in ["MM", "QCM", "QCM-RF", "QRM", "QRM-RF", "QTM"]:
            expected_sequencers = SEQUENCERS_IN_MODULE[module]
            expected_channels = (
                AO_IN_MODULE[module]
                + DIGITAL_MARKERS_IN_MODULE[module]
                + AI_IN_MODULE[module]
            ) * SEQUENCERS_IN_MODULE[module]
            if "RF" in module:  # The RF modules are created using the regular non-RF channel map, giving double AIO
                expected_channels += 2 * SEQUENCERS_IN_MODULE[module]

            if module == "QTM":  # The QTM module has 8 "generic" IO channels in output
                expected_channels += SEQUENCERS_IN_MODULE[module]

            channels, sequencers = self.cluster.get_module_channels(module)
            self.assertEqual(expected_channels, len(channels))
            self.assertEqual(expected_sequencers, len(sequencers))


class SequencerObject:

    parameters = IO_CHANNEL_CONFIG


class ValString(str):
    @property
    def value(self):
        return str(self)


class QcodesClusterTestCase(unittest.TestCase):
    """Test SCPI cluster instance methods."""

    def _add_is_functions_to_module(self, mod, mod_e):
        types = ["mm", "qcm", "qrm", "qtm", "rf"]
        for mod_type in types:
            setattr(mod, f"is_{mod_type}_type", lambda: mod_type.upper() in mod_e)

        return mod

    def setUp(self) -> None:
        self._qblox_instruments_patch = patch("qmi.instruments.qblox.cluster.qblox_instruments", unittest.mock.Mock())
        self._qblox_instruments_patch.start()
        self.addCleanup(self._qblox_instruments_patch.stop)
        self._scpi_cluster_patch = patch("qmi.instruments.qblox.cluster.ScpiCluster", ScpiClusterStub)
        self._scpi_cluster_patch.start()
        self.addCleanup(self._scpi_cluster_patch.stop)
        with patch("qmi.instruments.qblox.cluster.Cluster") as cluster_patch:
            name, ip = "skippy", "123.45.67.89"
            qmi.instruments.qblox.cluster.DEBUG_LEVEL = 2  # Set to 2 to avoid useless error checks
            _ctx = QMI_Context("cluster_test")
            retval = unittest.mock.MagicMock()
            retval.instrument_type = TypeHandle_QbloxModule("MM", False, 0).instrument_type
            retval._type_handle = self._add_is_functions_to_module(unittest.mock.MagicMock("Cluster_MM"), "MM")
            retval_modules = []
            for e, mod in modules.items():
                model = mod["model"][8:] + "-RF" if mod["is_rf"] else mod["model"][8:]
                is_rf = True if "RF" in model else False
                inst_mod = TypeHandle_QbloxModule(model, is_rf, e)
                inst_mod.present = lambda : True
                inst_mod.module_type = ValString(model)
                inst_mod.is_mm_type = "MM" in model
                inst_mod.is_qcm_type = "QCM" in model
                inst_mod.is_qrm_type = "QRM" in model
                inst_mod.is_qtm_type = model == "QTM"
                retval_modules.append(inst_mod)

            retval.modules = retval_modules[1:] + [retval_modules.pop(0)]
            cluster_patch.return_value = retval
            self.cluster = Qblox_QcodesCluster(_ctx, name, ip)
            self.cluster.open()

    def tearDown(self) -> None:
        self.cluster.close()

    def test_get_module(self):
        mm = self.cluster.get_module("MM")
        self.assertTrue(mm.is_mm_type)
        self.assertFalse(mm.is_qcm_type)
        self.assertFalse(mm.is_qrm_type)
        self.assertFalse(mm.is_qtm_type)
        self.assertFalse(mm.is_rf_type)

        qcm = self.cluster.get_module("QCM")
        self.assertEqual("QCM", qcm.name)
        self.assertTrue(qcm.is_qcm_type)
        self.assertFalse(qcm.is_qrm_type)
        self.assertFalse(qcm.is_qtm_type)
        self.assertFalse(qcm.is_rf_type)

        qcm_rf = self.cluster.get_module("QCM-RF")
        self.assertEqual("QCM-RF", qcm_rf.name)
        self.assertTrue(qcm_rf.is_qcm_type)
        self.assertFalse(qcm_rf.is_qrm_type)
        self.assertFalse(qcm_rf.is_qtm_type)
        self.assertTrue(qcm_rf.is_rf_type)

        qrm = self.cluster.get_module("QRM")
        self.assertEqual("QRM", qrm.name)
        self.assertFalse(qrm.is_qcm_type)
        self.assertTrue(qrm.is_qrm_type)
        self.assertFalse(qrm.is_qtm_type)
        self.assertFalse(qrm.is_rf_type)

        qrm_rf = self.cluster.get_module("QRM-RF")
        self.assertEqual("QRM-RF", qrm_rf.name)
        self.assertFalse(qrm_rf.is_qcm_type)
        self.assertTrue(qrm_rf.is_qrm_type)
        self.assertFalse(qrm_rf.is_qtm_type)
        self.assertTrue(qrm_rf.is_rf_type)

        qtm = self.cluster.get_module("QTM")
        self.assertEqual("QTM", qtm.name)
        self.assertFalse(qtm.is_qcm_type)
        self.assertFalse(qtm.is_qrm_type)
        self.assertTrue(qtm.is_qtm_type)
        self.assertFalse(qtm.is_rf_type)

    def test_get_module_func_refs(self):
        qcm = self.cluster.get_module_func_refs("QCM")
        self.assertTrue(qcm["is_qcm_type"]())
        self.assertFalse(qcm["is_qrm_type"]())
        self.assertFalse(qcm["is_qtm_type"]())
        self.assertFalse(qcm["is_rf_type"]())

        qcm_rf = self.cluster.get_module_func_refs("QCM-RF")
        self.assertTrue(qcm_rf["is_qcm_type"]())
        self.assertFalse(qcm_rf["is_qrm_type"]())
        self.assertFalse(qcm_rf["is_qtm_type"]())
        self.assertTrue(qcm_rf["is_rf_type"]())

        qrm = self.cluster.get_module_func_refs("QRM")
        self.assertFalse(qrm["is_qcm_type"]())
        self.assertTrue(qrm["is_qrm_type"]())
        self.assertFalse(qrm["is_qtm_type"]())
        self.assertFalse(qrm["is_rf_type"]())

        qrm_rf = self.cluster.get_module_func_refs("QRM-RF")
        self.assertFalse(qrm_rf["is_qcm_type"]())
        self.assertTrue(qrm_rf["is_qrm_type"]())
        self.assertFalse(qrm_rf["is_qtm_type"]())
        self.assertTrue(qrm_rf["is_rf_type"]())

        qtm = self.cluster.get_module_func_refs("QTM")
        self.assertFalse(qtm["is_qcm_type"]())
        self.assertFalse(qtm["is_qrm_type"]())
        self.assertTrue(qtm["is_qtm_type"]())
        self.assertFalse(qtm["is_rf_type"]())

    def test_get_module_with_slot_and_errors(self):
        self.assertTrue(self.cluster.get_module("MM", slot_no=0).is_mm_type)
        self.assertEqual("QCM", self.cluster.get_module("QCM", slot_no=1).name)
        self.assertEqual("QRM-RF", self.cluster.get_module("QRM-RF", slot_no=4).name)

        with self.assertRaisesRegex(ValueError, "management module"):
            self.cluster.get_module("MM", slot_no=1)
        with self.assertRaisesRegex(ValueError, "Module QRC not found"):
            self.cluster.get_module("QRC")
        with self.assertRaisesRegex(ValueError, "slot position 2"):
            self.cluster.get_module_channels("QCM", slot_no=2)
        with self.assertRaisesRegex(ValueError, "not found on cluster"):
            self.cluster.get_module_channels("QRC")
        with self.assertRaisesRegex(ValueError, "slot 0"):
            self.cluster.get_module_channels("QCM", slot_no=0)

    def test_get_module_func_refs_does_not_mutate_module_type_flags(self):
        module = self.cluster.get_module("QCM")
        self.assertIs(module.is_qrm_type, False)

        refs = self.cluster.get_module_func_refs("QCM")

        self.assertIs(module.is_qrm_type, False)
        self.assertIs(refs["is_qrm_type"](), False)
        self.assertTrue(callable(refs["is_qrm_type"]))

    def test_get_module_func_refs_for_mm_and_slot(self):
        with self.assertRaises(AttributeError):
            self.cluster.get_module_func_refs("MM")

        qrm_rf_refs = self.cluster.get_module_func_refs("QRM-RF", slot_no=4)
        self.assertTrue(qrm_rf_refs["is_qrm_type"]())
        self.assertTrue(qrm_rf_refs["is_rf_type"]())
        self.assertIn("_check_error_queue", qrm_rf_refs)

    def test_check_error_queue_no_errors_and_raises(self):
        self.cluster.cluster._debug.value = 1
        self.cluster.cluster._read.side_effect = ["0"]
        self.cluster._check_error_queue()
        self.cluster.cluster._read.assert_called_once_with("SYSTem:ERRor:COUNt?")

        self.cluster.cluster._read.reset_mock()
        self.cluster.cluster._read.side_effect = ["1", "100,first error", "0"]
        with self.assertRaisesRegex(RuntimeError, "first error"):
            self.cluster._check_error_queue()

        self.cluster.cluster._read.reset_mock()
        self.cluster.cluster._read.side_effect = ["0"]
        with self.assertRaisesRegex(ValueError, "bad value"):
            self.cluster._check_error_queue(ValueError("bad value"))

    def test_qcodes_channel_filters_and_runtime_fallback(self):
        qcm = self.cluster._modules["1"]["QCM"]
        qcm.sequencers = [unittest.mock.Mock(parameters=IO_CHANNEL_CONFIG, sync_en=False) for _ in range(2)]
        for sequencer in qcm.sequencers:
            sequencer._get_sequencer_config.return_value = SequencerObject
        qcm._iter_connections = unittest.mock.Mock(return_value=[
            [0, "I", "dac0"],
            [0, "Q", "dac1"],
            [1, "I", "dac2"],
            [1, "Q", "dac3"],
        ])

        dac_channels, sequencers = self.cluster.get_module_channels("QCM", slot_no=1, channel_type=2)
        self.assertEqual(["dac0_I0", "dac1_Q0", "dac2_I1", "dac3_Q1"], list(dac_channels))
        self.assertEqual(["sequencer0", "sequencer1"], list(sequencers))

        marker_channels, _ = self.cluster.get_module_channels("QCM", slot_no=1, channel_type=3)
        self.assertEqual(["DO0_0", "DO1_0", "DO2_1", "DO3_1"], list(marker_channels))

        qtm = self.cluster._modules["5"]["QTM"]
        qtm.io_channels = []
        qtm._iter_connections = unittest.mock.Mock(side_effect=RuntimeError("no seq chan"))

        class SequencerStub:
            sync_en = True

            def _get_sequencer_config(self):
                return SequencerObject

            def __getattr__(self, name):
                if name.endswith("_count_threshold"):
                    return 12
                if name.endswith("_threshold_invert"):
                    return False
                raise AttributeError(name)

        qtm.sequencers = [SequencerStub(), SequencerStub()]
        fallback_channels, fallback_sequencers = self.cluster.get_module_channels("QTM", slot_no=5, channel_type=3)
        self.assertEqual(8, len(fallback_channels))
        self.assertEqual(["sequencer0", "sequencer1"], list(fallback_sequencers))

    def test_get_channels(self):
        """Test getting all channels and sequencers out from the modules"""
        # NO channels for "MM".
        with self.assertRaises(ValueError):
            self.cluster.get_module_channels("MM")

        for e, module in enumerate(["QCM", "QCM-RF", "QRM", "QRM-RF", "QTM"], start=1):
            # Arrange
            expected_sequencers = SEQUENCERS_IN_MODULE[module]
            if module != "QTM":
                expected_channels = (
                    AO_IN_MODULE[module]
                    + DIGITAL_MARKERS_IN_MODULE[module]
                    + AI_IN_MODULE[module]
                ) * SEQUENCERS_IN_MODULE[module]
            if module == "QTM":  # The QTM module has 8 "generic" IO channels in output
                expected_channels = SEQUENCERS_IN_MODULE[module]

            module_mock = self.cluster._modules[str(e)][module]
            module_mock.sequencers = []
            num_seq = 6 if module != "QTM" else 8
            module_mock.io_channels = [f"IO{i}" for i in range(num_seq)] if module == "QTM" else []
            sequencers_mock = unittest.mock.Mock()
            sequencers_mock._get_sequencer_config = unittest.mock.Mock(return_value=SequencerObject)
            for _ in range(num_seq):
                module_mock.sequencers.append(sequencers_mock)

            side_effects = []
            for seq in range(num_seq):
                if "QRM" not in module or module != "QTM":
                    channel_map = [(0, "IQ")] if "RF" in module else [(0, "I"), (1, "Q")]
                    for path, chn in channel_map:
                        channels = [0, 2] if not path else [1, 3]
                        for channel in channels:
                            side_effects.append([seq, chn, f"dac{channel}"])
                elif module != "QTM":
                    for path, chn in [(0, "acq_I"), (1, "acq_Q")]:
                        channels = [0, 2] if not path else [1, 3]
                        for channel in channels:
                            side_effects.append([seq, chn, f"adc{channel}"])
                else:
                    for channel in range(8):
                        side_effects.append([channel, "IQ", f"io{channel}"])

            module_mock._iter_connections = unittest.mock.Mock(side_effect=[side_effects])

            # Act
            channels, sequencers = self.cluster.get_module_channels(module)
            # Assert
            self.assertEqual(expected_channels, len(channels), f"failed for {module}")
            self.assertEqual(expected_sequencers, len(sequencers))


if __name__ == "__main__":
    unittest.main()
