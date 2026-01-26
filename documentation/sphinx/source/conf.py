# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# http://www.sphinx-doc.org/en/master/config

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

# We add the correct directory, enabling Sphinx to find our 'qmi_sphinx' extension.
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('../../..'))

# -- Project information -----------------------------------------------------

project = 'QMI'
copyright = '2019-2024, QuTech — Delft, The Netherlands'
author = 'QuTech'

# The full version, including alpha/beta/rc tags
release = '0.51.1'

# The default master_doc used to be 'index', but it was changed to 'contents'.
# Override that here (maybe rename the file to the new default later).
master_doc = 'index'
# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
#
# Order is important... autosummary should go before sphinx.ext.napoleon.
#

extensions = [ 'sphinx.ext.autodoc', 'sphinx.ext.autosummary', 'sphinx.ext.napoleon', 'sphinx.ext.todo' ]

autosummary_generate = True

autodoc_default_options = {
   # 'members'           : True,
   'member-order'      : 'bysource',
   # 'undoc_members'     : True,
   # 'private-members'   : False,
   # 'special-members'   : '',
   'inherited-members' : True,
   # 'show-inheritance'  : False,
   # 'ignore-module-all' : False,
   'imported-members'  : True
   # 'exclude-members'   : ''
}

todo_include_todos = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
#html_theme = 'alabaster'
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
#html_static_path = ['_static']
