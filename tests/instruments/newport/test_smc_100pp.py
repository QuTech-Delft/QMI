"""Unit tests for a Newport single axis motion controller."""
from typing import cast
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.newport import Newport_Smc100Pp
from qmi.instruments.newport.actuators import UTS100PP


class TestNewportSmc100Pp(unittest.TestCase):
    """
    Tests for the single axis motion controller.
    """

    TRANSPORT_STR = "/dev/cu.usbserial-FT5TMFGL"

    def setUp(self):
        qmi.start("Test100PpControllerContext", console_loglevel="CRITICAL")
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
        self.instr: Newport_Smc100Pp = qmi.make_instrument(
            "sam_controller", Newport_Smc100Pp, self.TRANSPORT_STR, "FT5TMFGL",
            {1: UTS100PP},
            90210)
        self.instr = cast(Newport_Smc100Pp, self.instr)
        self.instr.open()

    def tearDown(self):
        self.instr.close()
        qmi.stop()
