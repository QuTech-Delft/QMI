""" Instrument driver for the Raspberry Pi peripheral I/O.
"""

import enum
import typing

# Lazy import of the GPIO module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    import RPi.GPIO as GPIO
else:
    GPIO = None

from qmi.core.context import QMI_Context
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method


def _import_modules() -> None:
    """Import the Raspberry Pi GPIO module.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """
    global GPIO
    if GPIO is None:
        import RPi.GPIO as GPIO  # pylint: disable=W0621

# See:
#
# https://pypi.org/project/RPi.GPIO/
# https://www.raspberrypi-spy.co.uk/2012/06/simple-guide-to-the-rpi-gpio-header-and-pins

# GPIO pins (BOARD numbering):
#
#     3, 5, 7, 8, 10, 11, 12, 13, 15, 16, 18, 19, 21, 22, 23, 24, 26, 29, 31, 32, 33, 35, 36, 37, 38, 40]


class RaspberryPiGPIO(QMI_Instrument):
    """Instrument driver for the Raspberry Pi I/O, based on the 'RPi' module.

    NOTE: It is only sensible to instantiate this driver on a Raspberry Pi.
    Of course, from then on, it can be accessed via RPC.

    This is based on the package RPi.GPIO. We expose a subset of its functionality.
    """
    # Fault codes returned by get_operating_fault().
    class gpio_mode(enum.Enum):
        INPUT = 0
        OUTPUT = 1

    def __init__(self, context: QMI_Context, name: str) -> None:
        super().__init__(context, name)

        _import_modules()

    @rpc_method
    def open(self) -> None:
        self._check_is_closed()
        GPIO.setmode(GPIO.BOARD)
        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        GPIO.cleanup()
        super().close()

    @rpc_method
    def gpio_setup(self, pin_nr: int, mode: gpio_mode) -> None:
        """Setup a GPIO pin in given mode.

        Parameters:
            pin_nr: The pin number to setup.
            mode:   The mode the pin should be setup. Options: gpio_mode.INPUT, gpio_mode.OUTPUT.
        """
        self._check_is_open()
        mode = GPIO.IN if mode == RaspberryPiGPIO.gpio_mode.INPUT else GPIO.OUT
        GPIO.setup(pin_nr, mode)

    @rpc_method
    def gpio_input(self, pin_nr: int) -> bool:
        """Check if given pin is in high lor low state.

        Parameters:
            pin_nr: The pin number to check.

        Returns:
            value:  True if the pin state is GPIO.HIGH, False otherwise.
        """
        self._check_is_open()
        value = GPIO.input(pin_nr)
        value = (value == GPIO.HIGH)
        return value

    @rpc_method
    def gpio_output(self, pin_nr: int, value: bool) -> None:
        """Set given pin output to high or low.

        Parameters:
            pin_nr: The pin number to be set.
            value:  True to set pin to GPIO.HIGH or False to set pin to GPIO.LOW.
        """
        self._check_is_open()
        value = GPIO.HIGH if value else GPIO.LOW
        GPIO.output(pin_nr, value)
