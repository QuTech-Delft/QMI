#! /bin/bash

# Run maintainability index analysis. Positional arguments are source directories to analyse.
#
# Usage:
#    ./run_analysis_mi.sh DIR ...

# Run analysis
radon mi --show "$@" > radon-mi.log

# Determine minimum index value
python -c "
import re
min_index = 100
with open('radon-mi.log') as f:
    for line in f:
        m = re.findall(r'\(([0-9]+\.[0-9]{2})\)$', line.strip())  # match score between ( ) at end of line
        if m:
            s = float(m[0])
            if s < min_index:
                min_index = s
print(min_index)
"
