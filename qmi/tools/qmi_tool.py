"""Swiss army knife for QMI command line monitoring and control.

Run with `qmi_tool ls` or `qmi_tool lsqmi` to list all QMI contexts present on the network with the default
workgroup name ("default"). To see other contexts in other workgroups, use:
`qmi_tool ls <workgroup-name>`.
You can also give timeout:
`qmi_tool ls <workgroup-name> 10`.

You can also use this tool to kill all visible QMI contexts with the default workgroup name with:
`qmi_tool hard-kill`. Use with care and never use without first checking which contexts will be killed,
with `qmi_tool ls`.
"""

import random
import sys
import socket
import time
import re

from qmi.core.config_defs import CfgQmi
from qmi.core.context import ping_qmi_contexts
from qmi.core.udp_responder_packets import QMI_UdpResponderKillRequestPacket


UDP_RESPONDER_PORT = 35999


def lsqmi(workgroup_name: str = CfgQmi.workgroup, timeout: float = 0.1) -> None:
    """List all QMI contexts on the network.

    Parameters:
        workgroup_name: The name of the workgroup to be searched for. Default is the CfgQmi.workgroup default.
        timeout:        Timeout to wait for answers (default: 0.1).
    """
    # Ping and collect responses.
    timestamped_packets = ping_qmi_contexts(workgroup_name_filter=workgroup_name, timeout=timeout)

    # Print info.
    print("Number of contexts found: {}".format(len(timestamped_packets)))

    for (response_packet_received_timestamp, incoming_address, response_packet) in timestamped_packets:
        # Estimate, on our local clock, at what time the packet was processed on the other side.
        t_at_remote = 0.5 * (response_packet.request_pkt_timestamp + response_packet_received_timestamp)  # average

        # Determine clock deviation (their clock - our clock).
        clock_deviation = response_packet.pkt_timestamp - t_at_remote

        # Roundtrip time.
        roundtrip_time = response_packet_received_timestamp - response_packet.request_pkt_timestamp

        print("QMI_Context found: {}:{}, pid {!r}, name {!r}; workgroup {!r}; round-trip time {:.3f} ms; clock deviation {:+.3f} ms.".format(
            incoming_address[0],
            response_packet.context.port,
            response_packet.context.pid,
            response_packet.context.name.decode(),
            response_packet.context.workgroup_name.decode(),
            1e3 * roundtrip_time,
            1e3 * clock_deviation
        ))


def hard_kill() -> None:
    """Broadcast a hard-kill request."""
    # Preparing outgoing socket.
    udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

    try:
        # Allow broadcasts on the socket.
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Send packet.
        address_out = ('<broadcast>', UDP_RESPONDER_PORT)
        request_pkt_id = random.randint(1, 2**64 - 1)
        request_packet = QMI_UdpResponderKillRequestPacket.create(
            request_pkt_id,
            time.time()
        )
        udp_socket.sendto(request_packet, address_out)

    finally:
        udp_socket.close()


def run() -> None | str:
    for e, arg in enumerate(sys.argv[1:]):
        if arg not in ["ls", "lsqmi", "hard-kill", "hard-kill-yes-really-i-am-sure"]:
            return f"Invalid argument {arg}."

        if arg == "ls" or arg == "lsqmi":
            if len(sys.argv) == (e + 3):
                # we have one input and need to check if it is timeout or workgroup name
                if len(re.findall(r"[a-zA-z]+", sys.argv[e+2])) == 0:
                    #  no alphabet characters so it must be a number
                    lsqmi(timeout=float(sys.argv[e+2]))
                else:
                    lsqmi(sys.argv[e+2])

            elif len(sys.argv) == (e + 4):
                # we have two inputs and need to check which is timeout and which workgroup name
                if len(re.findall(r"[a-zA-z]+", sys.argv[e + 2])) == 0:
                    #  no alphabet characters so it must be a number and second argument must be the workgroup name
                    lsqmi(sys.argv[e + 3], timeout=float(sys.argv[e + 2]))
                else:
                    lsqmi(sys.argv[e + 2], timeout=float(sys.argv[e + 3]))

            else:
                # We use defaults
                lsqmi()

        if arg == "hard-kill":
            print("This kills all the contexts that are visible (see output of `ls`)!")
            print("If you are sure, use `qmi_tool hard-kill-yes-really-i-am-sure`")

        if arg == "hard-kill-yes-really-i-am-sure":
            hard_kill()

    return None


if __name__ == "__main__":
    sys.exit(run())
