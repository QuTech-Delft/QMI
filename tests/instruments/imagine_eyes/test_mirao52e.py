import unittest
from unittest.mock import Mock, MagicMock, patch
import os

import numpy

import qmi
from qmi.instruments.imagine_eyes import ImagineEyes_Mirao52e, MirrorStatus
from qmi.core.exceptions import QMI_InstrumentException

readline_mock = Mock()


class PopenMock:
    stdin = Mock(write=MagicMock())
    stdout = Mock(readline=readline_mock)

    def __init__(self, args="wine", stdin=None, stdout=None, cwd=None, env=None):
        pass

    def wait(self):
        pass


class InstanceCreationTestCase(unittest.TestCase):

    def test_default_directory(self):
        """Test that the behaviour is as expected when using default directory while creating instance."""
        if os.path.isdir(ImagineEyes_Mirao52e.DEFAULT_BRIDGE_DIR):
            expected_dir = ImagineEyes_Mirao52e.DEFAULT_BRIDGE_DIR
            mirao = ImagineEyes_Mirao52e(qmi.core.context.QMI_Context("Mirao"), "Mirao test")
            self.assertEqual(mirao._bridge_dir, expected_dir)

        else:
            with self.assertRaises(QMI_InstrumentException):
                ImagineEyes_Mirao52e(qmi.core.context.QMI_Context("Mirao"), "Mirao test")

    def test_custom_directory(self):
        """Test that a custom directory, set as local directory, does run without exceptions"""
        expected_dir = os.path.dirname(__file__)
        mirao = ImagineEyes_Mirao52e(qmi.core.context.QMI_Context("Mirao"), "Mirao test", expected_dir)
        self.assertEqual(mirao._bridge_dir, expected_dir)

    def test_faulty_custom_directory(self):
        """Test that a custom directory that does not exist raises an exception"""
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            ImagineEyes_Mirao52e(qmi.core.context.QMI_Context("Mirao"), "Mirao test", r"Q:\utech\QID\QMI")


@patch("sys.platform", "linux1")
class MethodsLinuxTestCase(unittest.TestCase):

    @patch("sys.platform", "linux1")
    def setUp(self):
        # First mock is for the Linux WinE opener
        self._popen_patcher = patch("qmi.instruments.imagine_eyes.mirao52e.subprocess.Popen", new=PopenMock)
        self._popen_patcher.start()
        readline_mock.side_effect = [b"MIRAO52_BRIDGE bla", b"READY"] + [b"OK", b"READY"] * 3
        path = os.path.dirname(__file__)
        self.mirao = ImagineEyes_Mirao52e(qmi.core.context.QMI_Context("Mirao"), "Mirao test", path)

    @patch("sys.platform", "linux1")
    def tearDown(self):
        if self.mirao._is_open:
            self.mirao.close()

        self._popen_patcher.stop()

    def test_01_open(self):
        """Test opening the instrument in Linux."""
        self.mirao.open()
        self.assertTrue(self.mirao._is_open)

    def test_01b_open_excepts_at_handshake(self):
        """Test opening the instrument in Linux."""
        readline_mock.side_effect = [b"MIRAO52_BRIDGE", b"READY"] + [b"OK", b"READY"] * 3
        expected_exception = "Unexpected handshake from helper program: ['MIRAO52_BRIDGE']"
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
            self.mirao.open()

        self.assertEqual(str(exc.exception), expected_exception)

    @patch("sys.platform", "linux1")
    def test_02_close(self):
        """Test closing the instrument in Linux."""
        self.mirao.open()
        self.mirao.close()
        self.assertFalse(self.mirao._is_open)

    def test_03_get_idn(self):
        """Test that the IDN request is correctly made and returns QMI_InstrumentIdentification instance."""
        expected_vendor = "ImagineEyes"
        expected_model = "Mirao52e"
        expected_version = "bla"

        self.mirao.open()
        val = self.mirao.get_idn()
        self.assertEqual(type(val), qmi.core.instrument.QMI_InstrumentIdentification)
        self.assertEqual(val.vendor, expected_vendor)
        self.assertEqual(val.model, expected_model)
        self.assertEqual(val.version, expected_version)
        self.assertEqual(self.mirao._version_string, expected_version)

    def test_04_apply(self):
        """See that the 'apply' command works as expected on Linux."""
        actuators = numpy.random.random(52)
        cmd = "APPLY " + ",".join("{:.6f}".format(v) for v in actuators) + "\r\n"
        expected_call = bytes(cmd.encode())
        self.mirao.open()
        self.mirao.apply(actuators)
        self.mirao._proc.stdin.write.assert_called_with(expected_call)

    def test_05_apply_wrong_actuator_length(self):
        """Test that the 'apply' excepts when length of the actuators is not 52."""
        actuators = numpy.random.random(51)
        self.mirao.open()
        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            self.mirao.apply(actuators)

        actuators = numpy.random.random(53)
        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            self.mirao.apply(actuators)

    def test_06_apply_erroneous_returns(self):
        """Test that the 'apply' excepts when program gives unvalid responses."""
        replies = [b"MIRAO52_BRIDGE bla", b"READY", b"OK", b"READY", b"ERROR Test Error", b"READY", b""]
        readline_mock.side_effect = replies + [b"READY", b"OK", b"READY"]
        expected_exception_1 = "Error from {}: {}".format("Mirao test", "Test Error")
        expected_exception_2 = "Unexpected end of input from helper program"
        expected_exception_3 = "Unexpected response from Mirao test: {}".format([])
        actuators = numpy.random.random(52)
        self.mirao.open()
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc1:
            self.mirao.apply(actuators)

        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc2:
            self.mirao.apply(actuators)

        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc3:
            self.mirao.apply(actuators)

        self.assertEqual(str(exc1.exception), expected_exception_1)
        self.assertEqual(str(exc2.exception), expected_exception_2)
        self.assertEqual(str(exc3.exception), expected_exception_3)

    def test_07_get_mirror_status(self):
        """See that 'get_mirror_status' returns correct MirrorStatus object."""
        psu_temp = 123.4
        locked = 0
        replies = [b"MIRAO52_BRIDGE bla", b"READY", b"OK", b"READY",
                   bytes(f"PSUTEMP={psu_temp} LOCKED={locked}".encode())]
        readline_mock.side_effect = replies + [b"OK", b"READY", b"OK", b"READY"]
        cmd = "MONITOR" + "\r\n"
        expected_call = bytes(cmd.encode())
        expected_result = MirrorStatus(psu_temp, bool(locked))
        self.mirao.open()
        mirror_status = self.mirao.get_mirror_status()
        self.mirao._proc.stdin.write.assert_called_with(expected_call)
        self.assertEqual(mirror_status, expected_result)


@patch("sys.platform", "win32")
class MethodsWindowsOnlyTestCase(unittest.TestCase):

    @patch("sys.platform", "win32")
    def setUp(self):
        self._popen_patcher = patch("qmi.instruments.imagine_eyes.mirao52e.subprocess.Popen", new=PopenMock)
        self._popen_patcher.start()
        readline_mock.side_effect = [b"MIRAO52_BRIDGE bla", b"READY"] + [b"OK", b"READY"] * 3
        path = os.path.dirname(__file__)
        self.mirao = ImagineEyes_Mirao52e(qmi.core.context.QMI_Context("Mirao"), "Mirao test", path)

    @patch("sys.platform", "win32")
    def tearDown(self):
        if self.mirao._is_open:
            self.mirao.close()

        self._popen_patcher.stop()

    def test_01_open(self):
        """Test opening the instrument in Windows."""
        self.mirao.open()
        self.assertTrue(self.mirao._is_open)

    def test_02_close(self):
        """Test closing the instrument in Windows."""
        self.mirao.open()
        self.mirao.close()
        self.assertFalse(self.mirao._is_open)

    def test_03_get_idn(self):
        """Test that the IDN request is correctly made and returns QMI_InstrumentIdentification instance."""
        expected_vendor = "ImagineEyes"
        expected_model = "Mirao52e"
        expected_version = "bla"

        self.mirao.open()
        val = self.mirao.get_idn()
        self.assertEqual(type(val), qmi.core.instrument.QMI_InstrumentIdentification)
        self.assertEqual(val.vendor, expected_vendor)
        self.assertEqual(val.model, expected_model)
        self.assertEqual(val.version, expected_version)
        self.assertEqual(self.mirao._version_string, expected_version)

    def test_04_apply(self):
        """See that the 'apply' command works as expected on Windows as well."""
        actuators = numpy.random.random(52)
        cmd = "APPLY " + ",".join("{:.6f}".format(v) for v in actuators) + "\r\n"
        expected_call = bytes(cmd.encode())
        self.mirao.open()
        self.mirao.apply(actuators)
        self.mirao._proc.stdin.write.assert_called_with(expected_call)

    def test_05_get_mirror_status(self):
        """See that 'get_mirror_status' returns correct MirrorStatus object."""
        psu_temp = 432.1
        locked = 1
        replies = [b"MIRAO52_BRIDGE bla", b"READY", b"OK", b"READY",
                   bytes(f"PSUTEMP={psu_temp} LOCKED={locked}".encode())]
        readline_mock.side_effect = replies + [b"OK", b"READY", b"OK", b"READY"]
        cmd = "MONITOR" + "\r\n"
        expected_call = bytes(cmd.encode())
        expected_result = MirrorStatus(psu_temp, bool(locked))
        self.mirao.open()
        mirror_status = self.mirao.get_mirror_status()
        self.mirao._proc.stdin.write.assert_called_with(expected_call)
        self.mirao._proc.stdout = Mock(readline=readline_mock)
        self.assertEqual(mirror_status, expected_result)


if __name__ == '__main__':
    unittest.main()
