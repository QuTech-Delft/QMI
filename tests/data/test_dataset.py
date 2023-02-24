#! /usr/bin/env python3

"""Test DataSet class."""

import io
import unittest

import numpy as np
import h5py

import qmi.data.dataset
from qmi.data.dataset import DataSet


def _internal_create_dataset(name, shape, dtype, add_labels, add_scale, add_attributes):
    """Internal helper function to create a dataset."""

    if np.dtype(dtype).kind == 'i':
        data = dtype(1000 * np.random.random(shape))
    else:
        data = dtype(1 - 2 * np.random.random(shape))

    ds = DataSet(name, data=data)

    if add_labels:
        for axis in range(len(shape) - 1):
            ds.set_axis_label(axis, "axis {} label".format(axis))
            ds.set_axis_unit(axis, "axis {} unit".format(axis))
        for col in range(shape[-1]):
            ds.set_column_label(col, "column {} label".format(col))
            ds.set_column_unit(col, "column {} unit".format(col))

    if add_scale:
        for axis in range(len(shape) - 1):
            scale = np.random.random() * np.arange(shape[axis])
            ds.set_axis_scale(axis, scale)

    if add_attributes:
        ds.attrs["simple_int"] = 123
        ds.attrs["big_int"] = -100000000000
        ds.attrs["simple_float"] = np.pi
        ds.attrs["big_float"] = -1.0e80
        ds.attrs["simple_str"] = "hello"
        ds.attrs["tricky_str"] = "a tricky:string \\to \"encode'"

    return ds


class TestDataSet(unittest.TestCase):

    def test_01_raise_exception_on_wrong_data_type(self):
        """See that an exception is raised if data is not np.array type."""
        with self.assertRaises(TypeError):
            DataSet("empty_dataset", shape=(8, 3), data=[1.0, 2.0, 3.0])

    def test_02_raise_exception_on_wrong_shape(self):
        """See that an exception is raised if data shape is not correct."""
        with self.assertRaises(ValueError) as exc:
            DataSet("empty_dataset", shape=(8, 3), data=np.array([[1.0, 2.0, 3.0]]))

        self.assertEqual(str(exc.exception), "Data does not match specified shape")

    def test_03_raise_exception_on_wrong_data_type(self):
        """See that an exception is raised if data type is not correct."""
        with self.assertRaises(ValueError) as exc:
            DataSet("empty_dataset", shape=(1, 3), dtype=int, data=np.array([[1.0, 2.0, 3.0]]))

        self.assertEqual(str(exc.exception), "Data does not match specified data type")

    def test_04_no_shape_nor_data_specified_raises_exception(self):
        """An exception must be raised if neither shape nor data is given as input"""
        with self.assertRaises(TypeError):
            DataSet("empty_dataset", shape=None, data=None)

    def test_05_data_dimensions_not_two_or_more(self):
        """An exception must be raised if neither data dimension and shape is less than 2"""
        with self.assertRaises(ValueError) as exc:
            DataSet("empty_dataset", shape=(3,), data=np.array([1.0, 2.0, 3.0]))

        self.assertEqual(str(exc.exception), "Dataset must have at least 2 axes")

    def test_06_data_dimension_invalid(self):
        """Zero (and negative) dimension values raise an exception"""
        with self.assertRaises(ValueError) as exc:
            DataSet("empty_dataset", shape=(1, 0), data=np.array([[]]))

        self.assertEqual(str(exc.exception), "Zero-size or negative size axes are not allowed")

    def test_10_create_empty_dataset(self):
        """Create a simple, empty DataSet instance."""

        ds = DataSet("empty_dataset", shape=(8, 3))

        self.assertEqual(ds.name, "empty_dataset")
        self.assertIsInstance(ds.data, np.ndarray)
        self.assertEqual(ds.data.shape, (8, 3))
        self.assertEqual(ds.data.dtype, np.float64)
        self.assertTrue(np.all(ds.data == 0))

        self.assertEqual(ds.axis_label, [""])
        self.assertEqual(ds.axis_unit, [""])
        self.assertEqual(ds.axis_scale, [None])
        self.assertEqual(ds.column_label, ["", "", ""])
        self.assertEqual(ds.column_unit, ["", "", ""])
        self.assertEqual(ds.attrs, {})

    def test_11_create_initialized_dataset(self):
        """Create a simple dataset from existing Numpy data."""

        data = np.sqrt(np.arange(10)).reshape(5, 2)
        ds = DataSet("my_dataset", data=data)

        self.assertEqual(ds.name, "my_dataset")
        self.assertIsInstance(ds.data, np.ndarray)
        self.assertEqual(ds.data.shape, (5, 2))
        self.assertEqual(ds.data.dtype, np.float64)
        self.assertTrue(np.all(ds.data == data))

    def test_20_labels(self):
        """Setting labels."""

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

        self.assertEqual(ds.name, "my_dataset")
        self.assertEqual(ds.axis_label, ["X", "Z"])
        self.assertEqual(ds.axis_unit, ["um", "mm"])
        self.assertEqual(ds.axis_scale, [None, None])
        self.assertEqual(ds.column_label, ["power", "countrate", "temperature"])
        self.assertEqual(ds.column_unit, ["mW", "kHz", "K"])

    def test_21_axis_scale(self):
        """Setting an axis scale."""

        ds = DataSet("my_dataset", shape=(2, 8, 3))

        ds.set_axis_scale(0, [0.1, 0.2])
        ds.set_axis_scale(1, 0.25 * np.arange(8))

        self.assertEqual(ds.name, "my_dataset")
        self.assertEqual(len(ds.axis_scale), 2)
        self.assertTrue(np.all(ds.axis_scale[0] == [0.1, 0.2]))
        self.assertTrue(np.all(ds.axis_scale[1] == 0.25 * np.arange(8)))

    def test_22_invalid_label(self):
        """Setting invalid labels raises exception."""

        ds = DataSet("my_dataset", shape=(2, 8, 3))

        with self.assertRaises(TypeError):
            ds.set_axis_label("0", "X")

        with self.assertRaises(ValueError):
            ds.set_axis_label(-1, "X")

    def test_23_invalid_axis_unit(self):
        """Setting invalid axis unit raises exception."""

        ds = DataSet("my_dataset", shape=(2, 8, 3))

        with self.assertRaises(TypeError):
            ds.set_axis_unit("0", "X")

        with self.assertRaises(ValueError):
            ds.set_axis_unit(-1, "X")

    def test_24_invalid_axis_scale(self):
        """Setting invalid axis unit raises exception."""

        ds = DataSet("my_dataset", shape=(2, 8, 3))

        with self.assertRaises(TypeError):
            ds.set_axis_scale("0", [0.1, 0.2])

        with self.assertRaises(ValueError) as exc:
            ds.set_axis_scale(-1, [0.1, 0.2])

        self.assertEqual(str(exc.exception), "Invalid value for parameter 'axis'")

        with self.assertRaises(ValueError) as exc:
            ds.set_axis_scale(0, [0.1, 0.2])
            ds.set_axis_scale(1, 0.25 * np.arange(7))

        self.assertEqual(str(exc.exception), "Invalid shape for scale array")

        with self.assertRaises(ValueError) as exc:
            ds.set_axis_scale(0, [0.1, np.nan])
            ds.set_axis_scale(1, 0.25 * np.arange(8))

        self.assertEqual(str(exc.exception), "Only finite values allowed on the axis scale")

    def test_25_invalid_column_label(self):
        """Setting invalid column labels raises exception."""

        ds = DataSet("my_dataset", shape=(2, 8, 3))

        with self.assertRaises(TypeError):
            ds.set_column_label("0", "X")

        with self.assertRaises(ValueError):
            ds.set_column_label(-1, "X")

    def test_26_invalid_column_unit(self):
        """Setting invalid column unit raises exception."""

        ds = DataSet("my_dataset", shape=(2, 8, 3))

        with self.assertRaises(TypeError):
            ds.set_column_unit("0", "X")

        with self.assertRaises(ValueError):
            ds.set_column_unit(-1, "X")

    def test_30_dataset_1col(self):
        """Create a 3-dimensional, 1-column dataset and setting labels."""

        data = np.arange(10).reshape(2, 5, 1)
        ds = DataSet("my_dataset", data=data)
        ds.set_axis_label(0, "X")
        ds.set_axis_label(1, "Y")
        ds.set_column_label(0, "Z")

        self.assertEqual(ds.name, "my_dataset")
        self.assertEqual(ds.data.shape, (2, 5, 1))
        self.assertEqual(ds.axis_label, ["X", "Y"])
        self.assertEqual(ds.axis_unit, ["", ""])
        self.assertEqual(ds.axis_scale, [None, None])
        self.assertEqual(ds.column_label, ["Z"])
        self.assertEqual(ds.column_unit, [""])
        self.assertEqual(ds.attrs, {})

    def test_40_write_hdf5_simple(self):
        """Writing a simple dataset as HDF5."""

        data = 1.4142 * (np.arange(24).reshape(8, 3) - 1)
        ds = DataSet("my_dataset", data=data)
        ds.axis_label[0] = "X axis"
        ds.axis_unit[0] = "mm"
        ds.column_label = ["red", "green", "blue"]
        ds.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds.set_axis_scale(0, scale_data)
        ds.attrs["hello"] = "world"
        ds.attrs["number"] = 2.71

        f = h5py.File("test.h5", "w", driver="core", backing_store=False)
        qmi.data.dataset.write_dataset_to_hdf5(ds, f)

        self.assertEqual(set(f.keys()), {"my_dataset", "my_dataset_axis0_scale"})
        self.assertEqual(f["my_dataset"].shape, (8, 3))
        self.assertEqual(f["my_dataset"].dtype, np.float64)
        self.assertTrue(np.all(data == f["my_dataset"]))

        self.assertEqual(f["my_dataset"].attrs["QMI_DataSet_axis0_label"], "X axis")
        self.assertEqual(f["my_dataset"].attrs["QMI_DataSet_axis0_unit"], "mm")
        self.assertEqual(f["my_dataset"].attrs["QMI_DataSet_column1_label"], "green")
        self.assertEqual(f["my_dataset"].attrs["QMI_DataSet_column1_unit"], "nm")

        self.assertEqual(f["my_dataset"].dims[0].label, "X axis")
        self.assertTrue(np.all(scale_data == f["my_dataset"].dims[0][0]))

        self.assertEqual(f["my_dataset"].attrs["hello"], "world")
        self.assertEqual(f["my_dataset"].attrs["number"], 2.71)

        f.close()

    def test_41_write_read_hdf5(self):
        """Writing and reading various datasets as HDF5."""

        f = h5py.File("test.h5", "w", driver="core", backing_store=False)
        datasets = []

        # Create datasets and write to file.
        for (name, shape, dtype) in [
                ("t1", (4, 4), np.float64),
                ("t2", (4, 4), np.float64),
                ("t3", (3, 3, 3, 3), np.float64),
                ("t4", (4, 4, 1), np.int32)]:
            ds = _internal_create_dataset(name,
                                          shape,
                                          dtype,
                                          add_labels=True,
                                          add_scale=True,
                                          add_attributes=True)
            datasets.append(ds)
            qmi.data.dataset.write_dataset_to_hdf5(ds, f)

        # Read back from file and verify.
        for ds in datasets:
            ds2 = qmi.data.dataset.read_dataset_from_hdf5(f[ds.name])
            self.assertEqual(ds2.name, ds.name)
            self.assertIsInstance(ds2.data, np.ndarray)
            self.assertEqual(ds2.data.shape, ds.data.shape)
            self.assertEqual(ds2.data.dtype, ds.data.dtype)
            self.assertTrue(np.all(ds2.data == ds.data))
            self.assertEqual(ds2.axis_label, ds.axis_label)
            self.assertEqual(ds2.axis_unit, ds.axis_unit)
            self.assertEqual(len(ds2.axis_scale), len(ds.axis_scale))
            for axis in range(len(ds.axis_scale)):
                if ds.axis_scale[axis] is None:
                    self.assertIsNone(ds2.axis_scale[axis])
                else:
                    self.assertTrue(np.all(ds2.axis_scale[axis] == ds.axis_scale[axis]))
            self.assertEqual(ds2.column_label, ds.column_label)
            self.assertEqual(ds2.column_unit, ds.column_unit)
            self.assertEqual(ds2.attrs, ds.attrs)

        f.close()

    def test_42_write_hdf5_raises_exception_on_invalid_attrs_name(self):
        """If attrs name is equal or starting with 'QMI_DataSet' or 'DIMENSION_', and exception is raised"""
        data = 1.4142 * (np.arange(24).reshape(8, 3) - 1)
        ds = DataSet("my_dataset", data=data)
        ds.axis_label[0] = "X axis"
        ds.axis_unit[0] = "mm"
        ds.column_label = ["red", "green", "blue"]
        ds.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds.set_axis_scale(0, scale_data)
        ds.attrs["QMI_DataSet"] = "Hello"  # <-- Error
        ds.attrs["number"] = 2.71

        f = h5py.File("test.h5", "w", driver="core", backing_store=False)
        with self.assertRaises(ValueError):
            qmi.data.dataset.write_dataset_to_hdf5(ds, f)

        ds2 = DataSet("my_dataset", data=data)
        ds2.axis_label[0] = "X axis"
        ds2.axis_unit[0] = "mm"
        ds2.column_label = ["red", "green", "blue"]
        ds2.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds2.set_axis_scale(0, scale_data)
        ds2.attrs["DIMENSION_"] = "Hello"  # <-- Error
        ds2.attrs["number"] = 2.71

        with self.assertRaises(ValueError):
            qmi.data.dataset.write_dataset_to_hdf5(ds2, f)

    def test_50_write_text_simple(self):
        """Writing a simple dataset as text."""

        data = 1.4142 * (np.arange(24).reshape(8, 3) - 1)
        ds = DataSet("my_dataset", data=data)
        ds.axis_label[0] = "X axis"
        ds.axis_unit[0] = "mm"
        ds.column_label = ["red", "green", "blue"]
        ds.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds.set_axis_scale(0, scale_data)
        ds.attrs["hello"] = "world"
        ds.attrs["number"] = 2.71

        with io.StringIO() as f:
            qmi.data.dataset.write_dataset_to_text(ds, f)
            text = f.getvalue()

        lines = text.splitlines()
        p = 0
        self.assertEqual(lines[p], "# QMI_DataSet")
        p += 1
        self.assertEqual(lines[p], "#")
        p += 1

        attrs = {}
        while lines[p] != "#":
            self.assertTrue(lines[p].startswith("# "))
            q = lines[p].find(":")
            self.assertGreater(q, 2)
            self.assertEqual(lines[p][q:q + 2], ": ")
            attrs[lines[p][2:q]] = lines[p][q + 2:]
            p += 1
        p += 1

        rawdata = []
        while p < len(lines):
            words = lines[p].split()
            self.assertEqual(len(words), 4)
            rawdata.append([float(w) for w in words])
            p += 1
        self.assertEqual(len(data), 8)
        rawdata = np.array(rawdata)

        self.assertEqual(rawdata.shape, (8, 4))
        self.assertTrue(np.all(rawdata == np.column_stack([scale_data, data])))

        self.assertEqual(attrs["QMI_DataSet_name"], repr("my_dataset"))
        self.assertEqual(attrs["QMI_DataSet_axis0_label"], repr("X axis"))
        self.assertEqual(attrs["QMI_DataSet_axis0_unit"], repr("mm"))
        self.assertEqual(attrs["QMI_DataSet_column1_label"], repr("red"))
        self.assertEqual(attrs["QMI_DataSet_column2_label"], repr("green"))
        self.assertEqual(attrs["QMI_DataSet_column2_unit"], repr("nm"))
        self.assertEqual(attrs["hello"], repr("world"))
        self.assertEqual(attrs["number"], repr(2.71))

    def test_51_write_read_text(self):
        """Writing and reading various datasets as text."""

        # Create datasets and write to file.
        for (name, shape, dtype) in [
                ("t1", (4, 4), np.float64),
                ("t2", (4, 4), np.float64),
                ("t3", (3, 3, 3, 3), np.float64),
                ("t4", (4, 4, 1), np.int32)]:
            ds = _internal_create_dataset(name,
                                          shape,
                                          dtype,
                                          add_labels=True,
                                          add_scale=True,
                                          add_attributes=True)
            with io.StringIO() as f:
                qmi.data.dataset.write_dataset_to_text(ds, f)
                f.seek(0)
                ds2 = qmi.data.dataset.read_dataset_from_text(f)

            self.assertEqual(ds2.name, ds.name)
            self.assertIsInstance(ds2.data, np.ndarray)
            self.assertEqual(ds2.data.shape, ds.data.shape)
            self.assertTrue(np.all(ds2.data == ds.data))
            self.assertEqual(ds2.axis_label, ds.axis_label)
            self.assertEqual(ds2.axis_unit, ds.axis_unit)
            self.assertEqual(len(ds2.axis_scale), len(ds.axis_scale))
            for axis in range(len(ds.axis_scale)):
                if ds.axis_scale[axis] is None:
                    self.assertIsNone(ds2.axis_scale[axis])
                else:
                    self.assertTrue(np.all(ds2.axis_scale[axis] == ds.axis_scale[axis]))
            self.assertEqual(ds2.column_label, ds.column_label)
            self.assertEqual(ds2.column_unit, ds.column_unit)
            self.assertEqual(ds2.attrs, ds.attrs)

    def test_52_write_text_raises_exception_on_invalid_attrs_name(self):
        """If attrs name is equal or starting with 'QMI_DataSet' or 'DIMENSION_', and exception is raised"""
        data = 1.4142 * (np.arange(24).reshape(8, 3) - 1)
        ds = DataSet("my_dataset", data=data)
        ds.axis_label[0] = "X axis"
        ds.axis_unit[0] = "mm"
        ds.column_label = ["red", "green", "blue"]
        ds.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds.set_axis_scale(0, scale_data)
        ds.attrs["QMI_DataSet"] = "Hello"  # <-- Error
        ds.attrs["number"] = 2.71

        with self.assertRaises(ValueError), io.StringIO() as f:
            qmi.data.dataset.write_dataset_to_text(ds, f)

        ds2 = DataSet("my_dataset", data=data)
        ds2.axis_label[0] = "X axis"
        ds2.axis_unit[0] = "mm"
        ds2.column_label = ["red", "green", "blue"]
        ds2.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds2.set_axis_scale(0, scale_data)
        ds2.attrs["DIMENSION_"] = "Hello"  # <-- Error
        ds2.attrs["number"] = 2.71

        with self.assertRaises(ValueError), io.StringIO() as f:
            qmi.data.dataset.write_dataset_to_text(ds, f)

        ds2 = DataSet("my_dataset", data=data)
        ds2.axis_label[0] = "X axis"
        ds2.axis_unit[0] = "mm"
        ds2.column_label = ["red", "green", "blue"]
        ds2.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds2.set_axis_scale(0, scale_data)
        ds2.attrs[""] = "Hello"  # <-- Error
        ds2.attrs["number"] = 2.71

        with self.assertRaises(ValueError), io.StringIO() as f:
            qmi.data.dataset.write_dataset_to_text(ds, f)

        ds2 = DataSet("my_dataset", data=data)
        ds2.axis_label[0] = "X axis"
        ds2.axis_unit[0] = "mm"
        ds2.column_label = ["red", "green", "blue"]
        ds2.column_unit = ["MHz", "nm", "K"]
        scale_data = 0.1 * np.arange(8)
        ds2.set_axis_scale(0, scale_data)
        ds2.attrs["hello:"] = "Hello"  # <-- Error
        ds2.attrs["number"] = 2.71

        with self.assertRaises(ValueError), io.StringIO() as f:
            qmi.data.dataset.write_dataset_to_text(ds, f)

    def test_60_parse_repr(self):
        """Test an internal parse function for repr-formatted values."""

        test_values = [
            # integer
            0,
            1,
            -123456789,
            (1 << 60),
            # float
            0.0,
            np.pi,
            1.0e-100,
            -1.0e100,
            -0.0,
            np.inf,
            np.nan,
            # string
            "",
            "hello",
            "multi\nline"
            "symbols: % # \\$",
            "quotes ' \" ''' \"\"\" ",
            "\x00 \x01 \r \t \b",
            "Falsches Üben von Xylophonmusik quält jeden größeren Zwerg",
            "いろはにほへとちりぬるを",
            "\u2002"
        ]

        for v in test_values:
            s = repr(v)
            w = qmi.data.dataset._parse_attribute_value(s)
            self.assertIs(type(w), type(v))
            if isinstance(v, float) and np.isnan(v):
                self.assertTrue(np.isnan(w))
            else:
                self.assertEqual(w, v)


if __name__ == "__main__":
    unittest.main()
