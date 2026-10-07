#! /usr/bin/env python

"""Client for the noisy sine generator example.

This script starts the `nsg_client` QMI context and connects to the `nsg_server` and
`nsg_service` contexts to show the instrument and task interfaces that they provide.

Point the `QMI_CONFIG` environment variable to `examples/noisy_sine_generator/qmi.conf`
before running this script, with `nsg_server` and `nsg_service` already running::

  export QMI_CONFIG=examples/noisy_sine_generator/qmi.conf
  python examples/noisy_sine_generator/noisy_sine_generator_client.py
"""

import qmi

from qmi.core.pubsub import QMI_SignalReceiver
from qmi.utils.context_managers import start_stop

with start_stop(qmi, "nsg_client"):

    qmi.show_contexts()
    qmi.show_rpc_objects()
    qmi.show_instruments()

    # The context "nsg_server" provides a simple sample-based interface.
    print()
    print("Getting some samples from 'nsg_server'...")

    nsg = qmi.get_instrument("nsg_server.nsg")
    for i in range(10):
        sample = nsg.get_sample()
        print(i, sample)

    # The context "nsg_service" provides a pubsub-based interface.
    print()
    print("Subscribing to 'nsg_service' for a while...")

    receiver = QMI_SignalReceiver()
    proxy = qmi.get_task("nsg_service.controller")
    proxy.sig_sample.subscribe(receiver)
    for i in range(10):
        sig = receiver.get_next_signal(timeout=None)
        print(i, "received: {} with arguments t={:.2f} value={:.2f}".format(sig.signal_name, *sig.args))
