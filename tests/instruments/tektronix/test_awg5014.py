"""Unit tests for Tektronix AWG 5014 QMI driver."""

import unittest
from unittest.mock import MagicMock, call, patch

import enum
import struct
from io import BytesIO
from time import time, localtime, sleep
from typing import Union, cast
import logging

import numpy as np

import qmi
from qmi.utils.context_managers import open_close
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.tektronix import Tektronix_Awg5014


### GLOBALS ###
AWG_FILE_FORMAT_HEAD = {
    "SAMPLING_RATE": "d",  # d
    "REPETITION_RATE": "d",  # # NAME?
    "HOLD_REPETITION_RATE": "h",  # True | False
    "CLOCK_SOURCE": "h",  # Internal | External
    "REFERENCE_SOURCE": "h",  # Internal | External
    "EXTERNAL_REFERENCE_TYPE": "h",  # Fixed | Variable
    "REFERENCE_CLOCK_FREQUENCY_SELECTION": "h",
    "REFERENCE_MULTIPLIER_RATE": "h",  #
    "DIVIDER_RATE": "h",  # 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256
    "TRIGGER_SOURCE": "h",  # Internal | External
    "INTERNAL_TRIGGER_RATE": "d",  #
    "TRIGGER_INPUT_IMPEDANCE": "h",  # 50 ohm | 1 kohm
    "TRIGGER_INPUT_SLOPE": "h",  # Positive | Negative
    "TRIGGER_INPUT_POLARITY": "h",  # Positive | Negative
    "TRIGGER_INPUT_THRESHOLD": "d",  #
    "EVENT_INPUT_IMPEDANCE": "h",  # 50 ohm | 1 kohm
    "EVENT_INPUT_POLARITY": "h",  # Positive | Negative
    "EVENT_INPUT_THRESHOLD": "d",
    "JUMP_TIMING": "h",  # Sync | Async
    "INTERLEAVE": "h",  # On | Off: This setting is stronger than .
    "ZEROING": "h",  # On | Off
    "COUPLING": "h",  # The Off | Pair | All setting is weaker than .
    "RUN_MODE": "h",  # Continuous | Triggered | Gated | Sequence
    "WAIT_VALUE": "h",  # First | Last
    "RUN_STATE": "h",  # On | Off
    "INTERLEAVE_ADJ_PHASE": "d",
    "INTERLEAVE_ADJ_AMPLITUDE": "d",
}
AWG_FILE_FORMAT_CHANNEL = {
    "OUTPUT_WAVEFORM_NAME_N": "s",  # Include NULL.(Output Waveform Name for Non-Sequence mode)
    "CHANNEL_STATE_N": "h",  # On | Off
    "ANALOG_DIRECT_OUTPUT_N": "h",  # On | Off
    "ANALOG_FILTER_N": "h",  # Enum type.
    "ANALOG_METHOD_N": "h",  # Amplitude/Offset, High/Low
    "ANALOG_AMPLITUDE_N": "d",  # When the Input Method is High/Low, it is skipped.
    "ANALOG_OFFSET_N": "d",  # When the Input Method is High/Low, it is skipped.
    "ANALOG_HIGH_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "ANALOG_LOW_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "MARKER1_SKEW_N": "d",
    "MARKER1_METHOD_N": "h",  # Amplitude/Offset, High/Low
    "MARKER1_AMPLITUDE_N": "d",  # When the Input Method is High/Low, it is skipped.
    "MARKER1_OFFSET_N": "d",  # When the Input Method is High/Low, it is skipped.
    "MARKER1_HIGH_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "MARKER1_LOW_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "MARKER2_SKEW_N": "d",
    "MARKER2_METHOD_N": "h",  # Amplitude/Offset, High/Low
    "MARKER2_AMPLITUDE_N": "d",  # When the Input Method is High/Low, it is skipped.
    "MARKER2_OFFSET_N": "d",  # When the Input Method is High/Low, it is skipped.
    "MARKER2_HIGH_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "MARKER2_LOW_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "DIGITAL_METHOD_N": "h",  # Amplitude/Offset, High/Low
    "DIGITAL_AMPLITUDE_N": "d",  # When the Input Method is High/Low, it is skipped.
    "DIGITAL_OFFSET_N": "d",  # When the Input Method is High/Low, it is skipped.
    "DIGITAL_HIGH_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "DIGITAL_LOW_N": "d",  # When the Input Method is Amplitude/Offset, it is skipped.
    "EXTERNAL_ADD_N": "h",  # AWG5000 only
    "PHASE_DELAY_INPUT_METHOD_N": "h",  # Phase/DelayInme/DelayInints
    "PHASE_N": "d",  # When the Input Method is not Phase, it is skipped.
    "DELAY_IN_TIME_N": "d",  # When the Input Method is not DelayInTime, it is skipped.
    "DELAY_IN_POINTS_N": "d",  # When the Input Method is not DelayInPoint, it is skipped.
    "CHANNEL_SKEW_N": "d",
    "DC_OUTPUT_LEVEL_N": "d",  # V
}


class _Channels(enum.Enum):
    RED_EOM_CH = 1
    RED_AOM_CH = 4
    HYDRAHARP_MRK_CH = 2
    GREEN_MRK_CH = 3


class _Markers(enum.Enum):
    HYDRAHARP_MRK_CH = 1
    GREEN_MRK_CH = 2

# pars = np.sort(list(awg1.parameters.keys()))

# noofseqelems = 1
NO_OF_POINTS = 2200  # sample rate of 1.2GS/s so, 1 point is 0.8[333333333333...] ns[??]
# creating green pulse
SAMPLING_RATE_CONVERSION = 1.2e9  # or 1.25e9 to make exactly 0.8ns??
ZEROS_ARRAY = np.zeros(NO_OF_POINTS)
GREEN_TIME_PULSE = int(1e3)
GREEN_OFF_TIME = int(1e3)
RED_AOM_TIME = 20
RED_PULSE_TIME = 30
GREEN_PULSE = np.zeros(NO_OF_POINTS)
GREEN_PULSE[0:GREEN_TIME_PULSE] = 1
EXTRA_TIME = 0
DELAY = 20
# Trigger position
TRIGGER_ANTICIPATION = 100


def pack_record(name: str, value: Union[int, str, tuple], data_type_string: str) -> bytes:
    """
    packs awg_file record structure: "<I(lenname)I(lendat)s[data of data_type_string]"
    The file record format is as follows:

    Record Name Size
    (32-bit unsigned integer)
    Record Data Size
    (32-bit unsigned integer)
    Record Name (ASCII)
    (Include NULL.)
    Record Data
    """
    if len(data_type_string) == 1:
        dat = struct.pack("<" + data_type_string, value)

    elif data_type_string[-1] == "s":
        value = value.encode("ascii")
        dat = struct.pack(data_type_string, value)

    else:
        dat = struct.pack("<" + data_type_string, *tuple(value))

    len_dat = len(dat)
    return struct.pack("<II", len(name + "\x00"), len_dat) + name.encode() + b"\x00" + dat


def pack_waveform(wf: np.ndarray, m1: np.ndarray, m2: np.ndarray) -> np.ndarray:
    """
    packs analog waveform in 14 bit integer, and two bits for markers m1 and m2 in a single 16 bit integer

    Parameters:
        wf: an array with digital (0...1) waveform values
        m1: an array of digital (0...1) marker1 values
        m2: an array of digital (0...2) marker2 values

    Returns:
        packed_wf: A packed waveform as a sum of unsigned 16-bit integer and 14-bit waveform and 16-bit markers
    """
    wf_len = len(wf)
    packed_wf = np.zeros(wf_len, dtype=np.uint16)
    packed_wf += (
        np.round(wf * 8191).astype(np.uint16)
        + 8191
        + np.round(16384 * m1).astype(np.uint16)
        + np.round(32768 * m2).astype(np.uint16)
    )
    return packed_wf


def generate_awg_file(
    packed_waveforms, wf_names, nrep, trig_wait, goto_state, jump_to, channel_cfg, sequence_cfg
) -> bytes:
    """
    Generates a .awg file from input waveforms, names and other options. For info on filestructure and valid record
    names, see AWG Help, File and Record Format.

    Parameters:
        packed_waveforms: dictionary containing packed waveforms with keys wf_names and delay_labs
        wf_names: array of waveform names array([[segm1_ch1, segm2_ch1..], [segm1_ch2, segm2_ch2..], ...])
        nrep: list of len(segments) specifying the no of reps per segment (0, 65536)
        trig_wait: list of len(segments) specifying trigger wait state (0, 1)
        goto_state: list of len(segments) specifying goto state (0, 65536, 0 means next)
        jump_to: list of len(segments) specifying logic jump (0 = off)
        channel_cfg: dictionary of valid channel configuration records
        sequence_cfg: dictionary of valid head configuration records (see AWG_FILE_FORMAT_HEAD)

    Returns:
        bytes sum of the generated records (header, channel settings, waveforms and the sequence)
    """
    timetuple = tuple(np.array(localtime())[[0, 1, 8, 2, 3, 4, 5, 6, 7]])

    # general settings
    head_str = BytesIO()
    head_str.write(pack_record("MAGIC", 5000, "h") + pack_record("VERSION", 1, "h"))
    for k in sequence_cfg.keys():
        if k in AWG_FILE_FORMAT_HEAD:
            head_str.write(pack_record(k, sequence_cfg[k], AWG_FILE_FORMAT_HEAD[k]))
        else:
            logging.warning("AWG: " + k + " not recognized as valid AWG setting")

    # channel settings
    ch_record_str = BytesIO()
    for k in channel_cfg.keys():
        ch_k = k[:-1] + "N"
        if ch_k in AWG_FILE_FORMAT_CHANNEL:
            ch_record_str.write(pack_record(k, channel_cfg[k], AWG_FILE_FORMAT_CHANNEL[ch_k]))
        else:
            logging.warning("AWG: " + k + " not recognized as valid AWG channel setting")

    # Write the waveforms in record
    ii = 21
    wf_record_str = BytesIO()
    wf_list = list(packed_waveforms.keys())
    wf_list.sort()
    for wf in wf_list:
        wf_data = packed_waveforms[wf]
        len_wf_data = len(wf_data)
        wf_record_str.write(
            pack_record(f"WAVEFORM_NAME_{ii}", wf + "\x00", f"{len(wf) + 1}s")
            + pack_record(f"WAVEFORM_TYPE_{ii}", 1, "h")
            + pack_record(f"WAVEFORM_LENGTH_{ii}", len_wf_data, "l")
            + pack_record(f"WAVEFORM_TIMESTAMP_{ii}", timetuple[:-1], "8H")
            + pack_record(f"WAVEFORM_DATA_{ii}", wf_data, f"{len_wf_data}H")
        )
        ii += 1

    # Write the sequence in record
    kk = 1
    seq_record_str = BytesIO()
    for segment in wf_names.transpose():
        seq_record_str.write(
            pack_record(f"SEQUENCE_WAIT_{kk}", trig_wait[kk - 1], "h")
            + pack_record(f"SEQUENCE_LOOP_{kk}", int(nrep[kk - 1]), "l")
            + pack_record(f"SEQUENCE_JUMP_{kk}", jump_to[kk - 1], "h")
            + pack_record(f"SEQUENCE_GOTO_{kk}", goto_state[kk - 1], "h")
        )
        for wf_name in segment:
            if wf_name is not None:
                # We write the sequence name in the record string
                ch = wf_name[-1]
                seq_record_str.write(
                    pack_record(f"SEQUENCE_WAVEFORM_NAME_CH_{ch}_{kk}", wf_name + "\x00", f"{len(wf_name) + 1}s")
                )
        kk += 1

    return head_str.getvalue() + ch_record_str.getvalue() + wf_record_str.getvalue() + seq_record_str.getvalue()


class SuppressLogging:
    """Context manager to temporarily suppress logging during a test."""

    def __enter__(self):
        # Suppress logging of all levels up to ERROR.
        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)

    def __exit__(self, typ, value, tb):
        # Restore default log levels.
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)


class TektronixAWG5014TestCase(unittest.TestCase):

    contents = b'1234,5678,"SAMPLE1.AWG,,2948","aaa.txt,,1024","ddd,DIR,0","zzz.awg,,2948"\n'

    def setUp(self):
        qmi.start("TestContext")
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
                'qmi.instruments.tektronix.awg5014.create_transport',
                return_value=self._transport_mock):
            self.instr: Tektronix_Awg5014 = qmi.make_instrument("instr", Tektronix_Awg5014, "transport_descriptor")
            self.instr = cast(Tektronix_Awg5014, self.instr)

    def tearDown(self):
        qmi.stop()

    def test_open_close(self):
        """Test that the open and close functions include calls as expected."""
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.open.reset_mock()
        self._transport_mock.write.reset_mock()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_wait_and_clear(self):
        """Test wait_and_clear function."""
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"\n"]
            self.instr.wait_and_clear()

        self.assertIn(call(b"*WAI\n"), self._transport_mock.write.mock_calls)
        self.assertIn(call(b"*CLS\n"), self._transport_mock.write.mock_calls)
        self.assertEqual(self._transport_mock.write.mock_calls.count(call(b"*CLS\n")), 1)

    def test_wait_and_clear_with_passing_timeouts(self):
        """Test wait_and_clear to pass the timeouts. Check that at least 1 second was passed"""
        def mock_write_fun(message):
            sleep(1.0)
            raise QMI_TimeoutException("Took too long")

        start = time()
        with open_close(self.instr), self.assertRaises(QMI_TimeoutException):
            self._transport_mock.write = mock_write_fun
            self.instr.wait_and_clear()

        end = time()
        self.assertGreater(end - start, 1.0)

    def test_wait_command_completion(self):
        """Test wait_command_completion function."""
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n", b"1\n", b'-800,"Operation complete"\n']
            self.instr.wait_command_completion()

        self.assertIn(call(b"*OPC\n"), self._transport_mock.write.mock_calls)
        self.assertIn(call(b"*OPC?\n"), self._transport_mock.write.mock_calls)
        self.assertIn(call(b"SYST:ERR?\n"), self._transport_mock.write.mock_calls)
        self.assertEqual(self._transport_mock.write.mock_calls.count(call(b"*OPC?\n")), 2)

    def test_wait_command_completion_with_passing_timeouts(self):
        """Test wait_command_completion to pass the timeouts. Check that at least 1 second was passed"""
        start = time()
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n", QMI_TimeoutException, b'0,"No error"\n']
            self.instr.wait_command_completion()

        end = time()
        self.assertGreater(end - start, 1.0)

        self.assertIn(call(b"*OPC\n"), self._transport_mock.write.mock_calls)
        self.assertIn(call(b"*OPC?\n"), self._transport_mock.write.mock_calls)
        self.assertIn(call(b"SYST:ERR?\n"), self._transport_mock.write.mock_calls)
        self.assertEqual(self._transport_mock.write.mock_calls.count(call(b"*OPC?\n")), 2)

    def test_wait_command_completion_excepts(self):
        """Test wait_command_completion function excepts with some error other than -800."""
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException):
            self._transport_mock.read_until.side_effect = [b"1\n", b'-1,"Some error"\n']
            self.instr.wait_command_completion()

    def test_reset_no_errors(self):
        """Test reset call. It calls also to check errors to clear them"""
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"\n", b"\n"]
            self.instr.reset()
            self.assertIn(call(b"*CLS\n"), self._transport_mock.write.mock_calls)
            self.assertIn(call(b"*RST\n"), self._transport_mock.write.mock_calls)
            self.assertIn(call(b"*OPC\n"), self._transport_mock.write.mock_calls)

    def test_reset_with_passing_timeouts(self):
        """Test reset call. Make it pass the timeouts. Check that at least 1 second was passed"""
        def mock_read_fun(message_terminator, timeout):
            sleep(timeout)
            raise QMI_TimeoutException("Took too long")

        with open_close(self.instr):
            self._transport_mock.read_until = mock_read_fun
            self.instr.reset()

    def test_get_error(self):
        """Test get_error call. Error check returns an error, so *CLS is called once more."""
        expected_error = "Instrument returned error: -102,SYNTAX ERROR"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"-102,SYNTAX ERROR\n"]
            with self.assertRaises(QMI_InstrumentException) as exc:
                self.instr.get_error()

            self.assertEqual(expected_error, str(exc.exception))
            self.assertIn(call(b"SYST:ERR?\n"), self._transport_mock.write.mock_calls)

    def test_get_state(self):
        """Test instrument state query."""
        expected_state = "IDLE"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n"]
            state = self.instr.get_state()

        self.assertEqual(expected_state, state)

    def test_get_state_error(self):
        """Test instrument state query raising a KeyError."""
        with SuppressLogging(), open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"-1\n"]
            with self.assertRaises(KeyError):
                self.instr.get_state()

    def test_get_setup_file_name(self):
        """Test file name query for current AWG file."""
        expected = ("\\Users\\OEM\\Documents", "SAMPLE1.AWG")
        with open_close(self.instr):
            self._transport_mock.read_until.return_value = b'"\\Users\\OEM\\Documents\\SAMPLE1.AWG","C:"\n'
            file_and_path = self.instr.get_setup_file_name()
            self.assertTupleEqual(expected, file_and_path)

    def test_get_file_names(self):
        """Test file name query from a 'folder'."""
        expected = ["SAMPLE1.AWG,,2948", "aaa.txt,,1024", "zzz.awg,,2948"]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            files = self.instr.get_file_names()
            self.assertEqual(expected, files)

    def test_get_directories(self):
        """Test directory query from a 'folder'."""
        expected = ["ddd"]
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            directories = self.instr.get_directories()
            self.assertEqual(expected, directories)

    def test_change_directory(self):
        """Make a simple 'folder change' test."""
        new_dir = "/DIR2"
        expected_call = bytes(f'MMEM:CDIR "{new_dir}"\n'.encode())
        with open_close(self.instr):
            self.instr.change_directory(new_dir)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_current_directory_name(self):
        """A simple test for the `get_current_directory_name` call."""
        expected_call = b"MMEM:CDIR?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b'"CURDIR"\n']
            curdir = self.instr.get_current_directory_name()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual('"CURDIR"', curdir)

    def test_cd_to_root(self):
        """A simple test for function that changes directory to root (C:\)."""
        expected_call = b'MMEM:CDIR "C:\\.."\n'
        with open_close(self.instr):
            self.instr.cd_to_root()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_create_directory(self):
        """A simple test for creating a new directory."""
        new_dir = "DIR3"
        expected_call = bytes(f'MMEM:MDIR "{new_dir}"\n'.encode())
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.create_directory(new_dir)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_create_directory_but_already_exists(self):
        """Directory cannot be created as the name already exists. Catch exception."""
        expected_error = "Error: Directory already exists."
        new_dir = "ddd"
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException) as exc:
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.create_directory(new_dir)
            self.assertEqual(str(exc.exception), expected_error)

    def test_remove_file(self):
        """Simple test in removing a 'file'."""
        file_to_delete = "aaa.txt"
        expected_call = bytes(f'MMEM:DEL "{file_to_delete}"\n'.encode())
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.remove_file(file_to_delete)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_remove_file_no_file(self):
        """See that trying to remove file that is not present, results in exception."""
        expected_error = "Error: File does not exist"
        file_to_delete = "ddd"
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException) as exc:
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.remove_file(file_to_delete)
            self.assertEqual(str(exc.exception), expected_error)

    def test_remove_directory(self):
        """Simple test in removing a 'directory'."""
        directory_to_delete = "ddd"
        expected_call = bytes(f'MMEM:DEL "{directory_to_delete}"\n'.encode())
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.remove_directory(directory_to_delete)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_remove_directory_no_directory(self):
        """See that trying to remove directory that is not present, results in exception."""
        expected_error = "Error: Directory does not exist.\n"
        directory_to_delete = "aaa.txt"
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException) as exc:
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.remove_directory(directory_to_delete)
            self.assertEqual(str(exc.exception), expected_error)

    def test_send_awg_file(self):
        """Test sending an awg file."""
        file_name = "test.awg"
        file_contents = "abcdeABCDE1234509876"
        len_file_contents = len(file_contents)
        data_block = f"#{len(str(len_file_contents))}{len_file_contents}{file_contents}"
        expected_call = bytes(f'MMEM:DATA "{file_name}",{data_block}\n'.encode("ascii"))
        with open_close(self.instr):
            self.instr.send_awg_file(file_name, file_contents.encode("ascii"))
            self._transport_mock.write.assert_called_with(expected_call)

    def test_send_and_load_real_awg_file(self):
        red_eom_voltage = 80e-9
        red_eom_voltage_off = 1e-9
        waveforms, m1s, m2s, trigger, nreps, trig_waits, goto_states, jump_tos = create_pulse(
            red_eom_voltage, red_eom_voltage_off
        )
        # If all is good we can proceed to setting up the Tektronix AWG style waveforms
        pulses = ["test_EOM_opt_pulse"]
        packed_waveforms = {}
        wf_names = []
        for pulse in pulses:
            for channel in _Channels:
                waveform_name = f"{pulse}_{channel.name}"
                channel_nr = channel.value - 1
                wf = waveforms[channel_nr]
                m1 = m1s[channel_nr]
                m2 = m2s[channel_nr]
                # let's try packing
                packed_waveforms[waveform_name] = pack_waveform(wf, m1, m2)
                wf_names.append(waveform_name)

        channel_cfg = {}
        for channel in _Channels:
            # Making the configs is a bit more demanding
            channel_cfg[f"CHANNEL_STATE_{channel.value}"] = 1  # TODO: For now, set all channels active. Is this OK?
            if "MRK" in channel.name or "marker" in channel.name.lower():
                marker_nr = _Markers[channel.name].value
                channel_cfg[f"MARKER1_METHOD_{channel.value}"] = 2
                channel_cfg[f"MARKER2_METHOD_{channel.value}"] = 2
                channel_cfg[f"MARKER{marker_nr}_LOW_{channel.value}"] = -1  # or -amplitude + offset
                channel_cfg[f"MARKER{marker_nr}_HIGH_{channel.value}"] = 1  # or amplitude + offset
                channel_cfg[f"MARKER{marker_nr}_SKEW_{channel.value}"] = 0  # or ???

            else:
                channel_cfg[f"ANALOG_METHOD_{channel.value}"] = 1
                channel_cfg[f"ANALOG_AMPLITUDE_{channel.value}"] = 1  # or amplitude
                channel_cfg[f"ANALOG_OFFSET_{channel.value}"] = 0  # or offset
                channel_cfg[f"CHANNEL_SKEW_{channel.value}"] = 0  # or ???

        sequence_cfg = {}  # Did not find at the moment any headers for settings
        # sequence_cfg["SAMPLING_RATE"] = SAMPLING_RATE_CONVERSION

        # Then let's try generating the AWG file for Tektronix
        generated_records_block = generate_awg_file(
            packed_waveforms, np.array(wf_names), nreps, trig_waits, goto_states, jump_tos, channel_cfg, sequence_cfg
        )
        # Create Tektronix instance
        file_name = "SAMPLE1.AWG"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.send_awg_file(file_name, generated_records_block)
            # Might be good to check the file indeed is present before loading
            self.instr.load_awg_file(file_name)
            # Set the waveform values
            amplitude = np.abs(red_eom_voltage_off - red_eom_voltage)
            self.instr.set_amplitude(_Channels.RED_EOM_CH.value, amplitude=amplitude)
            self.instr.set_offset(_Channels.RED_EOM_CH.value, offset=red_eom_voltage_off)
            self.instr.set_amplitude(_Channels.GREEN_MRK_CH.value, 0.5)
            self.instr.set_amplitude(_Channels.RED_AOM_CH.value, 1)
            # Set all channels ON
            for channel in range(1, 5):
                self.instr.set_channel_state(channel, True)

            self.instr.start()
            # Set all channels OFF
            for channel in range(1, 5):
                self.instr.set_channel_state(channel, True)

            self.instr.stop()

    def test_send_awg_file_excepts_file_too_large(self):
        """Test sending an awg file excepts when the file is too large."""
        expected_error = "Waveform data block length too large! Consider using more efficient " +\
                         "file encoding or direct control commands on instrument."
        file_name = "test_big.awg"
        file_contents = "abcdeABCDE1234509876" * (int(65E7) // 20 + 1)
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.send_awg_file(file_name, file_contents.encode())
            self.assertEqual(str(exc.exception), expected_error)

    def test_load_awg_file(self):
        """Simple test in loading a 'file'."""
        file_to_load = "zzz.awg"
        expected_call = bytes(f'AWGC:SRES "{file_to_load}"\n'.encode())
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.load_awg_file(file_to_load)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_load_awg_file_no_file(self):
        """See that trying to load a file that is not present, results in exception."""
        file_to_load = "ddd.awg"
        expected_error = f"Error: File {file_to_load} not found."
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException) as exc:
            self._transport_mock.read_until.side_effect = [self.contents]
            self.instr.load_awg_file(file_to_load)
            self.assertEqual(str(exc.exception), expected_error)

    def test_clear_waveforms(self):
        """Simple test to see all channels get called to clear the waveforms."""
        expected_calls = [call(b'SOUR1:FUNC:USER ""\n'), call(b'SOUR2:FUNC:USER ""\n'),
                          call(b'SOUR3:FUNC:USER ""\n'), call(b'SOUR4:FUNC:USER ""\n')]
        with open_close(self.instr):
            self.instr.clear_waveforms()
            self._transport_mock.write.assert_has_calls(expected_calls)

    def test_delete_all_waveforms_from_list(self):
        """Test that right call is made."""
        expected_call = b"WLIS:WAV:DEL ALL\n"
        with open_close(self.instr):
            self.instr.delete_all_waveforms_from_list()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_start(self):
        """Test that start makes right call."""
        expected_call = b"AWGC:RUN\n"
        with open_close(self.instr):
            self.instr.start()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_stop(self):
        """Test that stop makes right call."""
        expected_call = b"AWGC:STOP\n"
        with open_close(self.instr):
            self.instr.stop()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_clock_source(self):
        """Test clock source query."""
        expected_call = b"AWGC:CLOC:SOUR?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"INT\n"]
            answer = self.instr.get_clock_source()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, "INT")

    def test_set_clock_to_internal(self):
        """Test setting clock to 'internal' mode."""
        expected_call = b"AWGC:CLOC:SOUR INT\n"
        with open_close(self.instr):
            self.instr.set_clock_to_internal()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_clock_to_external(self):
        """Test setting clock to 'external' mode."""
        expected_call = b"AWGC:CLOC:SOUR EXT\n"
        with open_close(self.instr):
            self.instr.set_clock_to_external()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_reference_oscillator_source(self):
        """Test reference oscillator source query."""
        expected_call = b"ROSC:SOUR?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"INT\n"]
            answer = self.instr.get_reference_oscillator_source()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, "INT")

    def test_set_reference_oscillator_to_internal(self):
        """Test setting reference oscillator to 'internal' mode."""
        expected_call = b"ROSC:SOUR INT\n"
        with open_close(self.instr):
            self.instr.set_reference_oscillator_to_internal()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_reference_reference_oscillator_to_external(self):
        """Test setting reference oscillator to 'external' mode."""
        expected_call = b"ROSC:SOUR EXT\n"
        with open_close(self.instr):
            self.instr.set_reference_oscillator_to_external()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_reference_clock_frequency(self):
        """Test reference clock frequency query."""
        expected_call = b"ROSC:FREQ?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"2E+07\n"]
            freq = self.instr.get_reference_clock_frequency()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(freq, 2E7)

    def test_set_reference_clock_frequency(self):
        """Test that the reference clock frequency set is called with valid MHz value."""
        expected_call = b"ROSC:FREQ 20MHZ\n"
        with open_close(self.instr):
            self.instr.set_reference_clock_frequency(2E7)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_reference_clock_frequency_excepts(self):
        """Test that the reference clock frequency set excepts when not called in one of the three possible values."""
        with open_close(self.instr), self.assertRaises(ValueError):
            self.instr.set_reference_clock_frequency(5E7)

    def test_get_source_clock_frequency(self):
        """Test source clock frequency query."""
        expected_call = b"SOUR:FREQ?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"1.1000000E+07\n"]
            freq = self.instr.get_source_clock_frequency()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(freq, 11E6)

    def test_set_source_clock_frequency_int(self):
        """Test that the source clock frequency set is called when in "internal mode"."""
        expected_call = b"SOUR:FREQ 1.34E+07\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"INT\n"]
            self.instr.set_source_clock_frequency(13.4E6)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_source_clock_frequency_ext(self):
        """Test that the source clock frequency set is called when in "external mode"."""
        expected_call = b"SOUR:FREQ:FIX 1.34E+07\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"EXT\n", b"FIX\n"]
            self.instr.set_source_clock_frequency(13.4E6)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_source_clock_frequency_out_of_range(self):
        """Test that the source clock frequency set is called."""
        out_of_range_freqs = [9.9E6, 11E9]
        with open_close(self.instr):
            for freq in out_of_range_freqs:
                with self.assertRaises(ValueError):
                    self.instr.set_source_clock_frequency(freq)

    def test_get_reference_oscillator_type(self):
        """Test query of reference oscillator type."""
        expected_call = b"ROSC:TYPE?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"FIX\n"]
            answer = self.instr.get_reference_oscillator_type()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, "FIX")

    def test_set_reference_oscillator_type(self):
        """Test setting reference oscillator type to 'variable'."""
        expected_call = b"ROSC:TYPE VAR\n"
        with open_close(self.instr):
            self.instr.set_reference_oscillator_type("VAR")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_reference_oscillator_type_exception(self):
        """Test setting reference oscillator with invalid type."""
        expected_error = "Unknown reference oscillator type INT!"
        with open_close(self.instr), self.assertRaises(ValueError) as exc:
            self.instr.set_reference_oscillator_type("INT")

        self.assertEqual(expected_error, str(exc.exception))

    def test_get_dc_output_state(self):
        """Test the DC output state query."""
        expected_call = b"AWGC:DC:STAT?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n"]
            state = self.instr.get_dc_output_state()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(0, state)

    def test_set_dc_output_state(self):
        """Test set DC output state."""
        expected_call = b"AWGC:DC:STAT 1\n"
        with open_close(self.instr):
            self.instr.set_dc_output_state(1)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_dc_output_channel_offset(self):
        """Test DC output channel offset query."""
        expected_call = b"AWGC:DC1:VOLT:OFFS?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0.12\n"]
            offset = self.instr.get_dc_output_offset(1)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(0.12, offset)

    def test_get_dc_output_channel_offset_invalid_channel(self):
        """Test DC output channel offset query."""
        invalid_channels = [0, 5]
        with open_close(self.instr):
            for channel in invalid_channels:
                with self.assertRaises(ValueError):
                    self.instr.get_dc_output_offset(channel)

    def test_set_DC_channel_offset(self):
        """Test set DC channel offset."""
        output, offset = 1, 2.0
        expected_call = bytes(f"AWGC:DC{output}:VOLT:OFFS {offset:.1f}V\n".encode())
        with open_close(self.instr):
            self.instr.set_dc_output_offset(output, offset)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_raw_dac_waveform_output(self):
        """Test raw DAC waveform output channel state query."""
        channel = 1
        expected_call = bytes(f"AWGC:DOUT{channel}:STAT?\n".encode())
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n"]
            state = self.instr.get_raw_dac_waveform_output(channel)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(0, state)

    def test_set_raw_dac_waveform_output(self):
        """Test set raw DAC waveform output channel state."""
        channel, state = 4, 1
        expected_call = bytes(f"AWGC:DOUT{channel}:STAT {state}\n".encode())
        with open_close(self.instr):
            self.instr.set_raw_dac_waveform_output(channel, state)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_run_mode(self):
        """Test run mode query."""
        expected_call = b"AWGC:RMOD?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"CONT\n"]
            answer = self.instr.get_run_mode()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, "CONT")

    def test_set_run_mode_to_triggered(self):
        """Test setting run mode to triggered method."""
        expected_call = b"AWGC:RMOD TRIG\n"
        with open_close(self.instr):
            self.instr.set_run_mode_to_triggered()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_run_mode_to_continuous(self):
        """Test setting run mode to continuous method."""
        expected_call = b"AWGC:RMOD CONT\n"
        with open_close(self.instr):
            self.instr.set_run_mode_to_continuous()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_run_mode(self):
        """Test setting run mode with specific keyword."""
        expected_call = b"AWGC:RMOD SEQ\n"
        with open_close(self.instr):
            self.instr.set_run_mode("SEQ")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_run_mode_invalid(self):
        """Try to give invalid run mode."""
        with open_close(self.instr):
            with self.assertRaises(ValueError):
                self.instr.set_run_mode("KONT")

    def test_get_signal_addition(self):
        """Test signal addition from external input query"""
        expected_call = b"COMB:FEED?\n"
        expected_answer = ""
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [bytes(f'{expected_answer}\n'.encode())]
            answer = self.instr.get_signal_addition()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, expected_answer)

    def test_set_signal_addition(self):
        """Test setting signal addition from external input"""
        esig = "ESIG"
        expected_call = bytes(f'COMB:FEED "{esig}"\n'.encode())
        with open_close(self.instr):
            self.instr.set_signal_addition(esig)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_trigger_source(self):
        """Test trigger source query."""
        expected_call = b"TRIG:SOUR?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"EXT\n"]
            answer = self.instr.get_trigger_source()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, "EXT")

    def test_set_trigger_source_to_internal(self):
        """Test setting trigger source to 'internal' mode."""
        expected_call = b"TRIG:SOUR INT\n"
        with open_close(self.instr):
            self.instr.set_trigger_source_to_internal()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_trigger_source_to_external(self):
        """Test setting trigger source to 'external' mode."""
        expected_call = b"TRIG:SOUR EXT\n"
        with open_close(self.instr):
            self.instr.set_trigger_source_to_external()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_trigger_impedance(self):
        """Test trigger impedance query."""
        expected_call = b"TRIG:IMP?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"50\n"]
            imp = self.instr.get_trigger_impedance()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(imp, 50)

    def test_set_trigger_impedance(self):
        """Test set trigger impedance call."""
        expected_call = b"TRIG:IMP 50\n"
        with open_close(self.instr):
            self.instr.set_trigger_impedance(50)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_trigger_impedance_error(self):
        """Test set trigger impedance call with non-standard value (50 or 1000)."""
        expected_error = "Invalid impedance 650 Ohm. Must be either 50 Ohm or 1000 Ohm."
        with open_close(self.instr), self.assertRaises(ValueError) as exc:
            self.instr.set_trigger_impedance(650)

        self.assertEqual(expected_error, str(exc.exception))

    def test_get_trigger_level(self):
        """Test trigger level query."""
        expected_call = b"TRIG:LEV?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"2.100\n"]
            answer = self.instr.get_trigger_level()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, 2.1)

    def test_set_trigger_level(self):
        """Test set trigger level call."""
        expected_call = b"TRIG:LEV 1.230\n"
        with open_close(self.instr):
            self.instr.set_trigger_level(1.23)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_trigger_slope(self):
        """Test get trigger slope sign."""
        expected_slope = "POS"
        expected_call = b"TRIG:SLOP?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [bytes(f"{expected_slope}\n".encode())]
            answer = self.instr.get_trigger_slope()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, expected_slope)

    def test_set_trigger_slope(self):
        """Test setting the trigger slope sign."""
        expected_calls = [b"TRIG:SLOP POSitive\n", b"TRIG:SLOP NEGative\n"]
        for n, slope in enumerate(["POS", "NEG"]):
            with open_close(self.instr):
                self.instr.set_trigger_slope(slope)
                self._transport_mock.write.assert_called_with(expected_calls[n])

    def test_set_trigger_slope_exception(self):
        """Test setting the slope with invalid value"""
        with open_close(self.instr), self.assertRaises(ValueError):
            self.instr.set_trigger_slope("NEUtral")

    def test_get_trigger_polarity(self):
        """Test get trigger polarity sign."""
        expected_polarity = "POS"
        expected_call = b"TRIG:POL?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [bytes(f"{expected_polarity}\n".encode())]
            answer = self.instr.get_trigger_polarity()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, expected_polarity)

    def test_set_trigger_polarity(self) -> None:
        """Test setting the trigger polarity sign."""
        expected_calls = [b"TRIG:POL POSitive\n", b"TRIG:POL NEGative\n"]
        for n, polarity in enumerate(["POS", "NEG"]):
            with open_close(self.instr):
                self.instr.set_trigger_polarity(polarity)
                self._transport_mock.write.assert_called_with(expected_calls[n])

    def test_set_trigger_polarity_exception(self):
        """Test setting the polarity with invalid value"""
        with open_close(self.instr), self.assertRaises(ValueError):
            self.instr.set_trigger_polarity("NEUtral")

    def test_get_waveform_output_data_position(self):
        """Test waveform output data position query."""
        expected_call = b"TRIG:SEQ:WVAL?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"FIRS\n"]
            position = self.instr.get_waveform_output_data_position()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(position, "FIRS")

    def test_set_waveform_output_data_position(self):
        """Test that the waveform output data position set is called when in "Triggered" or "Gated" Run mode."""
        expected_call = b"TRIG:SEQ:WVAL LAST\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"GAT\n"]
            self.instr.set_waveform_output_data_position("LAST")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_waveform_output_data_position_invalid(self):
        """Test setting waveform output data position with invalid position."""
        ipos = "MID"
        expected_error = f"Invalid waveform position {ipos}"
        with open_close(self.instr), self.assertRaises(ValueError) as exc:
            self.instr.set_waveform_output_data_position(ipos)

        self.assertEqual(expected_error, str(exc.exception))

    def test_set_waveform_output_data_position_excepts(self):
        """Test setting waveform output data position when Run mode is not "Triggered" or "Gated"."""
        expected_error = "The Run mode must be Triggered or Gated to set WF output data position"
        with open_close(self.instr), self.assertRaises(QMI_InstrumentException) as exc:
            self._transport_mock.read_until.side_effect = [b"CONT\n"]
            self.instr.set_waveform_output_data_position("FIRSt")

        self.assertEqual(expected_error, str(exc.exception))

    def test_force_trigger_event(self):
        """See that force trigger event gets called correct."""
        expected_call = b"*TRG\n"
        with open_close(self.instr):
            self.instr.force_trigger_event()
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_channel_state(self):
        """Test the channel state query."""
        expected_call = b"OUTP4?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"1\n"]
            state = self.instr.get_channel_state(4)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(state, 1)

    def test_set_channel_state(self):
        """Test set channel state call."""
        expected_call = b"OUTP4 OFF\n"
        with open_close(self.instr):
            self.instr.set_channel_state(4, 0)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_low_pass_filter_frequency(self):
        """Test low-pass filter frequency of an output channel query."""
        channel, expected_frequency = 2, 2E8
        expected_call = bytes(f"OUTP{channel}:FILT:FREQ?\n".encode())
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [bytes(f"{expected_frequency}\n".encode())]
            frequency = self.instr.get_low_pass_filter_frequency(channel)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(frequency, expected_frequency)

    def test_set_low_pass_filter_frequency(self):
        """Test set low-pass filter frequency of an output channel call."""
        channel, frequency = 2, 2E8
        expected_call = bytes(f"OUTP{channel}:FILT:FREQ 2.0E+8\n".encode())
        with open_close(self.instr):
            self.instr.set_low_pass_filter_frequency(channel, frequency)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_low_pass_filter_frequency_inf(self):
        """Test set low-pass filter frequency to infinity of an output channel call."""
        channel, frequency = 2, "INF"
        expected_call = bytes(f"OUTP{channel}:FILT:FREQ INFinity\n".encode())
        with open_close(self.instr):
            self.instr.set_low_pass_filter_frequency(channel, frequency)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_low_pass_filter_frequency_exception(self):
        """Test set low-pass filter frequency to infinity of an output channel call."""
        channel, frequency = 2, "POS"
        expected_error = f"Low pass filer frequency cannot be {frequency}, use a float or 'INFinity'"
        with open_close(self.instr), self.assertRaises(ValueError) as err:
            self.instr.set_low_pass_filter_frequency(channel, frequency)
            self.assertEqual(expected_error, str(err.exception))

    def test_get_sequence_length(self):
        """Test the sequence length query."""
        expected_call = b"SEQ:LENG?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"100\n"]
            length = self.instr.get_sequence_length()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(length, 100)

    def test_set_sequence_length(self):
        """Test set sequence length call."""
        expected_call = b"SEQ:LENG 0\n"
        with open_close(self.instr):
            self.instr.set_sequence_length(0)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_sequencer_type(self):
        """Test the sequencer type query."""
        expected_call = b"AWGC:SEQ:TYPE?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"SOFT\n"]
            type = self.instr.get_sequencer_type()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(type, "SOFT")

    def test_get_sequencer_position(self):
        """Test get sequencer position query."""
        expected_call = b"AWGC:SEQ:POS?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"19\n"]
            pos = self.instr.get_sequencer_position()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(pos, 19)

    def test_set_sequence_element_goto_target_index(self):
        """Test setting 'GOTO' target index of a sequencer element function."""
        expected_call = b"SEQ:ELEM20:GOTO:IND 19\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_goto_target_index(20, 19)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_sequence_element_goto_target_index_zero_index_exception(self):
        """Test setting 'GOTO' target index raises an error if trying to use index numer 0."""
        with open_close(self.instr):
            with self.assertRaises(ValueError):
                self.instr.set_sequence_element_goto_target_index(20, 0)

    def test_set_sequence_element_goto_state(self):
        """Test setting 'GOTO' state of a sequencer element function."""
        expected_call = b"SEQ:ELEM20:GOTO:STAT 1\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_goto_state(20, 1)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_sequence_element_loop_count_infinite_state(self):
        """Test querying of the infinite loop count state."""
        expected_call = b"SEQ:ELEM2:LOOP:INF?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n"]
            state = self.instr.get_sequence_element_loop_count_infinite_state(2)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertFalse(state)

    def test_set_sequence_element_loop_count_infinite_state_on(self):
        """Test setting the infinite loop count state."""
        expected_call = b"SEQ:ELEM2:LOOP:INF 1\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_loop_count_infinite_state(2, True)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_sequence_element_loop_count_infinite_state_off(self):
        """Test setting the infinite loop count state."""
        expected_call = b"SEQ:ELEM2:LOOP:INF 0\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_loop_count_infinite_state(2, False)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_sequence_element_loop_count(self):
        """Test querying of the sequence element loop count."""
        expected_call = b"SEQ:ELEM2:LOOP:COUN?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"21\n"]
            count = self.instr.get_sequence_element_loop_count(2)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(count, 21)

    def test_set_sequence_element_loop_count(self):
        """Test setting the sequence element loop count."""
        expected_call = b"SEQ:ELEM2:LOOP:COUN 12345\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_loop_count(2, 12345)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_sequence_element_loop_count_out_of_range(self):
        """Test setting the sequence element loop count."""
        invalid_counts = [0, 66666]
        with open_close(self.instr):
            for count in invalid_counts:
                with self.assertRaises(ValueError):
                    self.instr.set_sequence_element_loop_count(2, count)

    def test_get_sequence_element_trigger_wait_state(self):
        """Test query of sequence element trigger wait state."""
        expected_call = b"SEQ:ELEM3:TWA?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"0\n"]
            state = self.instr.get_sequence_element_trigger_wait_state(3)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertFalse(state)

    def test_set_sequence_element_trigger_wait_state(self):
        """Test setting sequence element trigger wait state."""
        expected_call = b"SEQ:ELEM3:TWA 1\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_trigger_wait_state(3, 1)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_sequence_element_waveform(self):
        """Test query of sequence element waveform."""
        expected_call = b"SEQ:ELEM3:WAV2?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"*SineWave1\n"]
            wf = self.instr.get_sequence_element_waveform(3, 2)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(wf, "*SineWave1")

    def test_set_sequence_element_waveform(self):
        """Test setting sequence element waveform."""
        expected_call = b'SEQ:ELEM3:WAV2 "*CosineWave1"\n'
        with open_close(self.instr):
            self.instr.set_sequence_element_waveform(3, 2, "*CosineWave1")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_force_sequence_jump_to_index(self):
        """Test force jump sequence to index call."""
        expected_call = b"SEQ:JUMP:IMM 33\n"
        with open_close(self.instr):
            self.instr.force_sequence_jump_to_index(33)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_sequence_element_jump_target_index(self):
        """Test setting the sequence element jump target index."""
        expected_call = b"SEQ:ELEM1:JTAR:INDEX 33\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_jump_target_index(1, 33)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_sequence_element_jump_type(self):
        """Test query of the sequence element jump type."""
        expected_call = b"SEQ:ELEM1:JTAR:TYPE?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"OFF\n"]
            type = self.instr.get_sequence_element_jump_type(1)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(type, "OFF")

    def test_set_sequence_element_jump_type(self):
        """Test setting the sequence element jump type."""
        expected_call = b"SEQ:ELEM1:JTAR:TYPE IND\n"
        with open_close(self.instr):
            self.instr.set_sequence_element_jump_type(1, "IND")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_sequence_element_jump_type_error(self):
        """Test setting the sequence element jump type to invalid type."""
        invalid_type = "ON"
        with open_close(self.instr):
            with self.assertRaises(ValueError):
                self.instr.set_sequence_element_jump_type(1, invalid_type)

    def test_get_sequence_jump_mode(self):
        """Test query of sequence jump mode."""
        expected_call = b"AWGC:ENH:SEQ:JMOD?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"SOFT\n"]
            mode = self.instr.get_sequence_jump_mode()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(mode, "SOFT")

    def test_set_sequence_jump_mode(self):
        """Test setting the sequence jump mode."""
        expected_call = b"AWGC:ENH:SEQ:JMOD TABL\n"
        with open_close(self.instr):
            self.instr.set_sequence_jump_mode("TABL")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_set_sequence_jump_mode_invalid(self):
        """See that setting sequence jump mode with invalid input will raise an exception."""
        expected_error = "Error: Invalid jump mode HARD."
        with open_close(self.instr), self.assertRaises(ValueError) as exc:
            self.instr.set_sequence_jump_mode("HARD")

        self.assertEqual(str(exc.exception), expected_error)

    def test_get_jump_target_definition(self):
        """Test querying the dynamic jump target."""
        expected_call = b"AWGC:EVEN:DJUM:DEF? 234\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"432\n"]
            definition = self.instr.get_jump_target_definition(234)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(definition, 432)

    def test_set_jump_target_definition(self):
        """Test querying the dynamic jump target."""
        expected_call = b"AWGC:EVEN:DJUM:DEF 234,342\n"
        with open_close(self.instr):
            self.instr.set_jump_target_definition(234, 342)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_event_jump_mode(self):
        expected_call = b"AWGC:EVEN:JMOD?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"DJUMP\n"]
            mode = self.instr.get_event_jump_mode()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(mode, "DJUMP")

    def test_set_event_jump_mode(self):
        expected_call = b"AWGC:EVEN:JMOD EJUMP\n"
        with open_close(self.instr):
            self.instr.set_event_jump_mode("EJUMP")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_event_jump_timing_mode(self):
        expected_call = b"EVEN:JTIM?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"SYNC\n"]
            mode = self.instr.get_event_jump_timing_mode()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(mode, "SYNC")

    def test_set_event_jump_timing_mode(self):
        expected_call = b"EVEN:JTIM ASYN\n"
        with open_close(self.instr):
            self.instr.set_event_jump_timing_mode("ASYN")
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_event_input_impedance(self):
        expected_imp = 50
        expected_call = b"EVEN:IMP?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [bytes(f"{expected_imp}\n".encode())]
            imp = self.instr.get_event_input_impedance()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(expected_imp, imp)

    def test_set_event_input_impedance(self):
        for new_imp in [50, 1000]:
            expected_call = bytes(f"EVEN:IMP {new_imp}\n".encode())
            with open_close(self.instr):
                self.instr.set_event_input_impedance(new_imp)
                self._transport_mock.write.assert_called_with(expected_call)

    def test_set_event_input_impedance_raises_exception(self):
        """See that a value other than 50 or 1000 raises an exception."""
        with open_close(self.instr), self.assertRaises(ValueError):
            self.instr.set_event_input_impedance(123)

    def test_get_event_input_polarity(self):
        """Test get event input polarity sign."""
        expected_polarity = "POS"
        expected_call = b"EVEN:POL?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [bytes(f"{expected_polarity}\n".encode())]
            answer = self.instr.get_event_input_polarity()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(answer, expected_polarity)

    def test_set_event_input_polarity(self) -> None:
        """Test setting the event input polarity sign."""
        expected_calls = [b"EVEN:POL POSitive\n", b"EVEN:POL NEGative\n"]
        for n, polarity in enumerate(["POS", "NEG"]):
            with open_close(self.instr):
                self.instr.set_event_input_polarity(polarity)
                self._transport_mock.write.assert_called_with(expected_calls[n])

    def test_set_event_input_polarity_exception(self):
        """Test setting the polarity with invalid value"""
        with open_close(self.instr), self.assertRaises(ValueError):
            self.instr.set_event_input_polarity("NEUtral")

    def test_get_event_level(self):
        """Test querying the immediate event_level of the voltage level."""
        expected_call = b"EVEN:LEV?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"-2.3\n"]
            ampl = self.instr.get_event_level()
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(-2.3, ampl)

    def test_set_event_level(self):
        """Test setting immediate event_level of the voltage level."""
        expected_call = b"EVEN:LEV 1.250000V\n"
        with open_close(self.instr):
            self.instr.set_event_level(1.25)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_amplitude(self):
        """Test querying the immediate amplitude of the voltage level."""
        expected_call = b"SOUR3:VOLT:LEV:IMM:AMPL?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"12.3\n"]
            ampl = self.instr.get_amplitude(3)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(12.3, ampl)

    def test_set_amplitude(self):
        """Test setting immediate amplitude of the voltage level."""
        expected_call = b"SOUR3:VOLT:LEV:IMM:AMPL 12.500000\n"
        with open_close(self.instr):
            self.instr.set_amplitude(3, 12.5)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_marker_low(self):
        expected_call = b"SOUR1:MARK2:VOLT:LEV:IMM:LOW?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"1.0\n"]
            low = self.instr.get_marker_low(1, 2)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(low, 1.0)

    def test_set_marker_low(self):
        expected_call = b"SOUR1:MARK2:VOLT:LEV:IMM:LOW 0.500\n"
        with open_close(self.instr):
            self.instr.set_marker_low(1, 2, 0.5)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_marker_high(self):
        expected_call = b"SOUR1:MARK2:VOLT:LEV:IMM:HIGH?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"5.0\n"]
            high = self.instr.get_marker_high(1, 2)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(high, 5.0)

    def test_set_marker_high(self):
        expected_call = b"SOUR1:MARK2:VOLT:LEV:IMM:HIGH 5.100\n"
        with open_close(self.instr):
            self.instr.set_marker_high(1, 2, 5.1)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_marker_delay(self):
        expected_call = b"SOUR1:MARK2:DEL?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"1.0\n"]
            delay = self.instr.get_marker_delay(1, 2)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(delay, 1.0)

    def test_set_marker_delay(self):
        expected_call = b"SOUR1:MARK2:DEL 0.5\n"
        with open_close(self.instr):
            self.instr.set_marker_delay(1, 2, 0.5)
            self._transport_mock.write.assert_called_with(expected_call)

    def test_get_offset(self):
        expected_call = b"SOUR1:VOLT:LEV:IMM:OFFS?\n"
        with open_close(self.instr):
            self._transport_mock.read_until.side_effect = [b"1.0\n"]
            offset = self.instr.get_offset(1)
            self._transport_mock.write.assert_called_with(expected_call)
            self.assertEqual(offset, 1.0)

    def test_set_offset(self):
        expected_call = b"SOUR1:VOLT:LEV:IMM:OFFS 0.500000\n"
        with open_close(self.instr):
            self.instr.set_offset(1, 0.5)
            self._transport_mock.write.assert_called_with(expected_call)


def create_pulse(red_eom_voltage, red_eom_voltage_off):

    waveforms = np.array([ZEROS_ARRAY, ZEROS_ARRAY, ZEROS_ARRAY, ZEROS_ARRAY])
    m1s = np.array([ZEROS_ARRAY, ZEROS_ARRAY, ZEROS_ARRAY, ZEROS_ARRAY])
    m2s = np.array([ZEROS_ARRAY, ZEROS_ARRAY, ZEROS_ARRAY, ZEROS_ARRAY])

    total_green_pulse = GREEN_PULSE
    waveforms[_Channels.GREEN_MRK_CH.value - 1] = total_green_pulse

    # creating red pulse
    amplitude_eom = np.abs(red_eom_voltage_off - red_eom_voltage)
    waveform_of_0_voltage = -red_eom_voltage_off / amplitude_eom
    waveforms[_Channels.RED_EOM_CH.value - 1] = np.ones(NO_OF_POINTS) * waveform_of_0_voltage

    green_pulse_minus_extra_time = GREEN_TIME_PULSE + GREEN_OFF_TIME - EXTRA_TIME
    green_pulse_plus_red_aom_time = GREEN_TIME_PULSE + GREEN_OFF_TIME + RED_AOM_TIME
    green_pulse_plus_red_pulse_minus_extra_time = green_pulse_plus_red_aom_time + RED_PULSE_TIME - EXTRA_TIME
    if red_eom_voltage > red_eom_voltage_off:
        # print('it is case 1')
        times = np.arange(green_pulse_plus_red_aom_time - EXTRA_TIME, green_pulse_plus_red_pulse_minus_extra_time)
        anti_times = np.arange(
            green_pulse_plus_red_pulse_minus_extra_time + DELAY,
            green_pulse_plus_red_pulse_minus_extra_time + RED_PULSE_TIME + DELAY,
        )
    else:
        # print('it is case 2')
        anti_times = np.arange(green_pulse_plus_red_aom_time - EXTRA_TIME, green_pulse_plus_red_pulse_minus_extra_time)
        times = np.arange(
            green_pulse_plus_red_pulse_minus_extra_time + DELAY,
            green_pulse_plus_red_pulse_minus_extra_time + DELAY + RED_PULSE_TIME,
        )

    # Set to 0
    waveforms[_Channels.RED_EOM_CH.value - 1][green_pulse_minus_extra_time : green_pulse_plus_red_aom_time - EXTRA_TIME] = 0
    # Set to 1
    waveforms[_Channels.RED_EOM_CH.value - 1][times] = 1
    # Set to -1
    waveforms[_Channels.RED_EOM_CH.value - 1][anti_times] = -1
    # Set to 1
    waveforms[_Channels.RED_EOM_CH.value - 1][
        green_pulse_plus_red_pulse_minus_extra_time
        + DELAY
        + RED_PULSE_TIME: green_pulse_plus_red_pulse_minus_extra_time
        + DELAY
        + RED_PULSE_TIME
        + RED_AOM_TIME
    ] = 1

    aom_times = np.arange(green_pulse_minus_extra_time, green_pulse_minus_extra_time + RED_PULSE_TIME + RED_AOM_TIME)
    waveforms[_Channels.RED_AOM_CH.value - 1][aom_times] = 1

    # making the hydraharp trigger
    trigger = np.zeros(NO_OF_POINTS)
    trigger_time = green_pulse_plus_red_aom_time - TRIGGER_ANTICIPATION
    trigger[trigger_time: trigger_time + 1] = 1
    m1s[_Channels.HYDRAHARP_MRK_CH.value - 1] = trigger

    # We can visualise the waveforms and markers
    nreps = [0] * 4  # setting the number of repetitions to infinite
    trig_waits = [0] * 4
    goto_states = [1] * 4
    jump_tos = [1] * 4

    return np.array(waveforms), np.array(m1s), np.array(m2s), trigger, nreps, trig_waits, goto_states, jump_tos


if __name__ == '__main__':
    unittest.main()
