"""
The qmi.instruments.bristol package provides support for devices manufactured by Bristol Instruments.

Currently, supported are:
- 871 Series laser wavelength meter.
- four-channel Fiber-Optic Switch (FOS)
"""

from qmi.instruments.bristol.bristol_871a import Bristol_871A
from qmi.instruments.bristol.fos import Bristol_Fos as Bristol_Fos
