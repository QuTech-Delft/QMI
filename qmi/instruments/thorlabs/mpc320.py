"""Module for a Thorlabs MPC320 motorised fibre polarisation controller."""
import logging
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.instruments.thorlabs.apt_packets import HW_GET_INFO, MOD_GET_CHANENABLESTATE, MOT_GET_SET_POSCOUNTER, MOT_GET_USTATUSUPDATE, MOT_MOVE_COMPLETED, MOT_MOVE_HOMED, MOT_SET_EEPROMPARAMS, POL_GET_SET_PARAMS
from qmi.instruments.thorlabs.apt_protocol import AptChannelState, AptMessageId, AptProtocol
# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

class Thorlabs_MPC320(QMI_Instrument):
    """
    Driver for a Thorlabs MPC320 motorised fibre polarisation controller.
    """
    DEFAULT_RESPONSE_TIMEOUT = 1.0

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "rtscts": True})
        self._apt_protocol = AptProtocol(self._transport, default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)
        self._power_unit_configured = False

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """
        Read instrument type and version and return QMI_InstrumentIdentification instance.
        
        Returns:
            an instance of QMI_InstrumentIdentification. The version refers to the firmware version.
        """
        _logger.info("[%s] Getting identification of instrument", self._name)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.HW_REQ_INFO.value)
        # Get response
        resp = self._apt_protocol.ask(HW_GET_INFO)
        return QMI_InstrumentIdentification("Thorlabs", resp.model_number, resp.serial_number, resp.firmware_version)
    
    @rpc_method
    def identify_channel(self, channel_number: int) -> None:
        """
        Identify a channel by flashing the front panel LEDs.

        Parameters:
            channel_number: The channel to be identified.
        """
        _logger.info("[%s] Identify channel %d", self._name, channel_number)
        # TODO: check and validate channel number for MPC320
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.MOD_IDENTIFY.value, channel_number)

    def _toggle_channel_state(self, channel_number: int, state: AptChannelState) -> None:
        """
        Toggle the state of the channel.

        Parameters:
            channel_number: The channel to toggle.
            state:          The state to change the channel to.
        """
        # TODO: check and validate channel number for MPC320
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.MOD_IDENTIFY.value, channel_number, state.value)

    @rpc_method
    def enable_channel(self, channel_number: int) -> None:
        """
        Enable the channel.

        Parameters:
            channel_number: The channel to enable.
        """
        _logger.info("[%s] Enabling channel %d", self._name, channel_number)
        self._toggle_channel_state(channel_number, AptChannelState.ENABLE)

    @rpc_method
    def disable_channel(self, channel_number: int) -> None:
        """
        Disable the channel.

        Parameters:
            channel_number: The channel to disable.
        """
        _logger.info("[%s] Disabling channel %d", self._name, channel_number)
        self._toggle_channel_state(channel_number, AptChannelState.DISABLE)

    @rpc_method
    def get_channel_state(self, channel_number: int) -> AptChannelState:
        """
        Get the state of the specified channel.

        Parameters:
            channel_number: The channel to check.
        
        Returns:
            The state of the channel as an AptChannelState enum.
        """
        _logger.info("[%s] Getting state of channel %d", self._name, channel_number)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.MOD_REQ_CHANENABLESTATE.value, channel_number)
        # Get response
        resp = self._apt_protocol.ask(MOD_GET_CHANENABLESTATE)
        return AptChannelState(resp.enable_state)
    
    @rpc_method
    def disconnect_hardware(self) -> None:
        """
        Disconnect hardware from USB bus.
        """
        _logger.info("[%s] Disconnecting instrument from USB hub", self._name)
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.HW_DISCONNECT.value)

    @rpc_method
    def start_auto_status_update(self) -> None:
        """
        Start automatic status updates from device.
        """
        _logger.info("[%s] Starting automatic status updates from instrument", self._name)
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.HW_START_UPDATEMSGS.value)

    @rpc_method
    def stop_auto_status_update(self) -> None:
        """
        Stop automatic status updates from device.
        """
        _logger.info("[%s] Stopping automatic status updates from instrument", self._name)
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.HW_STOP_UPDATEMSGS.value)

    @rpc_method
    def restore_factory_settings(self) -> None:
        """
        Restore settings to the default values stored in the EEPROM.
        """
        _logger.info("[%s] Restoring factory settings of instrument", self._name)
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.RESTOREFACTORYSETTINGS.value)

    @rpc_method
    def set_position_counter(self, channel_number: int, position_counter: int) -> None:
        """
        Set the live position count in the controller.

        Paramters:
            channel_number:     The channel to change the position counter for.
            position_counter:   The value of the position counter.
        """
        _logger.info("[%s] Changing position counter of channel %d to %d", self._name, channel_number, position_counter)
        self._check_is_open()
        # Make data packet.
        data_packet = MOT_GET_SET_POSCOUNTER(chan_ident=channel_number, position=position_counter)
        # Send message.
        self._apt_protocol.write_data_command(AptMessageId.MOT_SET_POSCOUNTER.value, data_packet)

    @rpc_method
    def get_position_counter(self, channel_number: int) -> int:
        """
        Get the value of the position counter for a channel.

        Paramters:
            channel_number: The channel to query.
        
        Returns:
            position counter for a channel.
        """
        _logger.info("[%s] Getting position counter of channel %d", self._name, channel_number)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.MOT_REQ_POSCOUNTER.value, channel_number)
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_SET_POSCOUNTER)
        return resp.position
    
    @rpc_method
    def home_channel(self, channel_number: int) -> None:
        """
        Start the homing sequence for a given channel. 

        Paramters:
            channel_number: The channel to home.
        """
        _logger.info("[%s] Homing channel %d", self._name, channel_number)
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.MOT_MOVE_HOME.value)

    
    @rpc_method
    def is_channel_homed(self, channel_number: int, timeout: float = DEFAULT_RESPONSE_TIMEOUT) -> bool:
        """
        Check if a given channel is homed. This command should only be run after the method `home_channel`.
        Otherwise you will read bytes from other commands using this method. 

        Paramters:
            channel_number: The channel to check.
            timeout:        The time to wait for a response to the homing command. This is optional
                            and is set to a default value of DEFAULT_RESPONSE_TIMEOUT.

        Returns:
            True if the device was homed and a response was received before the timeout else False.
        """
        _logger.info("[%s] Check if channel %d is homed", self._name, channel_number)
        self._check_is_open()
        # Get response
        try:
            _ = self._apt_protocol.ask(MOT_MOVE_HOMED, timeout)
            return True
        except QMI_TimeoutException:
            return False
        
    @rpc_method
    def is_move_completed(self, channel_number: int, timeout: float = DEFAULT_RESPONSE_TIMEOUT) -> bool:
        """
        Check if a given channel has completed its move. This command should only be run after a relative or absolute move command.
        Otherwise you will read bytes from other commands using this method. 

        Paramters:
            channel_number: The channel to check.
            timeout:        The time to wait for a response to the homing command. This is optional
                            and is set to a default value of DEFAULT_RESPONSE_TIMEOUT.

        Returns:
            True if the move was completed and a response was received before the timeout else False.
        """
        # TODO: add status data packet
        _logger.info("[%s] Check if channel %d has completed its move", self._name, channel_number)
        self._check_is_open()
        # Get response
        try:
            _ = self._apt_protocol.ask(MOT_MOVE_COMPLETED, timeout)
            return True
        except QMI_TimeoutException:
            return False
    
    @rpc_method
    def save_parameter_settings(self, channel_number: int, message_id: int) -> None:
        """
        Save parameter settings for a specific message id. These parameters could have been edited via the QMI driver
        or the GUI provided by Thorlabs.

        Parameters:
            channel_number: The channel to address.
            message_id:     ID of message whose parameters need to be saved.
        """
        _logger.info("[%s] Saving parameters of message %d", self._name, message_id)
        self._check_is_open()
        # Make data packet.
        data_packet = MOT_SET_EEPROMPARAMS(chan_ident=channel_number, msg_id=message_id)
        # Send message.
        self._apt_protocol.write_data_command(AptMessageId.MOT_SET_EEPROMPARAMS.value, data_packet)

    @rpc_method
    def get_status_update(self, channel_number: int) -> MOT_GET_USTATUSUPDATE:
        """
        Get the status update for a given channel.

        Parameters:
            channel_number: The channel to query.

        Returns:
            An instance of MOT_GET_USTATUSUPDATE.
        """
        _logger.info("[%s] Getting position counter of channel %d", self._name, channel_number)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.MOT_GET_USTATUSUPDATE.value, channel_number)
        # Get response
        return self._apt_protocol.ask(MOT_GET_USTATUSUPDATE)
    
    @rpc_method
    def set_polarisation_parameters(self, velocity: int, home_pos: int, jog_step1: int, jog_step2: int, jog_step3: int) -> None:
        """
        Set the polarisation parameters.

        Parameters:
            velocity:       Velocity in range 10% to 100% of 400 degrees/s.
            home_position:  Home position in encoder counts.
            jog_step1:      Size fo jog step to be performed on paddle 1.
            jog_step2:      Size fo jog step to be performed on paddle 2.
            jog_step3:      Size fo jog step to be performed on paddle 3.
        """
        # TODO: finish command
        _logger.info("[%s] Setting polarisation parameters", self._name)
        self._check_is_open()
        # Make data packet.
        data_packet = POL_GET_SET_PARAMS(velocity=velocity, home_position=home_pos, jog_step1=jog_step1, jog_step2=jog_step2, jog_step3=jog_step3)
        # Send message.
        self._apt_protocol.write_data_command(AptMessageId.POL_SET_PARAMS.value, data_packet)

    @rpc_method
    def get_polarisation_parameters(self) -> MOT_GET_SET_POSCOUNTER:
        """
        Get the polarisation parameters.
        """
        _logger.info("[%s] Getting polarisation parameters", self._name)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.POL_REQ_PARAMS.value)
        # Get response
        return self._apt_protocol.ask(MOT_GET_SET_POSCOUNTER)