"""
Library wrapper module that utilizes a Python wrapper around the PicoQuant library header files
for implemented models. The wrapper uses the manufacturer provided software libraries. The library files and
the respective licence terms can be found in the dedicated instrument software packages at PicoQuant website:
https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules.
"""
import ctypes
import logging
import sys
from typing import Any

from qmi.core.exceptions import QMI_InstrumentException
from qmi.instruments.picoquant.support._hhlib_function_signatures import _hhlib_function_signatures
from qmi.instruments.picoquant.support._mhlib_function_signatures import _mhlib_function_signatures
from qmi.instruments.picoquant.support._phlib_function_signatures import _phlib_function_signatures

_logger = logging.getLogger(__name__)


class _LibWrapper:

    def __init__(self, model: str) -> None:
        """ A Library wrapper class that makes a wrapper around the PicoQuant libraries for implemented models.

        Parameters:
            model: The PicoQuant xxHarp model as a string. Possible values MH, HH, PH, TH260.

        Raises:
            FileNotFoundError: When the library file of a specific xxHarp model could not be found (not installed?)
            OSError: Trying to run on an unsupported platform, e.g. MacOS ("darwin").
        """
        self._prefix = model
        if sys.platform.startswith("linux"):
            if model == "HH":
                self._lib = ctypes.cdll.LoadLibrary("libhh400.so")
                self.annotate_function_signatures(_hhlib_function_signatures)

            elif model == "MH":
                self._lib = ctypes.cdll.LoadLibrary("libmh150.so")
                self.annotate_function_signatures(_mhlib_function_signatures)

            elif model == "PH":
                self._lib = ctypes.cdll.LoadLibrary("libph300.so")
                self.annotate_function_signatures(_phlib_function_signatures)

            else:
                raise FileNotFoundError("Unknown library: {lib}.".format(lib=model))

        elif sys.platform.startswith("win"):
            if model == "HH":
                try:
                    self._lib = ctypes.WinDLL("hhlib64.dll")  # 64-bit version
                except:
                    self._lib = ctypes.WinDLL("hhlib.dll")  # 32-bit version

                self.annotate_function_signatures(_hhlib_function_signatures)

            elif model == "MH":
                try:
                    self._lib = ctypes.WinDLL("mhlib64.dll")  # 64-bit version
                except:
                    self._lib = ctypes.WinDLL("mhlib.dll")  # 32-bit version

                self.annotate_function_signatures(_mhlib_function_signatures)

            elif model == "PH":
                try:
                    self._lib = ctypes.WinDLL("phlib64.dll")  # 64-bit version
                except:
                    self._lib = ctypes.WinDLL("phlib.dll")  # 32-bit version

                self.annotate_function_signatures(_phlib_function_signatures)

            else:
                raise FileNotFoundError("Unknown library: {lib}.".format(lib=model))

        else:
            raise OSError("Unsupported platform.")

    def __getattr__(self, item: str) -> Any:
        attr_name = "{prefix}_{item}".format(prefix=self._prefix, item=item)
        attr = getattr(self._lib, attr_name)

        def wrap_fun(*args, **kwargs):
            _logger.debug(
                "Using %s library to call function %s with arguments %s, %s",
                self._prefix, attr_name, args, kwargs
            )
            errcode = attr(*args, **kwargs)
            if errcode != 0:
                _logger.error("[%s] Call to function %s failed with errorcode %i", self._prefix, attr_name, errcode)
                raise QMI_InstrumentException(f"Interaction with PicoQuant library failed, errorcode [{errcode}].")

        return wrap_fun

    def annotate_function_signatures(self, sigs) -> None:
        """Annotate functions present in the MultiHarp shared library according to their function signatures."""
        function_signatures = sigs

        for (name, restype, argtypes) in function_signatures:
            try:
                func = getattr(self._lib, name)
                func.restype = restype
                func.argtypes = [argtype for (argname, argtype) in argtypes]
            except AttributeError:
                # Ignore functions that cannot be found.
                pass
