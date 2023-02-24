#! /usr/bin/env python3

"""
Test shutdown of QMI with instrument still open.

This program does not use the unittest framework because it tests
for problems that are difficult to trigger in the context of
a unit test.

A specific scenario is tested:
  - Application starts QMI.
  - Application creates a QMI instrument instance and opens the instrument.
  - Application leaks a reference to the instrument proxy into a global variable.
  - Application stops QMI (with instrument still open).
  - Application exits.

This is tricky is several ways:
  - The QMI context is stopped while an RPC object is still active.
  - The QMI instrument instance is eventually cleaned up while instrument still open.
  - The global reference to the instrument proxy may hold up cleanup of the
    QMI context until after the logging system has already shut down.
  - During cleanup, QMI may try to log while the logging system is already down
    and thus trigger mayhem.
"""

import socket
import threading
import time

import qmi
from qmi.instruments.cobolt.laser_06_01 import Cobolt_Laser_06_01


_global_proxies = []


def _start_server():
    """Start a background TCP server for the instrument to connect to."""

    global _server_thread
    global _server_port

    # Create server socket.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind to arbitrary port.
    sock.bind(("127.0.0.1", 0))
    (host, _server_port) = sock.getsockname()

    sock.listen(1)
    print("Dummy server waiting for TCP connection on port", _server_port)

    # Start background thread.
    _server_thread = threading.Thread(target=_run_server, args=(sock,))
    _server_thread.start()


def _run_server(sock):

    global _server_conn

    # Within background thread, wait for incoming connection.
    sock.settimeout(1.0)
    while True:
        try:
            (conn, addr) = sock.accept()
            break
        except (TimeoutError, socket.timeout):
            if not threading.main_thread().is_alive():
                print("Dummy server aborting")
                sock.close()
                return
        
    print("Dummy server got incoming TCP connection")
    sock.close()

    # Keep reference to connection socket to keep it open.
    _server_conn = conn

    # End background thread.


def main():

    # Start background TCP server.
    _start_server()

    # Start QMI.
    qmi.start("test_context")

    # Create laser instance.
    transport = "tcp:127.0.0.1:{}".format(_server_port)
    laser = qmi.make_instrument("laser", Cobolt_Laser_06_01, transport)

    # Open instrument.
    laser.open()

    # Leak the instrument proxy to a global variable.
    _global_proxies.append(laser)

    # Clean up background thread.
    _server_thread.join()

    # Wait for dramatic effect.
    time.sleep(1)

    # Stop QMI.
    qmi.stop()


if __name__ == "__main__":
    main()

