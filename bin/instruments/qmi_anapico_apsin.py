#! /usr/bin/env python
"""Command line client for the Anapico APSIN signal source."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys
import time

import qmi
from qmi.instruments.anapico.apsin import Anapico_APSIN
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Anapico APSIN signal source."

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--address", action="store", type=str, help="QMI RPC address of device.")
    source_group.add_argument("--host", action="store", type=str, help="IP address of the Anapico")

    parser.add_argument("--reset", action="store_true",
                        help="reset the instrument to default settings")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="enable RF output signal")
    group.add_argument("--disable", action="store_true", help="disable RF output signal")
    parser.add_argument("--frequency", action="store", type=float, metavar="FREQ",
                        help="set the RF output frequency in Hz")
    parser.add_argument("--phase", action="store", type=float,
                        help="set the RF output phase in radians")
    parser.add_argument("--power", action="store", type=float,
                        help="set the RF output power in dBm")
    parser.add_argument("--pulsemod", action="store", type=str, choices=("off", "norm", "inv"),
                        help="enable or disable external pulse modulation")
    parser.add_argument("--am", action="store", type=float, metavar="SENS",
                        help="set external amplitude modulation sensitivity (0=off)")
    parser.add_argument("--fm", action="store", type=float, metavar="SENS",
                        help="set external frequency modulation sensitivity (0=off)")
    parser.add_argument("--fmcouple", action="store", type=str, choices=("ac", "dc"),
                        help="set external frequency modulation input coupling")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--intref", action="store_true",
                       help="enable internal reference clock")
    group.add_argument("--extref", action="store", type=float, nargs="?",
                       metavar="FREQ", const=0.0,
                       help="enable external reference input with specified frequency")
    parser.add_argument("--refout", action="store", type=int, choices=(0, 1),
                        help="enable or disable reference clock output")

    args = parser.parse_args()

    instr: Anapico_APSIN
    with start_stop(qmi, "apsin_anapico_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        idn = instr.get_idn()
        print("IDN:", idn)

        if args.reset:
            print("Resetting instrument")
            instr.reset()

        if args.disable:
            print("Disabling RF output")
            instr.set_output_enabled(False)

        if args.frequency is not None:
            print("Setting RF frequency")
            instr.set_frequency(args.frequency)

        if args.phase is not None:
            print("Setting RF phase adjustment")
            instr.set_phase(args.phase)

        if args.power is not None:
            print("Setting RF output power")
            instr.set_power(args.power)

        if args.pulsemod:
            t0 = time.time()
            if args.pulsemod.upper() == "OFF":
                print("Disabling pulse modulation")
                instr.set_pulsemod_enabled(False)
            else:
                print("Enabling pulse modulation")
                instr.set_pulsemod_ext_source(True)
                instr.set_pulsemod_polarity(args.pulsemod.upper() == "INV")
                instr.set_pulsemod_enabled(True)
            t1 = time.time()
            print("  duration {:.3f} s".format(t1 - t0))

        if args.am is not None:
            t0 = time.time()
            if args.am == 0:
                print("Disabling amplitude modulation")
                instr.set_am_enabled(False)
            else:
                print("Enabling amplitude modulation")
                instr.set_am_ext_source(True)
                instr.set_am_sensitivity(args.am)
                instr.set_am_enabled(True)
            t1 = time.time()
            print("  duration {:.3f} s".format(t1 - t0))

        if args.fmcouple:
            print("Setting FM input coupling")
            instr.set_fm_coupling(args.fmcouple)

        if args.fm is not None:
            t0 = time.time()
            if args.fm == 0:
                print("Disabling frequency modulation")
                instr.set_fm_enabled(False)
            else:
                print("Enabling frequency modulation")
                instr.set_fm_sensitivity(args.fm)
                instr.set_fm_enabled(True)
            t1 = time.time()
            print("  duration {:.3f} s".format(t1 - t0))

        if args.intref:
            print("Enabling internal reference clock")
            instr.set_reference_source("INT")

        if args.extref is not None:
            print("Enabling external reference clock input")
            if args.extref != 0:
                instr.set_external_reference_frequency(args.extref)
            instr.set_reference_source("EXT")

        if args.refout is not None:
            if args.refout:
                print("Enabling reference clock output")
                instr.set_reference_output_enabled(True)
            else:
                print("Disabling reference clock output")
                instr.set_reference_output_enabled(False)

        if args.enable:
            print("Enabling RF output")
            t0 = time.time()
            instr.set_output_enabled(True)
            t1 = time.time()
            print("  duration {:.3f} s".format(t1 - t0))

        print()
        show_instrument_state(instr)

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # make the instrument
    if args.serial:
        return open_close(
            qmi.make_instrument("APSIN", Anapico_APSIN, f"tcp:{args.host}:18")
        )
    # get the instrument
    elif args.address:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))
    else:
        raise ValueError("Expected a source for the instrument!")


def show_instrument_state(instr: Anapico_APSIN) -> None:
    """Show instrument state."""

    print("Instrument state:")
    print()
    print("  reference source:             {}".format(instr.get_reference_source()))
    ext_ref_freq = instr.get_external_reference_frequency()
    print("  external reference frequency: {:10.6f} MHz".format(1.0e-6 * ext_ref_freq))
    ref_locked = instr.get_reference_is_locked()
    print("  reference locked:             {}".format("yes" if ref_locked else "no"))
    ref_out_en = instr.get_reference_output_enabled()
    print("  reference output enabled:     {}".format("enabled" if ref_out_en else "disabled"))
    print()
    print("  RF output enabled:            {}".format("enabled" if instr.get_output_enabled() else "disabled"))
    print("  RF frequency:               {:15.9f} MHz".format(1.0e-6 * instr.get_frequency()))
    print("  RF phase adjustment:        {:9.3f} rad".format(instr.get_phase()))
    print("  RF output power:            {:+9.3f} dBm".format(instr.get_power()))
    print()
    print("  pulse modulation:             {} source={} polarity={}".format(
        ("enabled" if instr.get_pulsemod_enabled() else "disabled"),
        ("external" if instr.get_pulsemod_ext_source() else "internal"),
        ("inverted" if instr.get_pulsemod_polarity() else "normal")))
    print("  amplitude modulation:         {} source={} sensitivity={:.3f} /V".format(
        ("enabled" if instr.get_am_enabled() else "disabled"),
        ("external" if instr.get_am_ext_source() else "internal"),
        instr.get_am_sensitivity()))
    print("  frequency modulation:         {} source={} sensitivity={:.3f} Hz/V".format(
        ("enabled" if instr.get_fm_enabled() else "disabled"),
        ("external" if instr.get_fm_ext_source() else "internal"),
        instr.get_fm_sensitivity()))
    print("                                coupling={}".format(instr.get_fm_coupling()))
    print()


if __name__ == "__main__":
    sys.exit(run())
