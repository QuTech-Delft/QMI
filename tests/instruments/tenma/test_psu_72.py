""" Testcase of the Tenma series 72 power supply units."""
import unittest
from unittest.mock import call, patch

import qmi
from qmi.core.transport import QMI_UdpTransport
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
        expected_model = "72-2550"
        expected_serial = "1231345"
        expected_version = "2.0"
        self._transport_mock.read_until_timeout.return_value = "TENMA 72-2550 SN:1231345 V2.0".encode("ascii")
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

    def test_set_current(self):
        """Set current within allowed range."""
        # Arrange
        allowed_currents = [Tenma72_2550.MAX_CURRENT, 0]
        channels = [None, 2]
        expected_calls = [
            call.write(f"ISET:{allowed_currents[0]:.3f}".encode("ascii")),
            call.write(f"ISET{channels[1]}:{allowed_currents[1]:.3f}".encode("ascii"))
        ]
        # Act
        for e, current in enumerate(allowed_currents):
            self.psu.set_current(current, channels[e])

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_current_excepts(self):
        """See that values out-of-range cause an exception."""
        # Arrange
        disallowed_currents = [Tenma72_2550.MAX_CURRENT + 0.1, -0.1]
        # Act
        for current in disallowed_currents:
            with self.assertRaises(ValueError):
                self.psu.set_current(current)

        self._transport_mock.write.assert_not_called()

    def test_set_voltage(self):
        """Set voltage within allowed range."""
        # Arrange
        allowed_voltages = [Tenma72_2550.MAX_VOLTAGE, 0]
        channels = [None, 2]
        expected_calls = [
            call.write(f"VSET:{allowed_voltages[0]:.3f}".encode("ascii")),
            call.write(f"VSET{channels[1]}:{allowed_voltages[1]:.3f}".encode("ascii"))
        ]
        # Act
        for e, voltage in enumerate(allowed_voltages):
            self.psu.set_voltage(voltage, channels[e])

        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_voltage_excepts(self):
        """See that values out-of-range cause an exception."""
        # Arrange
        disallowed_voltages = [Tenma72_2550.MAX_VOLTAGE + 0.1, -0.1]
        # Act
        for voltage in disallowed_voltages:
            with self.assertRaises(ValueError):
                self.psu.set_voltage(voltage)

        self._transport_mock.write.assert_not_called()

    def test_enable_disable_output(self):
        """Test enabling and disabling output. At implemented class this should work."""
        # Arrange
        enable_cmd = "OUT:1"
        disable_cmd = "OUT:0"
        self._transport_mock.read.side_effect = [chr(0x40), chr(0x00)]
        expected_enable_calls = [
            call(enable_cmd.encode("ascii")),
            call(b"STATUS?")
        ]
        expected_disable_calls = [
            call(disable_cmd.encode("ascii")),
            call(b"STATUS?")
        ]
        # Act
        self.psu.enable_output(True)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_enable_calls)
        self._transport_mock.write.reset_mock()

        # Act
        self.psu.enable_output(False)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_disable_calls)


class TestTenma72_13350(unittest.TestCase):
    """ Testcase of the TestTenma72_13350 psu """

    def setUp(self):
        qmi.start("TestSiglentTenma72_13350")
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_13350 = qmi.make_instrument("Tenma72_13350", Tenma72_13350, "")
        self.psu.open()

    def tearDown(self):
        self.psu.close()
        qmi.stop()

    def test_get_idn(self):
        """ Test case for `get_idn()` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-13350"
        expected_serial = "1231345"
        expected_version = "2.0"
        self._transport_mock.read_until_timeout.return_value = "TENMA 72-13350 SN:1231345 V2.0".encode("ascii")
        expected_calls = [call.read_until_timeout(Tenma72_13350.BUFFER_SIZE, 0.2)]  # 0.2 = default timeout
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
        responses = [chr(0x01), chr(0x02), chr(0x04), chr(0x10), chr(0x20)]
        self._transport_mock.read.side_effect = responses
        expected_statuses = [
            {"ChannelMode": "C.V", "OutputEnabled": False, "V/C priority": "Voltage priority", "Beep": False,
             "Lock": False},
            {"ChannelMode": "C.C", "OutputEnabled": True, "V/C priority": "Voltage priority", "Beep": False,
             "Lock": False},
            {"ChannelMode": "C.C", "OutputEnabled": False, "V/C priority": "Current priority", "Beep": False,
             "Lock": False},
            {"ChannelMode": "C.C", "OutputEnabled": False, "V/C priority": "Voltage priority", "Beep": True,
             "Lock": False},
            {"ChannelMode": "C.C", "OutputEnabled": False, "V/C priority": "Voltage priority", "Beep": False,
             "Lock": True}
        ]
        # Act
        for expected in expected_statuses:
            status = self.psu.get_status()
            # Assert
            self.assertDictEqual(expected, status)
            self._transport_mock.read.assert_called_once_with(2, 2)
            self._transport_mock.reset_mock()

    def test_set_current(self):
        """Set current within allowed range."""
        # Arrange
        allowed_currents = [Tenma72_13350.MAX_CURRENT, 0]
        channels = [None, 2]
        expected_calls = [
            call.write(f"ISET:{allowed_currents[0]:.3f}".encode("ascii")),
            call.write(f"ISET{channels[1]}:{allowed_currents[1]:.3f}".encode("ascii"))
        ]
        # Act
        for e, current in enumerate(allowed_currents):
            self.psu.set_current(current, channels[e])

        # Assert
        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_current_excepts(self):
        """See that values out-of-range cause an exception."""
        # Arrange
        disallowed_currents = [Tenma72_13350.MAX_CURRENT + 0.1, -0.1]
        # Act
        for current in disallowed_currents:
            with self.assertRaises(ValueError):
                self.psu.set_current(current)

        self._transport_mock.write.assert_not_called()

    def test_set_voltage(self):
        """Set voltage within allowed range."""
        # Arrange
        allowed_voltages = [Tenma72_13350.MAX_VOLTAGE, 0]
        channels = [None, 2]
        expected_calls = [
            call.write(f"VSET:{allowed_voltages[0]:.3f}".encode("ascii")),
            call.write(f"VSET{channels[1]}:{allowed_voltages[1]:.3f}".encode("ascii"))
        ]
        # Act
        for e, voltage in enumerate(allowed_voltages):
            self.psu.set_voltage(voltage, channels[e])

        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_set_voltage_excepts(self):
        """See that values out-of-range cause an exception."""
        # Arrange
        disallowed_voltages = [Tenma72_13350.MAX_VOLTAGE + 0.1, -0.1]
        # Act
        for voltage in disallowed_voltages:
            with self.assertRaises(ValueError):
                self.psu.set_voltage(voltage)

        self._transport_mock.write.assert_not_called()

    def test_enable_disable_output(self):
        """Test enabling and disabling output. At implemented class this should work."""
        # Arrange
        enable_cmd = "OUT:1"
        disable_cmd = "OUT:0"
        self._transport_mock.read.side_effect = [chr(0x02), chr(0x00)]
        expected_enable_calls = [
            call(enable_cmd.encode("ascii")),
            call(b"STATUS?")
        ]
        expected_disable_calls = [
            call(disable_cmd.encode("ascii")),
            call(b"STATUS?")
        ]
        # Act
        self.psu.enable_output(True)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_enable_calls)
        self._transport_mock.write.reset_mock()

        # Act
        self.psu.enable_output(False)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_disable_calls)


if __name__ == '__main__':
    unittest.main()
