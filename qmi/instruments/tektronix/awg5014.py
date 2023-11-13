"""QMI Instrument driver for the Tektronix's AWG 5014 arbitrary waveform generator."""
from pathlib import PureWindowsPath
import socket
from typing import List, Tuple, Union
import logging
import re
from time import time, sleep

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


AWG_FILE_BLOCK_DATA_LIMIT = 65E7


class Tektronix_Awg5014(QMI_Instrument):
    """QMI Instrument driver for the Tektronix AWG5014 Arbitrary Waveform Generator."""

    RESPONSE_TIMEOUT = 30
    NUM_CHANNELS = 4

    _instrument_status = {"0": "IDLE", "1": "WAIT_FOR_TRIGGER", "2": "RUNNING"}

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the driver.

        To connect to the instrument via Ethernet, specify transport descriptor "tcp:<IP-address>:4000".
        To connect to the instrument using VXI11, specify transport descriptor "vxi11:<IP-address>".
        WARNING: The following transport options have not been tested but should in principle work.
        To connect to the instrument via GPIB, specify transport descriptor "GPIB0:1:INSTR".
        To connect to the instrument via USB, specify transport descriptor
          "usbtmc:vendorid=0x0699:productid=0x0356:serialnr=<serial_number>".
        :END WARNING

        Parameters:
            context: The QMI context the instrument proxy is located.
            name: Name for this instrument instance.
            transport: Transport descriptor to access this instrument.
        """
        super().__init__(context, name)

        self._transport = create_transport(transport)
        self._scpi_transport = ScpiProtocol(self._transport, default_timeout=self.RESPONSE_TIMEOUT)

    def _check_error(self) -> None:
        """Read the instrument error queue and raise an exception if there is an error."""
        # Read error queue.
        resp = self._scpi_transport.ask("SYST:ERR?", discard=True)
        if not re.match(r"^\s*[+-]?0\s*,", resp):
            # Report the error.
            raise QMI_InstrumentException("Instrument returned error: {}".format(resp))

    def _check_channel_number(self, channel: int) -> None:
        if channel not in range(1, self.NUM_CHANNELS + 1):
            raise ValueError("Channel number must be in range [1-4].")

    def _get_memory_catalog(self) -> str:
        """Get a string with the total amount of storage used [bytes], free space left in the mass storage [bytes], and
        a list of file names and directories from instrument (from current directory).

        Returns:
            string <storage used>,<storage free>[,<file name>,<file type>,<file size>]*n for n files.
        """
        return self._scpi_transport.ask("MMEM:CAT?")

    @rpc_method
    def open(self) -> None:
        """Open the connection to the instrument."""
        self._check_is_closed()
        _logger.info("[%s] Opening connection to instrument", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        """Close the connection to the instrument."""
        self._check_is_open()
        _logger.info("[%s] Closing connection to instrument", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def wait_and_clear(self) -> None:
        """Wait and clear (responses of) previous command(s)."""
        # Wait until all pending commands are finished.
        self._scpi_transport.write("*WAI")
        try:
            # Clear out any possible hanging responses from the Tektronix
            self._scpi_transport.write("*CLS")

        except (QMI_TimeoutException, socket.timeout):
            # In case no hanging responses were present
            pass

        finally:
            # Clear transport buffer
            self._transport.discard_read()

    @rpc_method
    def wait_command_completion(self) -> None:
        """Wait completion of previous command."""
        self._scpi_transport.write("*OPC")
        start = time()
        try:
            while (time() - start) < self.RESPONSE_TIMEOUT:
                operation_complete = self._scpi_transport.ask("*OPC?")
                if operation_complete == "1":
                    break

                sleep(1)

        except (QMI_TimeoutException, socket.timeout):
            # We ignore timeout errors and go to check if there were errors from the controller
            pass

        finally:
            # Clear the error queue from "error" -800,"Operation complete"
            resp = self._scpi_transport.ask("SYST:ERR?", discard=True)
            if not re.match(r"^\s*-800\s*,", resp) and not re.match(r"^\s*[+-]?0\s*,", resp):
                # Report the error.
                raise QMI_InstrumentException(f"Instrument returned error: {resp}")

    @rpc_method
    def reset(self) -> None:
        """Resets the instrument to default values. In practise, it was seen that *CLS does not clear the memory as
        intended for stale responses. By making this as a query with discarding data in transport buffer, it clears
        up possible delayed response(s) from the scpi_protocol.
        """
        _logger.info("Resetting instrument [%s]", self._name)
        # Do reset
        self._scpi_transport.write("*RST")
        # Re-enable OPC
        self._scpi_transport.write("*OPC")
        try:
            self._scpi_transport.write("*CLS")
            self._transport.discard_read()

        except (QMI_TimeoutException, socket.timeout):
            # In case no hanging responses were present
            pass

    @rpc_method
    def get_error(self) -> None:
        """Allow client to poll for errors. Any errors will be raised as exceptions.

        Raises:
            QMI_InstrumentException with any error code other than 0.
        """
        self._check_error()

    @rpc_method
    def get_state(self) -> str:
        """Queries the instrument state. Possible responses are 0: IDLE, 1: WAIT_FOR_TRIGGER, 2: RUNNING.

        Returns:
            Instrument state translated from dictionary.
        """
        state = self._scpi_transport.ask("AWGC:RSTATE?")
        return self._instrument_status[state.strip()]

    @rpc_method
    def get_setup_file_name(self) -> Tuple[str, str]:
        """Returns the current setup file name of the arbitrary waveform generator.
           The response contains the full path for the file including the disk drive.
           Example: '"\\my\\project\\awg\\setup\\a1.awg","D:"'

        Returns:
            tuple: File path and name, e.g. ("\\Users\\OEM\\Documents", "newAWGfile.awg").
        """
        resp = PureWindowsPath(self._scpi_transport.ask("AWGC:SNAM?"))
        return str(resp.parent).lstrip('"'), resp.name.split(",")[0].rstrip('"')

    @rpc_method
    def get_file_names(self) -> List[str]:
        """Get a string with a list of file names from instrument.

        Returns:
            List [<file name>,<file type>,<file size>]*n for n files.
        """
        catalog = self._get_memory_catalog()
        catalog_list = catalog.split('"')[1:]  # drop off the storage info
        files = ""
        for entry in catalog_list:
            if ",DIR," not in entry and len(entry) > 1:
                files = files + f"{entry};"

        return files.rstrip(";").split(";")  # Remove last semi-colon and split into a list

    @rpc_method
    def get_directories(self) -> List[str]:
        """Return the directory contents from memory.

        Returns:
            List [<dir name>]*n for n directories.
        """
        catalog = self._get_memory_catalog()
        catalog_list = catalog.split('"')[1:]  # drop off the storage info
        directories = ""
        for entry in catalog_list:
            if ",DIR," in entry:
                dir_name = entry.split(",")[0]
                directories = directories + f"{dir_name};"

        return directories.rstrip(";").split(";")  # Remove last semi-colon

    @rpc_method
    def get_current_directory_name(self) -> str:
        """Return the current directory name from memory.

        Returns:
            Current directory name.
        """
        return self._scpi_transport.ask("MMEM:CDIR?").strip()

    @rpc_method
    def change_directory(self, cd: str) -> None:
        """Change the current directory.

        Parameters:
            cd: The new directory to cd to, in form "\\DIR1\\DIR2" or "C:\\DIR1\\DIR2" or ".." etc.
        """
        self._scpi_transport.write(f'MMEM:CDIR "{cd}"')

    @rpc_method
    def cd_to_root(self) -> None:
        """Change directory to root."""
        self._scpi_transport.write('MMEM:CDIR "C:\\.."')

    @rpc_method
    def create_directory(self, new_dir: str) -> None:
        """Create a new subdirectory in the current directory.

        Parameters:
            new_dir: The new directory name
        """
        # First check that we don't try to create a duplicate
        directories = self.get_directories()
        if new_dir in directories:
            raise QMI_InstrumentException("Error: Directory already exists.")

        self._scpi_transport.write(f'MMEM:MDIR "{new_dir}"')

    @rpc_method
    def remove_directory(self, del_dir: str) -> None:
        """Remove a subdirectory in the current directory.

        Parameters:
            del_dir: The deletable directory name
        """
        # First check that we have a directory named as the deletable one
        directories = self.get_directories()
        if del_dir in directories:
            self._scpi_transport.write(f'MMEM:DEL "{del_dir}"')
            return

        raise QMI_InstrumentException("Error: Directory does not exist.")

    @rpc_method
    def send_awg_file(self, file_name: str, awg_file_block_data: bytes) -> None:
        """This command creates a file on the AWG from the input block data. The file is created with the given name
        into the current directory the AWG files system is on. The waveform data should be in integers (-1, 0, 1) as
        only this format is currently supported. Floats could be needed when one needs to have correct waveform when
        waveform contains more than (-1, 0, 1) (+/-peak and 0) values. Using integer format is faster. Note that the
        "MMEM[ory]:DATA has a limit of 650 000 000 bytes of data.

        From the "AWG5000 and AWG7000 Series Arbitrary Waveform Generators Programmer Manual", table 2-4, data block is
        explained as string:
            #512234xxxxx... where 5 indicates that the following 5 digits (12234) specify the length of the data in
            bytes; xxxxx... indicates actual data or #0xxxxx...<LF><&EOI>.

        As this command is slow with large AWG files, successive command calls without waiting for the sending to
        complete can cause errors. Therefore, it is recommended to call `wait_command_completion` after this command.

        Parameters:
            file_name:           The file name, e.g. "newAWGfile.awg".
            awg_file_block_data: Block data for the file in bytes, should be sum of values of io.BytesIO objects
                headers + channel records + waveform records + sequence records. Currently only integer format.
        """
        data_length: int = len(awg_file_block_data)
        if data_length > AWG_FILE_BLOCK_DATA_LIMIT:
            raise QMI_InstrumentException("Waveform data block length too large! Consider using more efficient " +
                                          "file encoding or direct control commands on instrument.")

        block_data = f"#{len(str(data_length))}{data_length}".encode("ascii") + awg_file_block_data
        self._scpi_transport.write_raw(f'MMEM:DATA "{file_name}",'.encode("ascii") + block_data)

    @rpc_method
    def load_awg_file(self, file_name: str) -> None:
        """This command shall load the given .awg file into the AWG memory. Note that it will also overwrite
        all the current instrument settings with the values in the file.

        As this command is slow with large AWG files, successive command calls without waiting for the upload to
        complete can cause errors. Therefore, it is recommended to call `wait_command_completion` after this command.

        Parameters:
            file_name: The file name, e.g. "newAWGfile.awg".
        """
        # First check that we have a file named as the input file
        files = self.get_file_names()
        for f in files:
            if file_name in f:
                self._scpi_transport.write(f'AWGC:SRES "{file_name}"')
                return

        raise QMI_InstrumentException(f"Error: File {file_name} not found.")

    @rpc_method
    def remove_file(self, del_file: str) -> None:
        """Remove a file in the current directory.

        Parameters:
            del_file: The deletable file name
        """
        # First check that we have a file named as the deletable one
        files = self.get_file_names()
        for f in files:
            if del_file in f:
                self._scpi_transport.write(f'MMEM:DEL "{del_file}"')
                return

        raise QMI_InstrumentException("Error: File does not exist.")

    @rpc_method
    def clear_waveforms(self) -> None:
        """Clears the waveforms on all channels by settings the waveform files to be '' (empty string)."""
        for i in range(1, self.NUM_CHANNELS + 1):
            self._scpi_transport.write(f'SOUR{i}:FUNC:USER ""')

    @rpc_method
    def delete_all_waveforms_from_list(self) -> None:
        """Deletes all waveforms from memory list."""
        self._scpi_transport.write("WLIS:WAV:DEL ALL")

    @rpc_method
    def start(self) -> None:
        """Initiates the output of a waveform or a sequence.

        As this command can run for a relatively long time, successive command calls can cause errors. Therefore,
        it is recommended to call `wait_command_completion` after this command.
        """
        self._scpi_transport.write("AWGC:RUN")

    @rpc_method
    def stop(self) -> None:
        """Stops the output of a waveform or a sequence."""
        self._scpi_transport.write("AWGC:STOP")

    @rpc_method
    def get_clock_source(self) -> str:
        """Query the AWG whether the 10MHz is set to the internal or external source.

        Returns:
            "INT" or "EXT"
        """
        return self._scpi_transport.ask("AWGC:CLOC:SOUR?")

    @rpc_method
    def set_clock_to_internal(self) -> None:
        """Set the clock source to be internal."""
        self._scpi_transport.write(f"AWGC:CLOC:SOUR INT")

    @rpc_method
    def set_clock_to_external(self) -> None:
        """Set the clock source to be external."""
        self._scpi_transport.write(f"AWGC:CLOC:SOUR EXT")

    @rpc_method
    def get_reference_oscillator_source(self) -> str:
        """Query the AWG whether the 10MHz reference is set to the internal or external source.

        Returns:
            "INT" or "EXT"
        """
        return self._scpi_transport.ask("ROSC:SOUR?").strip()

    @rpc_method
    def set_reference_oscillator_to_internal(self) -> None:
        """Set the 10MHz reference source to be internal."""
        self._scpi_transport.write(f"ROSC:SOUR INT")

    @rpc_method
    def set_reference_oscillator_to_external(self) -> None:
        """Set the 10MHz reference source to be external."""
        self._scpi_transport.write(f"ROSC:SOUR EXT")

    @rpc_method
    def get_reference_oscillator_type(self) -> str:
        """Query the type of the reference oscillator.

        Returns:
            Reference oscillator type.
        """
        return self._scpi_transport.ask("ROSC:TYPE?").strip()

    @rpc_method
    def set_reference_oscillator_type(self, type: str) -> None:
        """Set the reference oscillator type to fixed or variable.

        Parameters:
              Reference oscillator type ["FIX" or "VAR"]
        """
        if type.upper() not in ["FIX", "VAR"]:
            raise ValueError(f"Unknown reference oscillator type {type}!")

        self._scpi_transport.write(f"ROSC:TYPE {type}")

    @rpc_method
    def get_reference_clock_frequency(self) -> float:
        """Query the reference clock frequency.

        Returns:
            The reference clock frequency in Hertz. Possible values 1E7, 2E7, 1E8.
        """
        return float(self._scpi_transport.ask("ROSC:FREQ?"))

    @rpc_method
    def set_reference_clock_frequency(self, frequency: float) -> None:
        """Set the reference clock frequency. The possible values are 10, 20 and 100 MHz.

        Parameters:
            frequency: The new reference clock frequency in Hertz.
        """
        mhz_dict = {1E7: "10MHZ", 2E7: "20MHZ", 10E7: "100MHZ"}
        if frequency not in mhz_dict.keys():
            raise ValueError("Error: New reference clock frequency is any of valid values [10, 20, 100] MHz!")

        self._scpi_transport.write(f"ROSC:FREQ {mhz_dict[frequency]}")

    @rpc_method
    def get_source_clock_frequency(self) -> float:
        """Query the source clock frequency.

        Returns:
            The source clock frequency in Hertz.
        """
        return float(self._scpi_transport.ask("SOUR:FREQ?"))

    @rpc_method
    def set_source_clock_frequency(self, frequency: float) -> None:
        """Set the source clock frequency. This will work either if "INT" is selected as reference source or
        reference source is set as "EXT" and reference type as "FIX".

        Parameters:
            frequency: The new source clock frequency in Hertz.
        """
        if frequency < 10E6 or frequency > 10E9:
            raise ValueError("Error: New source clock frequency is out of valid range of 10Mhz and 10GHz!")

        if self.get_reference_oscillator_source() == "INT":
            self._scpi_transport.write(f"SOUR:FREQ {frequency:.7G}")

        elif self.get_reference_oscillator_type() == "FIX":
            self._scpi_transport.write(f"SOUR:FREQ:FIX {frequency:.7G}")

        else:
            raise RuntimeError("Error: Can set frequency either when source oscillator source is 'INT', or " +
                               "when source oscillator is 'EXT' and source oscillator type is 'FIX'.")

    @rpc_method
    def get_amplitude(self, channel: int) -> float:
        """Get the signal amplitude of a waveform associated with specific channel.

        Parameters:
            channel: The channel number [1-4].

        Returns:
            The peak-to-peak signal amplitude in Volts.
        """
        self._check_channel_number(channel)
        return float(self._scpi_transport.ask(f"SOUR{channel}:VOLT:LEV:IMM:AMPL?"))

    @rpc_method
    def set_amplitude(self, channel: int, amplitude: float) -> None:
        """Set the signal amplitude for a waveform associated with specific channel.

        Parameters:
            channel: The channel number [1-4].
            amplitude: The target amplitude voltage (peak-to-peak).
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f"SOUR{channel}:VOLT:LEV:IMM:AMPL {amplitude:.6f}")

    @rpc_method
    def get_offset(self, channel: int) -> float:
        """Get the offset of a specific source channel.

        Parameters:
            channel: The channel number [1-4].

        Returns:
            The offset in Volts.
        """
        self._check_channel_number(channel)
        return float(self._scpi_transport.ask(f"SOUR{channel}:VOLT:LEV:IMM:OFFS?"))

    @rpc_method
    def set_offset(self, channel: int, offset: float) -> None:
        """Set the offset of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            offset: The offset in Volts
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f"SOUR{channel}:VOLT:LEV:IMM:OFFS {offset:.6f}")

    @rpc_method
    def get_dc_output_state(self) -> int:
        """Query if DC output state is 'on' or 'off'. The state is equal to all four DC outputs.

        Returns:
            DC state with 0 as 'off' and 1 as 'on'.
        """
        return int(self._scpi_transport.ask("AWGC:DC:STAT?"))

    @rpc_method
    def set_dc_output_state(self, state: int) -> None:
        """Set DC state as 'on' or 'off'. The command sets the same state for all four DC outputs.

        Parameters:
            state: DC state with 0 as 'off' and 1 as 'on'.
        """
        self._scpi_transport.write(f"AWGC:DC:STAT {state}")

    @rpc_method
    def get_dc_output_offset(self, output: int) -> float:
        """Get a DC output voltage offset.

        Parameters:
            output: DC output number in range [1-4].

        Returns:
            The offset in Volts.
        """
        self._check_channel_number(output)
        return float(self._scpi_transport.ask(f"AWGC:DC{output}:VOLT:OFFS?"))

    @rpc_method
    def set_dc_output_offset(self, output: int, offset: float) -> None:
        """Set a DC output voltage offset.

        Parameters:
            output: DC output number in range [1-4].
            offset: The offset in Volts, should be between [-3.0V-+5.0V].
        """
        self._check_channel_number(output)
        self._scpi_transport.write(f"AWGC:DC{output}:VOLT:OFFS {offset}V")

    @rpc_method
    def get_raw_dac_waveform_output(self, channel: int) -> int:
        """Get raw DAC waveform output channel state.

        Parameters:
            channel: DAC output channel number in range [1-4].

        Returns:
            Channel state with 0 as 'disabled' and 1 as 'enabled'.
        """
        self._check_channel_number(channel)
        return int(self._scpi_transport.ask(f"AWGC:DOUT{channel}:STAT?"))

    @rpc_method
    def set_raw_dac_waveform_output(self, channel: int, state: int) -> None:
        """Set raw DAC waveform output channel state. Channel state with 0 as 'disabled' and 1 as 'enabled'.

        Parameters:
            channel: DAC output channel number in range [1-4].
            state: Channel state with 0 as 'disabled' and 1 as 'enabled'.
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f"AWGC:DOUT{channel}:STAT {state}")

    @rpc_method
    def get_run_mode(self) -> str:
        """Get the current run mode.

        Returns:
            mode: The run mode.
        """
        return self._scpi_transport.ask("AWGC:RMOD?").strip()

    @rpc_method
    def set_run_mode_to_triggered(self) -> None:
        """Set the run mode to TRIGgered."""
        self._scpi_transport.write("AWGC:RMOD TRIG")

    @rpc_method
    def set_run_mode_to_continuous(self) -> None:
        """Set the run mode to CONTinuous."""
        self._scpi_transport.write("AWGC:RMOD CONT")

    @rpc_method
    def set_run_mode(self, run_mode: str) -> None:
        """Set new run mode.

        Parameters:
            run_mode: new run mode. Must be one of 'CONT', 'TRIG', 'SEQ' or 'GAT'. Also 'ENH' is possible for
                      compatibility reasons with other model series. 'ENH' is equal to 'SEQ'.
        """
        if run_mode.upper() not in ["CONT", "TRIG", "SEQ", "GAT", "ENH"]:
            raise ValueError(f"Invalid run mode {run_mode}")

        self._scpi_transport.write(f"AWGC:RMOD {run_mode}")

    @rpc_method
    def get_signal_addition(self) -> str:
        """Query the signal addition from external input state.

        Returns:
            The signal addition state. "ESIG" for enabled, "" for disabled.
        """
        return self._scpi_transport.ask("COMB:FEED?").strip()

    @rpc_method
    def set_signal_addition(self, state: str) -> None:
        """Set the signal addition from external input state.

        Parameters:
            state: The signal addition state. "ESIG" for enabled, "" for disabled.
        """
        self._scpi_transport.write(f'COMB:FEED "{state}"')

    @rpc_method
    def get_trigger_source(self) -> str:
        """Query the current trigger source."""
        return self._scpi_transport.ask("TRIG:SOUR?").strip()

    @rpc_method
    def set_trigger_source_to_internal(self) -> None:
        """Set the trigger source to INTernal."""
        self._scpi_transport.write("TRIG:SOUR INT")

    @rpc_method
    def set_trigger_source_to_external(self) -> None:
        """Set the trigger source to EXTernal."""
        self._scpi_transport.write("TRIG:SOUR EXT")

    @rpc_method
    def get_trigger_impedance(self) -> int:
        """Get the current external trigger impedance in Ohm.

        Returns:
            Trigger impedance value.
        """
        return int(float(self._scpi_transport.ask("TRIG:IMP?")))

    @rpc_method
    def set_trigger_impedance(self, impedance: int = 1000) -> None:
        """Sets the EXTERNAL trigger impedance to given value. Default value is 1000 Ohm. 50 Ohm is for the external
        trigger input.

        Parameters:
            impedance: The trigger impedance in Ohm. Possible values are 50 and 1000.
        """
        if impedance not in [50, 1000]:
            raise ValueError(f"Invalid impedance {impedance} Ohm. Must be either 50 Ohm or 1000 Ohm.")

        self._scpi_transport.write(f"TRIG:IMP {impedance}")

    @rpc_method
    def get_trigger_level(self) -> float:
        """Get current trigger level in Volts.

        Returns:
            Current trigger level.
        """
        return float(self._scpi_transport.ask("TRIG:LEV?"))

    @rpc_method
    def set_trigger_level(self, trigger_level: float) -> None:
        """Set a new trigger level. The value is rounded to 3 significant decimals.

        Parameters:
            trigger_level: The new trigger level in Volts.
        """
        self._scpi_transport.write(f"TRIG:LEV {trigger_level:.3f}")

    @rpc_method
    def get_trigger_slope(self) -> str:
        """Get trigger slope sign.

        Returns:
            Trigger slope sign as "POS" or "NEG".
        """
        return self._scpi_transport.ask("TRIG:SLOP?").strip()

    @rpc_method
    def set_trigger_slope(self, slope: str) -> None:
        """Set trigger slope sign.

        Parameters:
            Trigger slope sign as string "POS" or "POSitive" for positive slope and "NEG" or "NEGative" for
            negative slope.
        """
        if slope.upper() in ["POS", "POSITIVE"]:
            target_slope = "POSitive"

        elif slope.upper() in ["NEG", "NEGATIVE"]:
            target_slope = "NEGative"

        else:
            raise ValueError(f"Invalid slope sign {slope}")

        self._scpi_transport.write(f"TRIG:SLOP {target_slope}")

    @rpc_method
    def get_trigger_polarity(self) -> str:
        """Get trigger polarity sign.

        Returns:
            Trigger polarity sign as "POS" or "NEG".
        """
        return self._scpi_transport.ask("TRIG:POL?").strip()

    @rpc_method
    def set_trigger_polarity(self, polarity: str) -> None:
        """Set trigger polarity sign.

        Parameters:
            polarity: Trigger polarity sign as string "POS" or "POSitive" for positive polarity and "NEG" or "NEGative"
                      for negative polarity.
        """
        if polarity.upper() in ["POS", "POSITIVE"]:
            target_polarity = "POSitive"

        elif polarity.upper() in ["NEG", "NEGATIVE"]:
            target_polarity = "NEGative"

        else:
            raise ValueError(f"Invalid polarity sign {polarity}")

        self._scpi_transport.write(f"TRIG:POL {target_polarity}")

    @rpc_method
    def get_waveform_output_data_position(self) -> str:
        """Query The output data position of a waveform while the instrument is in the waiting-for-trigger state.
        This is valid only when Run Mode is Triggered or Gated.

        Returns:
            Waveform output data position as "FIRS" or "LAST".
        """
        return self._scpi_transport.ask("TRIG:SEQ:WVAL?").strip()

    @rpc_method
    def set_waveform_output_data_position(self, position: str) -> None:
        """
        This command sets the output data position of a waveform. This is valid only when
        Run Mode is Triggered or Gated.

        Parameters:
            position: Sets a position of a waveform as the output level. Possible values are "FIRS[t]" and "LAST".
        """
        if position.upper() not in ["FIRS", "FIRST", "LAST"]:
            raise ValueError(f"Invalid waveform position {position}")

        # Check the current Run mode before allowing to set
        if self.get_run_mode() not in ["TRIG", "GAT"]:
            raise QMI_InstrumentException("The Run mode must be Triggered or Gated to set WF output data position")

        self._scpi_transport.write(f"TRIG:SEQ:WVAL {position}")

    @rpc_method
    def force_trigger_event(self) -> None:
        """Generate a trigger event."""
        self._scpi_transport.write("*TRG")

    @rpc_method
    def get_channel_state(self, channel: int) -> bool:
        """Query if a channel is 'on' or 'off.

        Parameters:
            channel: Channel number in range [1-4].

        Returns:
            The channel state with False if 'off' and True if 'on'.
        """
        self._check_channel_number(channel)
        return bool(int(self._scpi_transport.ask(f"OUTP{channel}?")))

    @rpc_method
    def set_channel_state(self, channel: int, state: bool) -> None:
        """Set a channel state 'on' or 'off.

        Parameters:
            channel: Channel number in range [1-4].
            state: The new channel state with False if 'off' and True if 'on'.
        """
        set_state = "ON" if state else "OFF"
        self._check_channel_number(channel)
        self._scpi_transport.write(f"OUTP{channel} {set_state}")

    @rpc_method
    def get_low_pass_filter_frequency(self, channel: int) -> float:
        """Query low-pass filter frequency of an output channel.

        Parameters:
            channel: Channel number in range [1-4].

        Returns:
            The output channel filter frequency in MHz (9.9e37 at INFinity).
        """
        self._check_channel_number(channel)
        return float(self._scpi_transport.ask(f"OUTP{channel}:FILT:FREQ?"))

    @rpc_method
    def set_low_pass_filter_frequency(self, channel: int, frequency: Union[float, str]) -> None:
        """Set a low-pass filter frequency of an output channel frequency.

        Parameters:
            channel: Channel number in range [1-4].
            frequency: The new channel frequency in Hertz. Or "INF".
        """
        self._check_channel_number(channel)
        if isinstance(frequency, float):
            self._scpi_transport.write(
                f"OUTP{channel}:FILT:FREQ {frequency:.1E}".replace("E+0", "E+").replace("E-0", "E0")
            )

        elif isinstance(frequency, str):
            if frequency.upper() not in ["INF", "INFINITY"]:
                raise ValueError(f"Low pass filer frequency cannot be {frequency}, use a float or 'INFinity'")

            self._scpi_transport.write(f"OUTP{channel}:FILT:FREQ INFinity")

    @rpc_method
    def get_sequence_length(self) -> int:
        """Get sequence length.

        Returns:
            The sequence length.
        """
        return int(self._scpi_transport.ask("SEQ:LENG?"))

    @rpc_method
    def set_sequence_length(self, length: int) -> None:
        """Set sequence length. Note: length 0 will delete the sequence.

        Parameters:
            length: The sequence length.
        """
        self._scpi_transport.write(f"SEQ:LENG {length}")

    @rpc_method
    def get_sequencer_type(self) -> str:
        """Get the sequencer type to see if instrument is in hardware or software sequencer mode.

        Returns:
            Sequencer type, either "HARD" or "SOFT".
        """
        return self._scpi_transport.ask("AWGC:SEQ:TYPE?").strip()

    @rpc_method
    def get_sequencer_position(self) -> int:
        """Get the sequencer position.

        Returns:
            Sequencer position.
        """
        return int(self._scpi_transport.ask("AWGC:SEQ:POS?"))

    @rpc_method
    def set_sequence_element_goto_target_index(self, element_no: int, index_no: int) -> None:
        """Set target 'GOTO' index of a sequencer element. Note: First element is 1:

        Parameters:
            element_no: Element number.
            index_no: Target goto index number.
        """
        if index_no == 0:
            raise ValueError("Error: The sequence element indexing starts from 1, not from 0!")

        self._scpi_transport.write(f"SEQ:ELEM{element_no}:GOTO:IND {index_no}")

    @rpc_method
    def set_sequence_element_goto_state(self, element_no: int, goto_state: int) -> None:
        """Set 'GOTO' state for a sequencer element.

        Parameters:
            element_no: Element number.
            goto_state: New 'GOTO' state. 0 is 'off' and 1 is 'on'.
        """
        self._scpi_transport.write(f"SEQ:ELEM{element_no}:GOTO:STAT {goto_state}")

    @rpc_method
    def get_sequence_element_loop_count_infinite_state(self, element_no: int) -> bool:
        """Query the loop count infinity state of a sequencer element.

        Parameters:
            element_no: Element number.

        Returns:
            boolean, if the loop count to inf is 'on' = True or 'off' = False.
        """
        resp = self._scpi_transport.ask(f"SEQ:ELEM{element_no}:LOOP:INF?")
        return bool(int(resp))

    @rpc_method
    def set_sequence_element_loop_count_infinite_state(self, element_no: int, on: bool = True) -> None:
        """Set the loop count to infinity state for a sequencer element. Can be 'on' or 'off'.

        Parameters:
            element_no: Element number.
            on: boolean to set loop count to inf 'on' (True) or 'off' (False).
        """
        if on:
            self._scpi_transport.write(f"SEQ:ELEM{element_no}:LOOP:INF 1")

        else:
            self._scpi_transport.write(f"SEQ:ELEM{element_no}:LOOP:INF 0")

    @rpc_method
    def get_sequence_element_loop_count(self, element_no: int) -> int:
        """Get the loop count from a sequencer element.

        Parameters:
            element_no: Element number.

        Returns:
            Sequence element loop count.
        """
        return int(self._scpi_transport.ask(f"SEQ:ELEM{element_no}:LOOP:COUN?"))

    @rpc_method
    def set_sequence_element_loop_count(self, element_no: int, loop_count: int) -> None:
        """Set the loop count to given value for a sequencer element.

        Parameters:
            element_no: Element number.
            loop_count: The new loop count value in the range of [1, 65536]
        """
        if loop_count < 1 or loop_count > 65536:
            raise ValueError(f"Error: Invalid loop count value {loop_count}.")

        self._scpi_transport.write(f"SEQ:ELEM{element_no}:LOOP:COUN {loop_count}")

    @rpc_method
    def get_sequence_element_trigger_wait_state(self, element_no: int) -> int:
        """Get trigger wait state from a sequence element.

        Parameters:
            element_no: Element number.

        Returns:
            The sequence element trigger wait state. 0 for 'off', 1 for 'on'.
        """
        return int(self._scpi_transport.ask(f"SEQ:ELEM{element_no}:TWA?"))

    @rpc_method
    def set_sequence_element_trigger_wait_state(self, element_no: int, state: int) -> None:
        """Set trigger wait value state for a sequence element.

        Parameters:
            element_no: Element number.
            state: Trigger wait state. 0 for 'off', 1 for 'on'.
        """
        self._scpi_transport.write(f"SEQ:ELEM{element_no}:TWA {state}")

    @rpc_method
    def get_sequence_element_waveform(self, element_no: int, channel: int) -> str:
        """Get waveform from a sequence element channel.

        Parameters:
            element_no: Element number.
            channel: Channel number.

        Returns:
            The waveform type of the sequence element channel.
        """
        self._check_channel_number(channel)
        return self._scpi_transport.ask(f"SEQ:ELEM{element_no}:WAV{channel}?", discard=True).strip()

    @rpc_method
    def set_sequence_element_waveform(self, element_no: int, channel: int, waveform: str) -> None:
        """Set waveform for a sequence element channel.

        Parameters:
            element_no: Element number.
            channel: Channel number.
            waveform: Waveform type.
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f'SEQ:ELEM{element_no}:WAV{channel} "{waveform}"')

    @rpc_method
    def force_sequence_jump_to_index(self, jump_index_no: int) -> None:
        """Force sequence to jump to given index immediately.

        Parameters:
            jump_index_no: Target index number to jump to.
        """
        self._scpi_transport.write(f"SEQ:JUMP:IMM {jump_index_no}")

    @rpc_method
    def set_sequence_element_jump_target_index(self, element_no: int, jump_target_index: int) -> None:
        """Set sequence element event jump target index.

        Parameters:
            element_no: Element number.
            jump_target_index: The target index number.
        """
        self._scpi_transport.write(f"SEQ:ELEM{element_no}:JTAR:INDEX {jump_target_index}")

    @rpc_method
    def get_sequence_element_jump_type(self, element_no: int) -> str:
        """Get sequence element event jump type.

        Parameters:
            element_no: Element number.

        Returns:
            The jump type.
        """
        return self._scpi_transport.ask(f"SEQ:ELEM{element_no}:JTAR:TYPE?").strip()

    @rpc_method
    def set_sequence_element_jump_type(self, element_no: int, jump_type: str) -> None:
        """Set sequence element event jump type.

        Parameters:
            element_no: Element number.
            jump_type: The new jump type. Valid values are 'IND', 'NEXT', and 'OFF'.
        """
        if jump_type.upper() not in ["IND", "NEXT", "OFF"]:
            raise ValueError("Error: Invalid event jump target type.")

        self._scpi_transport.write(f"SEQ:ELEM{element_no}:JTAR:TYPE {jump_type}")

    @rpc_method
    def get_sequence_jump_mode(self) -> str:
        """Queries the sequence jump mode.

        Returns:
            Jump mode.
        """
        return self._scpi_transport.ask("AWGC:ENH:SEQ:JMOD?").strip()

    @rpc_method
    def set_sequence_jump_mode(self, jump_mode: str) -> None:
        """Set the sequence jump mode.

        Parameters:
            jump_mode: The jump mode, valid values are "LOG", "TABL" and "SOFT".
        """
        if jump_mode not in ["LOG", "TABL", "SOFT"]:
            raise ValueError(f"Error: Invalid jump mode {jump_mode}.")

        self._scpi_transport.write(f"AWGC:ENH:SEQ:JMOD {jump_mode}")

    @rpc_method
    def get_jump_target_definition(self, pattern: int) -> int:
        """Queries the dynamic jump target associated to specified event pattern.

        Parameters:
            pattern: The event pattern in range [0-511].

        Returns:
            The sequence index number associated to the event pattern.
        """
        return int(self._scpi_transport.ask(f"AWGC:EVEN:DJUM:DEF? {pattern}"))

    @rpc_method
    def set_jump_target_definition(self, pattern: int, jump_target: int) -> str:
        """Queries the dynamic jump target associated to specified event pattern.

        Parameters:
            pattern: The event pattern in range [0-511].
            jump_target: The target sequence index value, allowed values are [-1-511].

        Returns:
            The dynamic jump target associated to the event pattern.
        """
        return self._scpi_transport.ask(f"AWGC:EVEN:DJUM:DEF {pattern},{jump_target}").strip()

    @rpc_method
    def get_event_jump_mode(self) -> str:
        """Get event jump mode.

        Returns:
            The event jump mode.
        """
        return self._scpi_transport.ask("AWGC:EVEN:JMOD?").strip()

    @rpc_method
    def set_event_jump_mode(self, jump_mode: str) -> None:
        """Set the event jump mode.

        Parameters:
            jump_mode: The event jump mode, e.g. DJUMP, EJUMP.
        """
        self._scpi_transport.write(f"AWGC:EVEN:JMOD {jump_mode}")

    @rpc_method
    def get_event_jump_timing_mode(self) -> str:
        """Get event jump timing mode.

        Returns:
            Event jump timing mode.
        """
        return self._scpi_transport.ask("EVEN:JTIM?").strip()

    @rpc_method
    def set_event_jump_timing_mode(self, mode: str) -> None:
        """Set event jump timing mode to synchronous or to asynchronous.

        Parameters:
            Event jump timing mode. Valid modes are "SYNC" and "ASYN"
        """
        self._scpi_transport.write(f"EVEN:JTIM {mode}")

    @rpc_method
    def get_event_input_impedance(self) -> int:
        """Get external event input impedance.

        Returns:
            Impedance in Ohm. Possible values are 50 and 1000.
        """
        return int(float(self._scpi_transport.ask("EVEN:IMP?")))

    @rpc_method
    def set_event_input_impedance(self, impedance: int) -> None:
        """Set external event input impedance.

        Parameters:
            Impedance in Ohm. Possible values are 50 and 1000.
        """
        if impedance not in [50, 1000]:
            raise ValueError(f"Invalid impedance value {impedance}. Must be either 50 or 1000.")

        self._scpi_transport.write(f"EVEN:IMP {impedance}")

    @rpc_method
    def get_event_input_polarity(self) -> str:
        """Get event input polarity sign.

        Returns:
            Event input polarity sign as "POS" or "NEG".
        """
        return self._scpi_transport.ask("EVEN:POL?").strip()

    @rpc_method
    def set_event_input_polarity(self, polarity: str) -> None:
        """Set event input polarity sign.

        Parameters:
            Event input polarity sign as string "POS" or "POSitive" for positive polarity and "NEG" or "NEGative" for
            negative polarity.
        """
        if polarity.upper() in ["POS", "POSITIVE"]:
            target_polarity = "POSitive"

        elif polarity.upper() in ["NEG", "NEGATIVE"]:
            target_polarity = "NEGative"

        else:
            raise ValueError(f"Invalid polarity sign {polarity}")

        self._scpi_transport.write(f"EVEN:POL {target_polarity}")

    @rpc_method
    def get_event_level(self) -> float:
        """Get the event level voltage.

        Returns:
            The event level in Volts.
        """
        return float(self._scpi_transport.ask("EVEN:LEV?"))

    @rpc_method
    def set_event_level(self, level: float) -> None:
        """Set the event level voltage.

        Parameters:
            level: The target level voltage.
        """
        self._scpi_transport.write(f"EVEN:LEV {level:.6f}V")

    @rpc_method
    def get_marker_low(self, channel: int, marker: int) -> float:
        """Get the low level for a marker of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            marker: The marker number [1-2].

        Returns:
            The low level in Volts.
        """
        self._check_channel_number(channel)
        return float(self._scpi_transport.ask(f"SOUR{channel}:MARK{marker}:VOLT:LEV:IMM:LOW?"))

    @rpc_method
    def set_marker_low(self, channel: int, marker: int, low_level: float) -> None:
        """Set the low level for a marker of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            marker: The marker number [1-2].
            low_level: The low level in Volts.
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f"SOUR{channel}:MARK{marker}:VOLT:LEV:IMM:LOW {low_level:.3f}")

    @rpc_method
    def get_marker_high(self, channel: int, marker: int) -> float:
        """Get the high level for a marker of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            marker: The marker number [1-2].

        Returns:
            The high level in Volts.
        """
        self._check_channel_number(channel)
        return float(self._scpi_transport.ask(f"SOUR{channel}:MARK{marker}:VOLT:LEV:IMM:HIGH?"))

    @rpc_method
    def set_marker_high(self, channel: int, marker: int, high_level: float) -> None:
        """Set the high level for a marker of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            marker: The marker number [1-2].
            high_level: The high level in Volts.
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f"SOUR{channel}:MARK{marker}:VOLT:LEV:IMM:HIGH {high_level:.3f}")

    @rpc_method
    def get_marker_delay(self, channel: int, marker: int) -> float:
        """Query a marker delay of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            marker: The marker number [1-2].

        Returns:
            The delay in seconds.
        """
        self._check_channel_number(channel)
        return float(self._scpi_transport.ask(f"SOUR{channel}:MARK{marker}:DEL?"))

    @rpc_method
    def set_marker_delay(self, channel: int, marker: int, delay: float) -> None:
        """Set a marker delay of a specific source channel.

        Parameters:
            channel: The channel number [1-4].
            marker: The marker number [1-2].
            delay: The delay in seconds.
        """
        self._check_channel_number(channel)
        self._scpi_transport.write(f"SOUR{channel}:MARK{marker}:DEL {delay}")
