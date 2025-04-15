#! /usr/bin/env python
"""Command line client for the Bristol FOS Fiber-optic switch."""
import sys
import argparse
from contextlib import nullcontext, AbstractContextManager, ExitStack

import qmi
from qmi.instruments.bristol import Bristol_Fos
from qmi.utils.context_managers import start_stop


def run() -> None:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Bristol FOS Fiber-optic switch."

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rpc", help="QMI RPC address of device.")
    source.add_argument("--unique_id", help="Unique ID of the device")

    parser.add_argument("--board_id", type=int, nargs='?', const=1, help="Board number for the device. Windows only!")
    parser.add_argument("--channel", type=int, help="Channel number to set")

    args = parser.parse_args()

    instr: Bristol_Fos
    with start_stop(qmi, "bristol_fos_client", console_loglevel="WARNING"):
        with ExitStack() as stack:
            instr = stack.enter_context(parse_source(args))
            if args.channel is None:
                if instr.is_open():
                    print(f"Bristol FOS with unique ID {args.unique_id} found. No channel selected.")
                else:
                    print(f"Bristol FOS with unique ID {args.unique_id} not found!")

            else:
                open_at_start = instr.is_open()
                if not open_at_start:
                    instr.open()  # If we get a proxy with 'get_instrument', the proxy could be closed.

                print(f"Selecting channel {args.channel} for Bristol FOS with unique ID {args.unique_id}.")
                instr.select_channel(args.channel)
                if not open_at_start:
                    instr.close()  # Return proxy to closed state.


def parse_source(args) -> AbstractContextManager:
    # make the instrument
    if args.unique_id is not None and args.board_id is not None:
        return qmi.make_instrument(
            instrument_name="FOS",
                instrument_class=Bristol_Fos,
                unique_id=args.unique_id,
                board_id=args.board_id
        )

    elif args.unique_id is not None:
        return qmi.make_instrument(
                instrument_name="FOS",
                instrument_class=Bristol_Fos,
                unique_id=args.unique_id
        )

    # get the instrument
    elif args.rpc is not None:
        host_port = [ctx[1] for ctx in qmi.context().discover_peer_contexts() if ctx[0] == args.rpc.split('.')[0]][0]
        return nullcontext(qmi.get_instrument(args.rpc, auto_connect=True, host_port=host_port))

    raise ValueError("Expected an unique ID or RPC address for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
