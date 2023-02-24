"""
Instrument driver for the Newport CONEX-CC DC servo motion controller.
"""
import logging
from time import sleep
from typing import List, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.instruments.newport.actuators import LinearActuator


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Newport_ConexCC_Controller(QMI_Instrument):
    """Instrument driver for the Newport CONEX-CC DC servo motion controller."""

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # HOME search time out
    HOME_SEARCH_TIMEOUT = 5.0

    # Time to execute a command
    COMMAND_EXEC_TIME = 0.5

    # Code for no error
    ERROR_CODE_NONE = "@"

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
                 actuator: LinearActuator
                 ) -> None:
        """Initialize driver.

        Parameters:
            name:       Name for this instrument instance.
            transport:  QMI transport descriptor to connect to the instrument.
            actuator:   The linear actuator that this controller will drive.
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport_str = transport
        self._transport = create_transport(transport, default_attributes={"port": 5025})
        self._scpi_protocol = ScpiProtocol(self._transport,
                                           command_terminator="\r\n",
                                           response_terminator="\r\n",
                                           default_timeout=self._timeout)
        self._actuator = actuator
        self._serial = self._transport_str.split("-")[1].split(":")[0]

    def _parse_ascii_command(self, cmd: str, value: Optional[float] = None) -> str:
        """Parse ASCII command.

        Parameters:
            cmd:       Name of command.
            value:     Value to go with command if needed.
        """
        # NOTE: the control address is always set to 1
        # source: https://www.newport.com/mam/celum/celum_assets/resources/CONEX-CC_-_LabVIEW_Drivers_Manual.pdf?1
        if value is None:
            return f"1{cmd}\r\n"
        else:
            return f"1{cmd}{value}\r\n"

    def _check_error(self) -> None:
        """Check the currently memorised error."""
        error_code = self._scpi_protocol.ask(self._parse_ascii_command("TE"))[-1]
        sleep(self.COMMAND_EXEC_TIME)
        if error_code != self.ERROR_CODE_NONE:
            error_str = self._scpi_protocol.ask(self._parse_ascii_command("TB" + error_code)).strip().split(' ', 1)[1]
            _logger.error("Error %s: %s" % (error_code, error_str))
            raise QMI_InstrumentException(f"Error {error_code}: {error_str}")

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection instrument [%s]", self._name)
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
    def reset(self) -> None:
        """
        Reset the instrument. Equivalent to a power-up.
        """
        _logger.info("Resetting instrument [%s]", self._name)
        self._scpi_protocol.write(self._parse_ascii_command("RS"))
        self._check_error()

    @rpc_method
    def get_revision_info(self) -> QMI_InstrumentIdentification:
        """
        Read instrument type and version and return QMI_InstrumentIdentification instance.
        """
        instr_info = self._scpi_protocol.ask(self._parse_ascii_command("VE"))
        self._check_error()
        words = instr_info[1:].strip().split()
        return QMI_InstrumentIdentification(vendor="Newport",
                                            model=words[1],
                                            version=words[2],
                                            serial=self._serial)

    @rpc_method
    def get_positioner_error_and_state(self) -> Tuple[List[str], str]:
        """
        Get the positioner error and the current state of the controller.
        """
        err_and_state = self._scpi_protocol.ask(self._parse_ascii_command("TS"))
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
    def home_search(self) -> None:
        """
        Executes the home search. This is needed before any motion commands
        can be executed. It finds the origin position of the actuator.
        """
        self._scpi_protocol.write(self._parse_ascii_command("OR"))
        self._check_error()

    @rpc_method
    def set_home_search_timeout(self, timeout: float) -> None:
        """
        Sets the time-out for the home search.
        """
        self._scpi_protocol.write(self._parse_ascii_command("OT", timeout))
        self._check_error()

    @rpc_method
    def move_absolute(self, position: float) -> None:
        """
        Perform an absolute move.

        Parameters:
            position:   New position to move to in mm.
        """
        if position > self._actuator.TRAVEL_RANGE:
            raise QMI_InstrumentException(
                f"Provided value {position} greater than allowed maximum {self._actuator.TRAVEL_RANGE}")
        if position < self._actuator.MIN_INCREMENTAL_MOTION:
            raise QMI_InstrumentException(
                f"Provided value {position} lower than minimum {self._actuator.MIN_INCREMENTAL_MOTION}")
        self._scpi_protocol.write(self._parse_ascii_command("PA", position))
        self._check_error()

    @rpc_method
    def get_position(self) -> float:
        """
        Get the actual position of the actuator according to the encoder value.
        """
        pos = self._scpi_protocol.ask(self._parse_ascii_command("TP"))
        self._check_error()
        return float(pos[3:])

    @rpc_method
    def move_relative(self, displacement: float) -> None:
        """
        Perform a relative move from the current position.

        Parameters:
            displacement:   Displacement from current position.
        """
        self._scpi_protocol.write(self._parse_ascii_command("PR", displacement))
        self._check_error()

    @rpc_method
    def enter_configuration_state(self) -> None:
        """
        Enter the CONFIGURATION state of the controller from the NOT REFERENCED state.

        NOTE:   In this state the parameters are stored in the flash memory of the controller.
                The device supports up to 100 writes, so this command should not be used often.
        """
        self._scpi_protocol.write(self._parse_ascii_command("PW", 1))
        self._check_error()

    @rpc_method
    def exit_configuration_state(self) -> None:
        """
        Exit the CONFIGURATION state of the controller to the NOT REFERENCED state.
        NOTE:   Due to a quirk, checking the error after exiting this state throws
                a timeout error, so error checking is removed.
        """
        sleep(self.COMMAND_EXEC_TIME)
        self._scpi_protocol.write(self._parse_ascii_command("PW", 0))

    @rpc_method
    def get_encoder_increment_value(self) -> float:
        """
        Get the encoder increment.
        """
        pos = self._scpi_protocol.ask(self._parse_ascii_command("SU?"))
        self._check_error()
        return float(pos[3:])

    @rpc_method
    def set_encoder_increment_value(self, units: float) -> None:
        """
        Set the encoder increment.
        """
        self._scpi_protocol.write(self._parse_ascii_command("SU", units))
        self._check_error()

    @rpc_method
    def get_home_search_timeout(self) -> float:
        """
        Set the encoder increment.
        """
        timeout = self._scpi_protocol.ask(self._parse_ascii_command("OT?"))
        self._check_error()
        return float(timeout[3:])

    @rpc_method
    def set_velocity(self, velocity: float) -> None:
        """
        Sets the velocity at which the actuator moves.

        Parameters:
            velocity:   Velocity in unit/s. The unit depends on the encoder resolution,
                        which is usually set to 1mm
        """
        if velocity > self._actuator.MAX_VELOCITY:
            raise QMI_InstrumentException(
                f"Provided value {velocity} greater than allowed maximum {self._actuator.MAX_VELOCITY}")
        if velocity < self._actuator.MIN_VELOCITY:
            raise QMI_InstrumentException(f"Provided value {velocity} lower than minimum {self._actuator.MIN_VELOCITY}")
        self._scpi_protocol.write(self._parse_ascii_command("VA", velocity))
        self._check_error()

    @rpc_method
    def get_velocity(self) -> float:
        """
        Get the velocity of the actuator in unit/s, so if the the encoder unit is mm,
        then the returned value is in mm/s.
        """
        self.enter_configuration_state()
        vel = self._scpi_protocol.ask(self._parse_ascii_command("VA?"))
        self.exit_configuration_state()
        self._check_error()
        return float(vel[3:])

    @rpc_method
    def get_error(self) -> Tuple[str, str]:
        """
        Check the currently memorised error.

        Returns a tuple containing the error code and the human readable error message.
        """
        error_code = self._scpi_protocol.ask(self._parse_ascii_command("TE"))[-1]
        if error_code == self.ERROR_CODE_NONE:
            return ("@", "No error")
        error_str = self._scpi_protocol.ask(self._parse_ascii_command("TB" + error_code)).strip().split(' ', 1)[1]
        return (error_code, error_str)

    @rpc_method
    def setup_encoder_resolution(self, value: Optional[float] = None) -> None:
        """
        Sets up the encoder unit. By default to be as close to 1mm as possible.
        Check the example (SU command) in the doc below to see how the increment value is
        calculated:
        https://www.newport.com/mam/celum/celum_assets/np/resources/CONEX-CC_-_Controller_Documentation.pdf?0

        Parameters:
            value:    Increment value.
        """
        self.reset()
        self.enter_configuration_state()
        self.set_encoder_increment_value(value if value is not None else self._actuator.ENCODER_RESOLUTION)
        self.exit_configuration_state()

    @rpc_method
    def setup_home_search_timeout(self, timeout: Optional[float] = None) -> None:
        """
        Sets up the timeout for the home search.

        Parameters:
            timeout:    Timeout in seconds.
        """
        self.reset()
        self.enter_configuration_state()
        self.set_home_search_timeout(timeout if timeout is not None else (self.HOME_SEARCH_TIMEOUT))
        self.exit_configuration_state()

    @rpc_method
    def setup_velocity(self, velocity: float) -> None:
        """
        Sets up the velocity of the actuator.

        Parameters:
            velocity:   Velocity in unit/s. The unit depends on the encoder resolution,
                        which is usually set to 1mm
        """
        self.reset()
        self.enter_configuration_state()
        self.set_velocity(velocity)
        self.exit_configuration_state()

    @rpc_method
    def get_encoder_unit(self) -> float:
        """
        Calculate the encoder unit.

        Returns the value of encoder unit.
        """
        self.enter_configuration_state()
        res = self.get_encoder_increment_value()
        self.exit_configuration_state()
        return self._actuator.ENCODER_RESOLUTION / res
