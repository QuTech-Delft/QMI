"""
Pico Technology Ltd., oscilloscopes.

The qmi.instruments.picotech package provides support for:
- PicoScope 3403 and
- PicoScope 4824 Models.
"""
from qmi.instruments.picotech._picoscope import ChannelCoupling, TriggerEdge
from qmi.instruments.picotech.picoscope3403 import PicoTech_PicoScope3403
from qmi.instruments.picotech.picoscope4824 import PicoTech_PicoScope4824
