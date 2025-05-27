"""
Module for the APT protocol used by Thorlabs. The documentation for the protocol can be found
here https://www.thorlabs.com/Software/Motion%20Control/APT_Communications_Protocol.pdf
"""

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
from typing import ClassVar, Type, TypeVar

from qmi.core.transport import QMI_Transport
from qmi.core.exceptions import QMI_InstrumentException

# APT format specifiers
apt_word = c_uint16
apt_short = c_int16
apt_dword = c_uint32
apt_long = c_int32
apt_char = c_char
# this format specifier is not defined in the APT protocol manual but is helpful for packets that are divided into
# single bytes
apt_byte = c_uint8


class AptStatusBits(Enum):
    """Status bits for a status update message."""

    P_MOT_SB_CWHARDLIMIT = 0x00000001  # clockwise hardware limit switch
    P_MOT_SB_CCWHARDLIMIT = 0x00000002  # counter clockwise hardware limit switch
    P_MOT_SB_CWSOFTLIMIT = 0x00000004  # clockwise software limit switch
    P_MOT_SB_CCWSOFTLIMIT = 0x00000008  # counter clockwise software limit switch
    P_MOT_SB_INMOTIONCW = 0x00000010  # in motion, clockwise direction
    P_MOT_SB_INMOTIONCCW = 0x00000020  # in motion, counter clockwise direction
    P_MOT_SB_JOGGINGCW = 0x00000040  # jogging in clockwise direction
    P_MOT_SB_JOGGINGCCW = 0x00000080  # jogging in counter clockwise direction
    P_MOT_SB_CONNECTED = 0x00000100  # motor recognised by controller
    P_MOT_SB_HOMING = 0x00000200  # motor is homing
    P_MOT_SB_HOMED = 0x00000400  # motor is homed
    P_MOT_SB_INITIALISING = 0x00000800  # motor performing phase initialisation
    P_MOT_SB_TRACKING = 0x00001000  # actual position is within the tracking window
    P_MOT_SB_SETTLED = 0x00002000  # motor not moving and at target position
    P_MOT_SB_POSITIONERERROR = 0x00004000  # actual position outside margin specified around trajectory position
    P_MOT_SB_INSTRERROR = 0x00008000  # unable to execute command
    P_MOT_SB_INTERLOCK = 0x00010000  # used in controllers where a seperate signal is used to enable the motor
    P_MOT_SB_OVERTEMP = 0x00020000  # motor or motor power driver electronics reached maximum temperature
    P_MOT_SB_BUSVOLTFAULT = 0x00040000  # low supply voltage
    P_MOT_SB_COMMUTATIONERROR = 0x00080000  # problem with motor commutation. Can only be recovered with power cycle
    P_MOT_SB_DIGIP1 = 0x00100000  # state of digital input 1
    P_MOT_SB_DIGIP2 = 0x00200000  # state of digital input 2
    P_MOT_SB_DIGIP4 = 0x00400000  # state of digital input 3
    P_MOT_SB_DIGIP8 = 0x00800000  # state of digital input 4
    P_MOT_SB_OVERLOAD = 0x01000000  # some form of motor overload
    P_MOT_SB_ENCODERFAULT = 0x02000000  # encoder fault
    P_MOT_SB_OVERCURRENT = 0x04000000  # motor exceeded continuous current limit
    P_MOT_SB_BUSCURRENTFAULT = 0x08000000  # excessive current being drawn from motor power supply
    P_MOT_SB_POWEROK = 0x10000000  # controller power supplies operating normally
    P_MOT_SB_ACTIVE = 0x20000000  # controller executing motion commend
    P_MOT_SB_ERROR = 0x40000000  # indicates an error condition
    P_MOT_SB_ENABLED = 0x80000000  # motor output enabled, with controller maintaining position


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


class AptChannelState(Enum):
    """Channel state"""

    ENABLE = 0x01
    DISABLE = 0x02


class AptChannelJogDirection(Enum):
    """Jog direction"""

    FORWARD = 0x01
    BACKWARD = 0x02


class AptChannelHomeDirection(Enum):
    """Possible values for the ``home_direction`` field in the homing parameters."""
    FORWARD = 0x01
    REVERSE = 0x02


class AptChannelHomeLimitSwitch(Enum):
    """Possible values for the ``limit_switch`` field in the homing parameters."""
    REVERSE = 0x01
    FORWARD = 0x04


class AptMessageHeaderWithTwoParams(LittleEndianStructure):
    """
    This is the version of the APT message header when no data packet follows a header.
    """

    _pack_ = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", c_uint16),
        ("param1", c_uint8),
        ("param2", c_uint8),
        ("dest", c_uint8),
        ("source", c_uint8),
    ]


class AptMessageHeaderWithThreeParams(LittleEndianStructure):
    """
    This is the version of the APT message header when no data packet follows a header.
    """

    _pack_ = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", c_uint16),
        ("param1", apt_long),
        ("param2", apt_long),
        ("param3", apt_long),
    ]


class AptMessageHeaderForData(LittleEndianStructure):
    """
    This is the version of the APT message header when a data packet follows a header.
    """

    _pack_ = True
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("message_id", c_uint16),
        ("data_length", c_uint16),
        ("dest", c_uint8),
        ("source", c_uint8),
    ]


class AptMessage(LittleEndianStructure):
    """
    Base class for an APT message.
    """

    MESSAGE_ID: int
    HEADER_ONLY: bool = False
    _pack_ = True


T = TypeVar("T", bound=AptMessage)


class AptProtocol:
    """
    Implement the Thorlabs APT protocol primitives.
    """

    HEADER_SIZE_BYTES = 6

    def __init__(
        self,
        transport: QMI_Transport,
        apt_device_address: int = 0x50,
        host_address: int = 0x01,
        default_timeout: float | None = None,
    ):
        """Initialize the Thorlabs APT protocol handler.

        Parameters:
            transport:          Instance of `QMI_Transport` to use for sending APT commands to the instrument.
            apt_device_address: The address of the APT device. By default it is 0x50 which is a generic USB hardware
                                unit.
            host_address:       The address of the host that sends and receives messages. By default it is 0x01 which
                                is a host controller such as a PC.
            default_timeout:    Optional default response timeout in seconds.
                                The default is to wait indefinitely until a response is received.
        """
        self._transport = transport
        self._timeout = default_timeout
        self._apt_device_address = apt_device_address
        self._host_address = host_address

    def write_two_param_command(
        self,
        message_id: int,
        param1: int = 0x00,
        param2: int = 0x00,
    ) -> None:
        """
        Send an APT protocol command that is a header (i.e. 6 bytes) with params.

        Parameters:
            message_id: ID of message to send.
            param1:     Parameter 1 to be sent with default value of 0x00.
            param2:     Parameter 2 to be sent with default value of 0x00.
        """
        # Make the command.
        msg = AptMessageHeaderWithTwoParams(
            message_id,
            param1,
            param2,
            self._apt_device_address,
            self._host_address,
        )
        # Send command.
        self._transport.write(bytearray(msg))

    def write_three_param_command(
        self,
        message_id: int,
        param1: int = 0x00,
        param2: int = 0x00,
        param3: int = 0x00,
    ) -> None:
        """
        Send an APT protocol command that is a header (i.e. 6 bytes) with params.

        Parameters:
            message_id: ID of message to send.
            param1:     Parameter 1 to be sent with default value of 0x00.
            param2:     Parameter 2 to be sent with default value of 0x00.
            param3:     Parameter 3 to be sent with default value of 0x00.
        """
        # Make the command.
        msg = AptMessageHeaderWithThreeParams(
            message_id,
            param1,
            param2,
            param3
        )
        # Send command.
        self._transport.write(bytearray(msg))

    def write_home_param_command(
        self,
        message_id: int,
        home_dir: int,
        limit_switch: int,
        home_velocity: int,
        offset_dist: int
    ) -> None:
        """
        Send an APT protocol command that is a header (i.e. 6 bytes) with params.

        Parameters:
            message_id: ID of message to send.
        """
        # Make the command.
        msg = AptMessageHeaderWithThreeParams(
            message_id,
            home_dir,
            limit_switch,
            home_velocity,
            offset_dist
        )
        # Send command.
        self._transport.write(bytearray(msg))

    def write_data_command(self, message_id: int, data: T) -> None:
        """
        Send and APT protocol command with data.
        """
        # Get size of data packet.
        data_length = sizeof(data)

        # Make the header.
        msg = AptMessageHeaderForData(message_id, data_length, self._apt_device_address | 0x80, self._host_address)

        # Send the header and data packet.
        self._transport.write(bytearray(msg) + bytearray(data))

    def ask(self, data_type: Type[T], timeout: float | None = None) -> T:
        """
        Ask for a response.

        Parameters:
            data_type:  Data type of the data packet that follows the header.
            timeout:    Optional response timeout in seconds.

        Returns:
            The requested data typed as the provided data type.
        """

        if timeout is None:
            timeout = self._timeout

        # Read the header first.
        header_bytes = self._transport.read(nbytes=self.HEADER_SIZE_BYTES, timeout=timeout)
        if data_type.HEADER_ONLY:
            return data_type.from_buffer_copy(header_bytes)
        header = AptMessageHeaderForData.from_buffer_copy(header_bytes)
        data_length = header.data_length

        # Read the data packet that follows the header.
        data_bytes = self._transport.read(nbytes=data_length, timeout=timeout)

        # Check that the received message ID is the ID that is expected.
        if data_type.MESSAGE_ID != header.message_id:
            raise QMI_InstrumentException(
                f"Expected message with ID {data_type.MESSAGE_ID}, but received {header.message_id}"
            )

        return data_type.from_buffer_copy(data_bytes)
