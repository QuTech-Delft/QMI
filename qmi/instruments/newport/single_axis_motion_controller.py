"""
Instrument driver for a Newport single axis motion controller. This is a base class for other controllers,
but can be used without extending.
"""
from contextlib import contextmanager
import enum
import logging
from time import sleep
from typing import Dict, List, Optional, Tuple, Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.instruments.newport.actuators import LinearActuator


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class HomeSearchTypes(enum.IntEnum):
    """The types of HOME search used with the OR command."""
    MZ_SWITCH_AND_ENCODER_INDEX = 0
    CURRENT_POSITION_AS_HOME = 1
    MZ_SWITCH_ONLY = 2
    EOR_SWITCH_AND_ENCODER_INDEX = 3
    EOR_SWITCH_ONLY = 4


class Newport_SingleAxisMotionController(QMI_Instrument):
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
    PW0_EXEC_TIME = 10

    # Code for no error
    ERROR_CODE_NONE = "@"

    # Default contoller address to send commands to.
    DEFAULT_CONTROLLER_ADDRESS = 1

    # Floating point value FW limits
    MIN_FLOAT_LIMIT = 1E-6
    MAX_FLOAT_LIMIT = 1E12

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
                 actuators: Dict[Optional[int], LinearActuator],
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
        self._controller_address: int = self.DEFAULT_CONTROLLER_ADDRESS

    @property
    def controller_address(self) -> Optional[int]:
        """Address of the controller that needs to be controlled."""
        return self._controller_address

    @controller_address.setter
    def controller_address(self, controller_address: Optional[int]) -> None:
        # if controller address is not given use the default one.
        self._controller_address = controller_address or self.DEFAULT_CONTROLLER_ADDRESS
        # Check that the address is valid.
        if self._controller_address not in self._actuators.keys():
            raise QMI_InstrumentException(
                f"Invalid controller address {self._controller_address}")

    @contextmanager
    def configuration_state(self):
        try:
            yield self._enter_configuration_state()
        finally:
            self._exit_configuration_state()

    def _build_command(
            self, cmd: str, value: Union[float, int, None] = None
    ) -> str:
        """Build the command.

        Parameters:
            cmd:                Name of command.
            value:              Value to go with command if needed.
        """
        controller_address = self.controller_address
        return f"{controller_address}{cmd}{value}\r\n" if value is not None else f"{controller_address}{cmd}\r\n"

    def _check_error(self) -> None:
        """
        Check the currently memorised error.

        Raises:
            QMI_InstrumentException if an error exists.
        """
        error_code = self._scpi_protocol.ask(
            self._build_command("TE"))[-1]
        sleep(self.COMMAND_EXEC_TIME)
        if error_code != self.ERROR_CODE_NONE:
            error_str = self._scpi_protocol.ask(self._build_command(
                "TB" + error_code)).strip().split(' ', 1)[1]
            raise QMI_InstrumentException(f"Error {error_code}: {error_str}")

    def _get_current_state(self) -> str:
        """
        Get current controller state.

        Returns:
            state: The current controller 16-bit state value string.
        """
        err_and_state = self._scpi_protocol.ask(
            self._build_command("TS")
        )
        return err_and_state[7:9]

    def _state_ready_check(self, parameter: str) -> int:
        """Check if the state is READY (32-38) or DISABLE (3C-3F). Otherwise, raise an exception.

        Parameters:
            parameter: String to describe for which parameter the check is made.

        Raises:
            QMI_InstrumentException: If the state is not READY or DISABLE, with informing the parameter name.

        Returns:
            istate: The state number as an integer.
        """
        state = self._get_current_state()
        istate = int(state, 16)
        if istate < int("32", 16) or istate > int("3F", 16):
            raise QMI_InstrumentException(
                f"Cannot set {parameter} in controller state {self.STATE_TABLE[state]}")

        return istate

    def _enter_configuration_state(self) -> None:
        """
        Enter the CONFIGURATION state of the controller from the NOT REFERENCED state. If the controller
        is not in the NOT REFERENCED state, then call the `reset` method.
        NOTE:   In this state the parameters are stored in the flash memory of the controller.
                The device supports up to 100 writes, so this command should not be used often.
        """
        state = self._get_current_state()
        istate = int(state, 16)
        if istate == int("14", 16):
            # Already in CONFIGURATION state
            return

        _logger.info("Entering configuration state of instrument [%s]", self._name)
        # If the state is not NOT REFERENCED (0A-10) or CONFIGURATION (14), then reset.
        if istate > int("14", 16):
            # Call reset to get to NOT REFERENCED state.
            self._scpi_protocol.write(
                self._build_command("RS")
            )
            sleep(self.COMMAND_EXEC_TIME)

        self._scpi_protocol.write(
            self._build_command("PW", 1)
        )
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()

    def _exit_configuration_state(self) -> None:
        """
        Exit the CONFIGURATION state of the controller to the NOT REFERENCED state.
        NOTE:   The execution of a PW0 command may take up to 10 seconds. During that time the
                controller will not respond to any other command.
        """
        _logger.info("Exiting configuration state of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("PW", 0)
        )
        sleep(self.PW0_EXEC_TIME)

    def _enter_disable_state(self) -> None:
        """
        Enter the DISABLE state of the controller from the READY state. If the controller
        is not in the NOT REFERENCE state, then call the `reset` method.
        NOTE:   In this state the parameters are stored in the flash memory of the controller.
                The device supports up to 100 writes, so this command should not be used often.
        """
        _logger.info("Entering disable state of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("MM", 1)
        )
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()

    def _exit_disable_state(self) -> None:
        """
        Exit the DISABLE state of the controller to the READY state.
        """
        _logger.info("Exiting disable state of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("MM", 0)
        )

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
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        _logger.info("Resetting instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("RS"))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()

    @rpc_method
    def get_idn(self, controller_address: Optional[int] = None) -> QMI_InstrumentIdentification:
        """
        Read instrument type and version and return QMI_InstrumentIdentification instance.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            QMI_InstrumentIdentification with the information of the instrument.
        """
        _logger.info("Getting identification of instrument [%s]", self._name)
        self.controller_address = controller_address
        instr_info = self._scpi_protocol.ask(
            self._build_command("VE"))
        self._check_error()
        words = instr_info[1:].strip().split()
        return QMI_InstrumentIdentification(vendor="Newport",
                                            model=words[1],
                                            version=words[2],
                                            serial=self._serial)

    @rpc_method
    def get_stage_identifier(self, controller_address: Optional[int] = None) -> str:
        """
        Read stage identifier.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The stage identifier.
        """
        _logger.info("Getting stage identifier of instrument [%s]", self._name)
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to get the stage identifier.
        with self.configuration_state():
            identifier = self._scpi_protocol.ask(
                self._build_command("ID?"))
            self._check_error()

        return identifier

    @rpc_method
    def get_positioner_error_and_state(self, controller_address: Optional[int] = None) -> Tuple[List[str], str]:
        """
        Get the positioner error and the current state of the controller.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        _logger.info(
            "Getting positioner error and state of instrument [%s]", self._name)
        self.controller_address = controller_address
        err_and_state = self._scpi_protocol.ask(
            self._build_command("TS"))
        err = err_and_state[3:7]
        state = err_and_state[7:9]
        errors = []
        # convert the hexadecimal error code to binary
        bin_err_str = "{0:016b}".format(int(err, 16))
        # loop over bits and log the errors (i.e. high bits)
        for i, bit in enumerate(bin_err_str):
            if bit == "1":
                errors.append(self.POSITIONER_ERROR_TABLE[i])

        return errors, self.STATE_TABLE[state]

    @rpc_method
    def home_search(self, controller_address: Optional[int] = None) -> None:
        """
        Execute the home search. This is needed before any motion commands can be executed. It finds an origin position
        for the actuator. Can be done only in NOT REFERENCED state.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        _logger.info("Homing instrument [%s]", self._name)
        self.controller_address = controller_address
        self._scpi_protocol.write(
            self._build_command("OR"))
        self._check_error()

    @rpc_method
    def set_home_search_timeout(
            self, timeout: Optional[float] = None, controller_address: Optional[int] = None) -> None:
        """
        Set the timeout for the home search.

        Parameters:
            timeout:            Optional timeout in seconds. If not set, it defaults DEFAULT_HOME_SEARCH_TIMEOUT
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        t = timeout if timeout else self.DEFAULT_HOME_SEARCH_TIMEOUT
        _logger.info(
            "Setting homing timeout of instrument [%s] to [%s]", self._name, t)
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to set the timeout.
        with self.configuration_state():
            self._scpi_protocol.write(
                self._build_command("OT", t))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_home_search_timeout(self, controller_address: Optional[int] = None) -> float:
        """
        Get the timeout for the home search.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            The timeout in seconds.
        """
        _logger.info("Getting homing timeout of instrument [%s]", self._name)
        self.controller_address = controller_address
        timeout = self._scpi_protocol.ask(
            self._build_command("OT?"))
        self._check_error()
        return float(timeout[3:])

    @rpc_method
    def move_absolute(self, position: float, controller_address: Optional[int] = None) -> None:
        """
        Perform an absolute move. This command can take several seconds to finish. However, it is not blocking.
        Use other methods such as `get_positioner_error_and_state` to query the state of the controller.

        Parameters:
            position:           New position to move to, in encoder units. Must be within actuator's travel range.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        if position > self._actuators[self.controller_address].TRAVEL_RANGE.max or \
                position < self._actuators[self.controller_address].TRAVEL_RANGE.min:
            raise QMI_InstrumentException(
                f"Provided value {position} outside valid range ["
                f"{self._actuators[self.controller_address].TRAVEL_RANGE.min}, "
                f"{self._actuators[self.controller_address].TRAVEL_RANGE.max}]"
            )

        # The move can be made only in READY state.
        state = self._state_ready_check("absolute move")
        if state > int("38", 16):
            raise QMI_InstrumentException("The controller must be in READY state to move.")

        _logger.info(
            "Performing an absolute move of instrument [%s] to [%s]", self._name, position)
        self._scpi_protocol.write(
            self._build_command("PA", position))
        self._check_error()

    @rpc_method
    def get_setpoint(self, controller_address: Optional[int] = None) -> float:
        """
        Get the set-point position of the actuator according to the encoder value.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            Set-point position in encoder units.
        """
        _logger.info("Getting set-point of instrument [%s]", self._name)
        self.controller_address = controller_address
        setpoint = self._scpi_protocol.ask(
            self._build_command("TH"))
        self._check_error()
        return float(setpoint[3:])

    @rpc_method
    def get_position(self, controller_address: Optional[int] = None) -> float:
        """
        Get the actual position of the actuator according to the encoder value.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            Current position in encoder units.
        """
        _logger.info("Getting position of instrument [%s]", self._name)
        self.controller_address = controller_address
        pos = self._scpi_protocol.ask(
            self._build_command("TP"))
        self._check_error()
        return float(pos[3:])

    @rpc_method
    def move_relative(self, displacement: float, controller_address: Optional[int] = None) -> None:
        """
        Perform a relative move from the current position.

        Parameters:
            displacement:       Displacement from current position.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        if abs(displacement) < self._actuators[self.controller_address].MIN_INCREMENTAL_MOTION:
            raise QMI_InstrumentException(
                f"Provided value {displacement} lower than minimum "
                f"{self._actuators[self.controller_address].MIN_INCREMENTAL_MOTION}"
            )

        # The move can be made only in READY state.
        state = self._state_ready_check("relative move")
        if state > int("38", 16):
            raise QMI_InstrumentException("The controller must be in READY state to move.")

        _logger.info("Performing relative move of instrument [%s]", self._name)
        self._scpi_protocol.write(
            self._build_command("PR", displacement))
        self._check_error()

    @rpc_method
    def get_motion_time(self, displacement: float, controller_address: Optional[int] = None) -> float:
        """
        Get the motion time for a relative move.

        Parameters:
            displacement:       Displacement from current position (relative move size).
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            Motion time for a relative move in seconds.
        """
        _logger.info("Getting motion time for a relative move of instrument [%s]", self._name)
        self.controller_address = controller_address
        move_time = self._scpi_protocol.ask(
            self._build_command("PT", displacement))
        self._check_error()
        return float(move_time[3:])

    @rpc_method
    def is_in_configuration_state(self, controller_address: Optional[int] = None) -> bool:
        """
        Get the CONFIGURATION state of the controller.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            state: Boolean indicating if the controller is in CONFIGURATION state (True) or not (False).
        """
        _logger.info("Getting CONFIGURATION state of instrument [%s]", self._name)
        self.controller_address = controller_address
        state = self._scpi_protocol.ask(
            self._build_command("PW?"))
        self._check_error()
        return bool(int(state[3:]))

    @rpc_method
    def set_configuration_state(self, state: bool, controller_address: Optional[int] = None) -> None:
        """
        Set the NOT REFERENCED or CONFIGURATION state of the controller.
        If the controller is not in the either state, then an exception is raised in the _check_error.
        NOTE: In this state the parameters are stored in the flash memory of the controller.

        Parameters:
            state:              False for setting the configuration state from CONFIGURATION to NOT REFERENECED or
                                True for setting the configuration state from NOT REFERENECED to CONFIGURATION.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        """
        _logger.info(
            "Setting state of instrument [%s] to [%s]", self._name, "CONFIGURATION" if state else "NOT REFERENCED"
        )
        self.controller_address = controller_address
        self._scpi_protocol.write(
            self._build_command("PW", int(state)))

        if not state:
            # The execution of a PW0 command may take up to 10 seconds. During that time the
            # controller will not respond to any other command.
            sleep(self.PW0_EXEC_TIME)

        else:
            sleep(self.COMMAND_EXEC_TIME)

    @rpc_method
    def is_in_disable_state(self, controller_address: Optional[int] = None) -> bool:
        """
        Get the DISABLE or READY state of the controller.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            state: Boolean to indicate state is DISABLE (True) or READY (False)
        """
        _logger.info("Getting DISABLE state of instrument [%s]", self._name)
        self.controller_address = controller_address
        state = self._scpi_protocol.ask(
            self._build_command("MM?"))
        self._check_error()
        return bool(int(state[3:]))

    @rpc_method
    def set_disable_state(self, state: bool, controller_address: Optional[int] = None) -> None:
        """
        Set the DISABLE or READY state of the controller from the READY or DISABLE state, respectively.
        If the controller is not in the either state, then an exception is raised in the _check_error.
        NOTE: In this state the parameters are stored in the flash memory of the controller.

        Parameters:
            state: True for setting state from READY to DISABLE, False for vice versa.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        _logger.info("Setting state of instrument [%s] to [%s]", self._name, "DISABLE" if state else "READY")
        self.controller_address = controller_address
        self._scpi_protocol.write(
            self._build_command("MM", int(state)))
        sleep(self.COMMAND_EXEC_TIME)
        self._check_error()

    @rpc_method
    def get_acceleration(self, controller_address: Optional[int] = None) -> float:
        """
        Get the acceleration of the actuator in preset unit/s^2, so if the encoder unit is mm,
        then the returned value is in mm/s^2.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            Encoder increment value.
        """
        def _get_acceleration() -> str:
            acceleration = self._scpi_protocol.ask(
                self._build_command("AC?"))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()
            return acceleration

        _logger.info("Getting acceleration of instrument [%s]", self._name)
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION, DISABLE or READY state to get the acceleration.
        try:
            self._state_ready_check("acceleration")
            acceleration = _get_acceleration()

        except QMI_InstrumentException:
            with self.configuration_state():
                acceleration = _get_acceleration()

        return float(acceleration[3:])

    @rpc_method
    def set_acceleration(
            self, acceleration: float, persist: bool = False, controller_address: Optional[int] = None
    ) -> None:
        """
        Set the acceleration at which the actuator moves. Can be set only in CONFIGURATION, READY and DISABLE states.

        Parameters:
            acceleration:       Acceleration in preset unit/s^2. The unit depends on the encoder resolution,
                                which is usually set to 1mm.
            persist:            Flag to indicate if the acceleration should be persisted to the controller's memory, so
                                it is still available after powering down the controller. When not persisted, the
                                maximum allowable acceleration that can be set is the one stored in the controller's
                                memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        def _set_acceleration():
            self._scpi_protocol.write(
                self._build_command("AC", acceleration))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

        if self.MIN_FLOAT_LIMIT >= acceleration or acceleration >= self.MAX_FLOAT_LIMIT:
            raise QMI_InstrumentException(
                f"Provided value {acceleration} not in valid range {self.MIN_FLOAT_LIMIT} "
                f"< acceleration < {self.MAX_FLOAT_LIMIT}."
            )

        _logger.info(
            "Setting acceleration of instrument [%s] to [%f]", self._name, acceleration)
        self.controller_address = controller_address
        if persist:
            # instrument must be in CONFIGURATION state to set persistent acceleration.
            with self.configuration_state():
                _set_acceleration()

        else:
            # instrument must be in DISABLE or READY state to set acceleration.
            self._state_ready_check("acceleration")
            _set_acceleration()

    @rpc_method
    def get_velocity(self, controller_address: Optional[int] = None) -> float:
        """
        Get the velocity of the actuator in unit/s, so if the encoder unit is mm,
        then the returned value is in mm/s.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        def _get_velocity() -> str:
            velocity = self._scpi_protocol.ask(
                self._build_command("VA?"))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()
            return velocity

        _logger.info("Getting velocity of instrument [%s]", self._name)
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION, DISABLE or READY state to get the velocity.
        try:
            self._state_ready_check("velocity")
            velocity = _get_velocity()

        except QMI_InstrumentException:
            with self.configuration_state():
                velocity = _get_velocity()

        return float(velocity[3:])

    @rpc_method
    def set_velocity(self, velocity: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the velocity at which the actuator moves.

        Parameters:
            velocity:           Velocity in unit/s. The unit depends on the encoder resolution,
                                which is usually set to 1mm.
            persist:            Flag to indicate if the velocity should be persisted to the controller's memory, so it
                                is still available after powering down the controller. When not persisted, the maximum
                                allowable velocity that can be set is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        def _set_velocity():
            self._scpi_protocol.write(
                self._build_command("VA", velocity))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

        self.controller_address = controller_address
        if velocity > self._actuators[self.controller_address].MAX_VELOCITY:
            raise QMI_InstrumentException(
                f"Provided value {velocity} greater than allowed maximum "
                f"{self._actuators[self.controller_address].MAX_VELOCITY}"
            )
        if velocity < self._actuators[self.controller_address].MIN_VELOCITY:
            raise QMI_InstrumentException(
                f"Provided value {velocity} lower than minimum "
                f"{self._actuators[self.controller_address].MIN_VELOCITY}"
            )

        _logger.info(
            "Setting velocity of instrument [%s] to [%f]", self._name, velocity)
        if persist:
            # instrument must be in CONFIGURATION state to set persistent velocity.
            with self.configuration_state():
                _set_velocity()

        else:
            # instrument must be in DISABLE or READY state to set velocity.
            self.controller_address = controller_address
            self._state_ready_check("velocity")
            _set_velocity()

    @rpc_method
    def get_jerk_time(self, controller_address: Optional[int] = None) -> float:
        """
        Get the jerk time of the actuator.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            jerk_time: Jerk time in seconds.
        """
        def _get_jerk_time() -> str:
            jerk_time = self._scpi_protocol.ask(
                self._build_command("JR?"))
            self._check_error()
            return jerk_time

        _logger.info("Getting jerk time of instrument [%s]", self._name)
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION, DISABLE or READY state to get the jerk time.
        try:
            self._state_ready_check("jerk time")
            jerk_time = _get_jerk_time()

        except QMI_InstrumentException:
            with self.configuration_state():
                jerk_time = _get_jerk_time()

        return float(jerk_time[3:])

    @rpc_method
    def set_jerk_time(self, jerk_time: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the jerk time at which the actuator accelerates.

        Parameters:
            jerk_time:          Jerk time in seconds.
            persist:            Flag to indicate if the jerk time should be persisted to the controller's memory, so it
                                is still available after powering down the controller. When not persisted, the maximum
                                allowable jerk time that can be set is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        def _set_jerk_time():
            self._scpi_protocol.write(self._build_command(
                "JR", jerk_time))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

        if jerk_time <= 0.001 or jerk_time >= self.MAX_FLOAT_LIMIT:
            raise QMI_InstrumentException(
                f"Provided value {jerk_time} not in valid range 0.001 < jerk_time < {self.MAX_FLOAT_LIMIT}")

        _logger.info(
            "Setting jerk time of instrument [%s] to [%f]", self._name, jerk_time)
        self.controller_address = controller_address
        if persist:
            # instrument must be in CONFIGURATION state to set persistent jerk time.
            with self.configuration_state():
                _set_jerk_time()

        else:
            # instrument must be in DISABLE or READY state to set jerk time.
            self._state_ready_check("cut-off frequency")
            _set_jerk_time()

    @rpc_method
    def get_error(self, controller_address: Optional[int] = None) -> Tuple[str, str]:
        """
        Get the currently memorised error.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            A tuple containing the error code and the human-readable error message.
        """
        _logger.info("Getting error of instrument [%s]", self._name)
        self.controller_address = controller_address
        error_code = self._scpi_protocol.ask(
            self._build_command("TE"))[-1]
        if error_code == self.ERROR_CODE_NONE:
            return "@", "No error"

        error_str = self._scpi_protocol.ask(self._build_command(
            "TB" + error_code)).strip().split(' ', 1)[1]
        return error_code, error_str

    @rpc_method
    def stop_motion(self, controller_address: Optional[int] = None) -> None:
        """
        Stop the motion of the actuator by decelerating it. Works on DISABLE, READY and MOTION states.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        _logger.info("Stop motion of instrument [%s]", self._name)
        self.controller_address = controller_address
        self._scpi_protocol.write(
            self._build_command("ST"))
        self._check_error()

    @rpc_method
    def get_backlash_compensation(self, controller_address: Optional[int] = None) -> float:
        """
        Get the backlash value in encoder units.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        _logger.info("Getting backlash compensation of controller [%s] instrument [%s]",
                     self.controller_address, self._name)
        # instrument must be in CONFIGURATION state to get the backlash compensation.
        with self.configuration_state():
            backlash_comp = self._scpi_protocol.ask(
                self._build_command("BA?"))
            self._check_error()

        return float(backlash_comp[3:])

    @rpc_method
    def set_backlash_compensation(self, backlash_comp: float, controller_address: Optional[int] = None) -> None:
        """
        Set the backlash compensation of a controller.

        Parameters:
            backlash_comp:      backlash compensation in encoder units.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to set the backlash compensation.
        with self.configuration_state():
            # First check if the hysteresis compensation is enabled.
            hysteresis_comp = self._scpi_protocol.ask(
                self._build_command("BH?"))
            self._check_error()
            if float(hysteresis_comp[3:]) > 0.0:
                self._exit_configuration_state()
                raise QMI_InstrumentException(
                    "Backlash compensation cannot be set if hysteresis compensation is enabled!"
                )

            _logger.info(
                "Setting backlash compensation of controller [%s] instrument [%s] to [%f]",
                self.controller_address, self._name, backlash_comp)
            self._scpi_protocol.write(
                self._build_command("BA", backlash_comp))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_hysteresis_compensation(self, controller_address: Optional[int] = None) -> float:
        """
        Get the hysteresis value in encoder units.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        _logger.info("Getting hysteresis compensation of controller [%s] instrument [%s]",
                     self.controller_address, self._name)
        # instrument must be in CONFIGURATION state to get the hysteresis compensation.
        with self.configuration_state():
            hysteresis_comp = self._scpi_protocol.ask(
                self._build_command("BH?"))
            self._check_error()

        return float(hysteresis_comp[3:])

    @rpc_method
    def set_hysteresis_compensation(self, hysteresis_comp: float, controller_address: Optional[int] = None) -> None:
        """
        Set the hysteresis compensation of a controller.

        Parameters:
            hysteresis_comp:      hysteresis compensation in encoder units.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to set the hysteresis compensation.
        with self.configuration_state():
            # First check if the backlash compensation is enabled.
            backlash_comp = self._scpi_protocol.ask(
                self._build_command("BA?"))
            self._check_error()
            if float(backlash_comp[3:]) > 0.0:
                self._exit_configuration_state()
                raise QMI_InstrumentException(
                        "Hysteresis compensation cannot be set if backlash compensation is enabled!")

            _logger.info(
                "Setting hysteresis compensation of controller [%s] instrument [%s] to [%f]",
                self.controller_address, self._name, hysteresis_comp)
            self._scpi_protocol.write(
                self._build_command("BH", hysteresis_comp))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_home_search_type(self, controller_address: Optional[int] = None) -> int:
        """
        Get the type of HOME search used with the OR command.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        _logger.info(
            "Getting the type of HOME search used with the OR command of instrument [%s]", self._name)
        # instrument must be in CONFIGURATION state to get the home search type.
        with self.configuration_state():
            home_search_type = self._scpi_protocol.ask(
                self._build_command("HT?"))
            self._check_error()

        return int(home_search_type[3:])

    @rpc_method
    def set_home_search_type(self, home_search_type: int, controller_address: Optional[int] = None) -> None:
        """
        Set the type of HOME search used with the OR command.

        Parameters:
            home_search_type:   New type of HOME search used with the OR command.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        hst_values = [hst.value for hst in set(HomeSearchTypes)]
        if home_search_type not in hst_values:
            raise QMI_InstrumentException(
                f"Provided value {home_search_type} not in valid range {hst_values}.")

        _logger.info(
            "Setting the type of HOME search used with the OR command for instrument [%s] to [%s]",
            self._name, HomeSearchTypes(home_search_type).name
        )
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to set the home search type.
        with self.configuration_state():
            self._scpi_protocol.write(self._build_command(
                "HT", home_search_type))
            self._check_error()

    @rpc_method
    def get_peak_current_limit(self, controller_address: Optional[int] = None) -> float:
        """
        Get the controller’s maximum or peak output current limit to the motor.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        _logger.info("Getting the peak current limit of controller [%s] instrument [%s]",
                     self.controller_address, self._name)
        # instrument must be in CONFIGURATION state to get the current limit.
        with self.configuration_state():
            current_limit = self._scpi_protocol.ask(
                self._build_command("QIL?"))
            self._check_error()

        return float(current_limit[4:])

    @rpc_method
    def set_peak_current_limit(self, current_limit: float, controller_address: Optional[int] = None) -> None:
        """
        Set the controller’s maximum or peak output current limit to the motor.

        Parameters:
            current_limit:    Controller’s maximum or peak output current limit to the motor in [A].
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if current_limit < 0.05 or current_limit > 3.0:
            raise QMI_InstrumentException(
                    "Current limit value not in valid range 0.05 <= current_limit <= 3.0")

        self.controller_address = controller_address
        _logger.info(
            "Setting peak current limit of controller [%s] instrument [%s] to [%f]",
            self.controller_address, self._name, current_limit)
        # instrument must be in CONFIGURATION state to set the current limit.
        with self.configuration_state():
            self._scpi_protocol.write(
                self._build_command("QIL", current_limit))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_rms_current_limit(self, controller_address: Optional[int] = None) -> float:
        """
        Get the controller’s rms output current limit to the motor.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        _logger.info("Getting the RMS current limit of controller [%s] instrument [%s]",
                     self.controller_address, self._name)
        # instrument must be in CONFIGURATION state to get the current limit.
        with self.configuration_state():
            current_limit = self._scpi_protocol.ask(
                self._build_command("QIR?"))
            self._check_error()

        return float(current_limit[4:])

    @rpc_method
    def set_rms_current_limit(self, current_limit: float, controller_address: Optional[int] = None) -> None:
        """
        Set the controller’s maximum or rms output current limit to the motor.

        Parameters:
            current_limit:    Controller’s maximum or rms output current limit to the motor in [A].
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to check the peak current limit and to set the RMS current limit.
        with self.configuration_state():
            peak_current_limit = self._scpi_protocol.ask(
                self._build_command("QIL?"))
            self._check_error()
            peak_current_limit_f = min(1.5, float(peak_current_limit[4:]))
            if current_limit < 0.05 or current_limit > peak_current_limit_f:
                self._exit_configuration_state()
                raise QMI_InstrumentException(
                        f"Current limit value not in valid range 0.05 <= current_limit <= {peak_current_limit_f}"
                )

            _logger.info(
                "Setting RMS current limit of controller [%s] instrument [%s] to [%f]",
                self.controller_address, self._name, current_limit)
            self._scpi_protocol.write(self._build_command("QIR", current_limit))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_rms_current_averaging_time(self, controller_address: Optional[int] = None) -> float:
        """
        Get the controller’s averaging period for rms current calculation.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        self.controller_address = controller_address
        # instrument must be in CONFIGURATION state to get the current limit.
        with self.configuration_state():
            _logger.info("Getting the averaging period for rms current calculation of controller [%s] instrument [%s]",
                         self.controller_address, self._name)
            averaging_time = self._scpi_protocol.ask(
                self._build_command("QIT?"))
            self._check_error()

        return float(averaging_time[4:])

    @rpc_method
    def set_rms_current_averaging_time(self, averaging_time: float, controller_address: Optional[int] = None) -> None:
        """
        Set the controller’s averaging period for rms current calculation.

        Parameters:
            averaging_time:    Controller’s averaging period for rms current calculation in [s].
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if averaging_time <= 0.01 or averaging_time > 100.0:
            raise QMI_InstrumentException(
                    "Averaging period for rms current calculation not in valid range 0.01 < averaging_time <= 100.0")

        self.controller_address = controller_address
        _logger.info(
            "Setting averaging period for rms current calculation of controller [%s] instrument [%s] to [%f]",
            self.controller_address, self._name, averaging_time)
        # instrument must be in CONFIGURATION state to set the current limit.
        with self.configuration_state():
            self._scpi_protocol.write(
                self._build_command("QIT", averaging_time))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_analog_input_value(self, controller_address: Optional[int] = None) -> float:
        """
        Get the analog input value.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            Analog input value in Volts.
        """
        self.controller_address = controller_address
        _logger.info("Getting analog input value of instrument [%s]", self._name)
        analog_input = self._scpi_protocol.ask(
            self._build_command("RA"))
        self._check_error()
        return float(analog_input[3:])

    @rpc_method
    def get_ttl_input_value(self, controller_address: Optional[int] = None) -> int:
        """
        Get the TTL input value. The returned decimal number represents the binary word made of all 4 inputs,
        where bit 0 is input 1, bit 1 is input 2, bit 2 is input 3, and bit 3 is input 4.

        The TTL input value is 1 when the corresponding voltage on the pin is larger than 2.4
        volts, and it is 0 when the corresponding voltage is below 0.8 volt. When the voltage is
        between these two values, the result is unreliable and can be 1 or 0.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            TTL input value in bits. E.g. '5' means input 0 and 2 are high, all others are low.
        """
        self.controller_address = controller_address
        _logger.info("Getting TTL input value of instrument [%s]", self._name)
        ttl_input = self._scpi_protocol.ask(
            self._build_command("RB"))
        self._check_error()
        return int(ttl_input[3:])

    @rpc_method
    def get_ttl_output_value(self, controller_address: Optional[int] = None) -> int:
        """
        Get the TTL output value. The returned decimal number represents the binary word made of all 4 outputs,
        where bit 0 is output 1, bit 1 is output 2, bit 2 is output 3, and bit 3 is output 4.

        A 1 represents closed collector output transistor of the output. A 0 represents open
        collector output transistor of the output.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            TTL output value in bits. E.g. '3' means TTL outputs 1 & 2 are closed and outputs 3 & 4 open.
        """
        self.controller_address = controller_address
        _logger.info("Getting TTL output value of instrument [%s]", self._name)
        ttl_output = self._scpi_protocol.ask(
            self._build_command("SB?"))
        self._check_error()
        return int(ttl_output[3:])

    @rpc_method
    def set_ttl_output_value(self, ttl_output_value: int, controller_address: Optional[int] = None) -> None:
        """
        Get the TTL output value. The value is a binary word made of all 4 outputs,
        where bit 0 is output 1, bit 1 is output 2, bit 2 is output 3, and bit 3 is output 4.

        A 1 closes the open collector output transistor of the output. A 0 blocks the open
        collector output transistor of the output.

        Parameters:
            ttl_output_value:   New TTL output value.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        if ttl_output_value not in range(16):
            raise QMI_InstrumentException(
                f"Provided value {ttl_output_value} not in valid range 0-15 (all open - all closed).")

        self.controller_address = controller_address
        _logger.info(
            "Setting the TTL output value for instrument [%s] to [%i]", self._name, ttl_output_value
        )
        self._scpi_protocol.write(self._build_command(
            "SB", ttl_output_value))
        self._check_error()

    @rpc_method
    def get_controller_rs485_address(self) -> int:
        """
        Get the controller’s RS-485 address. Controller address is always 1 for this command.

        Returns:
            rs485_address:      Controller's axis number for new RS485 address.
        """
        self.controller_address = self.DEFAULT_CONTROLLER_ADDRESS
        _logger.info(
            "Getting RS485 address of controller [%s] instrument [%s]", self.controller_address, self._name
        )
        # instrument must be in CONFIGURATION state to get the RS485 address.
        with self.configuration_state():
            axis = self._scpi_protocol.ask(
                self._build_command("SA?"))
            self._check_error()

        return int(axis[3:])

    @rpc_method
    def set_controller_rs485_address(self, rs485_address: int) -> None:
        """
        Set the controller’s RS-485 address. Controller address is always 1 for this command.

        Parameters:
            rs485_address:      Controller's axis number for new RS485 address.
        """
        if 2 > rs485_address or rs485_address > 31:
            raise QMI_InstrumentException(
                f"Invalid controller axis number {rs485_address}")

        self.controller_address = self.DEFAULT_CONTROLLER_ADDRESS
        _logger.info(
            "Setting RS485 address of controller [%s] instrument [%s] to axis [%i]",
            self.controller_address, self._name, rs485_address
        )
        # instrument must be in CONFIGURATION state to set the RS485 address.
        with self.configuration_state():
            self._scpi_protocol.write(
                self._build_command("SA", rs485_address))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

    @rpc_method
    def get_negative_software_limit(self, controller_address: Optional[int] = None) -> float:
        """
        Get the negative software limit.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            neg_sw_limit:      Controller's negative software limit.
        """
        self.controller_address = controller_address
        _logger.info(
            "Getting the negative software limit of controller [%s] instrument [%s]",
            self.controller_address, self._name
        )
        # instrument must be in CONFIGURATION, DISABLE or READY state to get the negative software limit.
        try:
            config_state = False
            self._state_ready_check("negative software limit")

        except QMI_InstrumentException:
            self._enter_configuration_state()
            config_state = True

        neg_sw_limit = self._scpi_protocol.ask(
            self._build_command("SL?"))
        self._check_error()
        if config_state:
            self._exit_configuration_state()

        return float(neg_sw_limit[3:])

    @rpc_method
    def set_negative_software_limit(
            self, neg_sw_limit: float, persist: bool = False, controller_address: Optional[int] = None
    ) -> None:
        """
        Set the negative software limit.

        Parameters:
            neg_sw_limit:       Controller's negative software limit.
            persist:            Flag to indicate if the software limit should be persisted to the controller's memory,
                                so it is still available after powering down the controller. When not persisted, the
                                negative software limit is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        def _set_negative_software_limit():
            self._scpi_protocol.write(
                self._build_command("SL", neg_sw_limit))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

        if neg_sw_limit <= -self.MAX_FLOAT_LIMIT or neg_sw_limit > 0:
            raise QMI_InstrumentException(
                f"Negative software limit {neg_sw_limit} not in valid range -{self.MAX_FLOAT_LIMIT} "
                "< neg_sw_limit <= 0"
            )

        self.controller_address = controller_address
        _logger.info(
            "Setting negative software limit of controller [%s] instrument [%s] to [%f]",
            self.controller_address, self._name, neg_sw_limit)
        if persist:
            # instrument must be in CONFIGURATION state to set the software limit.
            with self.configuration_state():
                _set_negative_software_limit()

        else:
            # instrument must be in DISABLE or READY state to set the software limit.
            self._state_ready_check("negative software limit")
            _set_negative_software_limit()

    @rpc_method
    def get_positive_software_limit(self, controller_address: Optional[int] = None) -> float:
        """
        Get the positive software limit.

        Parameters:
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.

        Returns:
            pos_sw_limit:      Controller's positive software limit.
        """
        def _get_positive_software_limit() -> str:
            pos_sw_limit = self._scpi_protocol.ask(
                self._build_command("SR?"))
            self._check_error()
            return pos_sw_limit

        self.controller_address = controller_address
        _logger.info(
            "Getting the positive software limit of controller [%s] instrument [%s]",
            self.controller_address, self._name
        )
        # instrument must be in CONFIGURATION, DISABLE or READY state to get the positive software limit.
        try:
            self._state_ready_check("positive software limit")
            pos_sw_limit = _get_positive_software_limit()

        except QMI_InstrumentException:
            with self.configuration_state():
                pos_sw_limit = _get_positive_software_limit()

        return float(pos_sw_limit[3:])

    @rpc_method
    def set_positive_software_limit(
            self, pos_sw_limit: float, persist: bool = False, controller_address: Optional[int] = None) -> None:
        """
        Set the positive software limit.

        Parameters:
            pos_sw_limit:       Controller's positive software limit.
            persist:            Flag to indicate if the software limit should be persisted to the controller's memory,
                                so it is still available after powering down the controller. When not persisted, the
                                positive software limit is the one stored in the controller's memory.
            controller_address: Optional address of the controller that needs to be controlled. By default,
                                it is set to the initialised value of the controller address.
        """
        def _set_positive_software_limit():
            self._scpi_protocol.write(
                self._build_command("SR", pos_sw_limit))
            sleep(self.COMMAND_EXEC_TIME)
            self._check_error()

        if pos_sw_limit < 0 or pos_sw_limit >= self.MAX_FLOAT_LIMIT:
            raise QMI_InstrumentException(
                f"Positive software limit {pos_sw_limit} not in valid range 0 <= "
                f"pos_sw_limit <= {self.MAX_FLOAT_LIMIT}"
            )

        self.controller_address = controller_address
        _logger.info(
            "Setting positive software limit of controller [%s] instrument [%s] to [%f]",
            self.controller_address, self._name, pos_sw_limit)
        if persist:
            # instrument must be in CONFIGURATION state to set the software limit.
            with self.configuration_state():
                _set_positive_software_limit()

        else:
            # instrument must be in DISABLE or READY state to set the software limit.
            self._state_ready_check("positive software limit")
            _set_positive_software_limit()
