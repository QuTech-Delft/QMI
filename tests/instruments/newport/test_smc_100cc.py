"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.newport import Newport_Smc100Cc
from qmi.instruments.newport.actuators import TRA12CC, TRB6CC, CMA25CCL


class TestNewportSmc100Cc(unittest.TestCase):
    """
    Tests for the single axis motion controller.
    """

    TRANSPORT_STR = "/dev/cu.usbserial-FT5TMFGL"

    def setUp(self):
        qmi.start("Test100CcControllerContext", console_loglevel="CRITICAL")
        # Add patches
        patcher = patch(
            'qmi.instruments.newport.single_axis_motion_controller.create_transport', spec=QMI_TcpTransport)
        self._transport_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch(
            'qmi.instruments.newport.single_axis_motion_controller.ScpiProtocol', autospec=True)
        self._scpi_mock: Mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUTs
        self.controller_address = 1
        self.instr: Newport_Smc100Cc = qmi.make_instrument(
            "sam_controller", Newport_Smc100Cc, self.TRANSPORT_STR, "FT5TMFGL",
            {1: TRA12CC, 2: TRB6CC, 3: CMA25CCL},
            90210)
        self.instr = cast(Newport_Smc100Cc, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()

    def test_set_encoder_resolution_without_controller_address_sets_resolution(self):
        """Test set encoder resolution."""
        resolution = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}SU%s\r\n" % resolution),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        self.instr.set_encoder_increment_value(resolution)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_set_encoder_resolution_with_controller_address_sets_resolution(self):
        """Test set encoder resolution with controller address."""
        resolution = 0.004
        self._scpi_mock.ask.side_effect = ["@", "@", "@"]
        expected_write_calls = [
            call("3RS\r\n"),
            call("3PW1\r\n"),
            call(f"3SU{resolution}\r\n"),
            call("3PW0\r\n")
        ]
        expected_ask_calls = [
            call("3TE\r\n"),
            call("3TE\r\n"),
            call("3TE\r\n")
        ]
        self.instr.set_encoder_increment_value(resolution, 3)
        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)

    def test_get_encoder_increment_value_gets_value(self):
        """Test get encoder increment value."""
        expected_encoder_unit = 10
        encoder_resolution = TRA12CC.ENCODER_RESOLUTION
        self._scpi_mock.ask.side_effect = [
            "@", "@", f"{self.controller_address}SU %s" % (encoder_resolution / expected_encoder_unit), "@"]
        expected_write_calls = [
            call(f"{self.controller_address}RS\r\n"),
            call(f"{self.controller_address}PW1\r\n"),
            call(f"{self.controller_address}PW0\r\n")
        ]
        expected_ask_calls = [
            call(f"{self.controller_address}TE\r\n"),
            call(f"{self.controller_address}SU?\r\n"),
            call(f"{self.controller_address}TE\r\n")
        ]
        actual_encoder_unit = self.instr.get_encoder_increment_value()
        self.assertEqual(expected_encoder_unit, actual_encoder_unit)

        self._scpi_mock.write.assert_has_calls(expected_write_calls)
        self._scpi_mock.ask.assert_has_calls(expected_ask_calls)
