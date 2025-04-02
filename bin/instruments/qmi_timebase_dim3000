#! /usr/bin/env python
"""Command line client for the TimeBase DIM3000 AOM driver."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys
import time

import qmi
from qmi.instruments.timebase.dim3000 import TimeBase_DIM3000, DIM3000SweepMode, DIM3000FMDeviation
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the TimeBase DIM3000 AOM driver."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address",  help="QMI RPC address of device.")
    group.add_argument("--serial", help="Unique serial number of device.")

    cmd_group = parser.add_mutually_exclusive_group()
    cmd_group.add_argument("--freq", type=int, help=TimeBase_DIM3000.set_output_frequency.__doc__)
    cmd_group.add_argument("--ampl", type=float, help=TimeBase_DIM3000.set_output_amplitude.__doc__)
    cmd_group.add_argument("--swpm",
                           choices=[mode.value for mode in DIM3000SweepMode],
                           metavar=f"({' | '.join([f'{mode.value}={mode.name}' for mode in DIM3000SweepMode])})",
                           help=TimeBase_DIM3000.set_sweep_mode.__doc__)
    cmd_group.add_argument("--swps", type=int, help=TimeBase_DIM3000.set_sweep_start_frequency.__doc__)
    cmd_group.add_argument("--swpp", type=int, help=TimeBase_DIM3000.set_sweep_stop_frequency.__doc__)
    cmd_group.add_argument("--swpf", type=int, help=TimeBase_DIM3000.set_sweep_step_frequency.__doc__)
    cmd_group.add_argument("--swpt", type=int, help=TimeBase_DIM3000.set_sweep_step_time.__doc__)
    cmd_group.add_argument("--fmon",
                           choices=[0, 1],
                           metavar="(0=OFF | 1=ON)",
                           help=TimeBase_DIM3000.set_fm_input.__doc__)
    cmd_group.add_argument("--fmdev",
                           choices=[mode.value for mode in DIM3000FMDeviation],
                           metavar=f"({' | '.join([f'{mode.value}={mode.name}' for mode in DIM3000FMDeviation])})",
                           help=TimeBase_DIM3000.set_sweep_mode.__doc__)
    cmd_group.add_argument("--plson",
                           choices=[0, 1],
                           metavar="(0=OFF | 1=ON)",
                           help=TimeBase_DIM3000.set_pulse_mode.__doc__)
    cmd_group.add_argument("--plsfr", type=int, help=TimeBase_DIM3000.set_pulse_frequency.__doc__)
    cmd_group.add_argument("--plsdt", type=int, help=TimeBase_DIM3000.set_pulse_duty_cycle.__doc__)
    cmd_group.add_argument("--ffreq", type=int, help=TimeBase_DIM3000.set_fsk_frequency.__doc__)
    cmd_group.add_argument("--fampl", type=float, help=TimeBase_DIM3000.set_fsk_amplitude.__doc__)
    cmd_group.add_argument("--amoffs", type=int, help=TimeBase_DIM3000.set_am_offset.__doc__)

    args = parser.parse_args()

    instr: TimeBase_DIM3000
    with start_stop(qmi, "timebase_dim3000_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        if args.freq is not None:
            instr.set_output_frequency(args.freq)
        elif args.ampl is not None:
            instr.set_output_amplitude(args.ampl)
        elif args.swpm is not None:
            instr.set_sweep_mode(DIM3000SweepMode(args.swpm))
        elif args.swps is not None:
            instr.set_sweep_start_frequency(args.swps)
        elif args.swpp is not None:
            instr.set_sweep_stop_frequency(args.swpp)
        elif args.swpf is not None:
            instr.set_sweep_step_frequency(args.swpf)
        elif args.swpt is not None:
            instr.set_sweep_step_time(args.swpt)
        elif args.fmon is not None:
            instr.set_fm_input(bool(args.fmon))
        elif args.fmdev is not None:
            instr.set_fm_deviation(DIM3000FMDeviation(args.fmdev))
        elif args.plson is not None:
            instr.set_pulse_mode(bool(args.plson))
        elif args.plsfr is not None:
            instr.set_pulse_frequency(args.plsfr)
        elif args.plsdt is not None:
            instr.set_pulse_duty_cycle(args.plsdt)
        elif args.ffreq is not None:
            instr.set_fsk_frequency(args.ffreq)
        elif args.fampl is not None:
            instr.set_fsk_amplitude(args.fampl)
        elif args.amoffs is not None:
            instr.set_am_offset(args.amoffs)
        time.sleep(instr.MINIMUM_EXEC_DELAY_S)

        print(instr.get_device_info())
        time.sleep(instr.MINIMUM_EXEC_DELAY_S)
        print(instr.get_init_data())
        time.sleep(instr.MINIMUM_EXEC_DELAY_S)
        print(instr.get_parameters())
        time.sleep(instr.MINIMUM_EXEC_DELAY_S)

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    if args.serial is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="DIM3000",
                instrument_class=TimeBase_DIM3000,
                transport=f"serial:{args.serial}")
        )

    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
