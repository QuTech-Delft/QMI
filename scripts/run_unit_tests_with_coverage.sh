#! /bin/bash

# Run unit tests and collect coverage statistics. Tests are expected in directory `test/` with pattern `test_*.py`.
# Positional arguments are sources (directories) to collect statistics for.
#
# Usage:
#    ./run_unit_tests_with_coverage.sh DIR ...

sdirs=$(IFS=, ; echo "$*")  # join arguments to comma-separated list

sudo coverage run --branch --source=$sdirs -m unittest discover --start-directory=tests --pattern="test_*.py"
