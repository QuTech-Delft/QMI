"""
Instrument driver for the Tektronix FCA3000 and compatible frequency counters.
"""

import logging
import math
import struct
from typing import List, Optional, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Tektronix_FCA3000(QMI_Instrument):
    """Instrument driver for the Tektronix FCA3000 frequency counter.

    This driver is also compatible with the Pendulum CNT-91.
    """

    # Default response timeout in seconds.
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    def __init__(self, context: QMI_Context, name: str, transport: str) -> None:
        """Initialize the instrument driver.

        :param name: Name for this instrument instance.
        :param transport: Transport descriptor to access this instrument.
            For the Pendulum CNT-91, this is typically
            "usbtmc:vendorid=0x14eb:productid=0x0x0091:serialnr=<device_serial_number>"
        """

        super().__init__(context, name)
        self._transport = create_transport(transport)
        self._scpi_transport = ScpiProtocol(self._transport)

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    @rpc_method
    def reset(self) -> None:
        """Reset the instrument, returning (most) settings to their defaults."""
        self._scpi_transport.write("*RST")
        self._scpi_transport.ask("*OPC?")

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        resp = self._scpi_transport.ask("*IDN?")
        words = resp.rstrip().split(",")
        if len(words) != 4:
            raise QMI_InstrumentException(f"Unexpected response to *IDN?, got {resp!r}")
        return QMI_InstrumentIdentification(
            vendor=words[0].strip(),
            model=words[1].strip(),
            serial=words[2].strip(),
            version=words[3].strip(),
        )

    @rpc_method
    def get_errors(self) -> List[str]:
        """Read pending error messages from the instrument."""
        errors = []
        while True:
            resp = self._scpi_transport.ask("SYST:ERR?")
            if resp.startswith("0,"):
                break
            errors.append(resp)
        return errors

    @rpc_method
    def measure_frequency(self, channel: int = 1) -> float:
        """Start a single frequency measurement and return frequency [Hz].

        No configuration of the instrument is needed prior to this command.
        Each invocation of this command reconfigures the instrument.

        This command is easy to use but quite slow. It will typically take
        0.1 to 0.2 seconds to complete.

        Note: Attempting to read a frequency when there is no valid signal
        on the input of the frequency counter, may crash the USB connection
        to the instrument. When errors occur, the instrument must be
        power-cycled to recover.

        :param channel: Input channel to use (1 = channel A, 2 = channel B).
        """
        resp = self._scpi_transport.ask(f"MEAS:FREQ? (@{channel})")
        freq = float(resp.rstrip())
        return freq

    @rpc_method
    def configure_frequency(
        self,
        channel: int = 1,
        aperture: Optional[float] = None,
        trigger_level: Optional[float] = None,
        timestamp: bool = False,
    ) -> None:
        """Configure the instrument for frequency measurements.

        After this function returns, you can perform a series of measurements
        by calling read_value() or read_timestamped_value() in a loop.

        :param channel: Input channel for frequency measurements (1 = channel A, 2 = channel B).
        :param aperture: Acquisition time per measurement in seconds (default 0.01).
        :param trigger_level: Optional fixed trigger level.
            By default, the trigger level is set automatically at the beginning of each measurement.
            Setting a fixed trigger level makes the measurement faster.
        :param timestamp: True to enable timestamping of measurement values.
        """
        self._scpi_transport.write(f"CONF:FREQ (@{channel})")
        if aperture is not None:
            self._scpi_transport.write(f"ACQ:APER {aperture:.6g}")
        if trigger_level is not None:
            self._scpi_transport.write(f"INP{channel}:LEV:AUTO 0")
            self._scpi_transport.write(f"INP{channel}:LEV {trigger_level:.6g}")
        self._scpi_transport.write(f"FORM:TINF {int(timestamp)}")

    @rpc_method
    def read_value(self) -> float:
        """Read the next value in an ongoing measurement.

        Before calling this function, the instrument must be configured
        by calling configure_frequency().
        """
        response = self._scpi_transport.ask("READ?")
        words = response.split(",")
        return float(words[0])

    @rpc_method
    def read_timestamped_value(self) -> Tuple[float, float]:
        """Read a timestamped value in an ongoing measurement.

        Before calling this function, the instrument must be configured
        by calling configure_frequency() and timestamping must be enabled.

        :return: Tuple (timestamp, value) where "timestamp" is a relative timestamp in seconds.
        """
        response = self._scpi_transport.ask("READ?")
        words = response.split(",")
        if len(words) < 2:
            raise QMI_InstrumentException(
                f"Expecting timestamped value but got {response!r}"
            )
        val = float(words[0])
        timestamp = float(words[1])
        return timestamp, val

    @rpc_method
    def set_talk_only(self, enable: bool) -> None:
        """Enable or disable Talk Only mode.

        When the instrument is in talk only mode, the application must call
        get_value_talk_only() at short intervals to read each subsequent
        value from the instrument. No other commands to the instrument are
        allowed, except set_talk_only() to disable talk only mode.

        Usage example:

        .. code-block:: python

           instr.configure_frequency(channel=1, aperture=0.002, trigger_level=0)
           instr.set_talk_only(True)
           for i in range(n):
               (ts, freq) = instr.get_value_talk_only()
           instr.set_talk_only(False)

        This mode works only when the device is connected via GPIB, not USB.
        """
        self._check_is_open()

        # IFC - Interface Clear - to force the instrument out of Talk Only mode.
        # This is a special command which is interpreted by the Prologix
        # GPIB-ethernet adapter.
        self._scpi_transport.write("++ifc")

        # Read pending data in case the instrument was still sending.
        self._transport.read_until_timeout(nbytes=16384, timeout=1.0)

        # Check that the instrument is back to normal.
        self._scpi_transport.ask("*OPC?")

        if enable:
            # Enable binary mode (required for talk only).
            self._scpi_transport.write("FORM PACK")

            # Disable display (required for talk only).
            self._scpi_transport.write("DISP:ENAB 0")

            # Enable continuous initiating (required for talk only).
            self._scpi_transport.write("INIT:CONT 1")

            # Switch to talk only mode.
            self._scpi_transport.write("SYST:TALK 1")

            # Discard the first data value (it is usually invalid).
            self._scpi_transport.read_binary_data()

    @rpc_method
    def get_value_talk_only(self) -> Tuple[float, float]:
        """Read the next value in an ongoing measurement.

        Before calling this function, the instrument must be configured
        by calling configure_frequency() and then switched to talk only
        mode by calling set_talk_only(True).

        :return: Tuple (timestamp, value) where "timestamp" is a relative
            timestamp in seconds. If timestamping is not enabled in the
            instrument, a NaN value will be returned as timestamp.
        """
        resp = self._scpi_transport.read_binary_data()
        if len(resp) == 16:
            (val, timestamp) = struct.unpack(">dq", resp)
            timestamp = 1.0e-12 * timestamp
        else:
            (val,) = struct.unpack(">d", resp)
            timestamp = math.nan
        return (timestamp, val)

    @rpc_method
    def get_trigger_level(self, channel: int) -> float:
        """Read current trigger level used by the instrument.

        :param channel: Input channel (1 = channel A, 2 = channel B).
        :return: Trigger level in Volt.
        """
        response = self._scpi_transport.ask(f"INP{channel}:LEV?")
        return float(response)

    @rpc_method
    def set_display_enabled(self, enable: bool) -> None:
        """Enable or disable the display on the instrument operating panel.

        Measurements can be (slightly) faster when the display is disabled.

        :param enable: True to enable the display, False to disable it.
        """
        self._scpi_transport.write(f"DISP:ENAB {int(enable)}")

    @rpc_method
    def set_initiate_continuous(self, enable: bool) -> None:
        """Enable or disable continuous measurements.

        Enable continuous measurements to let the instrument spontaneously
        measure new values as fast as possible. This is useful to continuously
        refresh the value on the display of the operating panel while the
        instrument is not in use by software.

        Continuous measurements are automatically disabled when the
        instrument is configured to measure via software.

        :param enable: True to enable continous measurements.
        """
        self._scpi_transport.write(f"INIT:CONT {int(enable)}")
