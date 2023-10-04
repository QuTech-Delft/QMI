"""
Instrument driver for the Newport SMC100PP motion controller.
"""
import logging
from time import sleep
from typing import Dict, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.rpc import rpc_method
from qmi.instruments.newport.actuators import LinearActuator
from qmi.instruments.newport.single_axis_motion_controller import Newport_SingleAxisMotionController

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Newport_SMC100PP(Newport_SingleAxisMotionController):
    """Instrument driver for the Newport SMC100PP servo motion controller."""

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 serial: str,
                 actuators: Dict[Optional[int], LinearActuator],
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

    @rpc_method
    def get_micro_step_per_full_step_factor(self, controller_address: Optional[int] = None) -> float:
        """
        Get the micro-step per full step factor of the motor configuration.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            factor: The micro-step per full step factor as float.
        """
        self.controller_address = controller_address
        _logger.info(
            "Getting the micro-step per full step factor of instrument [%s]", self._name)
        # instrument must be in CONFIGURATION state to get the full step factor.
        self._enter_configuration_state()
        factor = self._scpi_protocol.ask(
            self._build_command("FRM?"))
        self._check_error()
        self._exit_configuration_state()
        return float(factor[4:])

    @rpc_method
    def set_micro_step_per_full_step_factor(self, factor: int, controller_address: Optional[int] = None) -> None:
        """
        Set the micro-step per full step factor of the motor configuration.

        Parameters:
            factor:             Micro-step per full step factor.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if factor <= 0 or factor > 2000:
            raise QMI_InstrumentException(
                f"Provided value {factor} not in valid range 0 < factor <= 2000.")

        self.controller_address = controller_address
        _logger.info(
            "Setting the micro-step per full step factor of instrument [%s] to [%i]", self._name, factor)
        # instrument must be in CONFIGURATION state to set the full step factor.
        self._enter_configuration_state()
        self._scpi_protocol.write(self._build_command(
            "FRM", factor))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self._exit_configuration_state()

    @rpc_method
    def get_motion_distance_per_full_step(self, controller_address: Optional[int] = None) -> float:
        """
        Get the motion distance per motor’s full step.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            m_dist: Motion distance as float.
        """
        self.controller_address = controller_address
        _logger.info(
            "Getting the motion distance per motor’s full step value of instrument [%s]", self._name)
        # instrument must be in CONFIGURATION state to get the motion distance.
        self._enter_configuration_state()
        m_dist = self._scpi_protocol.ask(
            self._build_command("FRS?"))
        self._check_error()
        self._exit_configuration_state()
        return float(m_dist[4:])

    @rpc_method
    def set_motion_distance_per_full_step(self, m_dist: float, controller_address: Optional[int] = None) -> None:
        """
        Set the motion distance per motor’s full step.

        Parameters:
            m_dist:             Motion distance per motor's full step.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if m_dist <= self.MIN_FLOAT_LIMIT or m_dist >= self.MAX_FLOAT_LIMIT:
            raise QMI_InstrumentException(
                f"Provided value {m_dist} not in valid range {self.MIN_FLOAT_LIMIT} < m_dist < {self.MAX_FLOAT_LIMIT}."
            )

        self.controller_address = controller_address
        _logger.info(
            "Setting the motion distance per motor’s full step of instrument [%s] to [%f]", self._name, m_dist)
        # instrument must be in CONFIGURATION state to set the motion distance.
        self._enter_configuration_state()
        self._scpi_protocol.write(self._build_command(
            "FRS", m_dist))
        self._check_error()
        self._exit_configuration_state()

    @rpc_method
    def get_base_velocity(self, controller_address: Optional[int] = None) -> float:
        """
        Get the profile generator base velocity.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            base_velocity: Base velocity as float.
        """
        self.controller_address = controller_address
        _logger.info(
            "Getting the profile generator base velocity of instrument [%s]", self._name)
        # instrument must be in CONFIGURATION, DISABLE or READY state to get the base velocity.
        try:
            config_state = False
            self._state_ready_check("base velocity")

        except QMI_InstrumentException:
            self._enter_configuration_state()
            config_state = True

        base_velocity = self._scpi_protocol.ask(
            self._build_command("VB?"))
        self._check_error()
        if config_state:
            self._exit_configuration_state()

        else:
            self._exit_disable_state()

        return float(base_velocity[3:])

    @rpc_method
    def set_base_velocity(
            self, base_velocity: float, persist: Optional[bool] = False, controller_address: Optional[int] = None
    ) -> None:
        """
        Set the profile generator base velocity. It must not be larger than the maximum velocity set by VA command.

        Parameters:
            base_velocity:      New profile generator base velocity.
            persist:            Flag to indicate if the velocity should be persisted to the controller's memory, so it
                                is still available after powering down the controller. When not persisted, the maximum
                                base velocity that can be set is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        if persist:
            self._enter_configuration_state()

        else:
            self._state_ready_check("base velocity")

        response = self._scpi_protocol.ask(
            self._build_command("VA?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        velocity = float(response[3:])
        if base_velocity < 0 or base_velocity > velocity:
            if persist:
                self._exit_configuration_state()
            raise QMI_InstrumentException(
                f"Provided value {base_velocity} not in valid range 0 <= base_velocity <= {velocity}.")

        _logger.info(
            "Setting the profile generator base velocity of instrument [%s] to [%f]", self._name, base_velocity)
        self._scpi_protocol.write(self._build_command(
            "VB", base_velocity))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self._exit_configuration_state()
