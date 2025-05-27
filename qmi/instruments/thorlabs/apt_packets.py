"""Module containing the packets for the APT protocol."""

from typing import ClassVar
from qmi.instruments.thorlabs.apt_protocol import (
    AptMessage,
    AptMessageId,
    apt_long,
    apt_dword,
    apt_char,
    apt_word,
    apt_byte,
    apt_short,
)


class HW_GET_INFO(AptMessage):
    """
    Data packet structure for the HW_GET_INFO response. This packet is sent as a response to HW_GET_INFO.

    Fields:
        serial_number:      Serial number of device.
        model_number:       Model number of device.
        type:               Hardware type of device.
        firmware_version:   Firmware version of device.
        hw_version:         Hardware version of device.
        mod_state:          Modification state of device.
        num_channels:       Number of channels in device.
    """

    MESSAGE_ID = AptMessageId.HW_GET_INFO.value
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("serial_number", apt_long),
        ("model_number", apt_char * 8),
        ("type", apt_word),
        ("fw_version", apt_dword),
        (
            "internal_use",
            apt_dword * 15,
        ),  # this is for internal use, so we don't know what type it returns
        ("hw_version", apt_word),
        ("mod_state", apt_word),
        ("num_channels", apt_word),
    ]


class MOD_GET_CHANENABLESTATE(AptMessage):
    """
    Header structure for the MOD_GET_CHANENABLESTATE response. This header is sent as a response to
    MOD_REQ_CHANENABLESTATE.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        enable_state:   Indicate whether chanel is enabled or disabled.
        dest:           Destination of message.
        source:         Source of message.
    """

    MESSAGE_ID = AptMessageId.MOD_GET_CHANENABLESTATE.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("enable_state", apt_byte),
        ("dest", apt_byte),
        ("source", apt_byte),
    ]


class MOT_GET_POS_COUNTER(AptMessage):
    """
    Header structure for the MOT_GET_POS_COUNTER response. This header is sent as a response to MOT_REQ_POS_COUNTER.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        position:       The counter position.
    """

    MESSAGE_ID = AptMessageId.MOT_GET_POS_COUNTER.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("position", apt_long),
    ]


class MOT_SET_VEL_PARAMS(AptMessage):
    """
    Data packet structure for a MOT_SET_VEL_PARAMS command.

    Fields:
        chan_ident: The channel being addressed.
        min_vel:    Minimum velocity of the channel.
        accel:      Acceleration of the channel.
        max_vel:    Maximum velocity of the channel.
    """

    MESSAGE_ID = AptMessageId.MOT_SET_VEL_PARAMS.value
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("min_vel", apt_long),
        ("accel", apt_long),
        ("max_vel", apt_long)
    ]


class MOT_GET_VEL_PARAMS(AptMessage):
    """
    Header structure for the MOT_GET_VEL_PARAMS response. This header is sent as a response to MOT_REQ_VEL_PARAMS.

    Fields:
        chan_ident: The channel being addressed.
        min_vel:    Minimum velocity of the channel.
        accel:      Acceleration of the channel.
        max_vel:    Maximum velocity of the channel.
    """
    MESSAGE_ID = AptMessageId.MOT_GET_VEL_PARAMS.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("min_vel", apt_long),
        ("accel", apt_long),
        ("max_vel", apt_long)
    ]


class MOT_GET_STATUS_BITS(AptMessage):
    """
    Header structure for the MOT_GET_STATUS_BITS response. This header is sent as a response to MOT_REQ_STATUS_BITS.

    Fields:
        chan_ident:    The channel being addressed.
        status_bits:   Channel status_bits.
    """

    MESSAGE_ID = AptMessageId.MOT_GET_STATUS_BITS.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("status_bits", apt_dword),
    ]


class MOT_SET_GEN_MOVE_PARAMS(AptMessage):
    """
    Data packet structure for a MOT_SET_GEN_MOVE_PARAMS command.

    Fields:
        chan_ident:    The channel being addressed.
        backlash_dist: Channel backlash distance.
    """

    MESSAGE_ID = AptMessageId.MOT_SET_GEN_MOVE_PARAMS.value
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("backlash_dist", apt_long),
    ]


class MOT_GET_GEN_MOVE_PARAMS(AptMessage):
    """
    Header structure for the MOT_GET_GEN_MOVE_PARAMS response. This header is sent as a response to MOT_REQ_GEN_MOVE_PARAMS.

    Fields:
        chan_ident:    The channel being addressed.
        backlash_dist: Channel backlash distance.
    """

    MESSAGE_ID = AptMessageId.MOT_GET_GEN_MOVE_PARAMS.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("backlash_dist", apt_long),
    ]


class MOT_SET_HOME_PARAMS(AptMessage):
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
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("home_dir", apt_word),
        ("limit_switch", apt_word),
        ("home_velocity", apt_long),
        ("offset_dist", apt_long)
    ]


class MOT_GET_HOME_PARAMS(AptMessage):
    """
    Header structure for the MOT_GET_HOME_PARAMS response. This header is sent as a response to MOT_REQ_HOME_PARAMS.

    Fields:
        chan_ident:    The channel being addressed.
        home_dir:      Channel home direction.
        limit_switch:  Channel limit switch.
        home_velocity: Channel homing velocity.
        offset_dist:   Channel offset distance.
    """

    MESSAGE_ID = AptMessageId.MOT_GET_GEN_MOVE_PARAMS.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("home_dir", apt_word),
        ("limit_switch", apt_word),
        ("home_velocity", apt_long),
        ("offset_dist", apt_long)
    ]


class MOT_MOVE_HOMED(AptMessage):
    """
    Header structure for the MOT_MOVE_HOMED response. This header is sent as a response to MOT_MOVE_HOME
    once homing is complete.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        param2:         To be left as 0x00.
        dest:           Destination of message.
        source:         Source of message.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_HOMED.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("param2", apt_byte),
        ("dest", apt_byte),
        ("source", apt_byte),
    ]


class MOT_MOVE_RELATIVE(AptMessage):
    """
    Data packet structure for a MOT_MOVE_RELATIVE command.

    Fields:
        chan_ident:    The channel being addressed.
        rel_dist:      The relative distance to move in encoder units.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_RELATIVE.value
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("rel_dist", apt_long),
    ]


class MOT_MOVE_ABSOLUTE(AptMessage):
    """
    Data packet structure for a MOT_MOVE_ABSOLUTE command.

    Fields:
        chan_ident:    The channel being addressed.
        abs_position:  The position to move to in encoder units.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_ABSOLUTE.value
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("abs_position", apt_long),
    ]


class MOT_MOVE_COMPLETED(AptMessage):
    """
    Header structure for the MOT_MOVE_COMPLETED response. This header is sent as a response to a relative or absolute
    move command once the move has been completed.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        position:       To be left as 0x00.
        reserved:       Destination of message.
        status_bits:    Move status bits.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_COMPLETED.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("position", apt_long),
        ("reserved", apt_long),
        ("status_bits", apt_dword),
    ]


class MOT_MOVE_STOPPED(AptMessage):
    """
    Header structure for the MOT_MOVE_STOPPED response. This header is sent as a response to a relative or absolute
    move command once the move has been stopped.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        position:       To be left as 0x00.
        reserved:       Destination of message.
        status_bits:    Move status bits.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_STOPPED.value
    HEADER_ONLY = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("position", apt_long),
        ("reserved", apt_long),
        ("status_bits", apt_dword),
    ]


class MOT_GET_USTATUSUPDATE(AptMessage):
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
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("chan_ident", apt_word),
        ("position", apt_long),
        ("velocity", apt_word),
        ("motor_current", apt_short),
        ("status_bits", apt_dword),
    ]


class MOT_SET_EEPROMPARAMS(AptMessage):
    """
    Data packet structure for a MOT_SET_EEPROMPARAMS command.

    Fields:
        chan_ident: The channel being addressed.
        msg_id:     ID of message whose settings should be saved.
    """

    MESSAGE_ID = AptMessageId.MOT_SET_EEPROMPARAMS.value
    _fields_: ClassVar[list[tuple[str, type]]] = [("chan_ident", apt_word), ("msg_id", apt_word)]


class POL_GET_SET_PARAMS(AptMessage):
    """ "
    Data packet structure for POL_SET_PARAMS command. It is also the data packet structure for the POL_GET_PARAMS.

    Fields:
        not_used:       This field is not used, but needs to be in the field structure to not break it.
        velocity:       Velocity in range 10% to 100% of 400 degrees/s.
        home_position:  Home position in encoder counts.
        jog_step1:      Size fo jog step to be performed on paddle 1.
        jog_step2:      Size fo jog step to be performed on paddle 2.
        jog_step3:      Size fo jog step to be performed on paddle 3.
    """

    MESSAGE_ID = AptMessageId.POL_GET_PARAMS.value
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("not_used", apt_word),
        ("velocity", apt_word),
        ("home_position", apt_word),
        ("jog_step1", apt_word),
        ("jog_step2", apt_word),
        ("jog_step3", apt_word),
    ]
