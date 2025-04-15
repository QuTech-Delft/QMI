#! /usr/bin/env python
"""Command line client for the HighFinesse WaveLength Meter (wlm).

Example uses:

  - Run a standalone (local) measurement to print version and identification info and get 5 wavelength values:
  `python.exe .\\qmi\\bin\\instruments\\qmi_highfinesse_ws --version --idn --wavelength --log 5`

  - Run a separate server and client in different shells/machines:
    - `python.exe .\\qmi\\bin\\instruments\\qmi_highfinesse_ws --server --config="C:\\Users\\john\\qmi.conf"`
    - `python.exe .\\qmi\\bin\\instruments\\qmi_highfinesse_ws --client --version --idn --wavelength --log 5
    --config="C:\\Users\\john\\qmi.conf"`
"""

import argparse
import sys
import time
from contextlib import AbstractContextManager
from collections.abc import Callable

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.instruments.high_finesse.wlm import HighFinesse_Wlm
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the High Finesse Wavelength Meter."

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--server", dest="server", default=False, action="store_true",
                       help="Start the server.")
    group.add_argument("--client", dest="client", default=False, action="store_true",
                       help="Start the client.")

    parser.add_argument("--config", help="QMI config file.")

    parser.add_argument("--wavelength", dest="wavelength", default=False, action="store_true",
                        help="measure wavelength")
    parser.add_argument("--frequency", dest="frequency", default=False, action="store_true", help="measure frequency")
    parser.add_argument("--version", dest="version", default=False, action="store_true", help="print library version")
    parser.add_argument("--idn", dest="idn", default=False, action="store_true", help="print device IDN")
    parser.add_argument("--log", type=int, metavar="N", default=1, help="log values during N intervals of 0.05 s")

    args = parser.parse_args()

    if args.server:
        _do_server(args)
    elif args.client:
        _do_client(args)
    else:
        _do_standalone(args)

    return 0


def _do_server(args: argparse.Namespace):
    instr: HighFinesse_Wlm
    with (start_stop(qmi, "highfinesse_wlm", console_loglevel="WARNING", config_file=args.config),
          _parse_instrument_source() as instr):
        started_server = instr.start_server()

        try:
            while not qmi.context().shutdown_requested():
                print("server: sleeping...")
                time.sleep(10)
        except KeyboardInterrupt:
            print("server: shutdown")
            if started_server:
                instr.stop_server()


def _do_client(args: argparse.Namespace):
    instr: HighFinesse_Wlm
    with start_stop(qmi, "highfinesse_client", config_file=args.config):
        qmi.context().connect_to_peer("highfinesse_wlm")
        instr = qmi.get_instrument("highfinesse_wlm.wlm")

        _perform_actions(instr, args)


def _do_standalone(args: argparse.Namespace):
    instr: HighFinesse_Wlm
    with (start_stop(qmi, "highfinesse_wlm", console_loglevel="INFO"),
          _parse_instrument_source() as instr):
        started_server = instr.start_server()

        _perform_actions(instr, args)

        if started_server:
            instr.stop_server()
    return 0


def _perform_actions(instr, args: argparse.Namespace):
    if args.version:
        _show_instrument_version(instr)
    if args.idn:
        _show_instrument_idn(instr)

    funcs = []
    if args.frequency:
        funcs.append(instr.get_frequency)
    if args.wavelength:
        funcs.append(instr.get_wavelength)
    if len(funcs) > 0:
        _log_values(args.log, funcs)


def _parse_instrument_source() -> AbstractContextManager:
    instr = open_close(qmi.make_instrument(
        instrument_name="wlm",
        instrument_class=HighFinesse_Wlm)
    )
    return instr


def _show_instrument_version(instr: HighFinesse_Wlm):
    version = instr.get_version()
    print(version)


def _show_instrument_idn(instr: HighFinesse_Wlm):
    idn = instr.get_idn()
    print(idn)


def _log_values(n: int, func_list: list[Callable], channel=1):
    """Log n measurement values by calling functions in func_list."""

    print("#time          " + " ".join([f"{f.__name__:>15s}" for f in func_list]))

    time.sleep(0.1)  # Otherwise the device might start with a WS8_ERR.NO_VALUE response

    for _ in range(n):
        timestamp = time.time()
        try:
            values = [f(channel) for f in func_list]
            print(f"{timestamp:14.3f} " + " ".join([f"{v:15.4f}" for v in values]))
        except QMI_InstrumentException as exc:
            print(f"{timestamp:14.3f} {exc}")
        sys.stdout.flush()
        time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(run())
