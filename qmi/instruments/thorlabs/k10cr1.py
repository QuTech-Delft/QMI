"""Instrument driver for the Thorlabs K10CR1/M motorized rotational mount.

This driver communicates with the device via a USB serial port, using the Thorlabs APT protocol. For details,
see the document "Thorlabs APT Controllers Host-Controller Communications Protocol", issue 25 from Thorlabs.

This driver has only been tested under Linux. In principle it should also work under Windows
after creating a virtual COM port for the internal USB serial port in the instrument.
"""

import logging

from qmi.core.context import QMI_Context
from qmi.core.rpc import rpc_method
from qmi.instruments.thorlabs.k10crx import Thorlabs_K10CRxBase

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Thorlabs_K10CR1(Thorlabs_K10CRxBase):
    """Instrument driver for the Thorlabs K10CR1/M motorized rotational mount."""

    # Maximum velocity in degrees/second
    MAX_VELOCITY = 10

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver.

        The motorized mount presents itself as a USB serial port.
        The transport descriptor should refer to the serial port device,
        e.g. "serial:/dev/ttyUSB1"

        Parameters:
            name:      Name for this instrument instance.
            transport: Transport descriptor to access the instrument.
        """
        super().__init__(context, name, transport)

    @rpc_method
    def open(self) -> None:
        try:
            super().open()
            # Check that this device is a K10CR1 motor.
            # Otherwise we should not talk to it, since we don't want to send
            # inappropriate commands to some unsupported device.
            self._check_k10crx("1")

        except Exception:
            # Close the transport if an error occurred during initialization of the instrument.
            self._transport.close()
            raise

        super(Thorlabs_K10CRxBase, self).open()
