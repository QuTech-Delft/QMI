import os.path
import tempfile
import time
import unittest

import numpy as np
import h5py

from qmi.data.hdf5recorder import HDF5Recorder


class HDF5RecorderTestCase(unittest.TestCase):

    def test_smoke_test(self):
        dtype1 = np.dtype([("timestamp", np.float64), ("value1", np.float64)])
        dtype2 = np.dtype([("timestamp", np.float64), ("value1", np.float64), ("value2", np.float64)])

        temp_file = tempfile.mktemp()

        hdf5 = HDF5Recorder(temp_file)

        ds1 = []
        ds2 = []
        for i in range(3000):
            timestamp = time.time()
            v1 = np.random.randn()
            v2 = np.random.randn()
            ds1.append(np.array((timestamp, v1), dtype=dtype1))
            ds2.append(np.array((timestamp, v1, v2), dtype=dtype2))

            if len(ds1) == 97:
                hdf5.record("g1/g2/dataset1", ds1)
                ds1 = []

            if len(ds2) == 197:
                hdf5.record("dataset2", ds2)
                ds2 = []

            time.sleep(0.001)

        hdf5.record("g1/g2/dataset1", ds1)
        hdf5.record("dataset2", ds2)

        hdf5.close()


class TestRecorder(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._dir.cleanup()

    def test_record(self):

        np.random.seed(112223)

        n1 = 5000
        dtype1 = np.dtype([('x', np.uint32), ('y', np.float64)])
        test_data1 = np.empty(n1, dtype=dtype1)
        test_data1["x"] = np.random.randint(0, 2**32-1, n1, dtype=np.uint32)
        test_data1["y"] = np.random.uniform(0, 10.0, n1)

        n2 = 15000
        dtype2 = np.dtype([('p', np.int64), ('q', np.uint8)])
        test_data2 = np.empty(n2, dtype=dtype2)
        test_data2["p"] = np.random.randint(1-2**63, 2**63-1, n2, dtype=np.int64)
        test_data2["q"] = np.random.randint(0, 2**8-1, n2, dtype=np.uint8)

        file_name = os.path.join(self._dir.name, "test_record.h5")
        rec = HDF5Recorder(file_name, write_interval=1.0)

        p1 = 0
        p2 = 0
        for (q1, q2) in [(1234, 2345), (2345, 4444), (3000, 5000), (4010, 8000), (5000, 11000), (5000, 15000)]:
            rec.record("d1", test_data1[p1:q1])
            rec.record("d2", test_data2[p2:q2])
            p1 = q1
            p2 = q2
            time.sleep(0.8)

        rec.close()

        # Check HDF5 file contents.
        hdf = h5py.File(file_name, "r")
        try:
            self.assertEqual(set(hdf.keys()), {"d1", "d2"})
            self.assertEqual(hdf["d1"].shape, test_data1.shape)
            self.assertEqual(hdf["d1"].dtype, test_data1.dtype)
            self.assertTrue(np.all(hdf["d1"][:] == test_data1))
            self.assertEqual(hdf["d2"].shape, test_data2.shape)
            self.assertEqual(hdf["d2"].dtype, test_data2.dtype)
            self.assertTrue(np.all(hdf["d2"][:] == test_data2))
        finally:
            hdf.close()

    def test_attributes(self):

        np.random.seed(112224)

        test_data1 = np.arange(11)
        test_data2 = np.arange(22)

        file_name = os.path.join(self._dir.name, "test_attributes.h5")
        rec = HDF5Recorder(file_name, write_interval=1.0)

        # Write to dataset.
        rec.record("d1", test_data1)
        time.sleep(1.2)

        # Add attribute to existing dataset.
        rec.set_attribute("d1", "one", 1)
        rec.set_attribute("d1", "more", "MOAR")

        # Add attribute to non-existing datasets.
        rec.set_attribute("d2", "two", 2.0)
        rec.set_attribute("d3", "three", 3)
        time.sleep(1.2)

        # Overwrite existing attribute and add new attribute
        rec.set_attribute("d1", "more", "less")
        rec.set_attribute("d1", "neg", -1000)
        time.sleep(1.2)

        # Create dataset that already has pending attribute.
        rec.record("d2", test_data2)
        rec.close()

        # Check HDF5 file contents.
        hdf = h5py.File(file_name, "r")
        try:
            self.assertEqual(set(hdf.keys()), {"d1", "d2"})
            self.assertEqual(hdf["d1"].shape, test_data1.shape)
            self.assertEqual(hdf["d1"].dtype, test_data1.dtype)
            self.assertTrue(np.all(hdf["d1"][:] == test_data1))
            self.assertEqual(dict(hdf["d1"].attrs), {"one": 1, "more": "less", "neg": -1000})
            self.assertEqual(hdf["d2"].shape, test_data2.shape)
            self.assertEqual(hdf["d2"].dtype, test_data2.dtype)
            self.assertTrue(np.all(hdf["d2"][:] == test_data2))
            self.assertEqual(dict(hdf["d2"].attrs), {"two": 2.0})
        finally:
            hdf.close()


if __name__ == "__main__":
    unittest.main()
