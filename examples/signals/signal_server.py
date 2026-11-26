#!/usr/bin/env python
"""QMI signals tutorial: a background program that publishes samples until it is stopped."""

import time

import qmi
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator

from demo_signals import SamplerTask


def main() -> None:
    with qmi.start("signal_server", config_file="qmi.conf"):
        with qmi.make_instrument("nsg", NoisySineGenerator):
            with qmi.make_task("sampler", SamplerTask, "signal_server.nsg"):
                print("publishing samples, press Ctrl+C to stop")
                try:
                    while True:
                        time.sleep(1.0)
                except KeyboardInterrupt:
                    pass


if __name__ == "__main__":
    main()
