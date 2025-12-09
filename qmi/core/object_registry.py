"""Debugging aid."""

import logging
import threading
import time
from collections import namedtuple
from typing import Any

_logger = logging.getLogger(__name__)

ObjectRegistration = namedtuple("ObjectRegistration", "oid, timestamp, obj_str, obj_repr, type_str, comment")


class ObjectRegistry:

    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._counter = 0
        self._registry: dict[int, ObjectRegistration] = {}

    def register(self, obj: Any, comment: str | None = None) -> int:
        timestamp = time.time()
        with self._mutex:
            oid = self._counter
            self._counter += 1
            registration = ObjectRegistration(oid, timestamp, str(obj), repr(obj), str(type(obj)), comment)
            self._registry[oid] = registration
        return oid

    def unregister(self, oid: int) -> None:
        err_flag = False
        with self._mutex:
            if oid in self._registry:
                del self._registry[oid]
            else:
                err_flag = True

        if err_flag:
            _logger.error(f"Attempt to unregister object id %i that is not registered.", oid)

    def report(self, force_summary_flag: bool = True) -> None:

        # Make a copy of the registry and counter.
        with self._mutex:
            registry = self._registry.copy()
            counter = self._counter

        if force_summary_flag or len(registry) > 0:
            num_past_objects = counter - len(registry)
            _logger.info(
                f"Number of objects currently in registry: %i (properly registered/unregistered: %i).",
                len(registry), num_past_objects
            )

        for registration in registry.values():
            _logger.info(f"registered object: {registration}")
