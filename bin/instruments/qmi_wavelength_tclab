#! /usr/bin/env python
"""Command line client for the Wavelength Electronic TC Lab temperature controller."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys
import time

import qmi
from qmi.instruments.wavelength.tclab import Wavelength_TC_Lab
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Wavelength Electronics TC Lab temperature controller."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="show a list of attached instruments")
    group.add_argument("--serial", help="Unique serial number of device.")
    group.add_argument("--address",  help="QMI RPC address of device.")

    parser.add_argument("--power", type=int, choices=(0, 1), help="turn instrument on (1) or off (0)")
    parser.add_argument("--output", type=int, choices=(0, 1), help="turn controller output on (1) or off (0)")
    parser.add_argument("--setpoint", type=float, help="change temperature setpoint")
    parser.add_argument("--log", type=int, metavar="N", help="log temperature during N intervals of 0.05 s")

    args = parser.parse_args()

    if args.list:
        list_instruments()
        return 0

    instr: Wavelength_TC_Lab
    with start_stop(qmi, "wavelength_tclab_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        print("IDN:", instr.get_idn(), end="\n\n")

        if args.power == 1:
            print("Switching power on")
            instr.set_power_on(True)
            time.sleep(2.0)

        if args.output == 1:
            print("Enabling controller output")
            instr.set_output_enabled(True)

        if args.output == 0:
            print("Disabling controller output")
            instr.set_output_enabled(False)

        if args.setpoint is not None:
            print("Changing setpoint to {:.4f}".format(args.setpoint))
            instr.set_setpoint(args.setpoint)

        if args.power == 0:
            print("Switching power off")
            instr.set_power_on(False)
            time.sleep(1.0)

        print()
        show_instrument_status(instr)

        if args.log:
            log_temperature(instr, args.log)

    return 0


def list_instruments():
    """Show a list of compatible instruments."""

    print("Detected Wavelength Electronics TC Lab instruments:")
    instruments = Wavelength_TC_Lab.list_instruments()
    for instrument in instruments:
        print("  ", instrument)
    if not instruments:
        print("  ", "(none)")
    print()


def parse_instrument_source(args) -> AbstractContextManager:
    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    # make the instrument
    if args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="TCLAB",
                instrument_class=Wavelength_TC_Lab,
                transport="usbtmc:vendorid=0x{vendor:04x}:productid=0x{product:04x}:serialnr={serial}".format(
                    vendor=Wavelength_TC_Lab.USB_VENDOR_ID,
                    product=Wavelength_TC_Lab.USB_PRODUCT_ID,
                    serial=args.serial
                )
            )
        )

    raise ValueError("Expected a source for the instrument!")


def show_instrument_status(instr):
    """Report the current status of the instrument."""

    power_on_state = instr.get_power_on()
    print("Power state:          {}".format("ON" if power_on_state else "standby"))

    output_state = instr.get_output_enabled()
    print("Controller output:    {}".format("enabled" if output_state else "disabled"))

    temp_unit = instr.get_unit()

    if power_on_state:
        temp_act = instr.get_temperature()
        print("Actual temperature:   {:8.4f} {}".format(temp_act, temp_unit[0]))

        temp_setpoint = instr.get_setpoint()
        print("Temperature setpoint: {:8.4f} {}".format(temp_setpoint, temp_unit[0]))

        tec_current = instr.get_tec_current()
        tec_voltage = instr.get_tec_voltage()
        print("Actual TEC current:   {:8.4f} A".format(tec_current))
        print("Actual TEC voltage:   {:8.4f} V".format(tec_voltage))

        autotune_mode = instr.get_autotune_mode()
        print("Tuning mode:          {}".format(autotune_mode.name))

        autotune_valid = instr.get_autotune_is_valid()
        print("Tuning data valid:    {}".format("yes" if autotune_valid else "no"))

    pid_params = instr.get_pid_parameters()
    print("PID parameters:       P={} I={} D={}".format(*pid_params))
    print()

    (temp_low, temp_high) = instr.get_temperature_limit()
    print("Temperature limits:   low={:.4f} high={:.4f} {}".format(temp_low, temp_high, temp_unit[0]))

    vlim = instr.get_tec_voltage_limit()
    (ilim_pos, ilim_neg) = instr.get_tec_current_limit()
    print("Voltage limit:        {:8.4f} V".format(vlim))
    print("Current limit:        pos={:.4f} neg={:.4f} A".format(ilim_pos, ilim_neg))
    print()

    cond = instr.get_condition_status()
    print("Condition status:")
    print("    current limit:    {}".format(cond.current_limit))
    print("    sensor limit:     {}".format(cond.sensor_limit))
    print("    temperature high: {}".format(cond.temperature_high))
    print("    temperature low:  {}".format(cond.temperature_low))
    print("    sensor shorted:   {}".format(cond.sensor_shorted))
    print("    sensor open:      {}".format(cond.sensor_open))
    print("    tec open:         {}".format(cond.tec_open))
    print("    in tolerance:     {}".format(cond.in_tolerance))
    print("    output on:        {}".format(cond.output_on))
    print("    laser shutdown:   {}".format(cond.laser_shutdown))
    print("    power on:         {}".format(cond.power_on))
    print()


def log_temperature(instr: Wavelength_TC_Lab, n: int):
    """Log temperature and TEC current."""

    print("#time          temperature    setpoint tec_current")

    for _ in range(n):
        timestamp = time.time()
        temp_act = instr.get_temperature()
        temp_set = instr.get_setpoint()
        tec_current = instr.get_tec_current()
        print("{:14.3f} {:11.4f} {:11.4f} {:11.4f}".format(timestamp, temp_act, temp_set, tec_current))
        sys.stdout.flush()
        time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(run())
