"""
Instrument driver for the Newport CONEX-CC DC servo motion controller.
"""
from typing import Dict
from qmi.core.context import QMI_Context
from qmi.instruments.newport.actuators import LinearActuator
from qmi.instruments.newport.single_axis_motion_controller import Newport_Single_Axis_Motion_Controller


class Newport_ConexCC(Newport_Single_Axis_Motion_Controller):
    """Instrument driver for the Newport CONEX-CC DC servo motion controller."""

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 serial: str,
                 actuators: Dict[int, LinearActuator],
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
