#! /usr/bin/env python3

"""
Test program for QMI_SerialTransport.

This program needs two serial ports (or USB serial port adapters)
which are connected by an RS-232 cross cable.
"""

import argparse
import queue
import threading
import time

import numpy as np
import serial

import qmi
from qmi.core.exceptions import QMI_TimeoutException
from qmi.core.transport import create_transport


def _make_message(message_length):
    return bytes([ord("a") + (i % 26) for i in range(message_length)])


def _report_interval_stats(text, data):
    print("  {:40}: avg={:.4f}, min={:.4f}, max={:.4f} (s)"
          .format(text, np.mean(data), np.min(data), np.max(data)))


def _test_write_helper(serial_bench, message_lengths, recv_messages, recv_timestamps):
    """Helper function to receive serial port data in a background thread."""

    for message_length in message_lengths:

        # Receive message and record timestamp.
        msg = serial_bench.read(message_length)
        t = time.monotonic()

        recv_messages.append(msg)
        recv_timestamps.append(t)

        if len(msg) != message_length:
            break


def test_write(transport, serial_bench):
    """Test writing through transport."""

    print()
    print("Test writing through transport:")

    message_lengths = [1, 2, 3, 5, 10, 15, 20, 25, 30, 35]
    send_messages = []
    send_timestamps = []
    recv_messages = []
    recv_timestamps = []

    thread = threading.Thread(target=_test_write_helper, kwargs={
        "serial_bench": serial_bench,
        "message_lengths": message_lengths,
        "recv_messages": recv_messages,
        "recv_timestamps": recv_timestamps
    })
    thread.start()

    try:
        for message_length in message_lengths:

            # Wait to decouple from previous message.
            time.sleep(0.1)

            # Create test message.
            msg = _make_message(message_length)
            send_messages.append(msg)

            # Record timestamp, then write message.
            t = time.monotonic()
            transport.write(msg)
            send_timestamps.append(t)

    finally:
        # Wait for background thread to end.
        thread.join()

    if len(recv_timestamps) != len(send_timestamps):
        print("ERROR: expected {} messages but received only {}"
              .format(len(send_timestamps), len(recv_timestamps)))
        return

    for (send_msg, recv_msg) in zip(send_messages, recv_messages):
        if recv_msg != send_msg:
            print("ERROR: expected message {!r} but received {!r}"
                  .format(send_msg, recv_msg))
            return

    # Report send-to-receive latency.
    wait_times = np.array(recv_timestamps) - np.array(send_timestamps)
    _report_interval_stats("send-to-receive latency", wait_times)


def _test_read_helper(serial_bench, message_queue):
    """Helper function to send data through the serial port in a background thread."""

    while True:

        # Get next message.
        (msg, msg_delay) = message_queue.get(block=True)

        if msg is None:
            break

        # Wait before starting to send the message.
        time.sleep(msg_delay)

        # Send the message.
        serial_bench.write(msg)


def _test_read_message_ready(transport, serial_bench, timeout):
    """Test reading a message which is already available."""

    read_latency = []
    for message_length in [1, 2, 3, 5, 10, 15, 20, 25, 30, 35]:

        # Send message through test bench.
        msg = _make_message(message_length)
        serial_bench.write(msg)

        # Wait to make sure message is received.
        time.sleep(0.2)

        # Read message and measure latency.
        t0 = time.monotonic()
        recv_msg = transport.read(nbytes=message_length, timeout=timeout)
        t1 = time.monotonic()
        read_latency.append(t1 - t0)

        if recv_msg != msg:
            print("ERROR: Expecting {!r} but received {!r}".format(msg, recv_msg))

    _report_interval_stats("read latency, message ready", read_latency)


def _test_read_no_data(transport, timeout):
    """Test timeout when nothing is received."""

    read_latency = []
    for message_length in [1, 2, 3, 5, 10, 15, 20, 25, 30, 35]:

        # Sleep to decouple from previous message.
        time.sleep(0.1)

        # Read message and measure latency until timeout.
        try:
            t0 = time.monotonic()
            recv_msg = transport.read(nbytes=message_length, timeout=timeout)
            print("ERROR: Expecting timeout but received {!r}".format(recv_msg))
        except QMI_TimeoutException:
            t1 = time.monotonic()
        read_latency.append(t1 - t0)

    _report_interval_stats("timeout latency, no data", read_latency)


def _test_read_partial_data(transport, serial_bench, timeout):
    """Test timeout when a partial message is received."""

    read_latency = []
    for message_length in [2, 3, 5, 10, 15, 20, 25, 30, 35]:

        # Send partial message.
        msg = _make_message(message_length // 2)
        serial_bench.write(msg)

        # Sleep to make sure partial message is available.
        time.sleep(0.2)

        # Read message and measure latency until timeout.
        try:
            t0 = time.monotonic()
            recv_msg = transport.read(nbytes=message_length, timeout=timeout)
            print("ERROR: Expecting timeout but received {!r}".format(recv_msg))
        except QMI_TimeoutException:
            t1 = time.monotonic()
        read_latency.append(t1 - t0)

        # Read partial message to flush it from the buffer.
        recv_msg = transport.read(nbytes=len(msg), timeout=0.0)
        if recv_msg != msg:
            print("ERROR: Expecting {!r} but received {!r}".format(msg, recv_msg))

    _report_interval_stats("timeout latency, partial data", read_latency)


def _test_read_wait_for_message(transport, message_queue, timeout, fragments):
    """Test latency when a message is received after waiting."""

    assert fragments in (1, 2)

    msg_delay = 0.5 if (timeout is None) else (0.4 * timeout)

    read_latency = []
    for message_length in range(fragments, 10+fragments):

        # Sleep to decouple from previous message.
        time.sleep(0.1)

        # Tell background thread to send message (in one or two fragments):
        msg = _make_message(message_length)
        if fragments == 2:
            message_queue.put((msg[:message_length//2], 0.5 * msg_delay))
            message_queue.put((msg[message_length//2:], 0.5 * msg_delay))
        else:
            message_queue.put((msg, msg_delay))

        # Read message and measure latency.
        t0 = time.monotonic()
        recv_msg = transport.read(nbytes=message_length, timeout=timeout)
        t1 = time.monotonic()
        read_latency.append(t1 - t0)

        if recv_msg != msg:
            print("ERROR: Expecting {!r} but received {!r}".format(msg, recv_msg))

    if fragments == 2:
        _report_interval_stats("read latency, 2*{:.3f}s message delay".format(0.5 * msg_delay), read_latency)
    else:
        _report_interval_stats("read latency, {:.3f}s message delay".format(msg_delay), read_latency)


def test_read(transport, serial_bench, timeout):
    """Test reading through transport."""

    print()
    print("Test reading fixed number of bytes through transport (timeout={}):".format(timeout))

    _test_read_message_ready(transport, serial_bench, timeout)
    if timeout is not None:
        _test_read_no_data(transport, timeout)
        _test_read_partial_data(transport, serial_bench, timeout)

    if (timeout is None) or (timeout > 0):

        # Start backgroud thread.
        message_queue = queue.Queue()
        thread = threading.Thread(target=_test_read_helper, kwargs={
            "serial_bench": serial_bench,
            "message_queue": message_queue
        })
        thread.start()

        try:
            _test_read_wait_for_message(transport, message_queue, timeout, 1)
            _test_read_wait_for_message(transport, message_queue, timeout, 2)

        finally:
            # Wait for background thread to end.
            message_queue.put((None, 0.0))
            thread.join()


def _test_read_until_message_ready(transport, serial_bench, message_terminator, timeout):
    """Test reading a message which is already available."""

    read_latency = []
    for message_length in [1, 2, 3, 5, 10, 15, 20, 25, 30, 35]:

        # Send message through test bench.
        msg = _make_message(message_length) + message_terminator
        serial_bench.write(msg)

        # Wait to make sure message is received.
        time.sleep(0.2)

        # Read message and measure latency.
        t0 = time.monotonic()
        recv_msg = transport.read_until(message_terminator=message_terminator, timeout=timeout)
        t1 = time.monotonic()
        read_latency.append(t1 - t0)

        if recv_msg != msg:
            print("ERROR: Expecting {!r} but received {!r}".format(msg, recv_msg))

    _report_interval_stats("read latency, message ready", read_latency)


def _test_read_until_no_data(transport, message_terminator, timeout):
    """Test timeout when nothing is received."""

    read_latency = []
    for i in range(10):

        # Sleep to decouple from previous message.
        time.sleep(0.1)

        # Read message and measure latency until timeout.
        try:
            t0 = time.monotonic()
            recv_msg = transport.read_until(message_terminator=message_terminator, timeout=timeout)
            print("ERROR: Expecting timeout but received {!r}".format(recv_msg))
        except QMI_TimeoutException:
            t1 = time.monotonic()
        read_latency.append(t1 - t0)

    _report_interval_stats("timeout latency, no data", read_latency)


def _test_read_until_partial_data(transport, serial_bench, message_terminator, timeout):
    """Test timeout when a partial message is received."""

    read_latency = []
    for message_length in [1, 2, 3, 5, 8, 10, 12, 15, 20]:

        # Send partial message.
        msg = _make_message(message_length)
        serial_bench.write(msg)

        # Sleep to make sure partial message is available.
        time.sleep(0.2)

        # Read message and measure latency until timeout.
        try:
            t0 = time.monotonic()
            recv_msg = transport.read_until(message_terminator=message_terminator, timeout=timeout)
            print("ERROR: Expecting timeout but received {!r}".format(recv_msg))
        except QMI_TimeoutException:
            t1 = time.monotonic()
        read_latency.append(t1 - t0)

        # Read partial message to flush it from the buffer.
        recv_msg = transport.read(nbytes=message_length, timeout=0.0)
        if recv_msg != msg:
            print("ERROR: Expecting {!r} but received {!r}".format(msg, recv_msg))

    _report_interval_stats("timeout latency, partial data", read_latency)


def _test_read_until_wait_for_message(transport, message_queue, message_terminator, timeout, fragments):
    """Test latency when a message is received after waiting."""

    assert fragments in (1, 2)

    msg_delay = 0.5 if (timeout is None) else (0.4 * timeout)

    read_latency = []
    for message_length in range(fragments, 10+fragments):

        # Sleep to decouple from previous message.
        time.sleep(0.1)

        # Tell background thread to send message (in one or two fragments):
        msg = _make_message(message_length) + message_terminator
        if fragments == 2:
            message_queue.put((msg[:message_length//2], 0.5 * msg_delay))
            message_queue.put((msg[message_length//2:], 0.5 * msg_delay))
        else:
            message_queue.put((msg, msg_delay))

        # Read message and measure latency.
        t0 = time.monotonic()
        recv_msg = transport.read_until(message_terminator=message_terminator, timeout=timeout)
        t1 = time.monotonic()
        read_latency.append(t1 - t0)

        if recv_msg != msg:
            print("ERROR: Expecting {!r} but received {!r}".format(msg, recv_msg))

    if fragments == 2:
        _report_interval_stats("read latency, 2*{:.3f}s message delay".format(0.5 * msg_delay), read_latency)
    else:
        _report_interval_stats("read latency, {:.3f}s message delay".format(msg_delay), read_latency)


def test_read_until(transport, serial_bench, message_terminator, timeout):
    """Test reading through transport until end of message."""

    print()
    print("Test reading through transport until {!r} (timeout={}):".format(message_terminator, timeout))

    _test_read_until_message_ready(transport, serial_bench, message_terminator, timeout)
    if timeout is not None:
        _test_read_until_no_data(transport, message_terminator, timeout)
        _test_read_until_partial_data(transport, serial_bench, message_terminator, timeout)

    if (timeout is None) or (timeout > 0):

        # Start backgroud thread.
        message_queue = queue.Queue()
        thread = threading.Thread(target=_test_read_helper, kwargs={
            "serial_bench": serial_bench,
            "message_queue": message_queue
        })
        thread.start()

        try:
            _test_read_until_wait_for_message(transport, message_queue, message_terminator, timeout, 1)
            _test_read_until_wait_for_message(transport, message_queue, message_terminator, timeout, 2)

        finally:
            # Wait for background thread to end.
            message_queue.put((None, 0.0))
            thread.join()


def test_serial_transport(dutdev, benchdev, baudrate):
    """Test serial port transport at a specific baudrate."""

    print()
    print("Testing at baud rate {}".format(baudrate))
    print()

    print("Opening test bench serial port {} ...".format(benchdev))
    serial_bench = serial.Serial(benchdev, baudrate, timeout=5.0)
    print("  ok")

    try:

        print("Opening serial transport device {} ...".format(dutdev))
        transport = create_transport("serial:{}:baudrate={}".format(dutdev, baudrate))
        transport.open()
        print("  ok")

        try:
            test_write(transport, serial_bench)
            for timeout in (None, 0.0, 0.1, 1.0):
                test_read(transport, serial_bench, timeout)
            for timeout in (None, 0.0, 0.5):
                test_read_until(transport, serial_bench, b"\n", timeout)
                test_read_until(transport, serial_bench, b"\r\n", timeout)

        finally:
            transport.close()

    finally:
        serial_bench.close()


def main():

    parser = argparse.ArgumentParser()
    parser.description = "Test program for QMI_SerialTransport."
    parser.add_argument("dutdev", action="store", type=str,
                        help="serial port device under test (e.g. /dev/ttyUSB0)")
    parser.add_argument("benchdev", action="store", type=str,
                        help="serial port to act as test bench (e.g. /dev/ttyUSB1)")

    args = parser.parse_args()

    qmi.start("test_transport_serial", "")
    try:
        test_serial_transport(args.dutdev, args.benchdev, baudrate=115200)
    finally:
        qmi.stop()


if __name__ == "__main__":
    main()
