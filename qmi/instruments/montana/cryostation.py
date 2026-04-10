"""Instrument driver for the Montana Cryostation."""

import logging
import threading
import time
from typing import Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Montana_Cryostation(QMI_Instrument):
    """Instrument driver for the Montana Cryostation.

    The Montana Cryostation is a cryostat that is delivered with a Windows 10 laptop. On the
    laptop, a GUI application is running. The GUI application allows remote control via TCP
    (by default, port 7773).

    IMPORTANT: the TCP server on the laptop's GUI needs to be manually enabled. There is,
      unfortunately, not a setting to do this automatically on startup.

    The Cryostation is monitored and controlled by a simple ASCII-based protocol as described in [1].

    The documentation lists 29 commands. Of these, 17 retrieve setpoints and sensor values;
    12 are used to alter setpoints or start behavior (e.g. cooldown):

    Getters:

        GAS   - Get Alarm State
        GCP   - Get Chamber Pressure
        GMS   - Get Magnet State
        GMTF  - Get Magnet Target Field
        GPHP  - Get Platform Heater Power
        GPIDF - Get PID Fi integral frequency
        GPIDK - Get PID Ki proportional gain
        GPIDT - Get PID Td derivative time
        GPS   - Get Platform Stability
        GS1T  - Get Stage 1 Temperature
        GS2T  - Get Stage 2 Temperature
        GPT   - Get Platform Temperature
        GSS   - Get Sample Stability
        GST   - Get Sample Temperature
        GTSP  - Get Temperature Set Point
        GUS   - Get User Stability
        GUT   - Get User Temperature
        RPID  - Reset PID parameters to their default values

    Setters:

        SCD   - Start Cool Down
        SMD   - Set Magnet Disabled
        SME   - Set Magnet Enabled
        SMTF  - Set Magnet Target Field
        SPIDF - Set PIDF Fi integral frequency
        SPIDK - Set PID proportional gain
        SPIDT - Set PID Td derivative time
        SSB   - Start StandBy
        STP   - SToP
        STSP  - Set Temperature Set Point
        SWU   - Start Warm Up
        SPHP  - Set Platform Heater Power

    We note that the three commands GPIDF, GPIDK, GPIDT that are used to retrieve PID control parameters
    do not work on our CryoStation.

    Note: this driver assumes that the Montana software uses a locale with '.' as decimal separator (e.g. "en_US"). The
    Montana software inherits this setting from the language settings of the operating system on the monitoring laptop.

    References:

    [1] Montana Cryostation Communication Specification, version 1.9
    """
    # Value ranges
    MIN_PROPORTIONAL_GAIN = 0.001
    MAX_PROPORTIONAL_GAIN = 100.0
    MIN_INTEGRAL_FREQUENCY = 0.0
    MAX_INTEGRAL_FREQUENCY = 100.0
    MIN_DERIVATIVE_TIME = 0.0
    MAX_DERIVATIVE_TIME = 100.0
    MIN_TEMPERATURE_SETPOINT = 2.0
    MAX_TEMPERATURE_SETPOINT = 350.0

    # The Cryostation should respond within 5 seconds.
    RESPONSE_TIMEOUT = 5.0

    # The user should not apply more than 1 Watt to the platform heater.
    _MAX_PLATFORM_HEATER_POWER = 1.0

    # There is a way to set the platform heater up to 10 Watt, but only for a limited duration.
    _MAX_PLATFORM_HEATER_BURST_POWER = 10.0
    _MAX_PLATFORM_HEATER_BURST_DURATION = 30.0

    # Retry turning off the platform heater if necessary.
    _MAX_TURN_OFF_HEATER_RETRY = 3

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initializes a Montana_Cryostation instance.

        Note:
            This method should not be called directly by a QMI user.
            Always instantiate an instrument via a QMI_Context `make_instrument()` call.

        Arguments:
            context: the QMI context
            name: the name of the instrument instance. Use the same name as the variable to which
                  the newly created instance is assigned.
            transport: the transport to the Cryostation software. This should be a TCP transport.
                  The default TCP port number for the Cryostation remote control is 7773.
        """

        super().__init__(context, name)
        self._transport = create_transport(transport, default_attributes={"port": 7773})
        self._timeout = Montana_Cryostation.RESPONSE_TIMEOUT
        self._platform_heater_on = False
        self._platform_heater_timer_thread: Optional[threading.Timer] = None
        self._command_lock = threading.Lock()

    def release_rpc_object(self) -> None:
        """Make sure the platform heater is safely turned off before destroying this instrument driver instance.

        The platform heater is normally turned off by the `close()` method. This function is only necessary
        to handle cases where the driver shuts down without properly calling `close()`.
        """
        super().release_rpc_object()
        if self.is_open():
            self._cancel_platform_heater_burst_timer()
            self._turn_off_platform_heater()

    @rpc_method
    def open(self) -> None:
        """Opens a connection to the Cryostation instrument."""
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """Closes a connection to the Cryostation instrument."""
        self._check_is_open()
        _logger.info("Closing connection to %s", self._name)

        # Make sure the platform heater is safely turned off before closing the connection.
        self._cancel_platform_heater_burst_timer()
        self._turn_off_platform_heater()

        super().close()
        self._transport.close()

    def _execute_command(self, command: str, *, check_ok=False) -> str:
        """Execute Cryostation command and return response.

        Cryostat commands and responses are ASCII commands preceded by a
        length-of-message field consisting of 2 ASCII decimal digits.
        No end-of-command terminators are used.

        If the `check_ok` flag is set, an extra check is done to see if the 'OK'
        string is present in the response.

        This function can be safely called concurrently from multiple threads.
        We use this to implement automatic shutdown of the platform heater
        via a background timer thread.
        """

        # Use a lock to make sure that only one thread talks to the instrument.
        with self._command_lock:

            # Discard any pending response that was meant for a previous command.
            self._transport.discard_read()

            command_bin = "{:02d}{}".format(len(command), command).encode('ascii')
            self._transport.write(command_bin)
            num_bytes = int(self._transport.read(2, self._timeout))
            response = self._transport.read(num_bytes, self._timeout).decode("ascii")

        if response == "Error: Invalid command.":
            raise QMI_InstrumentException("Cryostat does not recognise command {!r}".format(command))

        if check_ok and "OK" not in response:
            raise QMI_InstrumentException(f"Unexpected response received: {response}!")

        return response

    @rpc_method
    def get_alarm_state(self) -> bool:
        """Retrieves the alarm state, i.e., whether a system error is presently active."""

        command = "GAS"
        response = self._execute_command(command)

        if response not in ["T", "F"]:
            raise ValueError("Bad response from the Cryostat to the {!r} command: {!r}".format(command, response))

        alarm_state = (response == "T")

        return alarm_state

    @rpc_method
    def get_chamber_pressure(self, unit: Optional[str]=None) -> float:
        """Retrieve the current chamber pressure.

        The Cryostation always returns the pressure in [mTorr]. Since that is usually a pretty inconvenient
        unit, this method allows the specification of different units ([Pa], [atm]) that are usually more
        convenient, converting the retrieved value in [mTorr] to that unit is requested.

        Parameters:
            unit: the physical unit of pressure to return. This can be one of 'mTorr', 'Pa', or 'atm'.
                  The default if no unit is specified is mTorr.

        Returns: current chamber pressure in the unit selected, or NaN if the chamber pressure is not available.
        """

        if unit is None:
            unit = 'mTorr'

        if unit not in ['mTorr', 'Pa', 'atm']:
            raise ValueError(f"Bad unit specified for Montana Cryostation get_chamber_pressure method: {unit!r}")

        command = "GCP"
        response = self._execute_command(command)
        pressure = float(response)

        if unit == 'mTorr':
            pass
        elif unit == 'Pa':
            pressure = pressure * (101325.0 / 760000.0)
        elif unit == 'atm':
            pressure = pressure / 760000.0

        return pressure

    @rpc_method
    def get_magnet_state(self) -> Optional[bool]:
        """Retrieves the current magnet state.

        Returns: True if magnet is enabled; False if magnet is disabled;
            None if the system cannot execute the command (activate the magnet first).
        """

        command = "GMS"
        response = self._execute_command(command)

        # "System not able to execute command at this time.  Activate the magnet module first."
        magnet_state: Optional[bool] = None

        if response == "MAGNET ENABLED":
            magnet_state = True
        elif response == "MAGNET DISABLED":
            magnet_state = False

        return magnet_state

    @rpc_method
    def get_magnet_target_field(self) -> float:
        """Retrieves the current set point for magnetic field.

        Returns: current set point for magnetic field in [Tesla], or NaN if the magnet is not enabled or the magnet
            module is not activated.
        """

        command = "GMTF"
        response = self._execute_command(command)

        if response == "-9.999999":
            # The instrument will return -9.999999 if the magnet is not enabled or the magnet module is not activated.
            magnet_target_field = float("nan")
        else:
            magnet_target_field = float(response)

        return magnet_target_field

    @rpc_method
    def get_platform_heater_power(self) -> float:
        """Retrieves the current platform heater power.

        Returns: platform heater power in [Watt], or NaN if the platform heater power is not available.
        """

        command = "GPHP"
        response = self._execute_command(command)

        if response == "-0.100":
            # The instrument will return -0.100 if the platform heater power is not available.
            platform_heater_power = float("nan")
        else:
            platform_heater_power = float(response)

        return platform_heater_power

    @rpc_method
    def get_pid_integral_frequency(self) -> float:
        """Retrieves the current setting for PID Fi integral frequency.

        Returns: PID Fi integral frequency in [Hz].

        Warning: this function doesn't work on our Cryostation and raises a QMI_InstrumentException.
        """

        command = "GPIDF"
        response = self._execute_command(command)

        pid_integral_frequency = float(response)

        return pid_integral_frequency

    @rpc_method
    def set_pid_integral_frequency(self, i_freq_hz: float) -> None:
        """Set the PID integral frequency value.

        Note: 0 will result in no integral action.

        Parameters:
            i_freq: integral frequency in Hertz. (0.000 - 100.000)
        """
        if not self.MIN_INTEGRAL_FREQUENCY <= i_freq_hz <= self.MAX_INTEGRAL_FREQUENCY:
            raise ValueError(f"Integral frequency ({i_freq_hz}) is not in range {(self.MIN_INTEGRAL_FREQUENCY, self.MAX_INTEGRAL_FREQUENCY)}!")

        _logger.info("[%s] Setting integral frequency to %f Hertz", self._name, i_freq_hz)
        self._execute_command(f"SPIDF {i_freq_hz:.3f}", check_ok=True)

    @rpc_method
    def get_pid_proportional_gain(self) -> float:
        """Retrieves the current setting for PID Ki proportional gain.

        Returns: PID Ki proportional gain in [Watt/Kelvin].

        Warning: this function doesn't work on our Cryostation and raises a QMI_InstrumentException.
        """

        command = "GPIDK"
        response = self._execute_command(command)

        pid_proportional_gain = float(response)

        return pid_proportional_gain

    @rpc_method
    def set_pid_proportional_gain(self, p_gain: float) -> None:
        """Set the PID proportional gain value.

        Note: 0 will result in no derivative action.

        Parameters:
            p_gain: Proportional gain in Watts/Kelvin. (0.001 - 100.000)
        """
        if not self.MIN_PROPORTIONAL_GAIN <= p_gain <= self.MAX_PROPORTIONAL_GAIN:
            raise ValueError(f"Proportionial gain ({p_gain}) is not in range {(self.MIN_PROPORTIONAL_GAIN, self.MAX_PROPORTIONAL_GAIN)}!")

        _logger.info("[%s] Setting proportional gain to %f Watts/Kelvin", self._name, p_gain)
        self._execute_command(f"SPIDK {p_gain:.3f}", check_ok=True)

    @rpc_method
    def get_pid_derivative_time(self) -> float:
        """Retrieves the current setting for PID Td derivative time.

        Returns: PID Td derivative time in [seconds].

        Warning: this function doesn't work on our Cryostation and raises a QMI_InstrumentException.
        """

        command = "GPIDT"
        response = self._execute_command(command)

        pid_derivative_time = float(response)

        return pid_derivative_time

    @rpc_method
    def set_pid_derivative_time(self, d_time_s: float) -> None:
        """Set the PID derivative time value.

        Parameters:
            d_time: derivative time in seconds. (0.000 - 100.000)
        """
        if not self.MIN_DERIVATIVE_TIME <= d_time_s <= self.MAX_DERIVATIVE_TIME:
            raise ValueError(f"derivative time ({d_time_s}) is not in range {(self.MIN_DERIVATIVE_TIME, self.MAX_DERIVATIVE_TIME)}!")

        _logger.info("[%s] Setting derivative time to %f seconds", self._name, d_time_s)
        self._execute_command(f"SPIDT {d_time_s:.3f}", check_ok=True)

    @rpc_method
    def get_platform_stability(self) -> float:
        """Retrieves the current platform stability.

        Returns: platform stability in [Kelvin].
        """

        command = "GPS"
        response = self._execute_command(command)

        if response == "-0.10000":
            # The instrument will return -0.10000 if the platform stability is not available.
            platform_stability = float("nan")
        else:
            platform_stability = float(response)

        return platform_stability

    @rpc_method
    def get_stage_1_temperature(self) -> float:
        """Retrieves the current stage 1 temperature.

        Returns: stage 1 temperature in [Kelvin], or NaN if the stage 1 temperature is not available.
        """

        command = "GS1T"
        response = self._execute_command(command)

        if response == "-0.10":
            # The instrument will return -0.10 if the stage 1 temperature is not available.
            stage_1_temperature = float("nan")
        else:
            stage_1_temperature = float(response)

        return stage_1_temperature

    @rpc_method
    def get_stage_2_temperature(self) -> float:
        """Retrieves the current stage 2 temperature.

        Returns: stage 2 temperature in [Kelvin], or NaN if the stage 2 temperature is not available.
        """

        command = "GS2T"
        response = self._execute_command(command)

        if response == "-0.10":
            # The instrument will return -0.10 if the stage 2 temperature is not available.
            stage_2_temperature = float("nan")
        else:
            stage_2_temperature = float(response)

        return stage_2_temperature

    @rpc_method
    def get_platform_temperature(self) -> float:
        """Retrieves the current platform temperature.

        Returns: platform temperature in [Kelvin], or NaN if the platform temperature is not available.
        """

        command = "GPT"
        response = self._execute_command(command)

        if response == "-0.100":
            # The instrument will return -0.100 if the platform temperature is not available.
            temperature = float("nan")
        else:
            temperature = float(response)

        return temperature

    @rpc_method
    def get_sample_stability(self) -> float:
        """Retrieves the current sample stability.

        Returns: sample stability in [Kelvin], or NaN if the sample stability is not available.
        """

        command = "GSS"
        response = self._execute_command(command)

        if response == "-0.10000":
            # The instrument will return -0.10000 if the sample stability is not available.
            sample_stability = float("nan")
        else:
            sample_stability = float(response)

        return sample_stability

    @rpc_method
    def get_sample_temperature(self) -> float:
        """Retrieves the current sample temperature.

        Returns: sample temperature in [Kelvin], or NaN if the sample temperature is not available.
        """

        command = "GST"
        response = self._execute_command(command)

        if response == "-0.100":
            # The instrument will return -0.100 if the sample temperature is not available.
            sample_temperature = float("nan")
        else:
            sample_temperature = float(response)

        return sample_temperature

    @rpc_method
    def get_temperature_setpoint(self) -> float:
        """Retrieves the current temperature setpoint.

        Returns: temperature setpoint in [Kelvin], or NaN if the temperature setpoint is not available.
        """

        command = "GTSP"
        response = self._execute_command(command)

        temperature_setpoint = float(response)

        return temperature_setpoint

    @rpc_method
    def set_temperature_setpoint(self, setpoint_k: float) -> None:
        """Set temperature setpoint.

        Parameters:
            setpoint_k:   Temperature setpoint in Kelvin. (2.00 - 350.00)
        """
        if not self.MIN_TEMPERATURE_SETPOINT <= setpoint_k <= self.MAX_TEMPERATURE_SETPOINT:
            raise ValueError(f"Setpoint ({setpoint_k}) is not in range {(self.MIN_TEMPERATURE_SETPOINT, self.MAX_TEMPERATURE_SETPOINT)}!")

        _logger.info("[%s] Setting temperature setpoint to %f K", self._name, setpoint_k)
        self._execute_command(f"STSP {setpoint_k:.2f}", check_ok=True)

    @rpc_method
    def get_user_stability(self) -> float:
        """Retrieves the current user stability (whatever that may be).

        Returns: user stability in [Kelvin], or NaN if the user stability is not available.
        """

        command = "GUS"
        response = self._execute_command(command)

        if response == "-0.10000":
            # The instrument will return -0.10000 if the user stability is not available.
            user_stability = float("nan")
        else:
            user_stability = float(response)

        return user_stability

    @rpc_method
    def get_user_temperature(self) -> float:
        """Retrieves the current user temperature.

        Returns: user temperature in [Kelvin], or NaN if the user temperature is not available.
        """

        command = "GUT"
        response = self._execute_command(command)

        if response == "-0.100":
            # The instrument will return -0.100 if the user temperature is not available.
            user_stability = float("nan")
        else:
            user_stability = float(response)

        return user_stability

    @rpc_method
    def start_standby(self) -> None:
        """Start standby."""
        _logger.info("[%s] Starting standby.")

        command = "SSB"
        self._execute_command(command, check_ok=True)

    @rpc_method
    def start_cooldown(self) -> None:
        """Start the cooldown."""
        _logger.info("[%s] Starting the cooldown.")

        command = "SCD"
        self._execute_command(command, check_ok=True)

    @rpc_method
    def start_warmup(self) -> None:
        """Start the warmup."""
        _logger.info("[%s] Starting the warmup.")

        command = "SWU"
        self._execute_command(command, check_ok=True)

    @rpc_method
    def stop_system(self) -> None:
        """Stop either the standby, cooldown or warmup of the system."""
        _logger.info("[%s] Stopping the system.")

        command = "STP"
        self._execute_command(command, check_ok=True)

    def _internal_set_platform_heater_power(self, power: float) -> None:
        """Set platform heater to specified power."""

        # Power value has already been checked before calling this function.
        _logger.info("[%s] Setting platform heater to %f W", self._name, power)

        # Set "_platform_heater_on" before giving the command, so the flag
        # will be set properly even if the command gives an ambiguous response.
        if power > 0.0:
            self._platform_heater_on = True

        self._execute_command(f"SPHP {power:.4f}", check_ok=True)

        # Clear the "_platform_heater_on" flag after successfully turning off the heater.
        self._platform_heater_on = (power > 0.0)

    def _turn_off_platform_heater(self) -> None:
        """Turn off the platform heater.

        This function can be called:
         - by the timer thread, at the end of the specified heater burst duration;
         - after a failed attempt to set the platform heater;
         - when the instrument is closed.

        When invoked by the timer thread, this function runs inside that background thread.
        """

        # This function can run either inside the background timer thread or in
        # the main RPC thread. However it will never be invoked concurrently in both
        # threads because we stop the background timer before calling this function
        # when the instrument is closing.

        if self._platform_heater_on:

            # Turn off the platform heater.
            # Retry if necessary, because we really want to turn this heater off.
            for retry in range(self._MAX_TURN_OFF_HEATER_RETRY):
                _logger.info("[%s] Turning off platform heater", self._name)
                try:
                    self._internal_set_platform_heater_power(0.0)
                    break
                except (QMI_InstrumentException, QMI_TimeoutException) as exc:
                    _logger.error("[%s] Failed to turn off platform heater: %s",
                                  self._name, str(exc))
                    if retry >= self._MAX_TURN_OFF_HEATER_RETRY - 1:
                        # We are doomed. Report the error and find cover.
                        raise
                    # Short pause, then retry.
                    time.sleep(2.0)

    def _safe_set_platform_heater_power(self, power: float) -> None:
        """Set platform heater to specified power, or turn off the heater if an error occurs."""
        try:
            self._internal_set_platform_heater_power(power)
        except (QMI_InstrumentException, QMI_TimeoutException) as exc:
            _logger.error("[%s] Failed to set platform heater power: %s", self._name, str(exc))

            # Failed to change the heater power. This means the heater may still be at a dangerous level.
            # Turn the heater off to ensure a safe situation.
            self._turn_off_platform_heater()

            # Report the original exception.
            raise

    def _start_platform_heater_burst_timer(self, duration: float) -> None:
        """Start a background timer to turn off the platform heater."""
        assert self._platform_heater_timer_thread is None
        self._platform_heater_timer_thread = threading.Timer(duration, self._turn_off_platform_heater)
        _logger.debug("[%s] Starting burst timer for %f seconds", self._name, duration)
        self._platform_heater_timer_thread.start()

    def _cancel_platform_heater_burst_timer(self) -> None:
        """Cancel any currently running burst timer."""
        if self._platform_heater_timer_thread is not None:
            _logger.debug("[%s] Canceling burst timer", self._name)
            self._platform_heater_timer_thread.cancel()
            self._platform_heater_timer_thread.join()
            self._platform_heater_timer_thread = None

    @rpc_method
    def set_platform_heater_power(self, power: float) -> None:
        """Set the platform heater power.

        This function sets the platform heater to the specified power.
        The heater will remain at the requested power until explicitly turned off
        via another call to this function.

        This function only allows limited heater power levels. If you need more power,
        use `set_platform_heater_power_burst()` to set a high power level for a limited duration.

        Calling this function while a time-limited power burst is active, stops the burst timer and
        sets the new requested power without any time limit. The platform heater can always be turned off
        by calling this function and specifying 0 Watt power.

        Parameters:
            power:      Heater power in Watt (max 1 W).

        Raises:
            QMI_InstrumentException: If the Montana does not accept the command.
        """
        if not (0.0 <= power <= self._MAX_PLATFORM_HEATER_POWER):
            _logger.error("Trying to set %f W, but maximum is %d W", power, self._MAX_PLATFORM_HEATER_POWER)
            raise QMI_InvalidOperationException("Invalid platform heater power")

        # If a heater burst timer is running, cancel it.
        # This must be done before setting the heater, to make sure the timer will not interfere.
        # The timer is not needed anymore since we will set the heater to a safe level.
        self._cancel_platform_heater_burst_timer()

        # Set platform heater power, or turn off heater if an error occurs.
        self._safe_set_platform_heater_power(power)

    @rpc_method
    def set_platform_heater_power_burst(self, power: float, duration: float) -> None:
        """Set the platform heater to high power for a limited duration.

        This function sets the platform heater to the specified power, starts a timer,
        then returns while the timer keeps running in the background. If the timer reaches
        the specified duration, the heater power is automatically reset to 0 Watt.

        Calling this function while a background timer is running, restarts the timer for
        the specified new duration. It is thus possible to keep the heater at high power
        for a long time by repeatedly calling this function. A script that uses this technique,
        should also monitor temperatures and stop heating when temperatures reach a limit.

        A heating burst can always be stopped by calling this function (or `set_platform_heater_power`)
        and specifying 0 Watt power.

        WARNING: Setting the heater to high power for a long time can cause damage to
        the cryostat or the sample. Do not call this function unless you understand the risks.

        Parameters:
            power:      Heater power in Watt (max 10 W).
            duration:   Maximum duration for the specified power in seconds (max 30 s).

        Raises:
            QMI_InstrumentException: If the Montana does not accept the command.
        """

        if not (0.0 <= power <= self._MAX_PLATFORM_HEATER_BURST_POWER):
            _logger.error("Trying to set platform heater power burst of %f W for %f s, but maximum is %f W",
                          power, duration, self._MAX_PLATFORM_HEATER_BURST_POWER)
            raise QMI_InvalidOperationException("Invalid platform heater burst power")

        if (power > 0.0) and (duration < 0.0 or duration > self._MAX_PLATFORM_HEATER_BURST_DURATION):
            _logger.error("Trying to set platform heater power burst of %f W for %f s, but maximum is %f s",
                          power, duration, self._MAX_PLATFORM_HEATER_BURST_DURATION)
            raise QMI_InvalidOperationException("Invalid platform heater burst duration")

        # If a heater burst timer is running, cancel it.
        # This must be done before setting the heater, to make sure the timer will not interfere.
        self._cancel_platform_heater_burst_timer()

        # Set platform heater power, or turn off heater if an error occurs.
        self._safe_set_platform_heater_power(power)

        # If the heater is on, start a timer thread to turn it off after the specified duration.
        if power > 0:
            self._start_platform_heater_burst_timer(duration)
