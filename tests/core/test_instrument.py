#! /usr/bin/env python3
"""Unit-tests for testing context managing for `QMI_Instrument` class."""
import logging
import unittest

from numpy import random

from tests.patcher import PatcherQmiContext as QMI_Context
from qmi.core.context import QMI_Instrument, rpc_method


class MyInstrument_TestDriver(QMI_Instrument):

    def __init__(self, context: QMI_Context, name: str) -> None:
        super().__init__(context, name)
        self._it_is_open = False

    @rpc_method
    def open(self):
        super().open()
        self._it_is_open = True

    @rpc_method
    def close(self):
        super().close()
        self._it_is_open = False

    @rpc_method
    def is_it_open_then(self):
        return self._it_is_open


class TestInstrumentContextManager(unittest.TestCase):

    def setUp(self):
        # Suppress logging.
        logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)

        self._ctx_qmi_id = f"test-qmi-instrument-{random.randint(0, 100)}"
        self.qmi_patcher = QMI_Context("test_instrument_context_manager")
        self.qmi_patcher.start(self._ctx_qmi_id)

    def tearDown(self) -> None:
        self.qmi_patcher.stop()

    def test_create_instance(self):
        """Test creating an instrument object works without starting qmi."""
        instr = MyInstrument_TestDriver(self.qmi_patcher, self._ctx_qmi_id)
        # Get RPC object info
        name = instr.get_name()
        category = instr.get_category()
        # Assert
        self.assertFalse(instr.is_open())
        self.assertEqual(self._ctx_qmi_id, name)
        self.assertEqual("instrument", category)

    def test_make_instrument_with_with(self):
        """Test creating an instrument object with context manager and also opens and closes it."""
        with MyInstrument_TestDriver(self.qmi_patcher, self._ctx_qmi_id) as instr:
            # Assert
            name = instr.get_name()
            category = instr.get_category()
            # Assert
            self.assertTrue(instr.is_open())
            self.assertEqual(self._ctx_qmi_id, name)
            self.assertEqual("instrument", category)
            # Also see extra action in the instrument driver's `open` has been executed
            self.assertTrue(instr.is_it_open_then())

        # Assert
        self.assertFalse(instr.is_open())
        # Also see extra action in the instrument driver's `close` has been executed
        self.assertFalse(instr.is_it_open_then())


class TestInstrumentMakeFunction(unittest.TestCase):

    def setUp(self):
        # Suppress logging.
        logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)

        # Start a context with creating the "instrument".
        self.c1 = QMI_Context("c1")
        self.c1.start()

    def tearDown(self):
        self.c1.stop()
        self.c1 = None

        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_make_instrument(self):
        """Test making the instrument with 'make_instrument' works as expected"""
        instr_proxy = self.c1.make_instrument("instr", MyInstrument_TestDriver)

        # Assert
        self.assertFalse(instr_proxy.is_open())

    def test_make_instrument_with_with(self):
        """Test making the instrument with 'make_instrument' works also with context manager."""
        with self.c1.make_instrument("instr", MyInstrument_TestDriver) as instr_proxy:
            # Assert
            self.assertTrue(instr_proxy.is_open())
            # Also see extra action in the instrument driver's `open` has been executed
            self.assertTrue(instr_proxy.is_it_open_then())

        # Assert
        self.assertFalse(instr_proxy.is_open())
        # Also see extra action in the instrument driver's `close` has been executed
        self.assertFalse(instr_proxy.is_it_open_then())


if __name__ == '__main__':
    unittest.main()
