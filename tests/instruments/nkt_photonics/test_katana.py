"""Unit-tests for the NKT Photonics Katana laser driver."""

import logging
import unittest
from unittest.mock import MagicMock, patch

from qmi.core.exceptions import QMI_InvalidOperationException
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.instruments.nkt_photonics.katana import NKT_Katana

from tests.patcher import PatcherQmiContext as QMI_Context

MODULE = "qmi.instruments.nkt_photonics.katana"
TERMINATOR = b"\n"


class KatanaOpenCloseTestCase(unittest.TestCase):
    """Tests for creating, opening and closing the driver."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)
        patcher = patch(f"{MODULE}.create_transport")
        self.create_transport = patcher.start()
        self.addCleanup(patcher.stop)
        self.transport = MagicMock()
        self.create_transport.return_value = self.transport

        self.instr = NKT_Katana(QMI_Context("test_katana_open_close"), "katana", "serial:COM1")

    def test_init_transport(self):
        """The transport is created with the serial settings of the laser."""
        self.create_transport.assert_called_once_with(
            "serial:COM1",
            default_attributes={"baudrate": 38400},
        )

    def test_response_timeout_is_rpc_property(self):
        """RESPONSE_TIMEOUT is exposed as an RPC property."""
        self.assertIn("RESPONSE_TIMEOUT", NKT_Katana._rpc_properties)

    def test_open_close(self):
        """Opening opens the transport and discards stale input, closing closes the transport."""
        self.instr.open()
        self.transport.open.assert_called_once_with()
        self.transport.discard_read.assert_called_once_with()
        self.assertTrue(self.instr.is_open())

        self.instr.close()
        self.transport.close.assert_called_once_with()
        self.assertFalse(self.instr.is_open())

    def test_commands_when_closed_raise(self):
        """Sending a command without opening the instrument raises an exception."""
        for method in ["get_emission_status", "get_idn", "get_last_response"]:
            with self.subTest(method=method):
                with self.assertRaises(QMI_InvalidOperationException):
                    getattr(self.instr, method)()

        self.transport.write.assert_not_called()
        self.transport.read_until.assert_not_called()


class KatanaCommandsTestCase(unittest.TestCase):
    """Tests for the commands sent to the laser and the parsing of its responses."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)
        patcher = patch(f"{MODULE}.create_transport")
        self.transport = MagicMock()
        patcher.start().return_value = self.transport
        self.addCleanup(patcher.stop)

        self.instr = NKT_Katana(QMI_Context("test_katana_commands"), "katana", "serial:COM1")
        self.instr.open()
        self.transport.reset_mock()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()

    def assert_command_sent(self, command: bytes) -> None:
        """Assert that exactly the given command was sent, after discarding stale input."""
        self.transport.discard_read.assert_called_once_with()
        self.transport.write.assert_called_once_with(command + b"\n")
        self.transport.read_until.assert_called_once_with(
            message_terminator=TERMINATOR, timeout=NKT_Katana.RESPONSE_TIMEOUT
        )

    def test_get_idn(self):
        """The three-line version response is parsed into the identification."""
        for model_line in [b"Model:Katana-05HP\r\n", b"Model: Katana-05HP\r\n", b"Katana-05HP\r\n"]:
            with self.subTest(model_line=model_line):
                self.transport.reset_mock()
                self.transport.read_until.side_effect = [b"V1.07\r\n", model_line, b"2019-03-14\r\n"]

                idn = self.instr.get_idn()

                self.assertEqual(
                    QMI_InstrumentIdentification(vendor="NKT", model="Katana-05HP", serial=None, version="V1.07"),
                    idn,
                )
                self.transport.discard_read.assert_called_once_with()
                self.transport.write.assert_called_once_with(b"version?\n")
                self.assertEqual(3, self.transport.read_until.call_count)

    def test_get_firmware_version(self):
        """All three lines of the version response are read and the firmware version line is returned."""
        self.transport.read_until.side_effect = [b"V1.07\r\n", b"Model:Katana-05HP\r\n", b"2019-03-14\r\n"]

        self.assertEqual("V1.07", self.instr.get_firmware_version())

        self.transport.write.assert_called_once_with(b"version?\n")
        self.assertEqual(3, self.transport.read_until.call_count)

    def test_simple_commands(self):
        """Each query and set method sends its own command and returns the response."""
        for method, args, command in [
            ("get_emission_status", (), b"le?"),
            ("set_emission_on", (), b"le=1"),
            ("set_emission_off", (), b"le=0"),
            ("get_trigger_input_level", (), b"ltll?"),
            ("get_trigger_source", (), b"lts?"),
            ("set_laser_power_mode", (), b"lip=0"),
            ("set_laser_current_mode", (), b"lip=1"),
            ("get_laser_output_power", (), b"lp?"),
            ("get_laser_pump_current", (), b"li?"),
            ("get_initial_power_level", (), b"lx_ips?"),
            ("set_frequency", (40000000,), b"lx_freq=40000000"),
            ("get_frequency", (), b"lx_freq?"),
        ]:
            with self.subTest(method=method):
                self.transport.reset_mock()
                self.transport.read_until.return_value = b"response\r\n"

                self.assertEqual("response", getattr(self.instr, method)(*args))

                self.assert_command_sent(command)

    def test_number_formatting(self):
        """Numeric set values are formatted with fixed decimals and zero-padded to five characters."""
        for method, value, command in [
            ("set_trigger_input_level", 1.5, b"ltll=01.50"),
            ("set_trigger_input_level", -1.5, b"ltll=-1.50"),
            ("set_trigger_input_level", -5.0, b"ltll=-5.00"),
            ("set_laser_output_power", 4.1, b"lp=04.10"),
            ("set_laser_pump_current", 12.0, b"li=12.00"),
            ("set_initial_power_level", 1.2345, b"lx_ips=1.234"),
        ]:
            with self.subTest(method=method, value=value):
                self.transport.reset_mock()
                self.transport.read_until.return_value = b"ok\r\n"

                getattr(self.instr, method)(value)

                self.assert_command_sent(command)

    def test_set_trigger_source(self):
        """A valid trigger source is sent to the laser."""
        for mode in [0, 1, 2]:
            with self.subTest(mode=mode):
                self.transport.reset_mock()
                self.transport.read_until.return_value = b"ok\r\n"

                self.instr.set_trigger_source(mode)

                self.assert_command_sent(f"lts={mode}".encode())

    def test_set_invalid_trigger_source_raises(self):
        """An invalid trigger source raises an exception and is not sent to the laser."""
        for mode in [-1, 3]:
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    self.instr.set_trigger_source(mode)

        self.transport.write.assert_not_called()

    def test_set_trigger_input_level_out_of_range_raises(self):
        """A trigger input level outside [-5, 5] V raises an exception and is not sent to the laser."""
        for voltage in [-5.01, 5.01]:
            with self.subTest(voltage=voltage):
                with self.assertRaises(ValueError):
                    self.instr.set_trigger_input_level(voltage)

        self.transport.write.assert_not_called()

    def test_get_last_response(self):
        """The next pending line is read without sending a command."""
        self.transport.read_until.return_value = b"Model:Katana-05HP\r\n"

        self.assertEqual("Model:Katana-05HP", self.instr.get_last_response())

        self.transport.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
