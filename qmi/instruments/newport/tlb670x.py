"""Instrument driver for the NewPort/NewFocus TLB-670x tunable laser controller.

This driver depends on the usbdll.dll library from New Focus. The permission for linking to the DLL library file, with
a proprietary license, has been explicitly granted by Newport Corporation to QuTech.
"""
import ctypes
import logging
import re
import sys
import time
from typing import Any, List, Tuple, Union

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

from .tlb670x_error_messages import ERROR_MESSAGES


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class NewFocus_TLB670X(QMI_Instrument):
    """Instrument driver for the New Focus TLB-670x USB tunable laser controller (Windows platforms only.)

    This driver requires that the DLL provided by NewFocus ("usbdll.dll") is on the DLL search path.

    This class contains a number of functions. Most importantly, the _send and _receive functions allow for sending
    strings and receiving the TLC response data via a buffer, respectively. The various command strings
    are invoked through functions defined in this class. The most important functions are the get_- and
    set_wavelength that can be used to change the TLC setpoint.
    """

    # Shared library file name.
    DLL_NAME = "usbdll.dll"

    # USB speed (baud).
    USB_SPEED = 480e6

    # Sleep time after reset (seconds).
    RESET_SLEEP_TIME = 7

    # Maximum buffer length (bytes).
    MAX_BUFFER_LENGTH = 64

    # Device identification.
    VENDOR_ID = 0x104D
    PRODUCT_ID = 0x100A

    def __init__(self, context: QMI_Context, name: str, serial_number: Union[int, str]) -> None:
        """Initialize the instrument driver.

        Parameters:
            context:        QMI_Context for the instrument
            name:           Name for this instrument instance.
            serial_number:  The controller's serial number in format <SNabcd>, where a, b, c, d are digits 0-9. Not
                            including 'SN' or providing the serial number as integer works too, but is discouraged.
        """
        # Check platform first.
        if not sys.platform.startswith("win"):
            raise RuntimeError("The NewFocus TLB670x QMI driver is only supported on Windows platforms!")

        # Initialize driver superclass.
        super().__init__(context, name)

        # Prepare handle to DLL and device; set in open().
        self._handle: Any = ctypes.WinDLL(self.DLL_NAME)
        self._device_id: int = -1  # Initialize with non-existing device number. The real values are in range [0-31].

        # Generously parse serial number.
        serial_number = str(serial_number)
        if not serial_number.startswith("SN"):
            _logger.warning("Serial number should start with SN, but got %s", serial_number)
            serial_number = "SN" + str(serial_number)
        self.serial_number: str = serial_number

    def _send(self, command_string: str) -> str:
        """Sends the given command to the device and returns the response as a tuple (response_code, response_value),
        where a non-zero `response_code` indicates that the device reported that executing the command failed. In this
        case, `response_value` will hold the error message. If the command was executed successfully, `response_code`
        will be 0 and `response_value` will be the response to the command as a string.

        Parameters:
            command_string: Command string to be parsed for sending.
        Returns:
            The controller response.
        Raises:
            QMI_InstrumentException if the controller returned an error code.
        """
        self._check_is_open()
        _logger.debug("Sending message to device: %s", command_string)

        # Prepare command.
        command = ctypes.create_string_buffer(self.MAX_BUFFER_LENGTH)
        command.value = command_string.encode()
        command_length = ctypes.c_ulong(len(command.value))

        # Send command and check for any errors.
        result = self._handle.newp_usb_send_ascii(self._device_id, ctypes.byref(command), command_length)
        if result != 0:
            # Command failed.
            error_msg = ERROR_MESSAGES.get(result, "Unknown error")
            _logger.error("Received error response: %s (%d)", error_msg, result)
            self._reinit_device()  # needed to clear error state
            raise QMI_InstrumentException(f"Command {command_string} returned an error {result}: {error_msg}")

        # Query for response.
        time.sleep(1.0 / self.USB_SPEED * command_length.value)
        response = self._receive()
        if "?" in command_string:
            # Check if response string consists of multiple responses, separated by "\r\n".
            if len(response) > 1 and response[-1] != "OK":
                # The response probably is this. But check for sporadic "*IDN?" query response first.
                idn_match = re.search(r"v\d.\d(.\d)? [\d/]+ SN[\d]+", response[-1])
                if idn_match:  # The entry is the invalid response, delete it
                    del response[-1]

                # OK check. Otherwise checks response[0].
                if response[-1] != "OK" and response[-1] != "+00":
                    return response[-1]

            if response[0] == "OK":
                # Otherwise, we did not get the correct response to our query, try to re-read once
                time.sleep(1.0 / self.USB_SPEED * command_length.value)
                response = self._receive()

        return response[0]

    def _receive(self) -> List[str]:
        """Query the controller for a command response.

        Returns:
            List of response strings from the controller.
        Raises:
            QMI_InstrumentException if the device returns an error code.
        """
        # Prepare buffer.
        buf_length = ctypes.c_ulong(self.MAX_BUFFER_LENGTH)
        buf = ctypes.create_string_buffer(buf_length.value)
        bytes_read = ctypes.c_ulong(64)

        # Query controller and check for any errors.
        result = self._handle.newp_usb_get_ascii(
            self._device_id, ctypes.byref(buf), buf_length, ctypes.byref(bytes_read)
        )
        if result != 0:
            error = ERROR_MESSAGES.get(result, "Unknown error")
            _logger.error("Received error response: %s (%d)", error, result)
            self._reinit_device()  # needed to clear error state
            raise QMI_InstrumentException(f"No response from device: {error} ({result})")

        # Decode response.
        response = buf.value.decode().split("\r\n")
        _logger.debug("Response from device: %s", response)
        # Pop out empty strings
        response = [r for r in response if r != ""]
        return response

    def _get_device_info(self) -> List[Tuple[int, str]]:
        """Get the contents of the device information buffer (a list of deviceID,deviceDescription pairs).

        Raises:
            QMI_InstrumentException: In cases where getting the device info fails for some reason.

        Returns:
            device_info: The found devices' info as a list of tuples (device ID#, device description string).
        """
        # Prepare buffer.
        buf_length = ctypes.c_ulong(self.MAX_BUFFER_LENGTH)
        buf = ctypes.create_string_buffer(buf_length.value)

        # Query controller and check for any errors.
        result = self._handle.newp_usb_get_device_info(ctypes.byref(buf))
        if result != 0:
            # Cannot do reinit here, because this method is used in init_device(); only raise exception that needs to
            # be handled by the caller.
            error = ERROR_MESSAGES.get(result, "Unknown error")
            raise QMI_InstrumentException(f"Unable to load device info: {error}")

        # Decode response; this is a ;-separated list of <deviceID>,<deviceDescription> pairs.
        response: str = buf.value.decode()
        device_info = []
        if response:
            for device in response.split(';'):
                if ',' in device:
                    device_id_str, device_descr_string = device.split(',')
                    device_info.append(
                        (int(device_id_str), device_descr_string)
                    )

        return device_info

    def _init_device(self) -> None:
        """Find and initialize the device ID for the device with the given serial number. For re-initialization no
        SN number check is done.

        Attributes:
            self._device_id: Set the device ID attribute if an instrument with matching serial number is found.
        Raises:
            QMI_InstrumentException: If no device with the correct serial number is found.
        """
        # (Re-)Open all USB devices that match the USB product ID.
        self._handle.newp_usb_init_product(self.PRODUCT_ID)

        # Get list of all devices found.
        device_info = self._get_device_info()
        if not device_info:
            self._uninit_device()
            raise QMI_InstrumentException("No TLB-670X instrument present")

        # Check if a device has already been found previously. If yes, no need to re-check with serial number.
        if self._device_id in range(32):
            return

        # The deviceDescription contains the serial number; find the one that matches our serial number.
        _logger.debug("Devices found: %s", device_info)
        for device_id, device_descr in device_info:
            serial_number_match = re.search(r"SN\d+", device_descr)
            if serial_number_match is not None and serial_number_match[0] == self.serial_number:
                self._device_id = device_id
                _logger.debug("Match: device_id=%d", device_id)
                return

        # Device not found.
        self._uninit_device()
        raise QMI_InstrumentException(f"No device with serial_number={self.serial_number} was found")

    def _uninit_device(self) -> None:
        """Uninitialize the device."""
        self._handle.newp_usb_uninit_system()

    def _reinit_device(self) -> None:
        """Reinitialize the device, clearing any errors."""
        self._check_is_open()
        _logger.debug("Reinitializing device to clear error state...")
        self._uninit_device()
        self._init_device()

    @rpc_method
    def open(self) -> None:
        """Open connection to the device controller."""
        super().open()
        _logger.info(f"Opening connection to {self._name}")
        self._init_device()

    @rpc_method
    def close(self) -> None:
        """Close connection to the device controller."""
        super().close()
        _logger.info(f"Closing connection to {self._name}")
        self._uninit_device()

    @rpc_method
    def get_available_devices_info(self) -> List[Tuple[int, str]]:
        """Get a list of all available devices that match the product ID for the TLB670-X."""
        self._check_is_open()
        try:
            device_info = self._get_device_info()
        except QMI_InstrumentException as exc:
            self._reinit_device()  # needed to clear error state
            raise exc

        return device_info

    @rpc_method
    def get_ident(self) -> QMI_InstrumentIdentification:
        """Get device identification."""
        return QMI_InstrumentIdentification(
            vendor="NewFocus", model="TLB670X", serial=self.serial_number, version=None
        )

    @rpc_method
    def get_device_id(self) -> int:
        """Get the device ID of the device."""
        self._check_is_open()
        return self._device_id

    @rpc_method
    def reset(self) -> None:
        """Reset the device."""
        _logger.info(f"Resetting {self._name}")

        # First check for errors.
        self.check_error_status()

        # Send reset command.
        try:
            self._send("*RST")
        except QMI_InstrumentException as exc:
            raise exc

        time.sleep(self.RESET_SLEEP_TIME)

    @rpc_method
    def check_error_status(self) -> str:
        """Check the error status of the device and return the error string if any.

        Returns:
            The error query response.
        """
        response = self._send("ERRSTR?")
        _logger.info(f"Error query response: {response}")
        return response

    @rpc_method
    def get_wavelength(self) -> float:
        """Get the current wavelength setpoint.

        Returns:
            The wavelength setpoint in nanometers.
        """
        response = self._send("SOURce:WAVElength?")
        return float(response)

    @rpc_method
    def set_wavelength(self, wavelength: float) -> None:
        """Set wavelength.

        Parameters:
            wavelength: wavelength in nanometers.
        """
        if wavelength <= 0:
            raise ValueError(f"Wavelength must be a positive number; got {wavelength}")

        self._send(f"SOURce:WAVElength {wavelength}")

    @rpc_method
    def get_powermode(self) -> int:
        """Get power state.

        Returns:
            Power output state as 0: laser off; 1: laser on.
        """
        response = self._send("OUTPut:STATe?")
        return int(response)

    @rpc_method
    def set_powermode(self, powermode: int) -> None:
        """Set power state.

        Parameters:
            powermode:  0 turns the laser off, 1 turns the laser on.
        """
        if powermode not in (0, 1):
            raise ValueError(f"Power mode must be 0 or 1; got {powermode}")

        self._send(f"OUTPut:STATe {powermode}")

    @rpc_method
    def get_trackingmode(self) -> int:
        """Get tracking state.

        Returns:
            Tracking state as 0: disabled; 1: enabled.
        """
        response = self._send("OUTPut:TRACk?")
        return int(response)

    @rpc_method
    def set_trackingmode(self, trackingmode: int) -> None:
        """Set tracking state.

        Parameters:
            trackingmode:  0: disable, 1: enable.
        """
        if trackingmode not in (0, 1):
            raise ValueError(f"Tracking mode must be 0 or 1; got {trackingmode}")

        self._send(f"OUTPut:TRACk {trackingmode}")

    @rpc_method
    def get_diode_current(self) -> float:
        """Get the laser diode current.

        Returns:
            Laser diode current in mA.
        """
        response = self._send("SENSe:CURRent:DIODe")
        return float(response)

    @rpc_method
    def set_diode_current(self, current: Union[int, float, str]) -> None:
        """Set the laser diode current in mA.

        Parameters:
            current:    either a float representing the desired current in mA, or the string literal 'MAX' to set the
                        current to the maximum allowable value.
        """
        if isinstance(current, (int, float)):
            if current <= 0:
                raise ValueError(f"Diode current must be a positive value; got {current}")
        elif isinstance(current, str):
            current = current.upper()
            if current != "MAX":
                raise ValueError(f"Invalid string for diode current setpoint; must be 'MAX', got {current}")
        else:
            raise ValueError(f"Invalid value for diode current setpoint: {current}")

        self._send(f"SOURce:CURRent:DIODe {current}")

    @rpc_method
    def get_piezo_voltage(self) -> float:
        """Retrieve the current piezo voltage.

        Returns:
            Piezo voltage as percentage of its range.
        """
        response = self._send("SOURce:VOLTage:PIEZo?")
        return float(response)

    @rpc_method
    def set_piezo_voltage(self, percentage: float) -> None:
        """Set the piezo voltage as percentage of its range.

        Parameters:
            percentage: piezo voltage percentage.
        """
        if not 0 <= percentage <= 100.0:
            raise ValueError(f"Percentage should be in range 0..100; got {percentage}")

        self._send(f"SOURce:VOLTage:PIEZo {percentage}")
