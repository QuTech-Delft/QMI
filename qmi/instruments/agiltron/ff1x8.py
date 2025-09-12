"""
QMI driver for the Agiltron FF 1x8 optical switch driver.

The protocol implemented in this driver is documented in the document
'Command_List_for_CL-LB_Switch_Driver_5-20-2020.doc'

To use the instrument on Windows, it is necessary to have Virtual COM Port (VCP) driver installed on the PC.
See https://ftdichip.com/Drivers/vcp-drivers/.
"""

import logging

from qmi.instruments.agiltron._ff_optical_switch import Agiltron_FfOpticalSwitch

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Agiltron_FF1x8(Agiltron_FfOpticalSwitch):
    """QMI driver for the Agiltron FF 1x8 optical switch driver.

    Attributes:
        CHANNELS: The number of channels in the switch.
    """
    CHANNELS = 8
