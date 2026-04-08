ADbasic coding standard
=======================

This document describes the preferred coding style for ADbasic programs.


Indentation
-----------

Indentation should be used to delimit the body of macros, functions, loops, if-then blocks, etc.
Code should be indented by 4 spaces per level.
Only space characters should be used, no hard TAB characters.

The default setting of the ADbasic editor indents by 2 spaces.
This can be changed to 4 spaces under *Options* -> *Settings* -> *General*.


Upper/lower case
----------------

The ADbasic language is case-insensitive.
For readability and searchability of source code, it is important to use a consistent appearance for all
occurrences of a particular keyword or identifier.

ADbasic keywords should be written with each word capitalized (also known as *CapitalizedWords*).
This is the same style which is used in the ADbasic manual.
For example::

    Dim my_var As Long

    Event:
        If ((Par_1 < 2) And (Par_2 < 4)) Then
            ...
        EndIf

Functions and macros in the built-in library should be written in the same case as used
in the ADbasic manual.
This typically means capitalized words, but sometimes all capitals are used in case of abbreviations.
For example::

    P2_DAC(mod, chan, Round(1000 * FPar_1))
    P2_DigProg(mod, mask)
    P2_Digout_Long(mod, pattern)

Custom names for symbols, variables, macros and functions should use upper and lower case letters
in a consistent way. See below under *Names and prefixes* for further details on custom names.


Whitespace
----------

The first line of an ADbasic source file should be an empty line.
This is necessary to get correct line numbers in error messages from the ADbasic compiler.

When a comma is used to separate arguments, put a single space after the comma.
::

    Sub my_macro(arg1, arg2)
        ....
    EndSub

    my_macro(4, 5)


Include files
-------------

Custom include files may be used to modularize the ADbasic code.
In this case, the name of the include file should end in ``.inc`` and the file should appear in the same directory
as the ``.bas`` file that uses it.

To ensure that the compiler will find the include file, the include statement must explicitly specify
a path relative to the current directory.
A backslash must be used as the path separator.
For example::

    #Include .\my_file.inc

This way of specifying the include file path works under Linux as well as Windows.
Some other ways of specifying the path work either on Windows or on Linux, but not both.

Include files should themselves not contain any ``#Include`` statements.
All include statements should be located in the main ``.bas`` file.


Parameter mapping
-----------------

Communication between the ADwin and Python occurs via
global parameters ``Par_nn`` and global data arrays ``Data_nnn``.
It is convenient to assign names to these global variables
such that it becomes possible to refer to these variables by name instead of
by number.

The mapping of names to numbers can be achieved via ``#Define`` statements in ADbasic.
If these mappings are defined exactly as explained here, the QMI framework
will be able to recognize these definitions and the same variable names will
also be available in Python code.

Names can be assigned to 4 types of parameters: integer parameters, floating point parameters,
data arrays and individual array elements.
The following code example shows all of these forms::

    ' Bind the name "my_variable" to global integer parameter Par_12
    #Define PAR_my_variable Par_12

    ' Bind the name "my_float" to global floating point variable FPar_6
    #Define PAR_my_float FPar_6

    ' Bind the name "my_array" to global array Data_8
    #Define DATA_my_array Data_8

    ' Bind the name "another_parameter" to the 3rd element of array Data_11
    #Define DATA_more_params Data_11
    #Define PAR_another_parameter DATA_more_params[3]

With these definitions in place, the ADwin code can use the defined symbols
to directly access the underlying variables.
The QMI framework can recognize the definitions and provide the same
name-to-parameter mapping for the Python code.


Names and prefixes
------------------

When possible, functionality should be divided into separate *include* files.
We will refer to such files as *modules* here, although ADbasic does not support
a true concept of modules.

To avoid naming conflicts between files, each module should choose a unique short prefix for its global symbols.
For example ``LC`` for laser control, ``CR`` for CR-check, etc.

Custom names defined in one module and intended to be referenced by other modules,
should start with the module prefix followed by an underscore, e.g. ``CR_init``.
These names can be considered part of the public interface of the module.

Custom names intended to be used exclusively within the module that defines them,
should start with an underscore followed by the module prefix, e.g. ``_CR_last_success``.
The initial underscore will **not** actually protect such names from other modules,
but it makes it clear that these names are not intended as part of a public interface.

Constants created with ``#Define`` should be named in all uppercase letters
following the module prefix.
For example ``CR_MAX_CRCHECK_DURATION``.

The names of variables and functions should start with the uppercase module prefix,
followed by all lowercase letters for the rest of the name.
For example ``CR_init``.

A larger example::

    #Define CR_MAX_CRCHECK_DURATION  1000
    Dim _CR_last_success As Long

    Sub _CR_internal_subroutine()  ' This is a private helper function.
        _CR_last_success = 0
    EndSub

    Sub CR_start_check()  ' This is a public function.
        _CR_internal_subroutine()
    EndSub

