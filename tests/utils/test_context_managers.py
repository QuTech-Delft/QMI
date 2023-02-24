import unittest
from unittest.mock import Mock

from qmi.utils.context_managers import start_stop, start_stop_join, open_close, lock_unlock

from tests.utils import test_module


class StartStop:
    def start(self, *args, **kwargs) -> None: ...
    def stop(self) -> None: ...


class StartStopNoArgs:
    def start(self) -> None: ...
    def stop(self) -> None: ...


class StartStopJoin:
    def start(self, *args, **kwargs) -> None: ...
    def stop(self) -> None: ...
    def join(self) -> None: ...


class StartOnly:
    def start(self): ...


class OpenOnly:
    def open(self): ...


class LockOnly:
    def lock(self): ...


class TestContextManagers(unittest.TestCase):
    """Tests the context manager classes."""

    def test_with_start_stop(self) -> None:
        """Test that a right type of class has to be given for a `start_stop` context manager for it to work."""
        with start_stop(StartStop(), 'foo', bar='bar') as res1:
            # reveal_type(res1)  # Check if typed as StartStop
            pass

        with start_stop(StartStopNoArgs()) as res2:
            # reveal_type(res2)  # Check if typed as StartStopNoArgs
            pass

        with start_stop(test_module, "foo", bar=1) as res3:
            # reveal_type(res3)  # Check if typed as `test_module`
            pass

        with start_stop(Mock(), 'foo', bar='bar') as res4:
            # reveal_type(res4)  # Check if typed as Mock
            pass

        with self.assertRaises(AttributeError) as err1:
            with start_stop(object()):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with start_stop(StartOnly()):  # type: ignore
                pass

        res4.start.assert_called_once_with('foo', bar='bar')
        res4.stop.assert_called_once()

        self.assertTrue("'object' object has no attribute 'start'" in repr(err1.exception))
        self.assertTrue("'StartOnly' object has no attribute 'stop'" in repr(err2.exception))

    def test_with_start_stop_join(self) -> None:

        with self.assertRaises(AttributeError):
            with start_stop_join(StartStopNoArgs()):  # expect typing to complain
                pass

        with start_stop_join(StartStopJoin()) as res1:
            # reveal_type(res1)  # Check if typed as StartStopJoin
            pass

        with start_stop(Mock()) as res2:
            # reveal_type(res2)  # Check if typed as Mock
            pass

        with start_stop_join(Mock()) as res3:
            # reveal_type(res3)  # Check if typed as Mock
            pass

        res2.join.assert_not_called()
        res3.join.assert_called()

    def test_with_open_close(self) -> None:
        """Test that a right type of class has to be given for a `open_close` context manager for it to work."""
        with open_close(Mock()) as oc:
            # reveal_type(oc)  # Check if types as Mock
            pass

        oc.open.assert_called_once()
        oc.close.assert_called_once()

        with self.assertRaises(TypeError):
            with open_close(Mock(), 'foo', bar='bar') as oc:  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err1:
            with open_close(object()):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with open_close(OpenOnly()):  # type: ignore
                pass

        self.assertTrue("'object' object has no attribute 'open'" in repr(err1.exception))
        self.assertTrue("'OpenOnly' object has no attribute 'close'" in repr(err2.exception))

    def test_with_lock_unlock(self) -> None:
        """Test that a right type of class has to be given for a `lock_unlock` context manager for it to work."""
        with lock_unlock(Mock(), 'foo', bar='bar') as lu:
            # reveal_type(oc)  # Check if types as Mock
            pass

        lu.lock.assert_called_once_with('foo', bar='bar')
        lu.unlock.assert_called_once()

        with self.assertRaises(AttributeError) as err1:
            with lock_unlock(object()):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with lock_unlock(LockOnly()):  # type: ignore
                pass

        self.assertTrue("'object' object has no attribute 'lock'" in repr(err1.exception))
        self.assertTrue("'LockOnly' object has no attribute 'unlock'" in repr(err2.exception))


if __name__ == '__main__':
    unittest.main()
