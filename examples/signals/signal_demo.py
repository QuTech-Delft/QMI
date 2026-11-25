#!/usr/bin/env python
"""QMI signals tutorial: publishing and receiving data and triggers within one context."""

import time
from contextlib import ExitStack

import qmi
from qmi.core.exceptions import QMI_TimeoutException
from qmi.core.pubsub import QMI_SignalReceiver
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
from qmi.utils.context_managers import subscribe_unsubscribe

from demo_signals import AmplitudeControlSettings, AmplitudeControlTask, SamplerTask, Shutter


def receive_data_manually(sampler) -> None:
    """1. Subscribe, receive and unsubscribe by hand."""
    print("--- 1. Manual subscribe / unsubscribe")
    receiver = QMI_SignalReceiver()
    sampler.sig_sample.subscribe(receiver)
    try:
        for _ in range(3):
            received = receiver.get_next_signal(timeout=1.0)
            sample = received.args[0]
            print(f"{received.publisher_name}.{received.signal_name}: value = {sample.value:.2f}")
    finally:
        # Without this, the receiver stays subscribed and keeps queueing samples forever.
        sampler.sig_sample.unsubscribe(receiver)


def receive_data_with_context_manager(sampler) -> None:
    """2. The same with `subscribe_unsubscribe`. Passing None creates a default receiver."""
    print("--- 2. subscribe_unsubscribe context manager")
    with subscribe_unsubscribe(sampler.sig_sample, None) as receiver:
        for _ in range(3):
            sample = receiver.get_next_signal(timeout=1.0).args[0]
            print(f"value = {sample.value:.2f}")


def wait_for_trigger(sampler, nsg) -> None:
    """3. Wait for a trigger signal, i.e. a signal without arguments."""
    print("--- 3. Waiting for a trigger")
    with subscribe_unsubscribe(sampler.sig_overrange, None) as trigger:
        nsg.set_amplitude(200.0)  # Provoke the trigger.
        try:
            received = trigger.get_next_signal(timeout=5.0)
            print(f"trigger {received.signal_name} received, args = {received.args}")
        except QMI_TimeoutException:
            print("no over-range within 5 seconds")


def receive_from_several_signals(control, shutter) -> None:
    """5. One receiver subscribed to several signals of different publishers."""
    print("--- 5. One receiver, several signals")
    receiver = QMI_SignalReceiver()
    with ExitStack() as stack:
        for signal in (control.sig_amplitude_changed, control.sig_settings_updated, shutter.sig_state):
            stack.enter_context(subscribe_unsubscribe(signal, receiver))

        # Generate some activity.
        shutter.open()
        control.set_settings(AmplitudeControlSettings(limit=20.0, gain=0.05))
        time.sleep(0.5)
        shutter.close()

        # Drain the queue and dispatch on the signal name.
        while receiver.has_signal_ready():
            received = receiver.get_next_signal()
            if received.signal_name == "sig_state":
                print("shutter is", "open" if received.args[0] else "closed")
            elif received.signal_name == "sig_settings_updated":
                print("controller has new settings:", received.args[0])
            else:
                print(f"amplitude = {received.args[0]:.2f}")
    # Leaving the ExitStack unsubscribed the receiver from all three signals.


def detect_dropped_signals(sampler) -> None:
    """4. A short queue drops the oldest signals; `receiver_seqnr` shows the gaps."""
    print("--- 4. Detecting dropped signals")
    receiver = QMI_SignalReceiver(max_queue_length=3, discard_policy=QMI_SignalReceiver.DISCARD_OLD)
    with subscribe_unsubscribe(sampler.sig_sample, receiver):
        time.sleep(1.0)  # About 10 samples are published, only the last 3 are kept.
        seqnrs = [receiver.get_next_signal().receiver_seqnr for _ in range(receiver.get_queue_length())]
        print("sequence numbers in the queue:", seqnrs)


def main() -> None:
    with qmi.start("signal_demo"):
        with qmi.make_instrument("nsg", NoisySineGenerator) as nsg:
            shutter = qmi.make_rpc_object("shutter", Shutter)
            with qmi.make_task("sampler", SamplerTask, "signal_demo.nsg") as sampler:
                receive_data_manually(sampler)
                receive_data_with_context_manager(sampler)
                wait_for_trigger(sampler, nsg)
                detect_dropped_signals(sampler)
                # The controller task gets the sampler's signal as a constructor argument.
                with qmi.make_task("control", AmplitudeControlTask, "signal_demo.nsg", sampler.sig_sample) as control:
                    receive_from_several_signals(control, shutter)


if __name__ == "__main__":
    main()
