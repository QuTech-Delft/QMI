import os
import unittest
from unittest.mock import MagicMock

import qmi
import qmi.utils.context_managers
from qmi.core.transport import QMI_Transport
from qmi.instruments.ozoptics.epc_driver import OzOptics_EpcDriver


class TestEpcDriver(unittest.TestCase):

    def setUp(self) -> None:
        config_file = os.path.join(os.path.dirname(__file__), 'qmi.conf')
        qmi.start('unit_test', config_file)

    def tearDown(self) -> None:
        qmi.stop()

    def test_get_frequency(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Frequency(Hz): CH1 007  CH2 017  CH3 037  CH4 071\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            freq_ch1, freq_ch2, freq_ch3, freq_ch4 = instrument.get_frequencies()

        # assert
        transport.write.assert_called_once_with(b'F?\r\n')
        self.assertEqual(freq_ch1, 7)
        self.assertEqual(freq_ch2, 17)
        self.assertEqual(freq_ch3, 37)
        self.assertEqual(freq_ch4, 71)

    def test_set_frequency(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set CH2 AC Frequency at: 47Hz\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_frequency(1, 50)

        # assert
        transport.write.assert_called_once_with(b'F1,50\r\n')

    def test_set_frequency_wrong_channel(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_frequency(0, 50)

        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_frequency(5, 50)

    def test_set_frequency_wrong_frequency(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_frequency(1, 101)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_frequency(1, -1)

    def test_set_operating_mode_ac(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set To AC Mode\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_operating_mode_ac()

        # assert
        transport.write.assert_called_once_with(b'MAC\r\n')

    def test_set_operating_mode_dc(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set To DC Mode\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_operating_mode_dc()

        # assert
        transport.write.assert_called_once_with(b'MDC\r\n')

    def test_get_operating_mode_ac(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Work Mode: AC(Sine)\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            operating_mode_ac = instrument.get_operating_mode()

        # assert
        transport.write.assert_called_once_with(b'M?\r\n')
        self.assertEqual(operating_mode_ac, 'AC')

    def test_get_operating_mode_dc(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Work Mode: DC\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            operating_mode_ac = instrument.get_operating_mode()

        # assert
        transport.write.assert_called_once_with(b'M?\r\n')
        self.assertEqual(operating_mode_ac, 'DC')

    def test_set_voltage(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set CH3 DC Voltage at: 2500mV\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_voltage(3, 2500)

        # assert
        transport.write.assert_called_once_with(b'V3,2500\r\n')

    def test_set_voltage_wrong_channel(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_voltage(0, 2500)

        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_voltage(5, 2500)

    def test_set_voltage_wrong_voltage(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_voltage(3, -5001)

        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_voltage(3, 5005)

    def test_set_high(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set CH4 DC Voltage at: 5000mV\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_high(4)

        # assert
        transport.write.assert_called_once_with(b'VH4\r\n')

    def test_set_low(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set CH4 DC Voltage at: -5000mV\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_low(4)

        # assert
        transport.write.assert_called_once_with(b'VL4\r\n')

    def test_set_zero(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set CH4 DC Voltage at: 0mV\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_zero(4)

        # assert
        transport.write.assert_called_once_with(b'VZ4\r\n')

    def test_invalid_channel_voltage_command(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act and assert
        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_high(5)

        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_low(0)

        with qmi.utils.context_managers.open_close(instrument):
            with self.assertRaises(ValueError):
                instrument.set_zero(0)

    def test_get_voltages(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Voltage(mV): CH1 +2200 CH2 +5000 CH3 -1000 CH4 -4000\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            voltage_ch1, voltage_ch2, voltage_ch3, voltage_ch4 = instrument.get_voltages()

        # assert
        transport.write.assert_called_once_with(b'V?\r\n')
        self.assertEqual(voltage_ch1, 2200)
        self.assertEqual(voltage_ch2, 5000)
        self.assertEqual(voltage_ch3, -1000)
        self.assertEqual(voltage_ch4, -4000)

    def test_get_waveform_type_sine(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'AC Waveform: Sine\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            waveform_type = instrument.get_waveform_type()

        # assert
        transport.write.assert_called_once_with(b'WF?\r\n')
        self.assertEqual(waveform_type, 'Sine')

    def test_get_waveform_type_triangle(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'AC Waveform: Triangle\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            waveform_type = instrument.get_waveform_type()

        # assert
        transport.write.assert_called_once_with(b'WF?\r\n')
        self.assertEqual(waveform_type, 'Triangle')

    def test_save_to_flash(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Write Setting to Flash memory\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.save_to_flash()

        # assert
        transport.write.assert_called_once_with(b'SAVE\r\n')

    def test_set_waveform_type_sine(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set AC Waveform at: Sine\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_waveform_type_sine()

        # assert
        transport.write.assert_called_once_with(b'WF1\r\n')

    def test_set_waveform_type_triangle(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set AC Waveform at: Triangle\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.set_waveform_type_triangle()

        # assert
        transport.write.assert_called_once_with(b'WF2\r\n')

    def test_enable_dc_in_ac_mode(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Enable DC Voltage Output at AC Mode\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.enable_dc_in_ac_mode()

        # assert
        transport.write.assert_called_once_with(b'ENVF1\r\n')

    def test_disable_dc_in_ac_mode(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Disable DC Voltage Output at AC Mode\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.disable_dc_in_ac_mode()

        # assert
        transport.write.assert_called_once_with(b'ENVF0\r\n')

    def test_toggle_channel_ac_dc(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Set CH2 output to: Volt (if possible)\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            instrument.toggle_channel_ac_dc(2)

        # assert
        transport.write.assert_called_once_with(b'VF2\r\n')

    def test_get_ac_dc_status(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Hz<->Volt at AC Mode is enabled: CH1-V,CH2-V,CH3-F,CH4-F\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            ch1_mode, ch2_mode, ch3_mode, ch4_mode = instrument.get_ac_dc_channel_status()

        # assert
        transport.write.assert_called_once_with(b'VF?\r\n')

        self.assertEqual(ch1_mode, 'V')
        self.assertEqual(ch2_mode, 'V')
        self.assertEqual(ch3_mode, 'F')
        self.assertEqual(ch4_mode, 'F')

    def test_is_in_dc_in_ac_mode_enabled(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Hz<->Volt at AC Mode is enabled: CH1-V,CH2-V,CH3-F,CH4-F\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            is_dc_in_ac_mode = instrument.is_in_dc_in_ac_mode()

        # assert
        transport.write.assert_called_once_with(b'VF?\r\n')

        self.assertTrue(is_dc_in_ac_mode)

    def test_is_in_dc_in_ac_mode_disabled(self):
        # arrange
        transport = MagicMock(spec=QMI_Transport)
        transport.read_until.side_effect = [b'Hz<->Volt at AC Mode is disabled: CH1-V,CH2-V,CH3-F,CH4-F\r\n', b'Done\r\n']
        instrument: OzOptics_EpcDriver = qmi.make_instrument('epc_driver', OzOptics_EpcDriver, transport)

        # act
        with qmi.utils.context_managers.open_close(instrument):
            is_dc_in_ac_mode = instrument.is_in_dc_in_ac_mode()

        # assert
        transport.write.assert_called_once_with(b'VF?\r\n')

        self.assertFalse(is_dc_in_ac_mode)
