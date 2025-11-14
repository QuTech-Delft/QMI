#! /usr/bin/env python

import time

import qmi
from qmi.instruments.cobolt.laser_06_01 import Cobolt_Laser_06_01
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100D
from qmi.utils.context_managers import start_stop

laser_transport = "serial:/dev/ttyACM0"
pm_device = "USB0::4883::32888::P0019304::0::INSTR"

with start_stop(qmi, "calibration_server", "qmi.conf"):
    with qmi.make_instrument("laser", Cobolt_Laser_06_01, laser_transport
            ) as laser, qmi.make_instrument("pm", Thorlabs_PM100D, pm_device, '@py'
            ) as pm:
        time.sleep(0.100)
        input("\nRelay server active, press Enter to quit ...\n")
