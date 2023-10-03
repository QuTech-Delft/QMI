"""
Instrument driver for the Thorlabs PM100D and compatible optical power meter.
"""

import logging
import re
import time
from typing import List, NamedTuple, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport, list_usbtmc_transports, UsbTmcTransportDescriptorParser

# Global variable holding the logger for this module.

_logger = logging.getLogger(__name__)

# Tuple type returned by get_sensor_info().
SensorInfo = NamedTuple('SensorInfo',
                        [('name', str),
                         ('serial', str),
                         ('cal_msg', str),
                         ('type', str),
                         ('subtype', str),
                         ('flags', int)])


class Thorlabs_PM10x(QMI_Instrument):
    """General instrument driver for the Thorlabs PM10x optical power meters.

    This driver is also compatible with the Thorlabs PM16-120.
    """
    VENDOR_ID = 0x1313  # Thorlabs' vendor ID.
    PRODUCT_ID = 0x0000  # To be overridden by deriving subclasses.

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    @staticmethod
    def list_instruments() -> List[str]:
        """Return a list of QMI transport descriptors for attached power meters."""
        devices = []
        parser = UsbTmcTransportDescriptorParser
        for desc_str in list_usbtmc_transports():
            if parser.match_interface(desc_str):
                parameters = parser.parse_parameter_strings(desc_str)
                if parameters.get("vendorid") == Thorlabs_PM100D.VENDOR_ID and \
                        parameters.get("productid") in (Thorlabs_PM100D.PRODUCT_ID,
                                                        Thorlabs_PM100USB.PRODUCT_ID,
                                                        Thorlabs_PM101U.PRODUCT_ID,
                                                        Thorlabs_PM16_120.PRODUCT_ID):
                    devices.append(desc_str)
        return devices

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport = create_transport(transport)
        self._scpi_protocol = ScpiProtocol(self._transport, default_timeout=self._timeout)

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        resp = self._scpi_protocol.ask("SYST:ERR?")
        # When there are no errors, the response is '+0,"No error"'.
        if not re.match(r"^\s*[-+]?\s*0\s*,", resp):
            # Some error occurred.
            raise QMI_InstrumentException("Instrument returned error: {}".format(resp))

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        self._check_is_open()
        self._scpi_protocol.write("*CLS")  # clear error queue
        self._scpi_protocol.write("*RST")
        self._scpi_protocol.ask("*OPC?")
        self._check_error()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(resp))
        return QMI_InstrumentIdentification(vendor=words[0],
                                            model=words[1],
                                            serial=words[2],
                                            version=words[3])

    @rpc_method
    def get_sensor_info(self) -> SensorInfo:
        """Get sensor type and return information as a SensorInfo instance."""
        self._check_is_open()
        resp = self._scpi_protocol.ask('SYST:SENS:IDN?')
        words = resp.split(',')
        if len(words) != 6:
            raise QMI_InstrumentException("Unexpected response to SYST:SENS:IDN?, got {!r}".format(resp))
        return SensorInfo(name=words[0],
                          serial=words[1],
                          cal_msg=words[2],
                          type=words[3],
                          subtype=words[4],
                          flags=int(words[5]))

    @rpc_method
    def get_timestamped_power(self) -> Tuple[float, float]:
        """Start measurement and return measured power [W]."""
        self._check_is_open()
        resp = self._scpi_protocol.ask('MEAS:POW?')
        timestamp = time.time()
        power = float(resp)
        return timestamp, power

    @rpc_method
    def get_power(self) -> float:
        """Start measurement and return measured power [W].

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        """
        (_, power) = self.get_timestamped_power()
        return power

    @rpc_method
    def get_range(self) -> float:
        """Get measurement range [W]."""
        self._check_is_open()
        resp = self._scpi_protocol.ask("SENS:POW:RANG?")
        return float(resp)

    @rpc_method
    def get_range_in_use(self) -> float:
        """Return the currently used measuring range in Watt.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        Other implementations may return the range as an index or code.
        """
        return self.get_range()

    @rpc_method
    def set_range(self, measurement_range: float) -> None:
        """Set measurement range [W]."""
        self._check_is_open()
        cmd = "SENS:POW:RANG {}".format(measurement_range)
        self._scpi_protocol.write(cmd)
        self._check_error()

    @rpc_method
    def get_autorange(self) -> bool:
        """Return True if the power meter is in auto range mode."""
        self._check_is_open()
        resp = self._scpi_protocol.ask("SENS:POW:RANG:AUTO?")
        return bool(int(resp))

    @rpc_method
    def set_autorange(self, enable: bool) -> None:
        """Enable or disable auto range mode.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        """
        self._check_is_open()
        value = 1 if enable else 0
        cmd = "SENS:POW:RANG:AUTO {}".format(value)
        self._scpi_protocol.write(cmd)
        self._check_error()

    @rpc_method
    def get_wavelength(self) -> float:
        """Return configured wavelength [nm]."""
        self._check_is_open()
        resp = self._scpi_protocol.ask('SENS:CORR:WAV?')
        return float(resp)

    @rpc_method
    def set_wavelength(self, wavelength: float) -> None:
        """Configure the wavelength in nm.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        """
        self._check_is_open()
        cmd = "SENS:CORR:WAV {}".format(wavelength)
        self._scpi_protocol.write(cmd)
        self._check_error()

    @rpc_method
    def get_current(self) -> float:
        """Start measurement and return measured diode current in Ampere."""
        resp = self._scpi_protocol.ask('MEAS:CURR?')
        return float(resp)


class Thorlabs_PM100D(Thorlabs_PM10x):
    """Alias class for PM100D; uses the interface of PM10x."""
    PRODUCT_ID = 0x8078


class Thorlabs_PM100USB(Thorlabs_PM10x):
    """Alias class for PM100USB; uses the interface of PM10x."""
    PRODUCT_ID = 0x8072


class Thorlabs_PM101U(Thorlabs_PM10x):
    """Alias class for PM101U; uses the interface of PM10x."""
    PRODUCT_ID = 0x8076


class Thorlabs_PM16_120(Thorlabs_PM10x):
    """Alias class for PM16_120; uses the interface of PM10x."""
    PRODUCT_ID = 0x807b
