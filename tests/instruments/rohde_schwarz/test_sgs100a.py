"""Unit-tests for Rohde&Schwarz SGS100a."""
import unittest
from unittest.mock import patch

from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_TcpTransport
from qmi.instruments.rohde_schwarz import RohdeSchwarz_Sgs100a

from tests.patcher import PatcherQmiContext as QMI_Context


class TestSGS100A(unittest.TestCase):

    def setUp(self):
        ctx = QMI_Context("TestSGS100AContext")
        # Add patches
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.rohde_schwarz.rs_base_signal_gen.ScpiProtocol', autospec=True)
        self._scpi_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.instr: RohdeSchwarz_Sgs100a = RohdeSchwarz_Sgs100a(ctx, "SGS100a", "")
        self.instr.open()

    def tearDown(self):
        self.instr.close()

    def test_start_calibration(self):
        """Test start calibration."""
        self.instr.start_calibration()

        self._scpi_mock.write.assert_called_once_with(":CAL:ALL?")

    def test_check_if_calibrating(self):
        """Test that ongoing calibration inhibits interactions with the instrument."""
        # Device doesn't respond during calibration
        self._transport_mock.read_until.side_effect = QMI_TimeoutException

        self.instr.start_calibration()

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

    def test_get_set_ref_frequency(self):
        """Test get/set external reference frequency."""
        # Test get.
        value = "10MHZ"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_external_reference_frequency()

        self._scpi_mock.ask.assert_called_once_with(":ROSC:EXT:FREQ?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("10MHZ", "100MHZ", "1000MHZ", "10MHz", "100mhz"):
            self.instr.set_external_reference_frequency(target_value)

            self._scpi_mock.write.assert_called_once_with(f":ROSC:EXT:FREQ {target_value.upper()}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_external_reference_frequency("10000MHZ")

    def test_get_set_ref_bandwidth(self):
        """Test get/set reference bandwidth."""
        # Test get.
        value = "NARR"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_external_reference_bandwidth()

        self._scpi_mock.ask.assert_called_once_with(":ROSC:EXT:SBAN?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("NARR", "WIDE"):
            self.instr.set_external_reference_bandwidth(target_value)

            self._scpi_mock.write.assert_called_once_with(f":ROSC:EXT:SBAN {target_value}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_external_reference_bandwidth("flat")

    def test_get_set_trigger_impedance(self):
        """Test get/set trigger impedance."""
        # Test get.
        value = "G50"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_trigger_impedance()

        self._scpi_mock.ask.assert_called_once_with(":PULM:TRIG:EXT:IMP?")
        self.assertEqual(result, value)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in ("G50", "G10K"):
            self.instr.set_trigger_impedance(target_value)

            self._scpi_mock.write.assert_called_once_with(f":PULM:TRIG:EXT:IMP {target_value}")
            self._scpi_mock.write.reset_mock()

        # Test invalid value.
        with self.assertRaises(ValueError):
            self.instr.set_trigger_impedance("G10M")

    def test_get_set_iq_correction_enable(self):
        """Test get/set IQ correction enable."""
        # Test get.
        value = "1"
        self._scpi_mock.ask.return_value = value

        result = self.instr.get_iq_correction_enabled()

        self._scpi_mock.ask.assert_called_once_with(":IQ:IMP:STAT?")
        self.assertEqual(result, True)

        # Test set.
        self._scpi_mock.ask.return_value = "0,\"No error\""
        for target_value in (True, False):
            self.instr.set_iq_correction_enabled(target_value)

            self._scpi_mock.write.assert_called_once_with(":IQ:IMP:STAT {}".format(
                1 if target_value else 0
            ))
            self._scpi_mock.write.reset_mock()


if __name__ == '__main__':
    unittest.main()
