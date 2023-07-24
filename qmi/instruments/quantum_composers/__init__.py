"""
Quantum Composers, delay pulse generator.

The qmi.instruments.quantum_composers package provides support for:
- 9530 series.
"""

from qmi.instruments.quantum_composers.pulse_generator9530 import QuantumComposers_PulseGenerator9530 as\
    QuantumComposers_9530
from qmi.instruments.quantum_composers.pulse_generator9530 import RefClkSource, PulseMode, TriggerMode, TriggerEdge,\
    OutputDriver
