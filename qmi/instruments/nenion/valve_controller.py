"""QMI_Instrument driver for Nenion stepper motor driver leak valve controllers."""

import logging

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Nenion_ValveController(QMI_Instrument):
    """QMI_Instrument driver class for Nenion valve controllers."""

    # default response timeout in seconds
    DEFAULT_RESPONSE_TIMEOUT = 5.0
    VALVE_RESOLUTION = 400  # The valve range of 0-100 % is divided into 40000 steps

    def __init__(self, context: QMI_Context, name: str, transport: str):
        """Initialise driver.

        Parameters:
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport_str = transport
        self._transport = create_transport(transport)
        # Communication defaults
        self.message_terminator = b"\r"

    def _set(self, command: str):
        """Helper function for inspecting commands and their return values."""
        self._transport.write(command.encode('ascii') + self.message_terminator)
        response = self._transport.read_until(self.message_terminator, self._timeout)
        print(f"Controller command {command} resulted in response {response}.")  # For testing with HW
        _logger.debug("Controller command %s resulted in response %s." % command, response)
        # TODO: Depending on responses, create conditional behaviour

    @rpc_method
    def open(self) -> None:
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        super().close()
        self._transport.close()

    @rpc_method
    def enable_motor_current(self) -> None:
        """Enable the motor current."""
        self._set("E")

    @rpc_method
    def disable_motor_current(self) -> None:
        """Enable the motor current."""
        self._set("D")

    @rpc_method
    def valve_open_percentage(self, target: int) -> None:
        """Set the target percentage value for valve opening.

        Parameters:
            target: The target percentage in range [0-100%].
        """
        if target not in range(0, 101):
            raise ValueError(f"Target percentage {target} is not a valid value!")

        target_step = target * self.VALVE_RESOLUTION
        if target_step == 0:
            target_step = 1  # Needs to be at least 1

        self._set(f"G{target_step}")

    @rpc_method
    def fully_close(self) -> None:
        """Special command that calls "Null" to close the valve at 1/3rd of max speed."""
        self._set("N")

    @rpc_method
    def halt_motor(self) -> None:
        """Call to halt motor immediately."""
        self._set("H")

    @rpc_method
    def step_close(self, steps: int = 1):
        """Drives the valve towards close with 0,1% per step. This can be used for fine-tuning the
        position between percentages. Only allowed between 1 step and up to 9 steps.

        Parameters:
            steps: How many steps should the controller do. Default is 1.
        """
        if steps not in range(1, 10):
            raise ValueError(f"Invalid steps, {steps}, given for controller.")

        for _ in range(steps):
            self._set("M")  # TODO: Need some sleep between steps?

    @rpc_method
    def step_open(self, steps: int = 1):
        """Drives the valve towards open with 0,1% per step. This can be used for fine-tuning the
        position between percentages. Only allowed between 1 step and up to 9 steps.

        Parameters:
            steps: How many steps should the controller do. Default is 1.
        """
        if steps not in range(1, 10):
            raise ValueError(f"Invalid steps, {steps}, given for controller.")

        for _ in range(steps):
            self._set("P")  # TODO: Need some sleep between steps?
