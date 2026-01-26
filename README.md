[![pylint](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/pylint.svg)](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/pylint.svg)
[![mypy](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/mypy.svg)](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/mypy.svg)
[![Documentation Status](https://readthedocs.org/projects/qmi/badge/?version=latest)](https://qmi.readthedocs.io/en/latest/?badge=latest)
[![coverage](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/coverage.svg)](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/coverage.svg)
[![tests](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/tests.svg)](https://github.com/QuTech-Delft/QMI/blob/v0.51.1/.github/badges/tests.svg)

# Quantum Measurement Infrastructure

QMI is a Python 3 framework for controlling laboratory equipment. It is suitable for anything ranging from one-off
scientific experiments to robust operational setups.

QMI is developed by [QuTech](https://qutech.nl) to support advanced physics experiments involving quantum bits.
However, other than its name and original purpose, there is nothing specifically *quantum* about QMI — it is potentially
useful in any environment where monitoring and control of measurement equipment is needed.

## Dependencies
The full functioning of this software is dependent on several external Python packages, dynamic libraries and drivers.
The following items are not delivered as part of this software and must be acquired and installed by the user separately,
when necessary for the use of a specific QMI driver:
- [ADwin.py](https://pypi.org/project/ADwin/)
- [libadwin.so, adwin32.dll, adwin64.dll](https://www.adwin.de/us/download/download.html)
- [aravis](https://github.com/AravisProject/aravis)
- [Aviosys HTTP API](https://aviosys.com/products/lib/httpapi.html)
- [Boston Micromachines DM SDK](https://bostonmicromachines.com/dmsdk/)
- [libdwf.dll, libdwf.so](https://digilent.com/reference/software/waveforms/waveforms-sdk/start)
- [JPE cacli.exe](https://www.jpe-innovations.com/wp-content/uploads/CPSC_v7.3.20201222.zip)
- [libmh150.so](https://www.picoquant.com/dl_software/MultiHarp150/MultiHarp150_160_V3_0.zip)
- [libhh400.so](https://www.picoquant.com/dl_software/HydraHarp400/HydraHarp400_SW_and_DLL_v3_0_0_3.zip)
- [libph300.so](https://www.picoquant.com/dl_software/PicoHarp300/PicoHarp300_SW_and_DLL_v3_0_0_3.zip)
- [libusb](https://libusb.info/)
- [mcculw](https://pypi.org/project/mcculw/)
- [Picotech PicoSDK ps3000a, PicoSDK ps4000a](https://www.picotech.com/downloads)
- [PyGObject](https://pypi.org/project/PyGObject/)
- [tcdbase.dll](https://www.qutools.com/files/quTAU_release/quTAU_Setup_4.3.3_win.exe), libtcdbase.so
- [RPi.GPIO](https://pypi.org/project/RPi.GPIO/)
- [Silicon Labs CP210x USB to UART Bridge](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)
- [uldaq](https://pypi.org/project/uldaq/)
- [usbdll.dll](https://www.newport.com/software-and-drivers)
- [VCP driver](https://ftdichip.com/Drivers/vcp-drivers/)
- [stmcdc.inf](https://www.wieserlabs.com/products/radio-frequency/flexdds-ng-dual/FlexDDS-NG-ad9910_standalone.zip)
- [wlmData.dll, libwlmData.so](https://www.highfinesse.com/en/support/software-update.html)
- [zhinst](https://pypi.org/project/zhinst/)

Usage of the third-party software, drivers or libraries can be subject to copyright and license terms of the provider. Please review their terms before using the software, driver or library.

## Installation

Install with Pip from https://pypi.org/project/qmi/: `pip install qmi`.

## Documentation

### Latest version

The latest version of the documentation can be found [here](https://qmi.readthedocs.io/en/latest/).

### Installing for generating documentation

To install the necessary packages to perform documentation activities for QMI do:

```
pip install -e .[rtd]
```

To build the 'readthedocs' documentation locally do:

```
cd documentation/sphinx
./make-docs
```

The documentation can then be found in the `build/html` directory.

## Contribute

For contribution guidelines see [CONTRIBUTING](CONTRIBUTING.md)
