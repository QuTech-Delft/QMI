"""Test cases for Zurich Instruments HDAWG."""

import logging
import random
import unittest
from unittest.mock import Mock


import qmi.instruments.zurich_instruments.hdawg as hdawg
from qmi.instruments.zurich_instruments import ZurichInstruments_Hdawg
from tests.patcher import PatcherQmiContext


class TestZurichInstruments_Hdawg(unittest.TestCase):
    """Testcase for HDAWG initialization."""

    def setUp(self):
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)
        logging.getLogger("qmi.core.rpc").setLevel(logging.ERROR)
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        self.qmi_patcher = PatcherQmiContext()
        self.qmi_patcher.start(self._ctx_qmi_id)
        self._instr: ZurichInstruments_Hdawg = self.qmi_patcher.make_instrument(
            "test_hdawg", ZurichInstruments_Hdawg, "test_host", 1, "test_device_name"
        )

        # Mock DAQ server
        self._daq_server = Mock()

        hdawg.zhinst.toolkit.Session = Mock(return_value=self._daq_server)

    def tearDown(self):
        self.qmi_patcher.stop()
        logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)
        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_open_connects_to_device(self):
        # Arrange

        # Act
        self._instr.open()

        # Assert
