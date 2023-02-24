"""Instrument driver for the JPE CPSC piezo stage controller."""

import logging
import os
import sys
from subprocess import PIPE, CompletedProcess, Popen, run
from typing import Any, List, Optional, Iterable, NamedTuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class StatusPositionControl(NamedTuple):
    """A named tuple with status and position error information."""
    ENABLED: int
    FINISHED: int
    INVALID_SP1: int
    INVALID_SP2: int
    INVALID_SP3: int
    POS_ERROR1: int
    POS_ERROR2: int
    POS_ERROR3: int


class JPE_CPSC(QMI_Instrument):
    """Instrument driver for the JPE CPSC piezo stage controller.

    Note that the piezo stage controller will only hold its actuator positions
    while the connection to the instrument is open. Closing the connection
    will automatically return the controller to its free state.

    This driver communicates with the piezo stage controller via
    a helper program "cacli.exe".

    The helper program is a command-line Windows application.
    On Linux, it can run under Wine.
    """

    # Location of cpsc program.
    DEFAULT_CPSC_DIR = "C:\\HardwareControl\\CPSC_v7.3.20201222"

    CPSC_CMD = "cacli.exe"

    # USD vendor ID : product ID of the piezo stage controller.
    USB_ID = "045E:FFFF"

    def __init__(self, context: QMI_Context, name: str, serial_number: str, cpsp_dir: str = DEFAULT_CPSC_DIR) -> None:
        """Initialize the driver.

        Arguments:
            name: Name for this instrument instance.
            serial_number: Serial number of the controller.
            cpsp_dir: Path to directory where cacli.exe is installed.

        Raises:
            QMI_InstrumentException: If the CPSC program directory {cpsp_dir} is not found
        """
        if not os.path.isdir(cpsp_dir):
            raise QMI_InstrumentException(f"CPSC program directory {cpsp_dir} not found")
        super().__init__(context, name)
        if serial_number.startswith("@"):
            self._serial_number = serial_number

        else:
            self._serial_number = "@" + serial_number

        self._cpsp_dir = cpsp_dir
        self._cpsp_cmd = os.path.join(cpsp_dir, self.CPSC_CMD)
        self._proc_popen = None  # type: Optional[Popen]
        self._proc_run = None  # type: Optional[CompletedProcess]
        self._version_string = ""

    def _start_helper_wine(self) -> None:
        """Start the WinE. WARNING: NOT TESTED WITH HARDWARE!"""
        assert self._proc_popen is None
        env: dict = {}
        env.update(os.environ)
        env["WINEDLLPATH"] = "."
        env["FTDID"] = self.USB_ID
        self._proc_popen = Popen(args="wine", stdin=PIPE, stdout=PIPE, cwd=self._cpsp_dir, env=env)
        assert self._proc_popen.stdin is not None
        assert self._proc_popen.stdout is not None

    def _stop_helper(self) -> None:
        """Stop the helper program."""
        assert self._proc_popen is not None
        assert self._proc_popen.stdin is not None
        assert self._proc_popen.stdout is not None
        self._proc_popen.stdin.close()
        self._proc_popen.wait()
        self._proc_popen.stdout.close()
        self._proc_popen = None
        self._version_string = ""

    def _send_cmd(self, cmd: str, args: Optional[Iterable] = None) -> None:
        """Send command to helper program and check response.

        Arguments:
            cmd: The protocol command to send (without serial number)
            args: A list of input parameters. Can be in any format that can be cast as string.
        """
        if args:
            _logger.debug("Sending command {} with args {} to JPE CPSC {}".format(
                self._name, ",".join(map(str, args)), self._serial_number)
            )

        else:
            _logger.debug("Sending command {} without arguments to JPE CPSC {}".format(
                self._name, self._serial_number)
            )

        if sys.platform.startswith("linux"):
            assert self._proc_popen is not None
            assert self._proc_popen.stdin is not None
            # Add serial number at the start
            cmd = self._cpsp_cmd + " " + self._serial_number + " " + cmd
            if args:
                for arg in args:
                    cmd += " " + str(arg)

            self._proc_popen.stdin.write(cmd.encode("ascii") + b"\r\n")
            self._proc_popen.stdin.flush()

        elif sys.platform == "darwin":
            raise QMI_UsageException("Mac OS X not supported.")

        else:
            # We need to make argument list. Start with exe, then serial number followed by command and args
            arg_list = [self._cpsp_cmd, self._serial_number, cmd]
            if args:
                for arg in args:
                    arg_list.append(str(arg))

            self._proc_run = run(arg_list, stdin=PIPE, stdout=PIPE, encoding="utf-8", check=False)

    def _recv_response(self) -> str:
        """Read response from helper program.

        Raises:
            QMI_InstrumentException: If one of the read stdout lines is unexpectedly empty or None.
        """
        s: str = ""
        if sys.platform.startswith("linux"):
            assert self._proc_popen is not None
            assert self._proc_popen.stdout is not None
            lines = self._proc_popen.stdout.readlines()
            _logger.debug("recv: {}".format(lines))
            for line in lines:
                if not line:
                    raise QMI_InstrumentException("Unexpected end of input from helper program")

                line = line.decode()
                s += line

        else:
            s = self._proc_run.stdout  # type: ignore

        _logger.debug("Received response {} from JPE CPSC {}".format(s, self._serial_number))
        return s

    def _check_response(self, expected: str) -> None:
        """Check the obtained response against expected response.

        Arguments:
             expected: The expected response string.

        Raises:
            QMI_InstrumentException: If response start with "ERROR" message or response does not hold
            the expected string.
        """
        s = self._recv_response()
        if expected in s:
            return

        elif s.startswith("ERROR"):
            raise QMI_InstrumentException(f"Error from {self._name}: {s}")

        else:
            raise QMI_InstrumentException(f"Unexpected response from {self._name}: {s}. Expected {expected}")

    def _get_cli_version(self) -> str:
        """Get CLI version number.

        Returns:
            Response to the query as string.
        """
        self._send_cmd("/VER")
        return self._recv_response()

    @rpc_method
    def open(self) -> None:
        """The 'open()' function override. Starts the correct os-specific helper program."""
        self._check_is_closed()

        if sys.platform.startswith("linux"):  # TODO: Test with hardware on Linux if this really works.
            _logger.info("[%s] Starting helper program", self._name)
            self._start_helper_wine()

        super().open()

    @rpc_method
    def close(self) -> None:
        """The 'close()' function override. Stops the helper program and closes the instrument."""
        self._check_is_open()
        if sys.platform.startswith("linux"):
            _logger.info("[%s] Stopping helper program", self._name)
            self._stop_helper()

        _logger.info("[%s] the instrument", self._name)
        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version.

        Returns:
            QMI_InstrumentIdentification instance.
        """
        self._check_is_open()
        self._version_string = self._get_cli_version()
        return QMI_InstrumentIdentification(
            vendor="JPE", model="CPSC", serial=self._serial_number, version=self._version_string
        )

    @rpc_method
    def get_info_all_modules(self) -> List[str]:
        """Get information about installed modules.

        Returns:
            modlist: Listing of module info
        """
        self._check_is_open()
        self._send_cmd("MODLIST")
        modlist = self._recv_response().split(",")
        return modlist

    @rpc_method
    def get_info_module(self, address: int) -> str:
        """Get information about given module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
        Returns:
            info string about given module
        """
        self._check_is_open()
        self._send_cmd("Desc", [address])
        return self._recv_response().strip()

    @rpc_method
    def request_fail_safe_state(self, address: int) -> str:
        """Reguest fail-safe state from a specific module. In practice - check for errors.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.

        Returns:
            the response error code string
        """
        self._check_is_open()
        self._send_cmd("GFS", [address])
        return self._recv_response().strip()

    @rpc_method
    def move(
            self,
            address: int,
            direction: int,
            freq: int = 10,
            rss: int = 100,
            steps: int = 0,
            temp: int = 295,
            stage: str = "CBS10-RLS",
            df: float = 1.0,
    ) -> None:
        """Move an actuator with specific parameters

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            direction: 0 to 1. Direction of movement: set to 1 for positive movement and 0 (zero) for
                    negative movement
            freq: 1 to 600 Step frequency input. Value is in Hertz [Hz] (numerical values only).
            rss: 1 to 100 (Relative) actuator step size parameter input. Value is a percentage [%]
                    (numerical values only)
            steps: 0 to 50000 Number of actuation steps. Range 0 to 50000, where 0 is used for
                        infinite move (use STP command to stop actuator movement).
            temp: 0 to 300 Set this parameter to the temperature of the environment in which the
                    actuator is used. Input is in Kelvin [K] (numerical values only).
            stage: Sets specific internal drive parameters for the type of actuator or system
                        attached to that particular channel of that particular module set by [ADDR] and [CH].
            df: Optional[float] - 0.1 to 3.0 Drive factor (numerical values only). In normal operating conditions,
                    set this value to 1 (or 1.0).
        """
        self._check_is_open()
        args: List[Any] = [address, direction, freq, rss, steps, temp, stage, df]

        self._send_cmd("MOV", args)
        self._check_response("Actuating the stage.")

    @rpc_method
    def stop(self, address: int) -> None:
        """Stops movement of an actuator (MOV command), disables external input mode (EXT command) or disables
        scan mode (SDC command).

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
        """
        self._check_is_open()
        self._send_cmd("STP", [address])
        self._check_response("Stopping the stage.")

    @rpc_method
    def enable_scan_mode(self, address: int, value: int) -> None:
        """Enables and sets the scan mode for CADM2.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            value: A numerical value in between 0 and 1023 (10-bit value) where zero represents ~0[V] output
         (-30[V] in respect to REF) and the maximum value represents ~150[V] output (+120[V] in respect to REF).
        """
        self._check_is_open()
        self._send_cmd("SDC", [address, value])
        self._check_response("Scan mode enabled.")

    @rpc_method
    def use_external_input(
            self,
            address: int,
            direction: int,
            freq: int = 10,
            rss: int = 100,
            temp: int = 295,
            stage: str = "CBS10-RLS",
            df: float = 1.0,
    ) -> None:
        """To use the CADM2 in Flexdrive mode, it is required to set the module in external (analog) input mode
        prior to using Flexdrive.

        Arguments:
             address: 1 to 6. Address of module corresponding to controller slot.
             direction: 0 to 1. Direction of movement: set to 1 for positive movement and 0 (zero) for
                    negative movement
             freq: 1 to 600 Step frequency input. Value is in Hertz [Hz] (numerical values only).
             rss: 1 to 100 (Relative) actuator step size parameter input. Value is a percentage [%]
                    (numerical values only)
             temp: 0 to 300 Set this parameter to the temperature of the environment in which the
                    actuator is used. Input is in Kelvin [K] (numerical values only).
             stage:  Sets specific internal drive parameters for the type of actuator or system
                        attached to that particular channel of that particular module set by [ADDR] and [CH].
             df: 0.1 to 3.0 Drive factor (numerical values only). In normal operating conditions, set
                    this value to 1 (or 1.0).
        """
        self._check_is_open()
        args = []
        for arg in [address, direction, freq, rss, temp, stage, df]:
            if not isinstance(arg, type(None)):
                args.append(arg)

        self._send_cmd("EXT", args)
        self._check_response("External mode enabled.")

    @rpc_method
    def get_current_position(self, address: int, chan: int, stage: str = "CBS10-RLS") -> float:
        """Get current position of a Resistive Linear Sensor (RLS) connected to a specific channel [CH] of the RSM
        module.
        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            stage: stage name, e.g. "CLA2601", default "CBS10-RLS".
        Raises:
            QMI_InstrumentException: If the response cannot be cast into a float.
        Returns:
            cur_pos: Current position in [m].
        """
        self._check_is_open()
        self._send_cmd("PGV", [address, chan, stage])
        response = self._recv_response().strip()
        try:
            cur_pos = float(response)

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from position query SDC {address} {chan} {stage}: {response}"
            ) from exc

        return cur_pos

    @rpc_method
    def get_current_position_of_all_3_channels(self, address: int, stage: str = "CBS10-RLS") -> List[float]:
        """Get current position of all three channels of the RSM module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            stage: stage name, e.g. "CLA2601", default "CBS10-RLS".
        Raises:
            QMI_InstrumentException: If (one of the) response entries cannot be cast into a float.
        Returns:
            cur_pos: current positions in [m].
        """
        self._check_is_open()
        cur_pos = []
        self._send_cmd("PGVA", [address, stage, stage, stage])
        response = self._recv_response().strip()
        try:
            for rspv in response.split(","):
                cur_pos.append(float(rspv))

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from position query PGVA {address} {stage}: {response}"
            ) from exc

        return cur_pos

    @rpc_method
    def set_negative_end_stop(self, address: int, chan: int) -> None:
        """Set the current position of a Resistive Linear Sensor (RLS) connected to channel [CH] of the RSM to be
        the negative end-stop.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        """
        self._check_is_open()
        self._send_cmd("MIS", [address, chan])
        self._check_response("Minimum position set.")

    @rpc_method
    def set_positive_end_stop(self, address: int, chan: int) -> None:
        """Set the current position of a Resistive Linear Sensor (RLS) connected to channel [CH] of the RSM to be
        the positive end-stop.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        """
        self._check_is_open()
        self._send_cmd("MAS", [address, chan])
        self._check_response("Maximum position set.")

    @rpc_method
    def read_negative_end_stop(self, address: int, chan: int, stage: str = "CBS10-RLS") -> float:
        """Read the current value of the negative end-stop parameter set for a specific channel [CH] of an RSM.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            stage: Stage name, e.g. "CLA2601", default "CBS10-RLS".
        Raises:
            QMI_InstrumentException: If the response cannot be cast into a float.
        Returns:
            cur_val: The current value of the parameter in [m].
        """
        self._check_is_open()
        self._send_cmd("MIR", [address, chan, stage])
        response = self._recv_response().strip()
        try:
            cur_val = float(response)

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from end-stop query MIR {address} {chan} {stage}: {response}"
            ) from exc

        return cur_val

    @rpc_method
    def read_positive_end_stop(self, address: int, chan: int, stage: str = "CBS10-RLS") -> float:
        """Read the current value of the positive end-stop parameter set for a specific channel [CH] of an RSM.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            stage: stage name, e.g. "CLA2601", default "CBS10-RLS".
        Raises:
            QMI_InstrumentException: If the response cannot be cast into a float.
        Returns:
            cur_val: the current value of the parameter in [m].
        """
        self._check_is_open()
        self._send_cmd("MAR", [address, chan, stage])
        response = self._recv_response().strip()
        try:
            cur_val = float(response)

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from end-stop query MAR {address} {chan} {stage}: {response}"
            ) from exc

        return cur_val

    @rpc_method
    def reset_end_stops(self, address: int, chan: int):
        """Reset the current values of the negative and positive end-stop parameters set for a specific channel [CH]
        of an RSM.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        """
        self._check_is_open()
        self._send_cmd("MMR", [address, chan])
        self._check_response("Minimum and maximum end-stops reset.")

    @rpc_method
    def set_excitation_duty_cycle(self, address: int, duty: int) -> None:
        """Set the duty cycle of the sensor excitation signal of the RSM.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            duty: Value is in [%] and can be set to 0 (zero) or from 10 to (default) 100.
        """
        self._check_is_open()
        self._send_cmd("EXS", [address, duty])
        self._check_response("Excitation duty cycle set.")

    @rpc_method
    def read_excitation_duty_cycle(self, address: int) -> int:
        """Read the duty cycle of the sensor excitation signal of the RSM.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
        Raises:
            QMI_InstrumentException: If the response cannot be cast into an int.
        Returns:
            cur_val: Response value is in [%].
        """
        self._check_is_open()
        self._send_cmd("EXR", [address])
        response = self._recv_response().strip()
        try:
            cur_val = int(response)

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from excitation duty cycle query EXR {address}: {response}"
            ) from exc

        return cur_val

    @rpc_method
    def save_rsm_settings(self, address: int) -> None:
        """Store the current values of the following parameters of the RSM to the non-volatile memory of the
        controller: excitation duty cycle (EXS), negative end stop (MIS) and positive end-stop (MAS).

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
        """
        self._check_is_open()
        self._send_cmd("RSS", [address])
        self._check_response("Settings stored in flash.")

    @rpc_method
    def get_current_counter_value(self, address: int, chan: int) -> int:
        """Request the counter valuea of a Cryo Optical Encoder (COE) connected to a specific channel [CH] of the
        OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        Raises:
            QMI_InstrumentException: If the response cannot be cast into an int.
        Returns:
            cur_val: Response value is in [counter ticks].
        """
        self._check_is_open()
        self._send_cmd("CGV", [address, chan])
        response = self._recv_response().strip()
        try:
            cur_val = int(response)

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from current counter value query CGV {address} {chan}: {response}"
            ) from exc

        return cur_val

    @rpc_method
    def reset_counter_value(self, address: int, chan: int) -> None:
        """Resets the counter (to zero) for a specific cryo optical encoder connected to a specific channel [CH] of
        the OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        """
        self._check_is_open()
        self._send_cmd("CSZ", [address, chan])
        self._check_response("Position counter set to 0.")

    @rpc_method
    def get_current_encoder_signal_value(self, address: int, chan: int) -> int:
        """Request the (raw) encoder signal value of a Cryo Optical Encoder (COE) connected to a specific channel
        [CH] of the OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        Raises:
            QMI_InstrumentException: If the response cannot be cast into an int.
        Returns:
            cur_val: Return value is a (unitless) number between [0] and [255].
        """
        self._check_is_open()
        self._send_cmd("DGV", [address, chan])
        response = self._recv_response().strip()
        try:
            cur_val = int(response)

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from current encoder signal value query DGV {address} {chan}: {response}"
            ) from exc

        return cur_val

    @rpc_method
    def auto_oem_calibration(self, address: int, chan: int, cadm2_address: int, temp: int, stage: str = "CBS10-RLS")\
            -> None:
        """Command to initiate an automatic calibration procedure for a specific encoder connected to channel
        [CH] of an OEM2.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            cadm2_address: 1 to 6. Address of module corresponding to CADM2 slot.
            temp: 0 to 300 Set this parameter to the temperature of the environment in which the
                    actuator is used. Input is in Kelvin [K] (numerical values only).
            stage: stage name, e.g. "CLA2601", default "CBS10-RLS".
        """
        self._check_is_open()
        self._send_cmd("OEMC", [address, chan, cadm2_address, temp, stage])
        self._check_response("Channel calibrated.")

    @rpc_method
    def request_calibration_values(self, address: int, chan: int) -> List[int]:
        """Request the Detector Gain setting [GAIN], Upper Threshold value [UT] and Lower Threshold value [LT]
        set to a specific channel [CH] of the OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
        Raises:
            QMI_InstrumentException: If (one of the) response entries cannot be cast into an int.
        Returns:
            cal_vals: Three values in between [1] and [255].
        """
        self._check_is_open()
        cal_vals = []
        self._send_cmd("MLS", [address, chan])
        response = self._recv_response().strip()
        try:
            for rspv in response.split(","):
                cal_vals.append(int(rspv))

        except Exception as exc:
            raise QMI_InstrumentException(
                f"Erroneous response from calibration value query MLS {address} {chan}: {response}"
            ) from exc

        return cal_vals

    @rpc_method
    def set_detector_gain(self, address: int, chan: int, gain: int) -> None:
        """Set a Detector Gain [GAIN] for a specific channel [CH] of the OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            gain: a value in between [1] and [255].
        """
        self._check_is_open()
        self._send_cmd("DSG", [address, chan, gain])
        self._check_response("Detector gain set.")

    @rpc_method
    def set_upper_threshold(self, address: int, chan: int, ut: int) -> None:
        """Set a Detector Upper Threshold value [UT] for a specific channel [CH] of the OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            ut: a value in between [1] and [255]. Must be higher than Lower Threshold [LT] value.
        """
        self._check_is_open()
        self._send_cmd("DSH", [address, chan, ut])
        self._check_response("Detector upper threshold set.")

    @rpc_method
    def set_lower_threshold(self, address: int, chan: int, lt: int) -> None:
        """Set a Detector Lower Threshold value [LT] for a specific channel [CH] of the OEM2 module.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
            chan: 1 to 3. Specific channel number.
            lt: a value in between [1] and [255]. Must be lower than Upper Threshold [UT] value.
        """
        self._check_is_open()
        self._send_cmd("DSL", [address, chan, lt])
        self._check_response("Detector lower threshold set.")

    @rpc_method
    def save_detector_settings(self, address) -> None:
        """Store Detector Gain [GAIN], Detector Upper Threshold value [UT] and Detector Lower Threshold value [LT]
         values in nonvolatile memory.

        Arguments:
            address: 1 to 6. Address of module corresponding to controller slot.
        """
        self._check_is_open()
        self._send_cmd("MSS", [address])
        self._check_response("Detector settings stored in flash.")

    @rpc_method
    def enable_servodrive(
            self, stage1: str, freq1: int, stage2: str, freq2: int, stage3: str, freq3: int, df: int, temp: int
    ) -> None:
        """Enable servo drive control loop.

        Arguments:
            stage1: Sets specific internal drive parameters for the type of actuator or system
                        attached to that particular channel of that particular module set by [ADDR] and [CH].
            freq1: 1 to 600 Step frequency input. Value is in Hertz [Hz] (numerical values only).
            stage2: Sets specific internal drive parameters for the type of actuator or system
                        attached to that particular channel of that particular module set by [ADDR] and [CH].
            freq2: 1 to 600 Step frequency input. Value is in Hertz [Hz] (numerical values only).
            stage3: Sets specific internal drive parameters for the type of actuator or system
                        attached to that particular channel of that particular module set by [ADDR] and [CH].
            freq3: 1 to 600 Step frequency input. Value is in Hertz [Hz] (numerical values only).
            df: 0.1 to 3.0 Drive factor (numerical values only). In normal operating conditions, set
                    this value to 1 (or 1.0).
            temp: 0 to 300 Set this parameter to the temperature of the environment in which the
                        actuator is used. Input is in Kelvin [K] (numerical values only).
        """
        self._check_is_open()
        self._send_cmd("FBEN", [stage1, freq1, stage2, freq2, stage3, freq3, df, temp])
        self._check_response("Control loop enabled.")

    @rpc_method
    def disable_servodrive(self) -> None:
        """Disable servo drive control loop."""
        self._check_is_open()
        self._send_cmd("FBXT")
        self._check_response("Control loop disabled.")

    @rpc_method
    def move_to_setpoint(self, sp1: float, sp2: float, sp3: float, enable_abs_pos: int) -> None:
        """Move actuators to a set point position.

        Arguments:
            sp1: setpoint value in [m] for linear, in [rad] for rotational type actuators.
            sp2: setpoint value in [m] for linear, in [rad] for rotational type actuators.
            sp3: setpoint value in [m] for linear, in [rad] for rotational type actuators.
            enable_abs_pos: 1 to enable absolute positioning, otherwise set to 0 (zero).
        """
        self._check_is_open()
        self._send_cmd("FBCS", [sp1, enable_abs_pos, sp2, enable_abs_pos, sp3, enable_abs_pos])
        self._check_response("Control loop setpoints set.")

    @rpc_method
    def emergency_stop(self) -> None:
        """Immediate stop of all actuators. The control loop will be aborted and the actuators will stop at
        their current location."""
        self._check_is_open()
        self._send_cmd("FBES")
        self._check_response("Control loop emergency stop enabled.")

    @rpc_method
    def get_status_position_control(self) -> StatusPositionControl:
        """This command receives a (comma-separated) list with status and position error information. The list is then
        turned into a named tuple which is returned.

        Returns:
            [ENABLED] [FINISHED] [INVALID SP1] [INVALID SP2] [INVALID SP3] [POS ERROR1] [POS ERROR2]
            [POS ERROR3]
        """
        self._check_is_open()
        self._send_cmd("FBST")
        status = self._recv_response().strip()
        return StatusPositionControl(*map(int, status.split(",")))
