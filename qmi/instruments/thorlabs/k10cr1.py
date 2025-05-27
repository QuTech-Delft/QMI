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
from dataclasses import dataclass
import logging
import time
from typing import Any, ClassVar, NamedTuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.instruments.thorlabs.apt_packets import (
    HW_GET_INFO,
    MOT_GET_STATUS_BITS,
    MOD_GET_CHANENABLESTATE,
    MOT_GET_POS_COUNTER,
    MOT_GET_VEL_PARAMS,
    MOT_GET_GEN_MOVE_PARAMS,
    MOT_GET_HOME_PARAMS,
    MOT_SET_HOME_PARAMS,
    MOT_GET_USTATUSUPDATE,
    MOT_MOVE_ABSOLUTE,
    MOT_MOVE_COMPLETED,
    MOT_MOVE_HOMED,
    MOT_SET_EEPROMPARAMS,
    POL_GET_SET_PARAMS,
)
from qmi.instruments.thorlabs.apt_protocol import (
    AptChannelHomeDirection,
    AptChannelHomeLimitSwitch,
    AptChannelState,
    AptMessageId,
    AptProtocol,
)

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


_APT_HOST_ADDRESS = 0x01    # Address of the computer in the APT protocol.
_APT_DEVICE_ADDRESS = 0x50  # Address of the device in the APT protocol.


# class _AptMessage(ctypes.LittleEndianStructure):
#     """Base class for APT protocol messages."""
#
#     _pack_ = 1
#
#     @classmethod
#     def create(cls, **kwargs: Any) -> "_AptMessage":
#         """Return a new message instance.
#
#         Message ID, destination address, source address and data length
#         (if applicable) will already be filled in. Other fields may be
#         specified as keyword arguments.
#         """
#         message_size = ctypes.sizeof(cls)
#         if message_size > 6:
#             # This is a long APT message (header + data).
#             # Long APT messages are identified by bit 7 in the destination field.
#             return cls(
#                 message_id=cls.MESSAGE_ID,
#                 data_length=(message_size - 6),
#                 dest=(_APT_DEVICE_ADDRESS | 0x80),
#                 source=_APT_HOST_ADDRESS,
#                 **kwargs
#             )
#         else:
#             # This is a short APT message (header only).
#             return cls(
#                 message_id=cls.MESSAGE_ID,
#                 dest=_APT_DEVICE_ADDRESS,
#                 source=_APT_HOST_ADDRESS,
#                 **kwargs
#             )
#
#
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


# APT messages for the K10CR1 device.
# See the "Thorlabs APT Controllers Host-Controller Communications Protocol".

# class _AptMsgReqPosCounter(_AptMessage):
#     MESSAGE_ID = 0x0411
#     _fields_ = _apt_short_message_fields([("chan_ident", ctypes.c_uint8)])
#
# class _AptMsgGetPosCounter(_AptMessageHeader):
#     MESSAGE_ID = 0x0412
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("position",        ctypes.c_int32)]
#
# class _AptMsgSetVelParams(_AptMessageHeader):
#     MESSAGE_ID = 0x0413
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("min_vel",         ctypes.c_int32),
#                 ("accel",           ctypes.c_int32),
#                 ("max_vel",         ctypes.c_int32)]
#
# class _AptMsgReqVelParams(_AptMessage):
#     MESSAGE_ID = 0x0414
#     _fields_ = _apt_short_message_fields([("chan_ident", ctypes.c_uint8)])
#
# class _AptMsgGetVelParams(_AptMessageHeader):
#     MESSAGE_ID = 0x0415
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("min_vel",         ctypes.c_int32),
#                 ("accel",           ctypes.c_int32),
#                 ("max_vel",         ctypes.c_int32)]
#
# class _AptMsgSetGenMoveParams(_AptMessageHeader):
#     MESSAGE_ID = 0x043A
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("backlash_dist",   ctypes.c_int32)]
#
# class _AptMsgReqGenMoveParams(_AptMessage):
#     MESSAGE_ID = 0x043B
#     _fields_ = _apt_short_message_fields([("chan_ident", ctypes.c_uint8)])
#
# class _AptMsgGetGenMoveParams(_AptMessageHeader):
#     MESSAGE_ID = 0x043C
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("backlash_dist",   ctypes.c_int32)]
#
# class _AptMsgSetHomeParams(_AptMessageHeader):
#     MESSAGE_ID = 0x0440
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("home_dir",        ctypes.c_uint16),
#                 ("limit_switch",    ctypes.c_uint16),
#                 ("home_velocity",   ctypes.c_int32),
#                 ("offset_dist",     ctypes.c_int32)]
#
# class _AptMsgReqHomeParams(_AptMessage):
#     MESSAGE_ID = 0x0441
#     _fields_ = _apt_short_message_fields([("chan_ident", ctypes.c_uint8)])
#
# class _AptMsgGetHomeParams(_AptMessageHeader):
#     MESSAGE_ID = 0x0442
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("home_dir",        ctypes.c_uint16),
#                 ("limit_switch",    ctypes.c_uint16),
#                 ("home_velocity",   ctypes.c_int32),
#                 ("offset_dist",     ctypes.c_int32)]
#
# class _AptMsgMoveRelative(_AptMessageHeader):
#     MESSAGE_ID = 0x0448
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("rel_dist",        ctypes.c_int32)]
#
# class _AptMsgMoveCompleted(_AptMessageHeader):
#     MESSAGE_ID = 0x0464
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("position",        ctypes.c_int32),
#                 ("velocity",        ctypes.c_uint16),
#                 ("reserved",        ctypes.c_uint16),
#                 ("status_bits",     ctypes.c_uint32)]
#
# class _AptMsgMoveStop(_AptMessage):
#     MESSAGE_ID = 0x0465
#     _fields_ = _apt_short_message_fields([("chan_ident", ctypes.c_uint8),
#                                           ("stop_mode", ctypes.c_uint8)])
#
# class _AptMsgMoveStopped(_AptMessageHeader):
#     MESSAGE_ID = 0x0466
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("position",        ctypes.c_int32),
#                 ("velocity",        ctypes.c_uint16),
#                 ("reserved",        ctypes.c_uint16),
#                 ("status_bits",     ctypes.c_uint32)]
#
# class _AptMsgReqStatusBits(_AptMessage):
#     MESSAGE_ID = 0x0429
#     _fields_ = _apt_short_message_fields([("chan_ident", ctypes.c_uint8)])
#
# class _AptMsgGetStatusBits(_AptMessageHeader):
#     MESSAGE_ID = 0x042A
#     _fields_ = [("chan_ident",      ctypes.c_uint16),
#                 ("status_bits",     ctypes.c_uint32)]


# Build a table, mapping message ID to the corresponding Python class.
# _apt_message_type_table: dict[int, Type["_AptMessage"]] = {
#     _AptMsgIdentify.MESSAGE_ID:             _AptMsgIdentify,
#     _AptMsgSetChanEnableState.MESSAGE_ID:   _AptMsgSetChanEnableState,
#     _AptMsgReqChanEnableState.MESSAGE_ID:   _AptMsgReqChanEnableState,
#     _AptMsgGetChanEnableState.MESSAGE_ID:   _AptMsgGetChanEnableState,
#     _AptMsgHwReqInfo.MESSAGE_ID:            _AptMsgHwReqInfo,
#     _AptMsgHwGetInfo.MESSAGE_ID:            _AptMsgHwGetInfo,
#     _AptMsgReqPosCounter.MESSAGE_ID:        _AptMsgReqPosCounter,
#     _AptMsgGetPosCounter.MESSAGE_ID:        _AptMsgGetPosCounter,
#     _AptMsgSetVelParams.MESSAGE_ID:         _AptMsgSetVelParams,
#     _AptMsgReqVelParams.MESSAGE_ID:         _AptMsgReqVelParams,
#     _AptMsgGetVelParams.MESSAGE_ID:         _AptMsgGetVelParams,
#     _AptMsgSetGenMoveParams.MESSAGE_ID:     _AptMsgSetGenMoveParams,
#     _AptMsgReqGenMoveParams.MESSAGE_ID:     _AptMsgReqGenMoveParams,
#     _AptMsgGetGenMoveParams.MESSAGE_ID:     _AptMsgGetGenMoveParams,
#     _AptMsgSetHomeParams.MESSAGE_ID:        _AptMsgSetHomeParams,
#     _AptMsgReqHomeParams.MESSAGE_ID:        _AptMsgReqHomeParams,
#     _AptMsgGetHomeParams.MESSAGE_ID:        _AptMsgGetHomeParams,
#     _AptMsgMoveHome.MESSAGE_ID:             _AptMsgMoveHome,
#     _AptMsgMoveHomed.MESSAGE_ID:            _AptMsgMoveHomed,
#     _AptMsgMoveRelative.MESSAGE_ID:         _AptMsgMoveRelative,
#     _AptMsgMoveAbsolute.MESSAGE_ID:         _AptMsgMoveAbsolute,
#     _AptMsgMoveCompleted.MESSAGE_ID:        _AptMsgMoveCompleted,
#     _AptMsgMoveStop.MESSAGE_ID:             _AptMsgMoveStop,
#     _AptMsgMoveStopped.MESSAGE_ID:          _AptMsgMoveStopped,
#     _AptMsgReqStatusBits.MESSAGE_ID:        _AptMsgReqStatusBits,
#     _AptMsgGetStatusBits.MESSAGE_ID:        _AptMsgGetStatusBits,
# }
#
#
@dataclass
class VelocityParams:
    """Velocity parameters for the K10CR1.

    Attributes:
        max_velocity:    Maximum velocity in degrees/second.
        acceleration:    Acceleration in degrees/second/second.
    """
    max_velocity: float
    acceleration: float


# class HomeDirection(enum.IntEnum):
#     """Possible values for the ``home_direction`` field in the homing parameters."""
#     FORWARD = 1
#     REVERSE = 2
#
#
# class HomeLimitSwitch(enum.IntEnum):
#     """Possible values for the ``limit_switch`` field in the homing parameters."""
#     REVERSE = 1
#     FORWARD = 4


@dataclass
class HomeParams:
    """Homing parameters for the K10CR1.

    Attributes:
        home_direction:  Direction of moving to home (1 = forward, 2 = reverse).
        limit_switch:    Limit switch to use for homing (1 = reverse, 4 = forward).
        home_velocity:   Homing velocity in degrees/second.
        offset_distance: Distance of home postion from home limit switch (in degrees).
    """
    home_direction:     AptChannelHomeDirection
    limit_switch:       AptChannelHomeLimitSwitch
    home_velocity:      float
    offset_distance:    float


@dataclass
class MotorStatus:
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

    def _check_k10cr1(self) -> None:
        """Check that the connected device is a Thorlabs K10CR1.

        Raises:
            QMI_InstrumentException: If not connected to a K10CR1 device.
            QMI_TimeoutException: If the instrument does not answer our request.
        """

        # Send request message.
        self._apt_protocol.write_two_param_command(AptMessageId.HW_REQ_INFO.value)
        # Get response
        resp = self._apt_protocol.ask(HW_GET_INFO)

        # Check that this is a K10CR1 device.
        model_str = resp.model_number.decode("iso8859-1")
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
        self._apt_protocol.write_two_param_command(AptMessageId.HW_REQ_INFO.value)
        # Get response
        resp = self._apt_protocol.ask(HW_GET_INFO)

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
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_REQ_STATUS_BITS.value,
            self._channel
        )
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_STATUS_BITS)

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
        _logger.info("[%s] Identifying device", self._name)
        self._check_is_open()

        # Send command message.
        self._apt_protocol.write_two_param_command(AptMessageId.MOD_IDENTIFY.value, 0x01)

    @rpc_method
    def get_chan_enable_state(self) -> bool:
        """Return the enable state of the motor drive channel."""
        self._check_is_open()

        # Send request message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOD_REQ_CHANENABLESTATE.value,
            self._channel,
        )
        # Get response
        resp = self._apt_protocol.ask(MOD_GET_CHANENABLESTATE)
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
        enable_state = 0x01 if enable else 0x02
        # Send message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOD_SET_CHANENABLESTATE.value,
            self._channel,
            enable_state,
        )

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
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_REQ_POS_COUNTER.value,
            self._channel,
        )
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_POS_COUNTER)
        return resp.position / self.MICROSTEPS_PER_DEGREE

    @rpc_method
    def get_velocity_params(self) -> VelocityParams:
        """Return the current maximum velocity and acceleration."""

        self._check_is_open()

        # Send request message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_REQ_VEL_PARAMS.value,
            self._channel,
        )
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_VEL_PARAMS)
        return VelocityParams(
            max_velocity=(resp.max_vel / self.VELOCITY_FACTOR),
            acceleration=(resp.accel / self.ACCELERATION_FACTOR)
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
        self._apt_protocol.write_three_param_command(
            AptMessageId.MOD_SET_CHANENABLESTATE.value,
            0,
            accel,
            max_vel
        )

    @rpc_method
    def get_backlash_distance(self) -> float:
        """Return the backlash distance in degrees."""

        self._check_is_open()

        # Send request message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_REQ_GEN_MOVE_PARAMS.value,
            self._channel,
        )
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_GEN_MOVE_PARAMS)
        return resp.backlash_dist / self.MICROSTEPS_PER_DEGREE

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

        # Send message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOD_SET_CHANENABLESTATE.value,
            self._channel,
            raw_dist,
        )

    @rpc_method
    def get_home_params(self) -> HomeParams:
        """Return the homing parameters."""

        self._check_is_open()

        # Send request message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_REQ_HOME_PARAMS.value,
            self._channel,
        )
        # Get response
        resp = self._apt_protocol.ask(MOT_GET_HOME_PARAMS)
        return HomeParams(
            home_direction=AptChannelHomeDirection(resp.home_dir),
            limit_switch=AptChannelHomeLimitSwitch(resp.limit_switch),
            home_velocity=(resp.home_velocity / self.VELOCITY_FACTOR),
            offset_distance=(resp.offset_dist / self.MICROSTEPS_PER_DEGREE)
        )

    @rpc_method
    def set_home_params(
        self,
        home_direction: AptChannelHomeDirection,
        limit_switch: AptChannelHomeLimitSwitch,
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

        if home_direction not in (AptChannelHomeDirection.FORWARD, AptChannelHomeDirection.REVERSE):
            raise ValueError("Invalid value for home_direction")
        if limit_switch not in (AptChannelHomeLimitSwitch.FORWARD, AptChannelHomeLimitSwitch.REVERSE):
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
        self._apt_protocol.write_home_param_command(
            AptMessageId.MOT_SET_HOME_PARAMS.value,
            home_dir=int(home_direction),
            limit_switch=int(limit_switch),
            home_velocity=raw_velocity,
            offset_dist=raw_dist
        )

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
        # Send message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_MOVE_STOP.value,
            self._channel,
            stop_mode,
        )

    @rpc_method
    def move_home(self) -> None:
        """Start a homing move.

        This function returns immediately while homing is still in progress.
        Use ``wait_move_complete()`` to wait until the move is finished.
        """
        self._check_is_open()

        # Send message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_MOVE_HOME.value,
            self._channel,
        )

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

        # Send message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_MOVE_RELATIVE.value,
            self._channel,
            raw_dist
        )

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

        # Send message.
        self._apt_protocol.write_two_param_command(
            AptMessageId.MOT_MOVE_ABSOLUTE.value,
            self._channel,
            raw_pos,
        )

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
            try:
                status = self.get_motor_status()
            except QMI_TimeoutException:
                # No message from the motor.
                # This is normal and expected if the motor is still moving.
                # Go around the loop again and poll the motor status.
                continue

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

            # Any message from the motor is most likely an announcement that
            # the move has ended. Whatever the actual message, go around
            # the loop and poll the motor status again.
