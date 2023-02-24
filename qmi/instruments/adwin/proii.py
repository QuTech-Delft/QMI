"""
Instrument driver for the Adwin Pro II. Inherits from Adwin_Base class in adwin.py
"""
from qmi.core.context import QMI_Context
from qmi.instruments.adwin.adwin import Adwin_Base


class Adwin_ProII(Adwin_Base):
    """Instrument driver for Adwin real-time microcontroller.

    This driver is specific for the Adwin Pro 2.
    """

    def __init__(self, context: QMI_Context, name: str, device_no: int) -> None:
        """Initialize the Adwin driver.

        Parameters:
            context: QMI context.
            name: Name for this instrument instance.
            device_no: Adwin device number.
        """
        super().__init__(context, name, device_no)
