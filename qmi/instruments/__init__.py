""" QMI drivers for a variety of instruments, driver packages by vendor. Mainly using vendor name for package name.
"""
import os
if "QMI_CONFIG" in os.environ:
    del os.environ["QMI_CONFIG"]
