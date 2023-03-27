"""A Python wrapper module to wrap around manufacturer provided library header file 'hhdefin.h'. The header file used
is from software version 3.0.0.4.
Please find the header file in the dedicated software package for the HydraHarp instrument at
https://www.picoquant.com/dl_software/HydraHarp400/HydraHarp400_SW_and_DLL_v3_0_0_4.zip"""
# This is generated code, do not edit by hand!
import ctypes


_hhlib_function_signatures = [
        ('HH_GetLibraryVersion', ctypes.c_int, [('vers', ctypes.POINTER(ctypes.c_char))]),
        ('HH_GetErrorString', ctypes.c_int, [('errstring', ctypes.POINTER(ctypes.c_char)), ('errcode', ctypes.c_int)]),
        ('HH_OpenDevice', ctypes.c_int, [('devidx', ctypes.c_int), ('serial', ctypes.POINTER(ctypes.c_char))]),
        ('HH_CloseDevice', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('HH_Initialize', ctypes.c_int, [('devidx', ctypes.c_int), ('mode', ctypes.c_int), ('refsource', ctypes.c_int)]),
        ('HH_GetHardwareInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('model', ctypes.POINTER(ctypes.c_char)), ('partno', ctypes.POINTER(ctypes.c_char)), ('version', ctypes.POINTER(ctypes.c_char))]),
        ('HH_GetSerialNumber', ctypes.c_int, [('devidx', ctypes.c_int), ('serial', ctypes.POINTER(ctypes.c_char))]),
        ('HH_GetFeatures', ctypes.c_int, [('devidx', ctypes.c_int), ('features', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetBaseResolution', ctypes.c_int, [('devidx', ctypes.c_int), ('resolution', ctypes.POINTER(ctypes.c_double)), ('binsteps', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetHardwareDebugInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('debuginfo', ctypes.POINTER(ctypes.c_char))]),
        ('HH_GetNumOfInputChannels', ctypes.c_int, [('devidx', ctypes.c_int), ('nchannels', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetNumOfModules', ctypes.c_int, [('devidx', ctypes.c_int), ('nummod', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetModuleInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('modidx', ctypes.c_int), ('modelcode', ctypes.POINTER(ctypes.c_int)), ('versioncode', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetModuleIndex', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('modidx', ctypes.POINTER(ctypes.c_int))]),
        ('HH_Calibrate', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('HH_SetSyncDiv', ctypes.c_int, [('devidx', ctypes.c_int), ('div', ctypes.c_int)]),
        ('HH_SetSyncCFD', ctypes.c_int, [('devidx', ctypes.c_int), ('level', ctypes.c_int), ('zc', ctypes.c_int)]),
        ('HH_SetSyncChannelOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('value', ctypes.c_int)]),
        ('HH_SetInputCFD', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('level', ctypes.c_int), ('zc', ctypes.c_int)]),
        ('HH_SetInputChannelOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('value', ctypes.c_int)]),
        ('HH_SetInputChannelEnable', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('enable', ctypes.c_int)]),
        ('HH_SetStopOverflow', ctypes.c_int, [('devidx', ctypes.c_int), ('stop_ovfl', ctypes.c_int), ('stopcount', ctypes.c_uint)]),
        ('HH_SetBinning', ctypes.c_int, [('devidx', ctypes.c_int), ('binning', ctypes.c_int)]),
        ('HH_SetOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('offset', ctypes.c_int)]),
        ('HH_SetHistoLen', ctypes.c_int, [('devidx', ctypes.c_int), ('lencode', ctypes.c_int), ('actuallen', ctypes.POINTER(ctypes.c_int))]),
        ('HH_SetMeasControl', ctypes.c_int, [('devidx', ctypes.c_int), ('control', ctypes.c_int), ('startedge', ctypes.c_int), ('stopedge', ctypes.c_int)]),
        ('HH_ClearHistMem', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('HH_StartMeas', ctypes.c_int, [('devidx', ctypes.c_int), ('tacq', ctypes.c_int)]),
        ('HH_StopMeas', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('HH_CTCStatus', ctypes.c_int, [('devidx', ctypes.c_int), ('ctcstatus', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetHistogram', ctypes.c_int, [('devidx', ctypes.c_int), ('chcount', ctypes.POINTER(ctypes.c_uint)), ('channel', ctypes.c_int), ('clear', ctypes.c_int)]),
        ('HH_GetResolution', ctypes.c_int, [('devidx', ctypes.c_int), ('resolution', ctypes.POINTER(ctypes.c_double))]),
        ('HH_GetSyncPeriod', ctypes.c_int, [('devidx', ctypes.c_int), ('period', ctypes.POINTER(ctypes.c_double))]),
        ('HH_GetSyncRate', ctypes.c_int, [('devidx', ctypes.c_int), ('syncrate', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetCountRate', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('cntrate', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetFlags', ctypes.c_int, [('devidx', ctypes.c_int), ('flags', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetElapsedMeasTime', ctypes.c_int, [('devidx', ctypes.c_int), ('elapsed', ctypes.POINTER(ctypes.c_double))]),
        ('HH_GetWarnings', ctypes.c_int, [('devidx', ctypes.c_int), ('warnings', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetWarningsText', ctypes.c_int, [('devidx', ctypes.c_int), ('text', ctypes.POINTER(ctypes.c_char)), ('warnings', ctypes.c_int)]),
        ('HH_SetMarkerHoldoffTime', ctypes.c_int, [('devidx', ctypes.c_int), ('holdofftime', ctypes.c_int)]),
        ('HH_SetMarkerEdges', ctypes.c_int, [('devidx', ctypes.c_int), ('me1', ctypes.c_int), ('me2', ctypes.c_int), ('me3', ctypes.c_int), ('me4', ctypes.c_int)]),
        ('HH_SetMarkerEnable', ctypes.c_int, [('devidx', ctypes.c_int), ('en1', ctypes.c_int), ('en2', ctypes.c_int), ('en3', ctypes.c_int), ('en4', ctypes.c_int)]),
        ('HH_ReadFiFo', ctypes.c_int, [('devidx', ctypes.c_int), ('buffer', ctypes.POINTER(ctypes.c_uint)), ('count', ctypes.c_int), ('nactual', ctypes.POINTER(ctypes.c_int))]),
        ('HH_GetContModeBlock', ctypes.c_int, [('devidx', ctypes.c_int), ('buffer', ctypes.c_void_p), ('nbytesreceived', ctypes.POINTER(ctypes.c_int))])
    ]
