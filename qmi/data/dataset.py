"""Data structures for measurement data."""

import collections
import re
import time
from typing import Dict, List, Match, Optional, TextIO, Tuple, Union

import numpy as np
import h5py


class DataSet:
    """A dataset is a series of values obtained during a measurement.

    A dataset contains an array of values in the form of a N-dimensional Numpy array (N >= 2).

    The first (N-1) axes of the Numpy array represent independent variables or iterations in the measurement.
    Each of these axes may have an optional label, a physical unit, and a mapping of array indices to values
    on the physical axis.

    The last axis of the Numpy array acts as a "column index". Each column may have an associated label and
    physical unit.

    A dataset may have attributes. Each attribute has a name, which is a short string, unique to the dataset.
    Each attribute has a value which may be a string or a number.

    Reading or changing values in the dataset is done by directly accessing the Numpy array in the DataSet
    instance. For example:

        dataset.data[2, 0:5] += 1

    The following fields exist inside a DataSet instance. Application code may read or modify the contents of
    these fields directly. However the shape and data type of these fields must not be changed.

    Internal Variables:
        ~DataSet.name:         Name of the dataset.
        ~DataSet.data:         Numpy array containing the actual data.
        ~DataSet.timestamp:    POSIX time stamp associated with the data.
        axis_label:   List of strings specifying labels for the first (N-1) axes.
        axis_unit:    List of strings specifying units for the first (N-1) axes.
        axis_scale:   List of optional 1D Numpy arrays specifying value mappings for the first (N-1) axes.
        column_label: List of strings specifying column labels.
        column_unit:  List of strings specifying column units.
        attrs:        Dictionary of application-specific attributes.

    The entire dataset is kept in memory (RAM). This makes the dataset class unsuitable for very large amounts of data.
    """

    def __init__(self,
                 name: str,
                 shape: Optional[Tuple[int, ...]] = None,
                 dtype: Optional[Union[np.dtype, type]] = None,
                 data: Optional[np.ndarray] = None
                 ) -> None:
        """Initialize a new dataset.

        Parameters:
            name: Name of the dataset. This should be a short string without spaces or strange symbols,
                suitable for use as part of a file name.
            shape: Tuple of axis dimensions. Used to create a zero-initialized dataset if the actual data
                are not yet available. The last axis dimension represents the number of columns in the dataset.
            dtype: Type of value in each data point. If not specified, the default is np.float64.
            data: Optional Numpy array containing the actual data. The new dataset instance will contain a reference
                to the specified Numpy array. Modifying the Numpy array will cause the contents of the dataset to be
                changed as well.
        """

        self.name = name
        self.timestamp = time.time()

        if data is not None:
            # Check that the specified data is a Numpy array.
            if not isinstance(data, np.ndarray):
                raise TypeError("Specified 'data' parameter must be a Numpy array")

            # Check shape and data type.
            if shape is not None:
                if data.shape != tuple(shape):
                    raise ValueError("Data does not match specified shape")

            if dtype is not None:
                if data.dtype != dtype:
                    raise ValueError("Data does not match specified data type")

            # Copy array reference.
            self.data = data

        else:

            if shape is None:
                raise TypeError("Either 'shape' or 'data' parameter must be specified")

            if dtype is None:
                dtype = np.float64

            # Create zero-initialized array.
            self.data = np.zeros(tuple(shape), dtype=dtype)

        # Check shape.
        ndim = len(self.data.shape)
        if ndim < 2:
            raise ValueError("Dataset must have at least 2 axes")
        if np.min(self.data.shape) < 1:
            raise ValueError("Zero-size or negative size axes are not allowed")

        # Initialize axis labels.
        self.axis_label = [""]*(ndim - 1)
        self.axis_unit = [""]*(ndim - 1)
        self.axis_scale = [None]*(ndim - 1)  # type: List[Optional[np.ndarray]]

        # Initialize column labels.
        ncol = self.data.shape[-1]
        self.column_label = ncol * [""]
        self.column_unit = ncol * [""]

        # Initialize empty set of attributes.
        self.attrs = {}  # type: Dict[str, Union[str, int, float]]

    def set_axis_label(self, axis: int, label: str) -> None:
        """Specify an axis label.

        Parameters:
            axis: int - axis number (0, 1, ...)
            label: str - label string of the axis
        """
        if not isinstance(axis, int):
            raise TypeError("Parameter 'axis' must be an integer")

        if axis < 0 or axis >= len(self.axis_label):
            raise ValueError("Invalid value for parameter 'axis'")

        self.axis_label[axis] = label

    def set_axis_unit(self, axis: int, unit: str) -> None:
        """Specify the physical unit for an axis.

        Parameters:
            axis: int - axis number (0, 1, ...)
            unit: str - unit string of the axis
        """
        if not isinstance(axis, int):
            raise TypeError("Parameter 'axis' must be an integer")

        if axis < 0 or axis >= len(self.axis_unit):
            raise ValueError("Invalid value for parameter 'axis'")

        self.axis_unit[axis] = unit

    def set_axis_scale(self, axis: int, scale: np.ndarray) -> None:
        """Specify a mapping from array indices to physical values along an axis.

        Parameters:
            axis: Axis to which the mapping applies (the first axis has number 0).
            scale: 1D Numpy array of values along the axis. The length must match the size of the axis.
        """
        if not isinstance(axis, int):
            raise TypeError("Parameter 'axis' must be an integer")

        if axis < 0 or axis >= len(self.data.shape) - 1:
            raise ValueError("Invalid value for parameter 'axis'")

        v = np.array(scale)
        if v.shape != (self.data.shape[axis],):
            raise ValueError("Invalid shape for scale array")

        if not np.all(np.isfinite(scale)):
            raise ValueError("Only finite values allowed on the axis scale")

        self.axis_scale[axis] = scale

    def set_column_label(self, col: int, label: str) -> None:
        """Specify a label for a column in a multi-column data set.

        Parameters:
            col: int - column number (0, 1, ...)
            label: str - column label string
        """
        if not isinstance(col, int):
            raise TypeError("Parameter 'col' must be an integer")
        if col < 0 or col >= len(self.column_label):
            raise ValueError("Invalid value for parameter 'col'")
        self.column_label[col] = label

    def set_column_unit(self, col: int, unit: str) -> None:
        """Specify a physical unit for a column in a multi-column data set.

        Parameters:
            col: int - column number (0, 1, ...)
            unit: str - column unit string
        """
        if not isinstance(col, int):
            raise TypeError("Parameter 'col' must be an integer")

        if col < 0 or col >= len(self.column_unit):
            raise ValueError("Invalid value for parameter 'col'")

        self.column_unit[col] = unit


def _parse_attribute_value(s: str) -> Union[int, float, str]:
    """Parse an attribute value.

    This function should be able to evaluate any string
    produced by repr() when acting on a string, int or float.

    Parameters:
        s: str - the string to parse
    """

    def replace_esc(m: Match[str]) -> str:
        replace_table = {
            "\n": "",
            "\\": "\\",
            "'": "'",
            '"': '"',
            "a": "\a",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v"
        }
        t = m.group(1)
        if t in replace_table:
            return replace_table[t]
        elif t.startswith("x") or t.startswith("u"):
            return chr(int(t[1:], 16))
        else:
            return chr(int(t, 8))

    if ("'" in s) or ('"' in s):
        # Quoted string.
        quote_char = s[0]
        if quote_char not in ('"', "'"):
            raise ValueError(f"Invalid attribute value syntax {s!r}")
        if not s[1:].endswith(quote_char):
            raise ValueError(f"Invalid attribute value syntax {s!r}")
        # Strip quotes.
        s = s[1:-1]
        # Check for non-escaped occurrences of quote symbol.
        t = re.sub("\\\\.", "", s)
        if quote_char in t:
            raise ValueError(f"Invalid attribute value syntax {s!r}")
        # Expand escape sequences.
        s = re.sub("\\\\(['\"abfnrtv]|\\\\|[0-7]{1,3}|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4})", replace_esc, s)
        return s

    elif re.match(r"^[+-]?[0-9]*$", s):
        # Integer literal.
        return int(s)

    elif (s == 'True') or (s == 'False'):
        # Must be a boolean, one line return bool value.
        return s == 'True'

    else:
        # Must be floating point literal.
        return float(s)


def write_dataset_to_hdf5(dataset: DataSet, hdf_group: h5py.Group) -> None:
    """Write the specified dataset to the specified HDF5 group.

    The dataset "name" field determines the name of the corresponding HDF5 dataset.
    An error occurs if the HDF5 group already contains a dataset with the same name.

    Note that this function may create additional supporting datasets in the HDF5 group if the DataSet instance
    uses axis scales. In this case, HDF5 datasets named "<datasetname>_axisN_scale" will be created in
    addition to the main dataset.

    Parameters:
        dataset: DataSet instance to write to HDF5.
        hdf_group: HDF5 File or Group instance to which the dataset is written.
    """

    ndim = len(dataset.data.shape)
    ncol = dataset.data.shape[-1]

    ds = hdf_group.create_dataset(dataset.name, data=dataset.data)

    # Special timestamp attribute.
    ds.attrs["QMI_DataSet_timestamp"] = dataset.timestamp
    ds.attrs["QMI_DataSet_time_str"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(dataset.timestamp))

    # Special attributes for axis labels / units.
    for axis in range(ndim - 1):
        if dataset.axis_label[axis]:
            ds.attrs[f"QMI_DataSet_axis{axis}_label"] = dataset.axis_label[axis]

        if dataset.axis_unit[axis]:
            ds.attrs[f"QMI_DataSet_axis{axis}_unit"] = dataset.axis_unit[axis]

    # Special attributes for column labels / units.
    for col in range(ncol):
        if dataset.column_label[col]:
            ds.attrs[f"QMI_DataSet_column{col}_label"] = dataset.column_label[col]

        if dataset.column_unit[col]:
            ds.attrs[f"QMI_DataSet_column{col}_unit"] = dataset.column_unit[col]

    # Dimension scales.
    for axis in range(ndim - 1):
        if dataset.axis_label[axis]:
            ds.dims[axis].label = dataset.axis_label[axis]

        if dataset.axis_scale[axis] is not None:
            # Create an extra dataset to hold the dimension scale.
            scale_name = dataset.name + f"_axis{axis}_scale"
            ds_scale = hdf_group.create_dataset(scale_name, data=dataset.axis_scale[axis])
            # Attach the dimension scale to the axis.
            ds_scale.make_scale(scale_name)
            ds.dims[axis].attach_scale(ds_scale)

    # Custom attributes.
    for (name, value) in dataset.attrs.items():
        if name.startswith("QMI_DataSet") or name.startswith("DIMENSION_"):
            raise ValueError(f"Invalid use of special attribute name {name!r}")

        ds.attrs[name] = value

    # Special attribute to recognize format.
    ds.attrs["QMI_DataSet"] = 1


def read_dataset_from_hdf5(ds: h5py.Dataset) -> DataSet:
    """Extract a DataSet instance from the specified HDF5 dataset.

    Note that this function may fetch additional HDF5 datasets from
    the parent HDF5 group if the dataset uses dimension scales.

    Parameters:
        ds: HDF5 Dataset instance to read from.

    Returns:
        DataSet instance.
    """

    # Check that the HDF5 dataset was created by this Python module.
    if ds.attrs.get("QMI_DataSet") != 1:
        raise ValueError("HDF5 dataset not in expected format")

    # Sanity check.
    if (len(ds.shape) < 2) or np.min(ds.shape) < 1:
        raise ValueError("Invalid shape of HDF5 dataset")

    # Create DataSet instance and read actual data.
    name = ds.name.split("/")[-1]
    dataset = DataSet(name=name, data=ds[:])

    ndim = len(dataset.data.shape)
    ncol = dataset.data.shape[-1]

    # Read timestamp.
    dataset.timestamp = ds.attrs["QMI_DataSet_timestamp"]

    # Read special attributes for labels.
    for axis in range(ndim - 1):
        dataset.axis_label[axis] = ds.attrs.get(f"QMI_DataSet_axis{axis}_label", "")
        dataset.axis_unit[axis] = ds.attrs.get(f"QMI_DataSet_axis{axis}_unit", "")

    for col in range(ncol):
        dataset.column_label[col] = ds.attrs.get(f"QMI_DataSet_column{col}_label", "")
        dataset.column_unit[col] = ds.attrs.get(f"QMI_DataSet_column{col}_unit", "")

    # Read dimension scales.
    for axis in range(ndim - 1):
        if len(ds.dims[axis]) > 0:
            scale = ds.dims[axis][0]
            if scale.shape != (dataset.data.shape[axis],):
                raise ValueError(f"Invalid shape of dimension scale for axis {axis}")
            dataset.axis_scale[axis] = scale[:]

    # Read custom attributes.
    for (name, value) in ds.attrs.items():
        if (not name.startswith("QMI_DataSet")) and (not name.startswith("DIMENSION_")):
            dataset.attrs[name] = value

    return dataset


def write_dataset_to_text(dataset: DataSet, fh: TextIO) -> None:
    """Write the specified dataset to a text file.

    Note that this function may create additional supporting datasets in
    the HDF5 group if the DataSet instance uses axis scales. In this case,
    HDF5 datasets named "<datasetname>_axisN_scale" will be created in
    addition to the main dataset.

    Parameters:
        dataset: DataSet instance to write to HDF5.
        fh: File handle open for writing in text mode.
    """

    ndim = len(dataset.data.shape)
    ncol = dataset.data.shape[-1]

    # Create special columns if needed.
    special_column_label = []
    special_column_unit = []

    if ndim > 2:
        # Create special axis index columns.
        for axis in range(ndim - 1):
            special_column_label.append(f"axis{axis}_index")
            special_column_unit.append("")

    # Create special axis scale columns if needed.
    for axis in range(ndim - 1):
        if dataset.axis_scale[axis] is not None:
            special_column_label.append(f"axis{axis}_scale")
            special_column_unit.append(dataset.axis_unit[axis])

    # Prepare attributes.
    attrs = collections.OrderedDict()  # type: Dict[str, Union[int, float, str]]

    # Dataset name.
    attrs["QMI_DataSet_name"] = dataset.name

    # Timestamp.
    attrs["QMI_DataSet_timestamp"] = dataset.timestamp
    attrs["QMI_DataSet_time_str"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(dataset.timestamp))

    # Data shape.
    attrs["QMI_DataSet_ndim"] = ndim
    attrs["QMI_DataSet_ncol"] = ncol

    # Axis labels / units.
    for axis in range(ndim - 1):
        attrs[f"QMI_DataSet_axis{axis}_size"] = dataset.data.shape[axis]
        if dataset.axis_label[axis]:
            attrs[f"QMI_DataSet_axis{axis}_label"] = dataset.axis_label[axis]
        if dataset.axis_unit[axis]:
            attrs[f"QMI_DataSet_axis{axis}_unit"] = dataset.axis_unit[axis]

    # Column labels / units.
    column_label = special_column_label + dataset.column_label
    column_unit = special_column_unit + dataset.column_unit
    for col in range(len(column_label)):
        if column_label[col]:
            attrs[f"QMI_DataSet_column{col}_label"] = column_label[col]

        if column_unit[col]:
            attrs[f"QMI_DataSet_column{col}_unit"] = column_unit[col]

    # Custom attributes.
    for (name, val) in dataset.attrs.items():
        if name.startswith("QMI_DataSet"):
            raise ValueError(f"Invalid use of special attribute name {name!r}")

        if not name:
            raise ValueError("Invalid use of empty attribute name")

        if ':' in name:
            raise ValueError(f"Invalid character ':' in attribute name {name!r}")

        attrs[name] = val

    # Reshape data to 2D format.
    if ndim > 2:
        nrow = np.prod(dataset.data.shape[:-1])
        rawdata = dataset.data.reshape((nrow, ncol))

    else:
        rawdata = dataset.data

    # Insert axis index columns.
    extra_columns = []
    if ndim > 2:
        for axis in range(ndim - 1):
            n = dataset.data.shape[axis]
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            extra_columns.append(np.tile(np.repeat(np.arange(n), inner_rows), outer_rows))

    # Insert axis scale columns.
    for axis in range(ndim - 1):
        dataset_axis_scale = dataset.axis_scale[axis]
        if dataset_axis_scale is not None:
            assert dataset_axis_scale.shape == (dataset.data.shape[axis],)
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            extra_columns.append(np.tile(np.repeat(dataset_axis_scale, inner_rows), outer_rows))

    if extra_columns:
        rawdata = np.column_stack(extra_columns + [rawdata])

    # Write marker line.
    fh.write("# QMI_DataSet\n")
    fh.write("#\n")

    # Write attributes.
    for (name, value) in attrs.items():
        fh.write(f"# {name}: {value!r}\n")

    fh.write("#\n")

    # Write actual data.
    np.savetxt(fh, rawdata)


def read_dataset_from_text(fh: TextIO) -> DataSet:
    """Read a DataSet instance from a text file.

    Parameters:
        fh: File handle open for reading in text mode.

    Returns:
        DataSet instance.
    """

    # Check marker line.
    line = fh.readline().strip()
    if line != "# QMI_DataSet":
        raise ValueError(f"Invalid file format; expecting marker but got {line!r}")

    line = fh.readline().strip()
    if line != "#":
        raise ValueError(f"Invalid file format; expecting separator but got {line!r}")

    # Read attributes.
    attrs = {}
    while True:
        line = fh.readline().strip()
        # Stop at separator between attributes and data.
        if line == "#":
            break
        # Read attribute.
        p = line.find(":")
        if (not line.startswith("# ")) or (p < 0):
            raise ValueError(f"Invalid file format; expecting attribute but got {line!r}")

        name = line[2:p]
        value = line[p+1:].strip()
        if not name:
            raise ValueError(f"Invalid file format; expecting attribute but got {line!r}")

        attrs[name] = _parse_attribute_value(value)

    # Read raw data.
    rawdata = np.loadtxt(fh, ndmin=2)
    (nrow, total_columns) = rawdata.shape

    # Determine dataset name.
    dataset_name = attrs.get("QMI_DataSet_name")
    if not isinstance(dataset_name, str):
        raise ValueError("Missing required attribute QMI_DataSet_name")

    # Determine dataset shape.
    ndim = int(attrs["QMI_DataSet_ndim"])
    ncol = int(attrs["QMI_DataSet_ncol"])
    assert ndim >= 2

    shape_list: List[int] = []
    for axis in range(ndim - 1):
        axis_size = attrs[f"QMI_DataSet_axis{axis}_size"]
        if not isinstance(axis_size, int):
            raise ValueError(f"Invalid value for attribute QMI_DataSet_axis{axis}_size")
        shape_list.append(axis_size)
    shape_list.append(ncol)
    shape = tuple(shape_list)

    # Verify number of rows.
    expect_rows = np.prod(shape[:-1])
    if nrow != expect_rows:
        raise ValueError(f"Expecting {expect_rows} rows but got {nrow} rows")

    # Verify number of columns.
    if total_columns < ncol:
        raise ValueError(f"Expecting at least {ncol} columns but got {total_columns} columns")
    num_special_columns = total_columns - ncol

    # Extract and reshape actual data.
    data = rawdata[:, num_special_columns:].reshape(*shape)

    # Create DataSet instance.
    dataset = DataSet(name=dataset_name, data=data)

    # Set timestamp.
    dataset.timestamp = float(attrs["QMI_DataSet_timestamp"])

    # Set axis labels and units.
    for axis in range(ndim - 1):
        dataset.axis_label[axis] = str(attrs.get(f"QMI_DataSet_axis{axis}_label", ""))
        dataset.axis_unit[axis] = str(attrs.get(f"QMI_DataSet_axis{axis}_unit", ""))

    for col in range(ncol):
        dataset.column_label[col] = str(attrs.get(f"QMI_DataSet_column{num_special_columns + col}_label", ""))
        dataset.column_unit[col] = str(attrs.get(f"QMI_DataSet_column{num_special_columns + col}_unit", ""))

    # Verify index columns and extract axis scales.
    for col in range(num_special_columns):
        label = attrs.get(f"QMI_DataSet_column{col}_label")
        if not isinstance(label, str):
            raise ValueError(f"Missing label for special column {col}")

        if label.startswith("axis") and label.endswith("_index"):
            # Verify index column.
            axis = int(label[4:-6])
            n = dataset.data.shape[axis]
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            idx = np.tile(np.repeat(np.arange(n), inner_rows), outer_rows)
            if not np.all(rawdata[:, col].astype(np.int64) == idx):
                raise ValueError(f"Inconsistent index data for axis {axis}")

        elif label.startswith("axis") and label.endswith("_scale"):
            # Set axis scale.
            axis = int(label[4:-6])
            n = dataset.data.shape[axis]
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            scale = rawdata[0:n*inner_rows:inner_rows, col]
            scale_raw = np.tile(np.repeat(scale, inner_rows), outer_rows)
            if not np.all(rawdata[:, col] == scale_raw):
                raise ValueError(f"Inconsistent scale data for axis {axis}")

            dataset.axis_scale[axis] = scale

    # Read custom attributes.
    for attribute_name, attribute_value in attrs.items():
        if not attribute_name.startswith("QMI_DataSet"):
            dataset.attrs[attribute_name] = attribute_value

    return dataset
