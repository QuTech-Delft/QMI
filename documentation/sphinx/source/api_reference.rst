=============
API Reference
=============

The QMI framework consists of several Python 3 packages and modules.

.. hint:: In Python, a *package* corresponds to a directory, whereas a *module* normally corresponds to a Python source file. The QMI framework is itself a package (directory), containing several sub-packages (subdirectories) and also modules (files ending in .py). Classes and functions are normally defined in the module files.

    The confusing part is that, *technically*, packages are themselves also modules, and contain the classes and functions defined in the file __init__.py that resides in their directory.

.. rubric:: QMI package overview

The QMI main package:

.. autosummary::
   :toctree: build
   :template: custom-package.rst

   qmi


The QMI framework consists of the following sub-packages:

.. autosummary::
   :toctree: build
   :template: custom-module.rst
   :recursive:

   qmi.core
   qmi.data
   qmi.instruments
   qmi.tools
   qmi.utils

Click on the package name to see more details.
