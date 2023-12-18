""" Testcase of the Tenma series 72 power supply units."""
import unittest
from unittest.mock import call, patch

import qmi
from qmi.core.transport import QMI_UdpTransport
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.instruments.tenma import Tenma72_2550, Tenma72_13350
from qmi.instruments.tenma.psu_72 import Tenma72_Base


class TestTenma72_Base(unittest.TestCase):
    """ Testcase of the Tenma72_Base class """

    def setUp(self):
        qmi.start("TestSiglentTenma72_Base")
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_Base = qmi.make_instrument("Tenma72_Base", Tenma72_Base, "patched")
        self.psu.open()

    def tearDown(self):
        self.psu.close()
        qmi.stop()

    def test_get_idn(self):
        """ Test case for `get_idn()` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-2345"
        expected_serial = "1231345"
        expected_version = "2.0"
        self._transport_mock.read_until_timeout.return_value = "TENMA 72-2345 SN:1231345 V2.0".encode("ascii")
        expected_calls = [call.read_until_timeout(Tenma72_Base.BUFFER_SIZE, 0.2)]  # 0.2 = default timeout
        # act
        idn = self.psu.get_idn()
        # assert
        self.assertEqual(expected_calls, self._transport_mock.read_until_timeout.call_args_list)
        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertEqual(expected_serial, idn.serial)
        self.assertEqual(expected_version, idn.version)

    def test_get_status_errs(self):
        """Test case for not implemented get_status() function."""
        with self.assertRaises(NotImplementedError):
            self.psu.get_status()

    def test_read_current(self):
        """Test base read_current(...) method with a channel number and without."""
        # Arrange
        cmd_1 = "ISET?"  # No channel
        ch_2 = 2
        cmd_2 = f"ISET{ch_2}?"
        expected_current = 0.123
        self._transport_mock.read_until_timeout.return_value = f"{expected_current:.5f}".encode("ascii")
        # Act
        current = self.psu.read_current()  # No channel
        # Assert
        self.assertEqual(expected_current, current)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_1, "ascii"))
        self._transport_mock.write.reset_mock()
        # Act
        current = self.psu.read_current(ch_2)
        # Assert
        self.assertEqual(expected_current, current)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_2, "ascii"))

    def test_read_voltage(self):
        """Test base read_voltage(...) method with a channel number and without."""
        # Arrange
        cmd_1 = "VSET?"  # No channel
        ch_2 = 2
        cmd_2 = f"VSET{ch_2}?"
        expected_voltage = 1.230
        self._transport_mock.read_until_timeout.return_value = f"{expected_voltage:.5f}".encode("ascii")
        # Act
        voltage = self.psu.read_voltage()  # No channel
        # Assert
        self.assertEqual(expected_voltage, voltage)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_1, "ascii"))
        self._transport_mock.write.reset_mock()
        # Act
        voltage = self.psu.read_voltage(ch_2)
        # Assert
        self.assertEqual(expected_voltage, voltage)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_2, "ascii"))

    def test_set_commands_fail_with_default_base_values(self):
        """Check the default attributes are as expected and fail"""
        max_voltage = Tenma72_Base.MAX_VOLTAGE
        max_current = Tenma72_Base.MAX_CURRENT

        # Set commands should fail with the base class default values
        with self.assertRaises(ValueError):
            self.psu.set_voltage(max_voltage)

        # Set commands should fail with the base class default values
        with self.assertRaises(ValueError):
            self.psu.set_current(max_current)

    def test_enable_disable_output(self):
        """Test enabling and disabling output. At base class sending works but receiving excepts"""
        # Arrange
        enable_cmd = "OUT:1"
        disable_cmd = "OUT:0"
        # Act
        with self.assertRaises(NotImplementedError):
            self.psu.enable_output(True)

        # Assert
        self._transport_mock.write.assert_called_once_with(bytes(enable_cmd, "ascii"))
        self._transport_mock.write.reset_mock()

        # Act
        with self.assertRaises(NotImplementedError):
            self.psu.enable_output(False)

        # Assert
        self._transport_mock.write.assert_called_once_with(bytes(disable_cmd, "ascii"))


class TestTenma72_2550(unittest.TestCase):
    """ Testcase of the TestTenma72_2550 psu """

    def setUp(self):
        qmi.start("TestSiglentTenma72_2550")
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_2550 = qmi.make_instrument("Tenma72_2550", Tenma72_2550, "")
        self.psu.open()

    def tearDown(self):
        self.psu.close()
        qmi.stop()

    def test_get_idn(self):
        """ Test case for `get_idn()` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-2535"
        expected_serial = "1231345"
        expected_version = "2.0"
        self._transport_mock.read_until_timeout.return_value = "TENMA 72-2535 SN:1231345 V2.0".encode("ascii")
        expected_calls = [call.read_until_timeout(Tenma72_2550.BUFFER_SIZE, 0.2)]  # 0.2 = default timeout
        # act
        idn = self.psu.get_idn()
        # assert
        self.assertEqual(expected_calls, self._transport_mock.read_until_timeout.call_args_list)
        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertEqual(expected_serial, idn.serial)
        self.assertEqual(expected_version, idn.version)

    def test_get_status(self):
        """Test case for get_status() function."""
        # arrange
        responses = [chr(0x01), chr(0x02), chr(0x03), chr(0x07), chr(0x0B), chr(0x0C), chr(0x40)]
        self._transport_mock.read.side_effect = responses
        expected_statuses = [
            {"Ch1Mode": "C.V", "Ch2Mode": "C.C", "Tracking": "Independent", "OutputEnabled": False},
            {"Ch1Mode": "C.C", "Ch2Mode": "C.V", "Tracking": "Independent", "OutputEnabled": False},
            {"Ch1Mode": "C.V", "Ch2Mode": "C.V", "Tracking": "Independent", "OutputEnabled": False},
            {"Ch1Mode": "C.V", "Ch2Mode": "C.V", "Tracking": "Tracking Series", "OutputEnabled": False},
            {"Ch1Mode": "C.V", "Ch2Mode": "C.V", "Tracking": "Tracking Parallel", "OutputEnabled": False},
            {"Ch1Mode": "C.C", "Ch2Mode": "C.C", "Tracking": "Unknown", "OutputEnabled": False},
            {"Ch1Mode": "C.C", "Ch2Mode": "C.C", "Tracking": "Independent", "OutputEnabled": True}
        ]
        # Act
        for expected in expected_statuses:
            status = self.psu.get_status()
            # Assert
            self.assertDictEqual(expected, status)
            self._transport_mock.read.assert_called_once_with(1, 1)
            self._transport_mock.reset_mock()




if __name__ == '__main__':
    unittest.main()
