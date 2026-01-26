# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


[0.51.1] - 2026-01-26

### Fixed
- `psutil._common` does not contain `snicaddr` namedtuple since version 7.2.0. It has been moved to `psutil._ntuples`. Fixed this in `proc.py`.
- Not setting `ziDAQServer` and `AwgModule` as global variables in `qmi.instruments.zurich_instruments.hdawg` caused them not to be available in the driver after importing them in the `_import_modules`. This is not fixed.

## [0.51.0] - 2025-12-09

### Added
- Thorlabs KDC101 controller QMI driver. It can at the moment control Z906, Z912 and Z925 actuators and PRMTZ8 rotation stage.
- New QMI driver for Agiltron FF1x8 optical switch.
- New QMI driver for Yokogawa DLM4038 oscilloscope.

### Changed
- The Agiltron FF optical switch QMI drivers have now common base class in `qmi.instruments.agiltron._ff_optical_switch`
- Refactored also unit-tests for Agiltron FF optical switches.
- Zurich Instruments HDAWG instrument driver now uses `zhinst.core` instead of `zhinst.ziPython`. Also the 'schema' is obtained now from the instrument itself, and not from a separate file.
- Changed `qmi_tool` to be also an executable script like `qmi_proc`.

### Fixed
- In `usbtmc.py` now doing `.strip()` on `dev.serial_number` string to avoid SNs with whitespace character(s).
- Fixed in `pyproject.toml` the executable `qmi_proc` and "adwin" scripts in "bin" to be in separate section w.r.t. the other scripts which should not be executable.

### Removed
- Zurich Instruments HDAWG instrument driver `hdawg_command_table.schema` file.

## [0.50.0] - 2025-09-01

### Added
- A QMI RPC proxy object docstring is now automatically expanded with:
  - A list of RPC methods
  - A list of signals
  - A list of class constants

### Changed
- The Thorlabs APT protocol is now the same for both K10CR1 and MPC320 instruments.
- The handling of discarding data and waiting for data during requests in APT protocol was improved. The waiting times are now directly from the class attribute DEFAULT_RESPONSE_TIMEOUT unless otherwise defined in calls.
- The dummy instrument now requires to be opened before using the RPC methods, by additions of open-checks.

### Fixed
- Tenma power supply unit CLI read current and voltage calls fixed to be the correct `get_...` calls.
- Critical fix on `qmi.tools.proc` where the main program should also have `run` as the main method, not `main`.
- The `is_move_completed` in Thorlabs_Mpc320 is fixed to work now, providing a short wait is used if it is called continuously in a loop until the response is True
- The unittests were fixed accordingly to changes for K10CR1 and MPC320 device driver tests.
- Corrections in documentation.

### Removed
- The obsolete Raspberry Pi relay example.

## [0.49.0] - 2025-05-19

### Added
- The log file existence is checked and necessary folder structure is created if needed.
- The log file maximum size and number of backups can now be set. Defaults are 10GB size and 5 backups (total of 60GB).
- An example of how to define logging options, in the docstring of `logging_init.py` module.

### Changed
- All entry point functions in `bin` scripts from `main` to `run` to avoid unintended modifications of `pyproject.toml` when executing release procedure.
- The `configstruct` wrapper from `qmi.core.config_struct` now accepts only modern typing for field. Most (but not all) of the `typing.<Type>` will not be parsed anymore by the type parser.
- The obsoleted "python3" commands were replaced with "python" in `tools.proc`.

### Fixed
- In `context_singleton.py`, the QMI 'log_dir' path is now correctly retrieved from QMI configuration file, if it is defined.
- For QMI configuration and log file locations, the path is made OS-independent and the `~` character, if at start of the path, is replaced with full path.
- Fixed `pyproject.toml` not to point to incorrect qmi location for package installation, but to root by removing [tool.setuptools.packages.find] lines.
- The 'venv' executable path was made OS-dependent ("win" or else) for creating 'venv' in `tools.proc`.

### Removed
- The support for most old `typing.<Type>` types for `configstruct` wrapper.

## [0.48.0] - Accidental tag push for release, release removed

## [0.47.0] - 2025-03-14

### Added
- Python 3.12, 3.13 support.
- installing of `py-xdrlib` from GitHub source for Python 3.13 unit-tests.
- HighFinesse Wavelength Meter (Wlm) driver with unittests, and license terms in wlmConst.py and wlmData.py.
- `RELEASE.md` release procedure using `bump2version` with multiple configuration files.

### Changed
- `qmi_tool` script entry point to be at `main` function.
- Package management to be done via `pyproject.toml` instead of `setup.py`.
- Digilent and PicoTech devices' typing fixed and modernized.

### Fixed
- Full CI-test to install qmi package correctly and run unit-tests with all supported Python versions.
- Some new typing issues, due to Mypy and Numpy updates, were fixed and respective modules were updated to 3.10+ Python style.
- Possible fix on the badges not showing on Pypi page.

### Removed
- Python 3.8, 3.9 and 3.10 support, numpy and scipy version restrictions in dependencies.
- `qmi_run_contexts` script as unused.


## [0.46.0] - 2024-10-14

### Added
- The `QMI_Instrument` and `QMI_TaskRunner` (which inherit from `QMI_RpcObject`) are now equipped with specific `__enter__` and `__exit__` methods, which in the case of `QMI_Instrument`
  also open and close the instrument when run with a `with` context manager protocol. Meanwhile `QMI_TaskRunner` starts and stops then joins a QMI task thread. In practise, these context managers
  can be used instead of the to-be-obsoleted `open_close` and `start_stop_join` context managers. The context manager protocol cannot be used for `QMI_RpcObject` directly.
- The Bristol FOS has now a QMI driver version that works on Windows PCs. Also the respective CLI has been added in `bin/instruments`.

### Changed
- The CI pipelines are now using reusable workflows, placed in reusable-ci-workflows.yml.
- The file names for the different pipeline actions were also changed to be more descriptive.

### Fixed
- mypy error on `config_struct.py` by adding extra logic check `and not isinstance(val, type)` on L236.
- Also made in `config_struct.py` in L186 also tuples to be recognized as "untyped values".
- workflow artifacts to be of @v4 instead of @v3 that are to be deprecated. For `setup-python` @v5 even.
- Implemented the rtscts keyword in TransportDescriptorParser for the (serial) transport factory.

## [0.45.0] - 2024-07-19

### Added
- QMI driver for TeraXion TFN in `qmi.instruments.teraxion` with CLI client.
- QMI driver for Thorlabs MPC320 in `qmi.instruments.thorlabs`.

### Changed
- In `setup.py` limited NumPy and SciPy versions to be <2. Also added missing line for Tenma 72 PSU CLI.
- Refactored Newport `single_axis_motion_controller.py` to use context manager to enter and exit a configuration state.

### Fixed
- mypy errors not failing pipeline
- In `instruments.picoquant.support._decoders` made the lexical sorting (`numpy.lexsort`) to temporarily retype the data to signed integer, as from Numpy 2.0 the integers are not allowed anymore to overflow.
- The same fix is applied also in unit-tests.

### Removed
- Radon workflows as radon is no longer actively maintained. Pylint has taken over as the complexity checker.

## [0.44.0] - 2024-01-25

### Added
- More logging on levels from INFO to DEBUG into PicoQuant device drivers.
- Added a new transport for communicating with instruments over UDP protocol. This works with transport string "udp:host:port".
- The `transport.py` was introduced with common base class for TCP and UDP protocols, where several implementations are present
  for functions that work the same for both protocols. Some modifications, especially for `read` functions, were required for doing this.
  Other functions were implemented separately.
- QMI drivers for Tenma 72-series power supply units in `qmi.instruments.tenma`

### Changed
- Refactored some unit-tests to use a QMI_Context patcher rather than the real thing, and adjusted the CI pipeline files and package requirements.
- Changed the stopping of contexts in `qmi_proc.proc_stop()` to happen in reverse order to `proc_start()`.
- `_RpcObjectMetaClass` inherits from ABCMeta instead of type. This allows it to be used as a mixin with other ABCs.
- PicoTech PicoSCope 3404 driver to accept also time-bases of 0 and 1 (sample intervals 1ns and 2ns).

### Fixed
- Improved PicoQuant unit-testing modules and comment line fixes on some other modules.
- Bug in Newport Single Axis Motion Controller that did not allow for negative relative moves.

## [0.43.0] - 2023-11-23

### Added
- Calls to enable and disable basik emission for `KoherasAdjustikLaser`.
- Implementation of `discard_read` on `QMI_UsbTmcTransport` class, and `read_until` now forwards to `read_until_timeout` instead of raising error.
- QMI_Vxi11Transport.read_until_timeout() implementation such that it calls self.read() with the given input.
- Tektronix AWG5014 driver now utilizes the `discard_read` in `reset()` instead of work-around `ask` call for `*CLS`.
- New transport `QMI_VisaGpibTransport` for the need of instruments using National Instruments' GPIB-USB-HS device. Windows only.
- New Transport string in fashion of "gpib:..." 
- QMI driver for WL Photonics narrowband tunable filter instrument: `qmi.instruments.wl_photonics.WlPhotonics_WltfN`

### Changed
- Non-interface breaking changes on `QMI_UsbTmcTransport` class calls `read` and `read_until_timeout`.
- QMI_Vxi11Transport.read() to not discard read data buffer at exception. It also returns data immediately if requested nbytes of data is already in the read buffer.
- QMI_Vxi11Transport.read_until() to not discard read data buffer at exception. It also returns data immediately if requested message terminator is already in the read buffer.
- Above methods now also apply the maximum read size of 512 bytes at a time, repeated in `while` loop until finish.
- QMI_Vxi11Transport.discard_read() to also empty current read buffer, and to restore instrument timeout correctly.

### Fixed
- Fixed a regexp line in TLB-670x driver to a raw string to avoid future warnings.
- Fixed TLB-670x driver to remove empty response strings that sometimes appear.

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
- Function to turn on/off system and to specify which parts of the system to turn off for Edwards TIC.

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
