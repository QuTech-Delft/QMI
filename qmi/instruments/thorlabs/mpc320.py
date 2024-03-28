"""Module for a Thorlabs MPC320 motorised fibre polarisation controller."""

from dataclasses import dataclass
import logging
from typing import Dict, List
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.instruments.thorlabs.apt_packets import (
    HW_GET_INFO,
    MOD_GET_CHANENABLESTATE,
    MOT_GET_USTATUSUPDATE,
    MOT_MOVE_ABSOLUTE,
    MOT_MOVE_COMPLETED,
    MOT_MOVE_HOMED,
    MOT_SET_EEPROMPARAMS,
    POL_GET_SET_PARAMS,
)
from qmi.instruments.thorlabs.apt_protocol import AptChannelJogDirection, AptChannelState, AptMessageId, AptProtocol

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

@dataclass
class Thorlabs_MPC320_Status:
    """
    Data class for the status of the MPC320

    Attributes:
        channel:        Channel number.
        position:       Absolute position of the channel in degrees.
        velocity:       Velocity in controller units.
        motor_current:  Current of motor in mA
    """
    channel: int
    position: float
    velocity: int
    motor_current: int

@dataclass
class Thorlabs_MPC320_PolarisationParameters:
    """
    Data class for the polarisation parameters of the MPC320

    Attributes:
        velocity:       The velocity in percentage of the max velocity 400 degrees/s.
        home_position:  The home position of all the paddles/channels in degrees.
        jog_step1:      The position to move paddel/channel 1 by for a jog step in degrees.
        jog_step2:      The position to move paddel/channel 2 by for a jog step in degrees.
        jog_step3:      The position to move paddel/channel 3 by for a jog step in degrees.
    """
    velocity: float
    home_position: float
    jog_step1: float
    jog_step2: float
    jog_step3: float

Thorlabs_MPC320_ChannelMap: Dict[int, int] = {
    1: 0x01,
    2: 0x02,
    3: 0x04
}


class Thorlabs_MPC320(QMI_Instrument):
    """
    Driver for a Thorlabs MPC320 motorised fibre polarisation controller.
    """

    DEFAULT_RESPONSE_TIMEOUT = 1.0

    # the maximum range for a paddle is 170 degrees
    # the value returned by the encoder is 1370 for 170 degrees
    ENCODER_CONVERSION_UNIT = 170/1370

    MIN_POSITION_DEGREES = 0
    MAX_POSITION_DEGREES = 170

    MIN_VELOCITY_PERC = 10
    MAX_VELOCITY_PERC = 100

    MIN_CHANNEL_NUMBER = 1
    MAX_CHANNEL_NUMBER = 3

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "rtscts": True})
        self._apt_protocol = AptProtocol(self._transport, default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)

    def _validate_position(self, pos: float) -> None:
        """
        Validate the position. Any position for the MPC320 needs to be in the range 0 to 170 degrees, or 0 to 1370 in encoder counts.

        Parameters:
            pos:    Position to validate in degrees.

        Raises:
            an instance of QMI_InstrumentException if the position is invalid.
        """
        if not self.MIN_POSITION_DEGREES <= pos <= self.MAX_POSITION_DEGREES:
            raise QMI_InstrumentException(f"Given position {pos} is outside the valid range [{self.MIN_POSITION_DEGREES}, {self.MAX_POSITION_DEGREES}]")
        
    def _validate_velocity(self, vel: float) -> None:
        """
        Validate the velocity. Any velocity for the MPC320 needs to be in the range 40 to 400 degrees/s, or 10 to 100% of 400 degrees/s.

        Parameters:
            vel:    Velocity to validate in percentage.

        Raises:
            an instance of QMI_InstrumentException if the velocity is invalid.
        """
        if not self.MIN_VELOCITY_PERC <= vel <= self.MAX_VELOCITY_PERC:
            raise QMI_InstrumentException(f"Given relative velocity {vel} is outside the valid range [{self.MIN_VELOCITY_PERC}%, {self.MAX_VELOCITY_PERC}%]")
        
    def _validate_channel(self, channel_number: int) -> None:
        """
        Validate the channel number. The MPC320 has 3 channels.

        Parameters:
            channel_number: Channel number to validate.

        Raises:
            an instance of QMI_InstrumentException if the channel is not 1, 2 or 3
        """

        if channel_number not in [1, 2, 3]:
            raise QMI_InstrumentException(f"Given channel {channel_number} is not in the valid range [{self.MIN_CHANNEL_NUMBER}, {self.MAX_CHANNEL_NUMBER}]")

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
    def identify(self) -> None:
        """
        Identify device by flashing the front panel LEDs.
        """
        _logger.info("[%s] Identifying device", self._name)
        self._check_is_open()
        # Send message.
        # For the MPC320 the channel number does not matter here. The device has one LED that flashes irrespective
        # of the provided channel number.
        self._apt_protocol.write_param_command(AptMessageId.MOD_IDENTIFY.value, 0x01)

    @rpc_method
    def enable_channels(self, channel_numbers: List[int]) -> None:
        """
        Enable the channel(s). Note that this method will disable any channel that is not provided as an argument. For example, if
        you enable channel 1, then 2 and 3 will be disabled. If you have previously enabled a channel(s) and fail
        to include it/them again in this call, that channel(s) will be disabled. For example, if you run the following:
        self.enable_channel([1])
        self.enable_channel([2])
        only channel 2 will be enabled and 1 and 3 will be disabled. The correct way to call this method in this case is
        self.enable_channel([1,2])

        Parameters:
            channel_number: The channnels(s) to enable.
        """
        _logger.info("[%s] Enabling channel(s) %s", self._name, str(channel_numbers))
        self._check_is_open()
        for channel_number in channel_numbers:
            self._validate_channel(channel_number)
        # Make hexadecimal value for channels
        channels_to_enable = 0x00
        for channel_number in channel_numbers:
            channels_to_enable ^= channel_number
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.MOD_SET_CHANENABLESTATE.value, channels_to_enable, AptChannelState.ENABLE.value)

    @rpc_method
    def disable_all_channels(self) -> None:
        """
        Disable all the channels.
        """
        _logger.info("[%s] Disabling channels", self._name)
        self._check_is_open()
        self._apt_protocol.write_param_command(AptMessageId.MOD_SET_CHANENABLESTATE.value, 0x00, AptChannelState.ENABLE.value)

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
        self._validate_channel(channel_number)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.MOD_REQ_CHANENABLESTATE.value, Thorlabs_MPC320_ChannelMap[channel_number])
        # Get response
        resp = self._apt_protocol.ask(MOD_GET_CHANENABLESTATE)
        # For the MPC320 the state 0x00 is also a valid channel state. It is also the disable state
        if resp.enable_state == 0x00:
            return AptChannelState.DISABLE
        return AptChannelState(resp.enable_state)

    @rpc_method
    def disconnect_hardware(self) -> None:
        """
        Disconnect hardware from USB bus.
        """
        # TODO: this does nothing
        _logger.info("[%s] Disconnecting instrument from USB bus", self._name)
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
    def home_channel(self, channel_number: int) -> None:
        """
        Start the homing sequence for a given channel.

        Paramters:
            channel_number: The channel to home.
        """
        _logger.info("[%s] Homing channel %d", self._name, channel_number)
        self._validate_channel(channel_number)
        self._check_is_open()
        # Send message.
        self._apt_protocol.write_param_command(AptMessageId.MOT_MOVE_HOME.value, Thorlabs_MPC320_ChannelMap[channel_number])

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
            True if the channel was homed.
        """
        _logger.info("[%s] Checking if channel %d is homed", self._name, channel_number)
        self._validate_channel(channel_number)
        self._check_is_open()
        # Get response.
        resp = self._apt_protocol.ask(MOT_MOVE_HOMED, timeout)
        # Check if the channel number in the response is equal to the one that was asked for.
        return resp.chan_ident == Thorlabs_MPC320_ChannelMap[channel_number]
        
    @rpc_method
    def move_absolute(self, channel_number: int, position: float) -> None:
        """
        Move a channel to the specified position. The specified position is in degeres. A conversion is done to convert this
        into encoder counts. This means that there may be a slight mismatch in the specified position and the actual position.
        You may use the get_status_update method to get the actual position.

        Parameters:
            channel_number: The channel to address.
            position:       Absolute position to move to in degrees.
        """
        # TODO: check for move completed command, otherwise the that message will stay in the buffer
        _logger.info("[%s] Moving channel %d", self._name, channel_number)
        self._validate_channel(channel_number)
        self._check_is_open()
        # Convert position in degrees to encoder counts.
        encoder_position = round(position / self.ENCODER_CONVERSION_UNIT)
        # Make data packet.
        data_packet = MOT_MOVE_ABSOLUTE(chan_ident=Thorlabs_MPC320_ChannelMap[channel_number], absolute_distance=encoder_position)
        # Send message.
        self._apt_protocol.write_data_command(AptMessageId.MOT_MOVE_ABSOLUTE.value, data_packet)

    @rpc_method
    def is_move_completed(self, channel_number: int, timeout: float = DEFAULT_RESPONSE_TIMEOUT) -> bool:
        """
        Check if a given channel has completed its move. This command should only be run after a relative or absolute
        move command. Otherwise you will read bytes from other commands.

        Paramters:
            channel_number: The channel to check.
            timeout:        The time to wait for a response to the homing command. This is optional
                            and is set to a default value of DEFAULT_RESPONSE_TIMEOUT.

        Returns:
            True if the move for the channel was completed.
        """
        # TODO: add status data packet
        _logger.info("[%s] Checking if channel %d has completed its move", self._name, channel_number)
        self._validate_channel(channel_number)
        self._check_is_open()
        # Get response
        resp = self._apt_protocol.ask(MOT_MOVE_COMPLETED, timeout)
        return resp.chan_ident == Thorlabs_MPC320_ChannelMap[channel_number]

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
        self._validate_channel(channel_number)
        # Make data packet.
        data_packet = MOT_SET_EEPROMPARAMS(chan_ident=Thorlabs_MPC320_ChannelMap[channel_number], msg_id=message_id)
        # Send message.
        self._apt_protocol.write_data_command(AptMessageId.MOT_SET_EEPROMPARAMS.value, data_packet)

    @rpc_method
    def get_status_update(self, channel_number: int) -> Thorlabs_MPC320_Status:
        """
        Get the status update for a given channel. This call will return the position, velocity, motor current and
        status of the channel.

        Parameters:
            channel_number: The channel to query.

        Returns:
            An instance of Thorlabs_MPC320_Status.
        """
        _logger.info("[%s] Getting position counter of channel %d", self._name, channel_number)
        self._check_is_open()
        self._validate_channel(channel_number)
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.MOT_REQ_USTATUSUPDATE.value, Thorlabs_MPC320_ChannelMap[channel_number])
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_USTATUSUPDATE)
        return Thorlabs_MPC320_Status(channel=channel_number, position=resp.position * self.ENCODER_CONVERSION_UNIT,
                                      velocity=resp.velocity, motor_current=resp.motor_current)

    @rpc_method
    def jog(self, channel_number: int, direction: AptChannelJogDirection=  AptChannelJogDirection.FORWARD) -> None:
        """
        Move a channel specified by its jog step.

        Parameters:
            channel_number: The channel to job.
            direction:      The direction to job. This can either be forward or backward. Default is forward.
        """
        # TODO: check for jog completion
        _logger.info("[%s] Getting position counter of channel %d", self._name, channel_number)
        self._check_is_open()
        self._validate_channel(channel_number)
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.MOT_MOVE_JOG.value, Thorlabs_MPC320_ChannelMap[channel_number], direction.value)

    @rpc_method
    def set_polarisation_parameters(
        self,
        velocity: int,
        home_pos: int,
        jog_step1: int,
        jog_step2: int,
        jog_step3: int,
    ) -> None:
        """
        Set the polarisation parameters.

        Parameters:
            velocity:       Velocity in range 10% to 100% of 400 degrees/s.
            home_position:  Home position in degrees.
            jog_step1:      Size of jog step for paddle 1.
            jog_step2:      Size of jog step for paddle 2.
            jog_step3:      Size of jog step for paddle 3.
        """
        _logger.info("[%s] Setting polarisation parameters", self._name)
        self._check_is_open()
        # Validate parameters.
        self._validate_velocity(velocity)
        self._validate_position(home_pos)
        self._validate_position(jog_step1)
        self._validate_position(jog_step2)
        self._validate_position(jog_step3)
        # Make data packet.
        data_packet = POL_GET_SET_PARAMS(
            velocity=velocity,
            home_position=round(home_pos / self.ENCODER_CONVERSION_UNIT),
            jog_step1=round(jog_step1 / self.ENCODER_CONVERSION_UNIT),
            jog_step2=round(jog_step2 / self.ENCODER_CONVERSION_UNIT),
            jog_step3=round(jog_step3 / self.ENCODER_CONVERSION_UNIT),
        )
        # Send message.
        self._apt_protocol.write_data_command(AptMessageId.POL_SET_PARAMS.value, data_packet)

    @rpc_method
    def get_polarisation_parameters(self) -> Thorlabs_MPC320_PolarisationParameters:
        """
        Get the polarisation parameters.
        """
        _logger.info("[%s] Getting polarisation parameters", self._name)
        self._check_is_open()
        # Send request message.
        self._apt_protocol.write_param_command(AptMessageId.POL_REQ_PARAMS.value)
        # Get response.
        params = self._apt_protocol.ask(POL_GET_SET_PARAMS)
        return Thorlabs_MPC320_PolarisationParameters(velocity=params.velocity,
                                                      home_position=params.home_position * self.ENCODER_CONVERSION_UNIT,
                                                      jog_step1=params.jog_step1 * self.ENCODER_CONVERSION_UNIT,
                                                      jog_step2=params.jog_step2 * self.ENCODER_CONVERSION_UNIT,
                                                      jog_step3=params.jog_step3 * self.ENCODER_CONVERSION_UNIT)
