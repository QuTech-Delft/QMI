""" Testcase of the Tenma series 72 power supply units."""
import logging
import unittest
from unittest.mock import call, patch

from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_UdpTransport
from qmi.instruments.tenma import Tenma72_2550, Tenma72_13350
from qmi.instruments.tenma.psu_72 import Tenma72_Base

from tests.patcher import PatcherQmiContext as QMI_Context


class TestTenma72_BaseInit(unittest.TestCase):
    """ Testcase of the Tenma72_Base class initialization"""

    def setUp(self):
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_init(self):
        """See that __init__ excepts when invalid type of transport is given."""
        # Arrange
        ok_transport = "serial:/dev/ttyS0"
        ok_transport_2 = "udp:123.45.67.8"
        nok_transport = "tcp:123.45.67.8:1234"  # TCP cannot be used
        # Act
        Tenma72_Base(
            QMI_Context("Test_tenma_base_init"), "tenma_base_ok", ok_transport
        )
        Tenma72_Base(
            QMI_Context("Test_tenma_base_init2"), "tenma_base_ok2", ok_transport_2
        )
        # Assert
        with self.assertRaises(QMI_InstrumentException):
            Tenma72_Base(
                QMI_Context("Test_tenma_base_init_nok"), "tenma_base_nok", nok_transport
            )


class TestTenma72_Base(unittest.TestCase):
    """ Testcase of the Tenma72_Base class """

    def setUp(self):
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_Base = Tenma72_Base(QMI_Context("TestSiglentTenma72_Base"), Tenma72_Base, "udp:123.45.67.8")
        self.psu.open()

    def tearDown(self):
        self.psu.close()

    def test_get_idn(self):
        """ Test case for `get_idn()` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-2345"
        expected_serial = "1231345"
        expected_version = "V2.0"
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

    def test_get_idn_no_reply_excepts(self):
        """ Test case for `get_idn()` function. """
        # arrange
        self._transport_mock.read_until_timeout.return_value = "".encode("ascii")
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            self.psu.get_idn()

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
        current = self.psu.get_current()  # No channel
        # Assert
        self.assertEqual(expected_current, current)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_1, "ascii"))
        self._transport_mock.write.reset_mock()
        # Act
        current = self.psu.get_current(ch_2)
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
        voltage = self.psu.get_voltage()  # No channel
        # Assert
        self.assertEqual(expected_voltage, voltage)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_1, "ascii"))
        self._transport_mock.write.reset_mock()
        # Act
        voltage = self.psu.get_voltage(ch_2)
        # Assert
        self.assertEqual(expected_voltage, voltage)
        self._transport_mock.write.assert_called_once_with(bytes(cmd_2, "ascii"))

    def test_enable_disable_output(self):
        """Test enabling and disabling output. At base class sending works but receiving excepts"""
        # Act
        with self.assertRaises(NotImplementedError):
            self.psu.enable_output(True)

        with self.assertRaises(NotImplementedError):
            self.psu.enable_output(False)


class TestTenma72_2550(unittest.TestCase):
    """ Testcase of the TestTenma72_2550 psu """

    def setUp(self):
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_2550 = Tenma72_2550(QMI_Context("TestSiglentTenma72_2550"), Tenma72_2550, "serial:COM0")
        self.psu.open()

    def tearDown(self):
        self.psu.close()

    def test_get_idn(self):
        """ Test case for `get_idn()` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-2550"
        expected_serial = "1231345"
        expected_version = "V2.0"
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
        enable_cmd = "OUT1"
        disable_cmd = "OUT0"
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

    def test_enable_disable_output_excepts(self):
        """Test enabling or disabling output raises an exception when the check value is not the same as input."""
        # Suppress logging.
        logging.getLogger("qmi.instruments.tenma.psu_72").setLevel(logging.CRITICAL)

        # Arrange
        enable_cmd = "OUT1"
        disable_cmd = "OUT0"
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
        with self.assertRaises(QMI_InstrumentException):
            self.psu.enable_output(False)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_disable_calls)
        self._transport_mock.write.reset_mock()

        # Act
        with self.assertRaises(QMI_InstrumentException):
            self.psu.enable_output(True)

        # Assert
        self._transport_mock.write.assert_has_calls(expected_enable_calls)

        logging.getLogger("qmi.instruments.tenma.psu_72").setLevel(logging.NOTSET)


class TestTenma72_13350(unittest.TestCase):
    """ Testcase of the TestTenma72_13350 psu """

    def setUp(self):
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_13350 = Tenma72_13350(QMI_Context("TestSiglentTenma72_13350"), Tenma72_13350, "udp:not_parsed")
        self.psu.open()

    def tearDown(self):
        self.psu.close()

    def test_get_idn(self):
        """ Test case for `get_idn()` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-13350"
        expected_serial = "1231345"
        expected_version = "V2.0"
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
        responses = [b"\x01\n", b"\x02\n", b"\x04\n", b"\x10\n", b" \n"]  # last is chr(0x20)
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
            call.write(f"ISET:{allowed_currents[0]:.3f}\n".encode("ascii")),
            call.write(f"ISET{channels[1]}:{allowed_currents[1]:.3f}\n".encode("ascii"))
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
            call.write(f"VSET:{allowed_voltages[0]:.3f}\n".encode("ascii")),
            call.write(f"VSET{channels[1]}:{allowed_voltages[1]:.3f}\n".encode("ascii"))
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
        enable_cmd = "OUT:1\n"
        disable_cmd = "OUT:0\n"
        self._transport_mock.read.side_effect = [b"\x02\n", b"\x00\n"]
        expected_enable_calls = [
            call(enable_cmd.encode("ascii")),
            call(b"STATUS?\n")
        ]
        expected_disable_calls = [
            call(disable_cmd.encode("ascii")),
            call(b"STATUS?\n")
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

    def test_get_dhcp(self):
        """Get the DHCP state."""
        # Arrange
        cmd = ":SYST:DHCP?\n"
        expected_dhcp = 1
        self._transport_mock.read_until_timeout.return_value = f"{expected_dhcp}".encode("ascii")
        # Act
        state = self.psu.get_dhcp()
        # Assert
        self.assertEqual(expected_dhcp, state)
        self._transport_mock.write.assert_called_once_with(bytes(cmd, "ascii"))

    def test_set_dhcp(self):
        """Set DHCP on/off."""
        # Arrange
        dhcp = 0
        expected_calls = [
            call.write(f":SYST:DHCP {dhcp}\n".encode("ascii")),
        ]
        # Act
        self.psu.set_dhcp(dhcp)

        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_get_ip_address(self):
        """Get the IP address."""
        # Arrange
        cmd = ":SYST:IPAD?\n"
        expected_ipad = "192.168.1.90"
        self._transport_mock.read_until_timeout.return_value = f"{expected_ipad}".encode("ascii")
        # Act
        ipad = self.psu.get_ip_address()
        # Assert
        self.assertEqual(expected_ipad, ipad)
        self._transport_mock.write.assert_called_once_with(bytes(cmd, "ascii"))

    def test_set_ip_address(self):
        """Set an IP address."""
        # Arrange
        ip_address = "192.168.1.90"
        expected_calls = [
            call.write(f":SYST:IPAD {ip_address}\n".encode("ascii")),
        ]
        # Act
        self.psu.set_ip_address(ip_address)

        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_get_subnet_mask(self):
        """Get the subnet mask."""
        # Arrange
        cmd = ":SYST:SMASK?\n"
        expected_ipad = "255.255.255.0"
        self._transport_mock.read_until_timeout.return_value = f"{expected_ipad}".encode("ascii")
        # Act
        ipad = self.psu.get_subnet_mask()
        # Assert
        self.assertEqual(expected_ipad, ipad)
        self._transport_mock.write.assert_called_once_with(bytes(cmd, "ascii"))

    def test_set_subnet_mask(self):
        """Set a subnet mask."""
        # Arrange
        subnet_mask = "255.255.255.0"
        expected_calls = [
            call.write(f":SYST:SMASK {subnet_mask}\n".encode("ascii")),
        ]
        # Act
        self.psu.set_subnet_mask(subnet_mask)

        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_get_gateway_address(self):
        """Get the gateway address."""
        # Arrange
        cmd = ":SYST:GATE?\n"
        expected_gateway = "192.168.0.1"
        self._transport_mock.read_until_timeout.return_value = f"{expected_gateway}".encode("ascii")
        # Act
        gateway = self.psu.get_gateway_address()
        # Assert
        self.assertEqual(expected_gateway, gateway)
        self._transport_mock.write.assert_called_once_with(bytes(cmd, "ascii"))

    def test_set_gateway_address(self):
        """Set a gateway address."""
        # Arrange
        gateway_address = "192.168.0.1"
        expected_calls = [
            call.write(f":SYST:GATE {gateway_address}\n".encode("ascii")),
        ]
        # Act
        self.psu.set_gateway_address(gateway_address)

        self._transport_mock.write.assert_has_calls(expected_calls)

    def test_get_ip_port(self):
        """Get the IP port."""
        # Arrange
        cmd = ":SYST:PORT?\n"
        expected_port = 5990
        self._transport_mock.read_until_timeout.return_value = f"{expected_port}".encode("ascii")
        # Act
        port = self.psu.get_ip_port()
        # Assert
        self.assertEqual(expected_port, port)
        self._transport_mock.write.assert_called_once_with(bytes(cmd, "ascii"))

    def test_set_ip_port(self):
        """Set an IP port."""
        # Arrange
        port = 5990
        expected_calls = [
            call.write(f":SYST:PORT {port}\n".encode("ascii")),
        ]
        # Act
        self.psu.set_ip_port(port)

        self._transport_mock.write.assert_has_calls(expected_calls)


if __name__ == '__main__':
    unittest.main()
