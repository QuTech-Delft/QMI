"""
Stanford Research Systems; voltage source, SIM system mainframe and diode temperature monitor.

The qmi.instruments.picotech package provides support for:
- DC205 voltage source
- SIM900 mainframe
- SIM922 diode temperature monitor.
"""
# Alternative, QMI naming convention approved names
from qmi.instruments.stanford_research_systems.dc205 import SRS_DC205 as Srs_Dc205
from qmi.instruments.stanford_research_systems.sim900 import Sim900 as Srs_Sim900
from qmi.instruments.stanford_research_systems.sim922 import SIM922 as Srs_Sim922
