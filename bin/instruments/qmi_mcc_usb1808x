#! /usr/bin/env python
"""Command line client for the Measurement Computing USB-1808X DAQ device."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.mcc.usb1808x import MCC_USB1808X
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = """Command line client for the Measurement Computing USB-1808X DAQ device."""

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="show a list of attached instruments")
    group.add_argument("--serial", action="store", type=str, help="Unique serial number of device.")
    group.add_argument("--address", action="store", type=str, help="QMI RPC address of device.")

    subp = parser.add_subparsers(dest="command")

    sub_di = subp.add_parser("di", help="read digital input")
    sub_di.add_argument("channel", action="store", type=int, help="channel index (0 .. 3)")

    sub_do = subp.add_parser("do", help="set digital output")
    sub_do.add_argument("channel", action="store", type=int, help="channel index (0 .. 3)")
    sub_do.add_argument("value", action="store", type=int, help="digital output value (0 .. 1)")

    sub_ai = subp.add_parser("ai", help="read analog input")
    sub_ai.add_argument("channel", action="store", type=int, help="channel index (0 .. 8)")
    sub_ai.add_argument("mode", action="store", type=str, help="choose SINGLE_ENDED or DIFFERENTIAL")
    sub_ai.add_argument("range", action="store", type=str)

    sub_ao = subp.add_parser("ao", help="set analog output voltage")
    sub_ao.add_argument("channel", action="store", type=int, help="channel index (0 .. 1)")
    sub_ao.add_argument("value", action="store", type=float, help="analog output level in Volt (-10.0 .. +10.0)")

    args = parser.parse_args()

    if args.list:
        print("Detecting USB-1808X devices:")
        instruments = MCC_USB1808X.list_instruments()
        for unique_id in instruments:
            print("  found", unique_id)
        return 0

    instr: MCC_USB1808X
    with start_stop(qmi, "mcc_usb1808x_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        idn = instr.get_idn()
        print("IDN:", idn)

        print("Number of digital channels:", instr.get_dio_num_channels())
        print("Number of analog inputs:   ", instr.get_ai_num_channels())
        print("Number of analog outputs:  ", instr.get_ao_num_channels())
        print("Digital channel directions:",
              " ".join(["{}:{}".format(ch, "OUT" if v else "IN") for (ch, v) in enumerate(instr.get_dio_direction())]))
        print("Analog input ranges:       ", instr.get_ai_ranges())
        print("Analog output ranges:      ", instr.get_ao_ranges())
        print()

        if args.command == "di":
            instr.set_dio_direction(args.channel, False)
            v = instr.get_dio_input_bit(args.channel)
            print("DIO input {} = {}".format(args.channel, int(v)))
            print()

        if args.command == "do":
            v = (args.value != 0)
            print("Setting DIO output {} = {}".format(args.channel, int(v)))
            instr.set_dio_direction(args.channel, True)
            instr.set_dio_output_bit(args.channel, (args.value != 0))
            print()

        if args.command == "ai":
            v = instr.get_ai_value(args.channel, args.mode.upper(), args.range.upper())
            print("Analog input {} = {}".format(args.channel, v))
            print()

        if args.command == "ao":
            print("Setting analog output {} = {}".format(args.channel, args.value))
            instr.set_ao_value(args.channel, "BIP10VOLTS", args.value)
            print()

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    # make the instrument
    if args.serial is not None:
        return open_close(
            qmi.make_instrument("DAQ", MCC_USB1808X, args.serial)
        )

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
