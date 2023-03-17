import unittest.mock

from qmi.instruments.picoquant.support._library_wrapper import _LibWrapper
from qmi.instruments.picoquant.support import _phlib_function_signatures, \
    _mhlib_function_signatures, _hhlib_function_signatures


class LibraryWrapperTestCase(unittest.TestCase):

    @unittest.mock.patch("sys.platform", "darwin")
    def test_unsupported_platform_fail(self):
        with self.assertRaises(OSError) as exc:
            _LibWrapper("HH")

        self.assertEqual(str(exc.exception), "Unsupported platform.")

    @unittest.mock.patch("sys.platform", "linux")
    def test_unsupported_harp_lin(self):
        false_lib = "ASDF"
        with self.assertRaises(FileNotFoundError) as exc:
            _LibWrapper(false_lib)

        self.assertEqual(str(exc.exception), "Unknown library: {lib}.".format(lib=false_lib))

    @unittest.mock.patch("sys.platform", "win32")
    def test_unsupported_harp_win(self):
        false_lib = "ASDF"
        with self.assertRaises(FileNotFoundError) as exc:
            _LibWrapper(false_lib)

        self.assertEqual(str(exc.exception), "Unknown library: {lib}.".format(lib=false_lib))

    @unittest.mock.patch("sys.platform", "linux")
    def test_multiharp_wrapper_annotations_lin(self):
        attr_list = [fs[0] for fs in _mhlib_function_signatures._mhlib_function_signatures]
        with unittest.mock.patch("ctypes.cdll"):
            lib_wrapper = _LibWrapper("MH")
            annotations = dir(lib_wrapper._lib)
            for a in attr_list:
                self.assertIn(a, annotations)

    @unittest.mock.patch("sys.platform", "linux")
    def test_hydraharp_wrapper_annotations_lin(self):
        attr_list = [fs[0] for fs in _hhlib_function_signatures._hhlib_function_signatures]
        with unittest.mock.patch("ctypes.cdll"):
            lib_wrapper = _LibWrapper("HH")
            annotations = dir(lib_wrapper._lib)
            for a in attr_list:
                self.assertIn(a, annotations)

    @unittest.mock.patch("sys.platform", "linux")
    def test_picoharp_wrapper_annotations_lin(self):
        attr_list = [fs[0] for fs in _phlib_function_signatures._phlib_function_signatures]
        with unittest.mock.patch("ctypes.cdll"):
            lib_wrapper = _LibWrapper("PH")
            annotations = dir(lib_wrapper._lib)
            for a in attr_list:
                self.assertIn(a, annotations)

    @unittest.mock.patch("sys.platform", "win32")
    def test_multiharp_wrapper_annotations_win(self):
        attr_list = [fs[0] for fs in _mhlib_function_signatures._mhlib_function_signatures]
        with unittest.mock.patch("ctypes.WinDLL", create=True):
            lib_wrapper = _LibWrapper("MH")
            annotations = dir(lib_wrapper._lib)
            for a in attr_list:
                self.assertIn(a, annotations)

    @unittest.mock.patch("sys.platform", "win32")
    def test_hydraharp_wrapper_annotations_win(self):
        attr_list = [fs[0] for fs in _hhlib_function_signatures._hhlib_function_signatures]
        with unittest.mock.patch("ctypes.WinDLL", create=True):
            lib_wrapper = _LibWrapper("HH")
            annotations = dir(lib_wrapper._lib)
            for a in attr_list:
                self.assertIn(a, annotations)

    @unittest.mock.patch("sys.platform", "win32")
    def test_picoharp_wrapper_annotations_win(self):
        attr_list = [fs[0] for fs in _phlib_function_signatures._phlib_function_signatures]
        with unittest.mock.patch("ctypes.WinDLL", create=True):
            lib_wrapper = _LibWrapper("PH")
            annotations = dir(lib_wrapper._lib)
            for a in attr_list:
                self.assertIn(a, annotations)

    @unittest.mock.patch("sys.platform", "win32")
    def test_wrapper_exceptions_32bit_win(self):
        """Test that the library wrapper will try to call also for the 32-bit library if 64-bit library call excepts."""
        with unittest.mock.patch("ctypes.WinDLL", create=True, side_effect=[BaseException("No lib"), None]) \
                as ptc:

            _LibWrapper("MH")

        ptc.assert_any_call("mhlib64.dll")
        ptc.assert_called_with("mhlib.dll")

        with unittest.mock.patch("ctypes.WinDLL", create=True, side_effect=[BaseException("No lib"), None]) \
                as ptc:

            _LibWrapper("HH")

        ptc.assert_any_call("hhlib64.dll")
        ptc.assert_called_with("hhlib.dll")

        with unittest.mock.patch("ctypes.WinDLL", create=True, side_effect=[BaseException("No lib"), None]) \
                as ptc:

            _LibWrapper("PH")

        ptc.assert_any_call("phlib64.dll")
        ptc.assert_called_with("phlib.dll")


if __name__ == "__main__":
    unittest.main()
