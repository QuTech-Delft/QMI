#! /usr/bin/env python3

"""Command line client for the Thorlabs K10CR1 rotation mount."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.tenma import *
from qmi.utils.context_managers import start_stop, open_close


def main() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Tenma 72 series Power Supply Units."

    parser.add_argument("--model", type=str, help="The model number of the Tenma 72 series PSU (e.g. 2550)")
    parser.add_argument("--channel", type=int, help="Channel or memory slot of instrument", const=None)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tcp", type=str, help="IP address of device.")
    group.add_argument("--serial", type=str, help="Serial address of device (COMx, /dev/ttySx).")

    parser.add_argument("--idn", action="store_true", help="Get instrument identification")
    parser.add_argument("--status", action="store_true", help="Get instrument status")
    # setters/getters
    parser.add_argument("--current", type=float, help="Set current in Amperes", nargs='?', const='get',)
    parser.add_argument("--voltage", type=float, help="Set voltage in Volts", nargs='?', const='get',)
    parser.add_argument("--output", type=bool, help="Enable/disable output")
    parser.add_argument("--no-output", dest="output", action="store_false")
    args = parser.parse_args()

    instr: globals()[args.model]
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
                print(instr.read_current(channel))

            else:
                print("Setting current to {:.3f} A".format(args.current))
                instr.set_current(args.current, channel)

        if args.voltage is not None:
            if args.voltage == "get":
                print(instr.read_voltage(channel))

            else:
                print("Setting voltage to {:.3f} A".format(args.voltage))
                instr.set_voltage(args.voltage, channel)

        if args.output is not None:
            if args.output:
                print("Enabling output.")
            else:
                print("Disabling output.")

            instr.enable_output(args.output)

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    instr: globals()[args.model]
    if args.tcp is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name=f"Tenma 72-{args.model}",
                instrument_class=instr,
                transport=f"tcp:{args.tcp}"
            )
        )
    elif args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name=f"Tenma 72-{args.model}",
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
