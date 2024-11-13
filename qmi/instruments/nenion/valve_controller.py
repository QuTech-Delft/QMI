"""QMI_Instrument driver for Nenion stepper motor driver leak valve controllers."""

from dataclasses import dataclass
import logging
import time

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_TransportDescriptorException, QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# The status info query and return is not clear. Could be a string with several values or just one. Options:
@dataclass
class Status:
    """A dataclass for Nenion status info.

    Attributes:
        run_position: RP<a>, The motor is driving, return actual position <a>.
        in_position:  IP<c>, Return current position <c>.
        stands:       SP<p>, The motor is stopped, return actual position <p>.
        local:        LP<p>, Manual mode, return actual position <p>.
        analog:       AP<p>, Analog mode, return actual position <p>.
        disabled:     DP<p>, Disable was pressed, return actual position <p>.
    """
    run_position: int
    in_position: int
    stands: int
    local: int
    analog: int
    disabled: int

    def __str__(self) -> str:
        """Make the string nice and readable."""
        return "\n".join([k + f"={v}" for k, v in self.__dict__.items()])


class Nenion_ValveController(QMI_Instrument):
    """QMI_Instrument driver class for Nenion valve controllers."""

    DEFAULT_RESPONSE_TIMEOUT = 5.0  # default response timeout in seconds
    VALVE_RANGE = [1, 40000]  # Serial/TCP interface valve range.
    VALVE_RESOLUTION = VALVE_RANGE[1] // 100  # The valve range is divided into 0-100%, resolution is 1%.
    STEP_RESOLUTION = VALVE_RESOLUTION // 10 # The step resolution is 0.1%.
    MOVE_SPEED = 400.0  # Approximate valve move speed, in steps/second.

    def __init__(self, context: QMI_Context, name: str, transport: str):
        """Initialise driver.

        Parameters:
            transport:  QMI transport descriptor to connect to the instrument. Both serial and TCP are accepted.
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport_str = transport
        if not transport.startswith("tcp") and not transport.startswith("serial"):
            raise QMI_TransportDescriptorException("Only serial and TCP transports accepted.")

        self._transport = create_transport(transport)
        # Communication defaults
        self.message_terminator = b"\r"
        # Position tracking
        self._current_position: int | None = None  # TODO: Always 'Null' at start to be able to track from 0%?

    def _set(self, command: str):
        """Helper function for inspecting commands and their return values."""
        self._transport.write(command.encode('ascii') + self.message_terminator)
        response = self._transport.read_until(self.message_terminator, self._timeout).decode()
        print(f"Controller command {command} resulted in response {response}.")  # For testing with HW
        _logger.debug("Controller command %s resulted in response %s." % command, response)
        # TODO: Depending on responses, create conditional behaviour

    def _get(self, command: str) -> str:
        """Helper function to get responses from the controller."""
        self._transport.write(command.encode('ascii') + self.message_terminator)
        response = self._transport.read_until(self.message_terminator, self._timeout).decode()
        print(f"Controller command {command} resulted in response {response}.")  # For testing with HW
        _logger.debug("Controller command %s resulted in response %s." % command, response)

        return response

    @rpc_method
    def open(self) -> None:
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        super().close()
        self._transport.close()

    @rpc_method
    def get_status(self) -> Status:
        """Get status info from the controller.

        Returns:
            status: Status information as a dataclass.
        """
        status = self._get("S")
        # TODO: It is not clear what this returns. We might have to follow
        #  it with other calls like
        run_position = self._get("RP")
        in_position = self._get("IP")
        stands = self._get("SP")
        local = self._get("LP")
        analog = self._get("AP")
        disabled = self._get("DP")

        return Status(
            run_position,
            in_position,
            stands,
            local,
            analog,
            disabled
        )

    @rpc_method
    def enable_motor_current(self) -> None:
        """Enable the motor current."""
        self._set("E")

    @rpc_method
    def disable_motor_current(self) -> None:
        """Enable the motor current."""
        self._set("D")

    @rpc_method
    def open_to_target(self, target: int) -> None:
        """Set the target percentage value for valve opening and drive.

        Parameters:
            target: The target percentage in range [0-100%].

        Raises:
            ValueError: By invalid percentage, must be between 0-100%.
        """
        if target not in range(0, 101):
            raise ValueError(f"Target percentage {target} is not a valid value!")

        target_step = target * self.VALVE_RESOLUTION
        if target_step == 0:
            self._set(f"G1")  # According to manual 1 is the minimum, not 0.

        else:
            self._set(f"G{target_step}")

        # TODO: Need some sleep afterwards?
        # if self._current_position is not None:
        #     time.sleep(abs(self._current_position - target_step) / self.MOVE_SPEED)

        self._current_position = target_step

    @rpc_method
    def fully_close(self) -> None:
        """Special command that calls "Null" to close the valve at 1/3rd of max speed."""
        self._set("N")
        self._current_position = 0  # Actually it is 1, but to avoid shift by 1 for consecutive steps, set to 0.

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

        Raises:
            ValueError: By invalid number of steps. Must be in range 1 to 9.
        """
        if steps not in range(1, 10):
            raise ValueError(f"Invalid steps, {steps}, given for controller.")

        for _ in range(steps):
            if self._current_position is not None:
                if self._current_position - self.STEP_RESOLUTION < self.VALVE_RANGE[0]:
                    raise QMI_InstrumentException("Target position will be beyond limits. Excepting!")

                self._current_position -= self.STEP_RESOLUTION

            self._set("M")  # TODO: Need some sleep between steps?
            # time.sleep(self.STEP_RESOLUTION / self.MOVE_SPEED)

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
            if self._current_position is not None:
                if self._current_position + self.STEP_RESOLUTION > self.VALVE_RANGE[1]:
                    raise QMI_InstrumentException("Target position will be beyond limits. Excepting!")

                self._current_position += self.STEP_RESOLUTION

            self._set("P")  # TODO: Need some sleep between steps?
            # time.sleep(self.STEP_RESOLUTION / self.MOVE_SPEED)

