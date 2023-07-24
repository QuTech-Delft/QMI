"""
Zurich Instruments AG, arbitrary waveform generator.

The qmi.instruments.zurich_instruments package provides support for:
- HDAWG.
"""
from qmi.instruments.zurich_instruments.hdawg import CompilerStatus, UploadStatus
# Alternative, QMI naming convention approved name
from qmi.instruments.zurich_instruments.hdawg import ZurichInstruments_HDAWG as ZurichInstruments_Hdawg
