import logging
import os
import unittest
from unittest.mock import MagicMock

import qmi
import qmi.utils.context_managers
from qmi.core.exceptions import QMI_InstrumentException, QMI_InvalidOperationException
from qmi.core.transport import QMI_Transport
from qmi.instruments.instru_tech.instrutech_agc302 import InstruTech_AGC302


class MyTestCase(unittest.TestCase):

    def setUp(self) -> None:
        config_file = os.path.join(os.path.dirname(__file__), 'qmi.conf')
        qmi.start('unit_test', config_file)

    def tearDown(self) -> None:
        qmi.stop()
        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_read_gauge(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   1.55E-12\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            pressure = instrument.read_gauge()

        # assert
        transport.write.assert_called_once_with(b'#  RD\r')
        self.assertAlmostEqual(pressure, 1.55E-12)

    def test_read_gauge_sensor_off(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   1.10E+03\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(QMI_InstrumentException):
                _ = instrument.read_gauge()

    def test_read_gauge_sensor_not_exists(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   9.90E+09\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(QMI_InstrumentException):
                _ = instrument.read_gauge()

    def test_pressure_unit_torr(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   TORR    \r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            unit = instrument.read_pressure_unit()

        # assert
        transport.write.assert_called_once_with(b'#  RU\r')
        self.assertEqual(unit, 'TORR')

    def test_set_pressure_unit_torr(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   PROGM_OK\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_pressure_unit('T')

        # assert
        transport.write.assert_called_once_with(b'#  SUT\r')

    def test_set_pressure_unsupported_unit(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   PROGM_OK\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_pressure_unit('A')

    def test_unopened_device(self):
        # Suppress logging.
        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'*   PROGM_OK\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act and assert
        with self.assertRaises(QMI_InvalidOperationException):
            instrument.read_gauge()

    def test_syntax_error(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'?   SYNTX_ER\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(QMI_InstrumentException):
                instrument.read_gauge()
        transport.write.assert_called_once_with(b'#  RD\r')

    def test_invalid_response(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.return_value = b'sdfwe\r'
        instrument: InstruTech_AGC302 = qmi.make_instrument('pressure_gauge', InstruTech_AGC302, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(QMI_InstrumentException):
                instrument.read_gauge()
        transport.write.assert_called_once_with(b'#  RD\r')


if __name__ == '__main__':
    unittest.main()
