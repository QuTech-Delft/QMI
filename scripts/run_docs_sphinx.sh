#! /usr/bin/env bash

DOC_DIR="documentation/sphinx"
rm -rf $DOC_DIR/source/generated
sphinx-apidoc --no-toc --module-first --separate -o $DOC_DIR/source/generated qmi qmi/core/usbtmc.py
exec make -C $DOC_DIR clean html
