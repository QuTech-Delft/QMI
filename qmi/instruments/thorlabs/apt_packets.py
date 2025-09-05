"""Module containing the packets for the APT protocol."""

from ctypes import (
    LittleEndianStructure,
    c_uint8,
    c_uint16,
    c_int16,
    c_uint32,
    c_int32,
    c_char,
    sizeof,
)
from enum import Enum
from typing import Any, ClassVar

# APT format specifiers
apt_word = c_uint16
apt_short = c_int16
apt_dword = c_uint32
apt_long = c_int32
apt_char = c_char
# this format specifier is not defined in the APT protocol manual but is helpful for packets that are divided into
# single bytes
apt_byte = c_uint8


class AptMessageId(Enum):
    """Message IDs for devices using the APT protocol."""

    HW_REQ_INFO = 0x0005
    HW_GET_INFO = 0x0006
    MOD_IDENTIFY = 0x0223
    MOD_SET_CHANENABLESTATE = 0x0210
    MOD_REQ_CHANENABLESTATE = 0x0211
    MOD_GET_CHANENABLESTATE = 0x0212
    HW_START_UPDATEMSGS = 0x0011
    HW_STOP_UPDATEMSGS = 0x0012
    MOT_REQ_POS_COUNTER = 0x0411
    MOT_GET_POS_COUNTER = 0x0412
    MOT_SET_VEL_PARAMS = 0x0413
    MOT_REQ_VEL_PARAMS = 0x0414
    MOT_GET_VEL_PARAMS = 0x0415
    MOT_REQ_STATUS_BITS = 0x0429
    MOT_GET_STATUS_BITS = 0x042A
    MOT_SET_GEN_MOVE_PARAMS = 0x043A
    MOT_REQ_GEN_MOVE_PARAMS = 0x043B
    MOT_GET_GEN_MOVE_PARAMS = 0x043C
    MOT_SET_HOME_PARAMS = 0x0440
    MOT_REQ_HOME_PARAMS = 0x0441
    MOT_GET_HOME_PARAMS = 0x0442
    MOT_MOVE_HOME = 0x0443
    MOT_MOVE_HOMED = 0x0444
    MOT_MOVE_RELATIVE = 0x0448
    MOT_MOVE_ABSOLUTE = 0x0453
    MOT_MOVE_COMPLETED = 0x0464
    MOT_MOVE_STOP = 0x0465
    MOT_MOVE_STOPPED = 0x0466
    MOT_SET_EEPROMPARAMS = 0x04B9
    MOT_REQ_USTATUSUPDATE = 0x0490
    MOT_GET_USTATUSUPDATE = 0x0491
    MOT_MOVE_JOG = 0x046A
    POL_SET_PARAMS = 0x0530
    POL_REQ_PARAMS = 0x0531
    POL_GET_PARAMS = 0x0532


class _AptMessage(LittleEndianStructure):
    """Base class for APT protocol messages."""

    _pack_ = 1

    @classmethod
    def create(cls, dest: int, source: int, **kwargs: Any) -> "_AptMessage":
        """Return a new message instance.

        Message ID, destination address, source address and data length
        (if applicable) will already be filled in. Other fields may be
        specified as keyword arguments.
        """
        message_size = sizeof(cls)
        if message_size > 6:
            # This is a long APT message (header + data).
            # Long APT messages are identified by bit 7 in the destination field.
            return cls(
                message_id=cls.MESSAGE_ID,
                data_length=(message_size - 6),
                dest=(dest | 0x80),
                source=source,
                **kwargs
            )
        else:
            # This is a short APT message (header only).
            return cls(
                message_id=cls.MESSAGE_ID,
                dest=dest,
                source=source,
                **kwargs
            )


class _AptMessageHeader(_AptMessage):
    """Generic message header for the APT protocol.

    This is also the base class for long messages (header + data).
    """
    _pack_ = 1
    _fields_: ClassVar[list[tuple[str, type] | tuple[str, type, int]]] = [
        ('message_id', apt_word),
        ('data_length', apt_word),
        ('dest', apt_byte),
        ('source', apt_byte)
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
        data_length += sizeof(par_type)
    assert data_length <= 2

    # Build field list for ctypes structure.
    all_fields: list[tuple[str, type]] = [("message_id", apt_word)]
    all_fields += fields
    if data_length < 2:
        # Add dummy field if the message uses fewer than 2 bytes for parameters.
        all_fields.append(("_dummy", (2 - data_length) * apt_byte))

    all_fields.append(("dest", apt_byte))
    all_fields.append(("source", apt_byte))

    return all_fields


# APT messages. See the "Thorlabs APT Controllers Host-Controller Communications Protocol".
class _AptMsgHwReqInfo(_AptMessage):
    MESSAGE_ID = AptMessageId.HW_REQ_INFO.value
    _fields_ = _apt_short_message_fields([])


class _AptMsgHwGetInfo(_AptMessageHeader):
    """
    Data packet structure for the HW_GET_INFO response. This packet is sent as a response to HW_REQ_INFO.

    Fields:
        serial_number:      Serial number of device.
        model_number:       Model number of device.
        type:               Hardware type of device.
        fw_version:         Firmware version of device.
        hw_version:         Hardware version of device.
        mod_state:          Modification state of device.
        n_channels:         Number of channels in device.
    """
    MESSAGE_ID = AptMessageId.HW_GET_INFO.value
    _fields_ = [("serial_number", apt_dword),
                ("model_number", 8 * apt_char),
                ("type_", apt_word),
                ("fw_version", apt_dword),
                ("internal_use", 60 * apt_byte),
                ("hw_version", apt_word),
                ("mod_state", apt_word),
                ("n_channels", apt_word)]


class _AptMsgHwStartUpdateMsgs(_AptMessage):
    MESSAGE_ID = AptMessageId.HW_START_UPDATEMSGS.value
    _fields_ = _apt_short_message_fields([])


class _AptMsgHwStopUpdateMsgs(_AptMessage):
    MESSAGE_ID = AptMessageId.HW_STOP_UPDATEMSGS.value
    _fields_ = _apt_short_message_fields([])


class _AptMsgSetChanEnableState(_AptMessage):
    """
    Header structure for the MOD_SET_CHANENABLESTATE response.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        enable_state:   Indicate whether chanel is enabled or disabled.
    """
    MESSAGE_ID = AptMessageId.MOD_SET_CHANENABLESTATE.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte),
                                          ("enable_state", apt_byte)])


class _AptMsgReqChanEnableState(_AptMessage):
    MESSAGE_ID = AptMessageId.MOD_REQ_CHANENABLESTATE.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetChanEnableState(_AptMessage):
    """
    Header structure for the MOD_GET_CHANENABLESTATE response. This header is sent as a response to
    MOD_REQ_CHANENABLESTATE.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        enable_state:   Indicate whether chanel is enabled or disabled.
    """
    MESSAGE_ID = AptMessageId.MOD_GET_CHANENABLESTATE.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte),
                                          ("enable_state", apt_byte)])


class _AptMsgIdentify(_AptMessage):
    MESSAGE_ID = AptMessageId.MOD_IDENTIFY.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgReqPosCounter(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_REQ_POS_COUNTER.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetPosCounter(_AptMessageHeader):
    """
    Header structure for the MOT_GET_POS_COUNTER response. This header is sent as a response to MOT_REQ_POS_COUNTER.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        position:       The counter position.
    """
    MESSAGE_ID = AptMessageId.MOT_GET_POS_COUNTER.value
    _fields_ = [("chan_ident", apt_word),
                ("position", apt_long)]


class _AptMsgSetVelParams(_AptMessageHeader):
    """
    Data packet structure for a MOT_SET_VEL_PARAMS command.

    Fields:
        chan_ident: The channel being addressed.
        min_vel:    Minimum velocity of the channel.
        accel:      Acceleration of the channel.
        max_vel:    Maximum velocity of the channel.
    """
    MESSAGE_ID = AptMessageId.MOT_SET_VEL_PARAMS.value
    _fields_ = [("chan_ident", apt_word),
                ("min_vel", apt_long),
                ("accel", apt_long),
                ("max_vel", apt_long)]


class _AptMsgReqVelParams(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_REQ_VEL_PARAMS.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetVelParams(_AptMessageHeader):
    """
    Header structure for the MOT_GET_VEL_PARAMS response. This header is sent as a response to MOT_REQ_VEL_PARAMS.

    Fields:
        chan_ident: The channel being addressed.
        min_vel:    Minimum velocity of the channel.
        accel:      Acceleration of the channel.
        max_vel:    Maximum velocity of the channel.
    """
    MESSAGE_ID = AptMessageId.MOT_GET_VEL_PARAMS.value
    _fields_ = [("chan_ident", apt_word),
                ("min_vel", apt_long),
                ("accel", apt_long),
                ("max_vel", apt_long)]


class _AptMsgReqStatusBits(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_REQ_STATUS_BITS.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetStatusBits(_AptMessageHeader):
    """
    Header structure for the MOT_GET_STATUS_BITS response. This header is sent as a response to MOT_REQ_STATUS_BITS.

    Fields:
        chan_ident:    The channel being addressed.
        status_bits:   Channel status_bits.
    """
    MESSAGE_ID = AptMessageId.MOT_GET_STATUS_BITS.value
    _fields_: ClassVar[list[tuple[str, type] | tuple[str, type, int]]] = [
        ("chan_ident", apt_word),
        ("forward_limit", apt_byte, 1),
        ("reverse_limit", apt_byte, 1),
        ("forward_software_limit", apt_byte, 1),
        ("reverse_software_limit", apt_byte, 1),
        ("moving_forward", apt_byte, 1),
        ("moving_reverse", apt_byte, 1),
        ("jogging_forward", apt_byte, 1),
        ("jogging_reverse", apt_byte, 1),
        ("connected", apt_byte, 1),
        ("homing", apt_byte, 1),
        ("homed", apt_byte, 1),
        ("initializing", apt_byte, 1),  # For 3-phase brushless motors only
        ("tracking", apt_byte, 1),
        ("settled", apt_byte, 1),
        ("motion_error", apt_byte, 1),
        ("instruction_error", apt_byte, 1),
        ("interlock", apt_byte, 1),
        ("overheat", apt_byte, 1),
        ("voltage_fault", apt_byte, 1),
        ("commutation_error", apt_byte, 1),
        ("DI1", apt_byte, 1),
        ("DI2", apt_byte, 1),
        ("DI3", apt_byte, 1),
        ("DI4", apt_byte, 1),
        ("motor_overload", apt_byte, 1),
        ("encoder_fault", apt_byte, 1),
        ("current_limit", apt_byte, 1),
        ("current_fault", apt_byte, 1),
        ("power_ok", apt_byte, 1),
        ("moving", apt_byte, 1),
        ("unknown_error", apt_byte, 1),
        ("output_enabled", apt_byte, 1)
    ]


class _AptMsgSetGenMoveParams(_AptMessageHeader):
    """
    Data packet structure for a MOT_SET_GEN_MOVE_PARAMS command.

    Fields:
        chan_ident:    The channel being addressed.
        backlash_dist: Channel backlash distance.
    """
    MESSAGE_ID = AptMessageId.MOT_SET_GEN_MOVE_PARAMS.value
    _fields_ = [("chan_ident", apt_word),
                ("backlash_dist", apt_long)]


class _AptMsgReqGenMoveParams(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_REQ_GEN_MOVE_PARAMS.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetGenMoveParams(_AptMessageHeader):
    """
    Header structure for the MOT_GET_GEN_MOVE_PARAMS response. This header is sent as a response to MOT_REQ_GEN_MOVE_PARAMS.

    Fields:
        chan_ident:    The channel being addressed.
        backlash_dist: Channel backlash distance.
    """

    MESSAGE_ID = AptMessageId.MOT_GET_GEN_MOVE_PARAMS.value
    _fields_ = [("chan_ident", apt_word),
                ("backlash_dist", apt_long)]


class _AptMsgSetHomeParams(_AptMessageHeader):
    """
    Data packet structure for a MOT_SET_HOME_PARAMS command.

    Fields:
        chan_ident:    The channel being addressed.
        home_dir:      Channel home direction.
        limit_switch:  Channel limit switch.
        home_velocity: Channel homing velocity.
        offset_dist:   Channel offset distance.
    """
    MESSAGE_ID = AptMessageId.MOT_SET_HOME_PARAMS.value
    _fields_ = [("chan_ident", apt_word),
                ("home_dir", apt_word),
                ("limit_switch", apt_word),
                ("home_velocity", apt_long),
                ("offset_dist", apt_long)]


class _AptMsgReqHomeParams(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_REQ_HOME_PARAMS.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetHomeParams(_AptMessageHeader):
    """
    Header structure for the MOT_GET_HOME_PARAMS response. This header is sent as a response to MOT_REQ_HOME_PARAMS.

    Fields:
        chan_ident:    The channel being addressed.
        home_dir:      Channel home direction.
        limit_switch:  Channel limit switch.
        home_velocity: Channel homing velocity.
        offset_dist:   Channel offset distance.
    """
    MESSAGE_ID = AptMessageId.MOT_GET_HOME_PARAMS.value
    _fields_ = [("chan_ident", apt_word),
                ("home_dir", apt_word),
                ("limit_switch", apt_word),
                ("home_velocity", apt_long),
                ("offset_dist", apt_long)]


class _AptMsgMoveHome(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_MOVE_HOME.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgMoveHomed(_AptMessage):
    """
    Header structure for the MOT_MOVE_HOMED response. This header is sent as a response to MOT_MOVE_HOME
    once homing is complete.

    Fields:
        chan_ident:     Channel number.
    """
    MESSAGE_ID = AptMessageId.MOT_MOVE_HOMED.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgMoveRelative(_AptMessageHeader):
    """
    Data packet structure for a MOT_MOVE_RELATIVE command.

    Fields:
        chan_ident:    The channel being addressed.
        rel_dist:      The relative distance to move in encoder units.
    """
    MESSAGE_ID = AptMessageId.MOT_MOVE_RELATIVE.value
    _fields_ = [("chan_ident", apt_word),
                ("rel_dist", apt_long)]


class _AptMsgMoveAbsolute(_AptMessageHeader):
    """
    Data packet structure for a MOT_MOVE_ABSOLUTE command.

    Fields:
        chan_ident:    The channel being addressed.
        abs_position:  The position to move to in encoder units.
    """
    MESSAGE_ID = AptMessageId.MOT_MOVE_ABSOLUTE.value
    _fields_ = [("chan_ident", apt_word),
                ("abs_position", apt_long)]


class _AptMsgMoveCompleted(_AptMessageHeader):
    """
    Header structure for the MOT_MOVE_COMPLETED response. This header is sent as a response to a relative or absolute
    move command once the move has been completed.

    Fields:
        chan_ident:     Channel number.
        position:       Position of the counter.
        velocity:       Velocity.
        reserved:       Destination of message.
        status_bits:    Move status bits.
    """
    MESSAGE_ID = AptMessageId.MOT_MOVE_COMPLETED.value
    _fields_ = [("chan_ident", apt_word),
                ("position", apt_long),
                ("velocity", apt_word),
                ("reserved", apt_word),
                ("status_bits", apt_dword)]


class _AptMsgMoveStop(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_MOVE_STOP.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte),
                                          ("stop_mode", apt_byte)])


class _AptMsgMoveStopped(_AptMessageHeader):
    """
    Header structure for the MOT_MOVE_STOPPED response. This header is sent as a response to a relative or absolute
    move command once the move has been stopped.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        position:       Position of the counter.
        velocity:       Velocity.
        reserved:       Destination of message.
        status_bits:    Move status bits.
    """
    MESSAGE_ID = AptMessageId.MOT_MOVE_STOPPED.value
    _fields_ = [("chan_ident", apt_word),
                ("position", apt_long),
                ("velocity", apt_word),
                ("reserved", apt_word),
                ("status_bits", apt_dword)]


class _AptMsgReqUStatusUpdate(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_REQ_USTATUSUPDATE.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetUStatusUpdate(_AptMessageHeader):
    """
    Data packet structure for a MOT_GET_USTATUSUPDATE command.

    Fields:
        chan_ident:     The channel being addressed.
        position:       The position in encoder counts.
        velocity:       Velocity in controller units. Note that this is reported as a 16 bit
                        unsigned integer in the manual but it is actually signed according to the example.
        motor_current:  Motor current in mA.
        status_bits:    Status bits that provide various errors and indications.
    """
    MESSAGE_ID = AptMessageId.MOT_GET_USTATUSUPDATE.value
    _fields_ = [
        ("chan_ident", apt_word),
        ("position", apt_long),
        ("velocity", apt_word),
        ("motor_current", apt_short),  # Documentation says this is 'word' but description details it unsigned
        ("status_bits", apt_dword),
    ]


class _AptMsgSetEepromParams(_AptMessageHeader):
    """
    Data packet structure for a MOT_SET_EEPROMPARAMS command.

    Fields:
        chan_ident: The channel being addressed.
        msg_id:     ID of message whose settings should be saved.
    """
    MESSAGE_ID = AptMessageId.MOT_SET_EEPROMPARAMS.value
    _fields_ = [("chan_ident", apt_word), ("msg_id", apt_word)]


class _AptMsgMoveJog(_AptMessage):
    MESSAGE_ID = AptMessageId.MOT_MOVE_JOG.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte), ("direction", apt_byte)])


class _AptMsgSetPolParams(_AptMessageHeader):
    """
    Data packet structure for POL_SET_PARAMS command.

    Fields:
        not_used:       This field is not used, but needs to be in the field structure to not break it.
        velocity:       Velocity in range 10% to 100% of 400 degrees/s.
        home_position:  Home position in encoder counts.
        jog_step1:      Size fo jog step to be performed on paddle 1.
        jog_step2:      Size fo jog step to be performed on paddle 2.
        jog_step3:      Size fo jog step to be performed on paddle 3.
    """
    MESSAGE_ID = AptMessageId.POL_SET_PARAMS.value
    _fields_ = [
        ("not_used", apt_word),
        ("velocity", apt_word),
        ("home_position", apt_word),
        ("jog_step1", apt_word),
        ("jog_step2", apt_word),
        ("jog_step3", apt_word),
    ]


class _AptMsgReqPolParams(_AptMessage):
    MESSAGE_ID = AptMessageId.POL_REQ_PARAMS.value
    _fields_ = _apt_short_message_fields([("chan_ident", apt_byte)])


class _AptMsgGetPolParams(_AptMessageHeader):
    """
    Data packet structure for POL_GET_PARAMS command. It is also the data packet structure for the POL_REQ_PARAMS.

    Fields:
        not_used:       This field is not used, but needs to be in the field structure to not break it.
        velocity:       Velocity in range 10% to 100% of 400 degrees/s.
        home_position:  Home position in encoder counts.
        jog_step1:      Size fo jog step to be performed on paddle 1.
        jog_step2:      Size fo jog step to be performed on paddle 2.
        jog_step3:      Size fo jog step to be performed on paddle 3.
    """
    MESSAGE_ID = AptMessageId.POL_GET_PARAMS.value
    _fields_ = [
        ("not_used", apt_word),
        ("velocity", apt_word),
        ("home_position", apt_word),
        ("jog_step1", apt_word),
        ("jog_step2", apt_word),
        ("jog_step3", apt_word),
    ]


# Build a table, mapping message ID to the corresponding Python class.
APT_MESSAGE_TYPE_TABLE: dict[int, _AptMessage] = {}
global_items = dict(globals().items())
for name, obj in global_items.items():
    if name.startswith('_AptMsg'):
        assert hasattr(obj, "MESSAGE_ID"), f"{obj} class definition is missing MESSAGE_ID."
        APT_MESSAGE_TYPE_TABLE[obj.MESSAGE_ID] = obj
