"""Instrument driver for the OzOptics Electric Polarization Controller driver."""
import re
from typing import Tuple, Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import QMI_Transport, create_transport


class OzOptics_EpcDriver(QMI_Instrument):
    """Instrument driver for the OzOptics Electric Polarization Controller driver."""

    def __init__(self, context: QMI_Context, name: str, transport: Union[str, QMI_Transport]) -> None:
        """Initialize the Electric Polarization Controller driver.

        Args:
            context: QMI context.
            name: Name for this instrument instance.
            transport:  Either a transport string (see create_transport) or a QMI_Transport.
        """
        super().__init__(context, name)
        if isinstance(transport, str):
            self._transport = create_transport(transport)
        elif isinstance(transport, QMI_Transport):
            self._transport = transport

    @rpc_method
    def open(self) -> None:
        """See base class."""
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """See base class."""
        super().close()
        self._transport.close()

    def _ask(self, command: str, timeout=1) -> str:
        super()._check_is_open()
        bytes_command = "{}\r\n".format(command).encode(encoding='ascii')
        self._transport.write(bytes_command)
        content_line = self._transport.read_until(b'\r\n', timeout)
        done_line = self._transport.read_until(b'\r\n', timeout)
        if done_line.decode('ASCII') != 'Done\r\n':
            raise QMI_InstrumentException('Device did not respond correctly, expected Done message from device.')
        response = content_line.decode('ASCII')
        return response

    @staticmethod
    def _check_channel(channel: int) -> None:
        if not (1 <= channel <= 4):
            raise ValueError("{} is not a valid channel".format(channel))

    @rpc_method
    def get_frequencies(self) -> Tuple[int, ...]:
        """Get the present scrambling frequencies.

        Returns:
            (int, int, int, int) tuple of frequencies [Hz] belonging to channel 1..4 respectively. The returned
            frequencies will be in the range of 0 to 100 Hertz.
        """
        response = self._ask('F?')
        # Device responds with string like "Frequency(Hz): CH1 007  CH2 017  CH3 037  CH4 071", use regex to find all
        # digits for each channel.
        matched_frequencies = re.findall(r'CH. (\d+)', response)
        # convert strings to integers
        frequencies = tuple(map(int, matched_frequencies))
        return frequencies

    @rpc_method
    def set_frequency(self, channel: int, frequency: int) -> None:
        """Set channel to specified frequency.

        Args:
            channel (int): Channel number 1..4.
            frequency (int): Frequency [Hz] in the range of 0 to 100 Hz.
        """
        self._check_channel(channel)

        if not (0 <= frequency <= 100):
            raise ValueError("{} is not a valid channel".format(channel))

        command = 'F{},{}'.format(channel, frequency)
        self._ask(command)

    @rpc_method
    def set_operating_mode_ac(self) -> None:
        """Set operating mode to AC (scrambling)."""
        self._ask('MAC')

    @rpc_method
    def set_operating_mode_dc(self) -> None:
        """Set operating mode to DC (fixed voltage)."""
        self._ask('MDC')

    @rpc_method
    def enable_dc_in_ac_mode(self) -> None:
        """Enable dc voltage in ac mode

        Enables the user to use a fixed dc voltage while the unit is operating in AC mode.
        """
        self._ask('ENVF1')

    @rpc_method
    def disable_dc_in_ac_mode(self) -> None:
        """Disable dc voltage in ac mode

        Disable the user to use a fixed dc voltage while the unit is operating in AC mode.
        """
        self._ask('ENVF0')

    @rpc_method
    def toggle_channel_ac_dc(self, channel: int) -> None:
        """Toggle channel output between AC and DC.

        Notes:
            The device must be in "dc in ac mode" for this operating mode to be effective.

        Args:
            channel (int): Channel number 1..4.
        """
        self._check_channel(channel)
        self._ask('VF{}'.format(channel))

    @rpc_method
    def get_ac_dc_channel_status(self) -> Tuple[str, ...]:
        """Return operating mode of each of the channels.

        Returns:
            (str, str, str, str) tuple of strings, belonging to channel 1..4 respectively, indicating if the channel is
            in 'V' DC mode or 'F' AC mode.
        """
        ac_dc_status = self._ask('VF?')
        channel_status = re.findall(r'CH.-([VF])', ac_dc_status)
        return tuple(channel_status)

    @rpc_method
    def is_in_dc_in_ac_mode(self) -> bool:
        """Device is in dc in ac mode.

        Returns:
            True if the dc in ac mode is enabled, False when the dc in ac mode is disabled.
        """
        ac_dc_status = self._ask('VF?')
        is_dc_in_ac_mode = 'enabled' in ac_dc_status
        return is_dc_in_ac_mode

    @rpc_method
    def get_operating_mode(self) -> str:
        """Get the present operating mode (scrambling or fixed voltage).

        Returns:
            Operating mode string defined as 'AC' or 'DC'. AC (Alternating Current) means that the device is in
            scrambling mode and DC (Direct Current) means the device is in fixed voltage mode.
        """
        response = self._ask('M?')
        words = response.split()
        last_word = words[-1]
        first_two_chars = last_word[:2]
        return first_two_chars

    @rpc_method
    def set_voltage(self, channel: int, voltage: int) -> None:
        """Set channel to the specified voltage.

        Args:
            channel (int): Channel number 1..4.
            voltage (int): Voltage specified in millivolts [mV] that range between -5000 to +5000.
        """
        self._check_channel(channel)

        if not (-5000 <= voltage <= 5000):
            raise ValueError('Provided voltage [mV] is not between -5000 and 5000 mV')

        command = 'V{},{}'.format(channel, voltage)
        self._ask(command)

    @rpc_method
    def set_high(self, channel: int) -> None:
        """Set channel voltage high (maximum).

        Args:
            channel (int): Channel number 1..4.
        """
        self._check_channel(channel)
        command = 'VH{}'.format(channel)
        self._ask(command)

    @rpc_method
    def set_low(self, channel: int) -> None:
        """Set channel voltage low (minimum).

        Args:
            channel: Channel number 1..4.
        """
        self._check_channel(channel)
        command = 'VL{}'.format(channel)
        self._ask(command)

    @rpc_method
    def set_zero(self, channel: int) -> None:
        """Set channel voltage zero volts.

        Args:
            channel: Channel number 1..4.
        """
        self._check_channel(channel)
        command = 'VZ{}'.format(channel)
        self._ask(command)

    @rpc_method
    def get_voltages(self) -> Tuple[int, ...]:
        """Get the output voltages.

        Returns:
            Tuple (int, int, int, int) of voltages [mV] belonging to channel 1..4 respectively. The returned
            voltages will be in the range of -5000 mV to 5000 mV.
        """
        response = self._ask('V?')
        # Device responds with string like "Voltage(mV): CH1 +2200 CH2 +5000 CH3 -1000 CH4 -4000", use regex to find all
        # voltages for each channel.
        matched_frequencies = re.findall(r'CH. (.\d+)', response)
        # convert strings to integers
        frequencies = tuple(map(int, matched_frequencies))
        return frequencies

    @rpc_method
    def get_waveform_type(self) -> str:
        """Get Waveform type (Sine or Triangle)

        This command will get the present waveform type that is being used (Triangle or sine wave).

        Returns:
            A string that indicates either a Sine or a Triangle waveform is used.
        """
        response = self._ask('WF?')
        # Device responds with either "AC Waveform: Sine" or "AC Waveform: Triangle", returning the last word is
        # sufficient here.
        waveform = response.split()[-1]
        return waveform

    @rpc_method
    def save_to_flash(self) -> None:
        """Save current status to flash memory"""
        self._ask('SAVE')

    @rpc_method
    def set_waveform_type_sine(self) -> None:
        """Set waveform type to Sine"""
        self._ask('WF1')

    @rpc_method
    def set_waveform_type_triangle(self) -> None:
        """Set waveform type to Triangle"""
        self._ask('WF2')
