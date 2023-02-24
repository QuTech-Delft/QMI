#! /usr/bin/env python3

import qmi, time
from qmi.instruments.raspberry.relay import RaspberryPiRelay

qmi.start("relay_server", "qmi.conf")

relay = qmi.make_instrument("relay", RaspberryPiRelay, pin_nr=7)

time.sleep(0.100)
input("\nRelay server active, press Enter to quit ...\n")
