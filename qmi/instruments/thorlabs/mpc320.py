"""Module for a Thorlabs MPC320 motorised fibre polarisation controller.

This driver communicates with the device via a USB serial port, using the Thorlabs APT protocol. For details,
see the document "Thorlabs APT Controllers Host-Controller Communications Protocol",
issue 25 from Thorlabs.
"""

from dataclasses import dataclass
import logging
import time

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport, QMI_SerialTransport
from qmi.instruments.thorlabs.apt_packets import AptMessageId
from qmi.instruments.thorlabs.apt_protocol import (
    APT_MESSAGE_TYPE_TABLE,
    AptChannelJogDirection,
    AptChannelState,
    AptProtocol,
)

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


@dataclass
class Thorlabs_Mpc320_Status:
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
class Thorlabs_Mpc320_PolarisationParameters:
    """
    Data class for the polarisation parameters of the MPC320

    Attributes:
        velocity:       The velocity in percentage of the max velocity 400 degrees/s.
        home_position:  The home position of all the paddles/channels in degrees.
        jog_step1:      The position to move paddle/channel 1 by for a jog step in degrees.
        jog_step2:      The position to move paddle/channel 2 by for a jog step in degrees.
        jog_step3:      The position to move paddle/channel 3 by for a jog step in degrees.
    """

    velocity: float
    home_position: float
    jog_step1: float
    jog_step2: float
    jog_step3: float


Thorlabs_Mpc320_ChannelMap: dict[int, int] = {1: 0x01, 2: 0x02, 3: 0x04}


class Thorlabs_Mpc320(QMI_Instrument):
    """
    Driver for a Thorlabs MPC320 motorised fibre polarisation controller.
    """
    _rpc_constants = [
        "DEFAULT_RESPONSE_TIMEOUT",
        "MIN_POSITION_DEGREES",
        "MAX_POSITION_DEGREES",
        "MIN_VELOCITY_PERC",
        "MAX_VELOCITY_PERC",
    ]

    DEFAULT_RESPONSE_TIMEOUT = 0.5

    # the maximum range for a paddle is 170 degrees
    # the value returned by the encoder is 1370 for 170 degrees
    ENCODER_CONVERSION_UNIT = 170 / 1370

    MIN_POSITION_DEGREES = 0
    MAX_POSITION_DEGREES = 170

    MIN_VELOCITY_PERC = 10
    MAX_VELOCITY_PERC = 100

    NUMBER_OF_CHANNELS = 3

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "rtscts": True})
        assert isinstance(self._transport, QMI_SerialTransport)
        self._apt_protocol = AptProtocol(self._transport, default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)

    def _validate_position(self, pos: float) -> None:
        """
        Validate the position. Any position for the MPC320 needs to be in the range 0 to 170 degrees,
        or 0 to 1370 in encoder counts.

        Parameters:
            pos:    Position to validate in degrees.

        Raises:
            QMI_InstrumentException: If the position is invalid.
        """
        if not self.MIN_POSITION_DEGREES <= pos <= self.MAX_POSITION_DEGREES:
            raise QMI_InstrumentException(
                f"Given position {pos} is outside the valid range \
                    [{self.MIN_POSITION_DEGREES}, {self.MAX_POSITION_DEGREES}]"
            )

    def _validate_velocity(self, vel: float) -> None:
        """
        Validate the velocity. Any velocity for the MPC320 needs to be in the range 40 to 400 degrees/s,
        or 10 to 100% of 400 degrees/s.

        Parameters:
            vel:    Velocity to validate in percentage.

        Raises:
            QMI_InstrumentException: if the velocity is invalid.
        """
        if not self.MIN_VELOCITY_PERC <= vel <= self.MAX_VELOCITY_PERC:
            raise QMI_InstrumentException(
                f"Given relative velocity {vel} is outside the valid range \
                    [{self.MIN_VELOCITY_PERC}%, {self.MAX_VELOCITY_PERC}%]"
            )

    def _validate_channel(self, channel_number: int) -> None:
        """
        Validate the channel number. The MPC320 has 3 channels.

        Parameters:
            channel_number: Channel number to validate.

        Raises:
            QMI_InstrumentException: If the channel is not 1, 2 or 3
        """

        if channel_number not in range(1, self.NUMBER_OF_CHANNELS + 1):
            raise QMI_InstrumentException(
                f"Given channel {channel_number} is not in the valid range \
                    [1, {self.NUMBER_OF_CHANNELS}]"
            )

    def _is_move_complete(self, channel: int, timeout: float) -> bool:
        """Wait until the motor has stopped moving.

        If the motor is not currently moving, this function returns immediately.
        Otherwise, this function wait (blocks) until the motor has stopped moving
        or until the specified timeout expires.

        Parameters:
            channel: The channel number to check.
            timeout: Maximum time to wait in seconds.

        Returns:
            Boolean: To indicate if the move was finished or not.
        """
        end_time = time.monotonic() + timeout

        # Read the motor status to see if we are moving.
        status = self.get_status_update(channel)
        if status.velocity == 0 or status.motor_current == 0:
            # Not moving anymore. We are done here.
            _logger.debug("[%s] Not moving", self._name)
            return True

        # Check if we reached the timeout.
        time_left = end_time - time.monotonic()
        if time_left <= 0:
            return False

        # Wait for a short while, or until the motor sends a new message.
        try:
            msg = self._apt_protocol.read_message(timeout=min(self.DEFAULT_RESPONSE_TIMEOUT, time_left))
        except QMI_TimeoutException:
            # No message from the motor.
            # This is normal and expected if the motor is still moving.
            return False

        # Any message from the motor is most likely an announcement that
        # the move has ended. Whatever the actual message, return True
        _logger.debug("[%s] Ignoring message %s (message_id=0x%04x)",
                      self._name, type(msg).__name__, msg.MESSAGE_ID)

        return True

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
        req_msg = self._apt_protocol.create(APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_REQ_INFO.value])
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_GET_INFO.value]
        )
        resp = self._apt_protocol.ask(req_msg, reply_msg)

        return QMI_InstrumentIdentification("Thorlabs", resp.model_number, resp.serial_number, resp.fw_version)

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
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_IDENTIFY.value],
            chan_ident=1,
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def enable_channels(self, channel_numbers: list[int]) -> None:
        """
        Enable the channel(s). Note that this method will disable any channel that is not provided as an argument. For
        example, if you enable channel 1, then 2 and 3 will be disabled. If you have previously enabled a channel(s)
        and fail to include it/them again in this call, that channel(s) will be disabled. For example, if you run the
        following:
        self.enable_channel([1])
        self.enable_channel([2])
        only channel 2 will be enabled and 1 and 3 will be disabled.
        The correct way to call this method in this case is
        self.enable_channel([1,2])

        Parameters:
            channel_numbers: The channel(s) to enable.
        """
        _logger.info("[%s] Enabling channel(s) %s", self._name, str(channel_numbers))
        self._check_is_open()
        for channel_number in channel_numbers:
            self._validate_channel(channel_number)
        # Make hexadecimal value for channels
        channels_to_enable = 0x00
        for channel_number in channel_numbers:
            channels_to_enable ^= Thorlabs_Mpc320_ChannelMap[channel_number]
        # Send message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_SET_CHANENABLESTATE.value],
            chan_ident=channels_to_enable,
            enable_state=AptChannelState.ENABLE.value
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def disable_all_channels(self) -> None:
        """
        Disable all the channels. Note that this is done indirectly by "enabling"
        channel 0, which disables channels 1, 2 and 3.
        """
        _logger.info("[%s] Disabling channels", self._name)
        self._check_is_open()
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_SET_CHANENABLESTATE.value],
            chan_ident=0x00,
            enable_state=AptChannelState.ENABLE.value,
        )
        self._apt_protocol.send_message(req_msg)

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
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_REQ_CHANENABLESTATE.value],
            chan_ident=Thorlabs_Mpc320_ChannelMap[channel_number]
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_GET_CHANENABLESTATE.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        if resp.enable_state == AptChannelState.ENABLE.value:
            return AptChannelState.ENABLE
        elif resp.enable_state == AptChannelState.DISABLE.value:
           return AptChannelState.DISABLE
        else:
            raise ValueError(f"{resp.enable_state} is not a valid channel enable state.")

    @rpc_method
    def start_auto_status_update(self) -> None:
        """
        Start automatic status updates from device.
        """
        _logger.info("[%s] Starting automatic status updates from instrument", self._name)
        self._check_is_open()
        # Send message.
        req_msg = self._apt_protocol.create(APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_START_UPDATEMSGS.value])
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def stop_auto_status_update(self) -> None:
        """
        Stop automatic status updates from device.
        """
        _logger.info("[%s] Stopping automatic status updates from instrument", self._name)
        self._check_is_open()
        # Send message.
        req_msg = self._apt_protocol.create(APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_STOP_UPDATEMSGS.value])
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def home_channel(self, channel_number: int) -> None:
        """
        Start the homing sequence for a given channel.
        After running this command, you must clear the buffer by checking if the channel
        was homed, using is_channel_homed()

        Parameters:
            channel_number: The channel to home.
        """
        _logger.info("[%s] Homing channel %d", self._name, channel_number)
        self._validate_channel(channel_number)
        self._check_is_open()
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_HOME.value],
            chan_ident=Thorlabs_Mpc320_ChannelMap[channel_number],
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def is_channel_homed(self, channel_number: int, timeout: float = DEFAULT_RESPONSE_TIMEOUT) -> bool:
        """
        Check if a given channel is homed. This command should only be run after the method `home_channel`.
        Otherwise you will read bytes from other commands using this method.

        Parameters:
            channel_number: The channel to check.
            timeout:        The time to wait for a response to the homing command
                            with default value DEFAULT_RESPONSE_TIMEOUT.

        Returns:
            boolean: True if the channel was homed.
        """
        _logger.info("[%s] Checking if channel %d is homed", self._name, channel_number)
        self._validate_channel(channel_number)
        self._check_is_open()

        return self._is_move_complete(channel_number, timeout)

    @rpc_method
    def move_absolute(self, channel_number: int, position: float) -> None:
        """
        Move a channel to the specified position. The specified position is in degrees. A conversion is done to convert
        this into encoder counts. This means that there may be a slight mismatch in the specified position and the
        actual position. You may use the `get_status_update` method to get the actual position or use
        `is_move_completed` to wait until the move is finished.

        Parameters:
            channel_number: The channel to address.
            position:       Absolute position to move to in degrees.
        """
        _logger.info("[%s] Moving channel %d", self._name, channel_number)
        self._validate_channel(channel_number)
        self._validate_position(position)
        self._check_is_open()
        # Convert position in degrees to encoder counts.
        encoder_position = round(position / self.ENCODER_CONVERSION_UNIT)
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_ABSOLUTE.value],
            chan_ident=Thorlabs_Mpc320_ChannelMap[channel_number],
            abs_position=encoder_position,
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def is_move_completed(self, channel_number: int, timeout: float = DEFAULT_RESPONSE_TIMEOUT) -> bool:
        """
        Check if a given channel has completed its move. This command should only be run after a relative or absolute
        move command. Otherwise you will read bytes from other commands.

        NOTE: If the `is_move_completed` call is used in a loop to check the move status until a move is
              finished (i.e. returns `True`), it is better to have a short time.sleep (0.01 seconds should
              suffice) in between the `is_move_completed` calls. Polling too fast seems to cause issues.

        Parameters:
            channel_number: The channel to check.
            timeout:        The time to wait for a response to the homing command. This is optional
                            and is set to a default value of DEFAULT_RESPONSE_TIMEOUT.

        Returns:
            boolean: True if the move for the channel was completed.
        """
        _logger.info(
            "[%s] Checking if channel %d has completed its move",
            self._name,
            channel_number,
        )
        self._validate_channel(channel_number)
        self._check_is_open()

        return self._is_move_complete(channel_number, timeout)

    @rpc_method
    def save_parameter_settings(self, channel_number: int, message_id: int) -> None:
        """
        Save parameter settings for a specific message id. These parameters could have been edited via the QMI driver
        or the GUI provided by Thorlabs.

        Parameters:
            channel_number: The channel to address.
            message_id:     ID of message whose parameters need to be saved.
                            Must be provided as a hex number e.g. 0x04B6
        """
        _logger.info("[%s] Saving parameters of message %d", self._name, message_id)
        self._check_is_open()
        self._validate_channel(channel_number)
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_SET_EEPROMPARAMS.value],
            chan_ident=Thorlabs_Mpc320_ChannelMap[channel_number],
            msg_id=message_id,
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def get_status_update(self, channel_number: int) -> Thorlabs_Mpc320_Status:
        """
        Get the status update for a given channel. This call will return the position, velocity, motor current and
        status of the channel.

        Parameters:
            channel_number: The channel to query.

        Returns:
            status: An instance of Thorlabs_MPC320_Status.
        """
        _logger.info("[%s] Getting position counter of channel %d", self._name, channel_number)
        self._check_is_open()
        self._validate_channel(channel_number)
        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_USTATUSUPDATE.value],
            chan_ident=Thorlabs_Mpc320_ChannelMap[channel_number]
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_USTATUSUPDATE.value]
        )
        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        return Thorlabs_Mpc320_Status(
            channel=channel_number,
            position=resp.position * self.ENCODER_CONVERSION_UNIT,
            velocity=resp.velocity,
            motor_current=resp.motor_current,
        )

    @rpc_method
    def jog(
        self,
        channel_number: int,
        direction: AptChannelJogDirection = AptChannelJogDirection.FORWARD,
    ) -> None:
        """
        Move a channel specified by its jog step.

        Parameters:
            channel_number: The channel to jog.
            direction:      The direction to jog. This can either be forward or backward. Default is forward.
        """
        _logger.info("[%s] Getting position counter of channel %d", self._name, channel_number)
        self._check_is_open()
        self._validate_channel(channel_number)
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_JOG.value],
            chan_ident=Thorlabs_Mpc320_ChannelMap[channel_number],
            direction=direction.value,
        )
        self._apt_protocol.send_message(req_msg)

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
            velocity:   Velocity in range 10% to 100% of 400 degrees/s.
            home_pos:   Home position in degrees.
            jog_step1:  Size of jog step for paddle 1.
            jog_step2:  Size of jog step for paddle 2.
            jog_step3:  Size of jog step for paddle 3.
        """
        _logger.info("[%s] Setting polarisation parameters", self._name)
        self._check_is_open()
        # Validate parameters.
        self._validate_velocity(velocity)
        self._validate_position(home_pos)
        self._validate_position(jog_step1)
        self._validate_position(jog_step2)
        self._validate_position(jog_step3)
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.POL_SET_PARAMS.value],
            not_used=0x00,
            velocity=velocity,
            home_position=round(home_pos / self.ENCODER_CONVERSION_UNIT),
            jog_step1=round(jog_step1 / self.ENCODER_CONVERSION_UNIT),
            jog_step2=round(jog_step2 / self.ENCODER_CONVERSION_UNIT),
            jog_step3=round(jog_step3 / self.ENCODER_CONVERSION_UNIT),
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def get_polarisation_parameters(self) -> Thorlabs_Mpc320_PolarisationParameters:
        """
        Get the polarisation parameters.

        Returns:
            parameters: An instance of Thorlabs_Mpc320_PolarisationParameters.
        """
        _logger.info("[%s] Getting polarisation parameters", self._name)
        self._check_is_open()
        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.POL_REQ_PARAMS.value],
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.POL_GET_PARAMS.value]
        )
        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        return Thorlabs_Mpc320_PolarisationParameters(
            velocity=resp.velocity,
            home_position=resp.home_position * self.ENCODER_CONVERSION_UNIT,
            jog_step1=resp.jog_step1 * self.ENCODER_CONVERSION_UNIT,
            jog_step2=resp.jog_step2 * self.ENCODER_CONVERSION_UNIT,
            jog_step3=resp.jog_step3 * self.ENCODER_CONVERSION_UNIT,
        )
