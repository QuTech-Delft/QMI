"""Unit tests for Dummy Noisy Sine Generator."""
import time
from typing import cast
import unittest
from unittest.mock import Mock, patch

import qmi
from qmi.instruments.dummy import Dummy_NoisySineGenerator as NSG
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_UnknownRpcException

from tests.patcher import PatcherQmiContext as QMI_Context


class TestNsgOpenClose(unittest.TestCase):
    """Open close test for Dummy NSG."""

    def setUp(self):
        self.ctx = QMI_Context("dummy")
        self.ctx.start()
        self.nsg = NSG(self.ctx, "nsg")

    def tearDown(self):
        self.ctx.stop()

    def test_open_close(self):
        """Test the basic open-close functions and logic."""
        self.assertFalse(self.nsg.is_open())

        self.nsg.open()

        self.assertTrue(self.nsg.is_open())

        with self.assertRaises(QMI_InvalidOperationException):
            self.nsg.open()

        self.nsg.close()

        self.assertFalse(self.nsg.is_open())

        with self.assertRaises(QMI_InvalidOperationException):
            self.nsg.close()

    def test_function_call_excepts_if_not_open(self):
        """Test that an error is raised if any other method is called before 'open'."""
        with self.assertRaises(QMI_InvalidOperationException):
            self.nsg.get_noise()

        self.nsg.open()
        self.nsg.get_noise()

    
class TestNsgFunctions(unittest.TestCase):
    """Tests for Dummy NSG methods and constants."""
    
    def setUp(self):
        qmi.start("dummy", None)
        NSG.max_wait = 0.1
        self.nsg = qmi.make_instrument("nsg", NSG)
        self.nsg.open()

    def tearDown(self):
        self.nsg.close()
        qmi.stop()

    def test_frequency_setting(self):
        """Test that frequency can be set."""
        expected_freq = 10.0
        initial_freq = self.nsg.get_frequency()

        self.nsg.set_frequency(expected_freq)

        new_freq = self.nsg.get_frequency()

        self.assertNotEqual(initial_freq, new_freq)
        self.assertEqual(expected_freq, new_freq)

    def test_frequency_set_excepts(self):
        """Test frequency setting excepts at invalid values."""
        invalid_freqs = [-1.0, NSG.max_frequency + 1.0]
        for invalid_freq in invalid_freqs:
            with self.assertRaises(ValueError):
                self.nsg.set_frequency(invalid_freq)

    def test_max_frequency_change(self):
        """Test that _rpc_constants 'max_frequency' constant can be manipulated."""
        invalid_freq = NSG.max_frequency + 1.0
        new_max = NSG.max_frequency + 2.0

        with self.assertRaises(ValueError):
            self.nsg.set_frequency(invalid_freq)

        self.nsg.max_frequency = new_max
        self.nsg.set_frequency(invalid_freq)
        new_freq = self.nsg.get_frequency()

        self.assertEqual(invalid_freq, new_freq)

    def test_amplitude_setting(self):
        """Test that amplitude can be set."""
        expected_amp = 10.0
        initial_amp = self.nsg.get_amplitude()

        self.nsg.set_amplitude(expected_amp)

        new_amp = self.nsg.get_amplitude()

        self.assertNotEqual(initial_amp, new_amp)
        self.assertEqual(expected_amp, new_amp)

    def test_amplitude_set_excepts(self):
        """Test amplitude setting excepts at invalid values."""
        invalid_amps = [-1.0, NSG.max_amplitude + 1.0]
        for invalid_amp in invalid_amps:
            with self.assertRaises(ValueError):
                self.nsg.set_amplitude(invalid_amp)

    def test_max_amplitude_change(self):
        """Test that _rpc_constants 'max_amplitude' constant can be manipulated."""
        invalid_amp = NSG.max_amplitude + 1.0
        new_max = NSG.max_amplitude + 2.0

        with self.assertRaises(ValueError):
            self.nsg.set_amplitude(invalid_amp)

        self.nsg.max_amplitude = new_max
        self.nsg.set_amplitude(invalid_amp)
        new_amp = self.nsg.get_amplitude()

        self.assertEqual(invalid_amp, new_amp)

    def test_noise_setting(self):
        """Test that noise can be set."""
        expected_noise = 10.0
        initial_noise = self.nsg.get_noise()

        self.nsg.set_noise(expected_noise)

        new_noise = self.nsg.get_noise()

        self.assertNotEqual(initial_noise, new_noise)
        self.assertEqual(expected_noise, new_noise)

    def test_noise_set_excepts(self):
        """Test noise setting excepts at invalid values."""
        invalid_noises = [-1.0, NSG.max_noise + 1.0]
        for invalid_noise in invalid_noises:
            with self.assertRaises(ValueError):
                self.nsg.set_noise(invalid_noise)

    def test_max_noise_not_modifiable(self):
        """Test that 'max_noise' cannot be changed as it is not in _rpc_constants."""
        with self.assertRaises(AttributeError):
            self.nsg.max_noise = NSG.max_noise + 2.0

    def test_wait_setting(self):
        """Test that wait waits."""
        expected_wait = 0.01

        start = time.time()
        self.nsg.wait(expected_wait)
        end = time.time()

        self.assertGreaterEqual(end - start, expected_wait)

    def test_wait_excepts(self):
        """Test wait excepts at invalid values."""
        invalid_waits = [-1.0, NSG.max_wait + 1.0]
        for invalid_wait in invalid_waits:
            with self.assertRaises(ValueError):
                self.nsg.wait(invalid_wait)

    def test_max_wait_change(self):
        """Test that _rpc_constants 'max_wait' constant can be manipulated."""
        invalid_wait = NSG.max_wait + 0.1
        new_max = NSG.max_wait + 0.2

        with self.assertRaises(ValueError):
            self.nsg.wait(invalid_wait)

        self.nsg.max_wait = new_max
        self.nsg.wait(invalid_wait)

    def test_get_sample(self):
        """Test get_sample, happy flow."""
        value = self.nsg.get_sample()

        self.assertGreater(value, -2.0 * NSG.max_amplitude)
        self.assertLess(value, 2.0 * NSG.max_amplitude)
