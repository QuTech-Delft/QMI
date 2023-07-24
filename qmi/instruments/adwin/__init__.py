"""
Jäger Computergesteuerte Messtechnik GmbH, 'ADwin' devices.

The qmi.instruments.adwin package provides support for:
- high-capacity compact real-time systems
  - ADwin-Gold II
  - ADwin-Pro II
- T11, T12 and T12.1 processor types.
"""
# Alternative, QMI naming convention approved names
from qmi.instruments.adwin.proii import Adwin_ProII as JagerMessTechnik_AdwinProII
from qmi.instruments.adwin.goldii import Adwin_GoldII as JagerMessTechnik_AdwinGoldII
