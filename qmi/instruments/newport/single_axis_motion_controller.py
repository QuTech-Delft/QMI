"""
Instrument driver for a Newport single axis motion controller. This is a base class for other controllers,
but can be used without extending.
"""
import logging
from time import sleep
from typing import Dict, List, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.instruments.newport.actuators import LinearActuator


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Newport_Single_Axis_Motion_Controller(QMI_Instrument):
    """
    Instrument driver for a Newport single-axis motion controller. This device
    is the controller for an actuator and is controlled via serial.
    """

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # Default home search time out
    DEFAULT_HOME_SEARCH_TIMEOUT = 5.0

    # Time to execute a command
    COMMAND_EXEC_TIME = 0.5

    # Code for no error
    ERROR_CODE_NONE = "@"

    # Default contoller address to send commands to.
    DEFAULT_CONTROLLER_ADDRESS = 1

    STATE_TABLE = {
        "0A": "NOT REFERENCED from RESET",
        "0B": "NOT REFERENCED from HOMING.",
        "0C": "NOT REFERENCED from CONFIGURATION.",
        "0D": "NOT REFERENCED from DISABLE.",
        "0E": "NOT REFERENCED from READY.",
        "0F": "NOT REFERENCED from MOVING.",
        "10": "NOT REFERENCED - NO PARAMETERS IN MEMORY.",
        "14": "CONFIGURATION.",
        "1E": "HOMING.",
        "28": "MOVING.",
        "32": "READY from HOMING.",
        "33": "READY from MOVING.",
        "34": "READY from DISABLE.",
        "36": "READY T from READY.",
        "37": "READY T from TRACKING.",
        "38": "READY T from DISABLE T.",
        "3C": "DISABLE from READY.",
        "3D": "DISABLE from MOVING.",
        "3E": "DISABLE from TRACKING.",
        "3F": "DISABLE from READY T.",
        "46": "TRACKING from READY T.",
        "47": "TRACKING from TRACKING.",
    }

    POSITIONER_ERROR_TABLE = {
        6: "80W output power exceeded",
        7: "DC voltage too low",
        8: "Wrong ESP stage",
        9: "Homing time out",
        10: "Following error",
        11: "Short circuit detection",
        12: "RMS current limit",
        13: "Peak current limit",
        14: "Positive end of run",
        15: "Negative end of run",
    }

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str,
                 serial: str,
                 actuators: Dict[int, LinearActuator],
                 baudrate: int) -> None:
        """Initialize driver.

        Parameters:
            name:                   Name for this instrument instance.
            transport:              QMI transport descriptor to connect to the instrument.
            serial:                 The serial number of the instrument.
            actuators:              The linear actuators that this controller will drive. Each controller address
                                    drives a linear actuator. The key of the dictionary is the controller address
                                    and the value is the actuator that it drives.
            baudrate:               The baudrate of the instrument.
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport_str = transport
        self._transport = create_transport(
            transport, default_attributes={"baudrate": baudrate})
        self._scpi_protocol = ScpiProtocol(self._transport,
                                           command_terminator="\r\n",
                                           response_terminator="\r\n",
                                           default_timeout=self._timeout)
        self._serial = serial
        self._actuators = actuators

    def _build_command(self, cmd: str, value: Optional[float] = None, controller_address: Optional[int] = None) -> str:
        """Build the command.

        Parameters:
            cmd:                Name of command.
            value:              Value to go with command if needed.
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        if controller_address not in self._actuators.keys():
            raise QMI_InstrumentException(
                f"Invalid controller address {controller_address}")
        return f"{controller_address}{cmd}{value}\r\n" if value is not None else f"{controller_address}{cmd}\r\n"

    def _check_error(self, controller_address: Optional[int] = None) -> None:
        """
        Check the currently memorised error.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.

        Raises:
            QMI_InstrumentException if an error exists.
        """
        error_code = self._scpi_protocol.ask(
            self._build_command("TE", controller_address=controller_address))[-1]
        sleep(self.COMMAND_EXEC_TIME)
        if error_code != self.ERROR_CODE_NONE:
            error_str = self._scpi_protocol.ask(self._build_command(
                "TB" + error_code, controller_address=controller_address)).strip().split(' ', 1)[1]
            raise QMI_InstrumentException(f"Error {error_code}: {error_str}")

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to instrument [%s]", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to instrument [%s]", self._name)
        self._check_is_open()
        self._transport.close()
        super().close()

    @rpc_method
    def reset(self, controller_address: Optional[int] = None) -> None:
        """
        Reset the instrument. Equivalent to a power-up.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        _logger.info("Resetting instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("RS", controller_address=controller_address))
        self._check_error(controller_address)

    @rpc_method
    def get_idn(self, controller_address: Optional[int] = None) -> QMI_InstrumentIdentification:
        """
        Read instrument type and version and return QMI_InstrumentIdentification instance.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.

        Returns:
            QMI_InstrumentIdentification with the information of the instrument.
        """
        _logger.info("Getting identification of instrument [%s]", self._name)
        instr_info = self._scpi_protocol.ask(
            self._build_command("VE", controller_address=controller_address))
        self._check_error(controller_address)
        words = instr_info[1:].strip().split()
        return QMI_InstrumentIdentification(vendor="Newport",
                                            model=words[1],
                                            version=words[2],
                                            serial=self._serial)

    @rpc_method
    def get_positioner_error_and_state(self, controller_address: Optional[int] = None) -> Tuple[List[str], str]:
        """
        Get the positioner error and the current state of the controller.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        _logger.info(
            "Getting positioner error and state of instrument [%s]", self._name)
        err_and_state = self._scpi_protocol.ask(
            self._build_command("TS", controller_address=controller_address))
        err = err_and_state[3:7]
        state = err_and_state[7:9]
        errors = []
        # convert the hexademical error code to binary
        bin_err_str = "{0:016b}".format(int(err, 16))
        # loop over bits and log the errors (i.e. high bits)
        for i, bit in enumerate(bin_err_str):
            if bit == "1":
                errors.append(self.POSITIONER_ERROR_TABLE[i])

        return (errors, self.STATE_TABLE[state])

    @rpc_method
    def home_search(self, controller_address: Optional[int] = None) -> None:
        """
        Execute the home search. This is needed before any motion commands
        can be executed. It finds the origin position of the actuator.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        _logger.info("Homing instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("OR", controller_address=controller_address))
        self._check_error(controller_address)

    @rpc_method
    def set_home_search_timeout(self, timeout: Optional[float] = None, controller_address: Optional[int] = None) -> None:
        """
        Set the timeout for the home search.

        Parameters:
            timeout:            Optional timeout in seconds. If not set, it defaults DEFAULT_HOME_SEARCH_TIMEOUT
            controller_address: Optional address of the controller that needs to be controlled. By default
                                it is set to the initialised value of the controller address.
        """
        t = timeout if timeout else self.DEFAULT_HOME_SEARCH_TIMEOUT
        _logger.info(
            "Setting homing timeout of instrument [%s] to [%s]", self._name, t)
        # instrument must be in configuration state to set the timeout.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        self._scpi_protocol.write(
            self._build_command("OT", t, controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        self.exit_configuration_state(controller_address)

    @rpc_method
    def get_home_search_timeout(self, controller_address: Optional[int] = None) -> float:
        """
        Get the timeout for the home search.

        Returns:
            The timeout in seconds.
        """
        _logger.info("Getting homing timeout of instrument [%s]", self._name)
        timeout = self._scpi_protocol.ask(
            self._build_command("OT?", controller_address=controller_address))
        self._check_error(controller_address)
        return float(timeout[3:])

    @rpc_method
    def move_absolute(self, position: float, controller_address: Optional[int] = None) -> None:
        """
        Perform an absolute move. This command can take several seconds to finish. However it is not blocking.
        Use other methods such as `get_positioner_error_and_state` to query the state of the controller.

        Parameters:
            position:   New position to move to, in encoder units.
        """
        _logger.info(
            "Performing an absolute move of instrument [%s] to [%s]", self._name, position)
        # if controller address is not given use the default one
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        if position > self._actuators[controller_address].TRAVEL_RANGE:
            raise QMI_InstrumentException(
                f"Provided value {position} greater than allowed maximum {self._actuators[controller_address].TRAVEL_RANGE}")
        if position < self._actuators[controller_address].MIN_INCREMENTAL_MOTION:
            raise QMI_InstrumentException(
                f"Provided value {position} lower than minimum {self._actuators[controller_address].MIN_INCREMENTAL_MOTION}")
        self._scpi_protocol.write(self._build_command(
            "PA", position, controller_address))
        self._check_error(controller_address)

    @rpc_method
    def get_position(self, controller_address: Optional[int] = None) -> float:
        """
        Get the actual position of the actuator according to the encoder value.

        Returns:
            Current position in encoder units.
        """
        _logger.info("Getting position of instrument [%s]", self._name)
        pos = self._scpi_protocol.ask(
            self._build_command("TP", controller_address=controller_address))
        self._check_error(controller_address)
        return float(pos[3:])

    @rpc_method
    def move_relative(self, displacement: float, controller_address: Optional[int] = None) -> None:
        """
        Perform a relative move from the current position.

        Parameters:
            displacement:   Displacement from current position.
        """
        _logger.info("Performing relative move of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("PR", displacement, controller_address))
        self._check_error(controller_address)

    @rpc_method
    def enter_configuration_state(self, controller_address: Optional[int] = None) -> None:
        """
        Enter the CONFIGURATION state of the controller from the NOT REFERENCED state. If the controller
        is not in the NOT REFERENCE state, then call the `reset` method.
        NOTE:   In this state the parameters are stored in the flash memory of the controller.
                The device supports up to 100 writes, so this command should not be used often.
        """
        _logger.info(
            "Entering configuration state of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("PW", 1, controller_address))
        self._check_error(controller_address)

    @rpc_method
    def exit_configuration_state(self, controller_address: Optional[int] = None) -> None:
        """
        Exit the CONFIGURATION state of the controller to the NOT REFERENCED state.
        NOTE:   Due to a quirk, checking the error after exiting this state throws
                a timeout error, so error checking is removed.
        """
        _logger.info(
            "Exiting configuration state of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("PW", 0, controller_address))

    @rpc_method
    def get_encoder_increment_value(self, controller_address: Optional[int] = None) -> float:
        """
        Get the encoder increment value.

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
            value:    Increment value.
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
    def set_velocity(self, velocity: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the velocity at which the actuator moves.

        Parameters:
            velocity:   Velocity in unit/s. The unit depends on the encoder resolution,
                        which is usually set to 1mm
            persist:    Flag to indicate if the velocity should be persisted to the controller's memory, so it
                        is still available after powering down the controller. When not persisted, the maximum allowable
                        velocity that can be set is the one stored in the controller's memory.
        """
        _logger.info(
            "Setting velocity of instrument [%s] to [%s]", self._name, velocity)
        # if controller address is not given use the default one
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        # instrument must be in configuration state to persist the set velocity.
        if persist:
            self.reset(controller_address)
            self.enter_configuration_state(controller_address)
        if velocity > self._actuators[controller_address].MAX_VELOCITY:
            raise QMI_InstrumentException(
                f"Provided value {velocity} greater than allowed maximum {self._actuators[controller_address].MAX_VELOCITY}")
        if velocity < self._actuators[controller_address].MIN_VELOCITY:
            raise QMI_InstrumentException(
                f"Provided value {velocity} lower than minimum {self._actuators[controller_address].MIN_VELOCITY}")
        self._scpi_protocol.write(self._build_command(
            "VA", velocity, controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        if persist:
            self.exit_configuration_state(controller_address)

    @rpc_method
    def get_velocity(self, controller_address: Optional[int] = None) -> float:
        """
        Get the velocity of the actuator in unit/s, so if the the encoder unit is mm,
        then the returned value is in mm/s.
        """
        _logger.info("Getting velocity of instrument [%s]", self._name)
        # if controller address is not given use the default one
        controller_address = controller_address if controller_address else self.DEFAULT_CONTROLLER_ADDRESS
        # instrument must be in configuration state to get the velocity.
        self.reset(controller_address)
        self.enter_configuration_state(controller_address)
        vel = self._scpi_protocol.ask(
            self._build_command("VA?", controller_address=controller_address))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error(controller_address)
        self.exit_configuration_state(controller_address)
        return float(vel[3:])

    @rpc_method
    def get_error(self, controller_address: Optional[int] = None) -> Tuple[str, str]:
        """
        Get the currently memorised error.

        Returns:
            A tuple containing the error code and the human readable error message.
        """
        _logger.info("Getting error of instrument [%s]", self._name)
        error_code = self._scpi_protocol.ask(
            self._build_command("TE", controller_address=controller_address))[-1]
        if error_code == self.ERROR_CODE_NONE:
            return ("@", "No error")
        error_str = self._scpi_protocol.ask(self._build_command(
            "TB" + error_code, controller_address=controller_address)).strip().split(' ', 1)[1]
        return (error_code, error_str)

    @rpc_method
    def stop_motion(self, controller_address: Optional[int] = None) -> None:
        """
        Stop the motion of the actuator by decelerating it.
        """
        _logger.info("Stop motion of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("ST", controller_address=controller_address))
        self._check_error(controller_address)
