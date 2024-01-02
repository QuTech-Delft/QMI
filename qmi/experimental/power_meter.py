"""
Module defining a generic power meter.
"""
from abc import ABC
from typing import Protocol, runtime_checkable

class QMI_PowerMeter_Mixin(ABC):
    """
    Mixin for a power meter.
    """
    def get_power(self) -> float:
        """
        Get the power measured by the power meter.

        Returns:
            measured power.
        """
        raise NotImplementedError()

@runtime_checkable
class QMI_PowerMeter_Protocol(Protocol):
    """
    Protocol for a power meter.
    """
    def get_power(self) -> float:
        """
        Get the power measured by the power meter.

        Returns:
            measured power.
        """
        raise NotImplementedError()