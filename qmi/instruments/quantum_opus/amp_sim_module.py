"""Instrument driver for the Quantum Opus amp-sim module."""
import re

from qmi.instruments.stanford_research_systems.sim900 import Sim900
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_UsageException, QMI_InstrumentException


class AmpSimModule(QMI_Instrument):
    """Instrument driver for the Quantum Opus amp-sim module."""

    # Commands
    _GET_MODULE_COMMAND = "+A?"
    _GET_BIAS_COMMAND = "+B?"
    _SET_BIAS_COMMAND = "+B{};"
    _SET_ADC_LOW_GAIN_MODE_COMMAND = "+C{};"
    _GET_DEVICE_VOLTAGE = "+C?"
    _SET_RESET_EVENT_DURATION_COMMAND = "+D{};"
    _GET_RESET_EVENT_DURATION_COMMAND = "+D?"
    _SET_AUTO_RESET_ENABLE_COMMAND = "+E{};"
    _GET_AUTO_RESET_ENABLE_COMMAND = "+E?"
    _INITIATE_RESET_EVENT_COMMAND = "+F;"
    _INITIATE_AUTO_BIAS_COMMAND = "+G;"
    _STORE_BIAS_CURRENT_NVM_COMMAND = "+H{};"
    _GET_BIAS_CURRENT_NVM_COMMAND = "+H?;"
    _USE_BIAS_CURRENT_NVM_COMMAND = "+H;"

    # Regexes
    _FIX_GET_BIAS_NVM_RESPOSE_REGEX = r'^\d+'

    def __init__(self, context: QMI_Context, name: str, sim_900: Sim900, port: int) -> None:
        """Initialize driver.

        Arguments:
            name: Name for this instrument instance.
            sim_900: Instance of sim 900 module or RPC proxy of it, that hosts the amp-sim module.
            port: Port number in which the amp-sim module is located.
        """
        super().__init__(context, name)
        self._sim_900 = sim_900
        self._port = port

    @rpc_method
    def get_module_id(self) -> str:
        """Query module identification string.

        Returns:
            Module identification string.
        """
        return self._sim_900.ask_module(self._port, self._GET_MODULE_COMMAND)

    @rpc_method
    def get_device_bias_current(self) -> int:
        """Query device bias current.

        Query device bias in DAC units (0 ─ 65535) for 0 to 2.5 V bias through 100 kΩ bias resistor (0-25 μA bias
        current)

        Returns:
            Query device bias in DAC units.
        """
        response = self._sim_900.ask_module(self._port, self._GET_BIAS_COMMAND)
        return int(response)

    @rpc_method
    def set_device_bias_current(self, dac_units: int) -> None:
        """Set device bias current.

        Set device bias current in DAC units (d = 0 ─ 65535, integer values). 0 = off, 65535 = 25μA. The bias current
        defaults to zero upon power-up.

        Arguments:
            dac_units: Device bias in DAC units.
        """
        if not 0 <= dac_units <= 65535:
            msg = 'The device bias current should be between 0 and 65535 but is {}'.format(dac_units)
            raise QMI_UsageException(msg)
        command = self._SET_BIAS_COMMAND.format(dac_units)
        self._sim_900.send_terminated_message(self._port, command)

    @rpc_method
    def set_adc_low_gain_mode(self) -> None:
        """Set ADC gain to low_gain mode."""
        command = self._SET_ADC_LOW_GAIN_MODE_COMMAND.format(1)
        self._sim_900.send_terminated_message(self._port, command)

    @rpc_method
    def set_adc_high_gain_mode(self) -> None:
        """Set ADC gain to high_gain mode."""
        command = self._SET_ADC_LOW_GAIN_MODE_COMMAND.format(0)
        self._sim_900.send_terminated_message(self._port, command)

    @rpc_method
    def get_device_voltage(self) -> int:
        """Query device voltage.

        Query device voltage in ADC units. If module is in high-gain mode (setting 0) the voltage (in volts) is
        calculated as (ADC units)/65535*1.1. If the module is in low-gain mode (setting 1) the voltage (in volts)
        is calculated as (ADC units)/65535*5.0

        Returns:
            Query device bias in ADC units.
        """
        # NOTE: we cannot interpret this value unless we known if we're in high- or low-gain mode,
        #   and we have no way to query that setting. (Sigh.)
        response = self._sim_900.ask_module(self._port, self._GET_DEVICE_VOLTAGE)
        return int(response)

    @rpc_method
    def set_reset_event_duration(self, duration: int) -> None:
        """Set reset event duration.

        Set the Reset Event duration (d = 0 ─ 255, integer). Sets the length of time the device bias is set to zero
        when a latch condition (i.e., device in non-superconducting state) is detected. The duration is calculated
        in units of 10 ms.

        Arguments:
            duration: Duration in units of 10ms.
        """
        if not 0 <= duration <= 255:
            raise QMI_UsageException('The event duration should be between 0 and 255 but is {}'.format(duration))
        command = self._SET_RESET_EVENT_DURATION_COMMAND.format(duration)
        self._sim_900.send_terminated_message(self._port, command)

    @rpc_method
    def get_reset_event_duration(self) -> int:
        """Query Reset Event duration.

        Query the presently set Reset Event duration.The duration is represented in units of 10 ms.

        Returns:
            Duration in units of 10ms.
        """
        response = self._sim_900.ask_module(self._port, self._GET_RESET_EVENT_DURATION_COMMAND)
        return int(response)

    @rpc_method
    def set_auto_reset_enabled(self, enabled_flag: bool) -> None:
        """Enable or disable the auto-reset function.

        Enable or disable the auto-reset function. When enabled the module will monitor the voltage on the
        nanowire device and if it exceeds an internally set value indicating the device is no longer
        superconducting, an auto-reset event will be triggered. If disabled, a latch condition will be persistent
        until manually cleared by front-panel operation or by initiating a reset event through software.

        Arguments:
            enabled_flag: Boolean flag to enable or disable the auto-reset function.
        """
        enabled = int(bool(enabled_flag))
        command = self._SET_AUTO_RESET_ENABLE_COMMAND.format(enabled)
        self._sim_900.send_terminated_message(self._port, command)

    @rpc_method
    def get_auto_reset_enabled(self) -> bool:
        """Query the auto-reset function.

        Returns:
            Return value is True if enabled, False if disabled.
        """
        response = self._sim_900.ask_module(self._port, self._GET_AUTO_RESET_ENABLE_COMMAND)
        return bool(int(response))

    @rpc_method
    def initiate_reset_event(self) -> None:
        """Initiate a Reset Event.

        Initiate a Reset Event. The device bias is reduced to zero, held at zero for the Reset Event duration,
        and then returned to its previously set value.
        """
        self._sim_900.send_terminated_message(self._port, self._INITIATE_RESET_EVENT_COMMAND)

    @rpc_method
    def initiate_auto_bias_function(self) -> None:
        """Initiate the auto-bias function.

        Initiate the auto-bias function. The device bias current is swept up from zero until a latch condition
        is detected. This latching current is measured. A Reset Event is initiated and then the bias is increased back
        up to approximately 95% of the measured latching current. This function is most reliable when the incoming
        light on the device is minimized as incoming photons can cause a slightly lower measured latching current.
        Note: The auto-bias function can result in slightly different bias currents each time it is run.
        """
        self._sim_900.send_terminated_message(self._port, self._INITIATE_AUTO_BIAS_COMMAND)

    @rpc_method
    def store_bias_current_in_non_volatile_memory(self, dac_current: int) -> None:
        """Store a bias DAC value into non-volatile memory.

        Store a bias DAC value into non-volatile memory (d = 0 ─ 65535, integer values). 0=off, 65535=25μA. This value
        will be written into internal non-volatile memory for reproducible biasing of the device through the
        use_device_bias_from_non_volatile_memory.

        Note: The internal non-volatile memory is only guaranteed to survive for 100,000 write functions. This limit
        can be easily exceeded if an external program repeatedly calls this function.

        Arguments:
            dac_current: Bias current that needs to be stored in non-volatile memory in units of 25μA.
        """
        if not 0 <= dac_current <= 65535:
            msg = 'The event duration should be between 0 and 65535 but is {}'.format(dac_current)
            raise QMI_UsageException(msg)
        command = self._STORE_BIAS_CURRENT_NVM_COMMAND.format(dac_current)
        self._sim_900.send_terminated_message(self._port, command)

    @rpc_method
    def get_bias_current_from_non_volatile_memory(self) -> int:
        """Query DAC bias value stored in non-volatile memory.

        Return the value of the DAC bias stored in non-volatile memory. The bias value is stored in units of 25μA.

        Returns:
            Bias value stored in non-voletile memory in units of 25μA.
        """
        response = self._sim_900.ask_module(self._port, self._GET_BIAS_CURRENT_NVM_COMMAND)
        # Note: the device returns x.0\n instead of just a integer value (represented in chars). This is fixed by
        # extracting the first digits from the response string.
        match = re.match(self._FIX_GET_BIAS_NVM_RESPOSE_REGEX, response)
        if match is None:
            raise QMI_InstrumentException(
                "Expected response to start with digits but instead got: {}".format(response))
        first_digits = match.group(0)
        return int(first_digits)

    @rpc_method
    def use_device_bias_from_non_volatile_memory(self) -> None:
        """Sets the device bias to the value stored in non-volatile memory."""
        self._sim_900.send_terminated_message(self._port, self._USE_BIAS_CURRENT_NVM_COMMAND)
