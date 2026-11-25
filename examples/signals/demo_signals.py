"""Demo tasks and RPC object for the QMI signals tutorial.

- `SamplerTask` publishes data (`sig_sample`) and a trigger (`sig_overrange`).
- `AmplitudeControlTask` receives the data of another task and publishes its own signal.
- `Shutter` is a plain RPC object (not a task) that publishes a signal from within its RPC methods.
"""

import time
from typing import NamedTuple

import qmi
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_TaskStopException, QMI_TimeoutException
from qmi.core.pubsub import QMI_Signal, QMI_SignalReceiver, QMI_SignalSubscriber
from qmi.core.rpc import QMI_RpcObject, rpc_method
from qmi.core.task import QMI_Task, QMI_TaskRunner
from qmi.utils.context_managers import subscribe_unsubscribe


class SampleData(NamedTuple):
    """A timestamped sample from the sine generator.

    Signal arguments travel between contexts in pickled form, so define the data types at module level
    in a module that both the publisher and the subscriber can import.

    Attributes:
        timestamp: UNIX timestamp of the sample in seconds.
        value:     Sample value.
    """

    timestamp: float
    value: float


class SamplerTask(QMI_Task):
    """Read the sine generator at a fixed rate and publish every sample.

    Signals:
        sig_sample:    Data signal, published with one `SampleData` argument for every sample.
        sig_overrange: Trigger signal without arguments, published when |sample| exceeds the threshold.
    """

    sig_sample = QMI_Signal([SampleData])
    sig_overrange = QMI_Signal([])

    def __init__(
        self, task_runner: QMI_TaskRunner, name: str, nsg_name: str, rate: float = 10.0, threshold: float = 50.0
    ) -> None:
        super().__init__(task_runner, name)
        self._nsg_name = nsg_name
        self._period = 1.0 / rate
        self._threshold = threshold

    def run(self) -> None:
        nsg = qmi.get_instrument(self._nsg_name)
        try:
            while not self.stop_requested():
                sample = SampleData(timestamp=time.time(), value=nsg.get_sample())
                self.sig_sample.publish(sample)
                if abs(sample.value) > self._threshold:
                    self.sig_overrange.publish()

                self.sleep(self._period)

        except QMI_TaskStopException:
            pass  # A normal stop request; no need for a warning in the log.


class AmplitudeControlSettings(NamedTuple):
    """Settings of the `AmplitudeControlTask`.

    Attributes:
        limit: Samples with |value| above this limit decrease the amplitude, others increase it.
        gain:  Relative amplitude change per received sample.
    """

    limit: float
    gain: float


class AmplitudeControlTask(QMI_Task):
    """Control the sine generator amplitude, driven by the samples that another task publishes.

    The task does not know or care who publishes the samples: it gets a `QMI_SignalSubscriber`,
    i.e. a signal attribute of a proxy, such as ``sampler_task.sig_sample``.

    Signals:
        sig_amplitude_changed: Published with the new amplitude after every adjustment.
        sig_settings_updated:  Inherited from `QMI_Task`; published by `update_settings()` when new settings arrive.
    """

    sig_amplitude_changed = QMI_Signal([float])
    settings: AmplitudeControlSettings

    def __init__(
        self, task_runner: QMI_TaskRunner, name: str, nsg_name: str, sample_signal: QMI_SignalSubscriber
    ) -> None:
        super().__init__(task_runner, name)
        self._nsg_name = nsg_name
        self._sample_signal = sample_signal
        self.settings = AmplitudeControlSettings(limit=10.0, gain=0.1)

    def run(self) -> None:
        nsg = qmi.get_instrument(self._nsg_name)

        # A control loop only needs the latest sample. A queue of length one with DISCARD_OLD
        # keeps the newest sample and drops the stale ones.
        receiver = QMI_SignalReceiver(max_queue_length=1, discard_policy=QMI_SignalReceiver.DISCARD_OLD)

        # The context manager unsubscribes the receiver on exit, also when the task is stopped or crashes.
        with subscribe_unsubscribe(self._sample_signal, receiver):
            try:
                while not self.stop_requested():
                    self.update_settings()
                    try:
                        # Wait for the next sample. Inside a task this wait is interrupted by a stop request,
                        # which raises QMI_TaskStopException, so no polling with sleep() is needed.
                        received = receiver.get_next_signal(timeout=1.0)
                    except QMI_TimeoutException:
                        continue  # The publisher is not running (yet).

                    sample: SampleData = received.args[0]
                    amplitude = nsg.get_amplitude()
                    if abs(sample.value) > self.settings.limit:
                        amplitude *= 1.0 - self.settings.gain
                    else:
                        amplitude *= 1.0 + self.settings.gain

                    nsg.set_amplitude(amplitude)
                    self.sig_amplitude_changed.publish(amplitude)

            except QMI_TaskStopException:
                pass


class Shutter(QMI_RpcObject):
    """A simulated shutter. Any RPC object, not only a task, can publish signals.

    Signals:
        sig_state: Published with the new state (True = open) whenever an RPC call changes the state.
    """

    sig_state = QMI_Signal([bool])

    def __init__(self, context: QMI_Context, name: str) -> None:
        super().__init__(context, name)
        self._is_open = False

    def _set_state(self, is_open: bool) -> None:
        self._is_open = is_open
        self.sig_state.publish(is_open)

    @rpc_method
    def open(self) -> None:
        """Open the shutter."""
        self._set_state(True)

    @rpc_method
    def close(self) -> None:
        """Close the shutter."""
        self._set_state(False)

    @rpc_method
    def is_open(self) -> bool:
        """Return True if the shutter is open."""
        return self._is_open
