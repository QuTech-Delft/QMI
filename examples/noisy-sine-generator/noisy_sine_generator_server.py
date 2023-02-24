#! /usr/bin/env python3

import time

import qmi
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator

qmi.start("nsg_server", "qmi.conf")

nsg = qmi.make_instrument("nsg", NoisySineGenerator)

time.sleep(0.100)
input("\nSimulated noisy sine generator instrument active, press Enter to quit ...\n")

qmi.stop()
