"""
Edwards Vacuum, TIC controller.

The qmi.instruments.edwards package provides support for:
- Turbo & Instrument Controller (TIC) models D397-21-000/D397-22-000.
"""
# Alternative, QMI naming convention approved name
from qmi.instruments.edwards.turbo_instrument_controller import Edwards_TurboInstrumentController as\
    EdwardsVacuum_TIC
