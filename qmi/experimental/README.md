With the Protocol `QMI_PowerMeter_Protocol`, doing the following with ensure that the class that you would like to implement `QMI_PowerMeter_Protocol` implements it
```python
import qmi
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100D
from qmi.experimental.power_meter import QMI_PowerMeter_Protocol
issubclass(Thorlabs_PM100D, QMI_PowerMeter_Protocol)
```
The last line will return true if `Thorlabs_PM100D` implements the protocol. For the ABC `QMI_PowerMeter`, the check will be done at compile time.