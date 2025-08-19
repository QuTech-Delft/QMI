#! /usr/bin/env python

import time

import numpy as np
import matplotlib.pyplot as plt

import qmi
from qmi.utils.context_managers import start_stop

with start_stop(qmi, "calibration_client", "qmi.conf"):

    laser = qmi.get_instrument("calibration_server.laser")
    pm    = qmi.get_instrument("calibration_server.pm")

    print("Laser:", laser.get_idn())
    print("Power meter:", pm.get_idn())

    pm.set_wavelength(515)
    pm.set_autorange(False)
    pm.set_range(0.100)

    current_start = 50.0
    current_stop  = 200.0
    nsteps = 80

    laser_current = np.zeros(nsteps+1)
    laser_power   = np.zeros(nsteps+1)

    plt.ion()
    (fig, ax) = plt.subplots(figsize=(7,5), dpi=160)
    ax.set_title("Laser calibration", fontsize=16)
    ax.set_xlabel("Laser current [mA]", fontsize=12)
    ax.set_ylabel("Laser power [mW]", fontsize=12)
    ax.tick_params(labelsize=11)
    ax.grid(True)
    fig.canvas.draw()
    fig.canvas.flush_events()

    (ln,) = ax.plot([], [], "rx-", linewidth=2)
    fig.canvas.draw()
    fig.canvas.flush_events()

    laser.set_laser_on_state(True)
    laser.set_constant_current_mode()
    laser.set_drive_current(current_start)
    time.sleep(10)

    for k in range(nsteps+1):
        x = current_start + (current_stop - current_start) * k / nsteps
        laser.set_drive_current(x)
        time.sleep(0.5)
        y = pm.get_power()
        laser_current[k] = x
        laser_power[k] = y
        ln.set_data(laser_current[:k+1], 1000 * laser_power[:k+1])
        ax.relim()
        ax.autoscale_view()
        fig.canvas.draw()
        fig.canvas.flush_events()

    laser.set_drive_current(current_start)
    laser.set_laser_on_state(False)

    (idx,) = np.where(laser_power > 0.002)
    (slope, offset) = np.polyfit(laser_current[idx], laser_power[idx], deg=1)

    print("Offset:", -offset / slope, "mA")
    print("Slope:", 1000 * slope, "mW/mA")

    ax.plot(laser_current, 1000 * (offset + slope * laser_current), "b", linewidth=2)

    fig.canvas.toolbar.update()
    fig.canvas.toolbar.push_current()

plt.ioff()
plt.show()
