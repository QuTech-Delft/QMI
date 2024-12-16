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
# wlmData API constants generated from wlmData.h
#

# Instantiating Constants for 'RFC' parameter
cInstCheckForWLM = -1
cInstResetCalc = 0
cInstReturnMode = cInstResetCalc
cInstNotification = 1
cInstCopyPattern = 2
cInstCopyAnalysis = cInstCopyPattern
cInstControlWLM = 3
cInstControlDelay = 4
cInstControlPriority = 5

# Notification Constants for 'Mode' parameter
cNotifyInstallCallback = 0
cNotifyRemoveCallback = 1
cNotifyInstallWaitEvent = 2
cNotifyRemoveWaitEvent = 3
cNotifyInstallCallbackEx = 4
cNotifyInstallWaitEventEx = 5

# ResultError Constants of Set...-functions
ResERR_NoErr = 0
ResERR_WlmMissing = -1
ResERR_CouldNotSet = -2
ResERR_ParmOutOfRange = -3
ResERR_WlmOutOfResources = -4
ResERR_WlmInternalError = -5
ResERR_NotAvailable = -6
ResERR_WlmBusy = -7
ResERR_NotInMeasurementMode = -8
ResERR_OnlyInMeasurementMode = -9
ResERR_ChannelNotAvailable = -10
ResERR_ChannelTemporarilyNotAvailable = -11
ResERR_CalOptionNotAvailable = -12
ResERR_CalWavelengthOutOfRange = -13
ResERR_BadCalibrationSignal = -14
ResERR_UnitNotAvailable = -15
ResERR_FileNotFound = -16
ResERR_FileCreation = -17
ResERR_TriggerPending = -18
ResERR_TriggerWaiting = -19
ResERR_NoLegitimation = -20
ResERR_NoTCPLegitimation = -21
ResERR_NotInPulseMode = -22
ResERR_OnlyInPulseMode = -23
ResERR_NotInSwitchMode = -24
ResERR_OnlyInSwitchMode = -25
ResERR_TCPErr = -26

# Mode Constants for Callback-Export and WaitForWLMEvent-function
cmiResultMode = 1
cmiRange = 2
cmiPulse = 3
cmiPulseMode = cmiPulse
cmiWideLine = 4
cmiWideMode = cmiWideLine
cmiFast = 5
cmiFastMode = cmiFast
cmiExposureMode = 6
cmiExposureValue1 = 7
cmiExposureValue2 = 8
cmiDelay = 9
cmiShift = 10
cmiShift2 = 11
cmiReduce = 12
cmiReduced = cmiReduce
cmiScale = 13
cmiTemperature = 14
cmiLink = 15
cmiOperation = 16
cmiDisplayMode = 17
cmiPattern1a = 18
cmiPattern1b = 19
cmiPattern2a = 20
cmiPattern2b = 21
cmiMin1 = 22
cmiMax1 = 23
cmiMin2 = 24
cmiMax2 = 25
cmiNowTick = 26
cmiCallback = 27
cmiFrequency1 = 28
cmiFrequency2 = 29
cmiDLLDetach = 30
cmiVersion = 31
cmiAnalysisMode = 32
cmiDeviationMode = 33
cmiDeviationReference = 34
cmiDeviationSensitivity = 35
cmiAppearance = 36
cmiAutoCalMode = 37
cmiWavelength1 = 42
cmiWavelength2 = 43
cmiLinewidth = 44
cmiLinewidthMode = 45
cmiLinkDlg = 56
cmiAnalysis = 57
cmiAnalogIn = 66
cmiAnalogOut = 67
cmiDistance = 69
cmiWavelength3 = 90
cmiWavelength4 = 91
cmiWavelength5 = 92
cmiWavelength6 = 93
cmiWavelength7 = 94
cmiWavelength8 = 95
cmiVersion0 = cmiVersion
cmiVersion1 = 96
cmiPulseDelay = 99

cmiDLLAttach = 121
cmiSwitcherSignal = 123
cmiSwitcherMode = 124
cmiExposureValue11 = cmiExposureValue1
cmiExposureValue12 = 125
cmiExposureValue13 = 126
cmiExposureValue14 = 127
cmiExposureValue15 = 128
cmiExposureValue16 = 129
cmiExposureValue17 = 130
cmiExposureValue18 = 131
cmiExposureValue21 = cmiExposureValue2
cmiExposureValue22 = 132
cmiExposureValue23 = 133
cmiExposureValue24 = 134
cmiExposureValue25 = 135
cmiExposureValue26 = 136
cmiExposureValue27 = 137
cmiExposureValue28 = 138
cmiPatternAverage = 139
cmiPatternAvg1 = 140
cmiPatternAvg2 = 141
cmiAnalogOut1 = cmiAnalogOut
cmiAnalogOut2 = 142
cmiMin11 = cmiMin1
cmiMin12 = 146
cmiMin13 = 147
cmiMin14 = 148
cmiMin15 = 149
cmiMin16 = 150
cmiMin17 = 151
cmiMin18 = 152
cmiMin21 = cmiMin2
cmiMin22 = 153
cmiMin23 = 154
cmiMin24 = 155
cmiMin25 = 156
cmiMin26 = 157
cmiMin27 = 158
cmiMin28 = 159
cmiMax11 = cmiMax1
cmiMax12 = 160
cmiMax13 = 161
cmiMax14 = 162
cmiMax15 = 163
cmiMax16 = 164
cmiMax17 = 165
cmiMax18 = 166
cmiMax21 = cmiMax2
cmiMax22 = 167
cmiMax23 = 168
cmiMax24 = 169
cmiMax25 = 170
cmiMax26 = 171
cmiMax27 = 172
cmiMax28 = 173
cmiAvg11 = cmiPatternAvg1
cmiAvg12 = 174
cmiAvg13 = 175
cmiAvg14 = 176
cmiAvg15 = 177
cmiAvg16 = 178
cmiAvg17 = 179
cmiAvg18 = 180
cmiAvg21 = cmiPatternAvg2
cmiAvg22 = 181
cmiAvg23 = 182
cmiAvg24 = 183
cmiAvg25 = 184
cmiAvg26 = 185
cmiAvg27 = 186
cmiAvg28 = 187
cmiPatternAnalysisWritten = 202
cmiSwitcherChannel = 203
cmiStartCalibration = 235
cmiEndCalibration = 236
cmiAnalogOut3 = 237
cmiAnalogOut4 = 238
cmiAnalogOut5 = 239
cmiAnalogOut6 = 240
cmiAnalogOut7 = 241
cmiAnalogOut8 = 242
cmiIntensity = 251
cmiPower = 267
cmiActiveChannel = 300
cmiPIDCourse = 1030
cmiPIDUseTa = 1031
cmiPIDUseT = cmiPIDUseTa
cmiPID_T = 1033
cmiPID_P = 1034
cmiPID_I = 1035
cmiPID_D = 1036
cmiDeviationSensitivityDim = 1040
cmiDeviationSensitivityFactor = 1037
cmiDeviationPolarity = 1038
cmiDeviationSensitivityEx = 1039
cmiDeviationUnit = 1041
cmiDeviationBoundsMin = 1042
cmiDeviationBoundsMax = 1043
cmiDeviationRefMid = 1044
cmiDeviationRefAt = 1045
cmiPIDConstdt = 1059
cmiPID_dt = 1060
cmiPID_AutoClearHistory = 1061
cmiDeviationChannel = 1063
cmiPID_ClearHistoryOnRangeExceed = 1069
cmiAutoCalPeriod = 1120
cmiAutoCalUnit = 1121
cmiAutoCalChannel = 1122
cmiServerInitialized = 1124
cmiWavelength9 = 1130
cmiExposureValue19 = 1155
cmiExposureValue29 = 1180
cmiMin19 = 1205
cmiMin29 = 1230
cmiMax19 = 1255
cmiMax29 = 1280
cmiAvg19 = 1305
cmiAvg29 = 1330
cmiWavelength10 = 1355
cmiWavelength11 = 1356
cmiWavelength12 = 1357
cmiWavelength13 = 1358
cmiWavelength14 = 1359
cmiWavelength15 = 1360
cmiWavelength16 = 1361
cmiWavelength17 = 1362
cmiExternalInput = 1400
cmiPressure = 1465
cmiBackground = 1475
cmiDistanceMode = 1476
cmiInterval = 1477
cmiIntervalMode = 1478
cmiCalibrationEffect = 1480
cmiLinewidth1 = cmiLinewidth
cmiLinewidth2 = 1481
cmiLinewidth3 = 1482
cmiLinewidth4 = 1483
cmiLinewidth5 = 1484
cmiLinewidth6 = 1485
cmiLinewidth7 = 1486
cmiLinewidth8 = 1487
cmiLinewidth9 = 1488
cmiLinewidth10 = 1489
cmiLinewidth11 = 1490
cmiLinewidth12 = 1491
cmiLinewidth13 = 1492
cmiLinewidth14 = 1493
cmiLinewidth15 = 1494
cmiLinewidth16 = 1495
cmiLinewidth17 = 1496
cmiTriggerState = 1497
cmiDeviceAttach = 1501
cmiDeviceDetach = 1502
cmiTimePerMeasurement = 1514
cmiAutoExpoMin = 1517
cmiAutoExpoMax = 1518
cmiAutoExpoStepUp = 1519
cmiAutoExpoStepDown = 1520
cmiAutoExpoAtSaturation = 1521
cmiAutoExpoAtLowSignal = 1522
cmiAutoExpoFeedback = 1523
cmiAveragingCount = 1524
cmiAveragingMode = 1525
cmiAveragingType = 1526
cmiNowTick_d  = 1527
cmiAirMode = 1532
cmiAirTemperature = 1534
cmiAirPressure = 1535
cmiAirHumidity = 1536
cmiAirCO2 = 1651
cmiSubSnapshotID = 1539
cmiInternalTriggerRate = 1540
cmiGain11 = 1541
cmiGain12 = 1542
cmiGain13 = 1543
cmiGain14 = 1544
cmiGain15 = 1545
cmiGain16 = 1546
cmiGain17 = 1547
cmiGain18 = 1548
cmiGain19 = 1549
cmiGain110 = 1550
cmiGain111 = 1551
cmiGain112 = 1552
cmiGain113 = 1553
cmiGain114 = 1554
cmiGain115 = 1555
cmiGain116 = 1556
cmiGain117 = 1557
cmiGain21 = 1558
cmiGain22 = 1559
cmiGain23 = 1560
cmiGain24 = 1561
cmiGain25 = 1562
cmiGain26 = 1563
cmiGain27 = 1564
cmiGain28 = 1565
cmiGain29 = 1566
cmiGain210 = 1567
cmiGain211 = 1568
cmiGain212 = 1569
cmiGain213 = 1570
cmiGain214 = 1571
cmiGain215 = 1572
cmiGain216 = 1573
cmiGain217 = 1574
cmiGain31 = 1575
cmiGain32 = 1576
cmiGain33 = 1577
cmiGain34 = 1578
cmiGain35 = 1579
cmiGain36 = 1580
cmiGain37 = 1581
cmiGain38 = 1582
cmiGain39 = 1583
cmiGain310 = 1584
cmiGain311 = 1585
cmiGain312 = 1586
cmiGain313 = 1587
cmiGain314 = 1588
cmiGain315 = 1589
cmiGain316 = 1590
cmiGain317 = 1591
cmiGain41 = 1592
cmiGain42 = 1593
cmiGain43 = 1594
cmiGain44 = 1595
cmiGain45 = 1596
cmiGain46 = 1597
cmiGain47 = 1598
cmiGain48 = 1599
cmiGain49 = 1600
cmiGain410 = 1601
cmiGain411 = 1602
cmiGain412 = 1603
cmiGain413 = 1604
cmiGain414 = 1605
cmiGain415 = 1606
cmiGain416 = 1607
cmiGain417 = 1608
cmiMultimodeLevel1 = 1609
cmiMultimodeLevel2 = 1610
cmiMultimodeLevel3 = 1611
cmiMultimodeLevel4 = 1612
cmiMultimodeLevel5 = 1613
cmiMultimodeLevel6 = 1614
cmiMultimodeLevel7 = 1615
cmiMultimodeLevel8 = 1616
cmiMultimodeLevel9 = 1617
cmiMultimodeLevel10 = 1618
cmiMultimodeLevel11 = 1619
cmiMultimodeLevel12 = 1620
cmiMultimodeLevel13 = 1621
cmiMultimodeLevel14 = 1622
cmiMultimodeLevel15 = 1623
cmiMultimodeLevel16 = 1624
cmiMultimodeLevel17 = 1625
cmiFastBasedLinewidthAnalysis = 1630
cmiMultimodeCount1 = 1633
cmiMultimodeCount2 = 1634
cmiMultimodeCount3 = 1635
cmiMultimodeCount4 = 1636
cmiMultimodeCount5 = 1637
cmiMultimodeCount6 = 1638
cmiMultimodeCount7 = 1639
cmiMultimodeCount8 = 1640
cmiMultimodeCount9 = 1641
cmiMultimodeCount10 = 1642
cmiMultimodeCount11 = 1643
cmiMultimodeCount12 = 1644
cmiMultimodeCount13 = 1645
cmiMultimodeCount14 = 1646
cmiMultimodeCount15 = 1647
cmiMultimodeCount16 = 1648
cmiMultimodeCount17 = 1649

# Index constants for Get- and SetExtraSetting
cesCalculateLive = 4501

# WLM Control Mode Constants
cCtrlWLMShow = 1
cCtrlWLMHide = 2
cCtrlWLMExit = 3
cCtrlWLMStore = 4
cCtrlWLMCompare = 5
cCtrlWLMWait        = 0x0010
cCtrlWLMStartSilent = 0x0020
cCtrlWLMSilent      = 0x0040
cCtrlWLMStartDelay  = 0x0080

# Operation Mode Constants (for "Operation" and "GetOperationState" functions)
cStop = 0
cAdjustment = 1
cMeasurement = 2

# Base Operation Constants (To be used exclusively, only one of this list at a time,
# but still can be combined with "Measurement Action Addition Constants". See below.)
cCtrlStopAll = cStop
cCtrlStartAdjustment = cAdjustment
cCtrlStartMeasurement = cMeasurement
cCtrlStartRecord = 0x0004
cCtrlStartReplay = 0x0008
cCtrlStoreArray  = 0x0010
cCtrlLoadArray   = 0x0020

# Additional Operation Flag Constants (combine with "Base Operation Constants" above.)
cCtrlDontOverwrite = 0x0000

cCtrlFileGiven     = 0x0000


# Measurement Control Mode Constants
cCtrlMeasDelayRemove = 0
cCtrlMeasDelayGenerally = 1
cCtrlMeasDelayOnce = 2
cCtrlMeasDelayDenyUntil = 3
cCtrlMeasDelayIdleOnce = 4
cCtrlMeasDelayIdleEach = 5
cCtrlMeasDelayDefault = 6

# Measurement Triggering Action Constants
cCtrlMeasurementContinue = 0
cCtrlMeasurementInterrupt = 1
cCtrlMeasurementTriggerPoll = 2
cCtrlMeasurementTriggerSuccess = 3
cCtrlMeasurementEx = 0x0100

# ExposureRange Constants
cExpoMin = 0
cExpoMax = 1
cExpo2Min = 2
cExpo2Max = 3

# Amplitude Constants
cMin1 = 0
cMin2 = 1
cMax1 = 2
cMax2 = 3
cAvg1 = 4
cAvg2 = 5

# Measurement Range Constants
cRange_250_410 = 4
cRange_250_425 = 0
cRange_300_410 = 3
cRange_350_500 = 5
cRange_400_725 = 1
cRange_700_1100 = 2
cRange_800_1300 = 6
cRange_900_1500 = cRange_800_1300
cRange_1100_1700 = 7
cRange_1100_1800 = cRange_1100_1700

# Measurement Range Model Constants
cRangeModelOld = 65535
cRangeModelByOrder = 65534
cRangeModelByWavelength = 65533

# Unit Constants for Get-/SetResultMode, GetLinewidth, Convert... and Calibration
cReturnWavelengthVac = 0
cReturnWavelengthAir = 1
cReturnFrequency = 2
cReturnWavenumber = 3
cReturnPhotonEnergy = 4

# Power Unit Constants
cPower_muW = 0
cPower_dBm = 1

# Source Type Constants for Calibration
cHeNe633 = 0
cHeNe1152 = 0
cNeL = 1
cOther = 2
cFreeHeNe = 3
cSLR1530 = 5

# Unit Constants for Autocalibration
cACOnceOnStart = 0
cACMeasurements = 1
cACDays = 2
cACHours = 3
cACMinutes = 4

# ExposureRange Constants
cGetSync = 1
cSetSync = 2

# Pattern- and Analysis Constants
cPatternDisable = 0
cPatternEnable = 1
cAnalysisDisable = cPatternDisable
cAnalysisEnable = cPatternEnable

cSignal1Interferometers = 0
cSignal1WideInterferometer = 1
cSignal1Grating = 1
cSignal2Interferometers = 2
cSignal2WideInterferometer = 3
cSignalAnalysis = 4
cSignalAnalysisX = cSignalAnalysis
cSignalAnalysisY = cSignalAnalysis + 1

# State constants used with AutoExposureSetting functions
cJustStepDown = 0
cRestartAtMinimum = 1
cJustStepUp = 0
cDriveToLevel = 1
cConsiderFeedback = 1
cDontConsiderFeedback = 0

# Options identifiers used with GetOptionInfo
cInfoSwitch = 1
cInfoSwitchChannelsCount = 2
cInfoIntNeonLamp = 11
cInfo2ndExternalPort = 13
cInfoPID = 21
cInfoPIDPortsCount = 22
cInfoPIDPortType = 23
cInfoPIDPortRes = 24
cInfoPIDPortUMin = 25
cInfoPIDPortUMax = 26

# PID type constants
cInfoPIDPortTypeInt = 1
cInfoPIDPortTypeExt = 2
cInfoPIDPortTypeDigi = 3

# State constants used with AveragingSetting functions
cAvrgFloating = 1
cAvrgSucceeding = 2
cAvrgSimple = 0
cAvrgPattern = 1

# Return errorvalues of GetFrequency, GetWavelength, GetWLMVersion and GetOptionInfo
ErrNoValue = 0
ErrNoSignal = -1
ErrBadSignal = -2
ErrLowSignal = -3
ErrBigSignal = -4
ErrWlmMissing = -5
ErrNotAvailable = -6
InfNothingChanged = -7
ErrNoPulse = -8
ErrChannelNotAvailable = -10
ErrDiv0 = -13
ErrOutOfRange = -14
ErrUnitNotAvailable = -15
ErrTCPErr = -26
ErrParameterOutOfRange = -28
ErrMaxErr = ErrParameterOutOfRange

# Return errorvalues of GetTemperature and GetPressure
ErrTemperature = -1000
ErrTempNotMeasured = ErrTemperature + ErrNoValue
ErrTempNotAvailable = ErrTemperature + ErrNotAvailable
ErrTempWlmMissing = ErrTemperature + ErrWlmMissing

# Return errorvalues of GetGain
ErrGain = -1000
ErrGainNotAvailable        = ErrGain + ErrNotAvailable
ErrGainWlmMissing          = ErrGain + ErrWlmMissing
ErrGainChannelNotAvailable = ErrGain + ErrChannelNotAvailable
ErrGainOutOfRange          = ErrGain + ErrOutOfRange
ErrGainParameterOutOfRange = ErrGain + ErrParameterOutOfRange

# Return errorvalues of GetMultimodeInfo
ErrMMI = -1000
ErrMMINotAvailable        = ErrMMI + ErrNotAvailable
ErrMMIWlmMissing          = ErrMMI + ErrWlmMissing
ErrMMIChannelNotAvailable = ErrMMI + ErrChannelNotAvailable
ErrMMIOutOfRange          = ErrMMI + ErrOutOfRange
ErrMMIParameterOutOfRange = ErrMMI + ErrParameterOutOfRange

# Return errorvalues of GetDistance
# real errorvalues are ErrDistance combined with those of GetWavelength
ErrDistance = -1000000000
ErrDistanceNotAvailable = ErrDistance + ErrNotAvailable
ErrDistanceWlmMissing = ErrDistance + ErrWlmMissing

# Return flags of ControlWLMEx in combination with Show or Hide, Wait and Res = 1
flServerStarted           = 0x00000001
flErrDeviceNotFound       = 0x00000002
flErrDriverError          = 0x00000004
flErrUSBError             = 0x00000008
flErrUnknownDeviceError   = 0x00000010
flErrWrongSN              = 0x00000020
flErrUnknownSN            = 0x00000040
flErrTemperatureError     = 0x00000080
flErrPressureError        = 0x00000100
flErrCancelledManually    = 0x00000200
flErrWLMBusy              = 0x00000400
flErrUnknownError         = 0x00001000
flNoInstalledVersionFound = 0x00002000
flDesiredVersionNotFound  = 0x00004000
flErrFileNotFound         = 0x00008000
flErrParmOutOfRange       = 0x00010000
flErrCouldNotSet          = 0x00020000
flErrEEPROMFailed         = 0x00040000
flErrFileFailed           = 0x00080000
flDeviceDataNewer         = 0x00100000
flFileDataNewer           = 0x00200000
flErrDeviceVersionOld     = 0x00400000
flErrFileVersionOld       = 0x00800000
flDeviceStampNewer        = 0x01000000
flFileStampNewer          = 0x02000000

# Return file info flags of SetOperationFile
flFileInfoDoesntExist = 0x0000
flFileInfoExists      = 0x0001
flFileInfoCantWrite   = 0x0002
flFileInfoCantRead    = 0x0004
flFileInfoInvalidName = 0x0008
cFileParameterError = -1


