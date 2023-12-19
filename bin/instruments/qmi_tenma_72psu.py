#! /usr/bin/env python3

"""Command line client for the Tenma 72-series power supplies."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.tenma import *  # This may look like unused in IDE but will import all PSU classes.
from qmi.utils.context_managers import start_stop, open_close


def main() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Tenma 72 series Power Supply Units."

    parser.add_argument("--model", type=str, help="The model number of the Tenma 72 series PSU (e.g. 2550)")
    parser.add_argument("--channel", type=int, help="Channel or memory slot of instrument", const=None)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--udp", type=str, help="IP address of device.")
    group.add_argument("--serial", type=str, help="Serial address of device (COMx, /dev/ttySx).")

    parser.add_argument("--port", type=int, help="Port number for the UDP connection")
    parser.add_argument("--idn", action="store_true", help="Get instrument identification")
    parser.add_argument("--status", action="store_true", help="Get instrument status")
    # setters/getters
    parser.add_argument("--current", type=str, help="Set current in Amperes", nargs='?', const='get',)
    parser.add_argument("--voltage", type=str, help="Set voltage in Volts", nargs='?', const='get',)
    parser.add_argument("--output", action="store_true", help="Enable output", default=None)
    parser.add_argument("--no-output", dest="output", action="store_false", help="Disable output")
    args = parser.parse_args()

    instr: globals()[f"Tenma72_{args.model}"]
    with start_stop(qmi, "tenma72_psu_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        if args.idn:
            idn = instr.get_idn()
            print("IDN:", idn)

        if args.status:
            print("Status of the instrument is:")
            print(instr.get_status())

        channel = args.channel
        if args.current is not None:
            if args.current == "get":
                print("Current is", instr.read_current(channel), "A")

            else:
                current = float(args.current)
                print("Setting current to {:.3f} A".format(current))
                instr.set_current(current, channel)

        if args.voltage is not None:
            if args.voltage == "get":
                print("Voltage is", instr.read_voltage(channel), "V")

            else:
                voltage = float(args.voltage)
                print("Setting voltage to {:.3f} A".format(voltage))
                instr.set_voltage(voltage, channel)

        if args.output is not None:
            if args.output:
                print("Enabling output.")
            else:
                print("Disabling output.")

            instr.enable_output(args.output)

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    instr = globals()[f"Tenma72_{args.model}"]
    if args.udp is not None:
        port = args.port or 0
        return open_close(
            qmi.make_instrument(
                instrument_name=f"tenma72_{args.model}",
                instrument_class=instr,
                transport=f"udp:{args.udp}:{port}"
            )
        )
    elif args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name=f"tenma72_{args.model}",
                instrument_class=instr,
                transport=f"serial:{args.serial}"
            )
        )

    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(main())
