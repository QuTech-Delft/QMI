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
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
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

    For obtaining data and pattern arrays, according to documentation, the data type, size and location of the data
    should be known. Also, the data has to be 'uncovered' first. Otherwise, arrays will not be exported. For getting
    array data from analysis or grating mode, the respective mode must be active in the main program.
    When obtaining array data, the following commands should be deployed (order is not strict):
    ```python
    > wlm.set_pattern|analysis_data(<index>, True)  # <index> for pattern only
    > data_size = wlm.get_pattern|analysis_data_size()
    > array_size = wlm.get_pattern|analysis_array_size()
    > data = get_pattern_data(<channel: int | None>, index, data_size, array_size)  # pattern<num> data
    > data = get_wavelength_data(data_size, array_size)  # analysis data axis x
    > data = get_amplitude_data(data_size, array_size)  # analysis data axis y
    ```
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

    def _get_analysis_data(
            self, ordinate: str, data_size: int, array_size: int
    ) -> np.typing.NDArray[np.short | np.float32 | np.double]:
        """This function returns a copy of spectral analysis data as an array.

        Note that to get data exported from the instrument, the exporting must first be enabled with SetAnalysis.

        Parameters:
            ordinate:   To select if to get wavelength or amplitude array of the spectral data. Possible values are
                        'wl' and 'amp'.
            data_size:  Size of a data point.
            array_size: Data array size.

        Returns:
            analysis_data: An array of data of the given ordinate.
        """
        if ordinate.lower() == "wl":
            index = wlmConst.cSignalAnalysisX

        elif ordinate.lower() == "amp":
            index = wlmConst.cSignalAnalysisY

        else:
            raise QMI_UsageException("Analysis data can be only retrieved from x or y axis index.")

        if data_size == 2:
            data_array = np.zeros(array_size, dtype=ctypes.c_short)
            c_ptr = ctypes.POINTER(ctypes.c_short)
        elif data_size == 4:
            data_array = np.zeros(array_size, dtype=ctypes.c_float)
            c_ptr = ctypes.POINTER(ctypes.c_float)
        elif data_size == 8:
            data_array = np.zeros(array_size, dtype=ctypes.c_double)
            c_ptr = ctypes.POINTER(ctypes.c_double)
        else:
            raise QMI_InstrumentException(f"Got an unexpected analysis data size {data_size}")

        ret_val = self._lib.dll.GetAnalysisData(index, data_array.ctypes.data_as(c_ptr))
        if ret_val == 0:
            # The channel and/or index was not (correctly) enabled.
            _logger.debug("[%s] GetAnalysisData error, perhaps SetAnalysis was not run first?", self._name)

        else:
            self._check_for_error_code(ret_val, "GetAnalysisData")

        return data_array

    @rpc_method
    def open(self) -> None:
        _logger.debug("[%s] Opening connection to instrument", self._name)
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()

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
    def start_server(
            self,
            action: int = wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMWait,
            app_start: str | int = 0,
            version: str | int = 0,
            delay: int = 10_000,
            extra_ret: int = 0,
    ) -> bool:
        """Start the device server with given parameters, if it is not running already.

        Parameters:
            action:    This parameter determines whether the server is to be shown, hidden, started or terminated.
                       show and hide options can be combined with one of the following values in order to suppress
                       error and information messages::
                       - cCtrlWLMStart-Silent: On start no error and information messages will be displayed.
                       - cCtrlWLMSilent: Like the previous but suppresses error and information messages while running.
                       And with the ControlWLMEx function it additionally can be combined with the following value in
                       order to wait until the operation is finished::
                       - cCtrlWLMWait: Causes the call not to return until the operation is finished or the
                                       specified timeout (Delay parameter) has elapsed.
                       Default value is to hide and wait.
            app_start: If `action` is cCtrlWLMShow or CtrlWLMHide, it also is possible to start the server software
                       (or any other) with giving `app_start` as a pointer to a zero terminated file name string of a
                       certain executable file. Default is 0, i.e. detect automatically.
            version:   If `app_start` is 0, `version` can be used to give version number of the WLM or LSA. Default
                       is 0 which uses either last accessed | only active server or if no server is active, the last
                       _installed_ WLM or LSA is started, unless `action` was set to cCtrlWLMExit.
            delay:     If `action` has been set also with wait option, waits `delay` milliseconds(?), or until the
                       operation is complete, before continuing. Set to -1 for infinite delay. Default is 10000ms.
            extra_ret: Set to 1 to get extended return information when starting the WLM or LSA with show or hide, and
                       wait `action` options. Default is 0 (standard return information).

        Returns:
             True if the server was started, or False if already running.
        """
        self._check_is_open()
        wlm_count = self._lib.dll.GetWLMCount(0)
        _logger.info("[%s] Starting server, current wlm count = %d", self._name, wlm_count)
        if wlm_count == 0:
            if app_start and action not in (
                    wlmConst.cCtrlWLMShow, wlmConst.cCtrlWLMHide,
                    wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMWait,
                    wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMWait,
                    wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMSilent,
                    wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMSilent,
            ):
                _logger.warning("Cannot use 'app_start' if 'action' does not include cCtrlWLMShow or cCtrlWLMHide.")
                app_start = 0

            if version and app_start:
                _logger.warning("Cannot use 'version' if 'app_start' is not 0.")
                version = 0

            elif version and action == wlmConst.cCtrlWLMExit:
                _logger.warning("Cannot use 'version' if 'action' is cCtrlWLMExit.")
                version = 0

            if delay != 0 and action not in (
                    wlmConst.cCtrlWLMWait,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMShow,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMHide,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMSilent,
            ):
                _logger.warning("Cannot use 'delay' if 'action' does not include cCtrlWLMWait.")
                delay = 0

            if extra_ret and action not in (
                    wlmConst.cCtrlWLMShow, wlmConst.cCtrlWLMHide, wlmConst.cCtrlWLMWait,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMShow,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMHide,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMStartSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMShow | wlmConst.cCtrlWLMSilent,
                    wlmConst.cCtrlWLMWait | wlmConst.cCtrlWLMHide | wlmConst.cCtrlWLMSilent,
            ):
                _logger.warning("No extra return information can be given with 'action' {action}.")
                extra_ret = 0

            status = self._lib.dll.ControlWLMEx(action, app_start, version, delay, extra_ret)
            _logger.debug("[%s] Started server with status = %d", self._name, status)
            if status <= 0:
                self._check_for_error_code(status, "ControlWLMEx")

            return True

        return False

    @rpc_method
    def stop_server(self) -> None:
        """Stop the device server if it is running."""
        self._check_is_open()
        wlm_count = self._lib.dll.GetWLMCount(0)
        _logger.info("[%s] Stopping server, current wlm count = %d", self._name, wlm_count)
        if wlm_count > 0:
            status = self._lib.dll.Operation(wlmConst.cCtrlStopAll)
            _logger.debug("[%s] Stopped measurement with status = %d", self._name, status)
            status = self._lib.dll.ControlWLM(wlmConst.cCtrlWLMExit, 0, 0)
            _logger.debug("[%s] Stopped server with status = %d", self._name, status)

    @rpc_method
    def start_measurement(self) -> None:
        """Start measurement operation."""
        self._check_is_open()
        status = self._lib.dll.Operation(wlmConst.cCtrlStartMeasurement)
        _logger.debug("[%s] Started measurement with status = %d", self._name, status)
        self._check_for_error_code(status, "Operation")

    @rpc_method
    def stop_all(self) -> None:
        """Stop all operations."""
        self._check_is_open()
        status = self._lib.dll.Operation(wlmConst.cCtrlStopAll)
        _logger.debug("[%s] Started measurement with status = %d", self._name, status)
        self._check_for_error_code(status, "Operation")

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
    def calibrate(self, laser_type: int, unit: int, value: float, channel: int = 1):
        """Perform a WLM or LSA channel calibration based on a light of a reference source.
        The calibration only works if no measurement is active.

        Parameters:
            laser_type: "cHeNe633", red HeNe laser; the allowed wavelength range is 632.99 to 632.993 nm.
                        "cNeL", shipped neon lamp. This option is available only with Laser Spectrum
                                Analysers and WS/5, WS/6 and some WS/7 Wavelength Meters.
                        "cOther", any other stabilized reference single mode laser. This option is available
                        only with WS/7, WS/Ultimate and modern WS/5 and WS/6 Wavelength
                        Meters. The allowed calibration wavelength range is::
                          - 450 to 0900 nm with standard and UV Wavelength Meters
                          - 600 to 1750 nm with IR Wavelength Meters
                          - 632 to 2000 nm with IR2 Wavelength Meters
                        "cFreeHeNe", a free running red HeNe laser. This option is available only with WS/7
                        Wavelength Meters. The needed calibration wavelength is a distinctive value
                        for the special laser, it is published with the laser if the option is purchased.
            unit:       The physical unit which the Value parameter is interpreted in. Available are
                        cReturnWavelengthVac, cReturnWavelengthAir, cReturnFrequency,
                        cReturnWavenumber and cReturnPhotonEnergy.
            value:      The wavelength, frequency or energy value the calibration is performed on. This value must
                        match the connected laser and is interpreted in the unit of the Unit parameter above.
            channel:    The switch (multiplexer) channel used for calibration with versions which dispose of the switch
                        option (Note: With channels other than 1, the switch mode must be set in advance.). With
                        Wavelength Meters or Laser Spectrum Analysers without fiber switch option, 1 must be used here.
        """
        self._check_is_open()
        if laser_type not in (wlmConst.cHeNe633, wlmConst.cNeL, wlmConst.cOther, wlmConst.cFreeHeNe):
            raise QMI_UsageException(f"Invalid laser type {laser_type}.")

        if unit not in range(5):
            raise QMI_UsageException(f"Invalid physical unit {unit}.")

        self._check_channel(channel)

        ret_val = self._lib.dll.Calibration(laser_type, unit, value, channel)
        self._check_for_error_code(ret_val, "Calibration")

    @rpc_method
    def get_auto_calibration_mode(self) -> bool:
        """Get the current auto calibration mode parameter.

        Returns:
            boolean: True if auto calibration mode is on, else False.
        """
        self._check_is_open()

        ret_val = self._lib.dll.GetAutoCalMode(0)
        if ret_val not in [0, 1]:
            self._check_for_error_code(ret_val, "GetAutoCalMode")

        return bool(ret_val)

    @rpc_method
    def set_auto_calibration_mode(self, mode: bool) -> None:
        """Set auto calibration mode parameter.

        Parameters:
            mode: True if auto calibration mode is to be set on, else False.
        """
        self._check_is_open()

        ret_val = self._lib.dll.SetAutoCalMode(int(mode))
        self._check_for_error_code(ret_val, "SetAutoCalMode")

    @rpc_method
    def get_auto_calibration_settings(self) -> tuple[int, str]:
        """Get the auto calibration settings.

        Returns:
            period:   The calibration period value.
            unit_str: The unit of the calibration period value.
        """
        period = ctypes.POINTER(ctypes.c_long)
        unit = ctypes.POINTER(ctypes.c_long)
        # First use the call to set period
        ret_val = self._lib.dll.GetAutoCalSetting(wlmConst.cmiAutoCalPeriod, period, 0, 0)
        self._check_for_error_code(ret_val, "GetAutoCalSetting")
        # Then use the call to set unit
        ret_val = self._lib.dll.GetAutoCalSetting(wlmConst.cmiAutoCalUnit, unit, 0, 0)
        self._check_for_error_code(ret_val, "GetAutoCalSetting")
        # Handle the values returned from pointers
        unit_str = "once on start"
        if unit.value == wlmConst.cACOnceOnStart:
            period.value = 1  # The value is now meaningless, so set it to return 1

        elif unit.value == wlmConst.cACMeasurements:
            unit_str = "measurements"

        elif unit.value == wlmConst.cACDays:
            unit_str = "days"

        elif unit.value == wlmConst.cACHours:
            unit_str = "hours"

        elif unit.value == wlmConst.cACMinutes:
            unit_str = "minutes"

        return period.value, unit_str

    @rpc_method
    def set_auto_calibration_settings(self, period: int, unit: str) -> None:
        """Set the auto calibration settings.

        Parameters:
            period: The calibration period value.
            unit:   The unit of the calibration period value.
        """
        unit_int = wlmConst.cACOnceOnStart
        if unit.lower() == "measurements":
            unit_int = wlmConst.cACMeasurements

        elif unit.lower() == "days":
            unit_int = wlmConst.cACDays

        elif unit.lower() == "hours":
            unit_int = wlmConst.cACHours

        elif unit.lower() == "minutes":
            unit_int = wlmConst.cACMinutes

        # First use the call to set period
        ret_val = self._lib.dll.SetAutoCalSetting(wlmConst.cmiAutoCalPeriod, period, 0, 0)
        self._check_for_error_code(ret_val, "SetAutoCalSetting")
        # Then use the call to set unit
        ret_val = self._lib.dll.SetAutoCalSetting(wlmConst.cmiAutoCalUnit, unit_int, 0, 0)
        self._check_for_error_code(ret_val, "SetAutoCalSetting")

    @rpc_method
    def get_active_channel(self, mode: int) -> str | int:
        """Returns the currently active measurement channel number in given mode.
        NOTE:: A builtin neon lamp channel is treated like a rear port.

        Parameters:
            mode: Controls the interpretation of the return value. Following values are possible::
                    1. The channel is given in serial order, simply in the return value. This order is, first all
                        channels at the front port and appended all channels at the rear port (if any).
                    2. The channel is given in separated order. The low word of the return value contains the
                        channel number related to the specific port, the high order word contains the port
                        number, 1 for the front, 2 for the rear port.
                    3. The channel is given in separated order. The return value contains the channel number
                        related to the specific port and the port parameter contains the port number.

        Returns:
            channel: The channel number in mode 1, or a channel string indicating "front" or "rear" port
                      with "F" or "R", respectively, followed by the channel number.
        """
        port = ctypes.POINTER(ctypes.c_long)
        ret_val = self._lib.dll.GetActiveChannel(mode, port, 0)
        self._check_for_error_code(ret_val, "GetActiveChannel")

        if mode == 3:
            port_str = "F" if port.value == 1 else "R"
            return f"{port_str}{ret_val}"

        elif mode == 2:
            high_word = (ret_val >> 16)
            low_word = (ret_val & 0xFFFF)
            if high_word not in (1, 2):
                raise ValueError(f"Unexpected port value {high_word}")

            if low_word not in range(1, self.MAX_CHANNEL_NUMBER + 1):
                raise ValueError(f"Unexpected channel number {low_word}")

            port_str = "F" if high_word == 1 else "R"
            return f"{port_str}{low_word}"

        return ret_val

    @rpc_method
    def set_active_channel(self, channel: int, mode: int = 1, port: str = "F") -> None:
        """Set the currently active measurement channel in non-switch mode.
        NOTE:: A builtin neon lamp channel is treated like a rear port.

        Parameters:
            channel: The channel number.
            mode:    Controls the interpretation of the return value. Following values are possible::
                       1. The channel needs to be given in serial order in the CH parameter. This order is, first all
                          channels at the front port and appended all channels at the rear port (if any). Default.
                       2. The channel is given in separated order. The low word of the CH parameter must
                          contain the channel number related to the specific port, the high order word the port
                          number, 1 for the front, 2 for the rear port.
                       3. The channel again is treated in separated order. Overhand the channel number related
                          to the specific port in the CH parameter and the front or rear port in the Port parameter,
                          1 for the front, 2 for the rear port.
            port:    If you have set Mode to 3, indicate the port here: "F" for the front (default),
                     "R" for the rear port.
        """
        self._check_channel(channel)  # TODO: We need an advanced check for different modes.
        if mode not in (1, 2, 3):
            raise ValueError(f"Invalid mode: {mode}")

        if port.upper() not in ("F", "R"):
            raise ValueError(f"Invalid port: {port}")

        port_int = 1 if port.upper() == "F" else 2
        # TODO: should port_int be 0 if 'mode' is not 3?
        ret_val = self._lib.dll.SetActiveChannel(mode, port_int, channel, 0)
        self._check_for_error_code(ret_val, "SetActiveChannel")

    @rpc_method
    def get_switcher_mode(self) -> int:
        """Returns the current switcher mode of the optional multichannel switch.

        Returns:
            mode: The switcher mode.
        """
        ret_val = self._lib.dll.GetSwitcherMode(0)
        if ret_val < 0:
            # Return value is an error code.
            self._check_for_error_code(ret_val, "GetSwitcherMode")

        return ret_val

    @rpc_method
    def set_switcher_mode(self, mode: int) -> None:
        """Set the mode of the optional multichannel switch on or off.

        Parameters:
            mode: New mode value. must be 0 (off) or 1 (on).

        Raises:
            ValueError: If the new mode value is not valid (0 or 1).
        """
        if mode not in (0, 1):
            raise ValueError(f"Switch mode must be 0 or 1. Not {mode}")

        ret_val = self._lib.dll.SetSwitcherMode(mode)
        # Return value is an error code.
        self._check_for_error_code(ret_val, "SetSwitcherMode")

    @rpc_method
    def get_switcher_channel(self) -> int:
        """Returns the currently active (signal) channel of the optional multichannel switch.

        Returns:
            channel: The switcher channel number.
        """
        ret_val = self._lib.dll.GetSwitcherChannel(0)
        return self._check_for_error_code(ret_val, "GetSwitcherChannel")

    @rpc_method
    def set_switcher_channel(self, channel: int) -> None:
        """Set the currently active (signal) channel of the optional multichannel switch in non-switch mode.

        Parameters:
            channel: The channel number.
        """
        self._check_channel(channel)
        ret_val = self._lib.dll.SetSwitcherChannel(channel)
        self._check_for_error_code(ret_val, "SetSwitcherChannel")

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
    def get_analysis_data_size(self) -> int:
        """Obtain the analysis data point size. Successful inquiry should return value
        2, 4 or 8, referring to a short integer, floating point or double precision data.
        Note that this value does not change during a measurement.

        Returns:
            data_size: The returned data size.
        """
        data_size = self._lib.dll.GetAnalysisItemSize(wlmConst.cSignalAnalysis)
        return self._check_for_error_code(data_size, "GetAnalysisItemSize")

    @rpc_method
    def get_analysis_array_size(self) -> int:
        """Obtain the analysis data array size.
        Note that this value does not change during a measurement.

        Returns:
            array_size: How many data points can be exported in a data array.
        """
        array_size = self._lib.dll.GetAnalysisItemCount(wlmConst.cSignalAnalysis)
        return self._check_for_error_code(array_size, "GetAnalysisItemCount")

    @rpc_method
    def set_analysis_data(self, enable: bool) -> None:
        """Set if analysis array is to be exported. This should be set as true to enable exporting analysis data
        to an array."""
        state = wlmConst.cAnalysisEnable if enable else wlmConst.cAnalysisDisable
        ret_val = self._lib.dll.SetAnalysis(wlmConst.cSignalAnalysis, state)
        self._check_for_error_code(ret_val, "SetAnalysis")

    @rpc_method
    def get_wavelength_data_location(self) -> int:
        """Get the memory start location of the wavelength data."""
        location = self._lib.dll.GetAnalysis(wlmConst.cSignalAnalysisX)
        return self._check_for_error_code(location, "GetAnalysis")

    @rpc_method
    def get_amplitude_data_location(self) -> int:
        """Get the memory start location of the amplitude data."""
        location = self._lib.dll.GetAnalysis(wlmConst.cSignalAnalysisY)
        return self._check_for_error_code(location, "GetAnalysis")

    @rpc_method
    def get_wavelength_data(
            self, data_size: int, array_size: int
    ) -> np.typing.NDArray[np.short | np.float32 | np.double]:
        """This function returns a copy of spectral analysis wavelength data as an array."""
        return self._get_analysis_data("wl", data_size, array_size)
        
    @rpc_method
    def get_amplitude_data(
        self, data_size: int, array_size: int
    ) -> np.typing.NDArray[np.short | np.float32 | np.double]:
        """This function returns a copy of spectral analysis amplitude data as an array."""
        return self._get_analysis_data("amp", data_size, array_size)

    @rpc_method
    def get_pattern_data_size(self) -> int:
        """Obtain the pattern data point size. Successful inquiry should return value
        2, 4 or 8, referring to a short integer, long integer or double precision data.
        Note that this value does not change during a measurement.

        Returns:
            data_size: The returned data size.
        """
        data_size = self._lib.dll.GetPatternItemSize(wlmConst.cSignalAnalysis)
        return self._check_for_error_code(data_size, "GetPatternItemSize")

    @rpc_method
    def get_pattern_array_size(self) -> int:
        """Obtain the pattern data array size.
        Note that this value does not change during a measurement.

        Returns:
            array_size: How many data points can be exported in a data array.
        """
        array_size = self._lib.dll.GetPatternItemCount(wlmConst.cSignalAnalysis)
        return self._check_for_error_code(array_size, "GetPatternItemCount")

    @rpc_method
    def set_pattern_data(self, index: int = 1, enable: bool = True) -> None:
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
            enable: True to enable data pattern (default), False to disable.

        Raises:
            ValueError: With invalid index number.
        """
        if index not in range(4):
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
    def get_pattern_location(self, channel: int | None, index: int) -> int:
        """Get the memory location of an exported array.

        Parameters:
            channel: The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
                     option (MLC). For WLMs without these options 1 should be overhanded.
            index:   Array identifier index. See 'set_data_pattern' for possible values.

        Returns:
            location: The pattern memory location.
        """
        if index not in range(4):
            raise ValueError(f"Invalid data pattern index number {index}")

        if channel is None:
            location = self._lib.dll.GetPattern(index)
            return self._check_for_error_code(location, "GetPattern")

        else:
            self._check_channel(channel)
            location = self._lib.dll.GetPatternNum(channel, index)
            return self._check_for_error_code(location, "GetPatternNum")

    @rpc_method
    def get_pattern_data(
        self, channel: int | None, index: int, data_size: int, array_size: int
    ) -> np.typing.NDArray[np.short | np.long | np.double]:
        """Get data from the given data pattern. It must be set first with `set_data_pattern`.

        Parameters:
            channel:    The signal number (1 to 8) in case of a WLM with multichannel switch or with double pulse
                        option (MLC). For WLMs without these options 1 should be overhanded.
            index:      Index number to get the data pattern from. See 'set_data_pattern' for definitions.
            data_size:  Size of a data point.
            array_size: Data array size.

        Returns:
            pattern_array: Data array from the data pattern.

        Raises:
            ValueError: With invalid index number.
        """
        _logger.debug("[%s] Getting data pattern data on channel %d and index %i", self._name, channel, index)
        if index not in range(4):
            raise ValueError(f"Invalid data pattern index number {index}")

        if data_size == 2:
            pattern_array = np.zeros(array_size, dtype=ctypes.c_short)
            c_ptr = ctypes.POINTER(ctypes.c_short)
        elif data_size == 4:
            pattern_array = np.zeros(array_size, dtype=ctypes.c_long)
            c_ptr = ctypes.POINTER(ctypes.c_long)
        elif data_size == 8:
            pattern_array = np.zeros(array_size, dtype=ctypes.c_double)
            c_ptr = ctypes.POINTER(ctypes.c_double)
        else:
            raise QMI_InstrumentException(f"Got an unexpected pattern data size {data_size}")

        if channel is None:
            ret_val = self._lib.dll.GetPatternData(index, pattern_array.ctypes.data_as(c_ptr))
            func = "GetPatternData"
        else:
            self._check_channel(channel)
            ret_val = self._lib.dll.GetPatternDataNum(channel, index, pattern_array.ctypes.data_as(c_ptr))
            func = "GetPatternDataNum"

        if ret_val == 0:
            # The channel and/or index was not (correctly) enabled.
            _logger.debug("[%s] %s error, perhaps SetPattern was not run first?", self._name, func)

        elif ret_val not in [0, 1]:
            # Return value is an error code.
            self._check_for_error_code(ret_val, func)

        return pattern_array
