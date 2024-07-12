"""Module containing the packets for the APT protocol."""

from typing import List, Tuple
from qmi.instruments.thorlabs.apt_protocol import (
    AptMessage,
    AptMessageId,
    apt_long,
    apt_dword,
    apt_char,
    apt_word,
    apt_byte,
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
    _fields_: List[Tuple[str, type]] = [
        ("serial_number", apt_long),
        ("model_number", apt_char * 8),
        ("type", apt_word),
        ("firmware_version", apt_dword),
        (
            "internal",
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
    _fields_: List[Tuple[str, type]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("enable_state", apt_byte),
        ("dest", apt_byte),
        ("source", apt_byte),
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
    _fields_: List[Tuple[str, type]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("param2", apt_byte),
        ("dest", apt_byte),
        ("source", apt_byte),
    ]


class MOT_MOVE_ABSOLUTE(AptMessage):
    """
    Data packet structure for a MOT_SMOVE_ABSOLUTE command.

    Fields:
        chan_ident:         The channel being addressed.
        absolute_distance:  The distance to move in encoder units.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_ABSOLUTE.value
    _fields_: List[Tuple[str, type]] = [
        ("chan_ident", apt_word),
        ("absolute_distance", apt_long),
    ]


class MOT_MOVE_COMPLETED(AptMessage):
    """
    Header structure for the MOT_MOVE_COMPLETED response. This header is sent as a response to a relative or absolute
    move command once the move has been completed.

    Fields:
        message_id:     ID of message.
        chan_ident:     Channel number.
        param2:         To be left as 0x00.
        dest:           Destination of message.
        source:         Source of message.
    """

    MESSAGE_ID = AptMessageId.MOT_MOVE_COMPLETED.value
    HEADER_ONLY = True
    _fields_: List[Tuple[str, type]] = [
        ("message_id", apt_word),
        ("chan_ident", apt_byte),
        ("param2", apt_byte),
        ("dest", apt_byte),
        ("source", apt_byte),
    ]


class MOT_GET_USTATUSUPDATE(AptMessage):
    """
    Data packet structure for a MOT_GET_USTATUSUPDATE command.

    Fields:
        chan_ident:     The channel being addressed.
        position:       The position in encoder counts.
        velocity:       Velocity in controller units.
        motor_current:  Motor current in mA.
        status_bits:    Status bits that provide various errors and indications.
    """

    MESSAGE_ID = AptMessageId.MOT_GET_USTATUSUPDATE.value
    _fields_: List[Tuple[str, type]] = [
        ("chan_ident", apt_word),
        ("position", apt_long),
        ("velocity", apt_word),
        ("motor_current", apt_word),
        ("status_bits", apt_dword),
    ]


class MOT_SET_EEPROMPARAMS(AptMessage):
    """
    Data packet structure for a MOT_SET_EEPROMPARAMS command.

    Fields:
        chan_ident: The channel being addressed.
        msg_id:     ID of message whose settings should be save.
    """

    MESSAGE_ID = AptMessageId.MOT_SET_EEPROMPARAMS.value
    _fields_: List[Tuple[str, type]] = [("chan_ident", apt_word), ("msg_id", apt_word)]


class POL_GET_SET_PARAMS(AptMessage):
    """ "
    Data packet structure for POL_SET_PARAMS command. It is also the data packet structure for the POL_SET_PARAMS.

    Fields:
        not_used:       This field is not used, but needs to be in the field structure to not break it.
        velocity:       Velocity in range 10% to 100% of 400 degrees/s.
        home_position:  Home position in encoder counts.
        jog_step1:      Size fo jog step to be performed on paddle 1.
        jog_step2:      Size fo jog step to be performed on paddle 2.
        jog_step3:      Size fo jog step to be performed on paddle 3.
    """

    MESSAGE_ID = AptMessageId.POL_GET_PARAMS.value
    _fields_: List[Tuple[str, type]] = [
        ("not_used", apt_word),
        ("velocity", apt_word),
        ("home_position", apt_word),
        ("jog_step1", apt_word),
        ("jog_step2", apt_word),
        ("jog_step3", apt_word),
    ]
