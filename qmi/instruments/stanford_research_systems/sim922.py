"""Instrument driver for the Stanford Research Systems SIM922 Temperature Monitor """
from qmi.core.instrument import QMI_Instrument
from qmi.core.context import QMI_Context
from qmi.core.rpc import rpc_method
from qmi.instruments.stanford_research_systems.sim900 import Sim900
from qmi.core.exceptions import QMI_UsageException, QMI_InstrumentException


class SIM922(QMI_Instrument):
    """Instrument driver for the Stanford Research Systems SIM922 Temperature Monitor """

    def __init__(self, context: QMI_Context, name: str, sim900: Sim900, port: int) -> None:
        """Initialize driver.

        Arguments:
            name: Name for this instrument instance
            sim900: Instance of sim 900 module or RPC proxy of it, that hosts the amp-sim module.
            port: Port number in which the amp-sim module is located.
        """
        super().__init__(context, name)
        self._sim900 = sim900
        self._port = port
        self._channel_limits = (1, 4)

    @rpc_method
    def get_id(self) -> str:
        """ Query module identification string.

        Returns:
            Module identification string.
        """
        return self._sim900.ask_module(self._port, "*IDN?")

    @rpc_method
    def get_voltage(self, channel: int) -> float:
        """ Query the readout voltage on the specified channel.

        Returns:
            Readout voltage in millivolts.
        """
        self._is_valid(channel)
        voltage_string = self._sim900.ask_module(self._port, f"VOLT? {channel}")
        try:
            return float(voltage_string)
        except ValueError as error:
            raise QMI_InstrumentException(
                "Value returned by module should have been a string representation of a float, "
                f"instead received \"{voltage_string}\"."
            ) from error

    @rpc_method
    def get_temperature(self, channel: int) -> float:
        """ Query the temperature on the specified channel.

        Returns:
            Temperature in Kelvin.
        """
        self._is_valid(channel)
        temperature_string = self._sim900.ask_module(self._port, f"TVAL? {channel}")
        try:
            return float(temperature_string)
        except ValueError as error:
            raise QMI_InstrumentException(
                "Value returned by module should have been a string representation of a float, "
                f"instead received \"{temperature_string}\""
            ) from error

    @rpc_method
    def is_excited(self, channel: int) -> bool:
        """ Query the specified channel if excitation current is on.

        Arguments:
            channel: Channel to query
        Returns:
            True if excitation current is on, else False.
        """
        self._is_valid(channel)
        excitation_string = self._sim900.ask_module(self._port,f"EXON? {channel}").strip()
        if excitation_string in ("0", "OFF"):
            return False
        elif excitation_string in ("1", "ON"):
            return True
        else:
            raise QMI_InstrumentException(
                "Value returned by module should state whether excitation current is ON/1 or OFF/0, "
                f"instead received \"{excitation_string}\""
            )

    @rpc_method
    def set_excitation(self, channel: int, current_on: bool) -> None:
        """ Set current excitation to the specified channel to on/off.
        Arguments:
            channel: Channel to set excitation current.
            current_on: True if current on, else False.
        """
        self._is_valid(channel)
        if not isinstance(current_on, bool):
            raise QMI_UsageException(f"Expected parameter \"current_on\" to be of type bool, but is {current_on!r}")
        self._sim900.send_terminated_message(self._port, f"EXON {channel},{'ON' if current_on else 'OFF'}")

    def _is_valid(self, channel: int) -> None:
        if not self._channel_limits[0] <= channel <= self._channel_limits[1]:
            raise QMI_UsageException(
                f"Channel has to be between {self._channel_limits[0]} and "
                f"{self._channel_limits[1]}, but is {channel}.")

    def __repr__(self):
        return f"{self.__class__.__name__}("\
            f"context={self._context},"\
            f"name=\"{self._name}\","\
            f"sim900={self._sim900!r},"\
            f"port={self._port})"
