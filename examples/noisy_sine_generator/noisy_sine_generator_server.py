#! /usr/bin/env python

"""Server for the noisy sine generator example.

This script starts the `nsg_server` QMI context, which makes a `NoisySineGenerator`
instrument available to other contexts.

Point the `QMI_CONFIG` environment variable to `examples/noisy_sine_generator/qmi.conf`
before running this script::

  export QMI_CONFIG=examples/noisy_sine_generator/qmi.conf
  python examples/noisy_sine_generator/noisy_sine_generator_server.py
"""

import time

import qmi
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
from qmi.utils.context_managers import start_stop

with start_stop(qmi, "nsg_server"):

    with qmi.make_instrument("nsg", NoisySineGenerator) as nsg:
        time.sleep(0.100)
        input("\nSimulated noisy sine generator instrument active, press Enter to quit ...\n")
