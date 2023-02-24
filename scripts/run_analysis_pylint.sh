#! /bin/bash

# Run pylint. Use only the score for code quality; MyPy is used for coding errors.
#
# Usage:
#    ./run_analysis_pylint.sh

# Run analysis
pylint --ignore="pydwf,mhlib_function_signatures.py" --reports=no --score=yes qmi/ > pylint.log

# Extract linting score from log file (penultimate line, first of two reported numbers)
SCORE=$( tail -n 2 pylint.log | grep -o '[0-9]\{1,2\}\.[0-9]\{2\}' | head -n 1 )
echo $SCORE
