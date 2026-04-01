#! /usr/bin/env bash
# This file is not executable, so the shebang won't do anything.

DOC_DIR="documentation/sphinx"
rm -rf $DOC_DIR/source/generated
# There seems to be no makefile at this location.
sphinx-apidoc --no-toc --module-first --separate -o $DOC_DIR/source/generated qmi qmi/core/usbtmc.py\
exec make -C $DOC_DIR clean html
