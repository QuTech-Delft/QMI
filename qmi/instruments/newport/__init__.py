"""
Newport Corporation, MKS and New Focus; motion controllers, steppers, power meter, tunable laser controller.

The qmi.instruments.newport package provides support for:
- Agilis AG-UC8 piezo stepper controller
- Motion controllers (including, but not limited to):
  - SMC100CC, with linear actuator:
    - CMA25CCL
  - CONEX-CC, with linear actuators:
    - TRA12CC
    - TRB6CC
- 843-R optical power meter
- TLB-6700 series tunable laser controllers.
"""
# Alternative, QMI naming convention approved name
from qmi.instruments.newport.ag_uc8 import Newport_AG_UC8 as Newport_AgilisUc8
from qmi.instruments.newport.ag_uc8 import AxisStatus
from qmi.instruments.newport.smc_100cc import Newport_SMC100CC as Newport_Smc100Cc, ControlLoopState
from qmi.instruments.newport.smc_100pp import Newport_SMC100PP as Newport_Smc100Pp
from qmi.instruments.newport.conex_cc import Newport_ConexCC as Newport_ConexCc
from qmi.instruments.newport.newport_843r import Newport_843R
from qmi.instruments.newport.tlb670x import NewFocus_TLB670X as NewFocus_Tlb670x
