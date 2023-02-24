"""Mapping of error number to error message for Newport TLB670x laser controller."""
ERROR_MESSAGES = {
    -4: "NO PARAMETER SPECIFIED",
    -3: "LASER HEAD DISCONNECTED",
    -2: "COMMAND NOT VALID",
    0: "NO ERROR",
    # No error exists in the error buffer
    116: "SYNTAX ERROR",
    # This error is generated when the instrument receives a command that cannot be processed.
    # Some typical causes:
    # a. Using ASCII characters outside of a string constant that are not defined by the command language syntax.
    # b. Missing space between a set command and parameter.
    # c. Missing “?” character in case of query
    126: "WRONG NUM OF PARAMS",
    # This error is generated when the instrument is unable to process a command due to a mismatch between the number
    # of parameters received and the number of parameters required for the command.
    201: "VALUE OUT OF RANGE",
    # This error is generated when the instrument is unable to process a command because the parameter value received
    # is out of range of the acceptable values for the command.
    424: "TEC OVER TEMP",
    # The temperature control subsystem output has been turned OFF because the internal heatsink temperature has
    # exceeded safe levels. Please allow the unit to cool down, and reset the controller by turning it OFF and back ON.
    501: "LDD INTERLOCK FLT",
    # The Laser Diode Driver subsystem output has been turned OFF because of remote interlock (BNC connector on rear
    # panel) assertion.
    502: "LDD CURRENT LIMIT",
    # The Laser Diode Driver subsystem output has been turned OFF because of actual current exceeding the current limit
    # set point.
    514: "LDD MODE CHANGE",
    # The Laser Diode Driver subsystem output has been turned OFF because a mode change was commanded using
    # “SOURce:CPOWer” command or through front-panel interface.
    524: "LDD OVER TEMP",
    # The Laser Diode Driver subsystem output has been turned OFF because the internal heatsink temperature has
    # exceeded safe levels. Please allow the unit to cool down before turning the output ON again.
    803: "WAVE OVER TEMP",
    # The Wavelength control subsystem output has been turned OFF because the internal heatsink temperature
    # has exceeded safe levels. Please allow the unit to cool down before turning the wavelength tracking ON again.
    802: "WAVE FOLLOW ERROR",
    # Wavelength tracking has been turned OFF because the difference between actual wavelength and wavelength
    # setpoint exceeded 2nm. Please reduce the scan speed setting and turn wavelength tracking ON again.
    804: "PIEZO OVER TEMP",
    # The piezo control subsystem setpoint has been changed to 0% because the internal heatsink temperature has
    # exceeded safe levels. Please allow the unit to cool down before changing the piezo setpoint again.
    805: "CMD NOT SUPPORTED",
    # This error is generated when the command received by the controller is not supported by laser head connected to
    # it
    902: "KEY ENABLE OFF",
    # This error is generated when user tries to turn the Laser Diode Driver subsystem output ON with key switch in
    # OFF position.
    919: "LASER DISCONNECTED",
    # This error is generated when user tries to turn the Laser Diode Driver subsystem output ON without having a
    # laser head connected to the controller.
    920: "LASER EEPROM ERROR",
    # This error is generated when user tries to connect a laser head to the controller using an incompatible cable.
}
