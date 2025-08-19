#! /usr/bin/env python

import time

import qmi
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
from qmi.utils.context_managers import start_stop

with start_stop(qmi, "nsg_server", "qmi.conf"):

    with qmi.make_instrument("nsg", NoisySineGenerator) as nsg:
        time.sleep(0.100)
        input("\nSimulated noisy sine generator instrument active, press Enter to quit ...\n")
