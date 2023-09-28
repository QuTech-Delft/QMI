"""
Instrument driver for the Newport CONEX-CC DC servo motion controller.
"""
from typing import Dict, Optional
from qmi.core.context import QMI_Context
from qmi.instruments.newport.actuators import LinearActuator
from qmi.instruments.newport.single_axis_motion_controller import Newport_SingleAxisMotionController


class Newport_ConexCC(Newport_SingleAxisMotionController):
    """Instrument driver for the Newport CONEX-CC DC servo motion controller."""

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 serial: str,
                 actuators: Dict[Optional[int], LinearActuator],
                 baudrate: int = 921600) -> None:
        """Initialize driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
            serial:     The serial number of the device.
            actuators:  The linear actuator that this controller will drive.
            baudrate:   The baudrate of the instrument. Defaults to 921600.
        """
        super().__init__(context, name, transport, serial, actuators, baudrate)
