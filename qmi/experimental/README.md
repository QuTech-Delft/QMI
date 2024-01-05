With the Protocol `QMI_PowerMeter_Protocol`, doing the following with ensure that the class that you would like to implement `QMI_PowerMeter_Protocol` implements it
```python
from qmi.instruments.thorlabs.pm100d import Thorlabs_PM100D
from qmi.experimental.power_meter import QMI_PowerMeter_Protocol
issubclass(Thorlabs_PM100D, QMI_PowerMeter_Protocol)
```
The last line will return true if `Thorlabs_PM100D` implements the protocol. For the ABC `QMI_PowerMeter_Mixin`, the check will be done at compile time. The same holds for `QMI_PowerMeter_Single_Inheritance`.

Currently `Thorlabs_PM100D` and `Newport_843R` implement the protocol and `Thorlabs_PM100D` implements `QMI_Instrument` and the mixin `QMI_PowerMeter_Mixin`, whereas `Newport_843R` implements `QMI_PowerMeter_Single_Inheritance`.