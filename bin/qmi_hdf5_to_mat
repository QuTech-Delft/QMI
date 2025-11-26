#!/usr/bin/env python

import os
import argparse
import h5py
import numpy as np
import scipy.io


def process(name, obj, datasets):
    if isinstance(obj, h5py.Dataset):
        datasets[name] = np.array(obj)


def convert(filename_in):

    (root, ext) = os.path.splitext(filename_in)
    filename_out = root + ".mat"

    print("Converting {!r} to {!r} ...".format(filename_in, filename_out))
    datasets = {}
    with h5py.File(filename_in, "r") as fi:
        fi.visititems(lambda name, obj: process(name, obj, datasets))

    scipy.io.savemat(filename_out, datasets, do_compression=True)


def run():
    parser = argparse.ArgumentParser(description="Convert HDF5 data files to Matlab (.mat) format.")
    parser.add_argument("filenames", action="append", nargs='+')
    args = parser.parse_args()

    for filename in args.filenames[0]:
        convert(filename)


if __name__ == "__main__":
    run()
