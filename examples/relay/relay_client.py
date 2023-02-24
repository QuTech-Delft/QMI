#! /usr/bin/env python3

import qmi

qmi.start("relay_client", "qmi.conf")

qmi.show_instruments()

relay = qmi.get_instrument("relay_server.relay")

print(relay.get_value())
