"""AlphaLab Inc.; magnetic field meters.

The instruments.alphalab package provides support for:
- MR3 three-axis magnetic field meter, using the AlphaLab data acquisition communication protocol.
"""

from qmi.instruments.alphalab.mr3 import AlphaLab_MR3 as AlphaLab_MR3
from qmi.instruments.alphalab.mr3 import ParsedDataPoint as ParsedDataPoint
