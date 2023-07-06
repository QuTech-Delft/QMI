import logging
import unittest
from unittest.mock import MagicMock

import qmi
import qmi.utils.context_managers
from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.core.transport import QMI_Transport
from qmi.instruments.instru_tech.instrutech_agc302 import InstruTech_AGC302


class MyTestCase(unittest.TestCase):

    def setUp(self) -> None:
        # Suppress logging.
        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)
        self.transport = MagicMock(spec=QMI_Transport)
        qmi.start("AGC302_unit-test")
        self.instrument: InstruTech_AGC302 = qmi.make_instrument("pressure_gauge", InstruTech_AGC302, self.transport)

    def tearDown(self) -> None:
        qmi.stop()
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_read_gauge(self):
        # arrange
        self.transport.read_until.return_value = b'*   1.55E-12\r'

        # act
        with qmi.utils.context_managers.open_close(self.instrument):
            pressure = self.instrument.read_gauge()

        # assert
        self.transport.write.assert_called_once_with(b'#  RD\r')
        self.assertAlmostEqual(pressure, 1.55E-12)

    def test_read_gauge_sensor_off(self):
        # arrange
        self.transport.read_until.return_value = b'*   1.10E+03\r'

        # act and assert
        with qmi.utils.context_managers.open_close(self.instrument):
            with self.assertRaises(QMI_InstrumentException):
                self.instrument.read_gauge()

    def test_read_gauge_sensor_not_exists(self):
        # arrange
        self.transport.read_until.return_value = b'*   9.90E+09\r'

        # act and assert
        with qmi.utils.context_managers.open_close(self.instrument):
            with self.assertRaises(QMI_InstrumentException):
                self.instrument.read_gauge()

    def test_pressure_unit_torr(self):
        # arrange
        self.transport.read_until.return_value = b'*   TORR    \r'

        # act
        with qmi.utils.context_managers.open_close(self.instrument):
            unit = self.instrument.read_pressure_unit()

        # assert
        self.transport.write.assert_called_once_with(b'#  RU\r')
        self.assertEqual(unit, 'TORR')

    def test_set_pressure_unit_torr(self):
        # arrange
        self.transport.read_until.return_value = b'*   PROGM_OK\r'

        # act
        with qmi.utils.context_managers.open_close(self.instrument):
            self.instrument.set_pressure_unit('T')

        # assert
        self.transport.write.assert_called_once_with(b'#  SUT\r')

    def test_set_pressure_unsupported_unit(self):
        # arrange
        self.transport.read_until.return_value = b'*   PROGM_OK\r'

        # act and assert
        with qmi.utils.context_managers.open_close(self.instrument):
            with self.assertRaises(ValueError):
                self.instrument.set_pressure_unit('A')

    def test_unopened_device(self):
        # arrange
        self.transport.read_until.return_value = b'*   PROGM_OK\r'

        # act and assert
        with self.assertRaises(QMI_InvalidOperationException):
            self.instrument.read_gauge()

    def test_syntax_error(self):
        # arrange
        self.transport.read_until.return_value = b'?   SYNTX_ER\r'

        # act and assert
        with qmi.utils.context_managers.open_close(self.instrument):
            with self.assertRaises(QMI_InstrumentException):
                self.instrument.read_gauge()

        self.transport.write.assert_called_once_with(b'#  RD\r')

    def test_invalid_response(self):
        # arrange
        self.transport.read_until.return_value = b'sdfwe\r'

        # act and assert
        with qmi.utils.context_managers.open_close(self.instrument):
            with self.assertRaises(QMI_InstrumentException):
                self.instrument.read_gauge()

        self.transport.write.assert_called_once_with(b'#  RD\r')


if __name__ == '__main__':
    unittest.main()
