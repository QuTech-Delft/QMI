"""Data structures for measurement data."""

import collections
import re
import time
from typing import Match, TextIO

import numpy as np
import h5netcdf
import h5py

# Constant names
QMI_DATASET_MARKER = "QMI_Dataset"
QMI_DATASET_NAME = "QMI_Dataset_name"
QMI_DATASET_LAYOUT = "QMI_Dataset_layout"
QMI_DATASET_TIMESTAMP = "QMI_Dataset_timestamp"
QMI_DATASET_TIME_STR = "QMI_Dataset_time_str"
QMI_DATASET_DATA_NDIM = "QMI_Dataset_data_ndim"
QMI_DATASET_N_AXES = "QMI_Dataset_n_axes"
QMI_DATASET_NCOL = "QMI_Dataset_ncol"


class DataSet:
    """A dataset is a series of values obtained during a measurement.

    A dataset contains an array of values in the form of a N-dimensional Numpy array.

    For raw datasets without measurement axes, the array may be one-dimensional ``(n,)`` for a single data column,
    or two-dimensional ``(nrow, ncol)`` for tabular data with multiple columns.

    For axis-based datasets, the last axis of the array acts as a "column index" while the first axes represent
    independent variables or iterations in the measurement. Each of these axes may have an optional label,
    a physical unit, and a mapping of array indices to values on the physical axis.

    Each data column may have an associated label and physical unit.

    A dataset may have attributes. Each attribute has a name, which is a short string, unique to the dataset.
    Each attribute has a value which may be a string or a number.

    Reading or changing values in the dataset is done by directly accessing the Numpy array in the DataSet
    instance. For example:

        dataset.data[2, 0:5] += 1

    The following fields exist inside a DataSet instance. Application code may read or modify the contents of
    these fields directly. However, the shape and data type of these fields must not be changed.

    Internal Variables:
        ~DataSet.name:      Name of the dataset.
        ~DataSet.data:      Numpy array containing the actual data.
        ~DataSet.timestamp: POSIX time stamp associated with the data.
        axis_label:         List of strings specifying labels for the measurement axes.
        axis_unit:          List of strings specifying units for the measurement axes.
        axis_scale:         List of optional 1D Numpy arrays specifying value mappings for the measurement axes.
        column_label:       List of strings specifying column labels.
        column_unit:        List of strings specifying column units.
        attrs:              Dictionary of application-specific attributes.

    The entire dataset is kept in memory (RAM). This makes the dataset class unsuitable for very large amounts of data.
    """

    def __init__(
        self,
        name: str,
        shape: tuple[int, ...] | None = None,
        dtype: np.dtype | type | None = None,
        data: np.ndarray | None = None
    ) -> None:
        """Initialize a new dataset.

        Parameters:
            name:  Name of the dataset. This should be a short string without spaces or strange symbols,
                   suitable for use as part of a file name.
            shape: Tuple of axis dimensions. Used to create a zero-initialized dataset if the actual data
                   are not yet available. For raw datasets this may be ``(n,)`` or ``(nrow, ncol)``.
                   For axis-based datasets, the last axis dimension represents the number of columns in the dataset.
            dtype: Type of value in each data point. If not specified, the default is np.float64.
            data:  Optional Numpy array containing the actual data. The new dataset instance will contain a reference
                   to the specified Numpy array. Modifying the Numpy array will cause the contents of the dataset
                   to be changed as well.
        """

        self.name = name
        self.timestamp = time.time()

        if data is not None:
            if not isinstance(data, np.ndarray):
                raise TypeError("Specified 'data' parameter must be a Numpy array.")

            if shape is not None:
                if data.shape != tuple(shape):
                    raise ValueError("Data does not match specified shape.")

            if dtype is not None:
                if data.dtype != dtype:
                    raise ValueError("Data does not match specified data type.")

            # Copy array reference.
            self.data = data

        else:
            if shape is None:
                raise TypeError("Either 'shape' or 'data' parameter must be specified.")

            if dtype is None:
                dtype = np.float64

            # Create zero-initialized array.
            self.data = np.zeros(tuple(shape), dtype=dtype)

        # Check shape.
        if self.data.ndim < 1:
            raise ValueError("DataSet requires at least one dimension.")

        if np.min(self.data.shape) < 1:
            raise ValueError("Zero-size or negative size axes are not allowed.")

        if self.data.ndim == 1:
            self.__axis_capacity = 0
            self.__axis_ndim = 0
            self.__raw_mode = True
            ncol = 1

        elif self.data.ndim == 2:
            self.__axis_capacity = 1
            self.__axis_ndim = 0
            self.__raw_mode = True
            ncol = self.data.shape[-1]

        else:
            self.__axis_capacity = self.data.ndim - 1
            self.__axis_ndim = self.data.ndim - 1
            self.__raw_mode = False
            ncol = self.data.shape[-1]

        self.axis_label: list[str] = [""] * self.__axis_capacity if self.__axis_capacity > 0 else []
        self.axis_unit: list[str] = [""] * self.__axis_capacity if self.__axis_capacity > 0 else []
        self.axis_name: list[str] = [""] * self.__axis_capacity if self.__axis_capacity > 0 else []
        self.axis_scale: list[np.ndarray | None] = [None] * self.__axis_capacity if self.__axis_capacity > 0 else []

        self.column_label: list[str] = ncol * [""]
        self.column_unit: list[str] = ncol * [""]
        self.column_name: list[str] = ncol * [""]

        # Initialize set of attributes.
        self.attrs: dict[str, str | int | float | bool] = {}

    @property
    def _ndim(self) -> int:
        return self.__axis_ndim

    @property
    def n_axes(self) -> int:
        return self.__axis_ndim

    @property
    def ncol(self) -> int:
        return len(self.column_label)

    @property
    def is_raw(self) -> bool:
        return self.__raw_mode

    def _activate_axis_mode(self) -> None:
        """If two-dimensional data has an axis, create it here.
        
        This won't have any effect on three-dimensional data.
        """
        if self.data.ndim == 2 and self.__raw_mode:
            self.__raw_mode = False
            self.__axis_ndim = 1
            if len(self.axis_label) == 0:
                self.axis_label = [""]
                self.axis_unit = [""]
                self.axis_name = [""]
                self.axis_scale = [None]

    def _check_axis_number(self, axis: int) -> None:
        """Check that an axis number is valid.

        Parameters:
            axis:  Axis number (0, 1, ...).

        Raises:
            TypeError:  If axis parameter is not an integer.
            ValueError: If the axis value is not valid, e.g. larger than defined axes at dataset initialization.
        """
        if not isinstance(axis, int):
            raise TypeError("Parameter 'axis' must be an integer.")

        if axis < 0 or axis >= self.__axis_capacity:
            raise ValueError("Invalid value for parameter 'axis'.")

    def set_axis_label(self, axis: int, label: str) -> None:
        """Specify an axis label.

        Parameters:
            axis:  Axis number (0, 1, ...).
            label: Label string of the axis.
        """
        self._check_axis_number(axis)
        self._activate_axis_mode()
        self.axis_label[axis] = label

    def set_axis_unit(self, axis: int, unit: str) -> None:
        """Specify the physical unit for an axis.

        Parameters:
            axis: Axis number (0, 1, ...).
            unit: Unit string of the axis.
        """
        self._check_axis_number(axis)
        self._activate_axis_mode()
        self.axis_unit[axis] = unit

    def set_axis_name(self, axis: int, name: str) -> None:
        """Specify an axis 'long' name.

        Parameters:
            axis: Axis number (0, 1, ...).
            name: 'Long' name string of the axis.
        """
        self._check_axis_number(axis)
        self._activate_axis_mode()
        self.axis_name[axis] = name

    def set_axis_scale(self, axis: int, scale: np.ndarray) -> None:
        """Specify a mapping from array indices to physical values along an axis.

        Parameters:
            axis:  Axis to which the mapping applies (the first axis has number 0).
            scale: 1D Numpy array of values along the axis. The length must match the size of the axis.
        """
        self._check_axis_number(axis)
        self._activate_axis_mode()
        v = np.array(scale)
        if v.shape != (self.data.shape[axis],):
            raise ValueError("Invalid shape for scale array.")

        if not np.all(np.isfinite(scale)):
            raise ValueError("Only finite values allowed on the axis scale.")

        self.axis_scale[axis] = scale

    def set_column_label(self, col: int, label: str) -> None:
        """Specify a label for a column in a multi-column data set.

        Parameters:
            col:   Column number (0, 1, ...).
            label: Column label string.
        """
        if not isinstance(col, int):
            raise TypeError("Parameter 'col' must be an integer")

        if col < 0 or col >= len(self.column_label):
            raise ValueError("Invalid value for parameter 'col'")

        self.column_label[col] = label

    def set_column_unit(self, col: int, unit: str) -> None:
        """Specify a physical unit for a column in a multi-column data set.

        Parameters:
            col:  Column number (0, 1, ...).
            unit: Column unit string.
        """
        if not isinstance(col, int):
            raise TypeError("Parameter 'col' must be an integer")

        if col < 0 or col >= len(self.column_unit):
            raise ValueError("Invalid value for parameter 'col'")

        self.column_unit[col] = unit

    def set_column_name(self, col: int, name: str) -> None:
        """Specify a name for a column in a multi-column data set.

        Parameters:
            col:  Column number (0, 1, ...).
            name: Descriptive name for column data.
        """
        if not isinstance(col, int):
            raise TypeError("Parameter 'col' must be an integer")

        if col < 0 or col >= len(self.column_name):
            raise ValueError("Invalid value for parameter 'col'")

        self.column_name[col] = name


def _parse_attribute_value(s: str) -> int | float | str | bool:
    """Parse an attribute value.

    This function should be able to evaluate any string
    produced by repr() when acting on a string, int or float.

    Parameters:
        s: The string to parse
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

    elif s in {'True', 'False'}:
        # Must be a boolean, one line return bool value.
        return s == 'True'

    else:
        # Must be floating point literal.
        return float(s)


def _dataset_layout(dataset: DataSet) -> str:
    return "raw" if dataset.is_raw else "axis"


def _column_keys(dataset: DataSet) -> list[str]:
    keys: list[str] = []
    used: set[str] = set()
    for col in range(dataset.ncol):
        base = dataset.column_label[col] or (dataset.name if dataset.data.ndim == 1 else f"column_{col}")
        key = base
        suffix = 1
        while key in used:
            key = f"{base}_{suffix}"
            suffix += 1
        used.add(key)
        keys.append(key)
    return keys


def _axis_scale_keys(dataset: DataSet) -> list[str]:
    keys: list[str] = []
    used: set[str] = set()
    for axis in range(dataset.n_axes):
        base = dataset.axis_label[axis] or f"axis_{axis}_scale"
        key = base
        suffix = 1
        while key in used:
            key = f"{base}_{suffix}"
            suffix += 1
        used.add(key)
        keys.append(key)
    return keys


def _write_common_metadata(
    container: h5py.Group | h5netcdf.Group | h5py.File | h5netcdf.File,
    dataset: DataSet,
) -> tuple[str, list[str], list[str]]:
    group_name = dataset.name if isinstance(container, (h5py.File, h5netcdf.File)) else container.name.split("/")[-1]

    container.attrs[QMI_DATASET_MARKER] = 1
    container.attrs[QMI_DATASET_NAME] = dataset.name
    container.attrs[QMI_DATASET_LAYOUT] = _dataset_layout(dataset)
    container.attrs[f"{group_name}_timestamp"] = dataset.timestamp
    container.attrs[f"{group_name}_time_str"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(dataset.timestamp))
    container.attrs[f"{group_name}_data_ndim"] = dataset.data.ndim
    container.attrs[f"{group_name}_n_axes"] = dataset.n_axes
    container.attrs[f"{group_name}_ncol"] = dataset.ncol

    for dim_index, dim_size in enumerate(dataset.data.shape):
        container.attrs[f"{group_name}_dim{dim_index}_size"] = dim_size

    axis_scale_keys = _axis_scale_keys(dataset)
    for axis in range(dataset.n_axes):
        if dataset.axis_label[axis]:
            container.attrs[f"{group_name}_axis{axis}_label"] = dataset.axis_label[axis]
        if dataset.axis_unit[axis]:
            container.attrs[f"{group_name}_axis{axis}_unit"] = dataset.axis_unit[axis]
        if dataset.axis_name[axis]:
            container.attrs[f"{group_name}_axis{axis}_name"] = dataset.axis_name[axis]
        if dataset.axis_scale[axis] is not None:
            container.attrs[f"{group_name}_axis{axis}_key"] = axis_scale_keys[axis]

    column_keys = _column_keys(dataset)
    for col in range(dataset.ncol):
        container.attrs[f"{group_name}_column{col}_key"] = column_keys[col]
        if dataset.column_label[col]:
            container.attrs[f"{group_name}_column{col}_label"] = dataset.column_label[col]
        if dataset.column_unit[col]:
            container.attrs[f"{group_name}_column{col}_unit"] = dataset.column_unit[col]
        if dataset.column_name[col]:
            container.attrs[f"{group_name}_column{col}_name"] = dataset.column_name[col]

    for (name, value) in dataset.attrs.items():
        if name.startswith("QMI_Dataset") or name.startswith(group_name) or name.startswith("DIMENSION_"):
            raise ValueError(f"Invalid use of special attribute name {name!r}")
        container.attrs[name] = value

    return group_name, column_keys, axis_scale_keys


def _create_dataset_node(
    container: h5py.Group | h5netcdf.Group | h5py.File | h5netcdf.File,
    key: str,
    data: np.ndarray,
    dim_names: tuple[str, ...],
) -> h5py.Dataset | h5netcdf.Variable:
    if isinstance(container, (h5py.File, h5py.Group)):
        return container.create_dataset(key, data=data)

    for dim_name, dim_size in zip(dim_names, data.shape):
        if dim_name not in container.dimensions:
            container.dimensions[dim_name] = dim_size
    return container.create_variable(key, dimensions=dim_names, data=data)


def _read_shape(attrs: dict, group_name: str) -> tuple[int, ...]:
    data_ndim = int(attrs[f"{group_name}_data_ndim"])
    return tuple(int(attrs[f"{group_name}_dim{dim_index}_size"]) for dim_index in range(data_ndim))


def _read_qmi_dataset(container: h5py.Group | h5netcdf.Group | h5py.File | h5netcdf.File) -> DataSet:
    attrs = dict(container.attrs)
    name = str(attrs.get(QMI_DATASET_NAME) or container.name.split("/")[-1] or "dataset")
    group_name = name
    layout = str(attrs.get(QMI_DATASET_LAYOUT, "axis"))
    data_ndim = int(attrs[f"{group_name}_data_ndim"])
    n_axes = int(attrs.get(f"{group_name}_n_axes", 0))
    ncol = int(attrs[f"{group_name}_ncol"])
    shape = _read_shape(attrs, group_name)

    column_keys = [
        str(attrs.get(f"{group_name}_column{col}_key", attrs.get(f"{group_name}_column{col}_label", f"column_{col}")))
        for col in range(ncol)
    ]

    if data_ndim == 1:
        data = np.asarray(container[column_keys[0]])
    else:
        column_arrays = [np.asarray(container[key]) for key in column_keys]
        base_shape = column_arrays[0].shape
        for arr in column_arrays[1:]:
            if arr.shape != base_shape:
                raise ValueError("Column datasets do not have matching shapes")
        data = np.stack(column_arrays, axis=-1)
        if data.shape != shape:
            data = data.reshape(shape)

    dataset = DataSet(name=name, data=data)
    dataset.timestamp = float(attrs[f"{group_name}_timestamp"])

    if layout == "axis" and n_axes > 0 and dataset.is_raw:
        dataset._activate_axis_mode()
        dataset.__axis_ndim = n_axes
        dataset.__raw_mode = False

    for axis in range(n_axes):
        dataset.axis_label[axis] = str(attrs.get(f"{group_name}_axis{axis}_label", ""))
        dataset.axis_unit[axis] = str(attrs.get(f"{group_name}_axis{axis}_unit", ""))
        dataset.axis_name[axis] = str(attrs.get(f"{group_name}_axis{axis}_name", ""))
        scale_key = attrs.get(f"{group_name}_axis{axis}_key")
        if scale_key:
            scale = np.asarray(container[str(scale_key)])
            if scale.shape != (dataset.data.shape[axis],):
                raise ValueError(f"Invalid shape of dimension scale for axis {axis}")
            dataset.axis_scale[axis] = scale

    for col in range(ncol):
        dataset.column_label[col] = str(attrs.get(f"{group_name}_column{col}_label", ""))
        dataset.column_unit[col] = str(attrs.get(f"{group_name}_column{col}_unit", ""))
        dataset.column_name[col] = str(attrs.get(f"{group_name}_column{col}_name", ""))

    for name, value in attrs.items():
        if not name.startswith(group_name) and not name.startswith("QMI_Dataset") and not name.startswith("DIMENSION_"):
            dataset.attrs[name] = value

    return dataset


def write_dataset_to_hdf5(dataset: DataSet, hdf_group: h5py.Group | h5netcdf.Group | h5py.File | h5netcdf.File) -> None:
    """Write the specified dataset to the specified HDF5 group.

    The dataset "name" field determines the name of the corresponding HDF5 dataset.
    An error occurs if the HDF5 group already contains a dataset with the same name.

    Note that this function may create additional supporting datasets in the HDF5 group if the DataSet instance
    uses axis scales. In this case, HDF5 datasets named "<datasetname>_axisN_scale" will be created in
    addition to the main dataset.

    Parameters:
        dataset:   DataSet instance to write to HDF5.
        hdf_group: HDF5 File or Group instance to which the dataset is written.
    """

    group_name, column_keys, axis_scale_keys = _write_common_metadata(hdf_group, dataset)

    if dataset.data.ndim == 1:
        column_ds = _create_dataset_node(hdf_group, column_keys[0], dataset.data, ("row",))
        if dataset.column_label[0]:
            column_ds.attrs["name"] = dataset.column_label[0]
        if dataset.column_unit[0]:
            column_ds.attrs["unit"] = dataset.column_unit[0]
        if dataset.column_name[0]:
            column_ds.attrs["long_name"] = dataset.column_name[0]
        return

    if dataset.n_axes == 0:
        row_dim = "row"
        for col, key in enumerate(column_keys):
            column_ds = _create_dataset_node(hdf_group, key, dataset.data[..., col], (row_dim,))
            if dataset.column_label[col]:
                column_ds.attrs["name"] = dataset.column_label[col]
            if dataset.column_unit[col]:
                column_ds.attrs["unit"] = dataset.column_unit[col]
            if dataset.column_name[col]:
                column_ds.attrs["long_name"] = dataset.column_name[col]
        return

    dim_names = tuple(dataset.axis_label[axis] or f"dim_{axis}" for axis in range(dataset.n_axes))
    column_nodes: list[h5py.Dataset | h5netcdf.Variable] = []
    for col, key in enumerate(column_keys):
        column_ds = _create_dataset_node(hdf_group, key, dataset.data[..., col], dim_names)
        if dataset.column_label[col]:
            column_ds.attrs["name"] = dataset.column_label[col]
        if dataset.column_unit[col]:
            column_ds.attrs["unit"] = dataset.column_unit[col]
        if dataset.column_name[col]:
            column_ds.attrs["long_name"] = dataset.column_name[col]
        column_nodes.append(column_ds)

    for axis in range(dataset.n_axes):
        axis_scale = dataset.axis_scale[axis]
        if axis_scale is None:
            continue

        scale_key = axis_scale_keys[axis]
        scale_ds = _create_dataset_node(hdf_group, scale_key, axis_scale, (dim_names[axis],))
        if dataset.axis_label[axis]:
            scale_ds.attrs["name"] = dataset.axis_label[axis]
        if dataset.axis_unit[axis]:
            scale_ds.attrs["unit"] = dataset.axis_unit[axis]
        if dataset.axis_name[axis]:
            scale_ds.attrs["long_name"] = dataset.axis_name[axis]

        if isinstance(hdf_group, (h5py.File, h5py.Group)):
            scale_ds.make_scale(scale_key)
            for column_ds in column_nodes:
                column_ds.dims[axis].label = dataset.axis_label[axis]
                column_ds.dims[axis].attach_scale(scale_ds)


def read_dataset_from_hdf5(
    parent: h5py.File | h5netcdf.File | h5py.Group | h5netcdf.Group | h5py.Dataset | h5netcdf.Variable,
    container: h5py.File | h5netcdf.File | h5py.Group | h5netcdf.Group | None = None,
) -> DataSet:
    """Extract a QMI DataSet instance from the specified HDF5 dataset (group).

    Note that this function may fetch additional HDF5 datasets from
    the parent HDF5 group if the dataset uses dimension scales.

    Parameters:
        parent:    HDF5 file/group container, or a child dataset for backwards compatibility.
        container: Optional explicit parent file/group if `parent` is a child dataset.

    Returns:
        dataset:   DataSet instance.
    """
    source = parent
    meta_container = container or parent

    if isinstance(meta_container, (h5py.Dataset, h5netcdf.Variable)) and meta_container.attrs.get(QMI_DATASET_MARKER) == 1:
        return _read_qmi_dataset(meta_container)

    if isinstance(meta_container, (h5py.File, h5py.Group, h5netcdf.File, h5netcdf.Group)) and meta_container.attrs.get(QMI_DATASET_MARKER) == 1:
        return _read_qmi_dataset(meta_container)

    return convert_to_qmi_dataset(source)


def convert_to_qmi_dataset(
    parent: h5py.File | h5netcdf.File | h5py.Group | h5netcdf.Group | h5py.Dataset | h5netcdf.Variable,
) -> DataSet:
    """A function to convert a HDF5 dataset, in a group, or in file root, to a QMI dataset.

    If the input is a h5py.Dataset | h5netcdf.Variable, the dataset can have one or more dimensions.

    If the input is s h5py.Group | h5netcdf.Group, and the group has multiple datasets, the dataset attributes
    are looked into if we can determine a scaled axis | column or columns, and data axis | axes. If so,
    it will be converted into single QMI dataset with (multiple) ax[i|e]s and column[s]. A single dataset will be
    converted as a 1D dataset.

    If the input is a h5py.File | h5netcdf.File, and there are no groups, the handling is the same as for the group.
    If there is a single group present, that will be taken and handled like a group. For multiple groups in a file
    an error will be thrown.
    """
    if isinstance(parent, (h5py.Dataset, h5netcdf.Variable)):
        data = np.asarray(parent)
        name = parent.name.split("/")[-1] or str(parent.attrs.get("name", "dataset"))
        dataset = DataSet(name=name, data=data)
        if dataset.ncol > 0:
            dataset.column_label[0] = str(parent.attrs.get("label", parent.attrs.get("name", name)))
            dataset.column_unit[0] = str(parent.attrs.get("units", parent.attrs.get("unit", "")))
            dataset.column_name[0] = str(parent.attrs.get("long_name", ""))
        for attr_name, value in parent.attrs.items():
            if not str(attr_name).startswith("_") and not str(attr_name).startswith("DIMENSION_"):
                dataset.attrs[str(attr_name)] = value
        return dataset

    group: h5py.Group | h5netcdf.Group | None = None
    if isinstance(parent, (h5py.File, h5netcdf.File)):
        groups = [obj for obj in parent.values() if isinstance(obj, (h5py.Group, h5netcdf.Group))]
        if groups:
            if len(groups) > 1:
                raise RuntimeError("Cannot convert multiple groups from a HDF5 file.")
            group = groups[0]
        else:
            group = parent
    else:
        group = parent

    axes: list[tuple[str, h5py.Dataset | h5netcdf.Variable]] = []
    columns: list[tuple[str, h5py.Dataset | h5netcdf.Variable]] = []

    for item, hdf5_obj in group.items():
        if isinstance(hdf5_obj, (h5py.Group, h5netcdf.Group)):
            raise RuntimeError("Cannot convert nested groups to a single QMI dataset.")

        label = str(hdf5_obj.attrs.get("label", hdf5_obj.attrs.get("name", item)))
        if isinstance(hdf5_obj, h5py.Dataset):
            if hdf5_obj.is_scale:
                axes.append((label, hdf5_obj))
            else:
                columns.append((label, hdf5_obj))

        elif item in hdf5_obj.dimensions:
            axes.append((label, hdf5_obj))
            
        else:
            columns.append((label, hdf5_obj))

    if not columns and not axes:
        raise RuntimeError("No datasets found to convert from the HDF5 file.")

    name = group.name.split("/")[-1]
    if not name:
        name = str(group.attrs["name"]) if "name" in group.attrs else "dataset"

    if columns:
        column_arrays = [np.asarray(ds) for _, ds in columns]
        base_shape = column_arrays[0].shape
        for arr in column_arrays[1:]:
            if arr.shape != base_shape:
                raise ValueError("Column datasets do not have matching shapes")

        if len(column_arrays) == 1 and not axes:
            qmi_dataset = DataSet(name=name, data=column_arrays[0])
        else:
            data = np.stack(column_arrays, axis=-1)
            qmi_dataset = DataSet(name=name, data=data)
    else:
        label, axis_ds = axes[0]
        qmi_dataset = DataSet(name=name, data=np.asarray(axis_ds))
        qmi_dataset.column_label[0] = label
        qmi_dataset.column_unit[0] = str(axis_ds.attrs.get("units", axis_ds.attrs.get("unit", "")))
        qmi_dataset.column_name[0] = str(axis_ds.attrs.get("long_name", ""))

    if axes and qmi_dataset.data.ndim >= 2:
        for axis_index, (label, axis_ds) in enumerate(axes):
            qmi_dataset.set_axis_label(axis_index, label)
            qmi_dataset.set_axis_unit(axis_index, str(axis_ds.attrs.get("units", axis_ds.attrs.get("unit", ""))))
            qmi_dataset.set_axis_name(axis_index, str(axis_ds.attrs.get("long_name", "")))
            axis_values = np.asarray(axis_ds)
            if np.issubdtype(axis_values.dtype, np.number) and np.all(np.isfinite(axis_values)):
                qmi_dataset.set_axis_scale(axis_index, axis_values)

    for col_index, (label, column_ds) in enumerate(columns[:qmi_dataset.ncol]):
        qmi_dataset.column_label[col_index] = label
        qmi_dataset.column_unit[col_index] = str(column_ds.attrs.get("units", column_ds.attrs.get("unit", "")))
        qmi_dataset.column_name[col_index] = str(column_ds.attrs.get("long_name", ""))

    for name, value in group.attrs.items():
        if not str(name).startswith("_") and not str(name).startswith("DIMENSION_"):
            qmi_dataset.attrs[str(name)] = value

    return qmi_dataset


def write_dataset_to_text(dataset: DataSet, fh: TextIO) -> None:
    """Write the specified dataset to a text file.

    Note that this function may create additional supporting datasets in
    the HDF5 group if the DataSet instance uses axis scales. In this case,
    HDF5 datasets named "<datasetname>_axisN_scale" will be created in
    addition to the main dataset.

    Parameters:
        dataset: DataSet instance to write to HDF5.
        fh:      File handle open for writing in text mode.
    """

    attrs: dict[str, int | float | str | bool] = collections.OrderedDict()
    attrs[QMI_DATASET_NAME] = dataset.name
    attrs[QMI_DATASET_LAYOUT] = _dataset_layout(dataset)
    attrs[QMI_DATASET_TIMESTAMP] = dataset.timestamp
    attrs[QMI_DATASET_TIME_STR] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(dataset.timestamp))
    attrs[QMI_DATASET_DATA_NDIM] = dataset.data.ndim
    attrs[QMI_DATASET_N_AXES] = dataset.n_axes
    attrs[QMI_DATASET_NCOL] = dataset.ncol

    for dim_index, dim_size in enumerate(dataset.data.shape):
        attrs[f"QMI_Dataset_dim{dim_index}_size"] = dim_size

    for axis in range(dataset.n_axes):
        if dataset.axis_label[axis]:
            attrs[f"QMI_Dataset_axis{axis}_label"] = dataset.axis_label[axis]

        if dataset.axis_unit[axis]:
            attrs[f"QMI_Dataset_axis{axis}_unit"] = dataset.axis_unit[axis]

        if dataset.axis_name[axis]:
            attrs[f"QMI_Dataset_axis{axis}_name"] = dataset.axis_name[axis]

    special_column_label = []
    special_column_unit = []

    if dataset.n_axes > 1:
        for axis in range(dataset.n_axes):
            special_column_label.append(f"axis{axis}_index")
            special_column_unit.append("")

    for axis in range(dataset.n_axes):
        if dataset.axis_scale[axis] is not None:
            special_column_label.append(f"axis{axis}_scale")
            special_column_unit.append(dataset.axis_unit[axis])

    column_label = special_column_label + dataset.column_label
    column_unit = special_column_unit + dataset.column_unit
    for col in range(len(column_label)):
        if column_label[col]:
            attrs[f"QMI_Dataset_column{col}_label"] = column_label[col]

        if column_unit[col]:
            attrs[f"QMI_Dataset_column{col}_unit"] = column_unit[col]

    for (name, val) in dataset.attrs.items():
        if name.startswith("QMI_Dataset"):
            raise ValueError(f"Invalid use of special attribute name {name!r}")

        if not name:
            raise ValueError("Invalid use of empty attribute name")

        if ':' in name:
            raise ValueError(f"Invalid character ':' in attribute name {name!r}")

        attrs[name] = val

    if dataset.data.ndim == 1:
        rawdata = dataset.data.reshape(-1, 1)
    elif dataset.data.ndim > 2:
        nrow = np.prod(dataset.data.shape[:-1])
        rawdata = dataset.data.reshape((nrow, dataset.ncol))
    else:
        rawdata = dataset.data

    extra_columns = []
    if dataset.n_axes > 1:
        for axis in range(dataset.n_axes):
            n = dataset.data.shape[axis]
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            extra_columns.append(np.tile(np.repeat(np.arange(n), inner_rows), outer_rows))

    for axis in range(dataset.n_axes):
        dataset_axis_scale = dataset.axis_scale[axis]
        if dataset_axis_scale is not None:
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            if dataset.n_axes == 1:
                inner_rows = 1
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
        if line == "#":
            # Stop at separator between attributes and data.
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
    dataset_name = attrs.get(QMI_DATASET_NAME)
    if not isinstance(dataset_name, str):
        raise ValueError("Missing required attribute QMI_DataSet_name")

    # Determine dataset shape
    data_ndim = int(attrs[QMI_DATASET_DATA_NDIM])
    n_axes = int(attrs.get(QMI_DATASET_N_AXES, 0))
    ncol = int(attrs[QMI_DATASET_NCOL])
    shape = tuple(int(attrs[f"QMI_Dataset_dim{dim_index}_size"]) for dim_index in range(data_ndim))
    # Verify data dimensions.
    if total_columns < ncol:
        raise ValueError(f"Expecting at least {ncol} columns but got {total_columns} columns")
    
    num_special_columns = total_columns - ncol
    if data_ndim == 1:
        data = rawdata[:, num_special_columns]

    else:
        expect_rows = np.prod(shape[:-1]) if len(shape) > 1 else shape[0]
        if nrow != expect_rows:
            raise ValueError(f"Expecting {expect_rows} rows but got {nrow} rows")
        
        data = rawdata[:, num_special_columns:].reshape(shape)

    # Create dataset instance.
    dataset = DataSet(name=dataset_name, data=data)
    dataset.timestamp = float(attrs[QMI_DATASET_TIMESTAMP])

    if n_axes > 0 and dataset.is_raw:
        dataset._activate_axis_mode()
        dataset.__axis_ndim = n_axes
        dataset.__raw_mode = False

    for axis in range(n_axes):
        dataset.axis_label[axis] = str(attrs.get(f"QMI_Dataset_axis{axis}_label", ""))
        dataset.axis_unit[axis] = str(attrs.get(f"QMI_Dataset_axis{axis}_unit", ""))
        dataset.axis_name[axis] = str(attrs.get(f"QMI_Dataset_axis{axis}_name", ""))

    for col in range(ncol):
        dataset.column_label[col] = str(attrs.get(f"QMI_Dataset_column{num_special_columns + col}_label", ""))
        dataset.column_unit[col] = str(attrs.get(f"QMI_Dataset_column{num_special_columns + col}_unit", ""))

    for col in range(num_special_columns):
        label = attrs.get(f"QMI_Dataset_column{col}_label")
        if not isinstance(label, str):
            raise ValueError(f"Missing label for special column {col}")

        if label.startswith("axis") and label.endswith("_index"):
            axis = int(label[4:-6])
            n = dataset.data.shape[axis]
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            idx = np.tile(np.repeat(np.arange(n), inner_rows), outer_rows)
            if not np.all(rawdata[:, col].astype(np.int64) == idx):
                raise ValueError(f"Inconsistent index data for axis {axis}")

        elif label.startswith("axis") and label.endswith("_scale"):
            axis = int(label[4:-6])
            n = dataset.data.shape[axis]
            outer_rows = int(np.prod(dataset.data.shape[:axis], dtype=np.int32))
            inner_rows = int(np.prod(dataset.data.shape[axis+1:-1], dtype=np.int32))
            if dataset.n_axes == 1:
                inner_rows = 1
                
            scale = rawdata[0:n*inner_rows:inner_rows, col]
            scale_raw = np.tile(np.repeat(scale, inner_rows), outer_rows)
            if not np.all(rawdata[:, col] == scale_raw):
                raise ValueError(f"Inconsistent scale data for axis {axis}")

            dataset.axis_scale[axis] = scale

    for attribute_name, attribute_value in attrs.items():
        if not attribute_name.startswith("QMI_Dataset"):
            dataset.attrs[attribute_name] = attribute_value

    return dataset
