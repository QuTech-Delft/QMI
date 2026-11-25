#!/usr/bin/env python
"""QMI signals tutorial: receive the signals of a task that runs in another program."""

import qmi
from qmi.core.exceptions import QMI_TimeoutException
from qmi.utils.context_managers import subscribe_unsubscribe


def main() -> None:
    with qmi.start("signal_client", config_file="qmi.conf"):
        # The proxy of a remote task offers the same signal attributes as the proxy of a local one.
        sampler = qmi.get_task("signal_server.sampler", auto_connect=True, host_port="127.0.0.1:40002")
        with subscribe_unsubscribe(sampler.sig_sample, None) as receiver:
            # Throw away anything queued so far and wait for fresh data only.
            receiver.discard_all()
            for _ in range(5):
                try:
                    received = receiver.get_next_signal(timeout=2.0)
                except QMI_TimeoutException:
                    print("no samples; is signal_server.py running?")
                    break

                sample = received.args[0]
                print(f"{received.publisher_context}.{received.publisher_name}: value = {sample.value:.2f}")


if __name__ == "__main__":
    main()
