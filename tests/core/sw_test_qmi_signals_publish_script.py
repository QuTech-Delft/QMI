import time
import threading
from typing import cast

import qmi
from qmi.core.rpc import QMI_RpcObject
from qmi.core.pubsub import QMI_Signal


class DummyDataCreator(QMI_RpcObject):

    signal_publisher = QMI_Signal([list])

    def __init__(self, ctx, name):
        super().__init__(ctx, name)
        self._data = [0] * 5
        self._running = False

    def start(self):
        self._running = True
        while self._running:
            self._data.append(self._data.pop(0) + 1)
            self.signal_publisher.publish(self._data)
            time.sleep(1)

    def stop(self):
        self._running = False


if __name__ == "__main__":
    qmi.start("oh_yeah", context_cfg={"oh_yeah": {"tcp_server_port": 12345}})
    # Create an RPC proxy to the class that has the signal publisher.
    ddc = qmi.make_rpc_object("whoa", DummyDataCreator)
    ddc = cast(ddc, DummyDataCreator)(qmi.context(), "whoa")
    qmi.show_rpc_objects()
    pub_thread = threading.Thread(target=ddc.start)
    pub_thread.start()

    while True:
        try:
            time.sleep(1)

        except KeyboardInterrupt:
            break

        except:
            break

    ddc.stop()
    pub_thread.join()
    qmi.stop()
    exit()
