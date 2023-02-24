#! /bin/bash

# Run cyclomatic complexity analysis. Positional arguments are source directories to analyse.
#
# Usage:
#    ./run_analysis_cc.sh DIR ...

# Run analysis
radon cc --show-complexity --order=SCORE "$@" > radon-cc.log

# Determine maximum score
python -c "
import re
max_score = 0
with open('radon-cc.log') as f:
    for line in f:
        m = re.findall(r'\(([0-9]+)\)$', line.strip())  # match score between ( ) at end of line
        if m:
            s = int(m[0])
            if s > max_score:
                max_score = s
print(max_score)
"
