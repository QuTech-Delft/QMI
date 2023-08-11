"""QMI driver for the NKT Photonics Instruments "Boostik" laser amplifier.

The protocol implemented in this driver is documented in the document
'NKT_Photonics_BoostiK_HPA_Users_Manual rev06.pdf', section 4.3.2.
"""

import logging
import struct
from typing import Optional

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class KoherasBoostikLaserAmplifier(QMI_Instrument):
    DEFAULT_TIMEOUT = 0.500  # 500 ms ought to be plenty.

    def __init__(
        self,
        context: QMI_Context,
        name: str,
        transport: str,
        timeout: Optional[float] = DEFAULT_TIMEOUT,
    ):
        super().__init__(context, name)
        self._transport = create_transport(
            transport,
            default_attributes={
                "baudrate": 9600,
                "bytesize": 8,
                "parity": "N",
                "stopbits": 1.0,
                "rtscts": False,
            },
        )

        self._timeout = timeout

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        self._transport.discard_read()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    def _send_command(self, cmd: str) -> None:
        cmd_bin = (cmd + "\r\n").encode("ascii")
        self._transport.write(cmd_bin)

    def _get_string(self, cmd: str) -> str:
        self._send_command(cmd)
        response_bin = self._transport.read_until(b"\r\n", self._timeout)
        response_str = response_bin.decode("ascii")
        assert response_str.endswith("\r\n")
        response_str = response_str[:-2]
        return response_str

    def _get_float(self, cmd: str) -> float:
        response = self._get_string(cmd)
        return float(response)

    def _get_integer(self, cmd: str) -> int:
        response = self._get_string(cmd)
        return int(response)

    def _get_boolean(self, cmd: str) -> bool:
        response = self._get_integer(cmd)
        assert response in [0, 1]
        return bool(response)

    @rpc_method
    def get_current_setpoint(self) -> float:
        """Retrieve the setpoint in ACC (current controlled) mode, in [A]."""
        return self._get_float("ACC")

    @rpc_method
    def get_actual_current(self) -> float:
        """Retrieve the real current value, in [A]."""
        return self._get_float("AMC")

    @rpc_method
    def get_diode_booster_temperature(self) -> float:
        """Retrieve the diode booster temperature, in [°C]."""
        return self._get_float("AMT 1")

    @rpc_method
    def get_ambient_temperature(self) -> float:
        """Retrieve the ambient temperature, in [°C]."""
        return self._get_float("CMA")

    @rpc_method
    def get_input_power(self) -> float:
        """Retrieve input power, in [mW]."""
        return self._get_float("CMP 1")

    @rpc_method
    def get_amplifier_enabled(self) -> bool:
        """Retrieve the ON/OFF status of the amplifier."""
        return self._get_boolean("CDO")

    @rpc_method
    def get_amplifier_information(self) -> str:
        """Retrieve the serial number information of the amplifier."""
        return self._get_string("CDI")

    @rpc_method
    def set_current_setpoint(self, current: float) -> float:
        """Set the ACC current setpoint, in [A].

        The command returns the actual setpoint after executing the command.
        In case the command was unsuccessful (current out of range), the unchanged
        current setpoint is returned.

        Parameters:
            current: In Amperes.
        """
        return self._get_float(f"ACC {current}")

    @rpc_method
    def set_amplifier_enabled(self, enable: bool) -> bool:
        """Enable or disable the amplifier.

        The command returns the enabled status after the command.

        Parameters:
            enable: Boolean for disabling (False) or enabling (True).
        """
        value = int(bool(enable))
        return self._get_boolean(f"CDO {value}")
