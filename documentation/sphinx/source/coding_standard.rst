===================
QMI Coding Standard
===================

This short document describes the Python coding standard for QMI, the Quantum Measurement Infrastructure framework.

Our baseline for the coding standard is PEP-8 (https://www.python.org/dev/peps/pep-0008/), which provide specific
guidelines on how to format Python code. We agree with 95\% of the rules stated there, but we deviate on some specific
rules.

The rules given in this document take precedence over the rules given in PEP-8.
Note that PEP-8 explicitly condones having project-specific coding style guidelines that supersede it.

The rules given in this document are not absolutes. If there are very good reasons to deviate in a specific place
in your code, feel free to do so. A generic disagreement with a particular PEP-8 rule or a rule given here is never
a good reason, though.

----------------
PEP-8 Deviations
----------------

In the following, we follow the subsection structure of PEP-8.
The ``▻`` symbol denotes a reference to a named section of PEP-8.
Section headers in this file will link to PEP-8 where appropriate.
Note that we only cite those sections where we deviate.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `Code Lay-out: Tabs or Spaces? <https://peps.python.org/pep-0008/#tabs-or-spaces>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Tabs are not allowed. Indentation is to be done solely with spaces. Only the standard PEP-8 indentation of 4 spaces is
allowed.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `Code Lay-out: Maximum Line Length <https://peps.python.org/pep-0008/#maximum-line-length>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

PEP-8 mandates a line length maximum of 79 characters, and 72 characters for docstrings and comments.

We feel this is too constraining, given today's wide-screen monitors.
We mandate only a maximum line length of 119 characters, both for code and for comments and docstrings.

^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `Code Lay-out: Blank Lines <https://peps.python.org/pep-0008/#blank-lines>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^

PEP-8 suggests that the ASCII Form Feed (12) characters may be used. Don't.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `Code Lay-out: Source File Encoding <https://peps.python.org/pep-0008/#source-file-encoding>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

All QMI source code files shall be UTF-8 files.

We are more restrictive in terms of allowed characters than PEP-8:

* Outside of string literals, only the ASCII characters 10 (newline) and 32—126 should be used.
* Inside of string literals, it is allowed to use diacritical characters such as é, ë, and µ.

End-of-line is denoted by a single newline (ASCII 10) character; this is the default Unix convention.

The carriage return character (ASCII 13) is not allowed in the source code.
The Windows combined end-of line marker of carriage return followed by newline is disallowed.

The last line of a Python source file must end in a single newline, with the possible exception of files that are
completely empty. This can happen with '``__init__.py``' files used to signify that a directory is a package.

^^^^^^^^^^^^^^^
▻ `String Quotes <https://peps.python.org/pep-0008/#string-quotes>`_
^^^^^^^^^^^^^^^

For strings, we use double-quote characters.

Exception #1: single character strings will be written with single quotes (as in C).

Exception #2: In Python, sometimes shorts strings are used as a substitute for enums. These enum-like strings are to be
written with single quotes.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `Whitespace in Expressions and Statements: Pet Peeves <https://peps.python.org/pep-0008/#pet-peeves>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We disagree with PEP-8 on forbidding more than one space around an assignment (or other) operator to align it with
another. We allow it if it helps readability. Use your judgement.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `Whitespace in Expressions and Statements: Other Recommendations <https://peps.python.org/pep-0008/#other-recommendations>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Trailing spaces are absolutely forbidden.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
▻ `When to Use Trailing Commas <https://peps.python.org/pep-0008/#when-to-use-trailing-commas>`_
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We allow trailing commas only if necessary, when writing a one-element tuple.
Always enclose one-element tuples in parentheses.

In all other cases, trailing commas in lists, tuples, etc. are forbidden.

^^^^^^^^^^
▻ `Comments <https://peps.python.org/pep-0008/#comments>`_
^^^^^^^^^^

Comments should be complete sentences and thus start with a capital letter and end with a period.

However, very sparingly, this may be overly verbose.
Sometimes a trailing single-word inline comment is clearer, for example.

In contrast to what is mandated by PEP-8, comment sentences should be separated by a single space.

All QMI code must be commented in English, using US-English spelling.

^^^^^^^^^^^^^^^^^^^^
▻ `Naming Conventions <https://peps.python.org/pep-0008/#naming-conventions>`_
^^^^^^^^^^^^^^^^^^^^

In general, follow PEP-8 recommendations.

However:

* When implementing Qt classes, adopt the Qt coding conventions instead; for example, use 'mixedCase' for method names.
* QMI classes all start with a ``QMI_`` prefix.
* QMI exceptions must end with the word *Exception*, rather than *Error*, as prescribed by PEP-8.

Often class member variables are initialized at init time, and read-only after that.  One solution to solve this is to
make a private member variable, and provide a property to read it.  However, throughout QMI, we will simply make a
variable name public, and explicitly document that the member is to be treated as read-only in the class documentation.

.. This last part does not seem related to naming (other than not using a leading underscore).

-------------------
Specific coding conventions
-------------------

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
``__init__.py`` files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
In case of the top-level ``qmi`` package we want to do a few things:

* Define the QMI version and check the Python version running QMI.
* Setup logging if the ``QMI_DEBUG`` environment variable is set. Otherwise start at ``qmi.start()``.
* Selectively import symbols into the top-level ``qmi`` package.

For instruments, you can use the ``__init__.py`` file to shorten import statements, by importing the instrument classes
there. So, instead of doing ``from qmi.instruments.dummy.instrument import Dummy_Instrument`` you can import shortened
``from qmi.instruments.dummy import Dummy_Instrument``.

Also please note that when using ``__init__.py`` to shorten
import statements, careless use of it can lead to circular referencing which will make the code crash. Even the order
of imports can have an effect on this.

Otherwise, you can keep ``__init__.py`` files empty or write a short docstring describing the package.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Assert statements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. Note that asserting is disabled if you run Python in performance mode, so asserts are not reliable error detection mechanisms.

Asserting is fine in cases where you need to assert something is really the case even if you are (nearly) 100% that it
is so. For example in more complex data analysis scripts, or you want to assert system state before moving on.

For class attributes that were initialized as ``None``, it is often necessary to assert it is not None anymore if it is
to be used later on in the code. But, try to avoid this and think if you can initialize otherwise.

It should **not** be used to check input parameters or user-given parameters, where rather a check should be employed
(with possibly raising an exception on wrong input).

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Logger naming policy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For modules that are not run as ``__main__``, we should always initialize the logger with
``logging.getLogger(__name__)``.

For modules that can be run as ``__main__``, we should make a check ``if __name__ is "__main__"`` and in that case set
the logger name manually.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Logging argument strings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We only use the "old" way of string formatting with logging, using the `%` sign. See the
`Python documentation <https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting>`_ for details.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Exception documentation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. This section is also vague: when is a function considered to be raising an exception "itself"?
.. I would think that a divide by zero would be an exception in the function itself, for instance.

If a function includes raise statement or statements,
the docstring should describe when the error or exception can be raised."

For example:
::
    Raises:
        ValueError: If value of 'b' is 0 as we cannot divide by zero.

If we do not have the check, we would get the ZeroDivisionError but that we do not write in the docstring,
as it comes from "outside", in this case from a builtin function.

-------------------
Semantic guidelines
-------------------

This section provides guidelines that are concerned with the functionality of the software, as opposed to the formatting
and presentation of the code.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The use of ``__init()__`` methods
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For __init__ function a few conventions can be made:
  - When in instrument class, do not try to open the instrument in __init__, as we have the ``open`` function for it.
  - Try to declare all necessary class attributes with type and possibly an initial value, but such that ``None`` is
    avoided as much as possible so that we do not need to do any assert ``self.xxx is not None`` later on.

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The use of ``__del__()`` methods
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``__del__()`` methods (also called finalizers) should be avoided in QMI code. A deviation to this is that if we use
an external module, like the ``usbtmc.py``, and there is already a ``__del__`` method, we do not try to "fix" this to
force to follow our convention.

It may seem that the ``__del__()`` method can be a nice way to do automatic clean up when an object goes out of scope,
just like a destructor would do in C++. However, such clean up attempts will often have unforeseen consequences and may
cause strange errors.

Instead of ``__del__()`` methods, QMI classes should provide ``close()``, ``stop()``, or ``cleanup()`` methods which are
explicitly called by the application.

Python ``__del__()`` methods are not similar to C++ destructors.
The semantics of ``__del__()`` are quite unfavourable for cleanup purposes:

* ``__del__()`` will be called even if ``__init__()`` raised an exception.
* ``__del__()`` may run in an arbitrary thread, different from the thread where the object was used.
* ``__del__()`` may be invoked during shutdown of the Python interpreter, when parts of the Python library are no longer
  functional.

See https://docs.python.org/3/reference/datamodel.html#object.__del__ for more information.
