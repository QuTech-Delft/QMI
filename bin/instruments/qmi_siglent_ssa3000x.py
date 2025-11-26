#! /usr/bin/env python
"""Command line client for the Siglent SSA3000X Spectrum Analyzer."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.siglent.ssa3000x import SSA3000X
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Siglent SSA3000X Spectrum Analyzer."

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rpc", help="QMI RPC address of device.")
    source.add_argument("--ip", help="IP address of the Anapico")

    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print status information about device to stdout.")

    parser.add_argument("--span", type=float, help=SSA3000X.set_freq_span.__doc__)
    parser.add_argument("--center", type=float, help=SSA3000X.set_freq_center.__doc__)

    args = parser.parse_args()

    instr: SSA3000X
    with start_stop(qmi, "siglent_ssa3000x_client", console_loglevel="WARNING"), parse_source(args) as instr:
        if args.span is not None:
            instr.set_freq_span(args.span)
        if args.center is not None:
            instr.set_freq_center(args.center)

        if args.verbose:
            print(f"Device:    {instr.get_id()}")
            print(f"Center:    {to_eng_str(instr.get_freq_center(), 'Hz')}")
            print(f"Span:      {to_eng_str(instr.get_freq_span(), 'Hz')}")
            print(f"Start:     {to_eng_str(instr.get_freq_start(), 'Hz')}")
            print(f"Stop:      {to_eng_str(instr.get_freq_stop(), 'Hz')}")
            print(f"Trace FMT: {instr.get_trace_format()}")


def parse_source(args) -> AbstractContextManager:
    # make the instrument
    if args.ip is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="SSA3000X",
                instrument_class=SSA3000X,
                transport_descr=f"tcp:{args.ip}:5024")
        )

    # get the instrument
    if args.rpc is not None:
        qmi.context().connect_to_peer(args.rpc.split('.')[0])
        return nullcontext(qmi.get_instrument(args.rpc))

    raise ValueError("Expected a source for the instrument!")


def to_eng_str(val: float, unit: str = "") -> str:
    if val >= 1e9:
        return f"{val/1e9}G{unit}"
    elif val >= 1e6:
        return f"{val/1e6}M{unit}"
    elif val >= 1e3:
        return f"{val/1e3}k{unit}"
    else:
        return f"{val}{unit}"


if __name__ == "__main__":
    sys.exit(run())
