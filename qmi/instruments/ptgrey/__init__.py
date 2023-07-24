"""
Teledyne FLIR, Point Grey; machine vision camera.

The qmi.instruments.ptgrey package provides support for:
- Blackfly digital camera, with
  - Aravis open-source module.
"""
# The class names are not fully QMI style compliant, but a distinction needs to be made.
from qmi.instruments.ptgrey.blackfly_aravis import PtGrey_BlackFly_Aravis as Flir_Blackfly_Aravis
