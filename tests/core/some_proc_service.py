import sys, os
import time

import qmi
from qmi.core.exceptions import QMI_Exception


def main() -> int:
    """Application entry point."""
    runs: int = 10
    try:
        qmi.start("ContextName1", console_loglevel="CRITICAL")

        runned = 0

        while runned < runs:
            if qmi.context().wait_until_shutdown(duration=0.5):
                break

            # We do the update here instead of in a task due to
            # `get_context_status(...)` requiring main thread access.
            time.sleep(0.5)
            runned += 1

    except QMI_Exception as exc:
        print(f"ERROR: ({type(exc).__name__})", exc, file=sys.stderr)
        return 1

    finally:
        qmi.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
