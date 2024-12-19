""" QMI instrument driver for the High Finesse Wavemeter instrument.

The instrument driver makes use of the manufacturer provided software libraries, "libwlmData.so" for Linux OS,
or "wlmData.dll" for Windows, or "libwlmData.dylib" for MacOS.
Please find the licence terms for these files as well as further documentation on the manufacturer's website at
https://www.highfinesse.com/en/support/downloads.html.
This driver has been tested on the WS-6 model.
"""

import ctypes
import logging

import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.instruments.high_finesse.support import wlmConst
from qmi.instruments.high_finesse.support._library_wrapper import _LibWrapper, WlmGetErr

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class HighFinesse_Wlm(QMI_Instrument):
    """A network based driver for the High Finesse Wavelength meter.

    This driver automatically detects the platform of the client and will load the respective driver library
    (wlmData.dll for Windows, libwlmData.so for Linux, and libwlmData.dylib for MacOS). Make sure that the library is
    available on your system and that the wlmData.ini file contains the IP address of the server.
    """
    # TODO: This could set with GetChannelsCount call after super().open().
    MAX_CHANNEL_NUMBER = 8

    def __init__(self, context: QMI_Context, name: str) -> None:
        """Initialize the instrument driver.

        Parameters:
            context: QMI_Context object for the instrument driver.
            name:    Name for this instrument instance.
        """
        self._lib: _LibWrapper = _LibWrapper()
        super().__init__(context, name)

    def _check_channel(self, channel: int) -> None:
        """A method for checking the channel number.

        Raises:
            QMI_InstrumentException: In case of instrument error or channel out of range.
        """
        self._check_is_open()
        if not (0 < channel <= self.MAX_CHANNEL_NUMBER):
            raise QMI_InstrumentException(f"Channel number out of range: {channel}")

    def _check_for_error_code(self, value: float | int, method: str) -> float | int:
        """A method for checking error codes returned by the device.

        Parameters:
            value:  Value to check for an error code.
            method: The called method to check the value for.

        Returns:
            value:  If value is larger than 0, or NaN, it cannot be an error code but a result value.

        Raises:
            QMI_InstrumentException: If the value to check is an error code, raise.
        """
        # TODO: Expand in future also for other error types, which are call dependent. Now only WlmGetErr.
        if value > 0 or value is np.nan:
            return value

        i_val = int(value)
        err_msg = WlmGetErr(i_val) if i_val in [error.value for error in WlmGetErr] else str(value)
        _logger.error("[%s] %s error: %s", self._name, method, err_msg)

        raise QMI_InstrumentException(f"Error received from library call '{method}': {err_msg}")

    @rpc_method
    def open(self) -> None:
        _logger.debug("[%s] Opening connection to instrument", self._name)
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()

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
        self._check_is_open()
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
        version_str = self.get_version()
        model, version, revision = version_str[14:].split(".")[:3]
        return QMI_InstrumentIdentification(
            vendor="HighFinesse",
            model=f"WLM-{model}",
            serial=None,
            version=".".join([version, revision])
        )

    @rpc_method
    def get_operation_state(self) -> int:
        """Get the instrument operation state. Possible return values are:
        - 0 : cStop. Wlm active but stopped,
        - 1 : cAdjustment. Wlm active and program is adjusting,
        - 2 : cMeasurement. Wlm active and measuring, recording or replaying.

        Returns:
            op_state: The operation state integer.
        """
        self._check_is_open()
        op_state = self._lib.dll.GetOperationState(0)
        return op_state

    @rpc_method
    def get_frequency(self, channel: int) -> float:
        """Get the main results of the measurement of a specified signal.

        Parameters:
            channel: The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
                     option (MLC). For WLMs without these options 1 should be overhanded.

        Returns:
            frequency: The last measured frequency value in THz.

        Raises:
            QMI_InstrumentException: In case of instrument error.
        """
        _logger.debug("[%s] Getting frequency on channel %d", self._name, channel)
        self._check_channel(channel)

        frequency = self._lib.dll.GetFrequencyNum(channel, 0.0)

        return self._check_for_error_code(frequency, "GetFrequencyNum")

    @rpc_method
    def get_wavelength(self, channel: int) -> float:
        """Get the main results of the measurement of a specified signal.

        Parameters:
            channel: The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
                     option (MLC). For WLMs without these options 1 should be overhanded.

        Returns:
            wavelength: The last measured wavelength in nm.
        """
        _logger.debug("[%s] Getting wavelength on channel %d", self._name, channel)
        self._check_channel(channel)

        wavelength = self._lib.dll.GetWavelengthNum(channel, 0.0)

        return self._check_for_error_code(wavelength, "GetWavelengthNum")

    @rpc_method
    def get_power(self, channel: int) -> float:
        """Get the power of the current measurement shot of a specified signal.

        Parameters:
            channel: The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
                     option (MLC). For WLMs without these options 1 should be overhanded.

        Returns:
            power:   The power of the last measured cw or quasi cw signal in uW or the energy in uJ.
        """
        _logger.debug("[%s] Getting power on channel %d", self._name, channel)
        self._check_channel(channel)

        power = self._lib.dll.GetPowerNum(channel, 0.0)

        return self._check_for_error_code(power, "GetPowerNum")

    @rpc_method
    def set_data_pattern(self, index: int = 1, enable: bool = True) -> None:
        """Enable or disable a pattern index to export data from instrument.

        Parameters:
            index:  Index number for export control. Index values have the following meanings:
                    - 0 : cSignal1Interferometers. The array received by the Fizeau interferometers or
                      diffraction grating.
                    - 1 : cSignal1WideInterferometer. Additional long interferometer or grating array.
                    - 1 : cSignal1Grating. Only in Grating analyzing versions! The array received
                      by spectrum analysis (grating precision).
                    - 2 : cSignal2Interferometers. Only in Double Pulse versions! The array received by
                      the Fizeau interferometers for the 2nd pulse.
                    - 3 : cSignal2WideInterferometer. Only in Double Pulse versions! Additional long
                      interferometer array for 2nd pulse.

                    With SetAnalysis only the following value is possible (with LSA and resolver versions):
                    - 4 : cSignalAnalysis[X]. The [X] array[s] of the spectral analysis data.
                    - 5 : cSignalAnalysisY. The Y array of the spectral analysis data.

            enable: True to enable data pattern (default), False to disable.

        Raises:
            ValueError: With invalid index number.
        """
        if index not in range(6):
            raise ValueError(f"Invalid data pattern index number {index}")

        if enable:
            _logger.debug("[%s] Enabling data pattern with index %d", self._name, index)
            i_enable = wlmConst.cPatternEnable

        else:
            _logger.debug("[%s] Disabling data pattern with index %d", self._name, index)
            i_enable = wlmConst.cPatternDisable

        ret_val = self._lib.dll.SetPattern(index, i_enable)
        self._check_for_error_code(ret_val, "SetPattern")

    @rpc_method
    def get_data_pattern_data(
        self, channel: int, index: int, arr_size: int
    ) -> np.typing.NDArray[np.int16]:
        """Get data from the given data pattern. It must be set first with `set_data_pattern`.

        Parameters:
            channel:  The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
                      option (MLC). For WLMs without these options 1 should be overhanded.
            index:    Index number to get the data pattern from. Must be in range [0 .. 5]. See also 'set_data_pattern'.
            arr_size: A batch size for reading data pattern.

        Returns:
            pattern_array: Data array from the data pattern.

        Raises:
            ValueError: With invalid index number.
        """
        _logger.debug("[%s] Getting data pattern data on channel %d and index %i", self._name, channel, index)
        if index not in range(6):
            raise ValueError(f"Invalid data pattern index number {index}")

        self._check_channel(channel)
        pattern_array = np.zeros(arr_size, dtype=ctypes.c_short)
        c_short_ptr = ctypes.POINTER(ctypes.c_short)
        ret_val = self._lib.dll.GetPatternDataNum(channel, index, pattern_array.ctypes.data_as(c_short_ptr))
        if ret_val == 0:
            # The channel and/or index was not (correctly) enabled.
            _logger.debug("[%s] GetPatternDataNum error, perhaps SetPattern was not run first?", self._name)

        elif ret_val not in [0, 1]:
            # Return value is an error code.
            self._check_for_error_code(ret_val, "GetPatternDataNum")

        return pattern_array
