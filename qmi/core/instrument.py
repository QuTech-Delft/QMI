"""Implementation of the QMI_Instrument class.
"""

import logging
import warnings
import typing
from typing import Optional, NamedTuple

from qmi.core.exceptions import QMI_InvalidOperationException
from qmi.core.rpc import QMI_RpcObject, rpc_method


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


# Named tuple to hold result of get_idn() method.
QMI_InstrumentIdentification = NamedTuple(
    'QMI_InstrumentIdentification',
    [('vendor', Optional[str]),
     ('model',  Optional[str]),
     ('serial', Optional[str]),
     ('version', Optional[str])])
#QMI_InstrumentIdentification.__doc__ = """Identification information provided by many types of instruments.
#
#Attributes:
#    vendor: Vendor name.
#    model: Instrument model name or number.
#    serial: Serial number.
#    version: Version or revision number.
#"""


class QMI_Instrument(QMI_RpcObject):
    """Base class for all instrument drivers.

    After an instance of `QMI_Instrument` is created, it must be explicitly
    opened by calling the `open()` method before any interaction with the
    instrument is possible.

    Subclasses implement drivers for specific instrument types.

    All drivers must implement methods `open()` and `close()`
    which initializes resp. tears down the connection to the instrument hardware.

    Subclasses should add methods to implement instrument-specific operations
    (measurements, getting and setting of parameters).

    Driver should implement a method `reset()` when applicable.
    This methods returns the instrument to its default settings.

    Drivers should implement a method `get_idn()` when applicable.
    This method returns an instance of `QMI_InstrumentIdentification`.
    """

    @classmethod
    def get_category(cls) -> Optional[str]:
        return "instrument"

    def __init__(self, context: 'qmi.core.context.QMI_Context', name: str) -> None:
        """Initialize the instrument driver instance and store parameters.

        The `__init__()` method should not yet attempt to access the instrument
        hardware. That should be done in the `open()` method.
        """
        super().__init__(context, name)
        self._is_open = False

    def release_rpc_object(self) -> None:
        """Give a warning if the instrument is removed while still open."""
        if self._is_open:
            warnings.warn("QMI_Instrument {} removed while still open".format(self._name), ResourceWarning)

    def _check_is_open(self) -> None:
        """Verify that the instrument is open, otherwise raise an exception."""
        if not self._is_open:
            _logger.error("Interaction with closed instrument %s not allowed", self._name)
            raise QMI_InvalidOperationException(
                "Operation not allowed on closed instrument {}".format(self._name))

    def _check_is_closed(self) -> None:
        """Verify that the instrument is closed, otherwise raise an exception."""
        if self._is_open:
            _logger.error("Interaction with open instrument %s not allowed", self._name)
            raise QMI_InvalidOperationException(
                "Operation not allowed on open instrument {}".format(self._name))

    @rpc_method
    def is_open(self) -> bool:
        """Return True if the instrument is open (ready for interaction)."""
        return self._is_open

    @rpc_method
    def open(self) -> None:
        """Connect to the instrument hardware.

        When this method returns, the instrument must be ready for interaction
        via calls to instrument-specific methods.

        Subclasses can extend this method to implement instrument-specific
        initialization. If they do, they should call ``super().open()`` as a last statement.
        """
        self._check_is_closed()
        self._is_open = True

    @rpc_method
    def close(self) -> None:
        """Close the connection to the instrument hardware and release
        associated resources.

        When this method returns, the instrument must not be used again
        unless it is first re-opened by calling the open() method.

        Subclasses can extend this method if they have specific resources to close.
        If they do, they should call ``super().close()`` as a last statement.
        """
        self._check_is_open()
        self._is_open = False


# Imports needed only for static typing.
if typing.TYPE_CHECKING:
    import qmi.core.context
