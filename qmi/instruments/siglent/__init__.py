"""
Siglent Technologies, oscilloscopes and spectrum analyzers.

The qmi.instruments.siglent package provides support for:
- SDS1202X-E oscilloscope
- SSA300X series spectrum analyzers.
"""

from qmi.instruments.siglent.sds1202xe import SDS1202XE, CommHeader, TriggerCondition
from qmi.instruments.siglent.ssa3000x import SSA3000X
# Alternative, QMI naming convention approved names
Siglent_Sds1202xE = SDS1202XE
Siglent_Ssa3000x = SSA3000X
