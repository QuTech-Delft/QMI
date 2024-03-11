"""Unit-tests for Teraxion TFN."""
import unittest
from unittest.mock import patch

import qmi
from qmi.instruments.teraxion.tfn import Teraxion_TFN


class TestTeraxionTfn(unittest.TestCase):

    def setUp(self):
        qmi.start("unittest_tfn")

        # Add patches
        with patch("qmi.instruments.teraxion.tfn.create_transport") as self._transport_mock:
            self.tfn = Teraxion_TFN(qmi.context(), "teraxion_tfn", "")
        self.tfn.open()

    def tearDown(self) -> None:
        self.tfn.close()
        qmi.stop()

    @unittest.mock.patch("qmi.core.scpi_protocol.ScpiProtocol.ask")
    def test_get_firmware_version_gets_firmware_version(self, ask_mock):
        """Test get firmware version, gets firmware version."""
        # Arrange
        expected_version = "1.0"
        expected_command = "S600fP S6106P"
        ask_mock.return_value = "001000000100"

        ver = self.tfn.get_firmware_version()

        ask_mock.assert_called_once_with(expected_command, timeout=self.tfn.DEFAULT_READ_TIMEOUT)
        self.assertEqual(ver, expected_version)