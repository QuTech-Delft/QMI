#! /usr/bin/env python
"""Command line client for the Tenma 72-series power supplies."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.tenma import *  # This may look like unused in IDE but will import all PSU classes.
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Tenma 72 series Power Supply Units."

    parser.add_argument("--model", type=str, help="The model number of the Tenma 72 series PSU (e.g. 2550)")
    parser.add_argument("--channel", type=int, help="Channel or memory slot of instrument", const=None)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--udp", type=str, help="IP address of device.")
    group.add_argument("--serial", type=str, help="Serial address of device (COMx, /dev/ttySx).")

    parser.add_argument("--idn", action="store_true", help="Get instrument identification")
    parser.add_argument("--status", action="store_true", help="Get instrument status")
    # setters/getters
    parser.add_argument("--current", type=str, help="Get/Set current in Amperes", nargs='?', const='get',)
    parser.add_argument("--voltage", type=str, help="Get/Set voltage in Volts", nargs='?', const='get',)
    parser.add_argument("--output", action="store_true", help="Enable output", default=None)
    parser.add_argument("--no-output", dest="output", action="store_false", help="Disable output")
    parser.add_argument("--ip", type=str, help="Get/Set IP address", nargs='?', const='get')
    parser.add_argument("--dhcp", type=str, help="Get/Set IP address", nargs='?', const='get')
    parser.add_argument("--port", type=str, help="Get/Set IP port number", nargs='?', const='get')
    parser.add_argument("--mask", type=str, help="Get/Set IP subnet mask", nargs='?', const='get')
    parser.add_argument("--gateway", type=str, help="Get/Set IP gateway", nargs='?', const='get')
    args = parser.parse_args()

    instr: getattr(qmi.instruments.tenma, f"Tenma72_{args.model}")
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
                print("Current is", instr.get_current(channel), "A")

            else:
                current = float(args.current)
                print(f"Setting current to {current:.3f} A")
                instr.set_current(current, channel)

        if args.voltage is not None:
            if args.voltage == "get":
                print("Voltage is", instr.get_voltage(channel), "V")

            else:
                voltage = float(args.voltage)
                print(f"Setting voltage to {voltage:.3f} A")
                instr.set_voltage(voltage, channel)

        if args.output is not None:
            if args.output:
                print("Enabling output.")
            else:
                print("Disabling output.")

            instr.enable_output(args.output)

        if args.dhcp is not None:
            if args.dhcp == "get":
                print("DHCP state is", instr.get_dhcp())

            else:
                print(f"Setting DHCP state to {args.dhcp}")
                instr.set_dhcp(args.dhcp)

        if args.ip is not None:
            if args.ip == "get":
                print("IP address is", instr.get_ip_address())

            else:
                print(f"Setting IP address to {args.ip}")
                instr.set_ip_address(args.ip)

        if args.port is not None:
            if args.port == "get":
                print("IP port number is", instr.get_ip_port())

            else:
                print(f"Setting IP port number to {args.port}")
                instr.set_ip_port(args.port)

        if args.mask is not None:
            if args.mask == "get":
                print("IP subnet mask is", instr.get_subnet_mask())

            else:
                print(f"Setting IP subnet mask to {args.mask}")
                instr.set_subnet_mask(args.mask)

        if args.gateway is not None:
            if args.gateway == "get":
                print("IP gateway is", instr.get_gateway_address())

            else:
                print(f"Setting IP gateway to {args.gateway}")
                instr.set_gateway_address(args.gateway)

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    instr = getattr(qmi.instruments.tenma, f"Tenma72_{args.model}")
    if args.udp is not None:
        port = args.port if args.port != "get" and args.port is not None else 18190  # 18190 is the default in the manual
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
    sys.exit(run())
