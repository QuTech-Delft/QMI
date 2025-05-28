"""Instrument driver for the Thorlabs K10CR1/M motorized rotational mount.

This driver communicates with the device via a USB serial port,
using the Thorlabs APT protocol. For details, see the document
"Thorlabs APT Controllers Host-Controller Communications Protocol",
issue 25 from Thorlabs.

This driver has only been tested under Linux. In principle it should also
work under Windows, but that would require somehow creating a virtual COM port
for the internal USB serial port in the instrument.
"""

import ctypes
import contextlib
import enum
import logging
import time
from typing import Any, ClassVar, NamedTuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.instruments.thorlabs.apt_protocol import AptProtocol, _AptMessage, APT_MESSAGE_TYPE_TABLE, AptMessageId

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


_APT_HOST_ADDRESS = 0x01    # Address of the computer in the APT protocol.
_APT_DEVICE_ADDRESS = 0x50  # Address of the device in the APT protocol.


class _AptMessageHeader(_AptMessage):
    """Generic message header for the APT protocol.

    This is also the base class for long messages (header + data).
    """
    _pack_ = 1
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ('message_id',  ctypes.c_uint16),
        ('data_length', ctypes.c_uint16),
        ('dest',        ctypes.c_uint8),
        ('source',      ctypes.c_uint8)
    ]


def _apt_short_message_fields(fields: list[tuple[str, type]]) -> list[tuple[str, type]]:
    """Helper function to create the field list for a short APT message.

    The message consists of only a 6-byte header, including 2 bytes space
    for optional parameter fields.
    """

    # APT short message format:
    #   2 bytes:  uint16  message_id
    #   2 bytes:  uint16  data_length
    #   1 byte:           param1
    #   1 byte:           param2
    #   1 byte:   uint8   dest
    #   1 byte:   uint8   source

    # Calculate size of data fields.
    data_length = 0
    for (par_name, par_type) in fields:
        data_length += ctypes.sizeof(par_type)
    assert data_length <= 2

    # Build field list for ctypes structure.
    all_fields: list[tuple[str, type]] = []
    all_fields.append(("message_id", ctypes.c_uint16))
    all_fields += fields
    if data_length < 2:
        # Add dummy field if the message uses fewer than 2 bytes for parameters.
        all_fields.append(("_dummy", (2 - data_length) * ctypes.c_uint8))
    all_fields.append(("dest", ctypes.c_uint8))
    all_fields.append(("source", ctypes.c_uint8))

    return all_fields



class VelocityParams(NamedTuple):
    """Velocity parameters for the K10CR1.

    Attributes:
        max_velocity:    Maximum velocity in degrees/second.
        acceleration:    Acceleration in degrees/second/second.
    """
    max_velocity: float
    acceleration: float


class HomeDirection(enum.IntEnum):
    """Possible values for the ``home_direction`` field in the homing parameters."""
    FORWARD = 1
    REVERSE = 2


class HomeLimitSwitch(enum.IntEnum):
    """Possible values for the ``limit_switch`` field in the homing parameters."""
    REVERSE = 1
    FORWARD = 4


class HomeParams(NamedTuple):
    """Homing parameters for the K10CR1.

    Attributes:
        home_direction:  Direction of moving to home (1 = forward, 2 = reverse).
        limit_switch:    Limit switch to use for homing (1 = reverse, 4 = forward).
        home_velocity:   Homing velocity in degrees/second.
        offset_distance: Distance of home postion from home limit switch (in degrees).
    """
    home_direction:     HomeDirection
    limit_switch:       HomeLimitSwitch
    home_velocity:      float
    offset_distance:    float


class MotorStatus(NamedTuple):
    """Status bits of the K10CR1 motorized stage.

    Some of the status bits do not seem to work with the K10CR1.

    Attributes:
        moving_forward:     True if the motor is moving in forward direction.
        moving_reverse:     True if the motor is moving in reverse direction.
                            It looks like `move_forward` and `move_reverse` are both
                            active when the stage is moving, regardless of the actual
                            direction of movement.
        jogging_forward:    True if the motor is jogging in forward direction.
        jogging_reverse:    True if the motor is jogging in reverse direction.
                            It looks like `jogging_reverse` is also active when jogging
                            in forward direction, while `jogging_forward` is never active.
        homing:             True if the motor is homing.
        homed:              True if homing has been completed.
        motion_error:       True if an excessive position error is detected.
        current_limit:      True if the motor current limit has been reached.
        channel_enabled:    True if the motor drive channel is enabled.
    """
    forward_limit:      bool
    reverse_limit:      bool
    moving_forward:     bool
    moving_reverse:     bool
    jogging_forward:    bool
    jogging_reverse:    bool
    homing:             bool
    homed:              bool
    tracking:           bool
    settled:            bool
    motion_error:       bool
    current_limit:      bool
    channel_enabled:    bool


class Thorlabs_K10CR1(QMI_Instrument):
    """Instrument driver for the Thorlabs K10CR1/M motorized rotational mount."""

    DEFAULT_RESPONSE_TIMEOUT = 1.0

    # Number of microsteps per degree of rotation.
    MICROSTEPS_PER_DEGREE = 409600.0 / 3.0

    # Internal velocity setting for 1 degree/second.
    VELOCITY_FACTOR = 7329109.0

    # Internal acceleration setting for 1 degree/second/second.
    ACCELERATION_FACTOR = 1502.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver.

        The motorized mount presents itself as a USB serial port.
        The transport descriptor should refer to the serial port device,
        e.g. "serial:/dev/ttyUSB1"

        Parameters:
            name: Name for this instrument instance.
            transport: Transport descriptor to access the instrument.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"baudrate": 115200, "rtscts": True})
        self._apt_protocol = AptProtocol(self._transport, default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)

        # Expect a reply to normal commands within 1 second.
        self._reply_timeout = 1.0

        # The APT protocol supports multiple channels.
        # The K10CR1 only uses channel 1.
        self._channel = 1

    def _send_message(self, msg: _AptMessage) -> None:
        """Encode and send a binary message to the instrument."""
        # Before sending a new command, do a non-blocking read to consume
        # a potential old message from the instrument.
        # This prevents a buildup of unhandled notification messages from
        # the instrument after several move_XXX() commands.
        # Suppress the timeout exception if no old message is in the buffer.
        with contextlib.suppress(QMI_TimeoutException):
            pending_msg = self._apt_protocol._read_message(timeout=0.0)
            _logger.debug("[%s] Pending message %s (message_id=0x%04x)",
                          self._name, type(pending_msg).__name__, pending_msg.message_id)

        # Now send the new command.
        self._apt_protocol._send_message(msg)

    def _check_k10cr1(self) -> None:
        """Check that the connected device is a Thorlabs K10CR1.

        Raises:
            QMI_InstrumentException: If not connected to a K10CR1 device.
            QMI_TimeoutException: If the instrument does not answer our request.
        """

        # Send request message.
        req_msg = self._apt_protocol.create(APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_REQ_INFO.value])
        reply_msg = APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_GET_INFO.value]
        self._send_message(req_msg)

        # Receive response
        reply_msg = self._apt_protocol._wait_message(reply_msg, timeout=self._reply_timeout)

        # Check that this is a K10CR1 device.
        model_str = reply_msg.model_number.decode("iso8859-1")
        if model_str != "K10CR1":
            raise QMI_InstrumentException(
                "Driver only supports K10CR1 but instrument identifies as {!r}".format(model_str)
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

            # NOTE: The APT doc says we should wait another 50 ms and then enable RTS.
            #   We can not easily do this because our transport layer does not support explicit set/clear RTS.
            #   Skip this step for now; we can try it later if there are communication problems.

            # Check that this device is a K10CR1 motor.
            # Otherwise we should not talk to it, since we don't want to send
            # inappropriate commands to some unsupported device.
            self._check_k10cr1()

        except Exception:
            # Close the transport if an error occurred during initialization
            # of the instrument.
            self._transport.close()
            raise

        # Mark this instrument as open.
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
        reply_msg = APT_MESSAGE_TYPE_TABLE[AptMessageId.HW_GET_INFO.value]
        self._send_message(req_msg)

        # Receive response.
        resp = self._apt_protocol._wait_message(reply_msg, timeout=self._reply_timeout)

        return QMI_InstrumentIdentification(
            vendor="Thorlabs",
            model=resp.model_number.decode("iso8859-1"),
            serial=resp.serial_number,
            version="{}.{}.{}".format(resp.fw_version[2], resp.fw_version[1], resp.fw_version[0])
        )

    @rpc_method
    def get_motor_status(self) -> MotorStatus:
        """Return the motor status bits."""
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_REQ_STATUS_BITS.value],
            chan_ident=self._channel
        )
        reply_msg = APT_MESSAGE_TYPE_TABLE[AptMessageId.MOT_GET_STATUS_BITS.value]
        self._send_message(req_msg)

        # Receive response
        resp = self._wait_message(reply_msg, timeout=self._reply_timeout)

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
            chan_ident=self._channel
        )
        self._send_message(req_msg)

    @rpc_method
    def get_chan_enable_state(self) -> bool:
        """Return the enable state of the motor drive channel."""
        self._check_is_open()

        # Send request message.
        req_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_REQ_CHANENABLESTATE.value],
            chan_ident=self._channel
        )
        reply_msg = APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_GET_CHANENABLESTATE.value]
        self._send_message(req_msg)

        # Receive response
        resp = self._wait_message(reply_msg, timeout=self._reply_timeout)
        return resp.enable_state == 0x01

    @rpc_method
    def set_chan_enable_state(self, enable: bool) -> None:
        """Enable or disable the motor drive channel.

        When the drive channel is disabled, the motor will not hold its
        position and can be moved through external force.

        The drive channel is by default enabled at power-up.
        """
        self._check_is_open()

        # Send command message.
        # TODO: Use enumerator
        enable_state = 0x01 if enable else 0x02
        set_msg = self._apt_protocol.create(
            APT_MESSAGE_TYPE_TABLE[AptMessageId.MOD_SET_CHANENABLESTATE.value],
            chan_ident=self._channel, enable_state=enable_state
        )
        self._send_message(set_msg)

    @rpc_method
    def get_absolute_position(self) -> float:
        """Return the absolute position of the stage in degrees.

        After power-up, the absolute position of the stage will be
        unknown until the stage is homed. If the stage has not yet
        been homed, this function will return the current position
        relative to the position at power-up.

        Note that the absolute position can exceed the range of
        -360 .. +360 degrees when the stage has rotated a full turn.
        The absolute position counter overflows after 43 full turns
        and may then return incorrect results.
        """
        self._check_is_open()

        # Send request message.
        req_msg = _AptMsgReqPosCounter.create(chan_ident=self._channel)
        self._send_message(req_msg)

        # Receive response
        reply_msg = self._wait_message(_AptMsgGetPosCounter, timeout=self._reply_timeout)
        return reply_msg.position / self.MICROSTEPS_PER_DEGREE

    @rpc_method
    def get_velocity_params(self) -> VelocityParams:
        """Return the current maximum velocity and acceleration."""

        self._check_is_open()

        # Send request message.
        req_msg = _AptMsgReqVelParams.create(chan_ident=self._channel)
        self._send_message(req_msg)

        # Receive response
        reply_msg = self._wait_message(_AptMsgGetVelParams, timeout=self._reply_timeout)
        return VelocityParams(
            max_velocity=(reply_msg.max_vel / self.VELOCITY_FACTOR),
            acceleration=(reply_msg.accel / self.ACCELERATION_FACTOR)
        )

    @rpc_method
    def set_velocity_params(self, max_velocity: float, acceleration: float) -> None:
        """Set the maximum velocity and acceleration.

        These settings will be applied for subsequent absolute and relative moves.

        Parameters:
            max_velocity: Maximum velocity in degrees/second (max 10).
            acceleration: Acceleration in degree/second/second (max 20).
        """

        if max_velocity <= 0 or max_velocity > 10:
            raise ValueError("Invalid range for max_velocity")
        if acceleration <= 0 or acceleration > 20:
            raise ValueError("Invalid range for acceleration")

        self._check_is_open()

        # Send command message.
        max_vel = int(round(max_velocity * self.VELOCITY_FACTOR))
        accel = int(round(acceleration * self.ACCELERATION_FACTOR))
        req_msg = _AptMsgSetVelParams.create(
            chan_ident=self._channel,
            min_vel=0,
            accel=accel,
            max_vel=max_vel
        )
        self._send_message(req_msg)

    @rpc_method
    def get_backlash_distance(self) -> float:
        """Return the backlash distance in degrees."""

        self._check_is_open()

        # Send request message.
        req_msg = _AptMsgReqGenMoveParams.create(chan_ident=self._channel)
        self._send_message(req_msg)

        # Receive response
        reply_msg = self._wait_message(_AptMsgGetGenMoveParams, timeout=self._reply_timeout)
        return reply_msg.backlash_dist / self.MICROSTEPS_PER_DEGREE

    @rpc_method
    def set_backlash_distance(self, backlash: float) -> None:
        """Set the backlash distance.

        The backlash distance is used when the stage moves in reverse direction.
        While moving in reverse direction, the stage moves past its target position
        by the backlash distance, then moves back to the target in forward direction.

        Parameters:
            backlash: Backlash distance in degrees, or 0 to disable.
        """

        # Convert distance to microsteps and check that the value fits in a 32-bit signed integer.
        raw_dist = int(round(backlash * self.MICROSTEPS_PER_DEGREE))
        if abs(raw_dist) >= 2**31:
            raise ValueError("Backlash distance out of valid range")

        self._check_is_open()

        # Send command message.
        req_msg = _AptMsgSetGenMoveParams.create(chan_ident=self._channel, backlash_dist=raw_dist)
        self._send_message(req_msg)

    @rpc_method
    def get_home_params(self) -> HomeParams:
        """Return the homing parameters."""

        self._check_is_open()

        # Send request message.
        req_msg = _AptMsgReqHomeParams.create(chan_ident=self._channel)
        self._send_message(req_msg)

        # Receive response
        reply_msg = self._wait_message(_AptMsgGetHomeParams, timeout=self._reply_timeout)
        return HomeParams(
            home_direction=HomeDirection(reply_msg.home_dir),
            limit_switch=HomeLimitSwitch(reply_msg.limit_switch),
            home_velocity=(reply_msg.home_velocity / self.VELOCITY_FACTOR),
            offset_distance=(reply_msg.offset_dist / self.MICROSTEPS_PER_DEGREE)
        )

    @rpc_method
    def set_home_params(
        self,
        home_direction: HomeDirection,
        limit_switch: HomeLimitSwitch,
        home_velocity: float,
        offset_distance: float
    ) -> None:
        """Set the homing parameters.

        WARNING: The K10CR1 manual recommends that these settings should
        not be adjusted from the factory defaults.

        Parameters:
            home_direction:     Direction of moving to home (should be HomeDirection.REVERSE).
            limit_switch:       Limit switch to use for homing (should be HomeLimitSwitch.REVERSE).
            home_velocity:      Homing velocity in degrees/second (max 5).
            offset_distance:    Distance of home position from home limit switch (in degrees).
        """

        if home_direction not in (HomeDirection.FORWARD, HomeDirection.REVERSE):
            raise ValueError("Invalid value for home_direction")
        if limit_switch not in (HomeLimitSwitch.FORWARD, HomeLimitSwitch.REVERSE):
            raise ValueError("Invalid value for limit_switch")
        if home_velocity <= 0 or home_velocity > 5:
            raise ValueError("Invalid range for home_velocity")

        # Convert distance to microsteps and check that the value fits in a 32-bit signed integer.
        raw_dist = int(round(offset_distance * self.MICROSTEPS_PER_DEGREE))
        if abs(raw_dist) >= 2**31:
            raise ValueError("Invalid range for offset_distance")

        self._check_is_open()

        # Send command message.
        raw_velocity = int(round(home_velocity * self.VELOCITY_FACTOR))
        req_msg = _AptMsgSetHomeParams.create(
            chan_ident=self._channel,
            home_dir=int(home_direction),
            limit_switch=int(limit_switch),
            home_velocity=raw_velocity,
            offset_dist=raw_dist
        )
        self._send_message(req_msg)

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
        stop_mode = 0x01 if immediate_stop else 0x02
        req_msg = _AptMsgMoveStop.create(chan_ident=self._channel, stop_mode=stop_mode)
        self._send_message(req_msg)

    @rpc_method
    def move_home(self) -> None:
        """Start a homing move.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.
        """
        self._check_is_open()

        # Send command message.
        req_msg = _AptMsgMoveHome.create(chan_ident=self._channel)
        self._send_message(req_msg)

    @rpc_method
    def move_relative(self, distance: float) -> None:
        """Start a relative move.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.

        Parameters:
            distance: Relative move distance in degrees.
        """

        # Convert distance to microsteps and check that the value fits in a 32-bit signed integer.
        raw_dist = int(round(distance * self.MICROSTEPS_PER_DEGREE))
        if abs(raw_dist) >= 2**31:
            raise ValueError("Relative distance out of valid range")

        self._check_is_open()

        # Send command message.
        req_msg = _AptMsgMoveRelative.create(chan_ident=self._channel, rel_dist=raw_dist)
        self._send_message(req_msg)

    @rpc_method
    def move_absolute(self, position: float) -> None:
        """Start a move to an absolute position.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.

        After power-up, the absolute position of the stage will be
        unknown until the stage is homed. If the stage has not yet
        been homed, the position parameter of this function will
        be interpreted relative to the position at power-up.

        Note that the stage supports absolute positions above 360 degrees
        and will not automatically reduce such positions module 360.
        It is therefore possible that the stage must rotate more than
        a full turn in order to reach a specific absolute position.

        Parameters:
            position: Absolute target position in degrees.
        """

        # Convert distance to microsteps and check that the value fits in a 32-bit signed integer.
        raw_pos = int(round(position * self.MICROSTEPS_PER_DEGREE))
        if abs(raw_pos) >= 2**31:
            raise ValueError("Absolute position out of valid range")

        self._check_is_open()

        # Send command message.
        req_msg = _AptMsgMoveAbsolute.create(chan_ident=self._channel, abs_position=raw_pos)
        self._send_message(req_msg)

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
                msg = self._read_message(timeout=min(0.5, time_left))
            except QMI_TimeoutException:
                # No message from the motor.
                # This is normal and expected if the motor is still moving.
                # Go around the loop again and poll the motor status.
                continue

            # Any message from the motor is most likely an announcement that
            # the move has ended. Whatever the actual message, go around
            # the loop and poll the motor status again.
            _logger.debug("[%s] Ignoring message %s (message_id=0x%04x)",
                          self._name, type(msg).__name__, msg.message_id)
