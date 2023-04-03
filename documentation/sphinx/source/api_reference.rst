=============
API Reference
=============

The QMI framework consists of several Python 3 packages and modules.

.. hint:: In Python, a *package* corresponds to a directory, whereas a *module* normally corresponds to a Python source file. The QMI framework is itself a package (directory), containing several sub-packages (subdirectories) and also modules (files ending in .py). Classes and functions are normally defined in the module files.

    The confusing part is that, *technically*, packages are themselves also modules, and contain the classes and functions defined in the file __init__.py that resides in their directory.

.. rubric:: QMI package overview

The QMI framework consists of the following packages:

+------------------------+----------------------------------------------------------------------------+
| package                | description                                                                |
+========================+============================================================================+
| :mod:`qmi`             | Toplevel entry-point to access QMI functionality.                          |
+------------------------+----------------------------------------------------------------------------+
| :mod:`qmi.core`        | Core functionality of QMI, such as `contexts`, `instruments`, and `tasks`. |
+------------------------+----------------------------------------------------------------------------+
| :mod:`qmi.instruments` | QMI instrument drivers for specific types of instruments.                  |
+------------------------+----------------------------------------------------------------------------+
| :mod:`qmi.data`        | Functionality for data handling.                                           |
+------------------------+----------------------------------------------------------------------------+
| :mod:`qmi.analysis`    | Functionality for data analysis.                                           |
+------------------------+----------------------------------------------------------------------------+
| :mod:`qmi.tools`       | Functionality on which the QMI command line tools are based.               |
+------------------------+----------------------------------------------------------------------------+
| :mod:`qmi.utils`       | Miscellaneous functionality that doesn't fit elsewhere.                    |
+------------------------+----------------------------------------------------------------------------+

.. rubric:: Full list of QMI packages and modules [Test 9b]:

.. autosummary::
   :toctree: DIRNAME
   :template: module-template.rst
   :recursive:

   qmi
