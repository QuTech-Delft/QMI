"""
Instrument driver for the Adwin.

This driver requires that the ADwin library and ADwin Python module
are installed on the system.

On Linux, the ADwin system library must be at least version 5.0.13.
Earlier versions do not correctly support double-precision floating point
data from the Adwin T12. On Windows, library version 6.0.x should be used.
"""

import logging
import os
import os.path
import sys
import threading
import time
import typing

from typing import Any, List, Union

import numpy as np

# Lazy import of the ADwin module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    import ADwin
else:
    ADwin = None

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Global mutex to protect access to the Adwin library.
_adwin_mutex = threading.RLock()


def _import_modules() -> None:
    """Import the vendor-provided "ADwin" module.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global ADwin
    if ADwin is None:
        import ADwin  # pylint: disable=W0621


class Adwin_Base(QMI_Instrument):
    """Instrument driver base class for the Adwin real-time microcontrollers. ADwin.py has fixed maximum number of
    parameters and data that are dependent on processor type. The 'MAX_m' values here are valid for at least the T11,
    T12 and T12.1 processor types. The maximum number of slots instead is dependent on the enclosure type of the ADwin.
    """
    MAX_PAR: int = 80
    MAX_DATA: int = 200
    MAX_PROCESS_NO: int = 10

    # Maximum time to wait until an Adwin process stops (seconds).
    PROCESS_STOP_TIMEOUT = 1.0

    def __init__(self, context: QMI_Context, name: str, device_no: int) -> None:
        """Initialize the Adwin driver.

        Parameters:
            context: QMI context.
            name: Name for this instrument instance.
            device_no: ADwin device number.
        """
        super().__init__(context, name)

        _logger.info("[%s] Creating Adwin instance, device_no=%d", name, device_no)
        self._device_no = device_no

        _import_modules()

        # NOTE: Creating the ADwin instance does not yet initiate communication with the device.
        self._adwin = ADwin.ADwin(DeviceNo=self._device_no, raiseExceptions=1)

    def _is_integer_array(self, data_idx: int) -> bool:
        """Determine whether the specified global data array has integer elements.

        This function must be called with `_adwin_mutex` locked.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).

        Returns:
            True if the array has integer elements, False if it has floating point elements.

        Raise:
            QMI_InstrumentException: If the array has neither integer, nor floating point elements.
        """
        # See "Python_eng.pdf" page 30 for how "type_code" and "type_name" encode data types.
        type_code, type_name = self._adwin.Data_Type(data_idx)

        # Check on "type_name", since not all "type_code" values are enumerated in the ADwin class.
        if type_name in ("byte", "short", "int32", "int64", "long"):
            return True
        elif type_name in ("float", "float32", "float64"):  # "float" for backwards compatibility (T11 and older)
            return False
        else:
            # "string" or "undefined".
            raise QMI_InstrumentException("Unsupported data type {} ({}) for Data {}".format(
                type_name, type_code, data_idx
            ))

    @rpc_method
    def reboot(self) -> None:
        """Reboot the Adwin system, clear data and restart programs.

        This function must be called after power-on before communication
        with the Adwin is possible. This function may be called again
        to perform a full reset.

        This function boots the Adwin, removes all processes and data.
        """
        self._check_is_open()

        # Find boot loader file.
        with _adwin_mutex:
            processor_type = self._adwin.Processor_Type().strip()
            boot_file = "ADwin{}.btl".format(processor_type.replace(".", "").strip("T"))
            boot_file_path = os.path.join(self._adwin.ADwindir, boot_file)

        if not os.path.isfile(boot_file_path):
            # On Linux, boot files are in a subdirectory under the ADwindir.
            boot_file_path = os.path.join(self._adwin.ADwindir, "share", "btl", boot_file)

        if not os.path.isfile(boot_file_path):
            raise QMI_InstrumentException("Can not find boot file {}".format(boot_file))

        _logger.info("[%s] Rebooting Adwin", self._name)
        with _adwin_mutex:
            self._adwin.Boot(boot_file_path)

        self.check_ready()

    @rpc_method
    def check_ready(self) -> None:
        """Raise an exception if the Adwin is not ready."""
        self._check_is_open()
        with _adwin_mutex:
            err = self._adwin.Test_Version()

        if err != 0:
            raise QMI_InstrumentException("Incorrect Adwin operating system version {}".format(err))

    @rpc_method
    def get_processor_type(self) -> str:
        """Returns the ADwin processor type."""
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Processor_Type()

    @rpc_method
    def get_workload(self) -> int:
        """Return average processor workload in percent since the last call."""
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Workload()

    @rpc_method
    def load_process(self, bin_file: str) -> None:
        """Load the specified Adwin process but do not start it yet.

        Parameters:
            bin_file: Path to binary file to load into the Adwin.
        """
        self._check_is_open()
        with _adwin_mutex:
            self._adwin.Load_Process(bin_file)

    @rpc_method
    def start_process(self, slot: int) -> None:
        """Start the specified Adwin process.

        The process must already have been loaded by calling `load_process()`.

        Parameters:
            slot: Adwin process slot index (range 1 to MAX_PROCESS_NO).
        """
        if (slot < 1) or (slot > self.MAX_PROCESS_NO):
            raise ValueError("Invalid process slot index")
        self._check_is_open()
        with _adwin_mutex:
            status = self._adwin.Process_Status(slot)
            if status != 0:
                raise QMI_InstrumentException("Can not start Adwin process, slot {} already running".format(slot))
            self._adwin.Start_Process(slot)

    @rpc_method
    def stop_process(self, slot: int) -> None:
        """Stop the specified Adwin process.

        Parameters:
            slot: Adwin process slot index (range 1 to MAX_PROCESS_NO).
        """
        if (slot < 1) or (slot > self.MAX_PROCESS_NO):
            raise ValueError("Invalid process slot index")
        self._check_is_open()
        with _adwin_mutex:
            self._adwin.Stop_Process(slot)

    @rpc_method
    def wait_for_process(self, slot: int, timeout: float) -> None:
        """Wait until the specified Adwin process has stopped.

        Parameters:
            slot: Adwin process slot index (range 1 to MAX_PROCESS_NO).
            timeout: Maximum time to wait (seconds).

        Raises:
            ~qmi.core.exceptions.QMI_TimeoutException: If the process does not stop before timeout occurs.
        """
        if (slot < 1) or (slot > self.MAX_PROCESS_NO):
            raise ValueError("Invalid process slot index")
        self._check_is_open()
        t0 = time.monotonic()
        while True:
            with _adwin_mutex:
                status = self._adwin.Process_Status(slot)
            if status == 0:
                break
            t = time.monotonic()
            if t - t0 > timeout:
                raise QMI_TimeoutException("Adwin process slot {} still running".format(slot))
            time.sleep(0.02)

    @rpc_method
    def is_process_running(self, slot: int) -> bool:
        """Return True if the specified Adwin process is currently running.

        Parameters:
            slot: Adwin process slot index (range 1 to MAX_PROCESS_NO).
        """
        if (slot < 1) or (slot > self.MAX_PROCESS_NO):
            raise ValueError("Invalid process slot index")
        self._check_is_open()
        with _adwin_mutex:
            status = self._adwin.Process_Status(slot)
        return (status != 0)

    @rpc_method
    def get_par(self, par_idx: int) -> int:
        """Return the current value of the specified global parameter.

        Parameters:
            par_idx: Index into the global Par array (range 1 to MAX_PAR).

        Returns:
            Value of the parameter.
        """
        if (par_idx < 1) or (par_idx > self.MAX_PAR):
            raise ValueError("Invalid Par index {}".format(par_idx))
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Get_Par(par_idx)

    @rpc_method
    def get_fpar(self, par_idx: int) -> float:
        """Return the current value of the specified global parameter.

        Parameters:
            par_idx: Index into the global FPar array (range 1 to MAX_PAR).

        Returns:
            Value of the parameter.
        """
        if (par_idx < 1) or (par_idx > self.MAX_PAR):
            raise ValueError("Invalid FPar index {}".format(par_idx))
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Get_FPar_Double(par_idx)

    @rpc_method
    def get_par_block(self, par_first: int, par_count: int) -> np.ndarray:
        """Return the current values of a block of global parameters.

        Parameters:
            par_first: First index into the global Par array (range 1 to MAX_PAR).
            par_count: Number of parameters to get.

        Returns:
            1D Numpy array with the parameter values.
        """
        if (par_first < 1) or (par_count < 1) or (par_first + par_count - 1 > self.MAX_PAR):
            raise ValueError("Invalid Par index range {} .. {}".format(par_first, par_first + par_count - 1))
        self._check_is_open()
        with _adwin_mutex:
            value = self._adwin.Get_Par_Block(par_first, par_count)
        return np.array(value)

    @rpc_method
    def get_fpar_block(self, par_first: int, par_count: int) -> np.ndarray:
        """Return the current values of a block of global parameters.

        Parameters:
            par_first: First index into the global FPar array (range 1 to MAX_PAR).
            par_count: Number of parameters to get.

        Returns:
            1D Numpy array with the parameter values.
        """
        if (par_first < 1) or (par_count < 1) or (par_first + par_count - 1 > self.MAX_PAR):
            raise ValueError("Invalid FPar index range {} .. {}".format(par_first, par_first + par_count - 1))
        self._check_is_open()
        with _adwin_mutex:
            value = self._adwin.Get_FPar_Block_Double(par_first, par_count)
        return np.array(value)

    @rpc_method
    def set_par(self, par_idx: int, value: int) -> None:
        """Change the value of the specified global parameter.

        Parameters:
            par_idx: Index into the global Par array (range 1 to MAX_PAR).
            value: New value to write to the parameter (signed 32-bit integer).
        """
        if (par_idx < 1) or (par_idx > self.MAX_PAR):
            raise ValueError("Invalid Par index {}".format(par_idx))
        if not isinstance(value, int):
            raise TypeError("Expecting integer value for parameter but got {}".format(value))
        self._check_is_open()
        with _adwin_mutex:
            self._adwin.Set_Par(par_idx, value)

    @rpc_method
    def set_fpar(self, par_idx: int, value: float) -> None:
        """Change the value of the specified global parameter.

        Parameters:
            par_idx: Index into the global FPar array (range 1 to MAX_PAR).
            value: New value to write to the parameter.
        """
        if (par_idx < 1) or (par_idx > self.MAX_PAR):
            raise ValueError("Invalid FPar index {}".format(par_idx))
        if not isinstance(value, (int, float)):
            raise TypeError("Expecting numeric value for parameter but got {}".format(value))
        self._check_is_open()
        with _adwin_mutex:
            self._adwin.Set_FPar_Double(par_idx, value)

    @rpc_method
    def get_data_length(self, data_idx: int) -> int:
        """Return the length of the specified global Data array.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).

        Returns:
            Length of the data array (maximum valid array index).
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Data_Length(data_idx)

    @rpc_method
    def get_data(self, data_idx: int, first_index: int, count: int) -> np.ndarray:
        """Read values from a global Data array.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).
            first_index: First index into the data array (>= 1).
            count: Number of elements to read from the data array.

        Returns:
            1D Numpy array with data values.
            Element 0 of the returned array will correspond with `first_index` into the Adwin array.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        if (first_index < 1) or (count < 1):
            raise ValueError("Invalid Data element index range {} .. {}".format(first_index, first_index + count - 1))
        self._check_is_open()
        with _adwin_mutex:
            if self._is_integer_array(data_idx):
                value = self._adwin.GetData_Long(data_idx, first_index, count)
            else:
                value = self._adwin.GetData_Double(data_idx, first_index, count)
        return np.array(value)

    @rpc_method
    def get_full_data(self, data_idx: int) -> np.ndarray:
        """Read all elements from a global DATA array.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).

        Returns:
            1D Numpy array with data values.
            Element 0 of the returned array will correspond with element 1 into the Adwin array.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        self._check_is_open()
        with _adwin_mutex:
            length = self._adwin.Data_Length(data_idx)
            if self._is_integer_array(data_idx):
                value = self._adwin.GetData_Long(data_idx, 1, length)
            else:
                value = self._adwin.GetData_Double(data_idx, 1, length)
        return np.array(value)

    @rpc_method
    def set_data(self, data_idx: int, first_index: int, value: Union[np.ndarray, List[int], List[float]]) -> None:
        """Write values to a global Data array.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).
            first_index: First index into the Data array (>= 1).
            value: List of values to write to the Data array.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        if first_index < 1:
            raise ValueError("Invalid Data element index {}".format(first_index))
        self._check_is_open()
        with _adwin_mutex:
            raw_value: Any
            if self._is_integer_array(data_idx):
                if isinstance(value, np.ndarray):
                    # The Adwin library does not accept Numpy arrays.
                    if value.dtype.kind not in "iu":
                        raise ValueError("Invalid non-integer data for Data_{}".format(data_idx))
                    raw_value = np.ctypeslib.as_ctypes(value.astype(np.int32))
                else:
                    raw_value = value
                self._adwin.SetData_Long(raw_value, data_idx, first_index, len(value))
            else:
                if isinstance(value, np.ndarray):
                    # The Adwin library does not accept Numpy arrays.
                    raw_value = np.ctypeslib.as_ctypes(value.astype(np.float64))
                else:
                    raw_value = value
                self._adwin.SetData_Double(raw_value, data_idx, first_index, len(value))

    @rpc_method
    def get_fifo_filled(self, data_idx: int) -> int:
        """Return the number of values waiting in the FIFO.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).

        Returns:
            Number of FIFO entries currently in use.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Fifo_Full(data_idx)

    @rpc_method
    def get_fifo_room(self, data_idx: int) -> int:
        """Return the number of values that can be added to the FIFO without overflowing it.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).

        Returns:
            Number of empty FIFO entries available.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        self._check_is_open()
        with _adwin_mutex:
            return self._adwin.Fifo_Empty(data_idx)

    @rpc_method
    def read_fifo(self, data_idx: int, count: int) -> np.ndarray:
        """Read data from a global FIFO variable.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).
            count: Number of values to read from the FIFO.

        Returns:
            1D Numpy array containing the FIFO elements.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        self._check_is_open()
        with _adwin_mutex:
            if self._is_integer_array(data_idx):
                value = self._adwin.GetFifo_Long(data_idx, count)
            else:
                value = self._adwin.GetFifo_Double(data_idx, count)
        return np.array(value)

    @rpc_method
    def write_fifo(self, data_idx: int, value: Union[np.ndarray, List[int], List[float]]) -> None:
        """Write data to a global FIFO variable.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).
            value: Array of values to write to the FIFO.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        self._check_is_open()
        with _adwin_mutex:
            raw_value: Any
            if self._is_integer_array(data_idx):
                if isinstance(value, np.ndarray):
                    # The Adwin library does not accept Numpy arrays.
                    raw_value = np.ctypeslib.as_ctypes(value.astype(np.int32))
                    if value.dtype.kind not in "iu":
                        raise ValueError("Invalid non-integer data for Data_{}".format(data_idx))
                else:
                    raw_value = value
                self._adwin.SetFifo_Long(data_idx, raw_value, len(value))
            else:
                if isinstance(value, np.ndarray):
                    # The Adwin library does not accept Numpy arrays.
                    raw_value = np.ctypeslib.as_ctypes(value.astype(np.float64))
                else:
                    raw_value = value
                self._adwin.SetFifo_Double(data_idx, raw_value, len(value))

    @rpc_method
    def set_file_to_data(self, data_idx: int, first_index: int, file_path: str) -> None:
        """Upload the file at `file_path` to the specified array.
        This method is used to load binary programs into TiCo modules at ADwin runtime.

        Parameters:
            data_idx: Index into the global list of Data arrays (range 1 to MAX_DATA).
            first_index: First index into the Data array (>= 1).
            file_path: Path of the file to upload.
        """
        if (data_idx < 1) or (data_idx > self.MAX_DATA):
            raise ValueError("Invalid Data index {}".format(data_idx))
        if first_index < 1:
            raise ValueError("Invalid Data element index {}".format(first_index))
        self._check_is_open()
        with _adwin_mutex:
            if not self._is_integer_array(data_idx):
                _logger.error("Binary files should be uploaded to long arrays.")
                raise QMI_InstrumentException("Target data array should be of type long.")

            # Here we workaround a bug in the ADwin library, data type should be
            # two, but on Linux it needs 3 to work correctly. They are working
            # on it. Matteo Pompili June 2021.
            if sys.platform.startswith("linux"):
                adwin_data_type = 3  # Long array
            else:
                adwin_data_type = 2  # Long array

            # Check if file exists, so we can provide a better error than what ADwin would.
            if not os.path.isfile(file_path):
                _logger.error("Trying to upload %s to the ADwin, but it does not exist.", file_path)
                raise QMI_InstrumentException("The specified file does not exist.")

            self._adwin.File2Data(file_path, adwin_data_type, data_idx, first_index)
