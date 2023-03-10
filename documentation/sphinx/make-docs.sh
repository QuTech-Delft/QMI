#! /usr/bin/env bash

rm -rf source/generated
sphinx-apidoc --no-toc --module-first --separate -o source/generated ../../qmi ../../qmi/core/usbtmc.py
exec make clean html
