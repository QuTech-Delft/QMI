"""
Edwards Vacuum, TIC controller.

The qmi.instruments.edwards package provides support for:
- Turbo & Instrument Controller (TIC) models D397-21-000/D397-22-000.
"""
# Alternative, QMI naming convention approved name
from qmi.instruments.edwards.turbo_instrument_controller import Edwards_TurboInstrumentController as\
    EdwardsVacuum_TIC, EdwardsVacuum_TIC_StatusResponse, EdwardsVacuum_TIC_PumpStateResponse,\
    EdwardsVacuum_TIC_PumpSpeedResponse, EdwardsVacuum_TIC_PumpPowerResponse,\
    EdwardsVacuum_TIC_GaugePressureResponse, EdwardsVacuum_TIC_StateResponse, EdwardsVacuum_TIC_AlertId,\
    EdwardsVacuum_TIC_ErrorCode, EdwardsVacuum_TIC_GaugeState, EdwardsVacuum_TIC_Priority,\
    EdwardsVacuum_TIC_PumpState, EdwardsVacuum_TIC_State, EdwardsVacuum_TIC_SystemOnOffSetupConfigResponse
