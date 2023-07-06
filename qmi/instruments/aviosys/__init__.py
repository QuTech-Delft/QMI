"""
Aviosys, relay unit device.

The qmi.instruments.aviosys package provides support for:
- IP Power 9850 relay unit.
"""
# Alternative, QMI naming convention approved name
from qmi.instruments.aviosys.ippower import IPPower9850 as Aviosys_IpPower9850
from qmi.instruments.aviosys.ippower import PowerState, PowerSocket, Command
