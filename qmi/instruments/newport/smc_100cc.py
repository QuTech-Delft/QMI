"""
Instrument driver for the Newport SMC100CC motion controller.
"""
import logging
from time import sleep
from typing import Dict, Optional
import enum

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.rpc import rpc_method
from qmi.instruments.newport.actuators import LinearActuator
from qmi.instruments.newport.single_axis_motion_controller import Newport_Single_Axis_Motion_Controller

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class ControlLoopState(enum.IntEnum):
    """Control loop states of the controller."""
    OPEN = 0
    CLOSED = 1


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

    @rpc_method
    def get_encoder_increment_value(self, controller_address: Optional[int] = None) -> float:
        """
        Get the encoder increment value.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            Encoder increment value.
        """
        _logger.info(
            "Getting encoder increment value of instrument [%s]", self._name)
        # instrument must be in configuration state to get the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("SU?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return self._actuators[self.controller_address].ENCODER_RESOLUTION / float(res[3:])

    @rpc_method
    def set_encoder_increment_value(self, value: float, controller_address: Optional[int] = None) -> None:
        """
        Set the encoder increment value. By default, to be as close to 1mm as possible.
        Check the example (SU command) in the doc below to see how the increment value is
        calculated:
        https://www.newport.com/mam/celum/celum_assets/np/resources/CONEX-CC_-_Controller_Documentation.pdf?0

        Parameters:
            value:              Increment value.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        _logger.info(
            "Setting encoder increment value of instrument [%s] to [%f]", self._name, value)
        # instrument must be in configuration state to set the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(self._build_command(
            "SU", value))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)

    @rpc_method
    def get_driver_voltage(self, controller_address: Optional[int] = None) -> float:
        """
        Get the max. output voltage of the driver to the motor.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        _logger.info(
            "Getting the max. output voltage of the driver to the motor of instrument [%s]", self._name)
        self.controller_address = controller_address
        driver_voltage = self._scpi_protocol.ask(
            self._build_command("DV?"))

        self._check_error()
        return float(driver_voltage[3:])

    @rpc_method
    def set_driver_voltage(self, driver_voltage: float, controller_address: Optional[int] = None) -> None:
        """
        Set the max. output voltage of the driver to the motor.

        Parameters:
            driver_voltage:      New profile generator base velocity.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if 12.0 > driver_voltage or driver_voltage > 48.0:
            raise QMI_InstrumentException(
                f"Provided value {driver_voltage} not in valid range 12 >= driver_voltage >= 48.")

        self.controller_address = controller_address
        _logger.info(
            "Setting the max. output voltage of the driver to the motor of instrument [%s] to [%f]",
            self._name, driver_voltage
        )
        self._scpi_protocol.write(self._build_command(
            "DV", driver_voltage))
        self._check_error()

    @rpc_method
    def get_low_pass_filter_cutoff_frequency(self, controller_address: Optional[int] = None) -> float:
        """
        Get the low pass filter cut-off frequency Kd.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The low pass filter cut-off frequency, Kd, in Hertz.
        """
        _logger.info(
            "Getting encoder increment value of instrument [%s]", self._name)
        # instrument must be in configuration state to get the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("FD?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(res[3:])

    @rpc_method
    def set_low_pass_filter_cutoff_frequency(
            self, frequency: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the low pass filter cut-off frequency Kd.

        Parameters:
            frequency:          Cutoff frequency Kd in Hertz.
            persist:            Flag to indicate if the frequency cutoff should be persisted to the controller's memory,
                                so it is still available after powering down the controller. When not persisted, the
                                frequency cutoff is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised frequency of the controller address.
        """
        if 2000 <= frequency or frequency <= self.MIN_FLOAT_LIMIT:
            raise QMI_InstrumentException(
                f"Provided value {frequency} not in valid range {self.MIN_FLOAT_LIMIT} > frequency > 2000.")

        _logger.info(
            "Setting encoder increment frequency of instrument [%s] to [%s]", self._name, frequency)
        self.controller_address = controller_address
        # instrument must be in configuration state to persist the set velocity.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)

        self._scpi_protocol.write(self._build_command(
            "FD", frequency))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_following_error_limit(self, controller_address: Optional[int] = None) -> float:
        """
        Get the maximum allowed following error.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The value for the maximum allowed following error.
        """
        _logger.info(
            "Getting encoder increment value of instrument [%s]", self._name)
        # instrument must be in configuration state to get the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("FE?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(res[3:])

    @rpc_method
    def set_following_error_limit(
            self, error_limit: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the value for the maximum allowed following error.

        Parameters:
            error_limit:        The value for the maximum allowed following error.
            persist:            Flag to indicate if the error limit should be persisted to the controller's memory, so
                                it is still available after powering down the controller. When not persisted, the error
                                limit is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised error limit of the controller address.
        """
        if self.MAX_FLOAT_LIMIT <= error_limit or error_limit <= self.MIN_FLOAT_LIMIT:
            raise QMI_InstrumentException(
                f"Provided value {error_limit} not in valid range {self.MIN_FLOAT_LIMIT} > error limit "
                f"> {self.MAX_FLOAT_LIMIT}."
            )

        _logger.info(
            "Setting the value for the maximum allowed following error of instrument [%s] to [%f]",
            self._name, error_limit
        )
        self.controller_address = controller_address
        # instrument must be in configuration state to persist the set velocity.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)

        self._scpi_protocol.write(self._build_command(
            "FE", error_limit))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_friction_compensation(self, controller_address: Optional[int] = None) -> float:
        """
        Get the friction compensation.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        # instrument must be in configuration state to get the friction compensation.
        _logger.info(
            "Getting the friction compensation of instrument [%s]", self._name)
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        friction_compensation = self._scpi_protocol.ask(
            self._build_command("FF?"))
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(friction_compensation[3:])

    @rpc_method
    def set_friction_compensation(
            self, friction_compensation: float, persist: bool = False, controller_address: Optional[int] = None
    ) -> None:
        """
        Set the friction compensation. It must not be larger than the driver voltage set by DV command.

        Parameters:
            friction_compensation:      New friction compensation value.
            persist:            Flag to indicate if the friction compensation should be persisted to the controller's
                                memory, so it is still available after powering down the controller. When not persisted,
                                the friction compensation is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        response = self._scpi_protocol.ask(
            self._build_command("DV?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        driver_voltage = float(response[3:])
        if driver_voltage <= friction_compensation or friction_compensation < 0:
            raise QMI_InstrumentException(
                f"Provided value {friction_compensation} not in valid range 0 >= "
                f"friction_compensation > {driver_voltage}."
            )

        _logger.info(
            "Setting the friction compensation of instrument [%s] to [%f]", self._name, friction_compensation)
        # instrument must be in configuration state to get the friction compensation.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)

        self._scpi_protocol.write(self._build_command(
            "FF", friction_compensation))
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_derivative_gain(self, controller_address: Optional[int] = None) -> float:
        """
        Get the derivative gain of the PID control loop.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The derivative gain of the PID control loop.
        """
        _logger.info(
            "Getting derivative gain of the PID control loop of instrument [%s]", self._name)
        # instrument must be in configuration state to get the derivative gain of the PID control loop value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("KD?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(res[3:])

    @rpc_method
    def set_derivative_gain(
            self, derivative_gain: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the derivative gain of the PID control loop.

        Parameters:
            derivative_gain:    New derivative_gain value in Volt * second/preset unit.
            persist:            Flag to indicate if the derivative gain should be persisted to the controller's memory,
                                so it is still available after powering down the controller. When not persisted, the
                                derivative gain is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised derivative_gain of the controller address.
        """
        if self.MAX_FLOAT_LIMIT <= derivative_gain or derivative_gain < 0:
            raise QMI_InstrumentException(
                f"Provided value {derivative_gain} not in valid range 0 >= derivative_gain > {self.MAX_FLOAT_LIMIT}.")

        _logger.info(
            "Setting derivative gain of the PID control loop of instrument [%s] to [%f]",
            self._name, derivative_gain
        )
        self.controller_address = controller_address
        # instrument must be in configuration state to persist the set derivative gain of the PID control loop.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)

        self._scpi_protocol.write(self._build_command(
            "KD", derivative_gain))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_integral_gain(self, controller_address: Optional[int] = None) -> float:
        """
        Get the integral gain of the PID control loop.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The integral gain of the PID control loop.
        """
        _logger.info(
            "Getting integral gain of the PID control loop of instrument [%s]", self._name)
        # instrument must be in configuration state to get the integral gain of the PID control loop value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("KI?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(res[3:])

    @rpc_method
    def set_integral_gain(
            self, integral_gain: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the integral gain of the PID control loop.

        Parameters:
            integral_gain:    New integral_gain value in Volt * second/preset unit.
            persist:            Flag to indicate if the integral gain should be persisted to the controller's memory,
                                so it is still available after powering down the controller. When not persisted, the
                                integral gain is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised integral_gain of the controller address.
        """
        if self.MAX_FLOAT_LIMIT <= integral_gain or integral_gain < 0:
            raise QMI_InstrumentException(
                f"Provided value {integral_gain} not in valid range 0 >= integral_gain > {self.MAX_FLOAT_LIMIT}.")

        _logger.info(
            "Setting integral gain of the PID control loop of instrument [%s] to [%f]",
            self._name, integral_gain
        )
        self.controller_address = controller_address
        # instrument must be in configuration state to persist the set integral gain of the PID control loop.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)

        self._scpi_protocol.write(self._build_command(
            "KI", integral_gain))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_proportional_gain(self, controller_address: Optional[int] = None) -> float:
        """
        Get the proportional gain of the PID control loop.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The proportional gain of the PID control loop.
        """
        _logger.info(
            "Getting proportional gain of the PID control loop of instrument [%s]", self._name)
        # instrument must be in configuration state to get the proportional gain of the PID control loop value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("KP?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(res[3:])

    @rpc_method
    def set_proportional_gain(
            self, proportional_gain: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the proportional gain of the PID control loop.

        Parameters:
            proportional_gain:  New proportional_gain value in Volt * second/preset unit.
            persist:            Flag to indicate if the proportional gain should be persisted to the controller's
                                memory, so it is still available after powering down the controller. When not persisted,
                                the proportional gain is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised proportional_gain of the controller address.
        """
        if self.MAX_FLOAT_LIMIT <= proportional_gain or proportional_gain < 0:
            raise QMI_InstrumentException(
                f"Provided value {proportional_gain} not in valid range 0 >= proportional_gain "
                f"> {self.MAX_FLOAT_LIMIT}."
            )

        _logger.info(
            "Setting proportional gain of the PID control loop of instrument [%s] to [%f]",
            self._name, proportional_gain
        )
        # instrument must be in configuration state to persist the set proportional gain of the PID control loop.
        self.controller_address = controller_address
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(self._build_command(
            "KP", proportional_gain))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_velocity_feed_forward(self, controller_address: Optional[int] = None) -> float:
        """
        Get the velocity feed forward of the PID control loop.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The velocity feed forward of the PID control loop.
        """
        _logger.info(
            "Getting velocity feed forward of the PID control loop of instrument [%s]", self._name)
        # instrument must be in configuration state to get the velocity feed forward of the PID control loop value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("KV?"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        self.exit_configuration_state(controller_address)
        return float(res[3:])

    @rpc_method
    def set_velocity_feed_forward(
            self, velocity_feed_forward: float, persist: bool = False, controller_address: Optional[int] = None
    ) -> None:
        """
        Set the velocity feed forward of the PID control loop.

        Parameters:
            velocity_feed_forward: New velocity_feed_forward value in Volt * second/preset unit.
            persist:            Flag to indicate if the velocity feed forward should be persisted to the controller's
                                memory, so it is still available after powering down the controller. When not persisted,
                                the velocity feed forward is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised velocity_feed_forward of the controller address.
        """
        if self.MAX_FLOAT_LIMIT <= velocity_feed_forward or velocity_feed_forward < 0:
            raise QMI_InstrumentException(
                f"Provided value {velocity_feed_forward} not in valid range 0 >= velocity_feed_forward "
                f"> {self.MAX_FLOAT_LIMIT}."
            )

        _logger.info(
            "Setting velocity feed forward of the PID control loop of instrument [%s] to [%f]",
            self._name, velocity_feed_forward
        )
        self.controller_address = controller_address
        # instrument must be in configuration state to persist the set velocity feed forward of the PID control loop.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(self._build_command(
            "KV", velocity_feed_forward))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_control_loop_state(self, controller_address: Optional[int] = None) -> ControlLoopState:
        """
        Get the current state of the control loop.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            control_loop_state: The current control loop state.
        """
        _logger.info(
            "Getting the current state of the control loop of instrument [%s]", self._name)
        self.controller_address = controller_address
        control_loop_state = self._scpi_protocol.ask(
            self._build_command("SC?"))
        self._check_error()
        return ControlLoopState(int(control_loop_state[3:]))

    @rpc_method
    def set_control_loop_state(self, control_loop_state: int, controller_address: Optional[int] = None) -> None:
        """
        Set the current state of the control loop.

        Parameters:
            control_loop_state: New state for the control loop. 0 is OPEN, 1 is CLOSED.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if control_loop_state not in iter(ControlLoopState):
            raise QMI_InstrumentException(
                f"Provided value {control_loop_state} not in valid range {[s.value for s in set(ControlLoopState)]}.")

        _logger.info(
            "Setting the state of the control loop of instrument [%s] to [%s]",
            self._name, ControlLoopState(control_loop_state).name
        )
        self.controller_address = controller_address
        self._scpi_protocol.write(self._build_command(
            "SC", control_loop_state))
        self._check_error()
