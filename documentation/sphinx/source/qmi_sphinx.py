""" This is a Sphinx extension that takes care of some peculiarities of the QMI code base.
"""


def autodoc_process_docstring_func(app, what, name, obj, options, lines):
    if hasattr(obj, "_rpc_method"):
        lines.append('')
        lines.append('Note:')
        lines.append('    This is an rpc-callable method.')


def autodoc_skip_member_func(app, what, name, obj, skip, options):
    if name == "Proxy":
        return True  # skip this member
    # Do not skip __init__ methods with an explicit docstring.
    # See https://stackoverflow.com/questions/5599254/how-to-use-sphinxs-autodoc-to-document-a-classs-init-self-method
    if name == "__init__" and getattr(obj, "__doc__"):
        return False
    # Skip auto-generated docstrings of namedtuple fields.
    if (isinstance(obj, property)
            and obj.__doc__
            and obj.__doc__.startswith("Alias for field number")):
        return True
    # Skip attributes which are created through __slots__ declarations.
    if (what == "class") and (type(obj) is object):
        return True
    return None  # Fall back on default behavior.


def setup(app):
    app.connect('autodoc-skip-member', autodoc_skip_member_func)
    app.connect('autodoc-process-docstring', autodoc_process_docstring_func)

    return {
        'version' : '0.1',
        'parallel_read_safe' : True,
        'parallel_write_safe' : True
    }
