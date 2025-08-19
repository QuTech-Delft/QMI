#! /usr/bin/env python

import sys

import qmi

from qmi.core.exceptions import QMI_Exception
from qmi.core.read_keyboard import KeyboardReader
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
from qmi.utils.context_managers import start_stop_join

from noisy_sine_generator_controller import NoisySineGeneratorSettings, NoisySineGeneratorController

def main():

    qmi.start("nsg_service", "qmi.conf")

    try:
        # Make the instrument as a QMI instrument.
        nsg = qmi.make_instrument("nsg", NoisySineGenerator)

        # Create the task; the task initializer applies the settings.
        settings = NoisySineGeneratorSettings(frequency=2.0, amplitude=100.0, noise=1.0)
        controller = qmi.make_task(
            "controller",
            NoisySineGeneratorController,
            generator=nsg,
            settings=settings,
            sample_time=1.0
        )

        # Start the task.
        with start_stop_join(controller):
            print("Service running {!r} - type 'Q' + Enter to terminate.".format(qmi.context().name))

            # Run until termination is requested, either by RPC call or by the user.
            kbd = KeyboardReader()
            while True:
                if qmi.context().wait_until_shutdown(duration=0.1):
                    print("Context shutdown requested - stopping the service.")
                    break
                if kbd.poll_quit():
                    print("Shutdown requested by user - stopping the service.")
                    break

    except QMI_Exception as e:
        print("ERROR: {}".format(e))
        return 1

    finally:
        # Always stop the context.
        qmi.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
