"""
NKT Photonics, laser driver and amplifier.

The qmi.instruments.nkt_photonics package provides support for:
- Koheras ADJUSTIK laser driver
- Koheras BOOSTIK laser amplifier.
"""
# Alternative, QMI naming convention approved names
from qmi.instruments.nkt_photonics.adjustik import KoherasAdjustikLaser as NktPhotonics_KoherasAdjustik
from qmi.instruments.nkt_photonics.boostik import KoherasBoostikLaserAmplifier as NktPhotonics_KoherasBoostik
