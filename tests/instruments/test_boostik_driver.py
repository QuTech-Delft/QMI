#! /usr/bin/env python3

"A basic test script for the NKT Koheras Boostik laser amplifier."

import argparse
import qmi

from qmi.utils.context_managers import start_stop, open_close
from qmi.instruments.nkt_photonics.boostik import KoherasBoostikLaserAmplifier

boostik_transports = {
        "node1" : "serial:/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A1070VQD-if00-port0",
        "node2" : "serial:/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A106T0T3-if00-port0"
    }

def _dump_boostik_status(boostik: KoherasBoostikLaserAmplifier):
    print("amplifier information .......... : {}".format(boostik.get_amplifier_information()))
    print("current setpoint ............... : {:10.2f} [A]".format(boostik.get_current_setpoint()))
    print("actual current ................. : {:10.2f} [A]".format(boostik.get_actual_current()))
    print("diode booster temperature ...... : {:10.2f} [°C]".format(boostik.get_diode_booster_temperature()))
    print("ambient temperature ............ : {:10.2f} [°C]".format(boostik.get_ambient_temperature()))
    print("input power .................... : {:10.2f} [?]".format(boostik.get_input_power()))
    print("amplifier enabled .............. : {} [bool]".format(boostik.get_amplifier_enabled()))

def main():

    parser = argparse.ArgumentParser(description="Basic test of the Koheras Boostik laser amplifier.")
    parser.add_argument("node", choices = ["node1", "node2"], help="use the Boostik connected to this node")

    args = parser.parse_args()

    with start_stop(qmi, "test_boostik_driver"):
        boostik_transport = boostik_transports[args.node]
        boostik = qmi.make_instrument("boostik", KoherasBoostikLaserAmplifier, boostik_transport)
        boostik.open()
        try:
            _dump_boostik_status(boostik)
        finally:
            boostik.close()

if __name__ == "__main__":
    main()
