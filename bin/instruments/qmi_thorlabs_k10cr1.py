#! /usr/bin/env python
"""Command line client for the Thorlabs K10CR1 rotation mount."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.thorlabs.k10cr1 import Thorlabs_K10CR1
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Thorlabs K10CR1 rotation mount."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address", type=str, help="QMI RPC address of device.")
    group.add_argument("--serial", type=str, help="Unique serial number of device.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--absolute", type=float, metavar="POS", help="Rotate to absolute position in degrees")
    group.add_argument("--relative", type=float, metavar="DIST", help="Rotate by relative displacement in degrees")
    group.add_argument("--home", type=float, metavar="VELOCITY",
                       help="Go to home position at specified velocity (max 5)")
    group.add_argument("--stop", action="store_true", help="Stop current motion")

    parser.add_argument("--velocity", type=float, help="Set velocity in degree/second (max 10)")
    parser.add_argument("--accel", type=float, help="Set acceleration in degree/second/second (max 20)")
    parser.add_argument("--wait", type=float, help="Specify how long to wait for motion to complete.")

    args = parser.parse_args()

    instr: Thorlabs_K10CR1
    with start_stop(qmi, "thorlabs_k10cr1_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        idn = instr.get_idn()
        print("IDN:", idn)

        (velocity, accel) = instr.get_velocity_params()  # get the current values as defaults

        if args.velocity is not None:
            velocity = args.velocity
            print("Setting velocity to {:.3f} degree/second".format(velocity))

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
    if args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="K10CR1",
                instrument_class=Thorlabs_K10CR1,
                transport=f"serial:/dev/serial/by-id/usb-Thorlabs_Kinesis_K10CR1_Rotary_Stage_{args.serial}-if00-port0"
            )
        )

    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
