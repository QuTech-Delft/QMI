#! /usr/bin/env python
"""Command line client for the Wieserlabs FlexDDS-NG-Dual signal source."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.instruments.wieserlabs.flexdds import Wieserlabs_FlexDDS_NG_Dual, OutputChannel
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Wieserlabs FlexDDS-NG-Dual signal source."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address",  help="QMI RPC address of device.")
    group.add_argument("--serial", help="Unique serial number of device.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tone", action="store_true", help="configure a single tone")
    group.add_argument("--am", action="store_true", help="configure amplitude modulation")
    group.add_argument("--fm", action="store_true", help="configure frequency modulation")
    group.add_argument("--pm", action="store_true", help="configure pulse modulation (on/off)")

    parser.add_argument("--channel", choices=("0", "1", "both"), help="output port to configure")
    parser.add_argument("--frequency", type=float, metavar="FREQ", help="tone frequency in Hz")
    parser.add_argument("--amplitude", type=float, default=1.0, metavar="AMPL",
                        help="amplitude scale factor (range 0.0 .. 1.0)")
    parser.add_argument("--phase", type=float, default=0.0,
                        help="phase offset as fraction of the full sine wave period")
    parser.add_argument("--mod_input", type=int, choices=(0, 1), help="analog input channel for modulation")
    parser.add_argument("--mod_offset", type=float, default=0.0, metavar="OFFS",
                        help="offset for analog input signal (Volt)")
    parser.add_argument("--mod_scale", type=float, metavar="SCALE", help="modulation scale factor")
    parser.add_argument("--pulse_input", type=int, choices=(0, 1, 2),
                        help="digital input channel for pulse modulation")

    args = parser.parse_args()

    if args.channel == "0":
        channel = OutputChannel.OUT0
    elif args.channel == "1":
        channel = OutputChannel.OUT1
    else:
        channel = OutputChannel.BOTH

    if args.tone or args.am or args.fm or args.pm:
        if args.channel is None:
            print("ERROR: Missing parameter --channel", file=sys.stderr)
            return 1
        if args.frequency is None:
            print("ERROR: Missing parameter --frequency", file=sys.stderr)
            return 1

    if args.am or args.fm:
        if args.mod_input is None:
            print("ERROR: Missing parameter --mod_input", file=sys.stderr)
            return 1
        if args.mod_scale is None:
            print("ERROR: Missing parameter --mod_scale", file=sys.stderr)
            return 1

    if args.pm:
        if args.pulse_input is None:
            print("ERROR: Missing parameter --pulse_input", file=sys.stderr)
            return 1

    instr: Wieserlabs_FlexDDS_NG_Dual
    with start_stop(qmi, "wieserlabs_flexdds_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
        instr_version = instr.get_version()
        print("Version:", repr(instr_version))
        print()

        pll_status = instr.get_pll_status()
        print("PLL status:")
        print("  PLL1={}, PLL2={}".format(("locked" if pll_status.pll1_lock else "UNLOCKED"),
                                          ("locked" if pll_status.pll2_lock else "UNLOCKED")))
        print("  holdover={}".format("ACTIVE" if pll_status.holdover else "inactive"))
        print("  CLKIN0={}, CLKIN1={}".format(("LOST" if pll_status.clkin0_lost else "not_lost"),
                                              ("LOST" if pll_status.clkin1_lost else "not_lost")))
        print()

        instr.dds_reset(channel=channel)
        if args.tone:
            print("Configuring", channel, "for single tone")
            instr.set_single_tone(channel=channel,
                                  frequency=args.frequency,
                                  amplitude=args.amplitude,
                                  phase=args.phase)
        if args.am:
            print("Configuring", channel, "for amplitude modulation")
            instr.set_amplitude_modulation(channel=channel,
                                           frequency=args.frequency,
                                           base_ampl=args.amplitude,
                                           phase=args.phase,
                                           mod_input=args.mod_input,
                                           mod_offset=args.mod_offset,
                                           mod_scale=args.mod_scale)
        elif args.fm:
            print("Configuring", channel, "for frequency modulation")
            instr.set_frequency_modulation(channel=channel,
                                           base_freq=args.frequency,
                                           amplitude=args.amplitude,
                                           phase=args.phase,
                                           mod_input=args.mod_input,
                                           mod_offset=args.mod_offset,
                                           mod_scale=args.mod_scale)
        if args.pm:
            print("Configuring", channel, "for pulse modulation")
            instr.set_digital_modulation(channel=channel,
                                         frequency=args.frequency,
                                         amplitude=args.amplitude,
                                         phase=args.phase,
                                         mod_input=args.pulse_input,
                                         mod_invert=False)

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
                instrument_name="FlexDDS",
                instrument_class=Wieserlabs_FlexDDS_NG_Dual,
                transport=f"serial:[/dev/serial/by-id/usb-Wieserlabs_UG_FlexDDS-NG_Console_{args.serial}-if00]"
            )
        )

    raise ValueError("Expected a source for the instrument!")


if __name__ == "__main__":
    sys.exit(run())
