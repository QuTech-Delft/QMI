"""Instrument driver for the AGC302 Active Vacuum Gauge Controller."""

from typing import Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport, QMI_Transport


class InstruTech_AGC302(QMI_Instrument):
    """Instrument driver for the AGC302 Active Vacuum Gauge Controller."""

    def __init__(self, context: QMI_Context, name: str, transport: Union[str, QMI_Transport], timeout: float = 1):
        """Initialize the pressure gauge Agc302 driver.

        Args:
            context: QMI context.
            name: Name for this instrument instance.
            transport:  Either a transport string (see create_transport) or a QMI_Transport.
            timeout: Maximum time [s] to wait before transport timeout occurs.
        """
        super().__init__(context, name)
        if isinstance(transport, str):
            self._transport = create_transport(transport)
        elif isinstance(transport, QMI_Transport):
            self._transport = transport
        self._timeout = timeout

    @rpc_method
    def open(self) -> None:
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        super().close()
        self._transport.close()

    def _ask(self, command: str) -> str:
        super()._check_is_open()
        bytes_command = "#  {}\r".format(command).encode(encoding='ascii')
        self._transport.write(bytes_command)
        response = self._transport.read_until(b'\r', self._timeout)
        if len(response) != 13:
            raise QMI_InstrumentException("Got wrong response from device: {!r}.".format(response))
        if response.startswith(b'?') and b'SYNTX_ER' in response:
            # Response to an unknown command
            raise QMI_InstrumentException("Syntax Error in command: {}.".format(command))
        return response[4:-1].decode('ascii')

    def _set(self, command: str) -> None:
        response = self._ask(command)
        if 'PROGM_OK' not in response:
            raise QMI_InstrumentException(
                "Did not successfully program device is command: {} ok?, got response {}.".format(command, response))

    @rpc_method
    def read_gauge(self) -> float:
        """Read the current gauge pressure.

        Returns:
            The device will return a pressure value in units of TORR, MBAR, or PASCAL depending on the current
            settings. Use read_pressure_unit to obtain the current used unit.

        Raises:
            QMI_InstrumentException: When sensor is off or when a device does not exists.
        """
        response = self._ask("RD")

        if "1.10E+03" in response:
            raise QMI_InstrumentException("Sensor is off")
        elif "9.90E+09" in response:
            raise QMI_InstrumentException("Device does not exist")
        else:
            return float(response)

    @rpc_method
    def read_pressure_unit(self) -> str:
        """Read the current set pressure unit.

        Returns:
            The gauge reports the measured pressure in Torr, mbar or Pascal. The return values are in capital letters so
            either TORR, MBAR, or PASCAL.
        """
        response = self._ask("RU")
        unit = response.split()
        return unit[0]

    @rpc_method
    def set_pressure_unit(self, unit: str) -> None:
        """Set pressure unit for display and RD response.

        Args:
            unit (str): pressure unit to use. A single letter needs to be provided that is either T = Torr, M = mBar, or
            P = Pascal.

        Raises:
            ValueError: when provided pressure unit letter is not T, M, or P.
        """
        if unit not in ['T', 'M', 'P']:
            raise ValueError('Unit not T = Torr, M = mBar, P = Pascal.')
        self._set('SU{}'.format(unit))
