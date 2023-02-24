#! /usr/bin/env python3

import time

import qmi
from qmi.instruments.cobolt.laser_06_01 import Cobolt_Laser_06_01
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100D

laser_transport = "serial:/dev/ttyACM0"
pm_device = "USB0::4883::32888::P0019304::0::INSTR"

qmi.start("calibration_server", "qmi.conf")

laser = qmi.make_instrument("laser", Cobolt_Laser_06_01, laser_transport)
pm    = qmi.make_instrument("pm", Thorlabs_PM100D, pm_device, '@py')

laser.open()
pm.open()

time.sleep(0.100)
input("\nRelay server active, press Enter to quit ...\n")

