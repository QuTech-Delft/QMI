"""Context managers for QMI RPC protocol contexts."""
from contextlib import contextmanager
from typing import Iterator, Protocol, TypeVar
import warnings

from qmi.core.pubsub import QMI_SignalReceiver, QMI_SignalSubscriber


class StartStoppable(Protocol):
    """Protocol for start_stop context class"""
    def start(self, *args, **kwargs) -> None: ...
    def stop(self) -> None: ...


class StartStopJoinable(StartStoppable, Protocol):
    """Protocol for start_stop context class, but has join as well."""
    def start(self, *args, **kwargs) -> None: ...
    def stop(self) -> None: ...
    def join(self) -> None: ...


class OpenClosable(Protocol):
    """Protocol for open_close context class. None of the `open` implementations take arguments."""
    def open(self) -> None: ...
    def close(self) -> None: ...


class LockUnlockable(Protocol):
    """Protocol for lock_unlock context class. None of the `lock` implementations take arguments."""
    def lock(self, *args, **kwargs) -> None: ...
    def unlock(self, *args, **kwargs) -> None: ...


_SS = TypeVar("_SS", bound=StartStoppable)
_SSJ = TypeVar("_SSJ", bound=StartStopJoinable)
_OC = TypeVar("_OC", bound=OpenClosable)
_LU = TypeVar("_LU", bound=LockUnlockable)


@contextmanager
def start_stop(thing: _SS, *args, **kwargs) -> Iterator[_SS]:
    thing.start(*args, **kwargs)
    try:
        yield thing
    finally:
        thing.stop()


@contextmanager
def start_stop_join(thing: _SSJ, *args, **kwargs) -> Iterator[_SSJ]:
    warnings.warn(
        "This context manager is obsoleted. The tasks can now by managed directly by their own context manager "
        "by calling `with qmi.make_task('task_name', TaskClass, args, kwargs) as task: ...`.",
        DeprecationWarning,
        stacklevel=3
    )
    thing.start(*args, **kwargs)
    try:
        yield thing
    finally:
        thing.stop()
        thing.join()


@contextmanager
def open_close(thing: _OC) -> Iterator[_OC]:
    warnings.warn(
        "This context manager is obsoleted. The instruments can now by managed directly by their own context manager "
        "by calling `with qmi.make_instrument('instr_name', InstrClass, args, kwargs) as instr: ...`.",
        DeprecationWarning,
        stacklevel=3
    )
    thing.open()
    try:
        yield thing
    finally:
        thing.close()


@contextmanager
def lock_unlock(thing: _LU, *args, **kwargs) -> Iterator[_LU]:
    thing.lock(*args, **kwargs)
    try:
        yield thing
    finally:
        thing.unlock()


@contextmanager
def subscribe_unsubscribe(
        signal: QMI_SignalSubscriber, receiver: QMI_SignalReceiver | None
    ) -> Iterator[QMI_SignalReceiver]:
    receiver = receiver if receiver is not None else QMI_SignalReceiver()
    signal.subscribe(receiver)
    try:
        yield receiver
    finally:
        signal.unsubscribe(receiver)

