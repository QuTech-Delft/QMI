"""
Instrument driver for the Thorlabs TSP01 environmental sensor.
"""

import logging
from typing import List

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport, list_usbtmc_transports, UsbTmcTransportDescriptorParser

# Global variable holding the logger for this module.

_logger = logging.getLogger(__name__)


class Thorlabs_TSP01(QMI_Instrument):
    """Instrument driver for the Thorlabs TSP01 environmental sensor."""

    USB_VENDOR_ID = 0x1313
    USB_PRODUCT_ID = 0x80f8

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
                if parameters.get("vendorid") == Thorlabs_TSP01.USB_VENDOR_ID and \
                        parameters.get("productid") == Thorlabs_TSP01.USB_PRODUCT_ID:
                    devices.append(desc_str)
        return devices

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialize the instrument driver.

        Parameters:
            name: Name for this instrument instance.
            transport: Transport descriptor to access this instrument.
                For the Thorlabs TSP01, this is typically
                "usbtmc:vendorid=0x1313:productid=0x80f8:serialnr=<device_serial_number>"
        """
        super().__init__(context, name)
        self._transport = create_transport(transport)
        self._scpi_protocol = ScpiProtocol(self._transport,
                                           default_timeout=self.DEFAULT_RESPONSE_TIMEOUT)

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        self._check_is_open()
        self._scpi_protocol.write("*RST")
        self._scpi_protocol.ask("*OPC?")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        response = self._scpi_protocol.ask("*IDN?")
        words = response.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException("Unexpected response to *IDN?, got {!r}".format(response))
        return QMI_InstrumentIdentification(vendor=words[0],
                                            model=words[1],
                                            serial=words[2],
                                            version=words[3])

    @rpc_method
    def get_errors(self) -> List[str]:
        """Read pending error messages from the instrument."""
        errors = []
        while True:
            response = self._scpi_protocol.ask("SYST:ERR?")
            if response.startswith("0,"):
                break
            errors.append(response)
        return errors

    @rpc_method
    def get_temperature(self, sensor: int) -> float:
        """Measure the temperature.

        Parameters:
            sensor: Select temperature sensor
                1 = internal sensor;
                2 = external thermistor 1;
                3 = external thermistor 2.
        Returns:
            Measured temperature in Celcius.
        """
        if sensor not in (1, 2, 3):
            raise QMI_InstrumentException("Unknown temperature sensor {}".format(sensor))
        cmd = "MEAS:TEMP{}?".format(sensor)
        response = self._scpi_protocol.ask(cmd)
        try:
            return float(response)
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to {!r}, got {!r}".format(cmd, response))

    @rpc_method
    def get_humidity(self) -> float:
        """Measure the relative humidity (using the internal sensor)..

        Returns:
            Measured relative humidity in percent.
        """
        cmd = "MEAS:HUM?"
        response = self._scpi_protocol.ask(cmd)
        try:
            return float(response)
        except ValueError:
            raise QMI_InstrumentException("Unexpected response to {!r}, got {!r}".format(cmd, response))
