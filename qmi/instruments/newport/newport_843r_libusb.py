"""
Basic input/output access to the Newport 843-R power meter via USB.

This Python 3 module provides access to ASCII command interface of
the Newport 843-R-USB via its proprietary USB protocol.

This module uses PyUSB and works only on Linux.

Access permission
-----------------

To access the instrument, read/write permission to the USB device node
(/dev/usb/<bus>/<addr>) is required. This is typically accomplished
on Linux by adding a suitable rule in /etc/udev/rules.d. For example:

  /etc/udev/rules.d/99-newport_usb.rules:
  SUBYSTEM=="usb", ATTRS{idVendor}=="0bd3", ATTRS{idProduct}=="e345", GROUP="dialout", MODE="0660"

Command language
----------------

The USB access provided by this module enables the use of the ASCII command
set of the 843-R instrument as documented by Newport.
See "PMManager-User-Commands.pdf" or "Newport User Commands.pdf".

Command strings start with "$", followed by a two-letter command,
optionally followed by parameters, and ending with "\r\n".

In case of success, the instrument sends a response string starting with "*",
followed by a command-specific response format, and ending with "\n".

If an error occurs, the instrument sends a response string starting with "?",
followed by an error message and ending with "\n".

Streaming mode
--------------

In addition to the command/response flow, the instrument also supports
a streaming mode in which it spontaneously sends several power readings
per second via the USB interrupt endpoint 0x82. A sequence of undocumented
commands is required to enable this streaming mode. The streaming mode
is currently not supported by this Python module.

Protocol notes
--------------

The instrument has USB vendor ID 0x0BD3, vendor string "Freescale", product ID 0xE345, product string "843-R".

A serial number string is present in the USB descriptor.

The USB device class is 255 (vendor-specified), subclass 0.
The device supports 1 USB configuration, containing 1 interface.
The interface class is 255 (vendor-specified), subclass 255.

The interface contains 4 USB endpoints:
  - EP 0x81: interrupt IN, max 512 bytes (purpose unknown)
  - EP 0x82: interrupt IN, max 512 bytes (used in streaming mode)
  - EP 0x83: bulk IN, max 512 bytes (purpose unknown)
  - EP 0x04: bulk OUT, max 512 bytes (purpose unknown)

The request/response flow based on ASCII strings is implemented
via control transfers on the default control endpoint (EP 0x00).

To send a command string to the instrument, the computer initiates
the following control transfer:

  bmRequestType = 0x40 (host-to-device, vendor-specified, device request)
  bRequest = 2
  wValue = 0
  wIndex = 0
  data = command string (starting with "$", ending with "\\r\\n")

To read a response string from the instrument, the computer initiates
the following control transfer:

  bmRequestType = 0xc0 (device-to-host, vendor-specifid, device request)
  bRequest = 4
  wValue = 0
  wIndex = 0
  wLength = 2000

The device then responds with an answer string (starting with "*" or "?"
and ending with "\n").

Write command and read response transactions are sent in strict alternation.
Each command triggers exactly 1 response from the device.

The device-side implementation of this protocol is quite fragile.
Attempting to read a response when the instrument is not ready to
send a response will easily crash the USB interface to the point
where it can no longer respond to USB descriptor requests.
"""

import logging
from typing import List, Optional

import usb
import usb.core
import usb.util


class Newport_843R_libusb:
    """Basic input/output access to the Newport 843-R power meter via USB."""

    # USB vendor ID and product ID of Newport 843-R-USB.
    VENDOR_ID = 0x0BD3
    PRODUCT_ID = 0xE345

    # Interface index.
    INTERFACE = 0

    @classmethod
    def list_instruments(cls) -> List[str]:
        """Return serial numbers of attached Newport 843-R instruments.

        Scan the USB bus for attached Newport 843-R instruments and
        return a list of their serial numbers.
        """

        logger = logging.getLogger(__name__)
        logger.debug("Looking for attached instruments")

        instruments = []

        devs = usb.core.find(find_all=True,
                             idVendor=cls.VENDOR_ID,
                             idProduct=cls.PRODUCT_ID)
        for dev in devs:
            try:
                snr = dev.serial_number
            except Exception:
                # This happens if the user does not have permission
                # to open the USB device node /dev/usb/<bus>/<addr>.
                logger.exception("Can not read USB serial_number")
                continue
            instruments.append(snr)

        return instruments

    def __init__(self, serial_number: Optional[str]) -> None:
        """Open a connection to an attached Newport 843-R instrument.

        Note that read/write permission to the USB device node is
        required to access the instrument. This is typically accomplished
        on Linux by adding a suitable rule in /etc/udev/rules.d.

        :param serial_number: USB serial number of the device to open.
            When serial_number is None and only one device is atached,
            the single device will be selected automatically.
        :raises LookupError: When the specified instrument is not found;
            or when communication with the instrument fails.
        :raises USBError: If an error occurs at the USB level.
        """

        logger = logging.getLogger(__name__)
        logger.debug("Looking for attached instrument, serial_number=%r", serial_number)

        # Find matching instruments.
        instruments = []
        devs = usb.core.find(find_all=True,
                             idVendor=self.VENDOR_ID,
                             idProduct=self.PRODUCT_ID)
        for dev in devs:
            if serial_number is None:
                snr = None
            else:
                try:
                    snr = dev.serial_number
                except Exception:
                    # This happens if the user does not have permission
                    # to open the USB device node /dev/usb/<bus>/<addr>.
                    logger.exception("Can not read USB serial_number")
                    snr = None
            if serial_number == snr:
                # Found matching device.
                instruments.append(dev)

        # Fail if no matching instruments.
        if len(instruments) == 0:
            errmsg = "No Newport-843R instrument found"
            if serial_number is not None:
                errmsg += " with serial_number {}".format(serial_number)
            raise LookupError(errmsg)

        # Fail if multiple matching instruments.
        if len(instruments) != 1:
            raise LookupError("Multiple Newport-843R instruments found")

        # Select the single matching instrument.
        (self._dev,) = instruments

        # Detach kernel driver.
        driver_active = self._dev.is_kernel_driver_active(self.INTERFACE)
        if driver_active:
            self._dev.detach_kernel_driver(self.INTERFACE)

        # Select configuration.
        # This should also resets the USB protocol somewhat.
        self._dev.set_configuration()

        # Claim the interface.
        usb.util.claim_interface(self._dev, self.INTERFACE)

    def close(self) -> None:
        """Release USB device.

        :raises USBError: If an error occurs at the USB level.
        """

        if self._dev is not None:
            usb.util.dispose_resources(self._dev)
        self._dev = None

    def send_command(self, cmd: bytes, timeout: float = 1.0) -> None:
        """Send a command to the instrument and return the response.

        See the Newport documentation for a list of supported commands
        (PMManager-User-Commands.pdf).

        :param cmd: Command string to send to the instrument.
            The command is typically an ASCII string, starting with "$"
            and ending with "\\r\\n".
        :return: Response from the instrument.
        :raises USBError: If an error occurs on the USB level.

        """

        assert len(cmd) > 0
        assert len(cmd) < 64
        assert self._dev is not None

        bmRequestType = 0x40    # vendor-specific device request OUT
        bRequest = 2            # write request ?
        wValue = 0
        wIndex = 0
        timeout = int(1000 * timeout) + 1

        self._dev.ctrl_transfer(bmRequestType,
                                bRequest,
                                wValue,
                                wIndex,
                                cmd,
                                timeout)

    def read_response(self, timeout: float = 1.0) -> bytes:
        """Read a response string from the instrument.

        Warning: The USB interface in the instrument is extremely fickle.
        Attempting to read a response when the instrument is not ready
        to send a response, may crash the USB interface and require
        power-cycling of the instrument to recover.

        :param timeout: Maximum time to wait for the response (seconds).
        :return: Response from the instrument.
            The response is typically an ASCII string ending with "\\n".
        :raises USBError: If the device does not respond or when
            an error occurs on the USB level.
        """

        assert self._dev is not None

        bmRequestType = 0xc0    # vendor-specific device request IN
        bRequest = 4            # read request ?
        wValue = 0
        wIndex = 0
        wLength = 2000
        timeout = int(1000 * timeout) + 1

        data = self._dev.ctrl_transfer(bmRequestType,
                                       bRequest,
                                       wValue,
                                       wIndex,
                                       wLength,
                                       timeout)
        return data.tobytes()
