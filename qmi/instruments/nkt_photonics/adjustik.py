"""QMI driver for the NKT Photonics Instruments "Adjustik" laser driver.

The communication protocol to the laser driver is documented in the "Software Development Kit for NKT Photonics
Instruments - Instruction Manual" document, v2.1.3, Oct 2018. [Reference 1].

Chapter 2 of this document describes the NKT Photonics Interbus protocol (physical, framing, CRC, etc.)

module type      standard address         section     description

20h              0Fh                      6.2         Koheras AdjustiK/BoostiK System (K81-1 to K83-1)
34h              80h                      6.3         Koheras ADJUSTIK/ACOUSTIK System (K822/K852)
21h              0Ah                      6.4         Koheras BasiK Module (K80-1)
36h              01h (default; settable)  6.5         Koheras BASIK MIKRO Module (K0x2)
33h              01h (default; settable)  6.6         Koheras BASIK MIKRO Module (K1x2)
70h              02h                      6.7         BoostiK OEM Amplifier (N83)
60h              15h                      6.7         BoostiK OEM Amplifier (N83)

Chapter 6 of this document describes the Register Files for different devices.
"""

import logging
import struct
from typing import Tuple

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method
from qmi.core.transport import create_transport
from qmi.instruments.nkt_photonics.nkt_photonics_interbus_protocol import NKTPhotonicsInterbusProtocol

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class KoherasAdjustikLaser(QMI_Instrument):

    # Unfortunately the laser does not always respond.
    # Most requests get a response within 0.1 seconds.
    # If the laser responds at all, it almost always responds within 0.8 seconds.
    # When this timeout is exceeded, the request will be retried.
    RESPONSE_TIMEOUT = 1.0

    BASIK_ADDRESS = 0x01
    ADJUSTIK_ADDRESS = 0x80

    def __init__(self, context: QMI_Context, name: str, transport: str):
        super().__init__(context, name)
        self._transport = create_transport(transport,
                                           default_attributes={
                                               "baudrate": 115200,
                                               "bytesize": 8,
                                               "parity": 'N',
                                               "stopbits": 1.0,
                                               "rtscts": True})
        self._interbus = NKTPhotonicsInterbusProtocol(self._transport, self.RESPONSE_TIMEOUT)

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s", self._name)
        self._transport.open()
        self._transport.discard_read()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        super().close()
        self._transport.close()

    # BASIK module interface, as described in Section 6.6 of the documentation.
    # The BASIK module refers to a specific laser controller.
    # 6.6.1 : BASIK module --- general settings.

    @rpc_method
    def get_basik_module_type(self) -> int:
        """Return BASIK module type. Should be 0x33."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x61)
        unpacked_response = struct.unpack("<B", response)[0]
        return unpacked_response

    @rpc_method
    def get_basik_emission(self) -> int:
        """Emission status."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x30)
        unpacked_response = struct.unpack("<B", response)[0]
        return unpacked_response

    def _set_basik_emission(self, status: bool) -> None:
        """
        Set emission status.

        Parameters:
            status: the status of the laser to be set. True for on and False for off.
        """
        value = struct.pack("<B", int(status))
        self._interbus.set_register(self.BASIK_ADDRESS, 0x30, value)

    @rpc_method
    def enable_basik_emission(self) -> None:
        """
        Enable basik emission.
        """
        self._set_basik_emission(True)

    @rpc_method
    def disable_basik_emission(self) -> None:
        """
        Disable basik emission.
        """
        self._set_basik_emission(False)

    @rpc_method
    def get_basik_setup_bits(self) -> int:
        """Return the setup bits.

        bit 0: -
        bit 1: wide wavelength modulation range
        bit 2: enable external wavelength modulation
        bit 3: wavelength modulation DC coupled
        bit 4: enable internal wavelength modulation
        bit 5: enable modulation output
        bit 6: -
        bit 7: -
        bit 8: pump operation constant current
        bit 9: external amplitude modulation source
        """
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x31)
        unpacked_response = struct.unpack("<H", response)[0]
        return unpacked_response

    @rpc_method
    def set_basik_setup_bits(self, bits: int) -> None:
        """Set the setup bits."""
        value = struct.pack("<H", bits)
        self._interbus.set_register(self.BASIK_ADDRESS, 0x31, value)

    @rpc_method
    def get_basik_output_power_setpoint_mW(self) -> float:
        """Return the output power setpoint, in [mW]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x22)
        unpacked_response = struct.unpack("<H", response)[0] / 100.0
        return unpacked_response

    @rpc_method
    def set_basik_output_power_setpoint_mW(self, power: float) -> None:
        """Set the the output power setpoint, in [mW]."""
        value = struct.pack("<H", int(round(power * 100.0)))
        self._interbus.set_register(self.BASIK_ADDRESS, 0x22, value)

    @rpc_method
    def get_basik_output_power_setpoint_dBm(self) -> float:
        """Return the output power setpoint, in [dBm].

        Should be equal to 10.0 * log10(output_power_setpoint_mW).
        """
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0xa0)
        unpacked_response = struct.unpack("<h", response)[0] / 100.0
        return unpacked_response

    @rpc_method
    def set_basik_output_power_setpoint_dBm(self, power: float) -> None:
        """Set the output power setpoint, in [dBm].

        Should be equal to 10.0 * log10(output_power_setpoint_mW).
        """
        value = struct.pack("<h", int(round(power * 100.0)))
        self._interbus.set_register(self.BASIK_ADDRESS, 0xa0, value)

    @rpc_method
    def get_basik_wavelength_offset_setpoint(self) -> float:
        """Return the wavelength offset setpoint, in [pm]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x2a)
        unpacked_response = struct.unpack("<h", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def set_basik_wavelength_offset_setpoint(self, setpoint: float) -> None:
        """Set the wavelength offset setpoint, in [pm]."""
        setpoint_int = int(round(setpoint * 10.0))
        value = struct.pack("<h", setpoint_int)

        self._interbus.set_register(self.BASIK_ADDRESS, 0x2a, value)

    @rpc_method
    def get_basik_user_area(self) -> bytes:
        """Return the 240-byte user area contents."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x8d)
        return response  # Return raw 'bytes' instance. No unpacking needed.

    # 6.6.2 : BASIK module --- readouts.

    @rpc_method
    def get_basik_status_bits(self) -> int:
        """Return BASIC module type."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x66)
        unpacked_response = struct.unpack("<H", response)[0]
        return unpacked_response

    @rpc_method
    def get_basik_output_power_mW(self) -> float:
        """Return the output power readout, in [mW]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x17)
        unpacked_response = struct.unpack("<H", response)[0] / 100.0
        return unpacked_response

    @rpc_method
    def get_basik_output_power_dBm(self) -> float:
        """Return the output power readout, in [dBm].

        Should be equal to 10.0 * log10(output_power_mW).
        """
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x90)
        unpacked_response = struct.unpack("<h", response)[0] / 100.0
        return unpacked_response

    @rpc_method
    def get_basik_standard_wavelength(self) -> float:
        """Return the standard wavelength, in [pm]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x32)
        unpacked_response = struct.unpack("<L", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def get_basik_wavelength_offset(self) -> float:
        """Return the wavelength offset, in [pm]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x72)
        unpacked_response = struct.unpack("<l", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def get_basik_module_temperature(self) -> float:
        """Return the module temperature, in [°C]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x1c)
        unpacked_response = struct.unpack("<H", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def get_basik_module_supply_voltage(self) -> float:
        """Return the module supply voltage, in [V]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x1e)
        unpacked_response = struct.unpack("<H", response)[0] / 1000.0
        return unpacked_response

    @rpc_method
    def get_basik_module_wavelength_modulation_enabled(self) -> int:
        """Undocumented: wavelength modulation on?"""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0xb5)
        unpacked_response = struct.unpack("<B", response)[0]
        return unpacked_response

    # 6.6.3 : BASIK module --- modulation.

    @rpc_method
    def get_basik_wavelength_modulation_frequency(self) -> Tuple[float, float]:
        """Return the two wavelength modulation frequencies, in ([Hz], [Hz])."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0xb8)
        unpacked_response = struct.unpack("<ff", response)
        return unpacked_response  # type: ignore

    @rpc_method
    def set_basik_wavelength_modulation_frequency(self, freq0: float, freq1: float) -> None:
        """Set the wavelength modulation frequency, in [Hz]."""
        value = struct.pack("<ff", freq0, freq1)
        self._interbus.set_register(self.BASIK_ADDRESS, 0xb8, value)

    @rpc_method
    def get_basik_wavelength_modulation_level(self) -> float:
        """Return the wavelength modulation level, in [%]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x2b)
        unpacked_response = struct.unpack("<H", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def set_basik_wavelength_modulation_level(self, level: float) -> None:
        """Set the wavelength modulation level, in [%]."""
        level_int = int(round(level * 10.0))
        value = struct.pack("<H", level_int)

        self._interbus.set_register(self.BASIK_ADDRESS, 0x2b, value)

    @rpc_method
    def get_basik_wavelength_modulation_offset(self) -> float:
        """Return the wavelength modulation offset, in [%]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x2f)
        unpacked_response = struct.unpack("<h", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def set_basik_wavelength_modulation_offset(self, offset: float) -> None:
        """Set the wavelength modulation offset, in [%]."""
        offset_int = int(round(offset * 10.0))
        value = struct.pack("<h", offset_int)
        self._interbus.set_register(self.BASIK_ADDRESS, 0x2f, value)

    @rpc_method
    def get_basik_amplitude_modulation_frequency(self) -> Tuple[float, float]:
        """Return the two amplitude modulation frequencies, in ([Hz], [Hz])."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0xba)
        unpacked_response = struct.unpack("<ff", response)
        return unpacked_response  # type:ignore

    @rpc_method
    def get_basik_amplitude_modulation_depth(self) -> float:
        """Return the amplitude modulation depth, in [%]."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0x2c)
        unpacked_response = struct.unpack("<H", response)[0] / 10.0
        return unpacked_response

    @rpc_method
    def get_basik_modulation_setup_bits(self) -> int:
        """Return the modulation setup bits."""
        response = self._interbus.get_register(self.BASIK_ADDRESS, 0xb7)
        unpacked_response = struct.unpack("<H", response)[0]
        return unpacked_response

    @rpc_method
    def set_basik_modulation_setup_bits(self, bits: int) -> None:
        """Set the modulation setup bits."""
        value = struct.pack("<H", bits)
        self._interbus.set_register(self.BASIK_ADDRESS, 0xb7, value)

    # ADJUSTIK module interface, as described in Section 6.3 of the documentation.
    # The ADJUSTIK module controls the frame (e.g., multiple BASIK units).

    # 6.3.1 : ADJUSTIK module --- general settings.

    @rpc_method
    def get_adjustik_module_type(self) -> int:
        """Return ADJUSTIK module type. Should be 0x34."""
        response = self._interbus.get_register(self.ADJUSTIK_ADDRESS, 0x61)
        unpacked_response = struct.unpack("<B", response)[0]
        return unpacked_response
