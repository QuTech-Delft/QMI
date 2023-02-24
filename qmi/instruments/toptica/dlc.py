"""Instrument driver for the Toptica DLC Pro digital laser controller."""

import logging
import time
from typing import Any, List, Tuple

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport


# Module logger.
_logger = logging.getLogger(__name__)


class Toptica_DLC(QMI_Instrument):
    """Instrument driver for the Toptica DLC Pro digital laser controller.

    This driver implements a single connection to the instrument. The communication is using a Scheme-based command
    language on TCP port 1998;

    NOTE: the driver does not currently support the parameter monitoring facility on TCP port 1999.

    Parameters:
        context:    QMI context.
        name:       name for the instrument instance.
        transport:  transport string.
    """

    # Instrument should respond within 2 seconds.
    RESPONSE_TIMEOUT = 2.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize driver."""
        super().__init__(context, name)
        self._transport = create_transport(transport)

    @rpc_method
    def open(self) -> None:
        """"Open connection with the instrument."""
        _logger.info("Opening connection to instrument")
        self._transport.open()
        try:
            self._main_handshake()
        except Exception:
            self._transport.close()
            raise
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close connection with the instrument."""
        _logger.info("Closing connection to instrument")
        super().close()
        self._transport.close()

    def _main_handshake(self) -> None:
        """Read initial welcome message from Telnet port."""
        self._transport.read_until(message_terminator=b"DeCoF Command Line\r\n> ", timeout=self.RESPONSE_TIMEOUT)

    @staticmethod
    def _parse_value_string(value_string: str) -> Any:
        """Parse a response string to a value."""
        # NOTE: for now, we don't handle ints, but instead return a float.
        if value_string == "#f":
            # Value is a boolean False.
            return False
        elif value_string == "#t":
            # Value is a boolean True.
            return True
        elif len(value_string) >= 2 and value_string.startswith('"') and value_string.endswith('"'):
            # Value is a string.
            return value_string[1:-1]
        elif value_string.startswith('(') and value_string.endswith(')'):
            # Tuple: this breaks for nested nested tuples.
            return tuple(Toptica_DLC._parse_value_string(x) for x in value_string[1:-1].split())
        else:
            # Assume it is a float or can be converted to a float.
            return float(value_string)

    @staticmethod
    def _value_to_string(value: Any) -> str:
        """Convert a value to its string representation."""
        # Only handles bools, ints, and floats.
        if isinstance(value, bool):
            return "#t" if value else "#f"
        elif isinstance(value, (int, float)):
            return repr(value)
        elif isinstance(value, str):
            return value
        else:
            raise ValueError(f"Invalid value or type for {value}")

    @rpc_method
    def get_timestamped_parameter(self, parameter_name: str) -> Tuple[float, Any]:
        """Get parameter value from the controller.

        Parameters:
            parameter_name: string identifier of the parameter to get.
        """
        # Send request.
        command = "(param-ref '{})\n".format(parameter_name).encode()
        self._transport.write(command)

        # Get response.
        response = self._transport.read_until(b"\n", timeout=self.RESPONSE_TIMEOUT)
        timestamp = time.time()

        # Read until prompt.
        self._transport.read_until(b"> ", timeout=self.RESPONSE_TIMEOUT)

        # Decode response.
        response = response[:-1]  # strip newline.
        decoded_response = response.decode()
        if decoded_response.startswith("Error:"):
            raise ValueError("While getting parameter {!r}: {!r}".format(parameter_name, decoded_response))

        return timestamp, self._parse_value_string(decoded_response)

    @rpc_method
    def get_parameter(self, parameter_name: str) -> Any:
        """Get a single parameter value from the controller.

        Returns a timestamp of when the parameteres were requested from the controller and the parameter value.

        Parameters:
            parameter_name: string identifier of the parameter to get.
        """
        _, value = self.get_timestamped_parameter(parameter_name)
        return value

    @rpc_method
    def get_multiple_timestamped_parameters(self, parameter_names: List[str]) -> Tuple[float, Tuple[Any, ...]]:
        """Get multiple parameter values from the controller.

        Returns a timestamp of when the parameters were requested from the controller and a tuple of parameter values.

        Note: this method cannot handle nested tuples (e.g. one of the parameter values is a tuple).

        Parameters:
            parameter_names:    a list of string identifiers of the parameters to get.
        """
        # Send request.
        command = "`({})\n".format(
            "".join(",(param-ref '{})".format(parameter_name) for parameter_name in parameter_names)).encode()
        self._transport.write(command)

        # Get response.
        response = self._transport.read_until(b"\n", timeout=self.RESPONSE_TIMEOUT)
        timestamp = time.time()

        # Read until prompt.
        self._transport.read_until(b"> ", timeout=self.RESPONSE_TIMEOUT)

        # Decode response.
        response = response[:-1]  # strip newline
        decoded_response = response.decode()
        if decoded_response.startswith("Error:"):
            raise ValueError("While getting multiple parameters {!r}: {!r}".format(parameter_names, response))

        # Check that a tuple was returned.
        retval = self._parse_value_string(decoded_response)
        assert isinstance(retval, tuple)

        return timestamp, retval

    @rpc_method
    def get_multiple_parameters(self, parameter_names: List[str]) -> Tuple[Any, ...]:
        """Get mulitple parameter values.

        Parameters:
            parameter_names:    a list of string identifiers of the parameters to get.
        """
        _, values = self.get_multiple_timestamped_parameters(parameter_names)
        return values

    @rpc_method
    def set_parameter(self, parameter_name: str, value: Any) -> float:
        """Set parameter value from the controller.

        Returns the time at which the set command was sent to the controller.

        Parameters:
            parameter_name: string identifier of the parameter to set.
            value:          new value for the parameter.
        """
        # Convert value to string respresentation.
        value_string = self._value_to_string(value)

        # Send command.
        command = "(param-set! '{} {})\n".format(parameter_name, value_string).encode()
        self._transport.write(command)
        timestamp = time.time()

        # Get response.
        response = self._transport.read_until(b"\n", self.RESPONSE_TIMEOUT)

        # Read until prompt.
        self._transport.read_until(b"> ", self.RESPONSE_TIMEOUT)

        # Decode response.
        response = response[:-1]  # strip newline
        decoded_response = response.decode()
        if decoded_response.startswith("Error:"):
            raise ValueError("while setting parameter {!r}: {!r}".format(parameter_name, response))

        return timestamp

    @rpc_method
    def set_multiple_parameters(self, parameters: List[Tuple[str, Any]]) -> float:
        """Set parameter value from the controller.

        Returns the time at which the set command was sent to the controller.

        Parameters:
            parameters: a list of tuples with parameter_name-value pairs.
        """
        # Compose command.
        subcommands = [
            "(param-set! '{} {})".format(pname, self._value_to_string(pvalue)) for pname, pvalue in parameters
        ]
        command = "(+ {})\n".format("".join(subcommands)).encode()

        # Send command.
        self._transport.write(command)
        timestamp = time.time()

        # Get response.
        response = self._transport.read_until(b"\n", self.RESPONSE_TIMEOUT)

        # Read until prompt.
        self._transport.read_until(b"> ", self.RESPONSE_TIMEOUT)

        # Decode response.
        response = response[:-1]  # strip newline.
        decoded_response = response.decode()
        if decoded_response.startswith("Error:"):
            raise ValueError("while setting multiple parameters {!r}: {!r}".format(
                [p for p, _ in parameters], response)
            )

        return timestamp
