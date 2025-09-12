"""
A base class module for the Agiltron FF optical switch drivers.

The protocol implemented in this driver is documented in the document
'Command_List_for_CL-LB_Switch_Driver_5-20-2020.doc'

To use the instrument on Windows, it is necessary to have Virtual COM Port (VCP) driver installed on the PC.
See https://ftdichip.com/Drivers/vcp-drivers/.
"""

import logging

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Agiltron_FfOpticalSwitch(QMI_Instrument):
    """QMI driver base class for the Agiltron FF optical switch drivers.

    Attributes:
        DEFAULT_TIMEOUT: The default timeout for the optical switch serial commands.
        CHANNELS:        The number of channels in the switch.
    """
    DEFAULT_TIMEOUT = 0.500  # 500 ms should be plenty
    CHANNELS = 1

    def __init__(self, context: QMI_Context, name: str, transport: str, timeout: float | None = None):
        """Initialize the driver.

        Parameters:
            context:   QMI_Context object for the instrument driver
            name:      Name for this instrument instance
            transport: Transport descriptor to access the instrument
            timeout:   Alternative timeout for the instrument serial communication.
        """
        super().__init__(context, name)
        self._transport = create_transport(
            transport,
            default_attributes={"baudrate": 9600, "bytesize": 8, "parity": "N", "stopbits": 1, "rtscts": False},
        )

        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT
        self._timeout = timeout

    def _send_command(self, cmd_list: list[int]) -> None:
        """Send a 4-byte command to the device.

        Parameters:
            cmd_list: A list of length of four, with "hex" bytes as entries.

        Raises:
            QMI_InstrumentException: If the inputted command list is not of expected length of four.
        """
        if len(cmd_list) != 4:
            raise QMI_InstrumentException(
                f"The byte command list must have four entries. Input has {len(cmd_list)}"
            )
        msg = bytes(cmd_list)
        self._transport.write(msg)

    def _read_reply(self) -> bytes:
        """Read a 4-byte reply from the device.

        Returns:
            response: Four bytes if read succeeded, otherwise empty string.
        """
        response = b""
        try:
            response = self._transport.read(4, timeout=self._timeout)  # 4 bytes expected
        finally:
            return response

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        self._transport.discard_read()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def get_active_channel(self) -> int:
        """Retrieve the current active channel in the switch.

        Returns:
            channel_active: The active channel number.
        """
        self._send_command([0x01, 0x11, 0x00, 0x00])
        reply = self._read_reply()
        channel_active = reply[-1]  # The last byte has the active channel number
        return channel_active

    @rpc_method
    def set_channel_active(self, channel: int) -> None:
        """Set the active channel in the switch.

        Parameters:
             channel: New active channel number.

        Raises:
            ValueError: If the input channel number is not in valid range for the switch.
        """
        if not 1 <= channel <= self.CHANNELS:
            raise ValueError(
                f"Channel number {channel} not in range of available channels 1-{self.CHANNELS}"
            )

        set_active_channel_list = [0x01, 0x12, 0x00, int(channel)]
        self._send_command(set_active_channel_list)

        # Check the echo that correct channel was set
        reply = self._read_reply()
        try:
            assert reply == bytes(set_active_channel_list)
        except AssertionError:
            raise QMI_InstrumentException(
                f"The reply {reply!r} does not match request {set_active_channel_list}. Correct channel not set."
            )
