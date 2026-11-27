"""Unit-tests for the NKT Photonics Fianium supercontinuum laser driver."""

import logging
import unittest
from unittest.mock import MagicMock, call, patch

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.instruments.nkt_photonics.fianium import NKT_Fianium

MODULE = "qmi.instruments.nkt_photonics.fianium"
TERMINATOR = b"\n\r"


class FianiumOpenCloseTestCase(unittest.TestCase):
    """Tests for creating, opening and closing the driver."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)
        patcher = patch(f"{MODULE}.create_transport")
        self.create_transport = patcher.start()
        self.addCleanup(patcher.stop)
        self.transport = MagicMock()
        self.create_transport.return_value = self.transport

        self.instr = NKT_Fianium(QMI_Context("test_fianium_open_close"), "fianium", "serial:COM1")

    def test_init_transport(self):
        """The transport is created with the serial settings of the laser."""
        self.create_transport.assert_called_once_with(
            "serial:COM1",
            default_attributes={"baudrate": 19200, "bytesize": 8, "parity": 'N', "stopbits": 1.0},
        )

    def test_open_close(self):
        """Opening opens the transport and discards stale input, closing closes the transport."""
        self.instr.open()
        self.transport.open.assert_called_once_with()
        self.transport.discard_read.assert_called_once_with()
        self.assertTrue(self.instr.is_open())

        self.instr.close()
        self.transport.close.assert_called_once_with()
        self.assertFalse(self.instr.is_open())

    def test_ask_when_closed_raises(self):
        """Sending a command without opening the instrument raises an exception."""
        with self.assertRaises(QMI_InvalidOperationException):
            self.instr.get_alarms()

        self.transport.write.assert_not_called()


class FianiumCommandsTestCase(unittest.TestCase):
    """Tests for the commands sent to the laser and the parsing of its responses."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)
        patcher = patch(f"{MODULE}.create_transport")
        self.transport = MagicMock()
        patcher.start().return_value = self.transport
        self.addCleanup(patcher.stop)

        self.instr = NKT_Fianium(QMI_Context("test_fianium_commands"), "fianium", "serial:COM1")
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
            message_terminator=TERMINATOR, timeout=NKT_Fianium.RESPONSE_TIMEOUT
        )

    def test_ask_strips_terminator(self):
        """The response is returned as a string without the trailing terminator."""
        self.transport.read_until.return_value = b"No alarms\n\r"

        self.assertEqual("No alarms", self.instr.get_alarms())

        self.assert_command_sent(b"A?")

    def test_get_idn(self):
        """The serial number and version are queried and combined in the identification."""
        self.transport.read_until.side_effect = [b"Serial number 12345\n\r", b"Version 1.2.3\n\r"]

        with patch(f"{MODULE}.time.sleep"):
            idn = self.instr.get_idn()

        self.assertEqual(
            QMI_InstrumentIdentification(
                vendor="NKT",
                model="Femtopower_1060_Supercontinuum_Laser_Source",
                serial="12345",
                version="Version 1.2.3",
            ),
            idn,
        )
        self.transport.write.assert_has_calls([call(b"J?\n"), call(b"V?\n")])

    def test_get_idn_invalid_serial_raises(self):
        """A serial number response that does not end in an integer raises an exception."""
        self.transport.read_until.side_effect = [b"Serial number unknown\n\r", b"Version 1.2.3\n\r"]

        with patch(f"{MODULE}.time.sleep"):
            with self.assertRaises(QMI_InstrumentException):
                self.instr.get_idn()

    def test_simple_commands(self):
        """Each query and set method sends its own command and returns the response."""
        for method, args, command in [
            ("get_alarms", (), b"A?"),
            ("clear_all_alarms", (), b"A=0"),
            ("get_back_refl_pd", (), b"B?"),
            ("display_command_list", (), b"H?"),
            ("get_status_display_interval", (), b"I?"),
            ("set_status_display_interval", (), b"I=1"),
            ("get_control_mode", (), b"M?"),
            ("set_control_mode", (1,), b"M=1"),
            ("get_preamp_pd", (), b"P?"),
            ("get_q", (), b"Q?"),
            ("get_heater_countdown", (), b"O?"),
            ("get_operation_time", (), b"W?"),
            ("get_status_display_mode", (), b"X?"),
            ("set_status_display_mode", (2,), b"X=2"),
            ("get_temp", (), b"T?"),
        ]:
            with self.subTest(method=method):
                self.transport.reset_mock()
                self.transport.read_until.return_value = b"response\n\r"

                self.assertEqual("response", getattr(self.instr, method)(*args))

                self.assert_command_sent(command)

    def test_set_invalid_mode_raises(self):
        """An invalid control or status display mode raises an exception and is not sent to the laser."""
        for method in ["set_control_mode", "set_status_display_mode"]:
            for mode in [-1, 3]:
                with self.subTest(method=method, mode=mode):
                    with self.assertRaises(ValueError):
                        getattr(self.instr, method)(mode)

        self.transport.write.assert_not_called()

    def test_set_q_temperature_ready(self):
        """The output power is set once the laser temperature is ready."""
        self.transport.read_until.side_effect = [b"Laser Temperature ready\n\r", b"Q=50\n\r"]

        self.assertEqual("Q=50", self.instr.set_q(50))

        self.transport.write.assert_has_calls([call(b"O?\n"), call(b"Q=50\n")])

    def test_set_q_temperature_not_ready_raises(self):
        """Setting the output power raises an exception while the laser is still heating up."""
        self.transport.read_until.return_value = b"Countdown 120 s\n\r"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_q(50)

        self.transport.write.assert_called_once_with(b"O?\n")


if __name__ == "__main__":
    unittest.main()
