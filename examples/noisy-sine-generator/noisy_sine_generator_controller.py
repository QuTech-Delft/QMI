"""
Controller task for NSG.
"""

import time
from typing import NamedTuple

from qmi.core.exceptions import QMI_Exception, QMI_TaskStopException
from qmi.core.task import QMI_Task, QMI_TaskRunner
from qmi.core.pubsub import QMI_Signal
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator


class NoisySineGeneratorSettings(NamedTuple):
    """Noisy sine generator settings.

    Attributes:
        frequency: frequency of the sine wave.
        amplitude: amplitude of the sine wave.
        noise:     noise standard deviation.
    """
    frequency: float = 2.0
    amplitude: float = 100.0
    noise: float = 1.0


class NoisySineGeneratorStatus(NamedTuple):
    """Noisy sine generator status.

    Attributes:
        runtime: time running.
    """
    runtime: float


class NoisySineGeneratorController(QMI_Task):
    """Controller for the noisy sine generator.

    This is a simple task for controlling a noisy sine generator.
    """

    sig_sample = QMI_Signal([float, float])
    sig_status = QMI_Signal([NoisySineGeneratorStatus])

    def __init__(self,
                 task_runner: QMI_TaskRunner,
                 name: str,
                 generator: NoisySineGenerator,
                 settings: NoisySineGeneratorSettings,
                 sample_time: float = 1.0
                ) -> None:
        """Initialize the controller task.

        Parameters:
            task_runner:    Task runner instance (will be provided by QMI via `make_task()`).
            name:           Name of the task.
            generator:      Instance of NoisySineGenerator to be controlled.
            settings:       Initial settings for the NoisySineGenerator.
            sample_time:    Sample time in seconds (default: 1.0).
        """
        super().__init__(task_runner, name)

        self._nsg = generator
        self.settings: NoisySineGeneratorSettings = settings
        self._sample_time = sample_time

    def _config_nsg(self) -> None:
        self._nsg.set_frequency(self.settings.frequency)
        self._nsg.set_amplitude(self.settings.amplitude)
        self._nsg.set_noise(self.settings.noise)

    def run(self) -> None:
        """Main loop."""
        # Configure the device.
        self._config_nsg()

        # Start the sampling loop.
        t_start = time.monotonic()
        try:
            # `stop_requested()` will return True if the task should stop (e.g. when context is torn down).
            while not self.stop_requested():

                # If new settings have been pushed to the task, they are put in a FIFO. Calling `update_settings()`
                # returns True if the FIFO is non-empty. One settings object is popped from the FIFO and stored in
                # `self.settings`. The routine returns False if the FIFO is empty.
                if self.update_settings():
                    self._config_nsg()

                # Sample the NSG.
                t_current = time.monotonic() - t_start
                sample = self._nsg.get_sample()
                status = NoisySineGeneratorStatus(runtime=t_current)

                # Broadcast the sample and the status of the NSG.
                self.sig_sample.publish(t_current, sample)
                self.sig_status.publish(status)

                # Sleep until the next sample time.
                t_next = t_current + self._sample_time
                delta = t_next - time.monotonic()
                if delta > 0:
                    self.sleep(duration=delta)

        except QMI_TaskStopException:
            # Do nothing, this is expected when the task is stopped while it is sleeping.
            pass

        except QMI_Exception:
            # Unexpected exceptions are re-raised.
            raise

        finally:
            # Clean-up code goes here.
            pass
