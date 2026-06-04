"""QBlox manager classes for controlling Qblox cluster modules: QCM, QRM, -RF and QTM control.

The classes should work equally with "native" and "Qcodes" Qblox `Cluster` instances.

Please report any issues in QMI Github at https://github.com/QuTech-Delft/QMI/issues
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import qblox_instruments
    from qblox_instruments.native.definitions import ChannelType
    from qblox_instruments.native.helpers import ChannelMapCache

else:
    qblox_instruments = None
    ChannelType, ChannelMapCache = None, None

from qmi.core.context import QMI_Context
from qmi.core.rpc import QMI_RpcObject, rpc_method
from qmi.instruments.qblox.cluster import Qblox_NativeCluster, Qblox_QcodesCluster
from qmi.instruments.qblox.cluster import (
    SEQUENCERS_IN_MODULE,
    AI_IN_MODULE,
    AO_IN_MODULE,
    DIGITAL_MARKERS_IN_MODULE,
)
from qmi.utils._qblox_channels import QbloxAdcChannel, QbloxDacChannel, QbloxIOChannel, QbloxMarkerChannel


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def _import_modules() -> None:
    """Import the vendor-provided Qblox modules.
    
    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global qblox_instruments, ChannelType, ChannelMapCache  # noqa: PLW0603
    if qblox_instruments is None:
        import qblox_instruments
        from qblox_instruments.native.definitions import ChannelType
        from qblox_instruments.native.helpers import ChannelMapCache


class QbloxManager(QMI_RpcObject):
    """
    A base class for all Qblox module and channel managers. This can also work as making a manager instance
    for the Qblox cluster management module (CMM) if giving 'MM' as module and '0' as slot index.

    Usage example::

        import qmi
        from qmi.instruments.qblox import Qblox_NativeCluster as Qblox_Cluster
        from qmi.utils.qblox_manager import QbloxManager

        with qmi.start("Cluster_context") as qmi_context:
            with qmi.make_instrument("cluster_1", Qblox_Cluster, "123.45.67.89") as qblox_cluster:
                cluster_manager = QbloxManager(
                    qmi_context, "cluster_manager", qblox_cluster, "MM", 0
                )
                # Start all armed sequencers across all modules present
                cluster_manager.start_sequencers(start_all=True)
    """

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        cluster: Qblox_NativeCluster | Qblox_QcodesCluster,
        module: str,
        slot: int,
    ) -> None:
        """Initialization of the manager.

        This creates a listing of ADC, DAC and DIO channels and sequencers on the given module.
        For cluster module at slot 0 these will be empty lists.

        Parameters:
            context: QMI context instance.
            name:    Unique name for this object instance.
            cluster: A Qblox Cluster object the managed module is on.
            module:  Module name that we want to manage.
            slot:    The slot number of the module. Used for checking that we refer to correct module.
        """
        _logger.info(
            f"Creating a QbloxManager instance for {module} on slot {slot} in Qblox cluster '{cluster.get_name()}'"
        )
        super().__init__(context, name)
        self.managed_module = module
        self.managed_slot = slot
        # Get module function references and all of its channels
        if module.upper() == "MM" and slot == 0:
            self.module_func_refs = cluster.get_module_func_refs(module, slot)
            channels, sequencers = {}, {}
        else:
            self.module_func_refs = cluster.get_module_func_refs(module, slot)
            channels, sequencers = cluster.get_module_channels(module, slot)

        self._module_channels = channels
        self._module_sequencers = sequencers
        # Channel counts
        self._adc_channel_count = AI_IN_MODULE[module]
        self._dac_channel_count = AO_IN_MODULE[module]
        self._marker_channel_count = DIGITAL_MARKERS_IN_MODULE[module]
        self._sequencer_count = SEQUENCERS_IN_MODULE[module]

    @property
    def adc_channel_count(self) -> int:
        """Getter for ADC channel count."""
        return self._adc_channel_count

    @property
    def dac_channel_count(self) -> int:
        """Getter for DAC channel count."""
        return self._dac_channel_count

    @property
    def marker_channel_count(self) -> int:
        """Getter for marker channel count."""
        return self._marker_channel_count

    @property
    def sequencer_count(self) -> int:
        """Getter for sequencer count."""
        return self._sequencer_count

    @rpc_method
    def get_idn(self) -> str:
        """Compile an identification string for the cluster module and return it."""
        return f"Qblox {self.managed_module} module on slot {self.managed_slot}."

    @rpc_method
    def get_sequencer(self, sequencer: int) -> dict[str, Any]:
        """Get a module sequencer.

        Parameters:
            sequencer: The sequence number to get.

        Returns:
            sequencer: The module's given sequencer configuration.
        """
        return self._module_sequencers[sequencer]

    @rpc_method
    def get_adc_channel(self, channel: int, sequencer: int | None = None) -> QbloxAdcChannel:
        """Get an ADC channel from the module. This function will check the validity of the channel number and sequencer
        combination first, and then grab the full sequencer configuration from the module. Before creation of the new
        channel instance, the existing connections are disconnected on all ADC channels present in the module. Then
        the selected channel will be connected with the sequencer index, and an ADC channel instance is made.

        Parameters:
            channel:     The ADC channel number that will be connected.
            sequencer:   The sequencer index number to connect the channel to.

        Returns:
            adc_channel: A _QbloxAdcChannel instance.

        Raises:
            ValueError:  If no ADC channel with given channel and sequencer number is present in the module.
        """
        raise NotImplementedError("Not implemented.")

    @rpc_method
    def get_dac_channel(self, channel: int, sequencer: int | None = None) -> QbloxDacChannel:
        """Get a DAC channel from the module. This function will check the validity of the channel number and sequencer
        combination first, and then grab the full sequencer configuration from the module. Before creation of the new
        channel instance, the existing connections are disconnected on all DAC channels present in the module. Then
        the selected channel will be connected with the sequencer index, and a DAC channel instance is made.

        Parameters:
            channel:     The DAC channel number that will be connected.
            sequencer:   The sequencer index number to connect the channel to.

        Returns:
            dac_channel: A _QbloxDacChannel instance.

        Raises:
            ValueError:  If no DAC channel with given channel and sequencer number is present in the module.
        """
        raise NotImplementedError("Not implemented.")

    @rpc_method
    def get_marker_channel(self, channel: int, sequencer: int | None = None) -> QbloxMarkerChannel:
        """Get a marker channel from the module. This function will check the validity of the channel number and
        sequencer combination first, and then grab the full sequencer configuration from the module. As marker channels
        are usually controlled together with some ADC or DAC channel, we do not connect marker channels to any
        output paths. The sequencer can be a shared sequencer with an ADC or DAC channel instance.

        Parameters:
            channel:        The marker channel number.
            sequencer:      Optional sequencer number to use with the marker channel.

        Returns:
            marker_channel: A _QbloxMarkerChannel instance.

        Raises:
            ValueError:     If no marker channel with given channel and sequencer number is present in the module.
        """
        raise NotImplementedError("Not implemented.")

    @rpc_method
    def get_io_channel(self, channel: int):
        """Get an IO channel from a QTM module. This function will check the validity of the channel number and
        sequencer combination first, and then grab the full sequencer configuration from the module. As IO channels
        are defined to use the same channel and sequencer number, we do not need to separate sequencer number input.

        Parameters:
            channel:    The IO channel number. The sequencer will have the same number.

        Returns:
            io_channel: A _QbloxIOChannel instance.

        Raises:
            ValueError: If no IO channel with given channel number is present in the module.
        """
        raise NotImplementedError("Not implemented.")

    @rpc_method
    def start_sequencer(self, sequencer: int) -> None:
        """Start a sequencer within this module.

        Parameters:
            sequencer: Sequencer number to start within this module.
        """
        self.module_func_refs["start_sequencer"](f"SLOT{self.managed_slot}:SEQuencer{sequencer}")

    @rpc_method
    def stop_sequencer(self, sequencer: int) -> None:
        """Stop a sequencers within this module.

        Parameters:
            sequencer: Sequencer number to stop within this module.
        """
        self.module_func_refs["stop_sequencer"](f"SLOT{self.managed_slot}:SEQuence{sequencer}r")

    @rpc_method
    def start_sequencers(self, start_all=False) -> None:
        """Start all sequencers within this module or at all modules.

        Parameters:
            start_all: True to start all sequencers across all modules, False (default) to start
                       all sequencers within this module.
        """
        if start_all:
            self.module_func_refs["start_sequencer"]("SLOT:SEQuencer")
        else:
            self.module_func_refs["start_sequencer"](f"SLOT{self.managed_slot}:SEQuencer")

    @rpc_method
    def stop_sequencers(self, stop_all=False) -> None:
        """Stop all sequencers within this module or at all modules.

        Parameters:
            stop_all: True to stop all sequencers across all modules, False (default) to stop
                       all sequencers within this module.
        """
        if stop_all:
            self.module_func_refs["stop_sequencer"]("SLOT:SEQuencer")
        else:
            self.module_func_refs["stop_sequencer"](f"SLOT{self.managed_slot}:SEQuencer")


class QbloxIOManager(QbloxManager):
    """A manager for Qblox modules' analog-to-digital (ADC), digital-to-analog (DAC) and digital input/output (DIO)
    channel control. An instance is module-specific with allowing control of ADC, DAC and DIO channels of that module.

    Usage example::

        import qmi
        from qmi.instruments.qblox import Qblox_NativeCluster as Qblox_Cluster
        from qmi.utils.qblox_manager import QbloxIOManager

        with qmi.start("Cluster_context") as qmi_context:
            with qmi.make_instrument("cluster_1", Qblox_Cluster, "123.45.67.89") as qblox_cluster:
                qblox_cluster.reset_cluster()
                # We want to create a manager for QCM module in slot 4
                qcm_mgr = QbloxIOManager(
                    qmi_context, "QCM_manager", qblox_cluster, "QCM", 4
                )
                # We want to control one DAC channel and one marker channel
                qcm_dac_0 = qcm_mgr.get_dac_channel(0)  # Will use sequencer 0
                qcm_dac_0.configure(output_channel=0, gain=[1.0, 1.0], nco_freq=100e6, enable_modulation=True)
                qcm_mrk_0 = qcm_mgr.get_marker_channel(0, sequencer=5)  # Bind with sequencer 5
                qcm_mrk_0.set_marker_channel_level(True, invert=True)  # Set marker 'high' and invert marker
                # To execute the changes in the changed sequencer values, we need to upload, arm and start the sequencer
                sequencer_program = {
                    "program": '''
                        nop
                        stop
                    ''',
                    "waveforms": {},
                    "weights": {},
                    "acquisitions": {}                  
                }
                qcm_dac_0.upload_sequence(sequencer_program)
                qcm_dac_0.arm_sequencer()
                qcm_mrk_0.upload_sequence(sequencer_program)
                qcm_mrk_0.arm_sequencer()

                # We also want to create a manager for QRM module in slot 5
                qrm_mgr = QbloxIOManager(
                    qmi_context, "QRM_manager", qblox_cluster, "QRM", 5
                )
                qrm_adc_1 = qrm_mgr.get_adc_channel(1)  # Will use sequencer 1
                qrm_adc_1.configure(threshold=0.4, auto_bin_increment=False, enable_demodulation=True)
                qcm_adc_1.upload_sequence(sequencer_program)
                qcm_adc_1.arm_sequencer()

                # Start all armed sequencers across all modules present
                qblox_cluster.start_sequencers(start_all=True)
    """

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        cluster: Qblox_NativeCluster | Qblox_QcodesCluster,
        module: str,
        slot: int,
    ) -> None:
        """Initialization of the manager. This should create a listing of DAC and DIO objects on the given module.
        We probably need to define at least following inputs:

        Parameters:
            context: QMI context instance.
            name:    Unique name for this object instance.
            cluster: A Qblox Cluster object the managed module is on.
            module:  Module name the ADC/DAC/DIO channel we want to manage is in.
            slot:    The slot number of the module. Used for checking that we refer to correct module.
        """
        super().__init__(context, name, cluster, module, slot)
        # list all possible channels in the module
        self._adc_channels: list[str] = [key for key in list(self._module_channels.keys()) if key.startswith("adc")]
        self._dac_channels: list[str] = [key for key in list(self._module_channels.keys()) if key.startswith("dac")]
        self._do_channels: list[str] = [key for key in list(self._module_channels.keys()) if key.startswith("DO")]
        self._io_channels: list[str] = [key for key in list(self._module_channels.keys()) if key.startswith("IO")]
        # Get the channel map
        if module.upper() == "MM" and slot == 0:
            self._channel_map = None
        else:
            self._channel_map = cluster.get_module_channel_map_cache(module, slot)

    @property
    def channel_map(self) -> ChannelMapCache:
        assert self._channel_map is not None, f"Module {self.managed_module} does not have a channel map."
        return self._channel_map

    @rpc_method
    def get_adc_channel(self, channel: int, sequencer: int | None = None) -> QbloxAdcChannel:
        channels = AI_IN_MODULE[self.managed_module]
        if channels == 0 or 0 > channel > channels:
            raise ValueError(f"Invalid ADC channel number {channel}. Available channels in module: {channels}")

        if sequencer is None:
            sequencer = channel

        sequencers = SEQUENCERS_IN_MODULE[self.managed_module]
        if 0 > sequencer > sequencers:
            raise ValueError(f"Invalid ADC sequencer number {sequencer}. Available sequencers in module: {sequencers}")

        direction = ChannelType.ACQ  # ADC is direction 'ACQ'
        # TODO: we get the sequencer config of the channel here, and it could be used for pre-setting variables
        channel_cfg = self._module_sequencers[f"sequencer{sequencer}"]
        # The channel can be either 'acq_I' or 'acq_Q' type, or 'IQ' for an "RF" module. Check which one it is.
        if "RF" in self.managed_module:
            adc_channel_string = f"adc{channel}_IQ{sequencer}"
            if adc_channel_string in self._adc_channels:
                # Map sequencer to specific output (but first disable all previous connections of this sequencer)
                for ch in range(channels):
                    self.channel_map.disconnect(direction, sequencer, ch % 2, ch)

                self.channel_map.connect(direction, sequencer, channel % 2, channel, True)
                adc_channel = QbloxAdcChannel(
                    self.module_func_refs, self.managed_slot, sequencer, channel, channel_cfg
                )
                self.channel_map.flush()
                if not self.channel_map.is_connected(direction, sequencer, channel % 2, channel):
                    raise RuntimeError(f"Channel {channel} did not get connected to sequencer {sequencer}")

                return adc_channel

        else:
            adc_i_channel_string = f"adc{channel}_acq_I{sequencer}"
            adc_q_channel_string = f"adc{channel}_acq_Q{sequencer}"
            if adc_i_channel_string in self._adc_channels or adc_q_channel_string in self._adc_channels:
                # Map sequencer to specific output (but first disable all previous connections of this sequencer)
                for ch in range(channels):
                    self.channel_map.disconnect(direction, sequencer, ch % 2, ch)

                self.channel_map.connect(direction, sequencer, channel % 2, channel, True)
                adc_channel = QbloxAdcChannel(
                    self.module_func_refs, self.managed_slot, sequencer, channel, channel_cfg
                )
                self.channel_map.flush()
                if not self.channel_map.is_connected(direction, sequencer, channel % 2, channel):
                    raise RuntimeError(f"Channel {channel} did not get connected to sequencer {sequencer}")

                return adc_channel

        raise ValueError(
            f"No ADC channel {channel} with sequencer number {sequencer} present in module."
            + f" Possible channels are {self._adc_channels}."
        )

    @rpc_method
    def get_dac_channel(self, channel: int, sequencer: int | None = None) -> QbloxDacChannel:
        # Map sequencer to specific output (but first disable all previous connections of this sequencer)
        channels = AO_IN_MODULE[self.managed_module]
        if channels == 0 or 0 > channel > channels:
            raise ValueError(f"Invalid DAC channel number {channel}. Available channels in module: {channels}")

        if sequencer is None:
            sequencer = channel

        sequencers = SEQUENCERS_IN_MODULE[self.managed_module]
        if 0 > sequencer > sequencers:
            raise ValueError(f"Invalid DAC sequencer number {sequencer}. Available sequencers in module: {sequencers}")

        # The channel can be either 'I' or 'Q' type, but not both. Check which one it is.
        dac_i_channel_string = f"dac{channel}_I{sequencer}"
        dac_q_channel_string = f"dac{channel}_Q{sequencer}"
        if dac_i_channel_string in self._dac_channels or dac_q_channel_string in self._dac_channels:
            direction = ChannelType.AWG  # DAC is direction 'AWG'
            for ch in range(channels):
                self.channel_map.disconnect(direction, sequencer, ch % 2, ch)

            self.channel_map.connect(direction, sequencer, channel % 2, channel, True)
            channel_cfg = self._module_sequencers[f"sequencer{sequencer}"]
            dac_channel = QbloxDacChannel(
                self.module_func_refs,
                self.managed_slot,
                sequencer,
                channel,
                channel_cfg,
            )
            self.channel_map.flush()
            if not self.channel_map.is_connected(direction, sequencer, channel % 2, channel):
                raise RuntimeError(f"Channel {channel} did not get connected to sequencer {sequencer}")

            return dac_channel

        raise ValueError(
            f"No DAC channel {channel} with sequencer number {sequencer} present in module."
            + f" Possible channels are {self._dac_channels}."
        )

    @rpc_method
    def get_marker_channel(self, channel: int, sequencer: int | None = None) -> QbloxMarkerChannel:
        channels = DIGITAL_MARKERS_IN_MODULE[self.managed_module]
        if channels == 0 or 0 > channel > channels:
            raise ValueError(f"Invalid marker channel number {channel}. Available channels in module: {channels}")

        if sequencer is None:
            sequencer = channel

        sequencers = SEQUENCERS_IN_MODULE[self.managed_module]
        if 0 > sequencer > sequencers:
            raise ValueError(
                f"Invalid marker sequencer number {sequencer}. Available sequencers in module: {sequencers}"
            )

        do_channel_string = f"DO{channel}_{sequencer}"
        if do_channel_string in self._do_channels:
            channel_cfg = self._module_sequencers[f"sequencer{sequencer}"]
            marker_channel = QbloxMarkerChannel(
                self.module_func_refs,
                self.managed_slot,
                sequencer,
                channel,
                channel_cfg,
            )

            return marker_channel

        raise ValueError(
            f"No DO channel {channel} with sequencer number {sequencer} present in module."
            + f" Possible channels are {self._do_channels}."
        )

    @rpc_method
    def get_io_channel(self, channel: int):
        # Number of I/O channels not defined in cluster level as only QTM modules contain them.
        channels = len(self._io_channels)
        if channels == 0 or 0 > channel > channels:
            raise ValueError(f"Invalid IO channel number {channel}. Available IO channels in module: {channels}")

        io_channel_string = f"IO{channel}"
        if io_channel_string in self._io_channels:
            sequencers = SEQUENCERS_IN_MODULE[self.managed_module]
            channel_cfg = self._module_channels[f"IO{channel}"]
            sequencer_cfg = self._module_sequencers[f"sequencer{channel}"]
            io_channel = QbloxIOChannel(
                self.module_func_refs, self.managed_slot, sequencers, channel, channel_cfg, sequencer_cfg
            )
            return io_channel

        raise ValueError(f"No IO channel {channel} present in module. Possible channels are {self._io_channels}.")
