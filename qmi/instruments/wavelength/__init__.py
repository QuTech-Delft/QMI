"""
Wavelength Electronics, temperature controller.

The qmi.instruments.wavelength package provides support for:
- TC LAB series.
"""
from qmi.instruments.wavelength.tclab import AutotuneMode, TemperatureControllerCondition
# Alternative, QMI naming convention approved name
from qmi.instruments.wavelength.tclab import Wavelength_TC_Lab as Wavelength_TcLab
