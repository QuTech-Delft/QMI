#! /usr/bin/env python

import argparse
import sys

import qmi
from qmi.core.exceptions import QMI_ApplicationException, QMI_UsageException
from qmi.utils.context_managers import start_stop
from qmi.instruments.nenion import Nenion_ValveController


def main() -> int:

    parser = argparse.ArgumentParser()
    parser.description = "Command line client for the Tenma 72 series Power Supply Units."

    address = parser.add_mutually_exclusive_group(required=True)
    address.add_argument("--tcp", type=str, help="IP address of device.")
    address.add_argument("--serial", type=str, help="(USB-to-)Serial address of device (COMx, /dev/ttySx).")

    conn_param = parser.add_mutually_exclusive_group(required=False)
    conn_param.add_argument("--port", type=str, help="IP address port number.", default=1512)
    conn_param.add_argument("--baud", type=str, help="Baud rate of the device connection.", default=115200)

    parser.add_argument("--status", action="store_true", help="Get instrument status")
    # setters/getters
    motor_current = parser.add_mutually_exclusive_group(required=False)
    motor_current.add_argument("--enable", action="store_true", help="Enable motor current")
    motor_current.add_argument("--disable", action="store_true", help="Disable motor current")

    parser.add_argument("--halt", action="store_true", help="Halt movement immediately")
    parser.add_argument("--fully_close", action="store_true", help="'Null' valve by closing it fully.")
    parser.add_argument("-t", "--target", type=int, help="Set valve open percentage target", nargs=1)
    steps = parser.add_mutually_exclusive_group(required=False)
    steps.add_argument("-p", "--step_open", type=int, help="Step towards open", nargs='?', const=1)
    steps.add_argument("-m", "--step_close", type=int, help="Step towards close", nargs='?', const=1)
    args = parser.parse_args()
    print(args.tcp, args.port)
    print(args.serial, args.baud)
    print(args.enable, args.disable)
    print(args.halt)
    print(args.fully_close)
    print(args.target)
    print(args.step_open)
    print(args.step_close)

    with start_stop(qmi, "nenion_valve_controller_client", console_loglevel="WARNING"):
        if args.tcp:
            transport = f"tcp:{args.tcp}:{args.port}"

        elif args.serial:
            transport = f"serial:{args.serial}"
            if args.baud != 115200:
                transport += f":baudrate={args.baud}:parity=E"

        with Nenion_ValveController(qmi.context(), "Nenion_Valve_Controller", transport) as instr:
            if args.status:
                status = instr.get_status()
                print(status.value, status.position)

            if args.halt:
                print("Halting motor.")
                instr.halt_motor()
                if args.disable:
                    instr.disable_motor_current()

            if args.halt and any([args.enable, args.fully_close, args.target, args.step_open, args.step_close]):
                raise QMI_UsageException("Cannot halt and enable current or drive at the same time!")

            if args.enable:
                print("Enabling motor current")
                instr.enable_motor_current()

            elif args.disable:
                print("Disabling motor current")
                instr.disable_motor_current()

            if args.disable and any([args.fully_close, args.target, args.step_close, args.step_open]):
                raise QMI_UsageException("Cannot drive after disabling current.")

            if args.fully_close and any([args.target, args.step_close, args.step_open]):
                raise QMI_UsageException("Full close and drive to target or stepping not allowed at the same time!")

            if args.target:
                print(f"Moving to target percentage {args.target[0]}")
                instr.open_to_target(args.target[0])

            if args.step_open:
                print(f"stepping +{args.step_open} steps.")
                instr.step_open(args.step_open)

            if args.step_close:
                print(f"stepping -{args.step_close} steps.")
                instr.step_close(args.step_close)

    return 0


if __name__ == "__main__":
    sys.exit(main())
