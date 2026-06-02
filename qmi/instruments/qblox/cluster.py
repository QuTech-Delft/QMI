# mypy: disable-error-code=import-untyped
# mypy: disable-error-code=import-not-found
"""This module is for Qblox cluster control. It requires qblox_instruments 1.1.0 or newer."""

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import logging
import sys
from functools import partial
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import qblox_instruments
    from qblox_instruments import Cluster
    from qblox_instruments.native import Cluster as NativeCluster
    from qblox_instruments.native.helpers import ChannelMapCache
    from qblox_instruments.qcodes_drivers.module import Module as QcodesModule
    from qblox_instruments.scpi.layers.cluster_mm_1_0 import Cluster as ScpiCluster
    from qblox_instruments.types import DebugLevel

else:
    qblox_instruments = None
    Cluster, NativeCluster, ScpiCluster = None, None, None
    ChannelMapCache, QcodesModule, DebugLevel = None, None, None

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method

_logger = logging.getLogger(__name__)

DEBUG_LEVEL: Any = None
_EXTRA_ATTRS = [
    "_get_sequencer_channel_map",
    "_get_sequencer_acq_channel_map",
    "_get_sequencer_state",
    "_set_sequencer_channel_map",
    "_set_sequencer_acq_channel_map",
    "_set_acq_acquisition_data",
    "_delete_awg_waveform",
    "_delete_acq_weight",
    "_delete_acq_acquisition",
    "_delete_acq_acquisition_data",
    "_add_acq_acquisition",
    "_add_awg_waveform",
    "_set_acq_acquisition_index",
    "_set_awg_waveform_data",
    "_set_awg_waveform_index",
]

# The amount of (external) trigger addresses in a cluster
EXT_TRIGGERS_IN_CLUSTER = 15
# Module configuration constants:
# AO_IN_MODULE:              Analog output channels in modules with value range -1V...+1V.
# AI_IN_MODULE:              Analog output channels in modules with value range -1V...+1V.
# DIGITAL_MARKERS_IN_MODULE: Digital marker channels in modules, with values 'low' and 'high' (3.3V LVTTL).
# SEQUENCERS_IN_MODULE:      Number of sequencers available in module.
AO_IN_MODULE = {"QCM": 4, "QCM-RF": 2, "QRM": 2, "QRM-RF": 1, "QTM": 0, "MM": 0}
AI_IN_MODULE = {"QCM": 0, "QCM-RF": 0, "QRM": 2, "QRM-RF": 1, "QTM": 0, "MM": 0}
DIGITAL_MARKERS_IN_MODULE = {"QCM": 4, "QCM-RF": 2, "QRM": 4, "QRM-RF": 2, "QTM": 4, "MM": 0}
SEQUENCERS_IN_MODULE = {"QCM": 6, "QCM-RF": 6, "QRM": 6, "QRM-RF": 6, "QTM": 8, "MM": 0}
_get_required_qrm_qcm_attr_names: Callable[..., list[str]] | None = None
_get_required_qtm_attr_names: Callable[..., list[str]] | None = None


def _import_modules() -> None:
    """Import the vendor-provided Qblox modules.
    
    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global qblox_instruments, Cluster, NativeCluster, ScpiCluster, ChannelMapCache, QcodesModule, DebugLevel  # noqa: PLW0603
    global DEBUG_LEVEL, _get_required_qrm_qcm_attr_names, _get_required_qtm_attr_names  # noqa: PLW0603
    if qblox_instruments is None:
        import qblox_instruments
        from qblox_instruments import Cluster
        from qblox_instruments.native import Cluster as NativeCluster
        from qblox_instruments.native.helpers import ChannelMapCache
        from qblox_instruments.qcodes_drivers.module import Module as QcodesModule
        from qblox_instruments.scpi.layers.cluster_mm_1_0 import Cluster as ScpiCluster
        from qblox_instruments.types import DebugLevel

        assert qblox_instruments is not None
        if tuple(map(int, qblox_instruments.__version__.split("."))) < tuple(map(int, "0.17.0".split("."))):
            raise RuntimeError("qblox_instruments version 0.17.0 or newer is needed.")

        DEBUG_LEVEL = DebugLevel.MINIMAL_CHECK
        _get_required_qrm_qcm_attr_names = QcodesModule._get_required_parent_qrx_qcm_attr_names
        _get_required_qtm_attr_names = QcodesModule._get_required_parent_qtm_attr_names


class _QbloxModule:
    """This class is for creating an 'instrument' instance which is used e.g. when creating a
    `ChannelMapCache` instance. It should have all the necessary `._is_xxx_type(slot)` methods,
    and module-specific set of function references.
    """

    def __init__(self, module: str, func_refs: dict[str, Callable]) -> None:
        """Initialize a module class instance.

        Parameters:
            module:    The module name, like "QCM".
            func_refs: The function reference dictionary for all calls.
        """
        self._module = module
        setattr(self, module.replace("-", "_"), func_refs)
        # We need to set some call specifically in the module level
        for key, func in func_refs.items():
            if key.startswith("is_") and hasattr(self, key):
                setattr(self, key, getattr(self, key))

            if module not in ["MM", "CMM"]:
                if "channel_map" in key:
                    setattr(self, key, func)

    def __str__(self) -> str:
        return self._module

    def is_mm_type(self) -> bool:
        if "MM" in str(self):
            return True

        return False

    def is_qcm_type(self) -> bool:
        """Check if a module in given slot is of type QCM.

        Returns:
            boolean: True if module is of type QCM, QCM-RF. Otherwise False.
        """
        if "QCM" in str(self):
            return True

        return False

    def is_qrm_type(self) -> bool:
        """Check if a module in given slot is of type QRM.

        Returns:
            boolean: True if module is of type QRM, QRM-RF. Otherwise False.
        """
        if "QRM" in str(self):
            return True

        return False

    def is_qrc_type(self) -> bool:
        """Check if a module in given slot is of type QRC.

        Returns:
            boolean: True if module is of type QCM. Otherwise False.
        """
        if "QRC" in str(self):
            return True

        return False

    def is_qtm_type(self) -> bool:
        """Check if a module in given slot is of type QTM.

        Returns:
            boolean: True if module is of type QTM. Otherwise False.
        """
        if "QTM" in str(self):
            return True

        return False

    def is_rf_type(self) -> bool:
        """Check if a module in given slot is of type RF.

        Returns:
            boolean: True if module is of type RF. Otherwise False.
        """
        if "-RF" in str(self):
            return True

        return False


class Qblox_ClusterBase(QMI_Instrument):
    """Base class for Qblox cluster versions based on 'native' or Qcodes-based implementations.
    
    Attributes:
        DEBUG_LEVEL: The debug level to use while using Qblox. If the user wants to change the debug level in an
                     interactive session, the cluster must be closed first, then the DEBUG_LEVEL RPC constant can
                     be changed, and the cluster instance re-opened.
    """
    _rpc_constants = ["DEBUG_LEVEL"]

    DEBUG_LEVEL = DEBUG_LEVEL

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        cluster_ip: str,
        port: int | None = None,
        dummy_cfg: dict | None = None,
    ) -> None:
        super().__init__(context, name)

        _logger.info("[%s] Creating Qblox Cluster instance, with device ip:port=%s:%i", name, cluster_ip, port)
        self.cluster_ip = cluster_ip
        self.port = port
        self.dummy_cfg = dummy_cfg
        self._cluster: Any | None = None
        self._instrument_type: str = ""
        self._modules: dict[str, Any] = {}
        self.cluster_funcs: dict[str, Callable] = {}

        _import_modules()

    @property
    def cluster(self) -> Any:
        """Return the underlying vendor cluster instance."""
        assert self._cluster is not None
        return self._cluster

    @rpc_method
    def open(self) -> None:
        """Mark the cluster driver as open after the child class has connected and discovered modules."""
        super().open()

    @rpc_method
    def close(self) -> None:
        try:
            self.cluster.stop_sequencer()
        except RuntimeError:
            _logger.exception("[%s] Got an error while stopping all sequencers: ", self._name)

        self.cluster.clear_sequencer_flags()
        super().close()

    @rpc_method
    def get_name(self) -> str:
        return self._name

    @rpc_method
    def get_funcs(self) -> dict[str, Callable]:
        """Return function references for direct cluster-level control."""
        return self.cluster_funcs

    @rpc_method
    def get_system_state(self) -> str:
        """Get the system state from system status. Possible states are:
        BOOTING = "System is booting."
        OKAY = "System is okay."
        RESOLVED = "An error indicated by the flags occured [sic], but has been resolved."
        ERROR = "An error indicated by the flags is occuring [sic]."
        CRIT_ERROR = "A critical error indicated by the flags is occurring"

        Returns:
            status.name: The system status name string from SystemStatuses Enum.
        """
        full_status = self.cluster.get_system_status()
        _logger.debug(f"System status: {full_status}")
        return full_status.status.name

    @rpc_method
    def reset_cluster(self) -> None:
        """Reset the cluster."""
        _logger.info("Resetting the cluster.")
        self.cluster._reset()

    @rpc_method
    def reset_module(self, slot_no: int) -> None:
        """Reset the cluster module in the specified slot."""
        raise NotImplementedError("This function is not implemented in the base class.")

    @rpc_method
    def get_module(self, module_type: str, slot_no: int | None = None) -> Any:
        """Find and return requested module instance, from module type, possibly on specified slot, from cluster.

        Parameters:
            module_type: A string describing module type, e.g. "QRM", "QCM-RF", etc.
            slot_no:     An optional expected slot position input. If `None`, first matching module is returned.

        Raises:
            ValueError: If no module with given type or in given slot is present.

        Returns:
            module: The found matching module (or cluster) instance.
        """
        raise NotImplementedError("This function is not implemented in the base class.")

    @rpc_method
    def get_module_func_refs(self, module_type: str, slot_no: int | None = None) -> dict[str, Callable]:
        """Find and return requested module's function reference dictionary, for a module type,
        possibly on specified slot, from cluster.

        Parameters:
            module_type: A string describing module type, e.g. "QRM", "QCM-RF", etc.
            slot_no:     An optional expected slot position input. If `None`, first matching module is returned.

        Returns:
            module_func_refs: The found matching module's function references dictionary.
        """
        raise NotImplementedError("This function is not implemented in the base class.")

    @rpc_method
    def get_module_channels(self, module_type: str, slot_no: int | None = None, channel_type: int = 0) -> Any:
        """Find and return requested channel configurations, all or of a specific type, on a module, on first matching
        or specified slot, from cluster.

        Always also includes full sequencer configurations -per module- in the result.

        The Qblox channels are mapped by definition such that (when connecting):
          - Output (DAC) channels in a QCM module are either 'I' or 'Q' type.
          - Input (ADC) channels in QRM module are either 'acq_I' or 'acq_Q' type.
          - QxM-RF modules connect_out parameter controls the configuration for two DACs, hardwired to I and Q input
            of the RF mixer on the front end, so channels are always a mixed 'IQ' type.
          - Marker channels are the type of digital output (DO). Typically, these are simple 'low-or-high' channels.
          - QTM has DI/O channels, fixed per sequencer.
        On top, the channels can be set as 'off' (disconnect) as well.

        Parameters:
            module_type:  A string describing module type, e.g. "QRM", "QCM-RF", etc.
            slot_no:      An optional expected slot position input. If `None`, first matching module is returned.
            channel_type: 0 - all channels (default), 1 - analog input channels (adc), 2 - analog output channels (dac),
                          3 - marker channels, 4 - IO channels (QTM only).

        Raises:
            ValueError: If no module with given type or in given slot is present.

        Returns:
            channels:   The found matching module channel sequencer configuration(s).
            sequencers: The simplified list of sequencer configurations of the module.
        """
        raise NotImplementedError("This function is not implemented in the base class.")

    @rpc_method
    def get_module_channel_map_cache(self, module_type: str, slot_no: int | None = None) -> ChannelMapCache:
        """Get the module's cached channel map.

        The 'ChannelMapCache' has several useful functions on (dis)connecting channels, clearing them, validity and
        availability checks etc.

        Parameters:
            module_type: A string describing module type, e.g. "QRM", "QCM-RF", etc.
            slot_no:     An optional expected slot position input. If `None`, first matching module is returned.
        """
        module = self.get_module(module_type, slot_no)
        return ChannelMapCache(module, slot_no)

    @rpc_method
    def reset_trigger_monitor_count(self, trigger_index: int) -> None:
        """Reset external trigger monitor count on given trigger.

        Parameters:
            trigger_index: The trigger number.

        Raises:
            ValueError: If the trigger index number is not valid.
        """
        if trigger_index not in range(1, EXT_TRIGGERS_IN_CLUSTER + 1):
            raise ValueError(f"Invalid trigger number {trigger_index}")

        self.cluster.reset_trigger_monitor_count(trigger_index)

    @rpc_method
    def get_trigger_monitor_count(self, trigger_index: int) -> int:
        """Get external trigger monitor count on given trigger.

        Parameters:
            trigger_index: The trigger number.

        Returns:
            count: The trigger monitor count of the given trigger.

        Raises:
            ValueError: If the trigger index number is not valid.
        """
        if trigger_index not in range(1, EXT_TRIGGERS_IN_CLUSTER + 1):
            raise ValueError(f"Invalid trigger number {trigger_index}")

        return self.cluster.get_trigger_monitor_count(trigger_index)

    @rpc_method
    def get_trigger_monitor_latest(self) -> int:
        """Get the latest trigger monitor count index, i.e. which trigger was last triggered.

        Returns:
            trigger_index: The trigger number.
        """
        return self.cluster.get_trigger_monitor_latest()


class Qblox_NativeCluster(Qblox_ClusterBase):
    """Class to control Qblox _native_ Cluster instrument with various devices."""

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        cluster_ip: str,
        port: int | None = None,
        dummy_cfg: dict | None = None,
    ) -> None:
        """Initialize Qblox cluster and collect information about the modules present.

        Parameters:
            context:    QMI context instance to create this driver in.
            name:       Name identifier for the cluster and also for QMI context instrument name.
            cluster_ip: The IP address string of the cluster.
            port:       Optional IP port number if non-default port is to be used.
            dummy_cfg:  Optional input for giving a dummy Qblox configuration dictionary. Useful for dry run testing.
        """
        super().__init__(context, name, cluster_ip, port, dummy_cfg)
        self._cluster: NativeCluster | None = None
        self._modules: dict[str, _QbloxModule] = {}

    @property
    def cluster(self) -> NativeCluster:
        assert self._cluster is not None
        return self._cluster

    @cluster.setter
    def cluster(self, cluster: NativeCluster) -> None:
        assert isinstance(cluster, NativeCluster)
        self._cluster = cluster

    def _add_cluster_funcs(self) -> None:
        """Add more functions to 'native' Cluster, as it does not have that many implemented."""
        self.cluster_funcs["reset_trigger_monitor_count"] = partial(
            getattr(self.cluster, "reset_trigger_monitor_count"), self.cluster
        )
        self.cluster_funcs["get_trigger_monitor_count"] = partial(
            getattr(self.cluster, "get_trigger_monitor_count"), self.cluster
        )
        self.cluster_funcs["get_trigger_monitor_latest"] = partial(
            getattr(self.cluster, "get_trigger_monitor_latest"), self.cluster
        )
        # self.cluster is the first "partial" parameter to fill in the 'self'.
        for x in range(4):
            self.cluster_funcs[f"_set_mrk_inv_en_{x}"] = partial(
                getattr(self.cluster, f"_set_mrk_inv_en_{x}"), self.cluster
            )
            self.cluster_funcs[f"_get_mrk_inv_en_{x}"] = partial(
                getattr(self.cluster, f"_get_mrk_inv_en_{x}"), self.cluster
            )

        # Add type handles as callables
        for type_handle, value in self.cluster._type_handle.__dict__.items():
            if type_handle.startswith("_is"):
                # As 'value' gets overridden in memory for the lambda function, do like this:
                if value:
                    self.cluster_funcs[type_handle.lstrip("_")] = lambda: True
                else:
                    self.cluster_funcs[type_handle.lstrip("_")] = lambda: False

    def _add_module_funcs(self, v: dict[str, Callable], module_type: str) -> None:
        """Add more functions to 'native' Cluster, specific for a module type."""
        # Reassign 'arm_sequencer', 'start_sequencer' and 'stop_sequencer' directly to SCPI calls
        v["arm_sequencer"] = partial(getattr(ScpiCluster, "_arm_sequencer"), self.cluster)
        v["start_sequencer"] = partial(getattr(ScpiCluster, "_start_sequencer"), self.cluster)
        v["stop_sequencer"] = partial(getattr(ScpiCluster, "_stop_sequencer"), self.cluster)
        for o in range(AO_IN_MODULE[module_type]):
            for x in range(4):
                v[f"_out{o}_exp{x}_config"] = partial(
                    getattr(NativeCluster, "_set_pre_distortion_config"), self.cluster
                )

            v[f"_out{o}_fir_config"] = partial(getattr(NativeCluster, "_set_pre_distortion_config"), self.cluster)

    @rpc_method
    def open(self) -> None:
        # Connect to the device cluster
        self._cluster = NativeCluster(
            identifier=self.cluster_ip, port=self.port, debug=self.DEBUG_LEVEL, dummy_cfg=self.dummy_cfg
        )
        self._instrument_type = self.cluster.instrument_type.value  # Should return string "MM"
        # dict {"<slot#>": {"<instrument_type>: _QbloxModule}, containing the modules.
        # Startup module dictionary with MM; {"<slot#>": {"<instrument_type>: _QbloxModule},
        # to contain all available modules.
        idn = self.cluster._get_idn()
        _, model, _, _ = idn.split(",")
        self._modules = {"0": _QbloxModule(model, self.cluster_funcs)}
        for k, v in self.cluster._mod_handles.items():
            type_handle_obj = v["type_handle"]
            module_type = type_handle_obj.instrument_type.value
            # Check if it is also "RF"
            if type_handle_obj.is_rf_type:
                module_type = module_type + "-RF"

            # Add type handles as callables
            for type_handle, value in type_handle_obj.__dict__.items():
                if type_handle.startswith("_is"):
                    # As 'value' gets overridden in memory for the lambda function, do like this:
                    if value:
                        v[type_handle.lstrip("_")] = lambda: True
                    else:
                        v[type_handle.lstrip("_")] = lambda: False

            extra_attrs = _EXTRA_ATTRS.copy()
            # With the new module version we need to rebrand the calls to have correct inputs
            if module_type in ["QCM", "QRM", "QCM-RF", "QRM-RF"]:
                num_lo = 2  # For QRM-RF it is 1, but the output is on path 1 so we need to make both, see the call...
                num_in_channels = AI_IN_MODULE[module_type]
                num_out_channels = AO_IN_MODULE[module_type]
                num_markers = DIGITAL_MARKERS_IN_MODULE[module_type]
                assert _get_required_qrm_qcm_attr_names is not None
                extra_attrs.extend(
                    _get_required_qrm_qcm_attr_names(num_lo, num_in_channels, num_out_channels, num_markers)
                )
            elif module_type in ["QTM"]:
                assert _get_required_qtm_attr_names is not None
                extra_attrs.extend(_get_required_qtm_attr_names())

            for attr_name in extra_attrs:
                for cluster in NativeCluster, ScpiCluster:
                    if hasattr(cluster, attr_name):
                        signature = str(inspect.signature(getattr(cluster, attr_name)))
                        if "slot: int" in signature:
                            v[attr_name] = partial(getattr(cluster, attr_name), self.cluster, int(k))
                        else:
                            v[attr_name] = getattr(cluster, attr_name)

                        break

            self._add_module_funcs(v, module_type)
            self._modules[k] = _QbloxModule(module_type, v)
            # Add type handles as callables
            for type_handle, value in type_handle_obj.__dict__.items():
                if type_handle.startswith("_is"):
                    # As 'value' gets overridden in memory for the lambda function, do like this:
                    if value:
                        setattr(self._modules[k], type_handle, lambda slot: True)
                    else:
                        setattr(self._modules[k], type_handle, lambda slot: False)

        # Add direct calls to ScpiCluster calls not implemented in 'native' Cluster
        self._add_cluster_funcs()
        super().open()

    @rpc_method
    def reset_module(self, slot_no: int) -> None:
        _logger.info(f"Resetting cluster module in slot {slot_no}.")
        self.cluster._slot_reset()

    @rpc_method
    def get_module(self, module_type: str, slot_no: int | None = None) -> NativeCluster | _QbloxModule:
        module_type = module_type.upper()
        if module_type == "MM" and (slot_no == 0 or slot_no is None):
            # The Cluster management module is always at slot 0
            return self.cluster

        if module_type == "MM" and slot_no != 0:
            raise ValueError("The Cluster management module is always at slot 0!")

        # Find a module in cluster. These possibly are in numerical order, but loop anyhow.
        # dict entry key="<slot#>", value={"<instrument_type>", func_refs": _QbloxModule}
        for slot, module in self._modules.items():
            # Then check if slot_no was given and matches. No need to go on if not.
            if slot_no is not None and int(slot) != slot_no:
                continue

            if str(module) == module_type:
                # Just double check module type before returning
                if (
                    module_type == "QCM"
                    and module.is_qcm_type()
                    or (module_type == "QRM" and module.is_qrm_type())
                    or (module_type == "QCM-RF" and module.is_qcm_type() and module.is_rf_type())
                    or (module_type == "QRM-RF" and module.is_qrm_type() and module.is_rf_type())
                    or (module_type == "QTM" and module.is_qtm_type())
                ):
                    return module

        if slot_no:
            raise ValueError(f"Module {module_type} not found on slot position {slot_no}.")

        raise ValueError(f"Module {module_type} not found.")

    @rpc_method
    def get_module_func_refs(self, module_type: str, slot_no: int | None = None) -> dict[str, Callable]:
        module_type = module_type.upper()
        if module_type == "MM" and (slot_no == 0 or slot_no is None):
            # The Cluster management module is always at slot 0
            return self.cluster_funcs

        module = self.get_module(module_type, slot_no)
        return getattr(module, module_type.replace("-", "_"))

    @rpc_method
    def get_module_channels(self, module_type: str, slot_no: int | None = None, channel_type: int = 0) -> Any:
        module_type = module_type.upper()
        sequencers: dict[str, Any] = {}
        channels: dict[str, Any] = {}
        module_func_refs = self.get_module_func_refs(module_type, slot_no)
        # The channels definition in Qblox is done through the sequencers, and not the other way around. So, for our
        # definition of control per channel we need to first map out the sequencers.
        for sequencer in range(SEQUENCERS_IN_MODULE[module_type]):
            try:
                sequencer_config = module_func_refs["_get_sequencer_config"](sequencer)
                if channel_type in [0, 1] and AI_IN_MODULE[module_type] > 0:
                    # Get 'ADC' input channels if present in module
                    sequencer_channel_map = module_func_refs["_get_sequencer_acq_channel_map"](sequencer)
                    if "RF" in module_type.upper():
                        for channel in [ch for map in sequencer_channel_map for ch in map]:
                            channels[f"adc{channel}_IQ{sequencer}"] = sequencer_config["acq"]

                    else:
                        for channel in sequencer_channel_map[0]:
                            channels[f"adc{channel}_acq_I{sequencer}"] = sequencer_config["awg"]

                        for channel in sequencer_channel_map[1]:
                            channels[f"adc{channel}_acq_Q{sequencer}"] = sequencer_config["awg"]

                if channel_type in [0, 2] and AO_IN_MODULE[module_type] > 0:
                    sequencer_channel_map = module_func_refs["_get_sequencer_channel_map"](sequencer)
                    # The first list defines 'I' type channels, the second 'Q' type
                    for channel in sequencer_channel_map[0]:
                        channels[f"dac{channel}_I{sequencer}"] = sequencer_config["awg"]  # TODO: Is this always valid?

                    for channel in sequencer_channel_map[1]:
                        channels[f"dac{channel}_Q{sequencer}"] = sequencer_config["awg"]  # TODO: Is this always valid?

                if channel_type in [0, 3] and DIGITAL_MARKERS_IN_MODULE[module_type] > 0:
                    # For QCM-RF channels 0, 2 are 'daci_Is' channels and channels 1, 3 are 'dacq_Qs` channels
                    for channel in range(DIGITAL_MARKERS_IN_MODULE[module_type]):
                        channels[f"DO{channel}_{sequencer}"] = sequencer_config["seq_proc"]

            except RuntimeError as rt_err:
                # This should always work, so except properly if something fails
                _logger.exception("Module %s failed to map sequencer %i." % module_type, sequencer, exc_info=rt_err)
                raise Exception(f"Module {module_type} failed to map sequencer {sequencer}.") from rt_err

            sequencers[f"sequencer{sequencer}"] = sequencer_config
            if channel_type in [0, 4] and module_type.upper() == "QTM":
                # QTM has IOx channels, where x is both the channel and sequencer number.
                channels[f"IO{sequencer}"] = module_func_refs["_get_io_channel_config"](sequencer)

        return channels, sequencers


@dataclass()
class TriggerThresholdConfig:
    """Dataclass for holding marker channel trigger threshold parameters."""

    threshold: Any
    invert: Any


class Qblox_QcodesCluster(Qblox_ClusterBase):
    """Class to control Qblox Cluster instrument with various devices through QCoDeS."""

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        cluster_ip: str,
        port: int | None = None,
        dummy_cfg: dict | None = None,
    ) -> None:
        super().__init__(context, name, cluster_ip, port, dummy_cfg)
        self._cluster: Cluster | None = None
        self._modules: dict[str, dict[str, dict[str, Callable]]] = {}

    @property
    def cluster(self) -> Cluster:
        assert self._cluster is not None
        return self._cluster

    @cluster.setter
    def cluster(self, cluster: Cluster) -> None:
        assert isinstance(cluster, Cluster)
        self._cluster = cluster

    def _check_error_queue(self, err: Exception | None = None) -> None:
        """This function does not work correctly when obtained from ScpiCluster. Therefore a modified copy is used.
        Check system error for errors. Empties and prints the complete error queue.

        Parameters:
            err:          Exception type to re-raise.

        Raises:
            Exception:    An exception was passed as input argument.
            RuntimeError: An error occurred in system run-time.
        """
        if self.cluster._debug.value <= 1:
            errors = [str(err)] if err is not None else []
            while int(self.cluster._read("SYSTem:ERRor:COUNt?")) != 0:
                errors.append(",".join(self.cluster._read("SYSTem:ERRor:NEXT?").split(",")[1:]))

            if len(errors) > 0:
                if err is not None:
                    err_type = type(err)
                else:
                    err_type = RuntimeError
                raise err_type("\n".join(errors)).with_traceback(sys.exc_info()[2]) from None

    def _add_type_check_calls(self, module: Any) -> Any:
        """Add `_is_xxx_type(slot)` calls into the module."""
        if hasattr(module, "is_mm_type"):
            setattr(module, "_is_mm_type", lambda slot: module.is_mm_type)

        setattr(module, "_is_qcm_type", lambda slot: module.is_qcm_type)
        setattr(module, "_is_qrm_type", lambda slot: module.is_qrm_type)
        setattr(module, "_is_qrc_type", lambda slot: module.is_qrc_type)
        setattr(module, "_is_qtm_type", lambda slot: module.is_qtm_type)
        setattr(module, "_is_rf_type", lambda slot: module.is_rf_type)

        return module

    def _add_sequencer_and_acquisition_calls(self, module: Any) -> Any:
        extra_attrs = _EXTRA_ATTRS.copy()
        # With the new module version we need to rebrand the calls to have correct inputs
        for attr_name in extra_attrs:
            if hasattr(NativeCluster, attr_name):
                try:
                    signature = str(inspect.signature(getattr(ScpiCluster, attr_name)))
                except AttributeError:
                    _logger.debug(f"ScpiCluster did not have attribute {attr_name}.")
                    continue

                if "slot: int" in signature:
                    if "channel_map" in attr_name:
                        setattr(module, attr_name, partial(getattr(ScpiCluster, attr_name), self.cluster))
                else:
                    setattr(module, attr_name, getattr(ScpiCluster, attr_name))

        # Reassign 'arm_sequencer', 'start_sequencer' and 'stop_sequencer' directly to SCPI write calls
        setattr(module, "arm_sequencer", partial(getattr(ScpiCluster, "_arm_sequencer"), self.cluster))
        setattr(module, "start_sequencer", partial(getattr(ScpiCluster, "_start_sequencer"), self.cluster))
        setattr(module, "stop_sequencer", partial(getattr(ScpiCluster, "_stop_sequencer"), self.cluster))

        return module

    def _make_func_refs_from_module(self, module: Any, slot: int) -> dict[str, Callable]:
        module_func_refs = module.__dict__.copy()
        for attr_name in ["_bin_block_write", "_write_bin", "_read", "_check_in_type"]:
            if hasattr(ScpiCluster, attr_name):
                partial_attr = partial(getattr(ScpiCluster, attr_name), module_func_refs)
                module_func_refs[attr_name] = partial_attr

        # TODO: Missing functions `_arm_scope_trigger` and `is_qdm_type`?
        module_func_refs["_check_error_queue"] = self._check_error_queue
        module_func_refs["_write"] = partial(getattr(ScpiCluster, "_write"), self.cluster)
        module_func_refs["_read_bin"] = partial(getattr(ScpiCluster, "_read_bin"), self.cluster)
        module_func_refs["_flush_line_end"] = partial(getattr(ScpiCluster, "_flush_line_end"), self.cluster)

        module_func_refs["is_qcm_type"] = lambda: module.is_qcm_type
        module_func_refs["is_qrm_type"] = lambda: module.is_qrm_type
        module_func_refs["is_qrc_type"] = lambda: module.is_qrc_type
        module_func_refs["is_qtm_type"] = lambda: module.is_qtm_type
        module_func_refs["is_rf_type"] = lambda: module.is_rf_type

        # Some extra attributes
        extra_attrs = _EXTRA_ATTRS.copy()
        # With the new module version we need to rebrand the calls to have correct inputs
        for attr_name in extra_attrs:
            if hasattr(NativeCluster, attr_name):
                signature = str(inspect.signature(getattr(NativeCluster, attr_name)))
                if "slot: int" in signature:
                    module_func_refs[attr_name] = partial(getattr(NativeCluster, attr_name), self.cluster, int(slot))
                else:
                    module_func_refs[attr_name] = getattr(NativeCluster, attr_name)

        module_func_refs["_debug"] = self.DEBUG_LEVEL

        # Add remaining module functions to the function references.
        for attr in dir(module):
            if isinstance(getattr(module, attr), partial) and attr not in module_func_refs:
                func = getattr(module, attr)
                module_func_refs[attr] = func

        return module_func_refs

    @rpc_method
    def open(self):
        # Connect to the device cluster
        self._cluster = Cluster(
            name=self._name, identifier=self.cluster_ip, port=self.port, debug=self.DEBUG_LEVEL, dummy_cfg=self.dummy_cfg
        )
        self._instrument_type = self.cluster.instrument_type.value  # Should return string "MM" for cluster
        self._modules["0"] = {self._instrument_type: self.cluster._type_handle}
        for name, member in inspect.getmembers(self.cluster._type_handle):
            if callable(member) and not name.startswith("__"):
                self.cluster_funcs[name] = member

        for module in self.cluster.modules:
            if module.present():
                slot = module.slot_idx
                self._modules[str(slot)] = {
                    self.cluster.modules[slot - 1].module_type.value: self.cluster.modules[slot - 1]
                }

        super().open()

    @rpc_method
    def get_module(self, module_type: str, slot_no: int | None = None) -> Any:
        if module_type == "MM" and (slot_no == 0 or slot_no is None):
            # The Cluster management module is always at slot 0
            module = self._add_type_check_calls(self._modules["0"]["MM"])
            return module

        if module_type == "MM" and slot_no != 0:
            raise ValueError("The Cluster management module is always at slot 0!")

        # The modules are enumerated (from 1), so if the number and type match, return immediately
        if slot_no is not None:
            module = list(self._modules[str(slot_no)].values())[0]
            module = self._add_type_check_calls(module)
            module = self._add_sequencer_and_acquisition_calls(module)
            return module

        # Otherwise, find the module in cluster
        for mod_dict in self._modules.values():
            if module_type == list(mod_dict.keys())[0]:
                module = list(mod_dict.values())[0]
                module = self._add_type_check_calls(module)
                module = self._add_sequencer_and_acquisition_calls(module)
                return module

        raise ValueError(f"Module {module_type} not found.")

    @rpc_method
    def get_module_func_refs(self, module_type: str, slot_no: int | None = None) -> dict[str, Callable]:
        module_type = module_type.upper()
        if module_type == "MM" and (slot_no == 0 or slot_no is None):
            # The Cluster management module is always at slot 0
            return self._add_type_check_calls(list(self._modules["0"].keys())[0])

        module = self.get_module(module_type, slot_no)
        return self._make_func_refs_from_module(module, module.slot_idx)

    @rpc_method
    def get_module_channels(self, module_type: str, slot_no: int | None = None, channel_type: int = 0) -> Any:
        module_type = module_type.upper()
        if module_type == "MM" or slot_no == 0:
            raise ValueError("The Cluster management module at slot 0 doesn't have channels!")

        # The modules are enumerated (from 1), so if the number and type match, return immediately
        if slot_no is not None:
            if module_type != list(self._modules[str(slot_no)].keys())[0]:
                raise ValueError(f"Module {module_type} not found on slot position {slot_no}.")

            module: QcodesModule = list(self._modules[str(slot_no)].values())[0]

        else:
            # Otherwise, find the module in cluster using type check
            module_found = False
            for slot, mod_dict in self._modules.items():
                if module_type == list(mod_dict.keys())[0]:
                    module = list(mod_dict.values())[0]
                    slot_no = int(slot)
                    module_found = True
                    break

            if not module_found:
                raise ValueError(f"Module {module_type} not found on cluster.")

        channels: dict[str, Any] = {}
        if module_type == "QTM" and channel_type in [0, 4]:
            io_channels = len(module.io_channels)
            for channel in range(io_channels):
                channels[f"IO{channel}"] = self.cluster._get_io_channel_config(slot_no, channel)

            return channels, {f"sequencer{s}": seq._get_sequencer_config() for s, seq in enumerate(module.sequencers)}

        try:
            for sequencer_idx, seq_conn_point, channel_idx in module._iter_connections():
                if channel_type in [0, 1]:
                    if "adc" in channel_idx:
                        ch_config = module.sequencers[sequencer_idx].parameters
                        channels[f"{channel_idx}_{seq_conn_point}{sequencer_idx}"] = ch_config

                if channel_type in [0, 2]:
                    if "dac" in channel_idx:
                        ch_config = module.sequencers[sequencer_idx].parameters
                        channels[f"{channel_idx}_{seq_conn_point}{sequencer_idx}"] = ch_config

                if channel_type in [0, 3]:
                    marker_config = {
                        "sync_en": module.sequencers[sequencer_idx].sync_en,
                    }
                    for trigger in range(1, EXT_TRIGGERS_IN_CLUSTER + 1):
                        trigger_str = f"trigger{trigger}"
                        threshold = module.sequencers[sequencer_idx].__getattr__(f"{trigger_str}_count_threshold")
                        invert = module.sequencers[sequencer_idx].__getattr__(f"{trigger_str}_threshold_invert")
                        marker_config.update({trigger_str: TriggerThresholdConfig(threshold=threshold, invert=invert)})

                    channels[f"DO{channel_idx.lstrip('dac').lstrip('adc')}_{sequencer_idx}"] = marker_config

        except RuntimeError:
            # The module probably does not accept the SEQ#:CHAN? command. We do only the markers, if interested.
            if channel_type in [0, 3]:
                for sequencer_idx, sequencer in enumerate(module.sequencers):
                    marker_config = {
                        "sync_en": sequencer.sync_en,
                    }
                    for trigger in range(1, EXT_TRIGGERS_IN_CLUSTER + 1):
                        trigger_str = f"trigger{trigger}"
                        threshold = sequencer.__getattr__(f"{trigger_str}_count_threshold")
                        invert = sequencer.__getattr__(f"{trigger_str}_threshold_invert")
                        marker_config.update({trigger_str: TriggerThresholdConfig(threshold=threshold, invert=invert)})

                    for channel_idx in range(4):  # We presume we end up here because the module is QTM, with 4 markers
                        channels[f"DO{channel_idx}_{sequencer_idx}"] = marker_config

        return channels, {f"sequencer{s}": seq._get_sequencer_config() for s, seq in enumerate(module.sequencers)}
