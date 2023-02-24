"""QMI driver for the Agiltron FF 1x4 optical switch driver.

The protocol implemented in this driver is documented in the document
'Command_List_for_CL-LB_Switch_Driver_5-20-2020.doc'

To use the instrument on Windows, it is necessary to have Virtual COM Port (VCP) driver installed on the PC.
See https://ftdichip.com/Drivers/vcp-drivers/.

"""

import logging
from typing import List, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Agiltron_FF1x4(QMI_Instrument):
    """QMI driver for the Agiltron FF 1x4 optical switch driver.
    driver-specific constants:
    DEFAULT_TIMEOUT: float. The default time-out for the optical switch serial commands
    CHANNELS: int. The number of channels in the switch.
    """
    DEFAULT_TIMEOUT = 0.500  # 500 ms ought to be plenty.
    CHANNELS = 4

    def __init__(self, context: QMI_Context, name: str, transport: str, timeout: Optional[float] = None):
        """

        :param context: QMI_Context object for the instrument driver.
        :param name: string. Name for this instrument instance.
        :param transport: string. Transport descriptor to access the instrument.
        :param timeout: Optional[float]. Alternative timeout for the default instrument serial communication.
        """
        super().__init__(context, name)
        self._transport = create_transport(
            transport,
            default_attributes={"baudrate": 9600, "bytesize": 8, "parity": "N", "stopbits": 1, "rtscts": False},
        )

        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT
        self._timeout = timeout

    def _send_command(self, cmd_list: List[int]) -> None:
        """
        Internal method to check there are correct number of bytes in the input list and sends it to the device.
        :param cmd_list: List[int]. A list of length of four, with "hex" bytes as entries
        """
        if len(cmd_list) != 4:
            raise QMI_InstrumentException(
                "The byte command list must have four byte entries. Input has {}".format(len(cmd_list))
            )

        msg = bytes(cmd_list)
        self._transport.write(msg)

    def _read_reply(self) -> bytes:
        """
        Internal method to query the device for response and to return it to the caller
        :return response: bytes string. Length of four bytes if read succeeded, otherwise empty string.
        """
        response = b""
        try:
            response = self._transport.read(4, timeout=self._timeout)  # We expect to read 4 bytes

        finally:
            return response

    @rpc_method
    def open(self) -> None:
        """ Open the connection to the instrument using the transport. """
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        self._transport.discard_read()
        super().open()

    @rpc_method
    def close(self) -> None:
        """ Close the connection to the instrument. """
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_active_channel(self) -> int:
        """
        Retrieve the current active channel in the switch.
        :return channel_active: int. The active channel number
        """
        self._send_command([0x01, 0x11, 0x00, 0x00])
        reply = self._read_reply()
        channel_active = reply[-1]  # Last byte informs the active channel number

        return channel_active

    @rpc_method
    def set_channel_active(self, channel: int) -> None:
        """
        Set the input channel as the active channel in the switch.
        :param channel: int, the input channel number
        """
        if channel < 1 or channel > self.CHANNELS:
            raise ValueError(
                "Channel number {} not in range of available channels 1-{}".format(channel, self.CHANNELS)
            )

        set_active_channel_list = [0x01, 0x12, 0x00, int(channel)]
        self._send_command(set_active_channel_list)
        # Check the echo that correct channel was set
        reply = self._read_reply()
        try:
            assert reply == bytes(set_active_channel_list)

        except AssertionError:
            raise QMI_InstrumentException("The reply {} does not match request {}. Correct channel not set.")
