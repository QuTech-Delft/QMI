#! /usr/bin/env python

import qmi

from qmi.core.pubsub import QMI_SignalReceiver
from qmi.utils.context_managers import start_stop

with start_stop(qmi, "nsg_client", "qmi.conf"):

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
