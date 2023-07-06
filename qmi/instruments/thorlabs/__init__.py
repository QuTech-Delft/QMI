"""
Thorlabs Inc.; motorized mounts, optical power meter, temperature controller, environmental sensors.

The qmi.instruments.thorlabs package provides support for:
- K10CR1 rotational mount
- MFF10X filter flip mounts
- PM100D power meter
- TSP01, TSP01B environmental sensors.
"""
from qmi.instruments.thorlabs.pm100d import SensorInfo
from qmi.instruments.thorlabs.tc200 import Tc200Status
# Alternative, QMI naming convention approved names
from qmi.instruments.thorlabs.k10cr1 import Thorlabs_K10CR1 as Thorlabs_K10Cr1
from qmi.instruments.thorlabs.mff10x import Thorlabs_MFF10X as Thorlabs_Mff10X
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM16_120 as Thorlabs_pm16120
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100D as Thorlabs_Pm100d
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100USB as Thorlabs_Pm100usb
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM101U as Thorlabs_Pm101u
from qmi.instruments.thorlabs.tc200 import Thorlabs_TC200 as Thorlabs_Tc200
from qmi.instruments.thorlabs.tsp01 import Thorlabs_TSP01 as Thorlabs_Tsp01
from qmi.instruments.thorlabs.tsp01b import Thorlabs_TSP01B as Thorlabs_Tsp01b
