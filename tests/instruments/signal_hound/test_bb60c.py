"""Unit tests for the Signal Hound BB60C spectrum analyzer driver."""

import logging
import unittest
from unittest.mock import MagicMock, call, patch

from tests.patcher import PatcherQmiContext as QMI_Context

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_InstrumentIdentification

from qmi.instruments.signal_hound import SignalHound_BB60C

MODULE = "qmi.instruments.signal_hound.bb60c"


class SignalHoundBB60CTestCase(unittest.TestCase):
    """Tests for BB60C SCPI behavior using a mocked transport and protocol."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)
        transport_patcher = patch(f"{MODULE}.create_transport")
        self.create_transport = transport_patcher.start()
        self.addCleanup(transport_patcher.stop)
        self.transport = MagicMock()
        self.create_transport.return_value = self.transport

        protocol_patcher = patch(f"{MODULE}.ScpiProtocol")
        self.protocol_class = protocol_patcher.start()
        self.addCleanup(protocol_patcher.stop)
        self.protocol = MagicMock()
        self.protocol_class.return_value = self.protocol

        self.instr = SignalHound_BB60C(QMI_Context("test_signal_hound_bb60c"), "bb60c", "tcp:192.0.2.5")
        self.instr.open()
        self.protocol.reset_mock()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()

    def test_transport_configuration(self):
        """The network transport is configured with the default BB60C port."""
        self.create_transport.assert_called_once_with(
            "tcp:192.0.2.5", default_attributes={"port": SignalHound_BB60C.DEFAULT_PORT}
        )
        self.protocol_class.assert_called_once_with(
            self.transport, default_timeout=SignalHound_BB60C.DEFAULT_RESPONSE_TIMEOUT
        )

    def test_open_close(self):
        """Opening and closing the QMI instrument opens and closes its transport."""
        self.transport.open.assert_called_once_with()
        self.assertTrue(self.instr.is_open())

        self.instr.close()

        self.transport.close.assert_called_once_with()
        self.assertFalse(self.instr.is_open())

    def test_get_idn(self):
        """The four ID fields are parsed into a QMI instrument identification."""
        self.protocol.ask.return_value = "Signal Hound,BB60C,12345,1.2"

        self.assertEqual(
            QMI_InstrumentIdentification("Signal Hound", "BB60C", "12345", "1.2"), self.instr.get_idn()
        )
        self.protocol.ask.assert_called_once_with("*IDN?")

    def test_get_idn_invalid_response_raises(self):
        """An ID response with the wrong number of fields raises an instrument exception."""
        self.protocol.ask.return_value = "Signal Hound,BB60C"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_frequency_and_reference_getters(self):
        """Frequency and reference-level queries parse numeric responses."""
        for method, command in (
            (self.instr.get_frequency_center, ":sense:frequency:center?"),
            (self.instr.get_frequency_span, ":sense:frequency:span?"),
            (self.instr.get_reference_level, ":sens:power:rf:rlev?"),
        ):
            with self.subTest(method=method.__name__):
                self.protocol.reset_mock()
                self.protocol.ask.return_value = "123.5"

                self.assertEqual(123.5, method())
                self.protocol.ask.assert_called_once_with(command)

    def test_invalid_numeric_response_raises(self):
        """A nonnumeric response to a numeric query raises an instrument exception."""
        self.protocol.ask.return_value = "invalid"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_frequency_center()

    def test_configuration_commands(self):
        """Configuration methods send the corresponding SCPI write and check the error queue."""
        commands_and_calls = [
            (":sense:frequency:center 1000000", lambda: self.instr.set_frequency_center(1_000_000)),
            (":sens:frequency:span 2000000", lambda: self.instr.set_frequency_span(2_000_000)),
            (":sens:power:rf:rlev -20", lambda: self.instr.set_reference_level(-20)),
            (":sens:band:res:auto on", lambda: self.instr.set_rbw_auto_enabled(True)),
            (":sens:band:vid:auto off", lambda: self.instr.set_vbw_auto_enabled(False)),
            (":sens:band:vid 3000", lambda: self.instr.set_vbw(3000)),
            (":sens:band:res 1000", lambda: self.instr.set_rbw(1000)),
            (":trac:aver:coun 5", lambda: self.instr.set_trace_average_count(5)),
            (":trac:type maxhold", lambda: self.instr.set_trace_type("maxhold")),
            (":trac:sel 2", lambda: self.instr.set_trace_index(2)),
            (":trac:upd off", lambda: self.instr.set_trace_update_enabled(False)),
            (":trac:disp on", lambda: self.instr.set_trace_display_enabled(True)),
            (":inst SA", lambda: self.instr.set_mode("SA")),
            (":initiate:continuous on", lambda: self.instr.set_continous_enabled(True)),
            (":FREQUENCY:CENTER:STEP 100", lambda: self.instr.set_freq_sweep_step(100)),
        ]
        for command, call_method in commands_and_calls:
            with self.subTest(command=command):
                self.protocol.reset_mock()
                self.protocol.ask.return_value = '0,"No error"'

                call_method()

                self.protocol.write.assert_called_once_with(command)
                self.protocol.ask.assert_called_once_with("SYSTem:ERRor?")

    def test_invalid_trace_type_and_index_raise_without_writing(self):
        """Unsupported trace selections raise before sending a command."""
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_trace_type("invalid")
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_trace_index(7)

        self.protocol.write.assert_not_called()
        self.protocol.ask.assert_not_called()

    def test_error_queue_response_raises(self):
        """A nonzero instrument error queue response raises an exception."""
        self.protocol.ask.return_value = '100,"Command error"'

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_rbw(1000)

    def test_reset(self):
        """Reset waits for preset completion with the longer reset timeout, then checks errors."""
        self.protocol.ask.side_effect = ["1", '0,"No error"']

        self.instr.reset()

        self.assertEqual(
            [
                call("SYST:PRES?", timeout=SignalHound_BB60C.RESET_TIMEOUT),
                call("SYSTem:ERRor?"),
            ],
            self.protocol.ask.call_args_list,
        )

    def test_trace_data(self):
        """Trace values are paired with frequencies generated from start and increment queries."""
        self.protocol.ask.side_effect = ["-10,-20,-30", "100", "2"]

        frequencies, power = self.instr.get_trace()

        self.assertEqual([100, 102, 104], frequencies.tolist())
        self.assertEqual([-10, -20, -30], power.tolist())

    def test_trigger_sweep_and_wait(self):
        """Each requested sweep waits for operation-complete before checking errors."""
        self.protocol.ask.side_effect = ["1", "1", '0,"No error"']

        self.instr.trigger_sweep_and_wait(times=2)

        self.assertEqual(2, sum(call.args[0] == ":INIT; *OPC?" for call in self.protocol.ask.call_args_list))
        self.assertEqual("SYSTem:ERRor?", self.protocol.ask.call_args_list[-1].args[0])


if __name__ == "__main__":
    unittest.main()
