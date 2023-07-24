"""
Tektronix Inc.; function and waveform generators, frequency counters

The qmi.instruments.tektronix package provides support for:
- AFG31000 series arbitrary function generator
- AWG 5014[C] arbitrary waveform generator
- FCA3000 and compatible frequency counters
"""
from qmi.instruments.tektronix.awg5014 import Tektronix_Awg5014
from qmi.instruments.tektronix.afg31000 import Waveform, BurstMode, TriggerEdge
# Alternative, QMI naming convention approved names
from qmi.instruments.tektronix.afg31000 import Tektronix_AFG31000 as Tektronix_Afg31000
from qmi.instruments.tektronix.fca3000 import Tektronix_FCA3000 as Tektronix_Fca3000
