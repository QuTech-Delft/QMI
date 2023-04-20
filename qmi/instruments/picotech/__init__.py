"""The qmi.instruments.picotech package provides support for devices manufactured by PicoTech.

Currently, instruments supported are: PicoScope 3403 and PicoScope 4824 Models.
"""
from qmi.instruments.picotech._picoscope import PicoTech_PicoScope, ChannelCoupling, TriggerEdge,\
    _check_error, _import_modules
from qmi.instruments.picotech.picoscope3403 import PicoTech_PicoScope3403
from qmi.instruments.picotech.picoscope4824 import PicoTech_PicoScope4824
