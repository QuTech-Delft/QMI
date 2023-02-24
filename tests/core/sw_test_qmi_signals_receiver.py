import qmi

from qmi.core.pubsub import QMI_SignalReceiver


def get_signals(recv_plot_signal: QMI_SignalReceiver):

    if recv_plot_signal.has_signal_ready():
        data = recv_plot_signal.get_next_signal()
        print(data)


if __name__ == "__main__":
    qmi.start("oh_no", context_cfg={"oh_yeah": {"tcp_server_port": 12345}})
    # First we need to find the context. If there are multiple contexts, filter by name.
    ctx = qmi.context().discover_peer_contexts()[0]  # The found context must be the one sending the data
    # Connect to it.
    qmi.context().connect_to_peer("oh_yeah", peer_address=ctx[1])
    # Get the RPC object from the connected context.
    ddc = qmi.get_rpc_object("oh_yeah.whoa")
    qmi.show_rpc_objects()
    # Create a signal receiver and subscribe to the publisher.
    sig_recv = QMI_SignalReceiver()
    ddc.signal_publisher.subscribe(sig_recv)
    # Then get signals and see that it works.
    while True:
        try:
            get_signals(sig_recv)

        except KeyboardInterrupt:
            break

        except:
            break

    try:
        qmi.context().disconnect_from_peer("oh_yeah")

    finally:
        qmi.stop()
        exit()
