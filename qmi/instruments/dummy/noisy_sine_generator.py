""" Instrument driver for a virtual noisy sine generator."""

import time
import math
import random

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method


class NoisySineGenerator(QMI_Instrument):
    """Simulated instrument, useful for testing."""

    def __init__(self, context: QMI_Context, name: str) -> None:
        super().__init__(context, name)
        self.frequency = 2.0
        self.amplitude = 100.0
        self.noise = 1.0

    @rpc_method
    def set_frequency(self, value: float) -> None:
        """Set the frequency of the sine wave.

        Parameters:
            value: The frequency value (unitless).
        """
        self._check_is_open()
        valid = isinstance(value, float) and math.isfinite(value) and value >= 0.0
        if not valid:
            raise ValueError("Bad value for frequency: {!r}".format(value))
        self.frequency = value

    @rpc_method
    def get_frequency(self) -> float:
        """Get the frequency of the sine wave.

        Returns:
            self.frequency: The current frequency (unitless).
        """
        self._check_is_open()
        return self.frequency

    @rpc_method
    def set_amplitude(self, value: float) -> None:
        """Set the amplitude of the sine wave.

        Parameters:
            value: The new amplitude (unitless).
        """
        self._check_is_open()
        valid = isinstance(value, float) and math.isfinite(value) and value >= 0.0
        if not valid:
            raise ValueError("Bad value for amplitude: {!r}".format(value))

        self.amplitude = value

    @rpc_method
    def get_amplitude(self) -> float:
        """Get the amplitude of the sine wave.

        Returns:
            self.amplitude: The current amplitude (unitless).
        """
        self._check_is_open()
        return self.amplitude

    @rpc_method
    def set_noise(self, value: float) -> None:
        """Set noise level for the sine wave.

        Parameters:
            value: The new noise level (unitless).
        """
        self._check_is_open()
        valid = isinstance(value, float) and math.isfinite(value) and value >= 0.0
        if not valid:
            raise ValueError("Bad value for noise: {!r}".format(value))
        self.noise = value

    @rpc_method
    def get_noise(self) -> float:
        """Get noise level for the sine wave.

        Returns:
            self.noise: The current noise level (unitless).
        """
        self._check_is_open()
        return self.noise

    @rpc_method
    def wait(self, duration: float) -> None:
        """Make driver to wait.

        Parameters:
            duration: The wait duration in seconds.
        """
        self._check_is_open()
        if duration < 0.0:
            raise ValueError("Bad value for duration: {!r}".format(duration))

        time.sleep(duration)

    @rpc_method
    def get_sample(self) -> float:
        """Get a 'sample' from the virtual instrument sine wave.

        Returns:
            sample: A time-dependent sample value of sine wave with given frequency and amplitude,
                    and added Gaussian noise.
        """
        self._check_is_open()
        t = time.time()
        return self.amplitude * math.sin(t * self.frequency * 2 * math.pi) + random.gauss(0.0, self.noise)
