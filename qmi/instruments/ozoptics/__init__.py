"""
OZ Optics, attenuator and polarization controller.

The qmi.instruments.adwin package provides support for:
- DD-100-MC attenuator
- Electric Polarization Controller (EPC).
"""
from qmi.instruments.ozoptics.dd100mc import OZO_AttenuatorPosition
# Alternative, QMI naming convention approved names
from qmi.instruments.ozoptics.dd100mc import OZOptics_DD100MC as OzOptics_Dd100Mc
from qmi.instruments.ozoptics.epc_driver import OzOptics_EpcDriver as OzOptics_EPC
