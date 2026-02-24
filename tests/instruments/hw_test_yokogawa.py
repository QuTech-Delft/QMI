# USB\VID_0B21&PID_0038&REV_0000
import os
import usb.core
import usb.util
from usb.backend import libusb1
import pyvisa

os.environ["LIBUSBPATH"] = (
"C:\\Users\\heevasti\\AppData\\Local\\anaconda3\\envs\\qmi\\Lib\\site-packages\\usb1\\libusb-1.0.dll"
)
backend = libusb1.get_backend(
    find_library=lambda x: os.getenv("LIBUSBPATH"))

import qmi
from qmi.core.transport_usbtmc_visa import QMI_VisaUsbTmcTransport
from qmi.instruments.yokogawa import Yokogawa_Dlm4038
from qmi.utils.context_managers import start_stop

# dev = list(usb.core.find(find_all=True))
#
# counter = 0
# for d in dev:
#     try:
#         print("USB Device number " + str(counter) + ":" + "\n")
#         print(d._get_full_descriptor_str() + "\n")
#         print(str(d.get_active_configuration()) + "\n")
#         print("\n")
#         counter += 1
#     except NotImplementedError:
#         print("Device number " + str(counter) + "is busy." + "\n")
#         print("\n")
#         counter += 1
#     except usb.core.USBError:
#         print("Device number " + str(counter) + " is either disconnected or not found." + "\n")
#         print("\n")
#         counter += 1

print(QMI_VisaUsbTmcTransport.list_resources())
rm = pyvisa.ResourceManager()
print(rm.list_resources(), rm.list_resources_info())


with start_stop(qmi, "Yokogawa_test"):
    with qmi.make_instrument(
            "yo",
            Yokogawa_Dlm4038,
            "vxi11:172.16.17.43"
            # "usbtmc:vendorid=0x0b21:productid=0x0038:serialnr="  # 91P115733"  # 393150313135373333"
    ) as yo:
        print(yo.get_idn())

