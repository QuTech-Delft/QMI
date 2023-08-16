"""
Instrument driver for the Newport SMC100CC motion controller.
"""
import logging
from time import sleep
from typing import Dict, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.rpc import rpc_method
from qmi.instruments.newport.actuators import LinearActuator
from qmi.instruments.newport.single_axis_motion_controller import Newport_Single_Axis_Motion_Controller

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


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
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.

        Returns:
            Encoder increment value.
        """
        _logger.info(
            "Getting encoder increment value of instrument [%s]", self._name)
        # if controller address is not given use the default one
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        # instrument must be in configuration state to get the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("SU?", controller_address=controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        self.exit_configuration_state(controller_address)
        return self._actuators[controller_address].ENCODER_RESOLUTION / float(res[3:])

    @rpc_method
    def set_encoder_increment_value(self, value: float, controller_address: Optional[int] = None) -> None:
        """
        Set the encoder increment value. By default to be as close to 1mm as possible.
        Check the example (SU command) in the doc below to see how the increment value is
        calculated:
        https://www.newport.com/mam/celum/celum_assets/np/resources/CONEX-CC_-_Controller_Documentation.pdf?0

        Parameters:
            value:              Increment value.
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        _logger.info(
            "Setting encoder increment value of instrument [%s] to [%s]", self._name, value)
        # instrument must be in configuration state to set the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(self._build_command(
            "SU", value, controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        self.exit_configuration_state(controller_address)

    @rpc_method
    def get_driver_voltage(self, controller_address: Optional[int] = None) -> float:
        """
        Get the max. output voltage of the driver to the motor.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        _logger.info(
            "Getting the max. output voltage of the driver to the motor of instrument [%s]", self._name)
        driver_voltage = self._scpi_protocol.ask(
            self._build_command("DV?", controller_address=controller_address))

        self._check_error(controller_address)
        return float(driver_voltage[3:])

    @rpc_method
    def set_driver_voltage(self, driver_voltage: float, controller_address: Optional[int] = None) -> None:
        """
        Set the max. output voltage of the driver to the motor.

        Parameters:
            driver_voltage:      New profile generator base velocity.
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        if 48 < driver_voltage < 12:
            raise QMI_InstrumentException(
                f"Provided value {driver_voltage} not in valid range 12 >= driver_voltage >= 48.")

        _logger.info(
            "Setting the max. output voltage of the driver to the motor of instrument [%s] to [%f]",
            self._name, driver_voltage
        )
        self._scpi_protocol.write(self._build_command(
            "DV", driver_voltage, controller_address))
        self._check_error(controller_address)

    @rpc_method
    def get_low_pass_filter_cutoff_frequency(self, controller_address: Optional[int] = None) -> float:
        """
        Get the low pass filter cut-off frequency Kd.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.

        Returns:
            The low pass filter cut-off frequency, Kd.
        """
        _logger.info(
            "Getting encoder increment value of instrument [%s]", self._name)
        # if controller address is not given use the default one
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        # instrument must be in configuration state to get the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("FD?", controller_address=controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        self.exit_configuration_state(controller_address)
        return self._actuators[controller_address].ENCODER_RESOLUTION / float(res[3:])

    @rpc_method
    def set_low_pass_filter_cutoff_frequency(
            self, frequency: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the low pass filter cut-off frequency Kd.

        Parameters:
            frequency:          Cutoff frequency Kd.
            persist:            Flag to indicate if the frequency cutoff should be persisted to the controller's memory, so it
                                is still available after powering down the controller. When not persisted, the frequency
                                cutoff is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised frequency of the controller address.
        """
        if 2000 <= frequency <= 1E-6:
            raise QMI_InstrumentException(
                f"Provided value {frequency} not in valid range 1E-6 > frequency > 2000.")

        _logger.info(
            "Setting encoder increment frequency of instrument [%s] to [%s]", self._name, frequency)
        # instrument must be in configuration state to persist the set velocity.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(self._build_command(
            "FD", frequency, controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_following_error_limit(self, controller_address: Optional[int] = None) -> float:
        """
        Get the maximum allowed following error.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.

        Returns:
            The value for the maximum allowed following error.
        """
        _logger.info(
            "Getting encoder increment value of instrument [%s]", self._name)
        # if controller address is not given use the default one
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        # instrument must be in configuration state to get the encoder increment value.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        res = self._scpi_protocol.ask(
            self._build_command("FE?", controller_address=controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        self.exit_configuration_state(controller_address)
        return self._actuators[controller_address].ENCODER_RESOLUTION / float(res[3:])

    @rpc_method
    def set_following_error_limit(
            self, error_limit: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the value for the maximum allowed following error.

        Parameters:
            error_limit:        The value for the maximum allowed following error.
            persist:            Flag to indicate if the error limit should be persisted to the controller's memory, so it
                                is still available after powering down the controller. When not persisted, the error
                                limit is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised error limit of the controller address.
        """
        if 1E12 <= error_limit <= 1E-6:
            raise QMI_InstrumentException(
                f"Provided value {error_limit} not in valid range 1E-6 > error limit > 1E12.")

        _logger.info(
            "Setting the value for the maximum allowed following error of instrument [%s] to [%s]", self._name, error_limit)
        # instrument must be in configuration state to persist the set velocity.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(self._build_command(
            "FE", error_limit, controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        if persist:
            self.exit_configuration_state(controller_address)
