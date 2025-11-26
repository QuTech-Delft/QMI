#! /usr/bin/env python
"""Command line client for the Quantum Composers 9530 pulse generator."""

import argparse
from contextlib import nullcontext, AbstractContextManager
import sys

import qmi
from qmi.core.exceptions import QMI_ApplicationException
from qmi.instruments.quantum_composers.pulse_generator9530 import (
    RefClkSource, PulseMode, TriggerMode, TriggerEdge, OutputDriver,
    QuantumComposers_PulseGenerator9530)
from qmi.utils.context_managers import start_stop, open_close


def run() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Quantum Composers 9530 pulse generator."

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address", action="store", type=str, help="QMI RPC address of device.")
    group.add_argument("--host", action="store", type=str, help="IP address (when connecting via Ethernet)")
    group.add_argument("--serial", action="store", type=str, help="serial port device (when connecting via USB)")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--intref", action="store_true", help="select internal reference clock")
    group.add_argument("--extref", action="store_true", help="select external reference clock input")

    parser.add_argument("--reffreq", action="store", type=int, help="external reference frequency in MHz")
    parser.add_argument("--reflevel", action="store", type=float, help="threshold level of external reference in Volt")
    parser.add_argument("--period", action="store", type=float, help="set pulse period in seconds")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--trigoff", action="store_true", help="disable external trigger")
    group.add_argument("--trigrise", action="store", type=float, metavar="LEVEL", help="trigger on rising edge")
    group.add_argument("--trigfall", action="store", type=float, metavar="LEVEL", help="trigger on falling edge")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--display", action="store_true", help="enable display and buttons")
    group.add_argument("--no-display", action="store_true", help="disable display and buttons")

    parser.add_argument("--channel", action="store", type=int, help="select channel to configure (default T0)")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="enable pulse generation")
    group.add_argument("--disable", action="store_true", help="disable pulse generation")

    parser.add_argument("--delay", action="store", type=float, help="channel delay in seconds")
    parser.add_argument("--width", action="store", type=float, help="pulse width in seconds")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cont", action="store_true", help="select continuous mode")
    group.add_argument("--burst", action="store", type=int, help="select burst mode")
    group.add_argument("--dutycycle", action="store", type=duty_cycle,
                       metavar="NPULSE,NSKIP", help="select duty-cycle mode")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ttl", action="store_true", help="set output to TTL mode")
    group.add_argument("--ampl", action="store", type=float, help="set output amplitude in Volt")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--invert", action="store_true", help="set output active low")
    group.add_argument("--no-invert", action="store_true", help="set output active high")

    args = parser.parse_args()

    try:
        with start_stop(qmi, "quantum_composer_9530_client", console_loglevel="WARNING"), parse_instrument_source(args) as instr:
            idn = instr.get_idn()
            print("IDN:", idn)

            # Validate channel index.
            num_channels = instr.get_num_channels()
            if args.channel is not None:
                if args.channel < 1 or args.channel > num_channels:
                    raise QMI_ApplicationException("Invalid channel index")

            # Some parameters only apply to output channels (not to T0).
            if ((args.delay is not None)
                    or (args.width is not None)
                    or args.ttl
                    or (args.ampl is not None)
                    or args.invert
                    or args.no_invert):
                if args.channel is None:
                    raise QMI_ApplicationException("Missing --channel parameter")

            # Reconfigure instrument as requested.
            if args.intref:
                print("Selecting internal reference clock")
                instr.set_refclk_source(RefClkSource.INTERNAL)
            if args.reffreq is not None:
                print("Setting reference clock frequency")
                instr.set_refclk_rate(args.reffreq)
            if args.reflevel is not None:
                print("Setting reference clock level")
                instr.set_refclk_level(args.reflevel)
            if args.extref:
                print("Selecting external reference clock")
                instr.set_refclk_source(RefClkSource.EXTPLL)
            if args.period is not None:
                print("Setting pulse period")
                instr.set_t0_period(args.period)
            if args.trigoff:
                print("Disabling external trigger")
                instr.set_trigger_mode(TriggerMode.DISABLED)
            if args.trigrise:
                print("Setting trigger on rising edge")
                instr.set_trigger_edge(TriggerEdge.RISING)
                instr.set_trigger_level(args.trigrise)
                instr.set_trigger_mode(TriggerMode.ENABLED)
            if args.trigfall:
                print("Setting trigger on falling edge")
                instr.set_trigger_edge(TriggerEdge.FALLING)
                instr.set_trigger_level(args.trigfall)
                instr.set_trigger_mode(TriggerMode.ENABLED)

            if args.channel is None:
                if args.enable:
                    print("Enabling pulse generation")
                    instr.set_output_enabled(True)
                if args.disable:
                    print("Disabling pulse generation")
                    instr.set_output_enabled(False)
                if args.cont:
                    print("Selecting continuous pulse mode")
                    instr.set_t0_mode(PulseMode.NORMAL)
                if args.burst is not None:
                    print("Selecting burst mode")
                    instr.set_t0_burst_count(args.burst)
                    instr.set_t0_mode(PulseMode.BURST)
                if args.dutycycle is not None:
                    print("Selecting duty-cycle mode")
                    instr.set_t0_duty_cycle(*args.dutycycle)
                    instr.set_t0_mode(PulseMode.DUTYCYCLE)
            else:
                if args.enable:
                    print("Enabling channel", args.channel)
                    instr.set_channel_enabled(args.channel, True)
                if args.disable:
                    print("Disabling channel", args.channel)
                    instr.set_channel_enabled(args.channel, False)
                if args.delay is not None:
                    print("Setting delay for channel", args.channel)
                    instr.set_channel_delay(args.channel, args.delay)
                if args.width is not None:
                    print("Setting pulse width for channel", args.channel)
                    instr.set_channel_width(args.channel, args.width)
                if args.cont:
                    print("Selecting continuous pulse mode for channel", args.channel)
                    instr.set_channel_mode(args.channel, PulseMode.NORMAL)
                if args.burst is not None:
                    print("Selecting burst mode for channel", args.channel)
                    instr.set_channel_burst_count(args.channel, args.burst)
                    instr.set_channel_mode(args.channel, PulseMode.BURST)
                if args.dutycycle is not None:
                    print("Selecting duty-cycle mode for channel", args.channel)
                    instr.set_channel_duty_cycle(args.channel, *args.dutycycle)
                    instr.set_channel_mode(args.channel, PulseMode.DUTYCYCLE)
                if args.ttl:
                    print("Selecting TTL output for channel", args.channel)
                    instr.set_output_driver(args.channel, OutputDriver.TTL)
                if args.ampl is not None:
                    print("Setting adjustable output level for channel", args.channel)
                    instr.set_output_amplitude(args.channel, args.ampl)
                    instr.set_output_driver(args.channel, OutputDriver.ADJUSTABLE)
                if args.invert:
                    print("Setting active low (inverted) output for channel", args.channel)
                    instr.set_output_inverted(args.channel, True)
                if args.no_invert:
                    print("Setting active high output for channel", args.channel)
                    instr.set_output_inverted(args.channel, False)

            if args.display:
                print("Enabling display")
                instr.set_display_enabled(True)
            if args.no_display:
                print("Disabling display")
                instr.set_display_enabled(False)

            print()
            show_info(instr)

    except QMI_ApplicationException as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

    return 0


def parse_instrument_source(args) -> AbstractContextManager:
    # get the instrument
    if args.address is not None:
        qmi.context().connect_to_peer(args.address.split('.')[0])
        return nullcontext(qmi.get_instrument(args.address))

    # make the instrument
    if args.serial is not None or args.host is not None:
        return open_close(
            qmi.make_instrument(
                instrument_name="9530",
                instrument_class=QuantumComposers_PulseGenerator9530,
                transport=(
                    # IPv6 address needs to be in square brackets
                    f"tcp:{f'[{args.host}]' if ':' in args.host else args.host}" if args.host is not None else
                    f"serial:/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_{args.serial}-if00-port0")))

    raise ValueError("Expected a source for the instrument!")


def show_info(instr):
    """Show current configuration of the instrument."""

    print("---- Instrument state ----")
    print()

    num_channels = instr.get_num_channels()
    print("Num channels:   ", num_channels)

    refclk = instr.get_refclk_source()
    refclk_str = refclk.name
    if refclk == RefClkSource.EXTPLL:
        if instr.is_refclk_pll_locked():
            refclk_str += ", locked"
        else:
            refclk_str += ", UNLOCKED"
    print("Reference clock:", refclk_str)
    if refclk != RefClkSource.INTERNAL:
        print("    Frequency:  ", instr.get_refclk_rate(), "MHz")
        print("    Threshold:  ", instr.get_refclk_level(), "V")

    print("Global enable:  ", "ENABLED" if instr.get_output_enabled() else "disabled")
    print("Pulse period:    {:.9f} s".format(instr.get_t0_period()))

    mode = instr.get_t0_mode()
    if mode == PulseMode.NORMAL:
        mode_str = "Continuous"
    elif mode == PulseMode.SINGLE:
        mode_str = "Single"
    elif mode == PulseMode.BURST:
        mode_str = "Burst(n={})".format(instr.get_t0_burst_count())
    else:
        mode_str = "DutyCycle(npulse={}, nskip={})".format(*instr.get_t0_duty_cycle())
    print("Pulse mode:     ", mode_str)

    trigger_mode = instr.get_trigger_mode()
    if trigger_mode == TriggerMode.DISABLED:
        trig_str = "Disabled"
    else:
        trig_str = trigger_mode.name
        trig_str += ", " + instr.get_trigger_edge().name
        trig_str += ", {:.2f} V".format(instr.get_trigger_level())
    print("Trigger mode:   ", trig_str)

    print()
    print("Ch#  Out Delay         PulseWidth    Mode           Level    Invert")
    for ch in range(1, num_channels + 1):
        enabled_str = "ENA" if instr.get_channel_enabled(ch) else "dis"
        delay_str = "D={:.9f}".format(instr.get_channel_delay(ch))
        width_str = "W={:.9f}".format(instr.get_channel_width(ch))
        mode = instr.get_channel_mode(ch)
        if mode == PulseMode.NORMAL:
            mode_str = "Continuous    "
        elif mode == PulseMode.SINGLE:
            mode_str = "Single        "
        elif mode == PulseMode.BURST:
            mode_str = "Burst({:4d})   ".format(instr.get_channel_burst_count(ch))
        else:
            mode_str = "Cyc({:4d},{:4d})".format(*instr.get_channel_duty_cycle(ch))
        driver = instr.get_output_driver(ch)
        if driver == OutputDriver.TTL:
            driver_str = "L=TTL   "
        else:
            driver_str = "L={:5.2f}V".format(instr.get_output_amplitude(ch))
        polarity_str = "Invert" if instr.get_output_inverted(ch) else "Normal"
        print("Ch{}:".format(ch),
              enabled_str, delay_str, width_str, mode_str, driver_str, polarity_str)


def duty_cycle(s):
    w = s.split(",")
    if len(w) != 2:
        raise argparse.ArgumentTypeError("Expecting 'NPULSE,NSKIP'")
    return (int(w[0]), int(w[1]))


if __name__ == "__main__":
    sys.exit(run())
