"""
NKT Photonics, laser driver and amplifier.

The qmi.instruments.nkt_photonics package provides support for:
- Koheras ADJUSTIK laser driver
- Koheras BOOSTIK laser amplifier
- Fianium (FemtoPower 1060) supercontinuum laser source
"""
# Alternative, QMI naming convention approved names
from qmi.instruments.nkt_photonics.adjustik import KoherasAdjustikLaser as NktPhotonics_KoherasAdjustik
from qmi.instruments.nkt_photonics.boostik import KoherasBoostikLaserAmplifier as NktPhotonics_KoherasBoostik
from qmi.instruments.nkt_photonics.fianium import NKT_Fianium as NktPhotonics_Fianium
