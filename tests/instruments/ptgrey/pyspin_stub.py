from enum import Enum

AcquisitionMode_Continuous = 0x1
AcquisitionMode_SingleFrame = 0x2
AcquisitionMode_MultiFrame = 0x3
AcquisitionMode_Invalid = 0xBEEFCAFE


class List:
    def __init__(self, cameras):
        ...

    def GetByIndex(self, index):
        ...

    def Clear(self):
        ...

    def GetSize(self):
        ...


class SystemPtr:
    def GetLibraryVersion(self):
        ...

    def GetCameras(self):
        ...


class System:
    def GetInstance(self):
        ...


class ImageEvent:
    ...


class ChunkPtr:
    def GetTimestamp(self):
        ...

    def GetGain(self):
        ...

    def GetBlackLevel(self):
        ...

    def GetExposureTime(self):
        ...


class ImagePtr:
    def GetWidth(self):
        ...

    def GetHeight(self):
        ...

    def GetXOffset(self):
        ...

    def GetYOffset(self):
        ...

    def GetPixelFormatName(self):
        ...

    def GetFrameID(self):
        ...

    def GetID(self):
        ...

    def GetChunkData(self):
        ...

    def GetNDArray(self):
        ...

    def Release(self):
        ...


class SpinnakerException(Exception):
    ...


def IsAvailable(thing):
    ...


def IsReadable(thing):
    ...


def IsWritable(thing):
    ...


def CCategoryPtr(node):
    ...


class CCategory:
    def GetFeatures(self):
        ...


class Feature:
    def GetName(self):
        ...


def CValuePtr(node):
    ...


class CValue:
    def __init__(self, thing):
        ...

    def ToString(self):
        ...


def CBooleanPtr(node):
    ...


class CBoolean:
    def GetValue(self):
        ...

    def SetValue(self, value):
        ...


class CEnumerationPtr:
    def __init__(self, node):
        ...

    def GetValue(self):
        ...

    def GetEntryByName(self, value):
        ...

    def SetIntValue(self, value):
        ...


def CIntegerPtr(node):
    ...


class CInteger:
    def GetValue(self):
        ...


class NodeMap:
    def GetNode(self, value):
        ...


class Entry:
    def GetSymbolic(self):
        ...

    def GetValue(self):
        ...


class CameraPtr:
    def Init(self):
        ...

    def DeInit(self):
        ...

    def BeginAcquisition(self):
        ...

    def EndAcquisition(self):
        ...

    def GetNodeMap(self):
        ...

    def GetNextImage(self):
        ...

    def RegisterEvent(self, event):
        ...

    def UnregisterEvent(self, event):
        ...

    def GetTLDeviceNodeMap(self):
        ...

    def IsStreaming(self):
        ...

    class DeviceReset:
        def Execute(self):
            ...

    class AcquisitionMode:
        def SetValue(self, value):
            ...

    class AcquisitionFrameRate:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class AcquisitionFrameCount:
        def SetValue(self, vlaue):
            ...

    class ChunkModeActive:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class GevTimestampTickFrequency:
        def GetValue(self):
            ...

    class ChunkSelector:
        def GetEntries(self):
            ...

        def SetIntValue(self, index):
            ...

    class ChunkEnable:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class Width:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class Height:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class OffsetX:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class OffsetY:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class Gain:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class BlackLevel:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class DeviceTemperature:
        def GetValue(self):
            ...

    class DeviceVendorName:
        def GetValue(self):
            ...

    class DeviceModelName:
        def GetValue(self):
            ...

    class DeviceSerialNumber:
        def GetValue(self):
            ...

    class DeviceVersion:
        def GetValue(self):
            ...

    class ExposureTime:
        def GetValue(self):
            ...

        def SetValue(self, value):
            ...

    class PixelFormat:
        def GetCurrentEntry(self):
            ...

    class ExposureAuto:
        def GetCurrentEntry(self):
            ...

    class GainAuto:
        def GetCurrentEntry(self):
            ...

    class ExposureMode:
        def GetCurrentEntry(self):
            ...

    class TLDevice:
        class GevDeviceIPAddress:
            def GetValue(self):
                ...

        class DeviceType:
            def GetCurrentEntry(self):
                ...

        class DeviceVendorName:
            def GetValue(self):
                ...

        class DeviceModelName:
            def GetValue(self):
                ...

        class DeviceSerialNumber:
            def GetValue(self):
                ...

        class DeviceVersion:
            def GetValue(self):
                ...
