#! /usr/bin/env python
"""Command line client for the Newport AG-UC8 piezo motor controller."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.newport.ag_uc8 import Newport_AG_UC8, AxisStatus
from qmi.utils.context_managers import start_stop, open_close


CHANNELS = [1, 2, 3, 4]
AXES = [1, 2]


def run() -> int:
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.description = "Command line client for the Newport AG-UC8 piezo motor controller."

    # instrument source
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address", type=str, help="QMI RPC address of device.")
    group.add_argument("--serial", type=str, help="Unique serial number of device.")

    # instrument setter
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", action="store_true",
                       help=Newport_AG_UC8.reset.__doc__)
    group.add_argument("--channel", type=int, choices=CHANNELS,
                       help=Newport_AG_UC8.select_channel.__doc__)
    group.add_argument("--step-delay", type=int, nargs=2, metavar=('AXIS', 'VALUE'),
                       help=Newport_AG_UC8.set_step_delay.__doc__)
    group.add_argument("--step-amplitude", type=int, nargs=3, metavar=('AXIS', 'DIRECTION', 'VALUE'),
                       help=Newport_AG_UC8.__doc__)
    group.add_argument("--clear-steps", type=int, nargs=1, metavar='AXIS', choices=AXES,
                       help=Newport_AG_UC8.clear_step_count.__doc__)
    group.add_argument("--jog", type=int, nargs=3, metavar=('CHANNEL', 'AXIS', 'SPEED'),
                       help=Newport_AG_UC8.jog.__doc__)
    group.add_argument("--move-limit", type=int, nargs=3, metavar=('CHANNEL', 'AXIS', 'SPEED'),
                       help=Newport_AG_UC8.move_limit.__doc__)
    group.add_argument("--move-abs", type=int, nargs=3, metavar=('CHANNEL', 'AXIS', 'POS'),
                       help=Newport_AG_UC8.move_abs.__doc__)
    group.add_argument("--move-rel", type=int, nargs=3, metavar=('CHANNEL', 'AXIS', 'STEPS'),
                       help=Newport_AG_UC8.move_rel.__doc__)
    group.add_argument("--stop", type=int, nargs=1, metavar='AXIS', choices=AXES,
                       help=Newport_AG_UC8.stop.__doc__)

    # instrument getters
    parser.add_argument("-v", "--verbose", type=int, nargs='*', metavar=('CHANNEL', 'AXIS'),
                        help="Display information about piezo motor controller. Constrain information to either a channel or a channel and axis.")


    args = parser.parse_args()

    instr: Newport_AG_UC8
    with start_stop(qmi, "newport_ag_uc8_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:

        # Parse setters
        if args.reset:
            instr.reset()
        elif args.step_delay is not None:
            instr.set_step_delay(*args.step_delay)
        elif args.step_amplitude is not None:
            instr.set_step_amplitude(*args.step_amplitude)
        elif args.clear_steps is not None:
            instr.clear_step_count(*args.clear_steps)
        elif args.jog is not None:
            instr.jog(*args.jog)
        elif args.move_limit is not None:
            instr.move_limit(*args.move_limit)
        elif args.move_abs is not None:
            instr.move_abs(*args.move_abs)
        elif args.move_rel is not None:
            instr.move_rel(*args.move_rel)
        elif args.stop is not None:
            instr.stop(*args.stop)
        elif args.channel is not None:
            instr.select_channel(args.channel)

        # Print getters
        if args.verbose:
            print("IDN:", instr.get_idn())
            channels = CHANNELS if len(args.verbose) < 1 else [args.verbose[0]]
            axes = AXES if len(args.verbose) < 2 else [args.verbose[1]]
            for channel in channels:
                print(f"CHANNEL {channel}:")
                print("  limit status ............................. : {}".format(instr.get_limit_status(channel)))
                for axis in axes:
                    print(f"AXIS {axis}:")
                    print("  status ................................... : {}".format(AxisStatus(instr.get_axis_status(axis)).name))
                    print("  step delay ............................... : {}".format(instr.get_step_delay(axis)))
                    print("  step count ............................... : {}".format(instr.get_step_count(axis)))
                    print("  step amplitude (positive direction) ...... : {}".format(instr.get_step_amplitude(axis, 0)))
                    print("  step amplitude (negative direction) ...... : {}".format(instr.get_step_amplitude(axis, 1)))
            print()

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    if args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="AG_UC8",
                instrument_class=Newport_AG_UC8,
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
