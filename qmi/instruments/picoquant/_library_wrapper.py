import ctypes
import sys
from typing import Any

from qmi.core.exceptions import QMI_InstrumentException
from qmi.instruments.picoquant._hhlib_function_signatures import _hhlib_function_signatures


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

            else:
                raise FileNotFoundError("Unknown library: {lib}.".format(lib=model))

        elif sys.platform.startswith("win"):
            if model == "HH":
                try:
                    self._lib = ctypes.WinDLL("hhlib64.dll")  # 64-bit version
                except:
                    self._lib = ctypes.WinDLL("hhlib.dll")  # 32-bit version

                self.annotate_function_signatures(_hhlib_function_signatures)

            else:
                raise FileNotFoundError("Unknown library: {lib}.".format(lib=model))

        else:
            raise OSError("Unsupported platform.")

    def __getattr__(self, item: str) -> Any:
        attr_name = "{prefix}_{item}".format(prefix=self._prefix, item=item)
        attr = getattr(self._lib, attr_name)

        def wrap_fun(*args, **kwargs):
            errcode = attr(*args, **kwargs)
            if errcode != 0:
                raise QMI_InstrumentException(f"Interaction with PicoQuant library failed, errorcode [{errcode}].")

        return wrap_fun

    def annotate_function_signatures(self, sigs) -> None:
        """Annotate functions present in the HydraHarp shared library according to their function signatures."""
        function_signatures = sigs

        for (name, restype, argtypes) in function_signatures:
            try:
                func = getattr(self._lib, name)
                func.restype = restype
                func.argtypes = [argtype for (argname, argtype) in argtypes]
            except AttributeError:
                # Ignore functions that cannot be found.
                pass
