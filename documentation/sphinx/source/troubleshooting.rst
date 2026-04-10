=============
Troubleshooting
=============
This page details some known peculiarities with QMI
or its supported devices and ways of working around them.

Devices
------------

USBTMC on Windows
==============

Connecting with USBTMC devices on Windows can be tricky. Make sure you have libusb1 and pyvisa installed.
https://pypi.org/project/libusb1/ and https://pypi.org/project/PyVISA/ (and perhaps pyvisa-py).

Then you'll need to have the backend set-up correctly, in case the ``libusb-1.0.dll`` is not found in your path.
An example script to set-up and test the backend is::

  import usb.core
  from usb.backend import libusb1

  backend = libusb1.get_backend(
      find_library=lambda x: "<path_to_your_env>\\Lib\\site-packages\\usb1\\libusb-1.0.dll")

  dev = list(usb.core.find(find_all=True))

If you can now find devices, the backend is set correctly. There are of course other ways to set-up your backend
as well, but as said, it can be tricky...
