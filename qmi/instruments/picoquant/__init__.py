"""
PicoQuant, time tagger instruments and event handling.

The qmi.instruments.pi package provides support for:
- MultiHarp 150
- HydraHarp 400
- PicoHarp 300.
"""
from qmi.instruments.picoquant.support._decoders import EventDataType, EventFilterMode, SYNC_TYPE
from qmi.instruments.picoquant.support._realtime import RealTimeHistogram, RealTimeCountRate, TttrHistogram
from qmi.instruments.picoquant.hydraharp import PicoQuant_HydraHarp400
from qmi.instruments.picoquant.multiharp import PicoQuant_MultiHarp150
from qmi.instruments.picoquant.picoharp import PicoQuant_PicoHarp300
