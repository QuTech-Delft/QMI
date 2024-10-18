============
Installation
============

`The QMI git repository <https://github.com/QuTech-Delft/QMI.git>`_ is hosted on GitHub.
While it is possible to install QMI by checking out the repository, for normal use we recommend installation via `pip`.

.. code-block:: shell

    pip install qmi

------------
Dependencies
------------

.. rubric:: Python version

QMI depends on Python 3.11 or newer.

.. rubric:: Python packages

QMI depends (directly or indirectly) on the following packages.
These packages can be installed via `pip`, if that is your preferred way of installing Python packages.

* Packages `numpy <https://pypi.org/project/numpy/>`_, `scipy <https://pypi.org/project/scipy/>`_, `h5py <https://pypi.org/project/h5py/>`_ and `matplotlib <https://pypi.org/project/matplotlib/>`_ for scientific data processing and visualisation;
* Packages `pyusb <https://pypi.org/project/pyusb/>`_, `python-vxi11 <https://pypi.org/project/python-vxi11/>`_ and `pyserial <https://pypi.org/project/pyserial/>`_ for hardware interfacing;
* Packages `pytz <https://pypi.org/project/pytz/>`_, `psutil <https://pypi.org/project/psutil/>`_, `jsonschema <https://pypi.org/project/jsonschema/>`_ and `colorama <https://pypi.org/project/colorama/>`_ for miscellaneous functionality;
* Packages `sphinx <https://pypi.org/project/sphinx/>`_ and `sphinx_rtd_theme <https://pypi.org/project/sphinx_rtd_theme/>`_ for generating documentation;
* Packages `pip <https://pypi.org/project/pip/>`_, `setuptools <https://pypi.org/project/setuptools/>`_, `wheel <https://pypi.org/project/wheel/>`_, and `twine <https://pypi.org/project/twine/>`_ for generating an installable package and deploying to `PyPi <https://pypi.org/>`_.

The following Python packages provide support for specific hardware. They are not hard dependencies: QMI will work fine without them, but you will be unable to use the instruments they support if they're not installed.

* Package `ADwin <https://pypi.org/project/ADwin/>`_ for Adwin instruments.
* Package `pydwf <https://pypi.org/project/pydwf/>`_ for Analog Discovery 2 instrument.
* Package `PyVISA <https://pypi.org/project/PyVISA/>`_ for certain Windows(-only) instruments.
* Package `uldaq <https://pypi.org/project/uldaq/>`_ for supporting MCC and MCC-based instruments (Bristol FOS);
* Package `zhinst <https://pypi.org/project/zhinst/>`_ for the Zürich Instruments AWG.
* Package `RPi.GPIO <https://pypi.org/project/RPi.GPIO/>`_ for controlling the digital pins of the Raspberry Pi.
Note that this list might not be complete, as by introduction of new hardware drivers, new packages could be added.

The QMI project uses Mypy and Pylint in checking the code quality. For local checks it is useful to have:

* Packages `pylint <https://pypi.org/project/pylint/>`_ and `mypy <https://pypi.org/project/mypy/>`_ for static code checks;


.. rubric:: Dependencies on closed-source drivers

* `Digilent <https://store.digilentinc.com/>`_ `Analog Discovery 2 <https://store.digilentinc.com/analog-discovery-2-100msps-usb-oscilloscope-logic-analyzer-and-variable-power-supply/>`_ and `Digital Discovery <https://store.digilentinc.com/digital-discovery-portable-usb-logic-analyzer-and-digital-pattern-generator/>`_;
* `PicoQuant <https://www.picoquant.com/>`_ `Multiharp 150 <https://www.picoquant.com/products/category/tcspc-and-time-tagging-modules/multiharp-150-high-throughput-multichannel-event-timer-tcspc-unit>`_;
* `Jäger Computergesteuerte Messtechnik <https://www.adwin.de/index-us.html>`_: `ADwin-Pro II <https://www.adwin.de/us/produkte/proII.html>`_;
* `Imagine Optic <https://www.imagine-optic.com/>`_ `mirao 52e <https://www.imagine-optic.com/product/mirao-52e/>`_.
Note that this list might not be complete, as by introduction of new hardware drivers, new dependencies could be added.

.. To be added:
..
.. import usb    "python3-usb"
.. from gi.repository import Aravis ; Aravis is Linux only. "gi.repository" ?? "gobject introspection" only used in Linux.
