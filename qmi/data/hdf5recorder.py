"""This module provides a class for recording data to an HDF5 file."""

import datetime
import threading

import h5netcdf
import h5py
import numpy as np

from qmi.core.thread import QMI_Thread

# Supported types for HDF5 attribute values.
_AttributeValueType = int | float | str


class _HDF5RecorderThread(QMI_Thread):
    """A QMI_Thread child which allows for continuous data recording in HDF5 files."""
    HDF5_FILE_MODE = "a"  # open for read/write access, create file if it does not exist
    HDF5_CHUNK_SIZE = 32768

    def __init__(
        self,
        filename: str,
        write_interval: float,
        keep_open: bool,
        backend = "hdf5",
    ) -> None:
        """Initialize thread.
        
        Parameters:
            filename:       The path to the HDF5 file to write to.
            write_interval: The interval at which to write data to disk in seconds, default is 30.0.
            keep_open:      If True, the HDF5 file will be kept open in between writes, default is False.
            backend:        Select HDF5 file backend. Options are "h5py" (default) or "h5netcdf".
        """
        super().__init__()

        self._filename = filename
        self._write_interval = write_interval
        self._keep_open = keep_open
        self._backend = backend
        self._recordings: dict[str, list[np.ndarray]] = {}
        self._attributes: dict[str, dict[str, _AttributeValueType]] = {}
        self._condition = threading.Condition(threading.Lock())

    def run(self) -> None:
        """Run _HDF5RecorderThread."""
        file_handle = None

        recordings: dict[str, list[np.ndarray]] = {}
        pending_attributes: dict[str, dict[str, _AttributeValueType]] = {}
        new_attributes: dict[str, dict[str, _AttributeValueType]] = {}

        quitflag = False
        while not quitflag:
            with self._condition:
                while not (self._shutdown_requested or len(self._recordings) != 0):
                    # Wake up every once in a while to write collected data.
                    self._condition.wait(self._write_interval)

                # We're still holding the mutex here. Obtain safe-to-use references to shared variables.
                (recordings, self._recordings) = (self._recordings, recordings)
                (new_attributes, self._attributes) = (self._attributes, new_attributes)
                quitflag = self._shutdown_requested

            # The mutex is now relinquished. We can now process the recordings at a leisurely pace.
            # Open the HDF5 file if it is not yet open.
            if file_handle is None and self._backend == "h5py":
                # Open for read/write (file must exist)
                file_handle = h5py.File(self._filename, self.HDF5_FILE_MODE)

            if file_handle is None:
                file_handle = h5netcdf.File(self._filename, self.HDF5_FILE_MODE, decode_vlen_strings=False)

            for dset_name, dset_values_list in recordings.items():
                append_dset_values = np.concatenate(dset_values_list)
                n = len(append_dset_values)
                if n != 0:
                    if self._backend == "h5netcdf":
                        if dset_name not in file_handle.dimensions:
                            file_handle.dimensions[dset_name] = None

                    # Check if the dataset already exists
                    if dset_name in file_handle:
                        # Append data to existing dataset
                        dset = file_handle[dset_name]
                        old_size = len(dset)
                        new_size = old_size + n
                        if self._backend == "h5py":
                            dset.resize((new_size,))

                        else:
                            file_handle.resize_dimension(dset_name, new_size)

                        dset[-n:] = append_dset_values

                    else:
                        # Create a new dataset and prepare for it to be extended.
                        if self._backend == "h5py":
                            dset = file_handle.create_dataset(dset_name, data=append_dset_values, maxshape=(None, ))

                        else:
                            dset = file_handle.create_variable(
                                dset_name,
                                dimensions=(dset_name,),
                                dtype=append_dset_values.dtype,
                                compression="gzip",
                                shuffle=True,
                                chunks=(self.HDF5_CHUNK_SIZE,),
                            )
                            file_handle.resize_dimension(dset_name, n)
                            dset[0:n] = append_dset_values

                    # Write any attributes that were queued for this dataset.
                    if dset_name in pending_attributes:
                        new_dset_attrs = pending_attributes.pop(dset_name)
                        dset.attrs.update(new_dset_attrs)

                    if dset_name in new_attributes:
                        new_dset_attrs = new_attributes.pop(dset_name)
                        dset.attrs.update(new_dset_attrs)

            # Loop over the newly queued attributes that have not yet been handled.
            for dset_name, new_dset_attrs in new_attributes.items():
                if dset_name in pending_attributes:
                    # We already know that this dataset does not yet exist.
                    pending_attributes[dset_name].update(new_dset_attrs)
                    continue

                if dset_name in file_handle:
                    # Write attributes to existing dataset.
                    file_handle[dset_name].attrs.update(new_dset_attrs)

                elif dset_name == "HDF5_ROOT":
                    file_handle.attrs.update(new_dset_attrs)

                else:
                    # This dataset does not exist yet.
                    # Hold on to the attributes - we will write them as soon as the dataset is created.
                    pending_attributes[dset_name] = new_dset_attrs

            new_attributes.clear()
            if not self._keep_open:
                file_handle.close()
                file_handle = None

            recordings.clear()  # All recordings were processed.

        if file_handle is not None:
            file_handle.close()
            file_handle = None

    def _request_shutdown(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def record(self, dset_name: str, dset_values: np.ndarray) -> None:
        """This function is called by HD5Recorder to record data."""
        # NOTE: Called from an outside thread.

        if len(dset_values) == 0:
            return

        dset_values = dset_values.copy()  # copy it.

        with self._condition:
            if dset_name not in self._recordings:
                self._recordings[dset_name] = [dset_values]
            else:
                self._recordings[dset_name].append(dset_values)

    def set_attribute(self, dset_name: str, attr_name: str, attr_val: _AttributeValueType) -> None:
        """This function is called by HD5Recorder to set an attribute."""
        with self._condition:
            dset_attrs = self._attributes.setdefault(dset_name, {})
            dset_attrs[attr_name] = attr_val


class HDF5Recorder:
    """The HDF5Recorder class is used to record data to an HDF5 file while the experiment is running.
    This is as opposed to the normal data saving routines, which are used to save data after the
    experiment has finished.

    For example, we use the HDF5Recorder to record the data from the timetaggers, which can generate
    a large amount of data, that would not fit in RAM.

    Example:
        >>> recorder = HDF5Recorder(path_to_hf5_file, write_interval=10.0)
        >>> recorder.record("x0", timestamps)
    """

    DEFAULT_WRITE_INTERVAL = 30.0  # Default interval to write, in seconds.

    def __init__(
        self, filename: str, write_interval: float = DEFAULT_WRITE_INTERVAL, keep_open: bool = False, backend: str = "h5py"
    ) -> None:
        """Initialize data recorder.

        Parameters:
            filename:       The path to the HDF5 file to write to.
            write_interval: The interval at which to write data to disk in seconds, default is 30.0.
            keep_open:      If True, the HDF5 file will be kept open in between writes, default is False.
            backend:        Select HDF5 file backend. Options are "h5py" (default) or "h5netcdf".
        """
        if backend.lower() not in ["h5py", "h5netcdf"]:
            raise ValueError(f"Invalid HDF5 file backend: {backend}")
        
        # Note, this is local time, so ambiguous w.r.t. summer/winter time.
        local_timestamp_string = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename.replace("<localtime>", local_timestamp_string)

        self._recorder_thread = _HDF5RecorderThread(filename, write_interval, keep_open, backend.lower())
        self._recorder_thread.start()

    def close(self) -> None:
        """Close the HDF5 file."""
        self._recorder_thread.shutdown()
        self._recorder_thread.join()

    def record(self, dset_name: str, dset_values: np.ndarray) -> None:
        """Record data to the HDF5 file.

        Parameters:
            dset_name: the name of the dataset to write to, e.g. "x0".
            dset_values: the data to write to the dataset, should be a numpy array.
        """
        self._recorder_thread.record(dset_name, dset_values)

    def set_attribute(self, dset_name: str, attr_name: str, attr_val: int | float | str) -> None:
        """Add or update a HDF5 attribute in the dataset.

        Attributes can only be written to existing datasets.
        If the named dataset does not yet exist, the attribute will be cached in the `HDF5Recorder`
        until the dataset is created by recording data to it. If the dataset is never created,
        pending attribute values are lost when the `HDF5Recorder` is closed.

        Parameters:
            dset_name: Name of the dataset to write the attribute to.
            attr_name: Attribute name.
            attr_val: Attribute value. Only numbers and strings are currently supported.
        """
        self._recorder_thread.set_attribute(dset_name, attr_name, attr_val)
