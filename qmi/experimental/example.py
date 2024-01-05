"""Examples for the experimental code."""
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100D
from qmi.experimental.power_meter import QMI_PowerMeter_Protocol


print(f"Thorlabs PM100D implements QMI_PowerMeter_Protocol {issubclass(Thorlabs_PM100D, QMI_PowerMeter_Protocol)}")
