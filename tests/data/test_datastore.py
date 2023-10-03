#! /usr/bin/env python3

"""Test datastore module."""

import unittest

import os
import inspect
import json
import time

from h5py._hl.files import File

from qmi.data.datastore import DataFolder, DataStore
from qmi.core.config_defs import CfgLogging
from qmi.data.dataset import DataSet
import qmi.core.exceptions

def _create_config(config_struct_class):
    config = {item[0]: item[1] for item in inspect.getmembers(config_struct_class()) if "__" not in item[0]}
    return config

def _create_dataset():
    ds = DataSet("my_dataset", shape=(2, 8, 3))

    ds.set_axis_label(0, "X")
    ds.set_axis_unit(0, "um")
    ds.set_axis_label(1, "Z")
    ds.set_axis_unit(1, "mm")
    ds.set_column_label(0, "power")
    ds.set_column_unit(0, "mW")
    ds.set_column_label(1, "countrate")
    ds.set_column_unit(1, "kHz")
    ds.set_column_label(2, "temperature")
    ds.set_column_unit(2, "K")
    
    return ds


class TestDataFolder(unittest.TestCase):

    def setUp(self) -> None:
        self.datafolder = DataFolder(os.getcwd(), "test", None, None)

    def tearDown(self) -> None:
        del self.datafolder

    def test_01_create_config_json_file(self):
        """Create a JSON file from given input `configstruct` class"""
        # Arrange
        expected_config = _create_config(CfgLogging)
        # Act
        self.datafolder.write_config(CfgLogging())
        # Assert
        try:
            with open(os.path.join(os.getcwd(), "test.json")) as f:
                written_config = json.load(f)

            self.assertDictEqual(expected_config, written_config)

        finally:
            os.remove(os.path.join(os.getcwd(), "test.json"))

    def test_02_make_file_copy(self):
        """Make a copy of a file"""
        # Arrange
        name = "test.file"
        expected_copied_file = os.path.join(os.getcwd(), name)
        tmp_folder = os.path.join(os.getcwd(), "tmp")
        os.mkdir(tmp_folder)
        file_to_copy = os.path.join(tmp_folder, name)
        try:
            with open(file_to_copy, "w") as f:
                f.write("bla")

            # act
            self.datafolder.copy_file(file_to_copy)

            # assert
            self.assertTrue(os.path.isfile(expected_copied_file))

        finally:
            os.remove(file_to_copy)
            os.removedirs(tmp_folder)
            os.remove(expected_copied_file)

    def test_03_write_dataset_to_hdf5(self):
        """Write a data set as HDF5 file.
        """
        # Arrange
        dataset = _create_dataset()
        expected_file = os.path.join(os.getcwd(), dataset.name + ".h5")
        # Act
        try:
            self.datafolder.write_dataset(dataset)
            # Assert
            self.assertTrue(os.path.isfile(expected_file))

        finally:
            os.remove(expected_file)

    def test_04_write_dataset_to_dat(self):
        """Write a data set as DAT file.
        """
        # Arrange
        dataset = _create_dataset()
        expected_file = os.path.join(os.getcwd(), dataset.name + ".dat")
        # Act
        try:
            self.datafolder.write_dataset(dataset, file_format="text")
            # Assert
            self.assertTrue(os.path.isfile(expected_file))

        finally:
            os.remove(expected_file)

    def test_05_write_dataset_wrong_file_format_raises_exception(self):
        """Wrong file format string raises an expection
        """
        # Arrange
        dataset = _create_dataset()
        # Act and assert
        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            self.datafolder.write_dataset(dataset, file_format="boh")

    def test_06_read_dataset_in_hdf5(self):
        """See that we can read in a data set in HDF5 format"""
        # Arrange
        expected_dataset = _create_dataset()
        expected_file = os.path.join(os.getcwd(), expected_dataset.name + ".h5")
        try:
            self.datafolder.write_dataset(expected_dataset)
            # Act
            dataset = self.datafolder.read_dataset(expected_dataset.name)
            # Assert
            self.assertEqual(expected_dataset.name, dataset.name)
            self.assertDictEqual(expected_dataset.attrs, dataset.attrs)
            self.assertListEqual(expected_dataset.axis_label, dataset.axis_label)
            self.assertListEqual(expected_dataset.axis_scale, dataset.axis_scale)
            self.assertListEqual(expected_dataset.axis_unit, dataset.axis_unit)
            self.assertListEqual(expected_dataset.column_label, dataset.column_label)
            self.assertListEqual(expected_dataset.column_unit, dataset.column_unit)
            self.assertEqual(expected_dataset.data.min(), dataset.data.min())
            self.assertEqual(expected_dataset.data.max(), dataset.data.max())
            self.assertEqual(expected_dataset.data.size, dataset.data.size)
            self.assertEqual(expected_dataset.timestamp, dataset.timestamp)

        finally:
            os.remove(expected_file)

    def test_07_read_dataset_in_dat(self):
        """See that we can read in a data set in DAT format"""
        # Arrange
        expected_dataset = _create_dataset()
        expected_file = os.path.join(os.getcwd(), expected_dataset.name + ".dat")
        try:
            self.datafolder.write_dataset(expected_dataset, file_format="text")
            # Act
            dataset = self.datafolder.read_dataset(expected_dataset.name)
            # Assert
            self.assertEqual(expected_dataset.name, dataset.name)
            self.assertDictEqual(expected_dataset.attrs, dataset.attrs)
            self.assertListEqual(expected_dataset.axis_label, dataset.axis_label)
            self.assertListEqual(expected_dataset.axis_scale, dataset.axis_scale)
            self.assertListEqual(expected_dataset.axis_unit, dataset.axis_unit)
            self.assertListEqual(expected_dataset.column_label, dataset.column_label)
            self.assertListEqual(expected_dataset.column_unit, dataset.column_unit)
            self.assertEqual(expected_dataset.data.min(), dataset.data.min())
            self.assertEqual(expected_dataset.data.max(), dataset.data.max())
            self.assertEqual(expected_dataset.data.size, dataset.data.size)
            self.assertEqual(expected_dataset.timestamp, dataset.timestamp)

        finally:
            os.remove(expected_file)

    def test_08_read_dataset_wrong_file_name_raises_exception(self):
        """Wrong file name string raises an expection
        """
        # Act and assert
        with self.assertRaises(FileNotFoundError):
            self.datafolder.read_dataset("boh")

    def test_09_make_hdf5_file(self):
        """Make a hdf5 file"""
        # Arrange
        name = "expected"
        expected_file = os.path.join(os.getcwd(), name + ".h5")
        # Act
        try:
            with self.datafolder.make_hdf5file(name) as hdf5_file:
                self.assertTrue(os.path.isfile(expected_file))
                self.assertEqual(type(hdf5_file), File)

        finally:
            os.remove(expected_file)

    def test_10_make_hdf5_file_raises_exception_with_non_latin_characters(self):
        """Trying to make a file with non-latin characters raises and exception"""
        # Arrange
        name = "väärin"
        # Act and Assert
        with self.assertRaises(ValueError):
            self.datafolder.make_hdf5file(name)

    def test_11_open_hdf5_file(self):
        """Open a hdf5 file"""
        # Arrange
        name = "expected"
        expected_file = os.path.join(os.getcwd(), name + ".h5")
        # Act and Assert
        try:
            with self.datafolder.make_hdf5file(name):
                self.assertTrue(os.path.isfile(expected_file))

            with self.datafolder.open_hdf5file(name) as hdf5_file:
                self.assertEqual(type(hdf5_file), File)

        finally:
            os.remove(expected_file)

    def test_12_open_hdf5_file_raises_exception_with_non_latin_characters(self):
        """Opening a file with non-latin characters raises and exception"""
        # Arrange
        name = "väärin"
        # Act and Assert
        with self.assertRaises(ValueError):
            self.datafolder.open_hdf5file(name)

    def test_13_write_dataset_again(self):
        """Write a data set if already exists.
        """
        # Arrange
        dataset = _create_dataset()
        expected_file = os.path.join(os.getcwd(), dataset.name + ".h5")
        self.datafolder.write_dataset(dataset)
        # Act
        try:
            # Assert
            with self.assertRaises(FileExistsError):
                self.datafolder.write_dataset(dataset)
            self.assertTrue(os.path.isfile(expected_file))
        finally:
            os.remove(expected_file)

    def test_14_write_dataset_again(self):
        """Write a data set if already exists, but with overwrite flag set.
        """
        # Arrange
        dataset = _create_dataset()
        expected_file = os.path.join(os.getcwd(), dataset.name + ".h5")
        self.datafolder.write_dataset(dataset)
        # Act
        try:
            self.datafolder.write_dataset(dataset, overwrite=True)
            # Assert
            self.assertTrue(os.path.isfile(expected_file))
        finally:
            os.remove(expected_file)


class TestDataFolderNoLabel(unittest.TestCase):

    def setUp(self) -> None:
        self.datafolder = DataFolder(os.getcwd(), None, None, None)

    def tearDown(self) -> None:
        del self.datafolder

    def test_01_create_config_json_file(self):
        """Create a JSON file from given input `configstruct` class with default name 'config.json' if no label
        is given.
        """
        # Arrange
        expected_file = os.path.join(os.getcwd(), "config.json")
        # Act
        self.datafolder.write_config(CfgLogging())
        # Assert
        try:
            self.assertTrue(os.path.isfile(expected_file))

        finally:
            os.remove(expected_file)


class TestDataStore(unittest.TestCase):

    def setUp(self) -> None:
        self.datastore = DataStore(os.getcwd())

    def tearDown(self) -> None:
        del self.datastore

    def test_01_make_folder_only_name_as_input(self):
        """Make a new datastore folder in the base folder and that a DataFolder instance is returned."""
        # Arrange
        name = "temp"
        tm = time.localtime(time.time())
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        try:
            # Act
            datafolder = self.datastore.make_folder(name)
            # We need to check for the rare case that the second just flipped between arranging the test and making
            # the folder. We ignore the super-rare case of this second being exactly at midnight, changing date also
            if not os.path.isdir(expected_folder):
                # Update to 'next' second
                tm = time.localtime(time.time())
                time_str = time.strftime("%H%M%S", tm)
                expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))

            # Assert
            self.assertTrue(os.path.isdir(expected_folder))
            self.assertEqual(type(datafolder), DataFolder)

        finally:
            os.removedirs(expected_folder)
            # os.removedirs(day_folder)

    def test_02_make_folder_with_timestamp_as_input(self):
        """Make a new datastore folder in the base folder and that a DataFolder instance is returned."""
        # Arrange
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        try:
            # Act
            time.sleep(1)  # Sleep to change the current time timestamp
            datafolder = self.datastore.make_folder(name, posix_time)

            # Assert
            self.assertTrue(os.path.isdir(expected_folder))
            self.assertEqual(type(datafolder), DataFolder)

        finally:
            os.removedirs(expected_folder)

    def test_03_make_folder_with_date_and_time_as_inputs(self):
        """Make a new datastore folder in the base folder and that a DataFolder instance is returned."""
        # Arrange
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        try:
            # Act
            time.sleep(1)  # Sleep to change the current time timestamp
            datafolder = self.datastore.make_folder(name, date_str=date_str, time_str=time_str)

            # Assert
            self.assertTrue(os.path.isdir(expected_folder))
            self.assertEqual(type(datafolder), DataFolder)

        finally:
            os.removedirs(expected_folder)

    def test_04_make_folder_with_date_or_time_only_as_input_raises_exception(self):
        """See that making a new data folder ends with exception if both date and time are not present"""
        # Arrange
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        # Act & Assert
        with self.assertRaises(ValueError):
            self.datastore.make_folder(name, date_str=date_str)

        with self.assertRaises(ValueError):
            self.datastore.make_folder(name, time_str=time_str)

    def test_05_make_folder_with_wrong_date_or_time_as_input_raises_exception(self):
        """See that making a new data folder ends with exception if both date and time are not present"""
        # Arrange
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        bad_date_strings = [date_str[:-1], date_str + date_str[0], "1234567A"]
        bad_time_strings = [time_str[:-1], time_str + time_str[0], "65432I"]
        # Act & Assert
        for bad_date in bad_date_strings:
            with self.assertRaises(ValueError):
                self.datastore.make_folder(name, date_str=bad_date, time_str=time_str)

        for bad_time in bad_time_strings:
            with self.assertRaises(ValueError):
                self.datastore.make_folder(name, date_str=date_str, time_str=bad_time)

    def test_06_make_folder_with_missing_label_raises_exception(self):
        """See that making a new data folder ends with exception if proper label is not present"""
        # Arrange
        bad_names = ["", None, True, 0x04, "yö-öylätti"]
        posix_time = time.time()
        # Act & Assert
        for bad_name in bad_names:
            with self.assertRaises(ValueError):
                self.datastore.make_folder(bad_name, posix_time)

    def test_07_make_folder_raises_exception_when_directory_already_exists(self):
        """See that making the new data folder raises exception if `time` folder is already created"""
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        try:
            os.mkdir(day_folder)
            os.mkdir(expected_folder)
            # Act & Assert
            with self.assertRaises(FileExistsError):
                self.datastore.make_folder(name, date_str=date_str, time_str=time_str)

        finally:
            os.removedirs(expected_folder)

    def test_08_make_folder_only_name_as_input(self):
        """Make a new datastore folder in the base folder and that a DataFolder instance is returned."""
        # Arrange
        name = "temp"
        tm = time.localtime(time.time())
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        try:
            # Act
            datafolder = self.datastore.make_folder(name)
            # We need to check for the rare case that the second just flipped between arranging the test and making
            # the folder. We ignore the super-rare case of this second being exactly at midnight, changing date also
            if not os.path.isdir(expected_folder):
                # Update to 'next' second
                tm = time.localtime(time.time())
                time_str = time.strftime("%H%M%S", tm)
                expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))

            # Assert
            self.assertTrue(os.path.isdir(expected_folder))
            self.assertEqual(type(datafolder), DataFolder)

        finally:
            os.removedirs(expected_folder)
            # os.removedirs(day_folder)

    def test_09_get_folder_with_name_date_and_time_as_inputs(self):
        """Get a datastore folder with the given input values."""
        # Arrange
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        self.datastore.make_folder(name, date_str=date_str, time_str=time_str)
        try:
            # Act
            datafolder = self.datastore.get_folder(name, date_str, time_str)
            # Assert
            self.assertEqual(type(datafolder), DataFolder)

        finally:
            os.removedirs(expected_folder)

    def test_10_get_folder_raises_exception_for_not_existing_folder(self):
        """See that exception is raised if a non-existing folder is tried to be found."""
        # Arrange
        name = "test"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        # Act & Assert
        with self.assertRaises(FileNotFoundError):
            self.datastore.get_folder(name, date_str, time_str)

    def test_11_get_folder_from_path(self):
        """Get a datastore folder with the given input values."""
        # Arrange
        name = "temp"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        self.datastore.make_folder(name, date_str=date_str, time_str=time_str)
        try:
            # Act
            datafolder = self.datastore.get_folder_from_path(expected_folder)
            # Assert
            self.assertEqual(type(datafolder), DataFolder)

        finally:
            os.removedirs(expected_folder)

    def test_12_get_folder_from_path_raises_exception_for_not_existing_folder(self):
        """See that exception is raised if a non-existing folder is tried to be found."""
        # Arrange
        name = "test"
        posix_time = time.time()
        tm = time.localtime(posix_time)
        date_str = time.strftime("%Y%m%d", tm)
        time_str = time.strftime("%H%M%S", tm)
        day_folder = os.path.join(os.getcwd(), date_str)
        expected_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
        # Act & Assert
        with self.assertRaises(FileNotFoundError):
            self.datastore.get_folder_from_path(expected_folder)

    def test_13_list_folders(self):
        """Get a list of data folders created with specific label"""
        # Arrange
        name = "test"
        date_strings = ["20122012", "20022002", "20111102"]
        time_str = "000102"
        for date_str in date_strings:
            self.datastore.make_folder(name, date_str=date_str, time_str=time_str)

        # Act
        try:
            data_folders = self.datastore.list_folders(name)
            # Assert
            self.assertEqual(len(data_folders), len(date_strings))
            for data_folder in data_folders:
                self.assertEqual(type(data_folder), DataFolder)
                self.assertEqual(os.path.split(data_folder.folder_path)[-1], "{}_{}".format(time_str, name))
                self.assertIn(data_folder.date_str, date_strings)
                self.assertEqual(data_folder.label, name)
                self.assertEqual(data_folder.time_str, time_str)

        finally:
            for date_str in date_strings:
                day_folder = os.path.join(os.getcwd(), date_str)
                time_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
                os.removedirs(time_folder)

    def test_14_find_latest_folder(self):
        """Get a the latest data folder from created data folders with specific label"""
        # Arrange
        name = "test"
        date_strings = ["20122012", "20022002", "20111102"]
        time_strings = ["000102", "011234", "235959"]
        for date_str in date_strings:
            for time_str in time_strings:
                self.datastore.make_folder(name, date_str=date_str, time_str=time_str)

        latest_day = sorted(date_strings)[-1]
        latest_time = sorted(time_strings)[-1]

        # Act
        try:
            data_folder = self.datastore.find_latest_folder(name)
            # Assert
            self.assertEqual(type(data_folder), DataFolder)
            self.assertEqual(os.path.split(data_folder.folder_path)[-1], "{}_{}".format(latest_time, name))
            self.assertEqual(data_folder.date_str, latest_day)
            self.assertEqual(data_folder.label, name)
            self.assertEqual(data_folder.time_str, latest_time)

        finally:
            for date_str in date_strings:
                for time_str in time_strings:
                    day_folder = os.path.join(os.getcwd(), date_str)
                    time_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
                    os.removedirs(time_folder)

    def test_15_find_latest_with_specific_date(self):
        """Get a the latest data folder from created data folders with specific label and date"""
        # Arrange
        name = "test"
        date_strings = ["20122012", "20022002", "20111102"]
        time_strings = ["000102", "011234", "235959"]
        for date_str in date_strings:
            for time_str in time_strings:
                self.datastore.make_folder(name, date_str=date_str, time_str=time_str)

        expected_day = date_strings[-1]
        latest_time = sorted(time_strings)[-1]

        # Act
        try:
            data_folder = self.datastore.find_latest_folder(name, expected_day)
            # Assert
            self.assertEqual(type(data_folder), DataFolder)
            self.assertEqual(os.path.split(data_folder.folder_path)[-1], "{}_{}".format(latest_time, name))
            self.assertEqual(data_folder.date_str, expected_day)
            self.assertEqual(data_folder.label, name)
            self.assertEqual(data_folder.time_str, latest_time)

        finally:
            for date_str in date_strings:
                for time_str in time_strings:
                    day_folder = os.path.join(os.getcwd(), date_str)
                    time_folder = os.path.join(day_folder, "{}_{}".format(time_str, name))
                    os.removedirs(time_folder)


if __name__ == "__main__":
    unittest.main()
