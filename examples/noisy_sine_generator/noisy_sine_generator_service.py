#! /usr/bin/env python

"""Service for the noisy sine generator example.

This module starts the `nsg_service` QMI context, which exposes a `NoisySineGenerator`
instrument and a `NoisySineGeneratorController` task that samples it periodically and
publishes the samples via a `QMI_Signal`.

Point the `QMI_CONFIG` environment variable to `examples/noisy_sine_generator/qmi.conf` and
start (and later stop) the service with `qmi_proc`, run from the repository root::

  export QMI_CONFIG=examples/noisy_sine_generator/qmi.conf
  qmi_proc start nsg_service
  qmi_proc stop nsg_service

Or run it directly, also from the repository root::

  python -m examples.noisy_sine_generator.noisy_sine_generator_service --config=examples/noisy_sine_generator/qmi.conf

The `nsg_service` context in `qmi.conf` starts this module via `program_args` containing a
`{config_dir}` placeholder (since `qmi_proc` passes `program_args` to `subprocess.Popen` literally,
without QMI variable substitution). When starting the service this way, set the `CONFIG_DIR`
environment variable to point to the `examples/noisy_sine_generator` folder, so the placeholder can
be resolved::

  export CONFIG_DIR=examples/noisy_sine_generator
  qmi_proc start nsg_service
"""

import argparse
import logging
import os
import sys

import qmi

from qmi.core.exceptions import QMI_Exception
from qmi.core.read_keyboard import KeyboardReader
from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
from qmi.utils.context_managers import start_stop_join

from .noisy_sine_generator_controller import NoisySineGeneratorSettings, NoisySineGeneratorController

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters:
        argv: Argument list to parse, or None to parse `sys.argv[1:]`.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="store", type=str, default="",
                        help="specify the QMI configuration file")
    return parser.parse_args(argv)


def resolve_config_path(config: str) -> str:
    """Resolve the value of the `--config` argument.

    `qmi_proc` passes `program_args` to `subprocess.Popen` literally, without any shell or QMI
    variable substitution. So a `{config_dir}` placeholder embedded in `program_args` is resolved
    here instead, via the `CONFIG_DIR` environment variable.

    Parameters:
        config: Raw value of the `--config` argument, possibly containing the `{config_dir}`
            placeholder.

    Returns:
        Resolved configuration file path.
    """
    if "{config_dir}" in config:
        if "CONFIG_DIR" not in os.environ:
            sys.exit("The '{config_dir}' placeholder is used in --config, but the CONFIG_DIR "
                      "environment variable is not set.")
        return os.path.expandvars(config.replace("{config_dir}", "${config_dir}"))
    return config


def main(config: str) -> int:
    """Start the `nsg_service` context and run it until termination is requested.

    Parameters:
        config: Path of the QMI configuration file, or "" to use the `QMI_CONFIG` environment variable.

    Returns:
        Process exit status (0 = success).
    """
    qmi.start("nsg_service", config)

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
            _logger.info("Service running %r - type 'Q' + Enter to terminate.", qmi.context().name)

            # Run until termination is requested, either by RPC call or by the user.
            kbd = KeyboardReader()
            while True:
                if qmi.context().wait_until_shutdown(duration=0.1):
                    _logger.info("Context shutdown requested - stopping the service.")
                    break
                if kbd.poll_quit():
                    _logger.info("Shutdown requested by user - stopping the service.")
                    break

    except QMI_Exception as exc:
        _logger.error("Unexpected error in noisy sine generator service: %s", exc)
        return 1

    finally:
        # Always stop the context.
        qmi.stop()

    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(resolve_config_path(args.config)))
