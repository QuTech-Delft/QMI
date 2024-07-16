""" QMI instrument driver for the High Finesse Wavemeter instrument.

The instrument driver makes use of the manufacturer provided software libraries, "libwlmData.so" for Linux OS,
or "wlmData.dll" for Windows, or "libwlmData.dylib" for MacOS.
Please find the licence terms for these files as well as further documentation on the manufacturer's website at
https://www.highfinesse.com/en/support/downloads.html.
This driver has been tested on the WS-6 model.
"""

from __future__ import annotations

import logging

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.instruments.high_finesse.support import wlmConst
from qmi.instruments.high_finesse.support._library_wrapper import _LibWrapper, WS8_ERR

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class HighFinesse_WS(QMI_Instrument):
    """A network based driver for the High Finesse Wavelength meter.

    This driver automatically detects the platform of the client and will load the respective driver library
    (wlmData.dll for Windows, libwlmData.so for Linux, and libwlmData.dylib for MacOS). Make sure that the library is
    available on your system and that the wlmData.ini file contains the IP address of the server.
    """

    MAX_CHANNEL_NUMBER = 8

    def __init__(self, context: QMI_Context, name: str) -> None:
        """Initialize the instrument driver.

        :param context: QMI_Context object for the instrument driver.
        :param name:    Name for this instrument instance.
        """
        self._lib: _LibWrapper = _LibWrapper()
        super().__init__(context, name)

    @rpc_method
    def open(self) -> None:
        """Connect to the WLM hardware."""
        _logger.debug("[%s] Opening connection to instrument", self._name)
        super().open()

    @rpc_method
    def start_server(self) -> bool:
        """Start the device server if it is not running already.

        Returns:
             True if the server was started, or False if already running.
        """
        wlm_count = self._lib.dll.GetWLMCount(0)
        _logger.info("[%s] Starting server, current wlm count = %d", self._name, wlm_count)
        if wlm_count == 0:
            status = self._lib.dll.ControlWLMEx(wlmConst.cCtrlWLMWait, 0, 0, 10_000, 0)
            _logger.debug("[%s] Started server with status = %d", self._name, status)
            status = self._lib.dll.Operation(wlmConst.cCtrlStartMeasurement)
            _logger.debug("[%s] Started measurement with status = %d", self._name, status)
            return True
        return False

    @rpc_method
    def stop_server(self) -> None:
        """Stop the device server if it is running."""
        wlm_count = self._lib.dll.GetWLMCount(0)
        _logger.info("[%s] Stopping server, current wlm count = %d", self._name, wlm_count)
        if wlm_count > 0:
            status = self._lib.dll.Operation(wlmConst.cCtrlStopAll)
            _logger.debug("[%s] Stopped measurement with status = %d", self._name, status)
            status = self._lib.dll.ControlWLM(wlmConst.cCtrlWLMExit, 0, 0)
            _logger.debug("[%s] Stopped server with status = %d", self._name, status)

    @rpc_method
    def get_version(self) -> str:
        """Get the WLM version as a string.

        Returns:
            str: The version in the format "WLM Version: [{type}.{version}.{revision}.{build}]"
        """
        version_type = self._lib.dll.GetWLMVersion(0)
        version_ver = self._lib.dll.GetWLMVersion(1)
        version_rev = self._lib.dll.GetWLMVersion(2)
        version_build = self._lib.dll.GetWLMVersion(3)

        version_str = f"{version_type}.{version_ver}.{version_rev}.{version_build}"
        _logger.info("[%s] Get version: [%s]", self._name, version_str)

        return f"WLM Version: [{version_str}]"

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        version_type = self._lib.dll.GetWLMVersion(0)
        version_ver = self._lib.dll.GetWLMVersion(1)
        version_rev = self._lib.dll.GetWLMVersion(2)
        return QMI_InstrumentIdentification(vendor="HighFinesse",
                                            model=f"WLM-{version_type}",
                                            serial=str(version_ver),
                                            version=str(version_rev))

    @rpc_method
    def get_frequency(self, channel: int) -> float:
        """Get the main results of the measurement of a specified signal.

        :param channel: The signal number (1 to 8) in case of a WLM with multi channel switch or with double pulse
            option (MLC). For WLMs without these options 1 should be overhanded.
        :return: The last measured frequency value in THz.
        :raises QMI_InstrumentException: In case of instrument error.
        """
        _logger.info("[%s] Getting frequency on channel %d", self._name, channel)
        self._check_channel(channel)

        frequency = self._lib.dll.GetFrequencyNum(channel, 0.0)

        return self._check_for_error_code(frequency, "GetFrequencyNum")

    @rpc_method
    def get_wavelength(self, channel: int) -> float:
        """Get the main results of the measurement of a specified signal.

        :param channel: The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
            option (MLC). For WLMs without these options 1 should be overhanded.
        :return: The last measured wavelength in nm.
        :raises QMI_InstrumentException: In case of instrument error or channel out of range.
        """
        _logger.info("[%s] Getting wavelength on channel %d", self._name, channel)
        self._check_channel(channel)

        wavelength = self._lib.dll.GetWavelengthNum(channel, 0.0)

        return self._check_for_error_code(wavelength, "GetWavelengthNum")

    @rpc_method
    def close(self) -> None:
        """Close the connection to the instrument hardware and release associated resources."""
        _logger.info("[%s] Closing connection to instrument", self._name)

        super().close()

    def _check_channel(self, channel: int) -> None:
        if not (0 < channel <= self.MAX_CHANNEL_NUMBER):
            raise QMI_InstrumentException(f"Channel number out of range: {channel}")

    def _check_for_error_code(self, value: float, method: str) -> float:
        if value > 0:
            return value

        err_msg = WS8_ERR(value) if value in [error.value for error in WS8_ERR] else str(value)

        _logger.warning("[%s] %s error: %s", self._name, method, err_msg)

        raise QMI_InstrumentException(f"Error received from library call '{method}': {err_msg}")
