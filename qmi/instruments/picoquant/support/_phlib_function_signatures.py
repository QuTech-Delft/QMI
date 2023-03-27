"""A Python wrapper module to wrap around manufacturer provided library header file 'phdefin.h'. The header file used
is from software version 3.0.0.3.
Please find the header file in the dedicated software package for the PicoHarp instrument at
https://www.picoquant.com/dl_software/PicoHarp300/PicoHarp300_SW_and_DLL_v3_0_0_3.zip"""
# This is generated code, do not edit by hand!
import ctypes


_phlib_function_signatures = [
        ('PH_GetLibraryVersion', ctypes.c_int, [('version', ctypes.POINTER(ctypes.c_char))]),
        ('PH_GetErrorString', ctypes.c_int, [('errstring', ctypes.POINTER(ctypes.c_char)), ('errcode', ctypes.c_int)]),
        ('PH_OpenDevice', ctypes.c_int, [('devidx', ctypes.c_int), ('serial', ctypes.POINTER(ctypes.c_char))]),
        ('PH_CloseDevice', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('PH_Initialize', ctypes.c_int, [('devidx', ctypes.c_int), ('mode', ctypes.c_int)]),
        ('PH_GetHardwareInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('model', ctypes.POINTER(ctypes.c_char)), ('partno', ctypes.POINTER(ctypes.c_char)), ('version', ctypes.POINTER(ctypes.c_char))]),
        ('PH_GetSerialNumber', ctypes.c_int, [('devidx', ctypes.c_int), ('serial', ctypes.POINTER(ctypes.c_char))]),
        ('PH_GetFeatures', ctypes.c_int, [('devidx', ctypes.c_int), ('features', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetBaseResolution', ctypes.c_int, [('devidx', ctypes.c_int), ('resolution', ctypes.POINTER(ctypes.c_double)), ('binsteps', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetHardwareDebugInfo', ctypes.c_int, [('devidx', ctypes.c_int), ('debuginfo', ctypes.POINTER(ctypes.c_char))]),
        ('PH_Calibrate', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('PH_SetInputCFD', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('level', ctypes.c_int), ('zc', ctypes.c_int)]),
        ('PH_SetSyncDiv', ctypes.c_int, [('devidx', ctypes.c_int), ('div', ctypes.c_int)]),
        ('PH_SetSyncOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('syncoffset', ctypes.c_int)]),
        ('PH_SetStopOverflow', ctypes.c_int, [('devidx', ctypes.c_int), ('stop_ovfl', ctypes.c_int), ('stopcount', ctypes.c_int)]),
        ('PH_SetBinning', ctypes.c_int, [('devidx', ctypes.c_int), ('binning', ctypes.c_int)]),
        ('PH_SetOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('offset', ctypes.c_int)]),
        ('PH_SetMultistopEnable', ctypes.c_int, [('devidx', ctypes.c_int), ('enable', ctypes.c_int)]),
        ('PH_ClearHistMem', ctypes.c_int, [('devidx', ctypes.c_int), ('block', ctypes.c_int)]),
        ('PH_StartMeas', ctypes.c_int, [('devidx', ctypes.c_int), ('tacq', ctypes.c_int)]),
        ('PH_StopMeas', ctypes.c_int, [('devidx', ctypes.c_int)]),
        ('PH_CTCStatus', ctypes.c_int, [('devidx', ctypes.c_int), ('ctcstatus', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetHistogram', ctypes.c_int, [('devidx', ctypes.c_int), ('chcount', ctypes.POINTER(ctypes.c_uint)), ('block', ctypes.c_int)]),
        ('PH_GetResolution', ctypes.c_int, [('devidx', ctypes.c_int), ('resolution', ctypes.POINTER(ctypes.c_double))]),
        ('PH_GetCountRate', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('rate', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetFlags', ctypes.c_int, [('devidx', ctypes.c_int), ('flags', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetElapsedMeasTime', ctypes.c_int, [('devidx', ctypes.c_int), ('elapsed', ctypes.POINTER(ctypes.c_double))]),
        ('PH_GetWarnings', ctypes.c_int, [('devidx', ctypes.c_int), ('warnings', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetWarningsText', ctypes.c_int, [('devidx', ctypes.c_int), ('text', ctypes.POINTER(ctypes.c_char)), ('warnings', ctypes.c_int)]),
        ('PH_SetMarkerEnable', ctypes.c_int, [('devidx', ctypes.c_int), ('en0', ctypes.c_int), ('en1', ctypes.c_int), ('en2', ctypes.c_int), ('en3', ctypes.c_int)]),
        ('PH_SetMarkerEdges', ctypes.c_int, [('devidx', ctypes.c_int), ('me0', ctypes.c_int), ('me1', ctypes.c_int), ('me2', ctypes.c_int), ('me3', ctypes.c_int)]),
        ('PH_SetMarkerHoldoffTime', ctypes.c_int, [('devidx', ctypes.c_int), ('holdofftime', ctypes.c_int)]),
        ('PH_ReadFiFo', ctypes.c_int, [('devidx', ctypes.c_int), ('buffer', ctypes.POINTER(ctypes.c_uint)), ('count', ctypes.c_int), ('nactual', ctypes.POINTER(ctypes.c_int))]),
        ('PH_GetRouterVersion', ctypes.c_int, [('devidx', ctypes.c_int), ('model', ctypes.POINTER(ctypes.c_char)), ('version', ctypes.POINTER(ctypes.c_char))]),
        ('PH_GetRoutingChannels', ctypes.c_int, [('devidx', ctypes.c_int), ('rtchannels', ctypes.POINTER(ctypes.c_int))]),
        ('PH_EnableRouting', ctypes.c_int, [('devidx', ctypes.c_int), ('enable', ctypes.c_int)]),
        ('PH_SetRoutingChannelOffset', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('offset', ctypes.c_int)]),
        ('PH_SetPHR800Input', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('level', ctypes.c_int), ('edge', ctypes.c_int)]),
        ('PH_SetPHR800CFD', ctypes.c_int, [('devidx', ctypes.c_int), ('channel', ctypes.c_int), ('level', ctypes.c_int), ('zc', ctypes.c_int)])
    ]
