===============
Welcome to QMI!
===============

You are reading the documentation of QMI, the Quantum Measurement Framework.

What is it?
-----------

QMI is a Python 3 framework for controlling laboratory equipment. It is suitable for anything ranging from
one-off scientific experiments to robust operational setups.

QMI is developed by `QuTech <https://www.qutech.nl>`_ to support advanced physics experiments involving quantum bits.
However, other than its name and original purpose, there is nothing specifically *quantum* about QMI — it is potentially
useful in any environment where monitoring and control of measurement equipment is needed.

Features
--------

QMI has a number of nice features:

* It is fully open source;
* It is written in modern Python 3;
* It is properly documented;
* It is optimized for monitoring and control of complicated setups, distributed over multiple locations;
* It supports *instruments* that encapsulate equipment under computer control.
  A number of instruments are provided out of the box, and it is relatively easy to add your own;
* It supports *tasks* that encapsulate a (background) process that needs to run indefinitely;
* It offers *network transparency*; instruments and tasks can be remotely started, stopped, monitored and controlled;
* It is multi-platform. At QuTech, QMI is regularly used in both Linux and Windows,
  and running QMI on macOS is also possible.
