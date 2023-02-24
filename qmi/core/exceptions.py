"""
Exception definitions for the QMI framework.
"""


class QMI_Exception(Exception):
    """Base class for QMI exceptions."""


class QMI_RuntimeException(QMI_Exception):
    """Raised when an error occurs that does not fit in any other category."""


class QMI_ApplicationException(QMI_Exception):
    """Raised in top-level application code to exit with an error message."""


#
# Exceptions typically caused by incorrect use of QMI:
#

class QMI_UsageException(QMI_Exception):
    """Raised when the library is used in a way that was not intended.

    Examples:
     - Bad data type of argument
     - Invalid order of operations
     - Use without initialization
    """


class QMI_DuplicateNameException(QMI_Exception):
    """Raised when a duplicate name is assigned while a unique name is required."""


class QMI_UnknownNameException(QMI_Exception):
    """Raised when an unknown name is used where an assigned name is required."""


class QMI_NoActiveContextException(QMI_UsageException):
    """Raised when an active default context is required while none exists."""


class QMI_InvalidOperationException(QMI_Exception):
    """Raised when attempting an operation which is not possible in the current state."""


class QMI_ConfigurationException(QMI_Exception):
    """Raised when an error occurs while processing configuration data."""


class QMI_WrongThreadException(QMI_Exception):
    """Raised when a function detects that it is called in a wrong thread."""


#
# Exceptions caused by interaction with instruments/hardware:
#

class QMI_InstrumentException(QMI_Exception):
    """Raised when an interaction with an instrument fails."""


class QMI_TimeoutException(QMI_Exception):
    """Raised when timeout occurs before a requested operation completes."""


class QMI_EndOfInputException(QMI_Exception):
    """Raised when a read operation can not complete because the end of the input is reached."""


class QMI_TransportDescriptorException(QMI_Exception):
    """Raised when an invalid transport descriptor is used."""


#
# Exceptions related to internal QMI functions:
#

class QMI_MessageDeliveryException(QMI_Exception):
    """Raised when a QMI message can not be delivered to its target."""


class QMI_RpcTimeoutException(QMI_Exception):
    """Raised when a remote procedure call fails to complete within the maximum duration."""


class QMI_UnknownRpcException(QMI_Exception):
    """Raised when an undefined RPC request occurs."""


class QMI_SignalSubscriptionException(QMI_Exception):
    """Raised when attempting to subscribe to an unavailable signal."""


#
# Task management related exceptions:
#

class QMI_TaskInitException(QMI_Exception):
    """An error occurred while instantiating the QMI_Task."""


class QMI_TaskRunException(QMI_Exception):
    """An error occurred while running the QMI_Task."""


class QMI_TaskStopException(QMI_Exception):
    """Raised to stop a sleeping task which has received a stop request."""
