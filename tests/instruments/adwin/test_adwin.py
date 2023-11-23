import logging
import os
import unittest
from unittest.mock import Mock, patch

import numpy as np

import sys
import tests.instruments.adwin.adwin_stub
sys.modules['ADwin'] = tests.instruments.adwin.adwin_stub
patcher = patch("ADwin.ADwin")
_patcher = patcher.start()

from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.context import QMI_Context
from qmi.instruments.adwin import adwin
from qmi.instruments.adwin import JagerMessTechnik_AdwinGoldII, JagerMessTechnik_AdwinProII

# Class constants from ADwin.ADwin class
ADWIN_DATATYPE_INT8 = 1
ADWIN_DATATYPE_INT16 = 2
ADWIN_DATATYPE_INT32 = 3
ADWIN_DATATYPE_SINGLE = 5
ADWIN_DATATYPE_DOUBLE = 6
ADWIN_DATATYPE_INT64 = 7


class AdwinProIITest(unittest.TestCase):
    def test_class_constants_are_ok(self) -> None:
        self._adwin = JagerMessTechnik_AdwinProII(QMI_Context("test"), "Adwin", 1234)
        self.assertEqual(self._adwin.MAX_PAR, 80)
        self.assertEqual(self._adwin.MAX_DATA, 200)
        self.assertEqual(self._adwin.MAX_PROCESS_NO, 10)


class AdwinGoldIITest(unittest.TestCase):
    def test_class_constants_are_ok(self) -> None:
        self._adwin = JagerMessTechnik_AdwinGoldII(QMI_Context("test"), "Adwin", 1234)
        self.assertEqual(self._adwin.MAX_PAR, 80)
        self.assertEqual(self._adwin.MAX_DATA, 200)
        self.assertEqual(self._adwin.MAX_PROCESS_NO, 10)


class ADwinTestBaseClass(unittest.TestCase):
    def setUp(self) -> None:
        self._adwin = adwin.Adwin_Base(QMI_Context("test"), "Adwin", 1234)
        self._adwin.MAX_PROCESS_NO = 1
        self._adwin.MAX_PAR = 2
        self._adwin.MAX_DATA = 3
        self._adwin._adwin.ADWIN_DATATYPE_INT8 = ADWIN_DATATYPE_INT8
        self._adwin._adwin.ADWIN_DATATYPE_DOUBLE = ADWIN_DATATYPE_DOUBLE
        self._adwin.open()

    def tearDown(self) -> None:
        logging.getLogger("qmi.instruments.adwin.adwin").setLevel(logging.NOTSET)

    def test_check_ready(self):
        """ This test should run without raising any exceptions """
        self._adwin._adwin.Test_Version = Mock(return_value=0)
        self._adwin.check_ready()

        self._adwin._adwin.Test_Version.assert_called_once()

    def test_check_ready_wrong_version(self):
        """ This test raises QMI_InstrumentException due to error in Test_Version """
        self._adwin._adwin.Test_Version = Mock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._adwin.check_ready()

    def test_get_processor_type(self):
        """ Get the processor type"""
        expected = "T11"
        self._adwin._adwin.Processor_Type = Mock(return_value=expected)
        processor_type = self._adwin.get_processor_type()
        self.assertEqual(processor_type, expected)
        self._adwin._adwin.Processor_Type.assert_called_once()

    def test_reboot_works_fine(self):
        """ Test reboot function."""
        self._adwin._adwin.Test_Version = Mock(return_value=0)
        self._adwin._adwin.Processor_Type = Mock(return_value="T12.1")
        self._adwin._adwin.ADwindir = os.path.split(os.path.abspath(adwin.__file__))[0]
        self._adwin._boot_file = "adwin.py"
        with patch("os.path.isfile", return_value=True) as p:
            p.start()
            self._adwin.reboot()

        p.clean()
        self._adwin._adwin.Boot.assert_called_once()
        self._adwin._adwin.Processor_Type.assert_called_once()
        self._adwin._adwin.Test_Version.assert_called_once()

    def test_reboot_exception(self):
        """ Test reboot function. It raises an QMI_InstrumentException due to not mocking Test_Version """
        self._adwin._adwin.Processor_Type = Mock(return_value="T12")
        self._adwin._adwin.ADwindir = os.path.split(os.path.abspath(adwin.__file__))[0]
        self._adwin._boot_file = "adwin.py"
        with self.assertRaises(QMI_InstrumentException):
            self._adwin.reboot()

        self._adwin._adwin.Processor_Type.assert_called_once()

    def test_reboot_wrong_file_path(self):
        """ Test reboot function. It raises an QMI_InstrumentException due to not mocking Test_Version """
        self._adwin._adwin.ADwindir = ""
        self._adwin._boot_file = "adwin.py"
        with self.assertRaises(QMI_InstrumentException):
            self._adwin.reboot()

    def test_get_workload(self):
        """ Test get_workload function. """
        expected = 0
        self._adwin._adwin.Workload = Mock(return_value=expected)
        ans = self._adwin.get_workload()
        self.assertEqual(ans, expected)

    def test_load_process(self):
        """ Test load_process function. """
        self._adwin._adwin.Load_Process = Mock()
        self._adwin.load_process("bin_file")
        self._adwin._adwin.Load_Process.assert_called_once()

    def test_start_process(self):
        """ Test start_process function. """
        self._adwin._adwin.Process_Status = Mock(return_value=0)
        self._adwin._adwin.Start_Process = Mock()
        self._adwin.start_process(1)
        self._adwin._adwin.Process_Status.assert_called_once()
        self._adwin._adwin.Start_Process.assert_called_once()

    def test_start_process_number_out_of_range(self):
        """ Test start_process function with wrong process number inputs """
        numbers = [0, 2]
        for number in numbers:
            with self.assertRaises(ValueError):
                self._adwin.start_process(number)

    def test_start_process_raises_exception_status(self):
        """ Test start_process function raises exception. """
        self._adwin._adwin.Process_Status = Mock(return_value=1)
        with self.assertRaises(QMI_InstrumentException):
            self._adwin.start_process(1)

    def test_stop_process(self):
        """ Test stop_process functions """
        self._adwin._adwin.Stop_Process = Mock(return_value=0)
        self._adwin.stop_process(1)
        self._adwin._adwin.Stop_Process.assert_called_once()

    def test_stop_process_number_out_of_range(self):
        """ Test stop_process function with wrong process number inputs """
        numbers = [0, 2]
        for number in numbers:
            with self.assertRaises(ValueError):
                self._adwin.stop_process(number)

    def test_wait_for_process(self):
        """ Test wait_for_process function """
        expected = 2
        number, timeout = 1, 0.1
        self._adwin._adwin.Process_Status = Mock()
        self._adwin._adwin.Process_Status.side_effect = [1, 0]  # has to wait once
        self._adwin.wait_for_process(number, timeout)
        self._adwin._adwin.Process_Status.assert_called_with(1)
        self.assertEqual(self._adwin._adwin.Process_Status.call_count, expected)

    def test_wait_for_process_number_out_of_range(self):
        """ Test wait_for_process function """
        numbers = [0, 2]
        for number in numbers:
            with self.assertRaises(ValueError):
                self._adwin.wait_for_process(number, 0.0)

    def test_wait_for_process_timeout_exception(self):
        """ Test wait_for_process function """
        number, timeout = 1, 0.01
        self._adwin._adwin.Process_Status = Mock()
        self._adwin._adwin.Process_Status.side_effect = [1, 1, 0]  # has to wait twice
        with self.assertRaises(QMI_TimeoutException):
            self._adwin.wait_for_process(number, timeout)

    def test_is_process_running_true(self):
        """ Test is_process_running function when process is running """
        self._adwin._adwin.Process_Status = Mock(return_value=1)
        ans = self._adwin.is_process_running(1)
        self.assertTrue(ans)

    def test_is_process_running_false(self):
        """ Test is_process_running function when process is not running """
        self._adwin._adwin.Process_Status = Mock(return_value=0)
        ans = self._adwin.is_process_running(1)
        self.assertFalse(ans)

    def test_is_process_running_wrong_slot_index(self):
        """ Test is_process_running with invalid slot index number """
        with self.assertRaises(ValueError):
            self._adwin.is_process_running(0)

    def test_get_par(self):
        """ Test get_par function """
        expected = 1
        self._adwin._adwin.Get_Par = Mock(return_value=expected)
        ans = self._adwin.get_par(1)
        self.assertEqual(ans, expected)

    def test_get_par_index_out_of_range(self):
        """ Test get_par function excepts when input index is out of range """
        indexes = [0, 3]
        for index in indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_par(index)

    def test_get_fpar(self):
        """ Test get_fpar function """
        expected = 1.0
        self._adwin._adwin.Get_FPar_Double = Mock(return_value=expected)
        ans = self._adwin.get_fpar(1)
        self.assertEqual(ans, expected)

    def test_get_fpar_index_out_of_range(self):
        """ Test get_fpar function excepts when input index is out of range """
        indexes = [0, 3]
        for index in indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_fpar(index)

    def test_get_par_block(self):
        """ test get_par_block function """
        par_first, par_count = 1, 2
        expected = [1, 2]
        self._adwin._adwin.Get_Par_Block = Mock(return_value=expected)
        ans = self._adwin.get_par_block(par_first, par_count)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

        self.assertIsInstance(ans, np.ndarray)

    def test_get_par_block_wrong_first_index(self):
        """ test get_par_block excepts when parameter first index is invalid """
        par_firsts = [0, 3]
        par_count = 2
        for par_first in par_firsts:
            with self.assertRaises(ValueError):
                self._adwin.get_par_block(par_first, par_count)

    def test_get_par_block_count_too_large(self):
        """ test get_par_block excepts when parameter count is too large """
        par_first = 1
        par_count = 3
        with self.assertRaises(ValueError):
            self._adwin.get_fpar_block(par_first, par_count)

    def test_get_fpar_block(self):
        """ test get_fpar_block function """
        par_first, par_count = 1, 2
        expected = [1.0, 2.0]
        self._adwin._adwin.Get_FPar_Block_Double = Mock(return_value=expected)
        ans = self._adwin.get_fpar_block(par_first, par_count)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

        self.assertIsInstance(ans, np.ndarray)

    def test_get_fpar_block_wrong_first_index(self):
        """ test get_fpar_block excepts when parameter first index is invalid """
        par_firsts = [0, 3]
        par_count = 2
        for par_first in par_firsts:
            with self.assertRaises(ValueError):
                self._adwin.get_fpar_block(par_first, par_count)

    def test_get_fpar_block_count_too_large(self):
        """ test get_par_block excepts when parameter count is too large """
        par_first = 1
        par_count = 3
        with self.assertRaises(ValueError):
            self._adwin.get_fpar_block(par_first, par_count)

    def test_set_par(self):
        """ test set_par """
        par_idx, value = 1, 0
        self._adwin._adwin.Set_Par = Mock()
        self._adwin.set_par(par_idx, value)

        self._adwin._adwin.Set_Par.assert_called_once_with(par_idx, value)

    def test_set_par_index_out_of_range(self):
        """ test set_par raises exception when parameter index is out of range """
        par_indexes = [0, 3]
        value = 1
        for par_idx in par_indexes:
            with self.assertRaises(ValueError):
                self._adwin.set_par(par_idx, value)

    def test_set_par_value_not_int(self):
        """ test set_par raises exception when parameter value is not an integer """
        par_idx = 1
        values = ["3", 1.0, None]  # Note: booleans True and False do not raise a TypeError!
        for value in values:
            with self.assertRaises(TypeError):
                self._adwin.set_par(par_idx, value)

    def test_set_fpar(self):
        """ test set_fpar """
        par_idx, value = 1, 0.0
        self._adwin._adwin.Set_FPar_Double = Mock()
        self._adwin.set_fpar(par_idx, value)

        self._adwin._adwin.Set_FPar_Double.assert_called_once_with(par_idx, value)

    def test_set_fpar_index_out_of_range(self):
        """ test set_fpar raises exception when parameter index is out of range """
        par_indexes = [0, 3]
        value = 1.0
        for par_idx in par_indexes:
            with self.assertRaises(ValueError):
                self._adwin.set_fpar(par_idx, value)

    def test_set_fpar_value_not_int(self):
        """ test set_fpar raises exception when parameter value is not an integer nor a float """
        par_idx = 1
        values = ["3", None]  # Note: booleans True and False do not raise a TypeError!
        for value in values:
            with self.assertRaises(TypeError):
                self._adwin.set_fpar(par_idx, value)

    def test_get_data_length(self):
        """ test get_data_length function """
        expected = 2
        par_idx = 3
        self._adwin._adwin.Data_Length = Mock(return_value=expected)
        ans = self._adwin.get_data_length(par_idx)
        self.assertEqual(ans, expected)

    def test_get_data_length_data_index_out_of_range(self):
        """ test get_data_length function raises an exception when data index is out of range """
        par_indexes = [0, 4]
        for par_idx in par_indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_data_length(par_idx)

    def test_get_data_long(self):
        """ test get_data function returning a long array """
        expected = [3, 4]
        data_idx, first_index, count = 1, 1, 2
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT8, "byte"])
        self._adwin._adwin.GetData_Long = Mock(return_value=expected)
        ans = self._adwin.get_data(data_idx, first_index, count)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

    def test_get_data_double(self):
        """ test get_data function returning a double array """
        expected = [3.0, 4.0]
        data_idx, first_index, count = 1, 1, 2
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_DOUBLE, "float64"])
        self._adwin._adwin.GetData_Double = Mock(return_value=expected)
        ans = self._adwin.get_data(data_idx, first_index, count)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

    def test_get_data_data_index_out_of_range(self):
        """ test get_data function raises an exception when data index is out of range """
        data_indexes = [0, 4]
        first_index, count = 1, 2
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_data(data_idx, first_index, count)

    def test_get_data_first_index_too_small(self):
        """ test get_data function raises an exception when first index is too small """
        data_idx, first_index, count = 1, 0, 2
        with self.assertRaises(ValueError):
            self._adwin.get_data(data_idx, first_index, count)

    def test_get_data_count_too_small(self):
        """ test get_data function raises an exception when count is too small """
        data_idx, first_index, count = 1, 1, 0
        with self.assertRaises(ValueError):
            self._adwin.get_data(data_idx, first_index, count)

    def test_get_data_invalid_index_type(self):
        """ See that QMI_InstrumentException gets raised with invalid index data type"""
        data_idx, first_index, count = 1, 1, 2
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_DOUBLE, "str"])
        with self.assertRaises(QMI_InstrumentException):
            self._adwin.get_data(data_idx, first_index, count)

    def test_get_full_data_array_long(self):
        """ test get_full_data function returning a long array """
        data_idx = 3
        expected = [3, 4]
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT8, "byte"])
        self._adwin._adwin.GetData_Long = Mock(return_value=expected)
        ans = self._adwin.get_full_data(data_idx)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

    def test_get_full_data_array_double(self):
        """ test get_full_data function returning a double array """
        data_idx = 3
        expected = [3.0, 4.0]
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_DOUBLE, "float64"])
        self._adwin._adwin.GetData_Long = Mock(return_value=expected)
        ans = self._adwin.get_full_data(data_idx)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

    def test_get_full_data_data_index_out_of_range(self):
        """ test get_full_data function raises an exception when data index is out of range """
        data_indexes = [0, 4]
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_full_data(data_idx)

    def test_set_data_long_list(self):
        """ test set_data function with a list of integers """
        data_idx, first_index, value = 3, 1, [1, 2, 3]
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT16, "short"])
        self._adwin._adwin.SetData_Long = Mock()
        self._adwin.set_data(data_idx, first_index, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetData_Long.assert_called_once()

    def test_set_data_float_list(self):
        """ test set_data function with a list of floats """
        data_idx, first_index, value = 3, 1, [1.0, 2.0, 3.0]
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_SINGLE, "float32"])
        self._adwin._adwin.SetData_Double = Mock()
        self._adwin.set_data(data_idx, first_index, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetData_Double.assert_called_once()

    def test_set_data_long_array(self):
        """ test set_data function with an array of integers """
        data_idx, first_index, value = 3, 1, np.array([1, 2, 3])
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT32, "int32"])
        self._adwin._adwin.SetData_Long = Mock()
        self._adwin.set_data(data_idx, first_index, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetData_Long.assert_called_once()

    def test_set_data_float_array(self):
        """ test set_data function with an array of floats """
        data_idx, first_index, value = 3, 1, np.array([1.0, 2.0, 3.0])
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_SINGLE, "float"])
        self._adwin._adwin.SetData_Double = Mock()
        self._adwin.set_data(data_idx, first_index, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetData_Double.assert_called_once()

    def test_set_data_int_array_with_invalid_value(self):
        """ test set_data function with an array of integers """
        data_idx, first_index, value = 3, 1, np.array([1, 2, None])
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT64, "int64"])
        self._adwin._adwin.SetData_Long = Mock()
        with self.assertRaises(ValueError):
            self._adwin.set_data(data_idx, first_index, value)

    def test_set_data_wrong_index(self):
        """ test set_data with wrong index number"""
        with self.assertRaises(ValueError):
            self._adwin.set_data(0, 1, np.ndarray([2]))

    def test_set_data_first_index_zero(self):
        """ test set_data with wrong first index number"""
        with self.assertRaises(ValueError):
            self._adwin.set_data(1, 0, np.ndarray([2]))

    def test_get_fifo_filled(self):
        """ Test function get_fifo_filled """
        data_idx = 3
        expected = 109
        self._adwin._adwin.Fifo_Full = Mock(return_value=expected)
        ans = self._adwin.get_fifo_filled(data_idx)

        self.assertEqual(ans, expected)

    def test_get_fifo_filled_data_index_out_of_range(self):
        """ Test function get_fifo_filled raises an exception when data index is out of range """
        data_indexes = [0, 4]
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_fifo_filled(data_idx)

    def test_get_fifo_room(self):
        """ Test function get_fifo_room """
        data_idx = 3
        expected = 91
        self._adwin._adwin.Fifo_Empty = Mock(return_value=expected)
        ans = self._adwin.get_fifo_room(data_idx)

        self.assertEqual(ans, expected)

    def test_get_fifo_room_data_index_out_of_range(self):
        """ Test function get_fifo_room raises an exception when data index is out of range """
        data_indexes = [0, 4]
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.get_fifo_room(data_idx)

    def test_read_fifo_long(self):
        """ test read_fifo function returning a long array """
        expected = [3, 4]
        data_idx, count = 1, 2
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT64, "int64"])
        self._adwin._adwin.GetFifo_Long = Mock(return_value=expected)
        ans = self._adwin.read_fifo(data_idx, count)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

    def test_read_fifo_double(self):
        """ test read_fifo function returning a double array """
        expected = [3.0, 4.0]
        data_idx, count = 1, 2
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_DOUBLE, "float64"])
        self._adwin._adwin.GetFifo_Double = Mock(return_value=expected)
        ans = self._adwin.read_fifo(data_idx, count)
        for e in range(len(expected)):
            self.assertEqual(ans[e], expected[e])

    def test_read_fifo_data_index_out_of_range(self):
        """ test read_fifo function raises an exception when data index is out of range """
        data_indexes = [0, 4]
        count = 2
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.read_fifo(data_idx, count)

    def test_write_fifo_long_list(self):
        """ test write_fifo function with a list of integers """
        data_idx, value = 3, [1, 2, 3]
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT16, "short"])
        self._adwin._adwin.SetFifo_Long = Mock()
        self._adwin.write_fifo(data_idx, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetFifo_Long.assert_called_once()

    def test_write_fifo_float_list(self):
        """ test write_fifo function with a list of floats """
        data_idx, value = 3, [1.0, 2.0, 3.0]
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_SINGLE, "float32"])
        self._adwin._adwin.SetFifo_Double = Mock()
        self._adwin.write_fifo(data_idx, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetFifo_Double.assert_called_once()

    def test_write_fifo_long_array(self):
        """ test write_fifo function with an array of integers """
        data_idx, value = 3, np.array([1, 2, 3])
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT64, "int64"])
        self._adwin._adwin.SetFifo_Long = Mock()
        self._adwin.write_fifo(data_idx, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetFifo_Long.assert_called_once()

    def test_write_fifo_float_array(self):
        """ test write_fifo function with an array of floats """
        data_idx, value = 3, np.array([1.0, 2.0, 3.0])
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_DOUBLE, "float64"])
        self._adwin._adwin.SetFifo_Double = Mock()
        self._adwin.write_fifo(data_idx, value)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.SetFifo_Double.assert_called_once()

    def test_write_fifo_int_array_with_invalid_value(self):
        """ test write_fifo function with an array of integers """
        data_idx, value = 3, np.array([1, 2, "tripel"])
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT32, "long"])
        self._adwin._adwin.SetFifo_Long = Mock()
        with self.assertRaises(ValueError):
            self._adwin.write_fifo(data_idx, value)

    def test_write_fifo_invalid_index(self):
        """ test write_fifo function with wrong index number"""
        with self.assertRaises(ValueError):
            self._adwin.write_fifo(201, np.array([3]))

    @patch('sys.platform', 'linux1')
    def test_set_file_to_data_linux(self):
        """ test set_file_to_data function in patched linux environment """
        expected_adwin_data_type = 3
        data_idx, first_index, file_path = 3, 1, os.path.abspath(__file__)
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT32, "long"])
        self._adwin._adwin.File2Data = Mock()
        self._adwin.set_file_to_data(data_idx, first_index, file_path)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.File2Data.assert_called_once_with(file_path, expected_adwin_data_type, data_idx, first_index)

    @patch('sys.platform', 'win32')
    def test_set_file_to_data_windows(self):
        """ test set_file_to_data function in patched windows environment """
        expected_adwin_data_type = 2
        data_idx, first_index, file_path = 3, 1, os.path.abspath(__file__)
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT32, "int32"])
        self._adwin._adwin.File2Data = Mock()
        self._adwin.set_file_to_data(data_idx, first_index, file_path)

        self._adwin._adwin.Data_Type.assert_called_once()
        self._adwin._adwin.File2Data.assert_called_once_with(file_path, expected_adwin_data_type, data_idx, first_index)

    def test_set_file_to_data_index_out_of_range(self):
        """ test set_file_to_data function raises an exception when data index is out of range """
        data_indexes = [0, 4]
        first_index, file_path = 1, os.path.abspath(__file__)
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.set_file_to_data(data_idx, first_index, file_path)

    def test_set_file_to_data_first_index_too_small(self):
        """ test set_file_to_data function raises an exception when data index is out of range """
        data_indexes = [1, 2]
        first_index, file_path = 0, os.path.abspath(__file__)
        for data_idx in data_indexes:
            with self.assertRaises(ValueError):
                self._adwin.set_file_to_data(data_idx, first_index, file_path)

    def test_set_file_to_data_wrong_index_type(self):
        """ test set_file_to_data function raises an exception when data index type is not an integer """
        # Suppress logging.
        logging.getLogger("qmi.instruments.adwin.adwin").setLevel(logging.CRITICAL)
        expected = "QMI_InstrumentException(\'Target data array should be of type long.\')"
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_DOUBLE, "float32"])
        data_idx = 3.0
        first_index, file_path = 1, os.path.abspath(__file__)
        with self.assertRaises(QMI_InstrumentException) as exc:
            self._adwin.set_file_to_data(data_idx, first_index, file_path)

        self.assertEqual(repr(exc.exception), expected)

    def test_set_file_to_data_file_is_missing(self):
        """ test set_file_to_data function raises an exception when the file specified is missing """
        # Suppress logging.
        logging.getLogger("qmi.instruments.adwin.adwin").setLevel(logging.CRITICAL)
        expected = "QMI_InstrumentException(\'The specified file does not exist.\')"
        self._adwin._adwin.Data_Type = Mock(return_value=[ADWIN_DATATYPE_INT16, "short"])
        data_idx, first_index, file_path = 3, 1, "niet_bestaand.bestand"
        with self.assertRaises(QMI_InstrumentException) as exc:
            self._adwin.set_file_to_data(data_idx, first_index, file_path)

        self.assertEqual(repr(exc.exception), expected)


if __name__ == "__main__":
    unittest.main()
