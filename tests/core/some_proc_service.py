#! /usr/bin/env python

"""Minimal QMI process used as the `program_module` target for the `qmi_proc start`/`stop`
integration tests in `tests.core.test_qmi_proc`. It starts a QMI context and keeps running
until a shutdown request is received via RPC."""

import qmi

CONTEXT_NAME = "ContextName1"


def main() -> None:
    with qmi.start(CONTEXT_NAME) as ctx:
        while not ctx.wait_until_shutdown(1.0):
            pass


if __name__ == "__main__":
    main()
