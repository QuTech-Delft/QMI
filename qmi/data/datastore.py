"""Routines for data storage."""

import os
import os.path
import re
import time
from typing import Any

import json
import h5netcdf
import h5py
import numpy as np
import shutil

from qmi.core.exceptions import QMI_UsageException
import qmi.data.dataset
from qmi.data.dataset import DataSet
from qmi.core.config_struct import config_struct_to_dict

# Global string definition
QMI_DATASET = "QMI_Dataset_{ds_count}"

def _relative_folder_path(date_str: str, time_str: str, label: str) -> str:
    """Internal function to determine the relative path to a DataFolder."""
    return os.path.join(date_str, time_str + "_" + label)


class DataFolder:
    """A DataFolder represents a collection of files from a single measurement.

    A DataFolder typically exists within a DataStore. In this case
    the DataFolder is identified by a label, date code and time code.

    The contents of a DataFolder may consist of:
      - any number of data files from the measurement;
      - a QMI configuration file and/or additional configuration files;
      - data files resulting from analysis;
      - plotted images.
    """

    def __init__(
        self, folder_path: str, label: str | None = None, date_str: str | None = None, time_str: str | None = None
    ) -> None:
        """Initialize a DataFolder instance.

        Parameters:
            folder_path: Path to the directory representing the DataFolder.
            label:       Optional label of the folder (indicating type of measurement)
            date_str:    Optional date code of the folder.
            time_str:    Optional time code of the folder.

        Raises:
            FileNotFoundError: If the specified DataFolder does not exist.
        """

        self.folder_path = folder_path
        self.label = label
        self.date_str = date_str
        self.time_str = time_str

        if not os.path.isdir(self.folder_path):
            raise FileNotFoundError(f"DataFolder directory {self.folder_path!r} not found")

    def __repr__(self) -> str:
        return f"DataFolder({self.folder_path!r})"

    def _hdf5_file(self, filename: str, mode: str, backend: str) -> h5py.File | h5netcdf.File:
        """Create a new, or open, HDF5 file in the data folder.

        Parameters:
            filename: Base name of the HDF5 file, with the extension ".h5" or ".hdf5".
            mode:     File mode.
            backend:  Backend for HDF5 file format. Options are "hdf5" (default) and "h5netcdf".

        Returns:
            A `File` object representing the HDF5 file.

        Raises:
            ValueError:         If the `name` has non-latin character(s).
            QMI_UsageException: Only '.h5' and '.hdf5' file name extensions are allowed.
            IOError:            If the file is already present and file mode does not allow truncation.
            FileNotFoundError:  If the file mode is set to read a file and the file was not found.
            ValueError:         Invalid HDF5 file backend.
        """
        if not re.match(r"^[-_a-zA-Z0-9(),]+$", os.path.splitext(filename)[0]):
            raise ValueError(f"Invalid name {filename!r}")

        if not filename.endswith((".h5", ".hdf5", ".H5", ".HDF5")):
            raise QMI_UsageException("Invalid HDF5 file extension, only '.h5' and '.hdf5' extensions are allowed.")

        file_path = os.path.join(self.folder_path, filename)
        if mode in ["r+", "r", "x"]:
            # Let's check the file exists.
            file_found = os.path.isfile(file_path)
            if mode == "x" and file_found:
                raise IOError(f"The file {filename} already exists and not allowed to overwrite.")

            if mode in ["r+", "r"] and not file_found:
                raise FileNotFoundError(f"Could not find HDF5 file with name {filename}.")

        if backend == "h5py":
            return h5py.File(file_path, mode=mode)

        elif backend == "h5netcdf":
            return h5netcdf.File(file_path, mode=mode, decode_vlen_strings=False)

        else:
            raise ValueError(f"Invalid backend type {backend}")

    def write_config(self, config: Any) -> None:
        """Write QMI configuration to a file in the data folder."""
        # Resolve file name for the config
        config_fn = ""
        if self.label:
            config_fn += self.label

        if self.date_str:
            config_fn += "-" + self.date_str

        if self.time_str:
            config_fn += "-" + self.time_str

        if not config_fn:
            config_fn = "config"

        full_path_fn = os.path.join(self.folder_path, config_fn + ".json")

        config_dict = config_struct_to_dict(config)

        with open(full_path_fn, "w") as output:
            json.dump(config_dict, output, indent=4, sort_keys=True)

    def copy_file(self, filename: str) -> None:
        """Copy an existing file into the data folder.

        Parameters:
            filename: Path to existing file to be copied to the data folder.

        Raises:
            FileExistsError: If the data folder already contains a file with the same name.
        """
        shutil.copy2(filename, self.folder_path)

    def write_dataset(
        self,
        ds: DataSet,
        file_format: str = "hdf5",
        overwrite: bool = False,
        backend: str = "h5py",
    ) -> None:
        """Write the specified DataSet to a new or existing file in the data folder.

        The file name will be determined from the name of the DataSet.

        Parameters:
            ds:          DataSet instance to write.
            file_format: File format specification.
                         - "hdf5". Selects HDF5 format with (default);
                         - "text". Selects a space-separated text format.
            overwrite:   Allow user to overwrite an existing dataset. Default is False.
            backend:     Select backend for HDF5 file format. Options are "hdf5" (default) and "h5netcdf".`

        Raises:
            ValueError: Dataset name is invalid.
            ValueError: Invalid HDF5 file backend.
            OSError:    If the data folder already contains a file with the same name.
        """
        if not re.match(r"^[-_a-zA-Z0-9(),]+$", ds.name):
            raise ValueError(f"Invalid DataSet name {ds.name!r}")

        if file_format == "hdf5":
            filename = ds.name + ".hdf5"
            file_path = os.path.join(self.folder_path, filename)
            if backend == "h5py":
                with h5py.File(file_path, "w" if overwrite else "x") as f:
                    # Add QMI version to file
                    f.attrs["QMI_version"] = qmi.__version__
                    f.attrs[QMI_DATASET.format(ds_count=0)] = ds.name
                    grp = f.create_group(ds.name)
                    qmi.data.dataset.write_dataset_to_hdf5(ds, grp)

            elif backend == "h5netcdf":
                with h5netcdf.File(file_path, "w" if overwrite else "x", decode_vlen_strings=False) as f:
                    # Add QMI version to file
                    f.attrs["QMI_version"] = qmi.__version__
                    f.attrs[QMI_DATASET.format(ds_count=0)] = ds.name
                    grp = f.create_group(ds.name)
                    qmi.data.dataset.write_dataset_to_hdf5(ds, grp)

            else:
                raise ValueError(f"Invalid backend type {backend}.")

        elif file_format == "text":
            filename = ds.name + ".dat"
            file_path = os.path.join(self.folder_path, filename)
            with open(file_path, "wt" if overwrite else "xt") as f:
                qmi.data.dataset.write_dataset_to_text(ds, f)

        else:
            raise QMI_UsageException(f"Unknown file format {file_format!r}.")

    def read_dataset(self, name: str, backend: str = "h5py") -> DataSet:
        """Read a DataSet from the data folder.

        The file name and format will be determined from the name of
        the DataSet and the contents of the data folder.

        Parameters:
            name:    Name of the dataset.
            backend: Select backend for HDF5 file format. Options are "hdf5" (default) and "h5netcdf".

        Returns:
            DataSet: Instance loaded from the data folder.

        Raises:
            ValueError:        Dataset name is invalid.
            ValueError:        Invalid HDF5 file backend.
            FileNotFoundError: If the data folder does not contain the specified dataset.
        """
        # Check that the name is safe (no path names).
        if os.path.split(name)[0]:
            raise ValueError(f"Invalid dataset name {name!r}.")

        # Look for a text file with matching name.
        file_path = os.path.join(self.folder_path, name + ".dat")
        if os.path.isfile(file_path):
            with open(file_path, "rt") as f:
                return qmi.data.dataset.read_dataset_from_text(f)

        # Look for a HDF5 file with matching name.
        extensions = [".hdf5", ".h5"]
        for ext in extensions:
            file_path = os.path.join(self.folder_path, name + ext)
            if os.path.isfile(file_path):
                if backend == "h5py":
                    with h5py.File(file_path, "r") as f:
                        if name not in f:
                            raise FileNotFoundError(f"No dataset {name!r} found in {file_path}.")

                        return qmi.data.dataset.read_dataset_from_hdf5(f[name])

                elif backend == "h5netcdf":
                    with h5netcdf.File(file_path, "r", decode_vlen_strings=False) as f:
                        if name not in f:
                            raise FileNotFoundError(f"No dataset {name!r} found in {file_path}.")

                        return qmi.data.dataset.read_dataset_from_hdf5(f[name])

                else:
                    raise ValueError(f"Invalid backend type {backend}.")

        # File not found.
        raise FileNotFoundError(f"No dataset {name!r} found in {self.folder_path}")

    def make_hdf5file(self, name: str, backend: str = "h5py") -> h5py.File | h5netcdf.File:
        """Create a new HDF5 file in the data folder.

        An error occurs if the specified file already exists.

        Parameters:
            name:       Base name of the HDF5 file, without the extension ".h5" or ".hdf5".
            backend:    Select backend for HDF5 file format. Options are "hdf5" (default) and "h5netcdf".

        Returns:
            hdf5_file: A file object representing a HDF5 file.
        """
        hdf5_file = self._hdf5_file(name, "x", backend)
        # Add QMI version to file
        hdf5_file.attrs["QMI_version"] = qmi.__version__

        return hdf5_file

    def open_hdf5file(self, name: str, write_mode: bool = False, backend: str = "h5py") -> h5py.File | h5netcdf.File:
        """Open an existing HDF5 file in the data folder.

        Parameters:
            name:       Base name of the HDF5 file, without the extension ".h5" or ".hdf5".
            write_mode: True to open the file in read/write mode, False to open the file in read-only mode.
            backend:    Select backend for HDF5 file format. Options are "hdf5" (default) and "h5netcdf".

        Returns:
            A `File` object representing the HDF5 file.
            See http://docs.h5py.org/ for information on how to use this object.
        """
        mode = "r+" if write_mode else "r"
        return self._hdf5_file(name, mode, backend)
    
    def add_dataset_to_file(
        self,
        hdf5_file: h5py.File | h5netcdf.File,
        ds: DataSet,
        root_attrs: dict[
            str, str | int | float | complex | str | np.ndarray | np.integer | list[
                int, float, complex, str
            ] | tuple[int, float, complex, str]
        ] | None = None
    ) -> None:
        """Add a dataset, and optional file attributes to an existing HDF5 file.

        Parameters:
            hdf5_file:  The file instance to add the dataset in.
            ds:         A QMI dataset instance that is to be added.
            root_attrs: A dictionary of attributes that should be written in the file root. Default is `None`.

        Raises:
            QMI_UsageException: If an attribute with the dataset name already exists in the file.
        """
        if hasattr(hdf5_file, ds.name):
            raise QMI_UsageException(f"Data file already has an attribute named {ds.name}")

        if isinstance(hdf5_file, h5netcdf.File):
            hdf5_file.dimensions[ds.column_label] = None

        keys = list(dict(hdf5_file.attrs).keys())
        ds_count = 0
        while True:
            if not QMI_DATASET.format(ds_count=ds_count) in keys:
                break

            ds_count += 1

        hdf5_file.attrs[QMI_DATASET.format(ds_count=ds_count)] = ds.name
        dataset_group = hdf5_file.create_group(ds.name)
        qmi.data.dataset.write_dataset_to_hdf5(ds, dataset_group)
        # Add optional file root attrbutes
        root_attrs = root_attrs or {}
        for attr, val in root_attrs.items():
            hdf5_file.attrs[attr] = val


class DataStore:
    """A DataStore represents a collection of stored data.

    A DataStore instance can potentially contain data from many different
    types of measurements, performed at different times under different
    conditions.

    A DataStore instance corresponds to a folder in the file system which
    contains the actual stored files. The DataStore instance provides
    a convenient interface to store and access the data.

    The file system structure of the DataStore is as follows:
      <basedir>/<date_str>/<time_str>_<label>/<measurement_file>

    where
      <date_str> is an 8-digit string in YYYYmmdd format;
      <time_str> is a 6-digit string in HHMMSS format.

    In other words, the DataStore base directory contains a separate
    sub-directory for each date. Each of these date sub-directories contains
    a separate sub-directory for each measurement, labeled by a time code
    and label for the measurement. Each of the measurement subdirectories
    contains any number of files related to the measurement.
    """

    # True to use local time for folder names; False to use UTC.
    USE_LOCAL_TIME = True

    def __init__(self, basedir: str) -> None:
        """Initialize a DataStore instance.

        Parameters:
            basedir: Base directory for stored files.
        """
        self.basedir = basedir
        if not os.path.isdir(basedir):
            raise FileNotFoundError(f"DataStore base directory {basedir!r} not found.")

    def __repr__(self) -> str:
        return f"DataStore({self.basedir!r})"

    def make_folder(
        self, label: str, timestamp: float | None = None, date_str: str | None = None, time_str: str | None = None
    ) -> DataFolder:
        """Create a new DataFolder with a unique name within the DataStore.

        Optionally, either "timestamp" or both "date_str" and "time_str"
        may be specified to determine the date code of the folder name.
        When neither are specified, the current date and time will be used.

        Parameters:
            label:     Short label describing the measurement. This label will be part of the directory name in the
                       file system. It should not contain whitespace or strange characters.
            timestamp: Optional POSIX timestamp to use for the folder name.
            date_str:  Optional date code to use for the folder name. If specified, it must be a string of 8 digits in
                       YYYYmmdd format.
            time_str:  Optional time code to use for the folder name. If specified, it must be a string of 6 digits in
                       HHMMSS format.

        Returns:
            New DataFolder instance.

        Raises:
            FileExistsError: If the DataFolder already exists.
        """

        # Determine date_str and time_str.
        if (date_str is None) or (time_str is None):
            if (date_str is not None) or (time_str is not None):
                raise ValueError("Specify both date_str and time_str or neither.")
            # Generate date_str and time_str from timestamp.
            if timestamp is None:
                timestamp = time.time()
            if self.USE_LOCAL_TIME:
                tm = time.localtime(timestamp)
            else:
                tm = time.gmtime(timestamp)
            date_str = time.strftime("%Y%m%d", tm)
            time_str = time.strftime("%H%M%S", tm)

        else:
            # Specified by user.
            if timestamp is not None:
                raise ValueError("Do not specify date_str, time_str and timestamp together.")
            if not re.match(r"^[0-9]{8}$", date_str):
                raise ValueError("Invalid format for date_str.")
            if not re.match(r"^[0-9]{6}$", time_str):
                raise ValueError("Invalid format for time_str.")

        # Check label format.
        if (not isinstance(label, str)) or (not label):
            raise ValueError("Label must be a non-empty string.")
        if not re.match(r"^[-_a-zA-Z0-9().,]+$", label):
            raise ValueError("Invalid characters in label.")

        # Ensure date subdirectory exists.
        date_path = os.path.join(self.basedir, date_str)
        if not os.path.isdir(date_path):
            try:
                os.mkdir(date_path)
            except FileExistsError:
                # Someone created the directory just before we did ?
                # Fine, it does not matter who created it.
                pass

        # Create DataFolder directory.
        rel_path = _relative_folder_path(date_str, time_str, label)
        full_path = os.path.join(self.basedir, rel_path)
        if os.path.exists(full_path):
            raise FileExistsError(f"Directory {full_path!r} already exists.")

        os.mkdir(full_path)

        return DataFolder(full_path, label, date_str, time_str)

    def get_folder(self, label: str, date_str: str, time_str: str) -> DataFolder:
        """Open the DataFolder item with specified date code and label.

        Parameters:
            date_str: Date code of the DataFolder.
            time_str: Time code of the DataFolder.
            label:    Label of the DataFolder.

        Returns:
            The matching DataFolder.
        
        Raises:
            FileNotFoundError: If the specified DataFolder does not exist.
        """

        rel_path = _relative_folder_path(date_str, time_str, label)
        full_path = os.path.join(self.basedir, rel_path)
        return DataFolder(full_path, label, date_str, time_str)

    def get_folder_from_path(self, path: str) -> DataFolder:
        """Open the DataFolder with the specified path in the filesystem.

        Parameters:
            path: Path to the DataFolder. The path may be either an absolute path,
                  or a relative path from the DataStore base directory,
                  or a relative path from the current directory.

        Returns:
            The matching DataFolder instance.

        Raises:
            FileNotFoundError: If the specified DataFolder does not exist.
        """

        if (not os.path.isabs(path)) and (not os.path.exists(path)):
            # Try to resolve the specified path relative to the base directory.
            path = os.path.join(self.basedir, path)

        if not os.path.isdir(path):
            raise FileNotFoundError(f"Data folder {path!r} not found.")

        return DataFolder(path, label=None, date_str=None, time_str=None)

    def list_folders(self, label: str | None = None) -> list[DataFolder]:
        """Return a list of DataFolder items in the DataStore.

        This function may be slow when used on a large DataStore.

        Parameters:
            label: Optional folder label. When specified, only folders with a matching name are returned.

        Returns:
            ret: List of matching DataFolder items.
        """

        ret = []

        date_dirs = os.listdir(self.basedir)
        date_dirs.sort()
        for dd in date_dirs:
            if re.match(r"^[0-9]{8}$", dd):
                date_str = dd
                date_path = os.path.join(self.basedir, dd)
                folders = os.listdir(date_path)
                folders.sort()
                for ff in folders:
                    m = re.match(r"^([0-9]{6})_(.+)$", ff)
                    if m:
                        time_str = m.group(1)
                        folder_label = m.group(2)
                        if (label is None) or (label == folder_label):
                            folder_path = os.path.join(date_path, ff)
                            if os.path.isdir(folder_path):
                                ret.append(DataFolder(folder_path, label, date_str, time_str))

        return ret

    def find_latest_folder(self, label: str, date_str: str | None = None) -> DataFolder | None:
        """Find the most recent matching DataFolder item.

        Parameters:
            label:    Folder label to search for.
            date_str: Optional date code to restrict the search. When not specified, the most recent matching folder
                      from any date is returned.
        Returns:
            Most recent matching DataFolder, or None if no matching DataFolder exists.
        """

        if date_str is None:
            date_dirs = os.listdir(self.basedir)
        else:
            date_dirs = [date_str]

        date_dirs.sort(reverse=True)
        for dd in date_dirs:
            if re.match(r"^[0-9]{8}$", dd):
                date_path = os.path.join(self.basedir, dd)
                folders = os.listdir(date_path)
                folders.sort(reverse=True)
                for ff in folders:
                    m = re.match(r"^([0-9]{6})_(.+)$", ff)
                    if m and m.group(2) == label:
                        time_str = m.group(1)
                        folder_path = os.path.join(date_path, ff)
                        if os.path.isdir(folder_path):
                            return DataFolder(folder_path, label, dd, time_str)

        return None
