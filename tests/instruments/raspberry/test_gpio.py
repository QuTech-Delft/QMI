import unittest
from unittest.mock import patch, Mock

from qmi.core.context import QMI_Context
from qmi.instruments.raspberry import RaspberryPi_Gpio


class RasperryPiGpioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.patcher = patch("qmi.instruments.raspberry.gpio.GPIO")
        self.board = [3, 5, 7, 8, 10, 11, 12, 13, 15, 16, 18, 19, 21, 22, 23, 24, 26, 29, 31, 32, 33, 35, 36]
        self.high = 1
        self.low = 0
        self.patcher.start()
        self.patcher.target.GPIO.BOARD = self.board
        self.patcher.target.GPIO.HIGH = self.high
        self.patcher.target.GPIO.LOW = self.low
        self.gpio = RaspberryPi_Gpio(QMI_Context("rpi_test"), "rpi_gpio")

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_open_close(self):
        """Test open and close functions."""
        self.patcher.target.GPIO.setmode = Mock()
        # with patch("qmi.instruments.raspberry.gpio.GPIO.setmode") as sm_patch:
        self.gpio.open()

        self.patcher.target.GPIO.setmode.assert_called_once_with(self.board)

        self.patcher.target.GPIO.cleanup = Mock()
        self.gpio.close()

        self.patcher.target.GPIO.cleanup.assert_called_once_with()

    def test_gpio_setup(self):
        """Test gpio_setup function with in oder aus."""
        # case IN
        self.gpio._is_open = True
        pin_nr = 15
        gpio_mode = self.gpio.gpio_mode.INPUT
        with patch("qmi.instruments.raspberry.gpio.GPIO.setup") as sp_patch:
            self.gpio.gpio_setup(pin_nr, gpio_mode)

        sp_patch.assert_called_once_with(pin_nr, self.patcher.target.GPIO.IN)

        # case OUT
        gpio_mode = self.gpio.gpio_mode.OUTPUT
        with patch("qmi.instruments.raspberry.gpio.GPIO.setup") as sp_patch:
            self.gpio.gpio_setup(pin_nr, gpio_mode)

        sp_patch.assert_called_once_with(pin_nr, self.patcher.target.GPIO.OUT)

    def test_gpio_input(self):
        """Test gpio_input function."""
        self.gpio._is_open = True
        pin_nr = 3
        self.patcher.target.GPIO.HIGH = self.high
        self.patcher.target.GPIO.input = Mock(return_value=1)

        success = self.gpio.gpio_input(pin_nr)

        self.assertTrue(success)
        self.patcher.target.GPIO.input.assert_called_once_with(pin_nr)

    def test_gpio_output(self):
        """Test gpio_output function."""
        self.gpio._is_open = True
        pin_nr = 34
        self.patcher.target.GPIO.HIGH = self.high
        self.patcher.target.GPIO.LOW = self.low
        self.patcher.target.GPIO.output = Mock()

        # case value  = True
        value = True
        self.gpio.gpio_output(pin_nr, value)

        self.patcher.target.GPIO.output.assert_called_once_with(pin_nr, self.high)

        self.patcher.target.GPIO.output.reset_mock()
        # case False
        value = False
        self.gpio.gpio_output(pin_nr, value = False)

        self.patcher.target.GPIO.output.assert_called_once_with(pin_nr, self.low)


if __name__ == '__main__':
    unittest.main()
