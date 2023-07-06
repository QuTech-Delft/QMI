"""
Instrument driver for the Newport SMC100CC motion controller.
"""
from typing import Dict
from qmi.core.context import QMI_Context
from qmi.instruments.newport.actuators import LinearActuator
from qmi.instruments.newport.single_axis_motion_controller import Newport_Single_Axis_Motion_Controller


class Newport_SMC100CC(Newport_Single_Axis_Motion_Controller):
    """Instrument driver for the Newport SMC100CC servo motion controller."""

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 serial: str,
                 actuators: Dict[int, LinearActuator],
                 baudrate: int = 57600) -> None:
        """Initialize driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
            serial:     The serial number of the instrument.
            actuators:  The linear actuators that this controller will drive. Each controller address
                        drives a linear actuator. The key of the dictionary is the controller address
                        and the value is the actuator that it drives.
            baudrate:   The baudrate of the instrument. Defaults to 57600.
        """
        super().__init__(context, name, transport, serial,
                         actuators, baudrate)
