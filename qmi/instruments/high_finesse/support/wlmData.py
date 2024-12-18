"""
© 2024 HighFinesse Laser and Electronic Systems GmbH, Tübingen, Germany

HighFinesse Laser and Electronic Systems GmbH (hereinafter referred to as
“HighFinesse”) hereby grants, free of charge, anyone who downloads the Python dll
loading functions “wlmData.py” and “wlmConst.py” (hereinafter referred to as
“software”) from the HighFinesse website at https://www.highfinesse-downloads.com/download/t0849yd8uzpj or who receives it in any other way from
HighFinesse, a non-exclusive, non-transferable and non-sublicensable right, unlimited in
time and place, to use the software in any way or form, whether known or unknown, now
or in the future. This includes in particular the right to edit, modify, present, demonstrate,
reproduce, publish, use, digitize, distribute, broadcast, exhibit, make publicly accessible
and exploit the software.

These rights are granted only on condition that the following requirements are met:
• Any copy of the source code of the software must retain these licence terms in its
entirety. Furthermore, any edits, modifications and other changes in the copy
compared to software originally provided by HighFinesse must be clearly and
comprehensibly marked within the source code as “modified, deviating from
original files provided by HighFinesse”.
• Any copy of the software in binary form must reproduce these licence terms in its
entirety in the documentation and/or other materials provided with or connected
to the copy. Furthermore, any edits, modifications and other changes in the copy
compared to software originally provided by HighFinesse must be clearly and
comprehensibly marked as “modified, deviating from original files provided by
HighFinesse” within the documentation and/or other materials provided with or
connected to the copy.

The law of the Federal Republic of Germany shall apply exclusively. The provisions of the
UN Convention on Contracts for the International Sale of Goods (CISG) are excluded.

The courts of the Federal Republic of Germany shall have exclusive international
jurisdiction for all disputes arising from or in connection with these License terms. Among
the courts of the Federal Republic of Germany, the court having jurisdiction over the place
of business of HighFinesse shall have exclusive local jurisdiction for all disputes arising
from or in connection with these Licence terms.

HighFinesse would like to point out that the software is only a preliminary prototype and
not a final software product. HighFinesse is making this prototype available to the
experienced research community free of charge in order to promote research and enable
a critical discussion of the advantages, disadvantages and possible errors of the
software. The prototype is still under development at HighFinesse and has not yet
undergone any quality control. The software may therefore still contain errors, lack
essential functions or have other deficiencies. It should therefore only be used by highly
qualified software developers and should be extensively tested and checked before each
use in order to rule out errors and avoid any damage.

HighFinesse would be grateful for any information on errors and any suggestions for
improvement sent to info@highfinesse.de.
"""
#
# wlmData API function bindings generated from wlmData.h
#

import ctypes
import os

dll = None

def LoadDLL(path):
    global dll
    dll = ctypes.WinDLL(path) if os.name == 'nt' else ctypes.CDLL(path)

# ***********  Functions for general usage  ****************************
    # intptr_t Instantiate(int32_t RFC, int32_t Mode, intptr_t P1, int32_t P2)
    dll.Instantiate.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_int32]
    dll.Instantiate.restype = ctypes.c_void_p


    # void CallbackProc(int32_t Mode, int32_t IntVal, double DblVal)

    # void CallbackProcEx(int32_t Ver, int32_t Mode, int32_t IntVal, double DblVal, int32_t Res1)

    # int32_t WaitForWLMEvent(int32_t* Mode, int32_t* IntVal, double* DblVal)
    dll.WaitForWLMEvent.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double)]
    dll.WaitForWLMEvent.restype = ctypes.c_int32

    # int32_t WaitForWLMEventEx(int32_t* Ver, int32_t* Mode, int32_t* IntVal, double* DblVal, int32_t* Res1)
    dll.WaitForWLMEventEx.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32)]
    dll.WaitForWLMEventEx.restype = ctypes.c_int32

    # int32_t WaitForNextWLMEvent(int32_t* Mode, int32_t* IntVal, double* DblVal)
    dll.WaitForNextWLMEvent.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double)]
    dll.WaitForNextWLMEvent.restype = ctypes.c_int32

    # int32_t WaitForNextWLMEventEx(int32_t* Ver, int32_t* Mode, int32_t* IntVal, double* DblVal, int32_t* Res1)
    dll.WaitForNextWLMEventEx.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32)]
    dll.WaitForNextWLMEventEx.restype = ctypes.c_int32
    
    # void ClearWLMEvents(void)
    dll.ClearWLMEvents.argtypes = []
    dll.ClearWLMEvents.restype = None


    # int32_t ControlWLM(int32_t Action, intptr_t App, int32_t Ver)
    dll.ControlWLM.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_int32]
    dll.ControlWLM.restype = ctypes.c_int32

    # int32_t ControlWLMEx(int32_t Action, intptr_t App, int32_t Ver, int32_t Delay, int32_t Res)
    dll.ControlWLMEx.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.ControlWLMEx.restype = ctypes.c_int32

    # int64_t SynchroniseWLM(int32_t Mode, int64_t TS)
    dll.SynchroniseWLM.argtypes = [ctypes.c_int32, ctypes.c_int64]
    dll.SynchroniseWLM.restype = ctypes.c_int64

    # int32_t SetMeasurementDelayMethod(int32_t Mode, int32_t Delay)
    dll.SetMeasurementDelayMethod.argtypes = [ctypes.c_int32, ctypes.c_int32]
    dll.SetMeasurementDelayMethod.restype = ctypes.c_int32

    # int32_t SetWLMPriority(int32_t PPC, int32_t Res1, int32_t Res2)
    dll.SetWLMPriority.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetWLMPriority.restype = ctypes.c_int32

    # int32_t PresetWLMIndex(int32_t Ver)
    dll.PresetWLMIndex.argtypes = [ctypes.c_int32]
    dll.PresetWLMIndex.restype = ctypes.c_int32


    # int32_t GetWLMVersion(int32_t Ver)
    dll.GetWLMVersion.argtypes = [ctypes.c_int32]
    dll.GetWLMVersion.restype = ctypes.c_int32

    # int32_t GetWLMIndex(int32_t Ver)
    dll.GetWLMIndex.argtypes = [ctypes.c_int32]
    dll.GetWLMIndex.restype = ctypes.c_int32

    # int32_t GetWLMCount(int32_t V)
    dll.GetWLMCount.argtypes = [ctypes.c_int32]
    dll.GetWLMCount.restype = ctypes.c_int32

    # int32_t GetOptionInfo(int32_t Index, int32_t Detail, int64_t* I64Val, double* DblVal)
    dll.GetOptionInfo.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_double)]
    dll.GetOptionInfo.restype = ctypes.c_int32


# ***********  General Get... & Set...-functions  **********************
    # double GetWavelength(double WL)
    dll.GetWavelength.argtypes = [ctypes.c_double]
    dll.GetWavelength.restype = ctypes.c_double

    # double GetWavelength2(double WL2)
    dll.GetWavelength2.argtypes = [ctypes.c_double]
    dll.GetWavelength2.restype = ctypes.c_double

    # double GetWavelengthNum(int32_t num, double WL)
    dll.GetWavelengthNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetWavelengthNum.restype = ctypes.c_double

    # double GetCalWavelength(int32_t ba, double WL)
    dll.GetCalWavelength.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetCalWavelength.restype = ctypes.c_double

    # double GetCalibrationEffect(double CE)
    dll.GetCalibrationEffect.argtypes = [ctypes.c_double]
    dll.GetCalibrationEffect.restype = ctypes.c_double

    # double GetFrequency(double F)
    dll.GetFrequency.argtypes = [ctypes.c_double]
    dll.GetFrequency.restype = ctypes.c_double

    # double GetFrequency2(double F2)
    dll.GetFrequency2.argtypes = [ctypes.c_double]
    dll.GetFrequency2.restype = ctypes.c_double

    # double GetFrequencyNum(int32_t num, double F)
    dll.GetFrequencyNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetFrequencyNum.restype = ctypes.c_double

    # double GetLinewidth(int32_t Index, double LW)
    dll.GetLinewidth.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetLinewidth.restype = ctypes.c_double

    # double GetLinewidthNum(int32_t num, double LW)
    dll.GetLinewidthNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetLinewidthNum.restype = ctypes.c_double

    # double GetDistance(double D)
    dll.GetDistance.argtypes = [ctypes.c_double]
    dll.GetDistance.restype = ctypes.c_double

    # double GetAnalogIn(double AI)
    dll.GetAnalogIn.argtypes = [ctypes.c_double]
    dll.GetAnalogIn.restype = ctypes.c_double

    # double GetMultimodeInfo(int32_t num, int32_t type, int32_t mode, double* Val)
    dll.GetMultimodeInfo.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_double)]
    dll.GetMultimodeInfo.restype = ctypes.c_double

    # double GetTemperature(double T)
    dll.GetTemperature.argtypes = [ctypes.c_double]
    dll.GetTemperature.restype = ctypes.c_double

    # int32_t SetTemperature(double T)
    dll.SetTemperature.argtypes = [ctypes.c_double]
    dll.SetTemperature.restype = ctypes.c_int32

    # double GetPressure(double P)
    dll.GetPressure.argtypes = [ctypes.c_double]
    dll.GetPressure.restype = ctypes.c_double

    # int32_t SetPressure(int32_t Mode, double P)
    dll.SetPressure.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.SetPressure.restype = ctypes.c_int32

    # int32_t GetAirParameters(int32_t Mode, int32_t* State, double* Val)
    dll.GetAirParameters.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double)]
    dll.GetAirParameters.restype = ctypes.c_int32

    # int32_t SetAirParameters(int32_t Mode, int32_t State, double Val)
    dll.SetAirParameters.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double]
    dll.SetAirParameters.restype = ctypes.c_int32

    # double GetExternalInput(int32_t Index, double I)
    dll.GetExternalInput.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetExternalInput.restype = ctypes.c_double

    # int32_t SetExternalInput(int32_t Index, double I)
    dll.SetExternalInput.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.SetExternalInput.restype = ctypes.c_int32

    # int32_t GetExtraSetting(int32_t Index, int32_t* lGet, double* dGet, char* sGet)
    dll.GetExtraSetting.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_char)]
    dll.GetExtraSetting.restype = ctypes.c_int32

    # int32_t SetExtraSetting(int32_t Index, int32_t lSet, double dSet, char* sSet)
    dll.SetExtraSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.POINTER(ctypes.c_char)]
    dll.SetExtraSetting.restype = ctypes.c_int32


    # uint16_t GetExposure(uint16_t E)
    dll.GetExposure.argtypes = [ctypes.c_uint16]
    dll.GetExposure.restype = ctypes.c_uint16

    # int32_t SetExposure(uint16_t E)
    dll.SetExposure.argtypes = [ctypes.c_uint16]
    dll.SetExposure.restype = ctypes.c_int32

    # uint16_t GetExposure2(uint16_t E2)
    dll.GetExposure2.argtypes = [ctypes.c_uint16]
    dll.GetExposure2.restype = ctypes.c_uint16

    # int32_t SetExposure2(uint16_t E2)
    dll.SetExposure2.argtypes = [ctypes.c_uint16]
    dll.SetExposure2.restype = ctypes.c_int32

    # int32_t GetExposureNum(int32_t num, int32_t arr, int32_t E)
    dll.GetExposureNum.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.GetExposureNum.restype = ctypes.c_int32

    # int32_t SetExposureNum(int32_t num, int32_t arr, int32_t E)
    dll.SetExposureNum.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetExposureNum.restype = ctypes.c_int32

    # double GetExposureNumEx(int32_t num, int32_t arr, double E)
    dll.GetExposureNumEx.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double]
    dll.GetExposureNumEx.restype = ctypes.c_double

    # int32_t SetExposureNumEx(int32_t num, int32_t arr, double E)
    dll.SetExposureNumEx.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double]
    dll.SetExposureNumEx.restype = ctypes.c_int32

    # bool GetExposureMode(bool EM)
    dll.GetExposureMode.argtypes = [ctypes.c_bool]
    dll.GetExposureMode.restype = ctypes.c_bool

    # int32_t SetExposureMode(bool EM)
    dll.SetExposureMode.argtypes = [ctypes.c_bool]
    dll.SetExposureMode.restype = ctypes.c_int32

    # int32_t GetExposureModeNum(int32_t num, bool EM)
    dll.GetExposureModeNum.argtypes = [ctypes.c_int32, ctypes.c_bool]
    dll.GetExposureModeNum.restype = ctypes.c_int32

    # int32_t SetExposureModeNum(int32_t num, bool EM)
    dll.SetExposureModeNum.argtypes = [ctypes.c_int32, ctypes.c_bool]
    dll.SetExposureModeNum.restype = ctypes.c_int32

    # int32_t GetExposureRange(int32_t ER)
    dll.GetExposureRange.argtypes = [ctypes.c_int32]
    dll.GetExposureRange.restype = ctypes.c_int32

    # double GetExposureRangeEx(int32_t ER)
    dll.GetExposureRangeEx.argtypes = [ctypes.c_int32]
    dll.GetExposureRangeEx.restype = ctypes.c_double

    # int32_t GetAutoExposureSetting(int32_t num, int32_t AES, int32_t* iVal, double* dVal)
    dll.GetAutoExposureSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double)]
    dll.GetAutoExposureSetting.restype = ctypes.c_int32

    # int32_t SetAutoExposureSetting(int32_t num, int32_t AES, int32_t iVal, double dVal)
    dll.SetAutoExposureSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double]
    dll.SetAutoExposureSetting.restype = ctypes.c_int32


    # uint16_t GetResultMode(uint16_t RM)
    dll.GetResultMode.argtypes = [ctypes.c_uint16]
    dll.GetResultMode.restype = ctypes.c_uint16

    # int32_t SetResultMode(uint16_t RM)
    dll.SetResultMode.argtypes = [ctypes.c_uint16]
    dll.SetResultMode.restype = ctypes.c_int32

    # uint16_t GetRange(uint16_t R)
    dll.GetRange.argtypes = [ctypes.c_uint16]
    dll.GetRange.restype = ctypes.c_uint16

    # int32_t SetRange(uint16_t R)
    dll.SetRange.argtypes = [ctypes.c_uint16]
    dll.SetRange.restype = ctypes.c_int32

    # uint16_t GetPulseMode(uint16_t PM)
    dll.GetPulseMode.argtypes = [ctypes.c_uint16]
    dll.GetPulseMode.restype = ctypes.c_uint16

    # int32_t SetPulseMode(uint16_t PM)
    dll.SetPulseMode.argtypes = [ctypes.c_uint16]
    dll.SetPulseMode.restype = ctypes.c_int32

    # int32_t GetPulseDelay(int32_t PD)
    dll.GetPulseDelay.argtypes = [ctypes.c_int32]
    dll.GetPulseDelay.restype = ctypes.c_int32

    # int32_t SetPulseDelay(int32_t PD)
    dll.SetPulseDelay.argtypes = [ctypes.c_int32]
    dll.SetPulseDelay.restype = ctypes.c_int32

    # uint16_t GetWideMode(uint16_t WM)
    dll.GetWideMode.argtypes = [ctypes.c_uint16]
    dll.GetWideMode.restype = ctypes.c_uint16

    # int32_t SetWideMode(uint16_t WM)
    dll.SetWideMode.argtypes = [ctypes.c_uint16]
    dll.SetWideMode.restype = ctypes.c_int32


    # int32_t GetDisplayMode(int32_t DM)
    dll.GetDisplayMode.argtypes = [ctypes.c_int32]
    dll.GetDisplayMode.restype = ctypes.c_int32

    # int32_t SetDisplayMode(int32_t DM)
    dll.SetDisplayMode.argtypes = [ctypes.c_int32]
    dll.SetDisplayMode.restype = ctypes.c_int32

    # bool GetFastMode(bool FM)
    dll.GetFastMode.argtypes = [ctypes.c_bool]
    dll.GetFastMode.restype = ctypes.c_bool

    # int32_t SetFastMode(bool FM)
    dll.SetFastMode.argtypes = [ctypes.c_bool]
    dll.SetFastMode.restype = ctypes.c_int32


    # bool GetLinewidthMode(bool LM)
    dll.GetLinewidthMode.argtypes = [ctypes.c_bool]
    dll.GetLinewidthMode.restype = ctypes.c_bool

    # int32_t SetLinewidthMode(bool LM)
    dll.SetLinewidthMode.argtypes = [ctypes.c_bool]
    dll.SetLinewidthMode.restype = ctypes.c_int32


    # bool GetDistanceMode(bool DM)
    dll.GetDistanceMode.argtypes = [ctypes.c_bool]
    dll.GetDistanceMode.restype = ctypes.c_bool

    # int32_t SetDistanceMode(bool DM)
    dll.SetDistanceMode.argtypes = [ctypes.c_bool]
    dll.SetDistanceMode.restype = ctypes.c_int32


    # int32_t GetSwitcherMode(int32_t SM)
    dll.GetSwitcherMode.argtypes = [ctypes.c_int32]
    dll.GetSwitcherMode.restype = ctypes.c_int32

    # int32_t SetSwitcherMode(int32_t SM)
    dll.SetSwitcherMode.argtypes = [ctypes.c_int32]
    dll.SetSwitcherMode.restype = ctypes.c_int32

    # int32_t GetSwitcherChannel(int32_t CH)
    dll.GetSwitcherChannel.argtypes = [ctypes.c_int32]
    dll.GetSwitcherChannel.restype = ctypes.c_int32

    # int32_t SetSwitcherChannel(int32_t CH)
    dll.SetSwitcherChannel.argtypes = [ctypes.c_int32]
    dll.SetSwitcherChannel.restype = ctypes.c_int32

    # int32_t GetSwitcherSignalStates(int32_t Signal, int32_t* Use, int32_t* Show)
    dll.GetSwitcherSignalStates.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]
    dll.GetSwitcherSignalStates.restype = ctypes.c_int32

    # int32_t SetSwitcherSignalStates(int32_t Signal, int32_t Use, int32_t Show)
    dll.SetSwitcherSignalStates.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetSwitcherSignalStates.restype = ctypes.c_int32

    # int32_t SetSwitcherSignal(int32_t Signal, int32_t Use, int32_t Show)
    dll.SetSwitcherSignal.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetSwitcherSignal.restype = ctypes.c_int32


    # int32_t GetAutoCalMode(int32_t ACM)
    dll.GetAutoCalMode.argtypes = [ctypes.c_int32]
    dll.GetAutoCalMode.restype = ctypes.c_int32

    # int32_t SetAutoCalMode(int32_t ACM)
    dll.SetAutoCalMode.argtypes = [ctypes.c_int32]
    dll.SetAutoCalMode.restype = ctypes.c_int32

    # int32_t GetAutoCalSetting(int32_t ACS, int32_t* val, int32_t Res1, int32_t* Res2)
    dll.GetAutoCalSetting.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)]
    dll.GetAutoCalSetting.restype = ctypes.c_int32

    # int32_t SetAutoCalSetting(int32_t ACS, int32_t val, int32_t Res1, int32_t Res2)
    dll.SetAutoCalSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetAutoCalSetting.restype = ctypes.c_int32


    # int32_t GetActiveChannel(int32_t Mode, int32_t* Port, int32_t Res1)
    dll.GetActiveChannel.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.c_int32]
    dll.GetActiveChannel.restype = ctypes.c_int32

    # int32_t SetActiveChannel(int32_t Mode, int32_t Port, int32_t CH, int32_t Res1)
    dll.SetActiveChannel.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetActiveChannel.restype = ctypes.c_int32

    # int32_t GetChannelsCount(int32_t C)
    dll.GetChannelsCount.argtypes = [ctypes.c_int32]
    dll.GetChannelsCount.restype = ctypes.c_int32


    # uint16_t GetOperationState(uint16_t OS)
    dll.GetOperationState.argtypes = [ctypes.c_uint16]
    dll.GetOperationState.restype = ctypes.c_uint16

    # int32_t Operation(uint16_t Op)
    dll.Operation.argtypes = [ctypes.c_uint16]
    dll.Operation.restype = ctypes.c_int32

    # int32_t SetOperationFile(char* lpFile)
    dll.SetOperationFile.argtypes = [ctypes.POINTER(ctypes.c_char)]
    dll.SetOperationFile.restype = ctypes.c_int32

    # int32_t Calibration(int32_t Type, int32_t Unit, double Value, int32_t Channel)
    dll.Calibration.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_int32]
    dll.Calibration.restype = ctypes.c_int32

    # int32_t RaiseMeasurementEvent(int32_t Mode)
    dll.RaiseMeasurementEvent.argtypes = [ctypes.c_int32]
    dll.RaiseMeasurementEvent.restype = ctypes.c_int32

    # int32_t TriggerMeasurement(int32_t Action)
    dll.TriggerMeasurement.argtypes = [ctypes.c_int32]
    dll.TriggerMeasurement.restype = ctypes.c_int32

    # int32_t GetTriggerState(int32_t TS)
    dll.GetTriggerState.argtypes = [ctypes.c_int32]
    dll.GetTriggerState.restype = ctypes.c_int32

    # int32_t GetInterval(int32_t I)
    dll.GetInterval.argtypes = [ctypes.c_int32]
    dll.GetInterval.restype = ctypes.c_int32

    # int32_t SetInterval(int32_t I)
    dll.SetInterval.argtypes = [ctypes.c_int32]
    dll.SetInterval.restype = ctypes.c_int32

    # bool GetIntervalMode(bool IM)
    dll.GetIntervalMode.argtypes = [ctypes.c_bool]
    dll.GetIntervalMode.restype = ctypes.c_bool

    # int32_t SetIntervalMode(bool IM)
    dll.SetIntervalMode.argtypes = [ctypes.c_bool]
    dll.SetIntervalMode.restype = ctypes.c_int32

    # double GetInternalTriggerRate(double TR)
    dll.GetInternalTriggerRate.argtypes = [ctypes.c_double]
    dll.GetInternalTriggerRate.restype = ctypes.c_double

    # int32_t SetInternalTriggerRate(double TR)
    dll.SetInternalTriggerRate.argtypes = [ctypes.c_double]
    dll.SetInternalTriggerRate.restype = ctypes.c_int32

    # int32_t GetBackground(int32_t BG)
    dll.GetBackground.argtypes = [ctypes.c_int32]
    dll.GetBackground.restype = ctypes.c_int32

    # int32_t SetBackground(int32_t BG)
    dll.SetBackground.argtypes = [ctypes.c_int32]
    dll.SetBackground.restype = ctypes.c_int32

    # int32_t GetAveragingSettingNum(int32_t num, int32_t AS, int32_t Value)
    dll.GetAveragingSettingNum.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.GetAveragingSettingNum.restype = ctypes.c_int32

    # int32_t SetAveragingSettingNum(int32_t num, int32_t AS, int32_t Value)
    dll.SetAveragingSettingNum.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.SetAveragingSettingNum.restype = ctypes.c_int32


    # bool GetLinkState(bool LS)
    dll.GetLinkState.argtypes = [ctypes.c_bool]
    dll.GetLinkState.restype = ctypes.c_bool

    # int32_t SetLinkState(bool LS)
    dll.SetLinkState.argtypes = [ctypes.c_bool]
    dll.SetLinkState.restype = ctypes.c_int32

    # void LinkSettingsDlg(void)
    dll.LinkSettingsDlg.argtypes = []
    dll.LinkSettingsDlg.restype = None


    # int32_t GetPatternItemSize(int32_t Index)
    dll.GetPatternItemSize.argtypes = [ctypes.c_int32]
    dll.GetPatternItemSize.restype = ctypes.c_int32

    # int32_t GetPatternItemCount(int32_t Index)
    dll.GetPatternItemCount.argtypes = [ctypes.c_int32]
    dll.GetPatternItemCount.restype = ctypes.c_int32

    # intptr_t GetPattern(int32_t Index)
    dll.GetPattern.argtypes = [ctypes.c_int32]
    dll.GetPattern.restype = ctypes.c_void_p

    # intptr_t GetPatternNum(int32_t Chn, int32_t Index)
    dll.GetPatternNum.argtypes = [ctypes.c_int32, ctypes.c_int32]
    dll.GetPatternNum.restype = ctypes.c_void_p

    # int32_t GetPatternData(int32_t Index, intptr_t PArray)
    dll.GetPatternData.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    dll.GetPatternData.restype = ctypes.c_int32

    # int32_t GetPatternDataNum(int32_t Chn, int32_t Index, intptr_t PArray)
    dll.GetPatternDataNum.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    dll.GetPatternDataNum.restype = ctypes.c_int32

    # int32_t SetPattern(int32_t Index, int32_t iEnable)
    dll.SetPattern.argtypes = [ctypes.c_int32, ctypes.c_int32]
    dll.SetPattern.restype = ctypes.c_int32

    # int32_t SetPatternData(int32_t Index, intptr_t PArray)
    dll.SetPatternData.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    dll.SetPatternData.restype = ctypes.c_int32


    # bool GetAnalysisMode(bool AM)
    dll.GetAnalysisMode.argtypes = [ctypes.c_bool]
    dll.GetAnalysisMode.restype = ctypes.c_bool

    # int32_t SetAnalysisMode(bool AM)
    dll.SetAnalysisMode.argtypes = [ctypes.c_bool]
    dll.SetAnalysisMode.restype = ctypes.c_int32

    # int32_t GetAnalysisItemSize(int32_t Index)
    dll.GetAnalysisItemSize.argtypes = [ctypes.c_int32]
    dll.GetAnalysisItemSize.restype = ctypes.c_int32

    # int32_t GetAnalysisItemCount(int32_t Index)
    dll.GetAnalysisItemCount.argtypes = [ctypes.c_int32]
    dll.GetAnalysisItemCount.restype = ctypes.c_int32

    # intptr_t GetAnalysis(int32_t Index)
    dll.GetAnalysis.argtypes = [ctypes.c_int32]
    dll.GetAnalysis.restype = ctypes.c_void_p

    # int32_t GetAnalysisData(int32_t Index, intptr_t PArray)
    dll.GetAnalysisData.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    dll.GetAnalysisData.restype = ctypes.c_int32

    # int32_t SetAnalysis(int32_t Index, int32_t iEnable)
    dll.SetAnalysis.argtypes = [ctypes.c_int32, ctypes.c_int32]
    dll.SetAnalysis.restype = ctypes.c_int32


    # int32_t GetMinPeak(int32_t M1)
    dll.GetMinPeak.argtypes = [ctypes.c_int32]
    dll.GetMinPeak.restype = ctypes.c_int32

    # int32_t GetMinPeak2(int32_t M2)
    dll.GetMinPeak2.argtypes = [ctypes.c_int32]
    dll.GetMinPeak2.restype = ctypes.c_int32

    # int32_t GetMaxPeak(int32_t X1)
    dll.GetMaxPeak.argtypes = [ctypes.c_int32]
    dll.GetMaxPeak.restype = ctypes.c_int32

    # int32_t GetMaxPeak2(int32_t X2)
    dll.GetMaxPeak2.argtypes = [ctypes.c_int32]
    dll.GetMaxPeak2.restype = ctypes.c_int32

    # int32_t GetAvgPeak(int32_t A1)
    dll.GetAvgPeak.argtypes = [ctypes.c_int32]
    dll.GetAvgPeak.restype = ctypes.c_int32

    # int32_t GetAvgPeak2(int32_t A2)
    dll.GetAvgPeak2.argtypes = [ctypes.c_int32]
    dll.GetAvgPeak2.restype = ctypes.c_int32

    # int32_t SetAvgPeak(int32_t PA)
    dll.SetAvgPeak.argtypes = [ctypes.c_int32]
    dll.SetAvgPeak.restype = ctypes.c_int32


    # int32_t GetAmplitudeNum(int32_t num, int32_t Index, int32_t A)
    dll.GetAmplitudeNum.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.GetAmplitudeNum.restype = ctypes.c_int32

    # double GetIntensityNum(int32_t num, double I)
    dll.GetIntensityNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetIntensityNum.restype = ctypes.c_double

    # double GetPowerNum(int32_t num, double P)
    dll.GetPowerNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetPowerNum.restype = ctypes.c_double


    # uint16_t GetDelay(uint16_t D)
    dll.GetDelay.argtypes = [ctypes.c_uint16]
    dll.GetDelay.restype = ctypes.c_uint16

    # int32_t SetDelay(uint16_t D)
    dll.SetDelay.argtypes = [ctypes.c_uint16]
    dll.SetDelay.restype = ctypes.c_int32

    # uint16_t GetShift(uint16_t S)
    dll.GetShift.argtypes = [ctypes.c_uint16]
    dll.GetShift.restype = ctypes.c_uint16

    # int32_t SetShift(uint16_t S)
    dll.SetShift.argtypes = [ctypes.c_uint16]
    dll.SetShift.restype = ctypes.c_int32

    # uint16_t GetShift2(uint16_t S2)
    dll.GetShift2.argtypes = [ctypes.c_uint16]
    dll.GetShift2.restype = ctypes.c_uint16

    # int32_t SetShift2(uint16_t S2)
    dll.SetShift2.argtypes = [ctypes.c_uint16]
    dll.SetShift2.restype = ctypes.c_int32

    # double GetGain(int32_t num, int32_t index, int32_t mode, double* Gain)
    dll.GetGain.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_double)]
    dll.GetGain.restype = ctypes.c_double

    # int32_t SetGain(int32_t num, int32_t index, int32_t mode, double Gain)
    dll.SetGain.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double]
    dll.SetGain.restype = ctypes.c_int32


# ***********  Deviation (Laser Control) and PID-functions  ************
    # bool GetDeviationMode(bool DM)
    dll.GetDeviationMode.argtypes = [ctypes.c_bool]
    dll.GetDeviationMode.restype = ctypes.c_bool

    # int32_t SetDeviationMode(bool DM)
    dll.SetDeviationMode.argtypes = [ctypes.c_bool]
    dll.SetDeviationMode.restype = ctypes.c_int32

    # double GetDeviationReference(double DR)
    dll.GetDeviationReference.argtypes = [ctypes.c_double]
    dll.GetDeviationReference.restype = ctypes.c_double

    # int32_t SetDeviationReference(double DR)
    dll.SetDeviationReference.argtypes = [ctypes.c_double]
    dll.SetDeviationReference.restype = ctypes.c_int32

    # int32_t GetDeviationSensitivity(int32_t DS)
    dll.GetDeviationSensitivity.argtypes = [ctypes.c_int32]
    dll.GetDeviationSensitivity.restype = ctypes.c_int32

    # int32_t SetDeviationSensitivity(int32_t DS)
    dll.SetDeviationSensitivity.argtypes = [ctypes.c_int32]
    dll.SetDeviationSensitivity.restype = ctypes.c_int32

    # double GetDeviationSignal(double DS)
    dll.GetDeviationSignal.argtypes = [ctypes.c_double]
    dll.GetDeviationSignal.restype = ctypes.c_double

    # double GetDeviationSignalNum(int32_t Port, double DS)
    dll.GetDeviationSignalNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.GetDeviationSignalNum.restype = ctypes.c_double

    # int32_t SetDeviationSignal(double DS)
    dll.SetDeviationSignal.argtypes = [ctypes.c_double]
    dll.SetDeviationSignal.restype = ctypes.c_int32

    # int32_t SetDeviationSignalNum(int32_t Port, double DS)
    dll.SetDeviationSignalNum.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.SetDeviationSignalNum.restype = ctypes.c_int32

    # double RaiseDeviationSignal(int32_t iType, double dSignal)
    dll.RaiseDeviationSignal.argtypes = [ctypes.c_int32, ctypes.c_double]
    dll.RaiseDeviationSignal.restype = ctypes.c_double


    # int32_t GetPIDCourse(char* PIDC)
    dll.GetPIDCourse.argtypes = [ctypes.POINTER(ctypes.c_char)]
    dll.GetPIDCourse.restype = ctypes.c_int32

    # int32_t SetPIDCourse(char* PIDC)
    dll.SetPIDCourse.argtypes = [ctypes.POINTER(ctypes.c_char)]
    dll.SetPIDCourse.restype = ctypes.c_int32

    # int32_t GetPIDCourseNum(int32_t Port, char* PIDC)
    dll.GetPIDCourseNum.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_char)]
    dll.GetPIDCourseNum.restype = ctypes.c_int32

    # int32_t SetPIDCourseNum(int32_t Port, char* PIDC)
    dll.SetPIDCourseNum.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_char)]
    dll.SetPIDCourseNum.restype = ctypes.c_int32

    # int32_t GetPIDSetting(int32_t PS, int32_t Port, int32_t* iSet, double* dSet)
    dll.GetPIDSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double)]
    dll.GetPIDSetting.restype = ctypes.c_int32

    # int32_t SetPIDSetting(int32_t PS, int32_t Port, int32_t iSet, double dSet)
    dll.SetPIDSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double]
    dll.SetPIDSetting.restype = ctypes.c_int32

    # int32_t GetLaserControlSetting(int32_t PS, int32_t Port, int32_t* iSet, double* dSet, char* sSet)
    dll.GetLaserControlSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_char)]
    dll.GetLaserControlSetting.restype = ctypes.c_int32

    # int32_t SetLaserControlSetting(int32_t PS, int32_t Port, int32_t iSet, double dSet, char* sSet)
    dll.SetLaserControlSetting.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.POINTER(ctypes.c_char)]
    dll.SetLaserControlSetting.restype = ctypes.c_int32

    # int32_t ClearPIDHistory(int32_t Port)
    dll.ClearPIDHistory.argtypes = [ctypes.c_int32]
    dll.ClearPIDHistory.restype = ctypes.c_int32


# ***********  Other...-functions  *************************************
    # double ConvertUnit(double Val, int32_t uFrom, int32_t uTo)
    dll.ConvertUnit.argtypes = [ctypes.c_double, ctypes.c_int32, ctypes.c_int32]
    dll.ConvertUnit.restype = ctypes.c_double

    # double ConvertDeltaUnit(double Base, double Delta, int32_t uBase, int32_t uFrom, int32_t uTo)
    dll.ConvertDeltaUnit.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    dll.ConvertDeltaUnit.restype = ctypes.c_double


# ***********  Obsolete...-functions  **********************************
    # bool GetReduced(bool R)
    dll.GetReduced.argtypes = [ctypes.c_bool]
    dll.GetReduced.restype = ctypes.c_bool

    # int32_t SetReduced(bool R)
    dll.SetReduced.argtypes = [ctypes.c_bool]
    dll.SetReduced.restype = ctypes.c_int32

    # uint16_t GetScale(uint16_t S)
    dll.GetScale.argtypes = [ctypes.c_uint16]
    dll.GetScale.restype = ctypes.c_uint16

    # int32_t SetScale(uint16_t S)
    dll.SetScale.argtypes = [ctypes.c_uint16]
    dll.SetScale.restype = ctypes.c_int32


    return dll
