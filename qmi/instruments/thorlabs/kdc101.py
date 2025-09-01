"""Instrument driver for the Thorlabs KDC101 Brushed DC Servo Motor Controller.

This driver communicates with the device via a USB serial port, using the Thorlabs APT protocol. For details,
see the document "Thorlabs APT Controllers Host-Controller Communications Protocol", issue 41 from Thorlabs.
"""

import logging
import time

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport, QMI_SerialTransport
from qmi.instruments.thorlabs.apt_packets import AptMessageId
from qmi.instruments.thorlabs.apt_protocol import (
    APT_MESSAGE_TYPE_TABLE,
    AptChannelHomeDirection,
    AptChannelHomeLimitSwitch,
    AptProtocol,
    AptChannelState,
    AptChannelStopMode,
    VelocityParams,
    HomeParams,
    MotorStatus,
)

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Thorlabs_Kdc101(QMI_Instrument):
    """Instrument driver for the Thorlabs KDC101 Brushed DC Servo Motor Controller. This driver should be
    compatible also with TDC001 and KVS30 controllers.

    This controller can be used with Z9 series 6mm, 12mm and 25mm linear actuators.
    An adaptation of the driver could be made in the future to also allow the use of the linear translation and
    rotation stages, and goniometers.
    """
    _rpc_constants = ["RESPONSE_TIMEOUT"]

    RESPONSE_TIMEOUT = 1.0

    # Z9 series motors: Number of rotations per 1.0mm lead screw displacement.
    ROTATIONS_PER_MM = 67.49

    # Encoder counts per revolution of the lead screw.
    ENCODER_COUNTS_PER_ROTATION = 512 * ROTATIONS_PER_MM

    # Linear displacement of the lead screw per encoder count
    DISPLACEMENT_PER_ENCODER_COUNT = 1.0 / ENCODER_COUNTS_PER_ROTATION

    # Sampling interval constant for KDC101, as described in p. 39 of documentation
    T = 2048 / 6E6

    # Maximum velocity for controlled profiles
    MAX_VELOCITY = 2.3  # 2.6 if "ripples" are allowed in the move profile.
    # Velocity scaling factor, VEL_APT = EncCnt × T × 65536 × Vel, where T = 2048 / (6 × 10^6).
    VELOCITY_SCALING_FACTOR = 772981.3692 * T * 65536

    # Maximum acceleration
    MAX_ACCELERATION = 4.0
    # Acceleration scaling factor, ACC_APT = EncCnt × T^2 × 65536 × Acc, where T = 2048 / (6 × 10^6).
    ACCELERATION_SCALING_FACTOR = 263.8443072 * T * 65536  # Using T**2 gives acc readout that is out-of-range!

    # Number of channels
    NUMBER_OF_CHANNELS = 1

    ACTUATOR_TRAVEL_RANGES = {
        "Z906": 6.0,
        "Z912": 12.0,
        "Z925": 25.0
    }

    def __init__(self, context: QMI_Context, name: str, transport: str, actuator: str) -> None:
        """Initialize driver.

        The motorized mount presents itself as a USB serial port.
        The transport descriptor should refer to the serial port device,
        e.g. "serial:/dev/ttyUSB1"

        Parameters:
            name:      Name for this instrument instance.
            transport: Transport descriptor to access the instrument.
            actuator:  The actuator model. For this driver, currently allowed models are:
                       Z906, Z906V, Z912, Z912B, Z912V, Z912BV, Z925B and Z925BV.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "rtscts": True})
        assert isinstance(self._transport, QMI_SerialTransport)
        self._apt_protocol = AptProtocol(self._transport, default_timeout=self.RESPONSE_TIMEOUT)
        try:
            self._travel_range = self.ACTUATOR_TRAVEL_RANGES[actuator[:4]]
        except KeyError:
            raise NotImplementedError(f"Actuator type {actuator} has not been implemented")

    def _check_kdc101(self) -> None:
        """Check that the connected device is a Thorlabs KDC101.

        Raises:
            QMI_InstrumentException: If not connected to a KDC101 device.
            QMI_TimeoutException:    If the instrument does not answer our request.
        """
        # Send request message.
        req_msg = self._apt_protocol.create(APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_REQ_INFO.value])
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_GET_INFO.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)

        # Check that this is a KDC101 device.
        model_str = resp.model_number.decode("iso8859-1")
        if model_str != "KDC101":
            raise QMI_InstrumentException(
                f"Driver only supports KDC101 but instrument identifies as {model_str!r}"
            )

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()

        try:
            # Wait and discard partial data, as recommended by the APT protocol documentation.
            time.sleep(0.050)
            self._transport.discard_read()
            self._check_kdc101()

        except Exception:
            # Close the transport if an error occurred during initialization of the instrument.
            self._transport.close()
            raise

        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_REQ_INFO.value])
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_GET_INFO.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        fw_version = str(resp.fw_version)

        return QMI_InstrumentIdentification(
            vendor="Thorlabs",
            model=resp.model_number.decode("iso8859-1"),
            serial=resp.serial_number,
            version="{}.{}.{}".format(fw_version[2], fw_version[1], fw_version[0])
        )

    @rpc_method
    def get_motor_status(self) -> MotorStatus:
        """Return the motor status bits.

        Returns:
            MotorStatus: The received motor status bits.
        """
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_STATUS_BITS.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_STATUS_BITS.value]
        )
        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)

        # Decode motor status bits.
        status_bits = resp.status_bits
        return MotorStatus(
            forward_limit=((status_bits & 0x01) != 0),
            reverse_limit=((status_bits & 0x02) != 0),
            moving_forward=((status_bits & 0x10) != 0),
            moving_reverse=((status_bits & 0x20) != 0),
            jogging_forward=((status_bits & 0x40) != 0),
            jogging_reverse=((status_bits & 0x80) != 0),
            homing=((status_bits & 0x200) != 0),
            homed=((status_bits & 0x400) != 0),
            tracking=((status_bits & 0x1000) != 0),
            settled=((status_bits & 0x2000) != 0),
            motion_error=((status_bits & 0x4000) != 0),
            current_limit=((status_bits & 0x01000000) != 0),
            channel_enabled=((status_bits & 0x80000000) != 0)
        )

    @rpc_method
    def identify(self) -> None:
        """Make the yellow LED on the instrument flash for a few seconds."""
        self._check_is_open()

        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_IDENTIFY.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def get_chan_enable_state(self) -> bool:
        """Return the enable state of the motor drive channel.

        Returns:
            boolean: True if the channel is enabled, False if the channel is disabled.
        """
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_REQ_CHANENABLESTATE.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_GET_CHANENABLESTATE.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        if resp.enable_state == AptChannelState.ENABLE.value:
            return True
        elif resp.enable_state == AptChannelState.DISABLE.value:
           return False
        else:
            raise ValueError(f"{resp.enable_state} is not a valid channel enable state.")

    @rpc_method
    def set_chan_enable_state(self, enable: bool) -> None:
        """Enable or disable the motor drive channel.

        When the drive channel is disabled, the motor will not hold its
        position and can be moved through external force.

        The drive channel is by default enabled at power-up.

        Parameters:
            enable:  Boolean to indicate new state. True for enable, False for disable.
        """
        self._check_is_open()

        # Send command message.
        enable_state = AptChannelState.ENABLE if enable else AptChannelState.DISABLE
        set_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_SET_CHANENABLESTATE.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            enable_state=enable_state.value,
        )
        self._apt_protocol.send_message(set_msg)

    @rpc_method
    def get_absolute_position(self) -> float:
        """Return the absolute position of the stage in millimeters.

        After power-up, the absolute position of the stage will be
        unknown until the stage is homed. If the stage has not yet
        been homed, this function will return the current position
        relative to the position at power-up.

        Returns:
            position: The absolute position if stage is homed, otherwise relative position. In mm.
        """
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_POS_COUNTER.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_POS_COUNTER.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        return resp.position * self.DISPLACEMENT_PER_ENCODER_COUNT

    @rpc_method
    def get_velocity_params(self) -> VelocityParams:
        """Return the current maximum velocity and acceleration.

        Returns:
            params: Maximum velocity and acceleration in mm/s and mm/s^2, respectively.
        """
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_VEL_PARAMS.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_VEL_PARAMS.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)
        return VelocityParams(
            max_velocity=(resp.max_vel / self.VELOCITY_SCALING_FACTOR),
            acceleration=(resp.accel / self.ACCELERATION_SCALING_FACTOR)
        )

    @rpc_method
    def set_velocity_params(self, max_velocity: float, acceleration: float) -> None:
        """Set the maximum velocity and acceleration.

        These settings will be applied for subsequent absolute and relative moves.

        Parameters:
            max_velocity: Maximum velocity in mm/s.
            acceleration: Acceleration in mm/s^2.
        """
        if not 0 < max_velocity <= self.MAX_VELOCITY:
            raise ValueError(f"Invalid value for {max_velocity=}")
        if not 0 < acceleration <= self.MAX_ACCELERATION:
            raise ValueError(f"Invalid value for {acceleration=}")

        self._check_is_open()

        # Send command message. Note that documentation describes 'min_vel' to be always zero.
        max_vel = int(round(max_velocity * self.VELOCITY_SCALING_FACTOR))
        accel = int(round(acceleration * self.ACCELERATION_SCALING_FACTOR))
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_SET_VEL_PARAMS.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            min_vel=0,
            accel=accel,
            max_vel=max_vel
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def get_backlash_distance(self) -> float:
        """Get the backlash distance.

        Returns:
            backlash_dist: The backlash distance in millimeters.
        """
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_GEN_MOVE_PARAMS.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_GEN_MOVE_PARAMS.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)

        return resp.backlash_dist * self.DISPLACEMENT_PER_ENCODER_COUNT

    @rpc_method
    def set_backlash_distance(self, backlash: float) -> None:
        """Set the backlash distance.

        The backlash distance is used when the stage moves in reverse direction.
        While moving in reverse direction, the stage moves past its target position
        by the backlash distance, then moves back to the target in forward direction.

        Parameters:
            backlash: Backlash distance in millimeters, or 0 to disable.
        """
        # Check that the backlash distance is sensible.
        if abs(backlash) > self._travel_range / 2.0:
            raise ValueError("Backlash distance larger than half of travel range")

        self._check_is_open()

        # Convert distance to microsteps.
        raw_dist = int(round(backlash / self.DISPLACEMENT_PER_ENCODER_COUNT))
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_SET_GEN_MOVE_PARAMS.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            backlash_dist=raw_dist
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def get_home_params(self) -> HomeParams:
        """Return the homing parameters."""
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_HOME_PARAMS.value],
            chan_ident=self.NUMBER_OF_CHANNELS
        )
        reply_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_HOME_PARAMS.value]
        )

        # Receive response
        resp = self._apt_protocol.ask(req_msg, reply_msg)

        return HomeParams(
            home_direction=AptChannelHomeDirection(resp.home_dir),
            limit_switch=AptChannelHomeLimitSwitch(resp.limit_switch),
            home_velocity=(resp.home_velocity / self.VELOCITY_SCALING_FACTOR),
            offset_distance=(resp.offset_dist * self.DISPLACEMENT_PER_ENCODER_COUNT)
        )

    @rpc_method
    def set_home_params(
        self,
        home_velocity: float,
        offset_distance: float
    ) -> None:
        """Set the homing parameters.

        WARNING: The KDC101 manual recommends that these settings should
        not be adjusted from the factory defaults.

        Parameters:
            home_velocity:      Homing velocity in mm/second (max 2.6).
            offset_distance:    Distance of home position from home limit switch (in mm).
        """
        if not 0 < home_velocity <= 2.6:
            raise ValueError(f"Invalid value for {home_velocity=}")
        if not 0 <= offset_distance <= self._travel_range:
            raise ValueError(f"Invalid value for {offset_distance=}")

        self._check_is_open()

        home_direction = AptChannelHomeDirection.REVERSE
        limit_switch = AptChannelHomeLimitSwitch.REVERSE
        # Convert values.
        raw_velocity = int(round(home_velocity * self.VELOCITY_SCALING_FACTOR))
        raw_dist = int(round(offset_distance / self.DISPLACEMENT_PER_ENCODER_COUNT))
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_SET_HOME_PARAMS.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            home_dir=home_direction.value,
            limit_switch=limit_switch.value,
            home_velocity=raw_velocity,
            offset_dist=raw_dist
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def move_stop(self, immediate_stop: bool = False) -> None:
        """Stop any ongoing move operation.

        This function returns immediately while the stage may still be moving.
        Use ``wait_move_complete()`` to wait until the stage has stopped.

        Parameters:
            immediate_stop: True to stop abruptly, False to perform a profiled stop.
        """
        self._check_is_open()

        # Send command message.
        stop_mode = AptChannelStopMode.IMMEDIATE if immediate_stop else AptChannelStopMode.PROFILED
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_STOP.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            stop_mode=stop_mode.value,
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def move_home(self) -> None:
        """Start a homing move.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.
        """
        self._check_is_open()

        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_HOME.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def move_relative(self, distance: float) -> None:
        """Start a relative move.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.

        Parameters:
            distance: Relative move distance in millimeters.
        """
        if abs(distance) > self._travel_range:
            raise ValueError("Relative distance larger than travel range")

        self._check_is_open()

        # Convert distance to microsteps.
        raw_dist = int(round(distance / self.DISPLACEMENT_PER_ENCODER_COUNT))
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_RELATIVE.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            rel_dist=raw_dist
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def move_absolute(self, position: float) -> None:
        """Start a move to an absolute position.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.

        After power-up, the absolute position of the stage will be
        unknown until the stage is homed. If the stage has not yet
        been homed, the position parameter of this function will
        be interpreted relative to the position at power-up.

        Parameters:
            position: Absolute target position in millimeters.
        """
        if not 0.0 <= position <= self._travel_range:
            raise ValueError("Absolute position out of valid range")

        self._check_is_open()

        # Convert distance to microsteps.
        raw_pos = int(round(position / self.DISPLACEMENT_PER_ENCODER_COUNT))
        # Send command message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_MOVE_ABSOLUTE.value],
            chan_ident=self.NUMBER_OF_CHANNELS,
            abs_position=raw_pos,
        )
        self._apt_protocol.send_message(req_msg)

    @rpc_method
    def wait_move_complete(self, timeout: float) -> None:
        """Wait until the motor has stopped moving.

        If the motor is not currently moving, this function returns immediately.
        Otherwise, this function wait (blocks) until the motor has stopped moving
        or until the specified timeout expires.

        Parameters:
            timeout: Maximum time to wait in seconds.

        Raises:
            QMI_TimeoutException: If the motor is still moving when the timeout expires.
        """
        self._check_is_open()
        _logger.debug("[%s] wait_move_complete(%f)", self._name, timeout)

        end_time = time.monotonic() + timeout

        while True:
            # Read the motor status to see if we are moving.
            status = self.get_motor_status()
            if (not (status.moving_forward
                     or status.moving_reverse
                     or status.jogging_forward
                     or status.jogging_reverse
                     or status.homing)):
                # Not moving anymore. We are done here.
                _logger.debug("[%s] Not moving", self._name)
                return

            # Check if we reached the timeout.
            time_left = end_time - time.monotonic()
            if time_left <= 0:
                raise QMI_TimeoutException("Timeout while waiting for end of move")

            # Wait for a short while, or until the motor sends a new message.
            try:
                msg = self._apt_protocol.read_message(timeout=min(self.RESPONSE_TIMEOUT, time_left))
            except QMI_TimeoutException:
                # No message from the motor.
                # This is normal and expected if the motor is still moving.
                # Go around the loop again and poll the motor status.
                time.sleep(0.01)
                continue

            # Any message from the motor is most likely an announcement that
            # the move has ended. Whatever the actual message, go around
            # the loop and poll the motor status again.
            _logger.debug("[%s] Ignoring message %s (message_id=0x%04x)",
                          self._name, type(msg).__name__, msg.message_id)
