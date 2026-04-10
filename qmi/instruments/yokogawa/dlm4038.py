"""
Instrument driver for the Yokogawa DLM4038 Oscilloscope. The instrument can be connected over ethernet and usb.

If the instrument is connected over ethernet, use the vxi11 protocol by passing the transport description
"vxi11:ip-address". If the mass storage function (over USB) is used, the scope directory needs to be specific
(default is "O:/").

Connecting to the instrument through USB is also possible but could not be tested. The testing was done on a
Windows 11 PC but the installation of the device driver to recognize the instrument correctly through USB was
not successful. In principle, the transport descriptor is likely to be either
"usbtmc:vendorid=0x0b21:productid=0x0038:serialnr=<serialnr>", or with a GPIB adapter "gbip:<address>".
"""

import logging
import os
import shutil
import time

import numpy as np
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Yokogawa_DLM4038(QMI_Instrument):
    """Instrument driver for the Yokogawa DLM4038 Oscilloscope.
    
    Arguments:
        CHANNELS: The number of signal channels in the device.
    """
    _rpc_constants = ["CHANNELS"]
    CHANNELS = 8

    def __init__(
            self, context: QMI_Context, name: str, transport: str, directory: str | None = "O:/", timeout: float = 1.0
    ) -> None:
        """Initialize the instrument driver.

        Parameters:
            name:      Name for this instrument instance.
            transport: QMI transport descriptor to connect to the instrument.
            directory: Path to the scope mass storage. Default is "O:/".
            timeout:   Scope response timeout. Default is 1.0.
        """
        super().__init__(context, name)
        self._transport = create_transport(transport)
        self._scpi_protocol = ScpiProtocol(self._transport, default_timeout=timeout)
        self._directory_oscilloscope = directory

    def _channels_check(self, channels: int | list[int] | str) -> int | list[int]:
        """Check for string type 'all' and return 'channels' as a list of integers"""
        if isinstance(channels, str) and channels.lower() == "all":
            return list(range(1, self.CHANNELS + 1))

        assert not isinstance(channels, str)
        return channels

    @staticmethod
    def _data_type_check(data_type: str) -> str:
        """Check the data type string and return in SCPI style."""
        if data_type.lower() == "binary":
            data_type = "BINary"
        elif data_type.lower() == "ascii":
            data_type = "ASCii"
        else:
            raise QMI_InstrumentException(f"Unexpected data type, got {data_type}")
        return data_type

    def _channel_value_setter(
            self,
            channels: int | list[int],
            values: str | int | float | list[int | float],
            parameter: str,
            unit: str = ""
    ) -> None:
        """A helper function to handle logic on setting diverse lengths of various channel parameters."""
        if isinstance(channels, int) and (
                isinstance(values, float) or isinstance(values, int) or isinstance(values, str)
        ):  # Single channel setter
            self._scpi_protocol.write(f":CHANnel{channels}:{parameter} {values}{unit}")

        elif not isinstance(values, list) and isinstance(channels, list):
            # Set the same value for all channels
            for chan in channels:
                self._scpi_protocol.write(f":CHANnel{chan}:{parameter} {values}{unit}")

        elif isinstance(values, list) and isinstance(channels, list):
            # Multi-channel setter with values per channel
            if len(values) != len(channels):
                raise QMI_UsageException(f"Invalid number of values ({len(values)}) for {len(channels)} channels.")

            for chan, val in zip(channels, values):
                self._scpi_protocol.write(f":CHANnel{chan}:{parameter} {val}{unit}")

        else:
            _logger.error("%s {parameter} not set due to invalid parameters: %d, %d", self._name, channels, values)

    def _channel_value_getter(
            self, channels: int | list[int], parameter: str, val_start: int, preposition: str = ""
    ) -> list[str]:
        """A helper function for getting various channel parameter values."""
        if len(preposition) > 0 and not preposition.startswith(":"):
            preposition = ":" + preposition

        values = []
        if isinstance(channels, int):
            channels = [channels]

        for chan in channels:
            current_value = self._scpi_protocol.ask(f"{preposition}:CHANnel{chan}:{parameter}?")
            values.append(current_value[val_start:])

        return values

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

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._scpi_protocol.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")
        return QMI_InstrumentIdentification(
            vendor=words[0].strip(), model=words[1].strip(), serial=words[2].strip(), version=words[3].strip()
        )

    @rpc_method
    def start(self) -> None:
        """Start waveform acquisition."""
        self._scpi_protocol.write(":START")

    @rpc_method
    def stop(self) -> None:
        """Stop waveform acquisition."""
        self._scpi_protocol.write(":STOP")

    @rpc_method
    def set_time_division(self, time_division: float) -> None:
        """Set the Time/div value.

        Parameters:
            time_division: The new Time/div value in seconds.
        """
        self._scpi_protocol.write(f":TIMEBASE:TDIV {time_division}")

    @rpc_method
    def get_time_division(self) -> float:
        """Get the Time/div value.

        Returns:
            time_division: The current Time/div value in seconds.
        """
        return float(self._scpi_protocol.ask(":TIMEBASE:TDIV?")[9:])

    @rpc_method
    def set_high_resolution(self, state: bool) -> None:
        """Set the High Resolution mode on or off.

        Parameters:
            state: True to set High Resolution mode on, False to set it off.
        """
        # self._scpi_protocol.write(":ACQUIRE:RESOLUTION " + str(state))
        state_str = "ON" if state else "OFF"
        self._scpi_protocol.write(":ACQUIRE:RESOLUTION " + state_str)

    @rpc_method
    def turn_channel_on(self, channels: int | list[int] | str) -> None:
        """Turns on the display of specified channel or channels.
        
        Parameters:
            channels: A single channel number or a list of selected channels. Use "all" for all channels.
        """
        checked_chs = self._channels_check(channels)
        self._channel_value_setter(checked_chs, "ON", "DISPlay")

    @rpc_method
    def turn_channel_off(self, channels: int | list[int] | str) -> None:
        """Turns off the display of specified channel or channels.

        Parameters:
            channels: A single channel number or a list of selected channels. Use "all" for all channels.
        """
        checked_chs = self._channels_check(channels)
        self._channel_value_setter(checked_chs, "OFF", "DISPlay")

    @rpc_method
    def set_voltage_offset(self, channels: int | list[int] | str, v_offset: float | list[float]) -> None:
        """Sets the voltage offset for the specified channels. Voltage offset is specified in volts.

        Parameters:
            channels: A single channel number or a list of selected channels. Use "all" for all channels.
            v_offset: A single voltage or a list of voltages. Can be given as one value which is then applied to
                      all 'channels'. Otherwise, length must match with 'channels'.

        Raises:
            QMI_UsageException: If the given input channels and v_offset parameters do not match.
        """
        checked_chs = self._channels_check(channels)
        self._channel_value_setter(checked_chs, v_offset, "OFFset", "V")

    @rpc_method
    def get_voltage_offset(self, channels: int | list[int] | str) -> np.ndarray:
        """Returns the current voltage offset for the specified channels.

        Parameters:
            channels: A single channel number or a list of selected channels. Use "all" for all channels.

        Returns:
            v_offset: An array of offset values, respective to the size of given input channels.
        """
        checked_chs = self._channels_check(channels)
        v_offset = self._channel_value_getter(checked_chs, "OFFset", 11)

        return np.array(v_offset, dtype=float)

    @rpc_method
    def set_voltage_division(self, channels: int | list[int] | str, v_division: float | list[float]) -> None:
        """Set the voltage division for the specified channels. Voltage division is specified in Volts.

        Parameters:
            channels:   A single channel number or a list of selected channels. Use "all" for all channels.
            v_division: A single voltage or a list of voltages. Can be given as one value which is then applied to
                        all 'channels'. Otherwise, length must match with 'channels'.

        Raises:
            QMI_UsageException: If the given input channels and v_division parameters do not match.
        """
        checked_chs = self._channels_check(channels)
        self._channel_value_setter(checked_chs, v_division, "VDIV", "V")

    @rpc_method
    def get_voltage_division(self, channels: int | list[int] | str) -> np.ndarray:
        """Returns the current voltage per division for the specified channels.

        Parameters:
            channels:   A single channel number or a list of selected channels. Use "all" for all channels.

        Returns:
            v_division: An array of division values, respective to the size of given input channels.
        """
        checked_chs = self._channels_check(channels)
        v_division = self._channel_value_getter(checked_chs, "VDIV", 12)

        return np.array(v_division, dtype=float)

    @rpc_method
    def get_max_waveform(self, channels: int | list[int] | str) -> np.ndarray:
        """Returns the current waveform maximum for the specified channels.

        WARNING: Undocumented feature.

        Parameters:
            channels: A single channel number or a list of selected channels. Use "all" for all channels.

        Returns:
            v_max: An array of waveform maximum voltage values, respective to the size of given input channels.
        """
        checked_chs = self._channels_check(channels)
        v_max = self._channel_value_getter(checked_chs, "MAXimum:VALUE", 19, "MEASure")

        return np.array(v_max, dtype=float)

    @rpc_method
    def set_channel_position(self, channels: int | list[int] | str, position: float | list[float]) -> None:
        """
        Changes the position of the specified channels in volts.
        """
        checked_chs = self._channels_check(channels)
        self._channel_value_setter(checked_chs, position, "POSition")

    @rpc_method
    def get_channel_position(self, channels: int | list[int] | str) -> np.ndarray:
        """
        Returns the current position for the specified channels in volts.
        """
        checked_chs = self._channels_check(channels)
        position = self._channel_value_getter(checked_chs, "POSition", 11)

        return np.array(position, dtype=float)

    @rpc_method
    def set_trigger_channel(self, channel: int) -> None:
        """Sets the channel used to set the trigger.

        Parameters:
            channel: The trigger channel number.
        """
        self._scpi_protocol.write(f":TRIGger:ATRigger:SIMPle:SOURce {channel}")

    @rpc_method
    def set_trigger_level(self, voltage: float) -> None:
        """Sets the level (in volts) of the trigger.

        Parameters:
            voltage: The trigger voltage level.
        """
        self._scpi_protocol.write(f":TRIGger:ATRigger:SIMPle:LEVel {voltage}V")

    @rpc_method
    def set_number_data_points(self, length: int) -> None:
        """Sets the scope acquire length.

        Parameters:
            length: The acquire length value.
        """
        self._scpi_protocol.write(f":ACQuire:RLENgth {length}")

    @rpc_method
    def get_number_data_points(self) -> int:
        """
        Gets the number of data points that will be saved.
        """
        return int(self._scpi_protocol.ask(":WAVeform:LENGth?")[10:])  # TODO: range 10:-1 needs to be checked with HW

    @rpc_method
    def set_average(self, average: int) -> None:
        """Sets the mode to average and set the average count.

         Parameters:
             average: Has to be between 2 and 1024 in 2**n steps.
        """
        self._scpi_protocol.write(":ACQUIRE:MODE AVERAGE")
        self._scpi_protocol.write(f":ACQUIRE:AVERAGE:COUNT {average}")

    @rpc_method
    def set_normal(self) -> None:
        """Sets acquisition mode to normal."""
        self._scpi_protocol.write(":ACQUIRE:MODE NORMAL")

    @rpc_method
    def save_file(self, name: str, data_type: str = "binary", waiting_time: float = 12.0) -> None:
        """Saves in the internal memory the file with a name "nameXXX.csv".
        Here XXX labels the files that have the same name with numbers from 000 to 999.

        Parameters:
            name:         The preposition of the file name.
            data_type:    Specify with type: 'binary' for raw data and 'ascii' for csv data.
            waiting_time: Time to wait for saving the file. In seconds.
        """
        data_type = self._data_type_check(data_type)

        # Stop in order to acquire the data
        self._scpi_protocol.write(":STOP")
        # Parameters of the saved file
        self._scpi_protocol.write(":WAV:FORM BYTE")
        _ = self.get_number_data_points()
        self._scpi_protocol.write(f":FILE:SAVE:NAME {name}")
        self._scpi_protocol.write(f":FILE:SAVE:{data_type}:EXECute")
        # waits until the save is completed
        time.sleep(waiting_time)
        # Starts again, notice that at least a time of 10*time_division is needed to get a full spectrum after starting
        self._scpi_protocol.write(":START")

    @rpc_method
    def find_file_name(self, name: str, select_files: str = "last") -> list[str]:
        """Finds the files in the oscilloscope with names 'nameXXX.csv'.
        It can be chosen whether to return the last file created with that name (higher XXX) with select_files = 'last'
        or to return all of them with select_files = 'all'.

        The full name including the label numbers can be specified to find a specific file.

        Parameters:
            name:         Preposition of file names to find.
            select_files: Optional parameter to select only the "last" file (default) or "all" the files.
        """
        # Get all files from the oscilloscope
        list_files = os.listdir(self._directory_oscilloscope)
        name = name.upper()
        if select_files == "last":
            # Start routine to get the last file with the introduced name
            for i in range(len(list_files)):
                # Go through the list in inverse order to find the last file created first
                file_name = list_files[-i - 1]
                if file_name.find(name) >= 0:
                    if len(file_name) == len(name) + 7:
                        return [file_name]

        elif select_files == "all":
            # Start routine to get all files with the same name
            file_names: list[str] = []
            for i in range(len(list_files)):
                file_name = list_files[i]
                if file_name.find(name) >= 0:
                    file_names.append(file_name)

            if len(file_names) > 0:
                return file_names

        else:
            raise QMI_UsageException(f"Invalid file selection '{select_files}")

        raise QMI_InstrumentException(f"Could not find any files starting with '{name}'")

    @rpc_method
    def copy_file(self, name: str, destination: str, select_files: str = "last") -> None:
        """
        Copies the files in the oscilloscope with names 'nameXXX.csv' to the destination.
        It can be chosen whether to copy the last file created with that name (higher XXX) with select_files = 'last'
        or to copy all of them with select_files = 'all'
        The full name including the label numbers can be specified to copy a specific file.

        Parameters:
            name:         Preposition of file names to find.
            destination:  Target directory to copy the file or files to.
            select_files: Optional parameter to select only the "last" file (default) or "all" the files.

        """
        file_names = self.find_file_name(name, select_files)
        for f in file_names:
            shutil.copy(f"{self._directory_oscilloscope}{f}", destination)

    @rpc_method
    def delete_file(self, name: str, select_files: str = "last", data_type: str = "binary") -> None:
        """Deletes files in the oscilloscope with names 'nameXXX.csv'.
        It can be chosen whether to delete the last file created with that name (higher XXX) with select_files = 'last'
        or to delete all of them with select_files = 'all'.

        Parameters:
            name:         Preposition of file names to find.
            select_files: Optional parameter to select only the "last" file (default) or "all" the files.
            data_type:    Specify with type: 'binary' for raw data and 'ascii' for csv data file.
        """
        data_type = self._data_type_check(data_type)

        # Stops in order to delete the data
        self.stop()
        file_names = self.find_file_name(name, select_files)
        for f in file_names:
            self._scpi_protocol.write(f':FILE:DELete:{data_type}:EXECute "{f[:-4]}"')

        # Starts again, notice that at least a time of 10*time_division is needed to get a full spectrum after starting
        self.start()
