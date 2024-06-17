"""Test cases for Zurich Instruments HDAWG."""

import random
from typing import Sequence
import unittest
from unittest.mock import MagicMock, Mock, PropertyMock


import qmi.instruments.zurich_instruments.hdawg as hdawg
from qmi.instruments.zurich_instruments import ZurichInstruments_Hdawg
from tests.patcher import PatcherQmiContext


class TestZurichInstruments_Hdawg_OpenClose(unittest.TestCase):
    """Testcase for HDAWG opening and closing."""

    def setUp(self):
        # Test variables
        self._host = "test_host"
        self._port = 1
        self._device_name = "test_device_name"

        # Mock session
        self._session = Mock()
        hdawg.zhinst = Mock()
        hdawg.zhinst.toolkit.Session = Mock(return_value=self._session)

        # Patch QMI context and make instrument
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        self.qmi_patcher = PatcherQmiContext()
        self.qmi_patcher.start(self._ctx_qmi_id)
        self._instr: ZurichInstruments_Hdawg = self.qmi_patcher.make_instrument(
            "test_hdawg", ZurichInstruments_Hdawg, self._host, self._port, self._device_name
        )

    def tearDown(self):
        if self._instr.is_open():
            self._instr.close()
        self.qmi_patcher.stop()

    def test_open_connects_to_device(self):
        # Arrange

        # Act
        self._instr.open()

        # Assert
        self._session.connect_device.assert_called_once_with(self._device_name)

    def test_close_disconnects_from_device(self):
        # Arrange
        self._instr.open()

        # Act
        self._instr.close()

        # Assert
        self._session.disconnect_device.assert_called_once_with(self._device_name)


class TestZurichInstruments_Hdawg(unittest.TestCase):
    """Testcase for HDAWG RPC methods."""

    def setUp(self):
        # Test variables
        self._host = "test_host"
        self._port = 1
        self._device_name = "test_device_name"

        # Mock awgs property
        self._awgs = PropertyMock(spec=Sequence[hdawg.zhinst.toolkit.driver.nodes.awg.AWG])
        self._awg_0 = MagicMock()
        self._awgs.return_value = [self._awg_0]

        # Mock HDAWG device
        self._device = Mock(spec=hdawg.zhinst.toolkit.driver.devices.HDAWG)
        type(self._device).awgs = self._awgs

        # Mock session
        self._session = Mock()
        self._session.connect_device = Mock(return_value=self._device)
        hdawg.zhinst = Mock()
        hdawg.zhinst.toolkit.Session = Mock(return_value=self._session)

        # Patch QMI context and make instrument
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        self.qmi_patcher = PatcherQmiContext()
        self.qmi_patcher.start(self._ctx_qmi_id)
        self._instr: ZurichInstruments_Hdawg = self.qmi_patcher.make_instrument(
            "test_hdawg", ZurichInstruments_Hdawg, self._host, self._port, self._device_name
        )
        self._instr.open()

    def tearDown(self):
        self._instr.close()
        self.qmi_patcher.stop()

    def test_load_sequencer_program_with_string_sequence__calls_zi_method(self):
        """Test load sequencer program with string sequence and calls relevant ZI method."""
        # Arrange
        sequencer_code = "dummy code here"

        # Act
        self._instr.compile_and_upload(1, sequencer_code)

        # Assert
        self._awg_0.load_sequencer_program.assert_called_once_with(sequencer_code)

    def test_load_sequencer_program_with_zi_sequence__calls_zi_method(self):
        """Test load sequencer program with zi's sequence and sequence loads."""
        # Arrange
        sequence = hdawg.zhinst.toolkit.Sequence()

        # Act
        self._instr.compile_and_upload(1, sequence)

        # Assert
        self._awg_0.load_sequencer_program.assert_called_once_with(sequence)

    def test_enable_sequencer_with_defaults__calls_zi_method(self):
        """Test enable sequencer, calls relevant ZI method."""
        # Arrange

        # Act
        self._instr.enable_sequencer(1)

        # Assert
        self._awg_0.enable_sequencer.assert_called_once_with(single=True)

    def test_enable_sequencer_with_disable_flag_false__calls_zi_method(self):
        """Test enable sequencer with disable flag False, calls relevant ZI method."""
        # Arrange

        # Act
        self._instr.enable_sequencer(1, False)

        # Assert
        self._awg_0.enable_sequencer.assert_called_once_with(single=False)

    def test_wait_done_calls_zi_method(self):
        """Test wait done, calls relevant ZI method."""
        # Arrange

        # Act
        self._instr.wait_done(1)

        # Assert
        self._awg_0.wait_done.assert_called_once_with(timeout=30)

    def test_compile_sequencer_program_calls_zi_method(self):
        """Test compile program, calls relevant ZI method."""
        # Arrange
        sequencer_code = "this is the program to compile"
        self._awg_0.compile_sequencer_program.return_value = (bytes(sequencer_code, "utf-8"), {})

        # Act
        self._instr.compile_sequencer_program(1, sequencer_code)

        # Assert
        self._awg_0.compile_sequencer_program.assert_called_once_with(sequencer_code)

    def test_upload_program_calls_zi_method(self):
        """Test upload program, calls relevant ZI method."""
        # Arrange
        sequencer_code = bytes()

        # Act
        self._instr.upload_program(1, sequencer_code)

        # Assert
        self._awg_0.elf.data.assert_called_once_with(sequencer_code)

    def test_write_to_waveform_memory_calls_zi_method(self):
        """Test write to waveform memoery with defaults indexes, calls relevant ZI method."""
        # Arrange
        waveforms = hdawg.zhinst.toolkit.Waveforms()

        # Act
        self._instr.write_to_waveform_memory(1, waveforms)

        # Assert
        self._awg_0.write_to_waveform_memory.assert_called_once_with(waveforms, None)

    def test_write_to_waveform_memory_with_indexes_calls_zi_method(self):
        """Test write to waveform memoery with indexes, calls relevant ZI method."""
        # Arrange
        waveforms = hdawg.zhinst.toolkit.Waveforms()
        indexes = [0, 1]

        # Act
        self._instr.write_to_waveform_memory(1, waveforms, indexes)

        # Assert
        self._awg_0.write_to_waveform_memory.assert_called_once_with(waveforms, indexes)

    def test_read_from_waveform_memory_calls_zi_method(self):
        """Test read from waveform memoery with defaults indexes, calls relevant ZI method."""
        # Arrange

        # Act
        self._instr.read_from_waveform_memory(1)

        # Assert
        self._awg_0.read_from_waveform_memory.assert_called_once_with(None)

    def test_read_from_waveform_memory_with_indexes_calls_zi_method(self):
        """Test read from waveform memoery with indexes, calls relevant ZI method."""
        # Arrange
        indexes = [0, 1]

        # Act
        self._instr.read_from_waveform_memory(1, indexes)

        # Assert
        self._awg_0.read_from_waveform_memory.assert_called_once_with(indexes)

    def test_validate_waveform_with_program_called_zi_method(self):
        """Test validate waveform with program, calls relevant ZI method."""
        # Arrange
        waveforms = Mock(return_value=hdawg.zhinst.toolkit.Waveforms())
        program = bytes("test_code", "utf-8")

        # Act
        self._instr.validate_waveforms(1, waveforms, program)

        # Assert
        waveforms.validate.assert_called_once_with(program)

    def test_validate_waveform_without_program_called_zi_method(self):
        """Test validate waveform without program, calls relevant ZI method."""
        # Arrange
        waveforms = Mock(return_value=hdawg.zhinst.toolkit.Waveforms())

        # Act
        self._instr.validate_waveforms(1, waveforms)

        # Assert
        waveforms.validate.assert_called_once_with(self._awg_0.waveform.descriptors())

    def test_get_command_table_calls_zi_method(self):
        """Test get command table, calls relevant ZI method."""
        # Arrange

        # Act
        self._instr.get_command_table(1)

        # Assert
        self._awg_0.commandtable.load_from_device.assert_called_once_with()
