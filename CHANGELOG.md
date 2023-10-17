# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## \[x.y.z] - Unreleased

### Added
- Implementation of `discard_read` on `QMI_UsbTmcTransport` class, and `read_until` now forwards to `read_until_timeout` instead of raising error.

### Changed
- Non-interface breaking changes on `QMI_UsbTmcTransport` class calls `read` and `read_until_timeout`.

### Fixed
- Changed a regexp line in TLB-670x driver to a raw string to avoid future warnings.

## [0.42.0] - 2023-09-29

### Added
- New QMI driver for Santec TSL-570 laser.
- New QMI driver for Newport SMC100PP and new actuator UTS100PP in the `actuators.py`. 
- New functions in the Newport_SingleAxisMotionController and Newport_SMC100CC classes.
- Unit-tests for Aviosys IPPower9850 instrument driver.
- Unit-tests for Anapico APSIN instrument driver.
- `qmi.data.DataFolder.write_dataset` has `overwrite` keyword argument that allows a user to overwrite the current dataset if it exists.
- Unit-tests for RasperryPi_GPIO instrument driver.
- Travel range for Newport's single axis motion controllers now have a travel range that can go negative.

### Changed
- Changed the product id of Thorlabs_PM10x classes to have the same name for all classes and overwrite the default value 0x0000 in base class.

### Fixed
- Newport single axis motion controller checks minimum incremental motion on `move_relative` instead of `move_absolute` command.
- K10C1 won't fail to open if no pending message is in the buffer.
- Unit-testing for Hydraharp event processing with test_get_events_limit.
- Added missing `hardware_type` input for call in `adbasic_compiler` and simplified unit-testing.
- Made SSA300X `open()` call sleep time to come from self._TIMEOUT instead of hard-coded value 2.0. Adjusted unit-tests to be faster using this change.
- Velocity TLB-670x QMI driver can now handle spurious instrument *IDN? returns. 

## [0.41.0] - 2023-08-11

### Added
- Unittest for BRISTOL_871A.
- Unittest for Wavelength_TC_Lab.
- Unittest for BostonMicromachines_MultiDM.
- Unittest for Newport_AG_UC8.
- Unittest for OZOptics_DD100MC.
- Unittest for KoherasBoostikLaserAmplifier.
- New context manager 'subscribe_unsubscribe' for managing QMI signals in `qmi/utils/context_managers.py`.
- driver calls to set and get the relay state for `EdwardsVacuum_TIC.`
- tests/core/test_usbtmc.py: Created unit-tests for the qmi.core.usbtmc module.
- Backlash compensation calls for Newport Single Axis Motion Controllers.
- New functions to the `awg5014.py` instrument driver: `wait_command_completion`, `get_setup_file_name` and 
  `get/set_waveform_output_data_position`.

### Changed
- responses of driver calls for `EdwardsVacuum_TIC` to return objects instead of dictionaries.

### Fixed
- The Tektronix AWG 5014 QMI driver error checking method. It clears the transport buffer before the error query to avoid mixed response.
- The `read_until` method of VXI11 transport protocol now tries to repeatedly read until terminating character until timeout, not just once.
- Changed the port numbers in `test_proc.py` from 511 and 512 to be > 1024, as the smaller port numbers caused permission issues.
- In some other tests in `test_proc.py` specified explicitly `popen.pid = 0` as the latest Python 3.11 otherwise throws an error about
  comparison of a MagicMock object with an int, like in `if pid >= 0:`.

## [0.40.0] - 2023-07-06

### Added
- qmi/tools/proc.py: Added a new option `--locals` in the command line call. This can be used to start/stop/restart local contexts only.
- New documentation. Now more details for RPC methods, messaging, signalling and logging in QMI. Also, more examples about how to use tasks.
- Unittest for Tektronix_FCA3000.
- Unittest for SRS_DC205.
- Unittest for MCC_USB1808X.

### Changed
- qmi/tools/proc.py: changed the WINENV validater method. Previous method was not compatible with python3.11. Included in unit test.
- Moved several functions from `RohdeSchwarz_SGS100A` to the base class, and removed and renamed some (double) methods in `RohdeSchwarz_SMBV100A`.
- Pololu Maestro default values are the hardware limits. `set_max`, `set_min`, `get_target_value`, `get_value`, `move_up` and `move_down` are deprecated in the Pololu Maestro driver. They have either been replaced by other methods or have been removed altogether.
- All the instrument packages now have module class imports in the package level (in __init__.py). The unit-tests were modified such that these imports are used when possible.
- The `get_system_state` and `get_system_goal` methods for the Montana S50 returns enums instead of strings.

## [0.39.0] - 2023-05-26

### Added

- Base class for Newport single axis motion controllers `Newport_Single_Axis_Motion_Controller`.
- Newport SMC100CC controller driver `Newport_SMC100CC`.
- Newport CMA25CCL linear actuator.

### Changed

- Added optional `btstat` and `adcoffs` parameters for DIM3000 driver. Now works with ADRV5.
- Newport CONEX-CC controller inherits from `Newport_Single_Axis_Motion_Controller`.
- Added default baudrate of 115200 to Thorlabs TC200 driver.

### Fixed

- ADBasic compiler now correctly doesn't fail compilation on warnings only. 
- ADBasic compiler now correctly parses `fixme` warning.
- qmi/tools/proc.py: get child pid when in WINENV. This fixes the incorrect error message on starting of a service, when using Windows virtual environment.

## [0.38.0] - 2023-04-21

### Added

- Added client for Newport AG-UC8. `qmi_newport_ag_uc8`.
- A new warning pattern "fixme" matching added to `qmi/tools/adbasic_compiler.py` function `_parse_stderr_lines`. It now also recognizes patterns starting with "<hex_code>:fixme"
- Added unit-tests for Thorlabs instruments TC200, TSP01, TSP01B and K10CR1.
- For K10CR1, one way to raise QMI_TimeoutException was added to _wait_message, so that the function description is valid.
- Meanwhile the same exception was removed from _send_message as it will be handled in _read_message already.
- Made `AdbasicCompilerException` RPC compatible by adding a custom `__reduce__` method to pack the arguments in a tuple.
- Unittests for qmi/tools/proc.py.

### Removed

- The 'toolage' folder has been removed and contents moved to qid-utilities.
- removed matplotlib from install_requires in setup.py, and added classifier for Python v3.11.
- `qmi/gui` reference in `run_docs_sphinx.sh`

### Fixed

- Some additional PicoQuant license text fixes and other typo fixes.

## [0.37.0] - 2023-03-17

### Added

- Included full coverage unit-tests for the PtGrey BlackFly cameras.
- Included full coverage unit-tests for the PhysikInstrument E-873 Servo Controller.
- Adding acknowledgements, licensing and copyright (waiver) to the QMI.
- Added Parallax USB Propeller QMI driver.
- Adding the licence referrals into PicoQuant modules.
- Added two new functions, `get_phase` and `set_phase` to Rigol DG4102 QMI driver.
- Added unit-tests for this instrument.

### Removed

- Removed installing `libhdf5-dev` linux package, and `ldconfig` steps in the CI YAML script as the latest Python 3.11 release now has applicable python-hdf5 package wheel that works without pre-installed libraries

## [x.y.z] creation of repository

### Added
- ACKNOWLEDGEMENTS.md.
- Copyright waiver in README.md.
- CI workflows for regular push, pull request and for publishing.
- Scheduled CI workflow for main branch.
- Workflow for creating documentation into readthedocs.io.
- Added licence references for files.

### Changed
- LICENSE.md with a small change on first sentence.

### Removed

### Deprecated

### Fixed

[Unreleased]: https://github.com/QuTech-Delft/QMI/releases/x.y.z
