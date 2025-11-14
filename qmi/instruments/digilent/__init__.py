"""
Digilent, USB oscilloscope and logic analyzer device.

The qmi.instruments.digilent package provides support for:
- Analog Discovery 2 device.
"""
from qmi.instruments.digilent.analog_discovery import OnClose, Filter
from qmi.instruments.digilent.analog_discovery import AnalogDiscovery2  # cannot remove due to legacy --> deprecate?
# Alternative, QMI naming convention approved names
Digilent_AnalogDiscovery2 = AnalogDiscovery2
