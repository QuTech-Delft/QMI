import unittest
from unittest.mock import Mock
from types import ModuleType

from qmi.core.pubsub import QMI_SignalReceiver
from qmi.utils.context_managers import start_stop, start_stop_join, open_close, lock_unlock, subscribe_unsubscribe

from tests.utils import test_module


def reveal_type(oobj, iobj):
    """Assert that the output object from the context manager is of same type as the input."""
    assert isinstance(iobj, oobj)


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


class SubscribeUnsubscribe:
    def subscribe(self, *args) -> None: ...
    def unsubscribe(self, *args) -> None: ...


class SubscribeUnsubscribeNoArgs:
    def subscribe(self) -> None: ...
    def unsubscribe(self) -> None: ...


class StartOnly:
    def start(self): ...


class OpenOnly:
    def open(self): ...


class LockOnly:
    def lock(self): ...
    
    
class SubscribeOnly:
    def subscribe(self, *args) -> None: ...


class TestContextManagers(unittest.TestCase):
    """Tests the context manager classes."""

    def test_with_start_stop(self) -> None:
        """Test that a right type of class has to be given for a `start_stop` context manager for it to work."""
        iobj_ss = StartStop
        with start_stop(iobj_ss(), 'foo', bar='bar') as res1:
            reveal_type(iobj_ss, res1)  # Check if typed as StartStop

        iobj_ssna = StartStopNoArgs
        with start_stop(iobj_ssna()) as res2:
            reveal_type(iobj_ssna, res2)  # Check if typed as StartStopNoArgs

        with start_stop(test_module, "foo", bar=1) as res3:  # type: ignore
            reveal_type(ModuleType, res3)  # Check if typed as a module

        iobj = Mock
        with start_stop(iobj(), 'foo', bar='bar') as res4:
            reveal_type(iobj, res4)  # Check if typed as Mock

        res4.start.assert_called_once_with('foo', bar='bar')
        res4.stop.assert_called_once()

        # Tests with incomplete or non-correct objects
        exp_err_1 = "'object' object has no attribute 'start'"
        exp_err_2 = "'StartOnly' object has no attribute 'stop'"
        with self.assertRaises(AttributeError) as err1:
            with start_stop(object()):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with start_stop(StartOnly()):  # type: ignore
                pass

        self.assertEqual(exp_err_1, str(err1.exception))
        self.assertEqual(exp_err_2, str(err2.exception))

    def test_with_start_stop_join(self) -> None:
        """Test that a right type of class has to be given for a `start_stop_join` context manager for it to work."""
        iobj_ssj = StartStopJoin
        with start_stop_join(iobj_ssj()) as res1:
            reveal_type(iobj_ssj, res1)  # Check if typed as StartStopJoin

        iobj = Mock
        with start_stop(iobj()) as res2:
            reveal_type(iobj, res2)  # Check if typed as Mock

        with start_stop_join(iobj()) as res3:
            reveal_type(iobj, res3)  # Check if typed as Mock
            pass

        res2.join.assert_not_called()
        res3.join.assert_called()

        # Test with incomplete object
        exp_err_1 = "'StartStopNoArgs' object has no attribute 'join'"
        with self.assertRaises(AttributeError) as err1:
            with start_stop_join(StartStopNoArgs()):  # type: ignore
                pass

        self.assertEqual(exp_err_1, str(err1.exception))

    def test_with_open_close(self) -> None:
        """Test that a right type of class has to be given for a `open_close` context manager for it to work."""
        iobj = Mock
        with open_close(iobj()) as oc:
            reveal_type(iobj, oc)  # Check if types as Mock

        oc.open.assert_called_once()
        oc.close.assert_called_once()

        # Tests with incomplete or non-correct objects
        exp_err_1 = "open_close() got an unexpected keyword argument 'bar'"
        exp_err_2 = "'object' object has no attribute 'open'"
        exp_err_3 = "'OpenOnly' object has no attribute 'close'"
        with self.assertRaises(TypeError) as err1:
            with open_close(iobj(), 'foo', bar='bar'):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with open_close(object()):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err3:
            with open_close(OpenOnly()):  # type: ignore
                pass

        self.assertEqual(exp_err_1, str(err1.exception))
        self.assertEqual(exp_err_2, str(err2.exception))
        self.assertEqual(exp_err_3, str(err3.exception))

    def test_with_lock_unlock(self) -> None:
        """Test that a right type of class has to be given for a `lock_unlock` context manager for it to work."""
        iobj = Mock
        with lock_unlock(iobj(), 'foo', bar='bar') as lu:
            reveal_type(iobj, lu)  # Check if types as Mock

        lu.lock.assert_called_once_with('foo', bar='bar')
        lu.unlock.assert_called_once()

        # Tests with incomplete or non-correct objects
        exp_error_1 = "'object' object has no attribute 'lock'"
        exp_error_2 = "'LockOnly' object has no attribute 'unlock'"
        with self.assertRaises(AttributeError) as err1:
            with lock_unlock(object()):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with lock_unlock(LockOnly()):  # type: ignore
                pass

        self.assertEqual(exp_error_1, str(err1.exception))
        self.assertEqual(exp_error_2, str(err2.exception))

    def test_with_subscribe_unsubscribe(self) -> None:
        """Test that a right type of class has to be given for a
        `subscribe_unsubscribe` context manager for it to work."""
        iobj = Mock()
        receiver = QMI_SignalReceiver()
        with subscribe_unsubscribe(iobj, receiver) as lu:
            reveal_type(QMI_SignalReceiver, lu)

        iobj.subscribe.assert_called_once_with(receiver)
        iobj.unsubscribe.assert_called_once_with(receiver)

        # It should also work with 'None'
        iobj.reset_mock()
        with subscribe_unsubscribe(iobj, None) as lu:
            reveal_type(QMI_SignalReceiver, lu)

        iobj.subscribe.assert_called_once()
        iobj.unsubscribe.assert_called_once()

        # Tests with incomplete or non-correct objects
        exp_error_1 = "'object' object has no attribute 'subscribe'"
        exp_error_2 = "'SubscribeOnly' object has no attribute 'unsubscribe'"
        exp_error_3 = "subscribe() takes 1 positional argument but 2 were given"

        with self.assertRaises(AttributeError) as err1:
            with subscribe_unsubscribe(object(), None):  # type: ignore
                pass

        with self.assertRaises(AttributeError) as err2:
            with subscribe_unsubscribe(SubscribeOnly(), object()):  # type: ignore
                pass

        with self.assertRaises(TypeError) as err3:
            with subscribe_unsubscribe(SubscribeUnsubscribeNoArgs(), None):
                pass

        self.assertEqual(exp_error_1, str(err1.exception))
        self.assertEqual(exp_error_2, str(err2.exception))
        self.assertTrue(exp_error_3 in str(err3.exception))


if __name__ == '__main__':
    unittest.main()
