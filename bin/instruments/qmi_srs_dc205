#! /usr/bin/env python
"""Command line client for the Stanford Research Systems DC205 voltage source."""
import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.stanford_research_systems.dc205 import SRS_DC205
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Stanford Research Systems DC205 voltage source."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--serial", action="store", type=str, help="Unique serial number of device.")
    group.add_argument("--address", action="store", type=str, help="QMI RPC address of device.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="enable output signal")
    group.add_argument("--disable", action="store_true", help="disable output signal")

    parser.add_argument("--voltage", action="store", type=float, help="set output voltage")
    parser.add_argument("--range", action="store", type=int, choices=(1, 10, 100), help="set output range")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ground", action="store_true", help="enable ground-referenced output mode")
    group.add_argument("--floating", action="store_true", help="enable floating output mode (isolated from ground)")

    parser.add_argument("--sense", action="store", type=str, choices=("2wire", "4wire"), help="set sense mode")

    args = parser.parse_args()

    instr: SRS_DC205
    with start_stop(qmi, "srs_dc205_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        idn = instr.get_idn()
        print("IDN:", idn)

        if args.disable:
            print("Disabling output")
            instr.set_output_enabled(False)

        if args.range is not None:
            print("Setting output range to +/- {} V".format(args.range))
            instr.set_range(args.range)

        if args.ground:
            print("Setting output to ground-referenced mode")
            instr.set_output_floating(False)

        if args.floating:
            print("Setting output to floating mode")
            instr.set_output_floating(True)

        if args.sense is not None:
            print("Setting sensing to {} mode".format(args.sense))
            instr.set_sensing_enabled(args.sense == "4wire")

        if args.voltage:
            print("Setting output voltage to {} V".format(args.voltage))
            instr.set_voltage(args.voltage)

        if args.enable:
            print("Enabling output")
            instr.set_output_enabled(True)

        print()
        print("Instrument state:")
        print("  output {}".format("ENABLED" if instr.get_output_enabled() else "disabled"))
        print("  output range: {} V".format(instr.get_range()))
        print("  output voltage: {} V".format(instr.get_voltage()))
        print("  output isolation: {}".format("floating" if instr.get_output_floating() else "ground"))
        print("  sensing mode: {}".format("4-wire" if instr.get_sensing_enabled() else "2-wire"))
        print("  overload detection: {}".format("OVERLOAD" if instr.get_overloaded() else "not overloaded"))
        print("  interlock status: {}".format("closed" if instr.get_interlock_status() else "LOCKED"))

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    # make the instrument
    if args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="DC205",
                instrument_class=SRS_DC205,
                transport=f"serial:/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_{args.serial}-if00-port0")
        )

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
