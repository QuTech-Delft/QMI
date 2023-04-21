import tests.instruments.picotech.ps3000a_stub as ps3000a
import tests.instruments.picotech.ps4000a_stub as ps4000a

class picosdk:
    def __init__(self):
        self.ps3000a = ps3000a.ps3000a()
        self.ps4000a = ps4000a.ps4000a()
