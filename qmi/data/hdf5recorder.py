
import threading
import datetime
from typing import Dict, List, Union

import numpy as np
import h5py

from qmi.core.thread import QMI_Thread


# Supported types for HDF5 attribute values.
_AttributeValueType = Union[int, float, str]


class _HDF5RecorderThread(QMI_Thread):

    def __init__(self, filename: str, write_interval: float, keep_open: bool) -> None:
        super().__init__()

        self._filename = filename
        self._write_interval = write_interval
        self._keep_open = keep_open
        self._recordings: Dict[str, List[np.ndarray]] = {}
        self._attributes: Dict[str, Dict[str, _AttributeValueType]] = {}
        self._condition = threading.Condition(threading.Lock())

    def run(self) -> None:

        HDF5_FILE_MODE = "a"  # open for read/write access, create file if it does not exist
        fo = None

        recordings: Dict[str, List[np.ndarray]] = {}
        pending_attributes: Dict[str, Dict[str, _AttributeValueType]] = {}
        new_attributes: Dict[str, Dict[str, _AttributeValueType]] = {}

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

            # The mutex is now relinquished. We can now process the recordings at a leasurely pace.

            for (dset_name, dset_values_list) in recordings.items():
                append_dset_values = np.concatenate(dset_values_list)
                n = len(append_dset_values)
                if n != 0:
                    # We have to write data...
                    if fo is None:
                        # Open for read/write (file must exist)
                        fo = h5py.File(self._filename, HDF5_FILE_MODE)

                    # Check if the dataset already exists
                    if dset_name in fo:
                        # Append data to existing dataset
                        dset = fo[dset_name]
                        old_size = len(dset)
                        new_size = old_size + n

                        dset.resize((new_size, ))
                        dset[-n:] = append_dset_values
                    else:
                        # Create a new dataset ; prepare for it to be extended.
                        dset = fo.create_dataset(dset_name, data=append_dset_values, maxshape=(None, ))

                    # Write any attributes that were queued for this dataset.
                    if dset_name in pending_attributes:
                        new_dset_attrs = pending_attributes.pop(dset_name)
                        dset.attrs.update(new_dset_attrs)
                    if dset_name in new_attributes:
                        new_dset_attrs = new_attributes.pop(dset_name)
                        dset.attrs.update(new_dset_attrs)

            # Loop over the newly queued attributes that have not yet been handled.
            for (dset_name, new_dset_attrs) in new_attributes.items():
                if dset_name in pending_attributes:
                    # We already know that this dataset does not yet exist.
                    pending_attributes[dset_name].update(new_dset_attrs)
                else:
                    # Open the HDF5 file if it is not yet open.
                    if fo is None:
                        fo = h5py.File(self._filename, HDF5_FILE_MODE)
                    if dset_name in fo:
                        # Write attributes to existing dataset.
                        fo[dset_name].attrs.update(new_dset_attrs)
                    else:
                        # This dataset does not exist yet.
                        # Hold on to the attributes; we will write them as soon as the dataset is created.
                        pending_attributes[dset_name] = new_dset_attrs

            new_attributes.clear()

            if not self._keep_open:
                if fo is not None:
                    fo.close()
                    fo = None

            recordings.clear()  # All recordings were processed.

        if fo is not None:
            fo.close()
            fo = None

    def _request_shutdown(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def record(self, dset_name: str, dset_values: np.ndarray) -> None:
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
        with self._condition:
            dset_attrs = self._attributes.setdefault(dset_name, {})
            dset_attrs[attr_name] = attr_val


class HDF5Recorder:

    DEFAULT_WRITE_INTERVAL = 60.0 # Default interval to write, in seconds.

    def __init__(self, filename: str, write_interval: float = DEFAULT_WRITE_INTERVAL, keep_open: bool = False):

        # Note, this is local time, so ambiguous w.r.t. summer/winter time.
        local_timestamp_string = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename.replace("<localtime>", local_timestamp_string)

        self._recorder_thread = _HDF5RecorderThread(filename, write_interval, keep_open)
        self._recorder_thread.start()

    def close(self) -> None:
        self._recorder_thread.shutdown()
        self._recorder_thread.join()
        self._recorder_thread = None  # type: ignore

    def record(self, dset_name: str, dset_values: np.ndarray) -> None:
        self._recorder_thread.record(dset_name, dset_values)

    def set_attribute(self, dset_name: str, attr_name: str, attr_val: Union[int, float, str]) -> None:
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
