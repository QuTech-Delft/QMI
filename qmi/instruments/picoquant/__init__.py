"""The qmi.instruments.picoquant package provides support for devices manufactured by PicoQuant.

Currently, four instruments are supported: MultiHarp 150, HydraHarp 400, TimeHarp 260 and PicoHarp 300.
"""
from qmi.instruments.picoquant._picoquant import TttrHistogram, RealTimeHistogram, RealTimeCountRate, EventFilterMode, \
    EventDataType
from qmi.instruments.picoquant.hydraharp import PicoQuant_HydraHarp400
from qmi.instruments.picoquant.multiharp import PicoQuant_MultiHarp150
from qmi.instruments.picoquant.timeharp import PicoQuant_TimeHarp260
from qmi.instruments.picoquant.picoharp import PicoQuant_PicoHarp300
