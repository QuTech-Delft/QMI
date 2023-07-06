"""
AimTTi: Function generators and frequency counters.

The qmi.instruments.tt package provides support for:
- TGF3000 series (discontinued)
- TGF4000 series.
"""
from qmi.instruments.tt.tgf import FrequencyMeasurement, WaveformType, CounterInputChannel
# Alternative, QMI naming convention approved names
from qmi.instruments.tt.tgf import TT_TGF_3000_4000_Series as AimTTi_Tgf30004000
