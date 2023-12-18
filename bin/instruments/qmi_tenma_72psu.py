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

        channel = args.channel
        if args.current is not None:
            if args.current == "get":
                print(instr.read_current(channel))

            else:
                print("Setting current to {:.3f} A".format(args.current))
                instr.set_current(args.current, channel)

        if args.accel is not None:
            accel = args.accel
            print("Setting acceleration to {:.3f} degree/second/second".format(accel))

        if (args.velocity is not None) or (args.accel is not None):
            instr.set_velocity_params(velocity, accel)

        if args.absolute is not None:
            print(f"Moving to absolute position {args.absolute:.5f} degrees at {velocity:.3f} degree/second")
            instr.move_absolute(args.absolute)

        if args.relative is not None:
            print(f"Moving by {args.relative:.5f} degrees relative at {velocity:.3f} degree/second")
            instr.move_relative(args.relative)

        if args.home is not None:
            print("Homing at {:.3f} degree/second".format(args.home))
            home_par = instr.get_home_params()
            instr.set_home_params(home_direction=home_par.home_direction,
                                  limit_switch=home_par.limit_switch,
                                  home_velocity=args.home,
                                  offset_distance=home_par.offset_distance)
            instr.move_home()

        if args.stop:
            print("Stopping motion")
            instr.move_stop()

        if args.wait is not None:
            print("Waiting for move to complete ...")
            instr.wait_move_complete(timeout=args.wait)

        pos = instr.get_absolute_position()
        print("Current position: {:.5f} degrees".format(pos))

        status = instr.get_motor_status()
        print("Status: "
              + ("moving, " if (status.moving_forward or status.moving_reverse) else "")
              + ("jogging, " if (status.jogging_forward or status.jogging_reverse) else "")
              + ("homing, " if status.homing else "")
              + ("homed, " if status.homed else "not homed, ")
              + ("motor enabled" if status.channel_enabled else "motor disabled"))

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    instr: globals()[args.model]
    if args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="K10CR1",
                instrument_class=instr,
                transport=f"serial:/dev/serial/by-id/usb-Thorlabs_Kinesis_K10CR1_Rotary_Stage_{args.serial}-if00-port0"
            )
        )

    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(main())
