"""
Instrument driver for the Newport 843-R optical power meter.

This driver depends on PyUSB and works only on Linux.
"""

import sys
import time
import logging
import math

import typing
from typing import List, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

if sys.platform.startswith("linux") or typing.TYPE_CHECKING:
    # Newport USB access is only supported on Linux.
    from qmi.instruments.newport.newport_843r_libusb import Newport_843R_libusb


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Newport_843R(QMI_Instrument):
    """Instrument driver for the Newport 843-R optical power meter."""

    _rpc_constants = ["SENSOR_TYPES"]

    # Meaning of sensor type codes returned by the instrument.
    SENSOR_TYPES = {
        "BT": "BeamTrack",
        "CP": "Pyroelectric",
        "SI": "Photodiode",
        "TH": "Termopile",
        "XX": "No sensor connected"
    }

    # Time in seconds to wait before each write and read operation.
    # The power meter needs some time between write and read operations
    # and between commands. Without sufficient delay, the power meter
    # may occasionally crash.
    COMMAND_DELAY = 0.05

    @staticmethod
    def list_instruments() -> List[str]:
        """Return a list of serial numbers for attached Newport 843-R instruments."""
        return Newport_843R_libusb.list_instruments()

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 serial_number: str
                 ) -> None:
        """Initialize driver.

        :argument name: Name for this instrument instance.
        :argument serial_number: USB serial number.
        """
        super().__init__(context, name)
        self._serial_number = serial_number
        self._instr = None  # type: Optional[Newport_843R_libusb]
        self._last_query_time: float = 0.0

    @rpc_method
    def open(self) -> None:
        _logger.info("[%s] Opening connection instrument serial_number=%r", self._name, self._serial_number)
        self._check_is_closed()
        self._instr = Newport_843R_libusb(self._serial_number)
        self._last_query_time = time.monotonic()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("[%s] Closing connection to instrument", self._name)
        self._check_is_open()
        assert self._instr is not None
        self._instr.close()
        self._instr = None
        super().close()

    def ask(self, cmd: str) -> str:
        """Send command to instrument and return response from instrument."""
        self._check_is_open()
        assert self._instr is not None
        if not cmd.startswith("$"):
            raise QMI_InstrumentException("Command must start with '$'")
        rawcmd = cmd.encode('ascii') + b"\r\n"

        # Make sure there is enough time between commands.
        delay = self._last_query_time + self.COMMAND_DELAY - time.monotonic()
        if delay > 0:
            time.sleep(delay)

        self._instr.send_command(rawcmd)

        # Make sure there is enough time between write and read operations.
        time.sleep(self.COMMAND_DELAY)

        rawresp = self._instr.read_response(timeout=5)
        self._last_query_time = time.monotonic()

        resp = rawresp.decode('ascii', errors='replace')
        resp = resp.rstrip()
        if resp.startswith("?"):
            raise QMI_InstrumentException(f"Command '{cmd}' failed with error '{resp[1:]}'")
        if not resp.startswith("*"):
            raise QMI_InstrumentException(f"Unexpected response to '{cmd}', got '{resp}'")
        return resp

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        _logger.info("[%s] Resetting instrument", self._name)
        self.ask("$RE")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        instr_info = self.ask("$II")
        version_info = self.ask("$VE")
        words = instr_info[1:].strip().split()
        if len(words) != 3:
            raise QMI_InstrumentException(f"Unexpected response to $II, got '{instr_info}'")
        if not version_info.startswith("*EF"):
            raise QMI_InstrumentException(f"Unexpected response to $VE, got '{version_info}'")
        fw_version = version_info[3:]
        return QMI_InstrumentIdentification(vendor="Newport",
                                            model=words[2],
                                            serial=words[1],
                                            version=fw_version)

    @rpc_method
    def get_sensor_info(self) -> Tuple[str, str, str, str]:
        """Get sensor type and return information.

        :return: Tuple (sensor_type, serial_number, sensor_name, capabilities).
        """
        resp = self.ask("$HI")
        words = resp[1:].strip().split()
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to $HI, got '{resp}'")
        return (words[0], words[1], words[2], words[3])

    @rpc_method
    def get_filter_mode(self) -> bool:
        """Return True if the power meter is configured to work with a filter."""
        resp = self.ask("$FQ")
        words = resp[1:].split()
        i = int(words[0])
        if i < 1 or i >= len(words):
            raise QMI_InstrumentException(f"Unexpected response to $FQ, got '{resp}'")
        v = words[i].upper()
        if v not in ("IN", "OUT"):
            # Some types of sensors do not support filters and will return "* 1 N/A".
            # In this case we just report the filter is not enabled.
            _logger.warning("Unexpected response to $FQ, got %r", resp)
            return False
        return v == "IN"

    @rpc_method
    def set_filter_mode(self, filter_in: bool) -> None:
        """Configure the power meter to work with or without filter.

        If the filter configuration of the power meter does not match
        the actual presence of an attenuation filter, the meter will
        return wildly incorrect power measurements.

        :param filter_in: True to configure the meter with filter;
            False to configure the meter without a filter.
        """
        v = 2 if filter_in else 1
        self.ask(f"$FQ {v}")

    @rpc_method
    def get_power(self) -> float:
        """Return result of next power measurement (Watt).

        If the power meter sends an over-range response,
        this function returns +inf.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        """
        resp = self.ask("$SP")
        if resp[1:].upper() == "OVER":
            return math.inf
        return float(resp[1:])

    @rpc_method
    def get_timestamped_power(self) -> Tuple[float, float]:
        """Return a tuple of (unix_timestamp, measured_power).

        The timestamp is determined on the computer and may deviate
        from the actual time of the measurement.
        """
        resp = self.ask("$SP")
        timestamp = time.time()
        if resp[1:].upper() == "OVER":
            power = math.inf
        else:
            power = float(resp[1:])
        return (timestamp, power)

    @rpc_method
    def do_zero(self) -> None:
        """Perform a zeroing of internal circuits.

        Zeroing may take approximately 30 seconds.
        This function waits until zeroing is finished before returning.
        """
        resp = self.ask("$ZE")
        while True:
            time.sleep(0.25)
            resp = self.ask("$ZQ")
            status = resp[1:].strip()
            if not status.startswith("ZEROING IN PROG"):
                break
        if not status.startswith("ZEROING COMPLETE"):
            raise QMI_InstrumentException(f"Zeroing failed with error '{status}'")

    @rpc_method
    def zero_save(self) -> None:
        """Save the result of the preceding zero operation to device memory."""
        self.ask("$ZS")

    @rpc_method
    def get_available_ranges(self) -> List[str]:
        """Return a list of available range settings.

        Each range is formatted as a number with unit, e.g. "3.00uW".
        """
        resp = self.ask("$AR")
        words = resp[1:].strip().split()
        p = 1
        while p < len(words) and words[p].upper() in ("AUTO", "DBM"):
            p += 1
        return words[p:]

    @rpc_method
    def get_range(self) -> int:
        """Return the currently configured measuring range.

        The value -1 is returned if the instrument is in auto-range mode.
        Otherwise, this function returns an index into the list of available
        range settings, where 0 refers to the first available range.
        """
        resp = self.ask("$RN")
        return int(resp[1:].strip())

    @rpc_method
    def get_range_in_use(self) -> int:
        """Return the currently used measuring range.

        This function returns an index into the list of available range
        setting, where 0 refers to the first available range.

        When the instrument is in auto-range mode, this function returns
        the index of the automatically selected range.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        Other implementations may return the range as a floating point
        value in Watt.
        """
        resp = self.ask("$GU")
        return int(resp[1:].strip())

    @rpc_method
    def set_range(self, range_index: int) -> None:
        """Set the measurement range.

        Specify the value -1 to set the instrument to auto-range mode.
        Otherwise, specify an index into the list of available range settings,
        where 0 refers to the first available range.
        """
        self.ask(f"$WN {int(range_index)}")

    @rpc_method
    def set_autorange(self, enable: bool) -> None:
        """Enable or disable auto range mode.

        When autoranging is switched from enabled to disabled,
        the power meter will hold its last auto-selected range.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        """
        if enable:
            self.set_range(-1)
        else:
            selected_range = self.get_range_in_use()
            self.set_range(selected_range)

    @rpc_method
    def get_wavelength_range(self) -> Tuple[int, int]:
        """Return the range of available wavelengths.

        Returns a tuple (min_wavelength, max_wavelength).
        Wavelengths are expressed in nanometers.

        This command assumes that a continous-wavelength sensor is used.
        """
        resp = self.ask("$AW")
        words = resp[1:].strip().split()
        if len(words) < 4:
            raise QMI_InstrumentException(f"Unexpected response to $AW, got '{resp}'")
        if words[0].upper() != "CONTINUOUS":
            raise QMI_InstrumentException("Only continuous-wavelength sensors supported")
        wlow = int(words[1])
        whigh = int(words[2])
        return (wlow, whigh)

    @rpc_method
    def get_wavelength(self) -> int:
        """Return the current configured wavelength (nm).

        This command assumes that a continous-wavelength sensor is used.
        """
        resp = self.ask("$AW")
        words = resp[1:].strip().split()
        if len(words) < 4:
            raise QMI_InstrumentException(f"Unexpected response to $AW, got '{resp}'")
        if words[0].upper() != "CONTINUOUS":
            raise QMI_InstrumentException("Only continuous-wavelength sensors supported")
        index = int(words[3])
        if index < 1 or 3 + index >= len(words):
            raise QMI_InstrumentException(f"Unexpected response to $AW, got '{resp}'")
        wlen = int(words[3 + index])
        return wlen

    @rpc_method
    def set_wavelength(self, wavelength: int) -> None:
        """Configure the wavelength in nm.

        This function is part of a generic power meter API
        and must be supported by all power meter implementations.
        """
        self.ask(f"$WL {int(wavelength)}")

    @rpc_method
    def get_available_averaging(self) -> List[str]:
        """Return a list of available averaging modes.

        The first available mode is "NONE", i.e. no averaging.
        All other modes are formatted as a duration with unit, e.g. "3sec".
        """
        resp = self.ask("$AQ")
        words = resp[1:].strip().split()
        return words[1:]

    @rpc_method
    def get_averaging_mode(self) -> int:
        """Return the current averaging mode.

        This function returns an index into the list of available averaging
        modes, where 1 refers to the first available mode (which is "NONE").
        """
        resp = self.ask("$AQ")
        words = resp[1:].strip().split()
        return int(words[0])

    @rpc_method
    def set_averaging_mode(self, averaging_mode: int) -> None:
        """Set the averaging mode.

        Mode 1 is "NONE", i.e. no averaging.
        Otherwise, the specified value is an index into the list of
        available averaging modes, where 1 refers to the first available mode.
        """
        self.ask(f"$AQ {int(averaging_mode)}")
