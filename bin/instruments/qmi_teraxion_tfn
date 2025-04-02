#! /usr/bin/env python
"""Command line client for the TeraXion TFN filter."""
import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.teraxion.tfn import Teraxion_TFN, Teraxion_TFNElement
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the TeraXion TFN filter."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--serial", action="store", type=str, help="Unique serial number of device.")
    group.add_argument("--address", action="store", type=str, help="QMI RPC address of device.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="enable device")
    group.add_argument("--disable", action="store_true", help="disable device")

    parser.add_argument("--frequency", action="store", type=float, help="set frequency setpoint in GHz")

    args = parser.parse_args()

    instr: Teraxion_TFN
    with start_stop(qmi, "teraxion_tfn_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        idn = instr.get_idn()
        print("IDN:", idn)

        if args.disable:
            print("Disabling device")
            instr.disable_device()

        if args.frequency:
            print(f"Setting frequency setpoint to {args.frequency} GHz")
            instr.set_frequency(args.frequency)

        if args.enable:
            print("Enabling device")
            instr.enable_device()

        print()
        print("Instrument state:")
        print(f"    Instrument status:      {instr.get_status()}")
        print(f"    Instrument settings:    {instr.get_nominal_settings()}")
        print(f"    Channel Plan:           {instr.get_channel_plan()}")
        for el in Teraxion_TFNElement:
            print(f"    Temperature {el.name}:      {instr.get_rtd_temperature(el)/100} degrees C")

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
                instrument_name="TFN",
                instrument_class=Teraxion_TFN,
                transport=f"serial:/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_{args.serial}-if00-port0")
        )

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
