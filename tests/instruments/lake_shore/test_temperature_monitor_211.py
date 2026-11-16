"""Unit tests for the Lake Shore Model 211 temperature monitor driver."""

import logging
import unittest
from unittest.mock import MagicMock, patch

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_InstrumentIdentification

from qmi.instruments.lake_shore.temperature_monitor_211 import LakeShore_Model211
from tests.patcher import PatcherQmiContext as QMI_Context

MODULE = "qmi.instruments.lake_shore.temperature_monitor_211"


class LakeShoreModel211TestCase(unittest.TestCase):
    """Tests for the Model 211 driver using a mocked serial transport and SCPI protocol."""

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

        time_patcher = patch(f"{MODULE}.time")
        self.time = time_patcher.start()
        self.addCleanup(time_patcher.stop)
        self.time.monotonic.return_value = 1000.0

        self.instr = LakeShore_Model211(QMI_Context("test_lake_shore_211"), "temp_monitor", "serial:COM1")
        self.instr.open()
        self.protocol.reset_mock()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()

    def test_transport_and_protocol_configuration(self):
        """The serial transport and SCPI protocol use the Model 211 settings."""
        self.create_transport.assert_called_once_with(
            "serial:COM1", default_attributes={"baudrate": 9600, "bytesize": 7, "parity": "E", "stopbits": 1}
        )
        self.protocol_class.assert_called_once_with(
            self.transport,
            command_terminator="\r\n",
            response_terminator="\r\n",
            default_timeout=LakeShore_Model211.DEFAULT_RESPONSE_TIMEOUT,
        )

    def test_open_close(self):
        """Opening and closing the driver opens and closes the serial transport."""
        self.transport.open.assert_called_once_with()
        self.assertTrue(self.instr.is_open())

        self.instr.close()

        self.transport.close.assert_called_once_with()
        self.assertFalse(self.instr.is_open())

    def test_get_idn(self):
        """The four comma-separated ID fields are returned as an identification object."""
        self.protocol.ask.return_value = "Lake Shore,211,12345,1.2"

        result = self.instr.get_idn()

        self.assertEqual(QMI_InstrumentIdentification("Lake Shore", "211", "12345", "1.2"), result)
        self.protocol.ask.assert_called_once_with("*IDN?")

    def test_get_idn_invalid_response_raises(self):
        """An ID response with the wrong number of fields raises an instrument exception."""
        self.protocol.ask.return_value = "Lake Shore,211"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_reset_and_status(self):
        """Reset writes *RST and status queries RDGST?."""
        self.instr.reset()
        self.protocol.write.assert_called_once_with("*RST")

        self.protocol.reset_mock()
        self.protocol.ask.return_value = "000"
        self.assertEqual("000", self.instr.get_status())
        self.protocol.ask.assert_called_once_with("RDGST?")

    def test_get_error(self):
        """A zero status register means no error; any other value means an error."""
        for status, expected in (("000", False), ("001", True)):
            with self.subTest(status=status):
                self.protocol.reset_mock()
                self.protocol.ask.return_value = status

                self.assertEqual(expected, self.instr.get_error())
                self.protocol.ask.assert_called_once_with("RDGST?")

    def test_numeric_readings(self):
        """Temperature and sensor-unit getters parse floating-point SCPI responses."""
        for method, command in (
            (self.instr.get_temperature_celsius, "CRDG?"),
            (self.instr.get_temperature_fahrenheit, "FRDG?"),
            (self.instr.get_temperature_kelvin, "KRDG?"),
            (self.instr.get_sensor_units_input, "SRDG?"),
        ):
            with self.subTest(method=method.__name__):
                self.protocol.reset_mock()
                self.protocol.ask.return_value = "12.375"

                self.assertEqual(12.375, method())
                self.protocol.ask.assert_called_once_with(command)

    def test_invalid_numeric_reading_raises(self):
        """A nonnumeric measurement response raises an instrument exception."""
        self.protocol.ask.return_value = "not-a-number"

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_temperature_celsius()

    def test_string_readings(self):
        """Input type, input curve, and alarm getters return their raw SCPI responses."""
        for method, command in (
            (self.instr.get_input_type, "INTYPE?"),
            (self.instr.get_input_curve, "INCRV?"),
            (self.instr.get_alarm, "ALARM?"),
        ):
            with self.subTest(method=method.__name__):
                self.protocol.reset_mock()
                self.protocol.ask.return_value = "sensor configuration"

                self.assertEqual("sensor configuration", method())
                self.protocol.ask.assert_called_once_with(command)

    def test_first_communication_does_not_wait(self):
        """The first communication after construction is sent without waiting."""
        self.protocol.ask.return_value = "000"

        self.instr.get_status()

        self.time.sleep.assert_not_called()

    def test_communication_waits_for_guard_time(self):
        """A communication shortly after the previous one waits until the guard time has passed."""
        self.protocol.ask.return_value = "000"
        # Check and end of the first query, check and end of the second communication.
        self.time.monotonic.side_effect = [1000.0, 1000.0, 1000.02, 1000.08]

        self.instr.get_status()
        self.instr.reset()

        self.time.sleep.assert_called_once()
        self.assertAlmostEqual(LakeShore_Model211.COMMAND_GUARD_TIME - 0.02, self.time.sleep.call_args.args[0])
        self.protocol.write.assert_called_once_with("*RST")

    def test_communication_after_guard_time_does_not_wait(self):
        """A communication after the guard time has already passed is sent without waiting."""
        self.protocol.ask.return_value = "000"
        self.time.monotonic.side_effect = [1000.0, 1000.0, 1000.06, 1000.07]

        self.instr.get_status()
        self.instr.get_status()

        self.time.sleep.assert_not_called()

    def test_guard_time_applies_after_failed_communication(self):
        """The guard time is also respected after a communication that raised an exception."""
        self.protocol.ask.side_effect = [QMI_InstrumentException("timeout"), "000"]
        self.time.monotonic.side_effect = [1000.0, 1000.0, 1000.01, 1000.06]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_status()
        self.instr.get_status()

        self.time.sleep.assert_called_once()
        self.assertAlmostEqual(LakeShore_Model211.COMMAND_GUARD_TIME - 0.01, self.time.sleep.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
