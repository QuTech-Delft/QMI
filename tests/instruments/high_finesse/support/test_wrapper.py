from unittest import TestCase
from unittest.mock import patch, sentinel

from qmi.instruments.high_finesse.support import wlmData
from qmi.instruments.high_finesse.support._library_wrapper import _LibWrapper


class TestHighFinesse_WS_Linux(TestCase):
    """Test the behavior of the High Finesse driver on a Linux platform."""

    def setUp(self):
        """Make the sys mock say that we run on Linux."""
        patcher = patch("qmi.instruments.high_finesse.support._library_wrapper.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="linux")
        self.addCleanup(patcher.stop)

    @patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
    def test_init(self, mocker):
        """The LoadDLL function should be called once."""
        wlmData.dll = sentinel.dll

        lib = _LibWrapper()
        mocker.assert_called_once_with("libwlmData.so")
        self.assertIsNotNone(lib.dll)
        self.assertEqual(lib.dll, sentinel.dll)


class TestHighFinesse_WS_Windows(TestCase):
    """Test the behavior of the High Finesse driver on a Windows platform."""

    def setUp(self):
        """Make the sys mock say that we run on Windows."""
        patcher = patch("qmi.instruments.high_finesse.support._library_wrapper.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="windows")
        self.addCleanup(patcher.stop)

    @patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
    def test_init(self, mocker):
        """The LoadDLL function should be called once."""
        wlmData.dll = sentinel.dll

        lib = _LibWrapper()
        mocker.assert_called_once_with("wlmData.dll")
        self.assertIsNotNone(lib.dll)
        self.assertEqual(lib.dll, sentinel.dll)


class TestHighFinesse_WS_MacOS(TestCase):
    """Test the behavior of the High Finesse driver on a MacOS platform."""

    def setUp(self):
        """Make the sys mock say that we run on MacOS."""
        patcher = patch("qmi.instruments.high_finesse.support._library_wrapper.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="darwin")
        self.addCleanup(patcher.stop)

    @patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
    def test_init(self, mocker):
        """The LoadDLL function should be called once."""
        wlmData.dll = sentinel.dll

        lib = _LibWrapper()
        mocker.assert_called_once_with("libwlmData.dylib")
        self.assertIsNotNone(lib.dll)
        self.assertEqual(lib.dll, sentinel.dll)


class TestHighFinesse_WS_Unknown(TestCase):
    """Test the behavior of the High Finesse driver on an unsupported platform."""

    def setUp(self):
        """Make the sys mock say that we run on Cygwin."""
        patcher = patch("qmi.instruments.high_finesse.support._library_wrapper.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="cygwin")
        self.addCleanup(patcher.stop)

    @patch("qmi.instruments.high_finesse.support._library_wrapper.wlmData.LoadDLL")
    def test_init(self, mocker):
        """The LoadDLL function should be called once."""
        with self.assertRaises(OSError) as exc:
            _ = _LibWrapper()

        self.assertEqual("Unsupported platform", str(exc.exception))
        mocker.assert_not_called()
