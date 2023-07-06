"""Testcase of Stanford Research Systems Sim900 instrument"""
import logging
import unittest
from unittest.mock import patch, call

import qmi
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_UsageException
from qmi.core.transport import QMI_Transport
from qmi.instruments.stanford_research_systems import Srs_Sim900


class TestSim900(unittest.TestCase):
    """Testcase of Stanford Research Systems Sim900 instrument"""

    def setUp(self):
        qmi.start("test_sim_900")
        # Add patches
        patcher = patch('qmi.instruments.stanford_research_systems.sim900.create_transport', spec=QMI_Transport)
        self.transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.sim900 = qmi.make_instrument('Sim900', Srs_Sim900, "")
        self.sim900.open()

    def tearDown(self):
        if self.sim900.is_open():
            self.sim900.close()
        qmi.stop()
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_check_constructor(self):
        # act
        self.sim900.close()
        # assert
        self.transport_mock.open.assert_called()
        self.transport_mock.close.assert_called()

    def test_invalid_use_raises_exception(self):
        # Suppress logging.
        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)
        self.sim900.close()
        # arrange & act
        with self.assertRaises(QMI_InvalidOperationException):
            self.sim900.input_bytes_waiting(6)

    def test_invalid_port(self):
        error_ports = [0,9]
        # arrange & act
        for error_port in error_ports:
            with self.subTest(i=error_port):
                with self.assertRaises(QMI_UsageException):
                    self.sim900.input_bytes_waiting(error_port)

    def test_input_bytes_waiting(self):
        # arrange
        self.transport_mock.read_until.return_value = b'10\n'
        expected_calls = [
            call.open(),
            call.write(b'NINP? 6\n'),
            call.read_until(message_terminator=b'\n', timeout=0.1)]

        # act
        result = self.sim900.input_bytes_waiting(6)
        # assert
        self.assertEqual(self.transport_mock.method_calls, expected_calls)
        self.assertEqual(result, 10)

    def test_get_raw_bytes(self):
        # arrange
        self.transport_mock.read.return_value = b'0123456789'
        expected_calls = [
            call.open(),
            call.write(b'RAWN? 6,10\n'),
            call.read(10, timeout=0.1)]

        # act
        result = self.sim900.get_raw_bytes(6, 10)
        # assert
        self.assertEqual(self.transport_mock.method_calls, expected_calls)
        self.assertEqual(result, b'0123456789')

    def test_send_terminated_message(self) -> None:
        # arrange
        expected_calls = [
            call.open(),
            call.write(b'SNDT 6,\"hi\"\n')]

        # act
        self.sim900.send_terminated_message(6, 'hi')
        # assert
        self.assertEqual(self.transport_mock.method_calls, expected_calls)

    def test_ask_module(self) -> None:
        # arrange
        self.transport_mock.read_until.return_value = b'10\n'
        self.transport_mock.read.return_value = b'123456789\n'

        expected_calls = [
            call.open(),
            call.write(b'SNDT 6,\"hi\"\n'),
            call.write(b'NINP? 6\n'),
            call.read_until(message_terminator=b'\n', timeout=0.1),
            call.write(b'RAWN? 6,10\n'),
            call.read(10, timeout=0.1)]
        # act
        result = self.sim900.ask_module(6,"hi")

        # assert
        self.assertEqual(self.transport_mock.method_calls, expected_calls)
        self.assertEqual(result, '123456789')
