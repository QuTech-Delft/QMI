"""
Tenma (Newark Electronics) power supply units.

The qmi.instruments.tenma package provides support for:
- Series 72 power supply unit groups
  - 72-2535, 72-2540, 72-2545, 72-2550, 72-2925, 72-2930, 72-2935, 72-2940 & 72-10480
  - 72-13350 & 72-13360
"""
import importlib

tenma_module = importlib.import_module("qmi.instruments.tenma.psu_72")
psu_classes = {name: cls for name, cls in dict(vars(tenma_module)).items() if name.startswith("Tenma")}
for k, v in psu_classes.items():
    if "Base" not in k:
        globals()[k] = v
