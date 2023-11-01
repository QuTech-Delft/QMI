"""Unit-tests for WL Photonics WLTF-N driver class."""
import logging
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.transport import QMI_SerialTransport
from qmi.core.usbtmc import Instrument

from qmi.instruments.wl_photonics import WlPhotonics_WltfN


class TestWlPhotonicsWltfNOpenCloseSerial(unittest.TestCase):

    def setUp(self):
        logging.getLogger("qmi.instruments.wl_photonics.wltf_n").setLevel(logging.CRITICAL)
        qmi.start("TestWlPhotonicsWltfNClassContext")
        # Add patches
        patcher = patch('qmi.instruments.wl_photonics.wltf_n.create_transport', spec=QMI_SerialTransport)
        self._transport_mock = patcher.start()
        self.addCleanup(patcher.stop)
        # Make DUT
        self.instr: WlPhotonics_WltfN = WlPhotonics_WltfN(qmi.context(), "WlPhotonics_wltf_n", "")

    def tearDown(self):
        qmi.stop()
        logging.getLogger("qmi.instruments.wl_photonics.wltf_n").setLevel(logging.NOTSET)

    def test_open_close(self):
        """open() command not just opens the instrument, but immediately also checks the wavelength/steps
        range and the power unit to set the power level range. Test the whole shebang.

        close() command then just closes the connection to the instrument and the transport.
        """
        # Initially, the wavelength and power range should be bare data classes
        expected_initial_out = "<class 'qmi.instruments.wl_photonics.wltf_n._{rng}Range'>"
        self.assertEqual(expected_initial_out.format(rng="Wavelength"), str(self.instr._wavelength_range))
        self.assertEqual(expected_initial_out.format(rng="Steps"), str(self.instr._steps_range))
        # Arrange
        expected_wl_min = 1021.509
        expected_wl_max = 1072.505
        step_min = 556
        step_max = 4654
        expected_start_step = (step_max - step_min) // 2

        self.instr._transport.read_until.side_effect = [
            # output of dev?
            b'WL200: SN(201307374), MD(2018-11-23)\r\n' +
            b'WL Range: 1021.509~1072.505nm(Step: 4654~556)\r\n' +
            b'OK\r\n',
            # output of s?
            f"Step: {expected_start_step}\r\n, ERR: -1, Status: 0x340880".encode() +
            b'OK\r\n',
        ]
        expected_calls = [
            call().open(),
            call().write(b"dev?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT),
            call().write(b"s?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT)
        ]
        # Act
        self.instr.open()
        # Assert
        self._transport_mock.assert_called_once()
        self.assertEqual(expected_wl_min, self.instr._wavelength_range.min)
        self.assertEqual(expected_wl_max, self.instr._wavelength_range.max)
        self.assertEqual(step_min, self.instr._steps_range.min)
        self.assertEqual(step_max, self.instr._steps_range.max)
        self.assertEqual(expected_start_step, self.instr._motor_position)
        self._transport_mock.assert_has_calls(expected_calls, any_order=True)
        # Test close
        self.instr.close()
        self._transport_mock.assert_called_once()


class TestWlPhotonicsWltfNOpenClosePyUSB(unittest.TestCase):

    def setUp(self):
        logging.getLogger("qmi.instruments.wl_photonics.wltf_n").setLevel(logging.CRITICAL)
        qmi.start("TestWlPhotonicsWltfNClassContext")
        # Add patches - now we should patch a bit deeper to test the creation of USBTMC transport without SN.
        patcher = patch('qmi.core.usbtmc.Instrument', autospec=Instrument)
        self._transport_mock = patcher.start()
        self.addCleanup(patcher.stop)
        # Make DUT
        self.vendor_id = 0x10C4
        self.product_id = 0xEA60
        serial = ""  # No serial number known. Does it still work?
        transport_string = f"usbtmc:vendorid={self.vendor_id}:productid={self.product_id}:serialnr={serial}"
        with patch("sys.platform", "linux1"):
            self.instr: WlPhotonics_WltfN = WlPhotonics_WltfN(qmi.context(), "WlPhotonics_wltf_n", transport_string)

    def tearDown(self):
        qmi.stop()
        logging.getLogger("qmi.instruments.wl_photonics.wltf_n").setLevel(logging.NOTSET)

    def test_open_close(self):
        """open() command not just opens the instrument, but immediately also checks the wavelength/steps
        range and the power unit to set the power level range. Test the whole shebang.

        close() command then just closes the connection to the instrument and the transport.
        """
        # Initially, the wavelength and power range should be bare data classes
        expected_initial_out = "<class 'qmi.instruments.wl_photonics.wltf_n._{rng}Range'>"
        self.assertEqual(expected_initial_out.format(rng="Wavelength"), str(self.instr._wavelength_range))
        self.assertEqual(expected_initial_out.format(rng="Steps"), str(self.instr._steps_range))
        # Arrange
        expected_wl_min = 1021.509
        expected_wl_max = 1072.505
        step_min = 556
        step_max = 4654
        expected_start_step = (step_max - step_min) // 2

        self.instr._transport._device = self._transport_mock
        self._transport_mock().read_raw.side_effect = [
            # output of dev?
            b'WL200: SN(201307374), MD(2018-11-23)\r\n' +
            b'WL Range: 1021.509~1072.505nm(Step: 4654~556)\r\n' +
            b'OK\r\n',
            # output of s?
            f"Step: {expected_start_step}\r\n, ERR: -1, Status: 0x340880".encode() +
            b'OK\r\n',
        ]
        expected_calls = [
            call(self.vendor_id, self.product_id, ''),  # QMI_PyUsbTransport __init__()
            call().open(),  # QMI_PyUsbTransport.open()
            call().write_raw(b"dev?\r\n"),  # dev? call in open()
            call().write_raw(b"s?\r\n")  # s? call in open()
        ]
        # Act
        self.instr.open()
        # Assert
        self.assertEqual(2, self._transport_mock.call_count)  # self._transport_mock()... is one call, __init__() 2nd
        self.assertEqual(expected_wl_min, self.instr._wavelength_range.min)
        self.assertEqual(expected_wl_max, self.instr._wavelength_range.max)
        self.assertEqual(step_min, self.instr._steps_range.min)
        self.assertEqual(step_max, self.instr._steps_range.max)
        self.assertEqual(expected_start_step, self.instr._motor_position)
        self._transport_mock.assert_has_calls(expected_calls, any_order=True)
        # Test close
        self.instr.close()
        self.assertEqual(2, self._transport_mock.call_count)


class TestWlPhotonicsWltfNClassMethods(unittest.TestCase):

    def setUp(self):
        # Make as standard to open in wavelength and dBm mode.
        self.wl_min = 1021.509
        self.wl_max = 1072.505
        self.step_min = 556
        self.step_max = 4654
        expected_start_step = (self.step_max - self.step_min) // 2

        logging.getLogger("qmi.instruments.wl_photonics.wltf_n").setLevel(logging.CRITICAL)
        qmi.start("TestWlPhotonicsWltfNClassContext")
        # Add patches
        patcher = patch('qmi.instruments.wl_photonics.wltf_n.create_transport', spec=QMI_SerialTransport)
        self._transport_mock = patcher.start()
        self.addCleanup(patcher.stop)
        self._transport_mock.write = Mock()
        # Make DUT
        self.instr: WlPhotonics_WltfN = WlPhotonics_WltfN(qmi.context(), "RSB100a", "")
        self.instr._transport.read_until.side_effect = [
            # output of dev?
            b'WL200: SN(201307374), MD(2018-11-23)\r\n' +
            b'WL Range: 1021.509~1072.505nm(Step: 4654~556)\r\n' +
            b'OK\r\n',
            # output of s?
            f"Step: {expected_start_step}\r\n, ERR: -1, Status: 0x340880".encode() +
            b'OK\r\n',
        ]
        self.instr.open()
        self._transport_mock.reset_mock()

    def tearDown(self):
        self.instr.close()
        qmi.stop()
        logging.getLogger("qmi.instruments.wl_photonics.wltf_n").setLevel(logging.NOTSET)

    def test_wrong_int_value(self):
        """Test a call that uses _ask_int to see that it raises an error at wrong response"""
        self.instr._transport.read_until.side_effect = [b"not an int\r\nNOK\r\n"]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_motor_position()

    def test_wrong_float_value(self):
        """Test a call that uses _ask_float to see that it raises an error at wrong response"""
        self.instr._transport.read_until.side_effect = [b"not a float\r\nNOK\r\n"]

        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_center_wavelength()

    def test_get_idn(self):
        """Test ident. """
        vendor = "WL Photonics"
        model = "WL200"
        serial = "201307374"
        version = "2018-11-23"
        self.instr._transport.read_until.side_effect = [
            b'WL200: SN(201307374), MD(2018-11-23)\r\n' +
            b'WL Range: 1021.509~1072.505nm(Step: 4654~556)\r\n' +
            b'OK\r\n',
        ]
        expected_calls = [
            call().write(b'dev?\r\n'),
            call().read_until(b'OK\r\n', timeout=5.0)
        ]

        ident = self.instr.get_idn()

        self._transport_mock.assert_has_calls(expected_calls)
        self.assertEqual(vendor, ident.vendor)
        self.assertEqual(model, ident.model)
        self.assertEqual(serial, ident.serial)
        self.assertEqual(version, ident.version)

    def test_wrong_idn_response(self):
        """Test ident. raises QMI_InstrumentException by a non-sense response."""
        self.instr._transport.read_until.side_effect = [b"nonsense"]
        expected_calls = [
            call().write(b"dev?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT)
        ]
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_idn()

        self._transport_mock.assert_has_calls(expected_calls)

    def test_set_center_wavelength(self):
        """Test setting the wavelength in nm."""
        input_wl = 1050
        decimals = 3
        self.instr._transport.read_until.side_effect = [
            f"Set Wavelength: {input_wl:.3f}\r\n".encode() + b"OK\r\n"
        ]
        expected_calls = [
            call().write(f"wl{input_wl:.{decimals}f}\r\n".encode()),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT)
        ]
        # Act
        self.instr.set_center_wavelength(input_wl)
        # Assert
        self._transport_mock.assert_has_calls(expected_calls)

    def test_set_center_wavelength_excepts(self):
        """Test setting the wavelength in nm with values out-of-bounds."""
        input_wl = [int(self.wl_min) - 1, int(self.wl_max) + 1]
        # Act
        for inp in input_wl:
            with self.assertRaises(ValueError):
                self.instr.set_center_wavelength(inp)

        # Assert
        self._transport_mock.assert_not_called()

    def test_get_center_wavelength(self):
        """Test getting the wavelength in nm."""
        wl = (self.wl_max - self.wl_min) / 2.0
        expected_wl = round(wl, 3)  # Output wl appears to be in 3 decimals.
        self.instr._transport.read_until.side_effect = [
            f"Wavelength:{wl:.3f}nm\r\nOK\r\n".encode()
        ]
        expected_calls = [
            call().write(b"wl?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT)
        ]
        # Act
        wavelength = self.instr.get_center_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._transport_mock.assert_has_calls(expected_calls)

    def test_get_minimum_wavelength_in_nm(self):
        """Test getting the minimum wavelength in nm."""
        expected_wl = round(self.wl_min, 4)  # We use 4 decimals for rounding output wl.
        # Act
        wavelength = self.instr.get_minimum_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._transport_mock.assert_not_called()

    def test_get_maximum_wavelength_in_nm(self):
        """Test getting the maximum wavelength in nm."""
        expected_wl = round(self.wl_max, 4)  # We use 4 decimals for rounding output wl.
        # Act
        wavelength = self.instr.get_maximum_wavelength()
        # Assert
        self.assertEqual(expected_wl, wavelength)
        self._transport_mock.assert_not_called()

    def test_reverse_motor(self):
        """Test moving the motor backwards."""
        input_steps = 200
        self.instr._transport.read_until.side_effect = [
            f"SB: {input_steps}\r\nOK\r\n".encode()
        ]
        expected_write_calls = [
            call().write(f"sb{input_steps}\r\n".encode())
        ]
        # Act
        self.instr.reverse_motor(input_steps)
        # Assert
        self._transport_mock.assert_has_calls(expected_write_calls)

    def test_reverse_motor_excepts(self):
        """Test setting the steps with values out-of-bounds."""
        input_step = self.step_max
        # Act
        with self.assertRaises(ValueError):
            self.instr.reverse_motor(input_step)

        # Assert
        self._transport_mock.assert_not_called()

    def test_forward_motor(self):
        """Test moving the motor forward."""
        input_steps = 200
        self.instr._transport.read_until.side_effect = [
            f"SF: {input_steps}\r\nOK\r\n".encode()
        ]
        expected_write_calls = [
            call().write(f"sf{input_steps}\r\n".encode())
        ]
        # Act
        self.instr.forward_motor(input_steps)
        # Assert
        self._transport_mock.assert_has_calls(expected_write_calls)

    def test_forward_motor_excepts(self):
        """Test setting the power_level with values out-of-bounds."""
        input_steps = self.step_max
        # Act
        with self.assertRaises(ValueError):
            self.instr.forward_motor(input_steps)

        # Assert
        self._transport_mock.assert_not_called()

    def test_get_motor_position(self):
        """Test getting the steps."""
        expected_step = (self.step_max - self.step_min) // 2
        self.instr._transport.read_until.side_effect = [
            f"Step: {expected_step}, Err: -1, Status: 0x340880\r\nOK\r\n".encode(),
            f"Step: {-expected_step}, Err: 1, Status: 0x340880\r\nOK\r\n".encode()
        ]
        expected_calls = [
            call().write(b"s?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT),
            call().write(b"s?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT)
        ]
        # Act
        steps_1 = self.instr.get_motor_position()
        steps_2 = self.instr.get_motor_position()  # Negative value, also possible
        # Assert
        self.assertEqual(expected_step, steps_1)
        self.assertEqual(-expected_step, steps_2)
        self._transport_mock.assert_has_calls(expected_calls)

    def test_get_minimum_steps(self):
        """Test getting the minimum steps."""
        expected_steps = self.step_min
        # Act
        steps = self.instr.get_minimum_steps()
        # Assert
        self.assertEqual(expected_steps, steps)
        self._transport_mock.assert_not_called()

    def test_get_maximum_steps(self):
        """Test getting the maximum steps."""
        expected_steps = self.step_max
        # Act
        steps = self.instr.get_maximum_steps()
        # Assert
        self.assertEqual(expected_steps, steps)
        self._transport_mock.assert_not_called()

    def test_go_to_zero(self):
        """Test zeroing motor position command."""
        # Shorten sleep time
        self.instr.ZEROING_WAIT = 0.01
        self.instr._transport.read_until.side_effect = [
            b"Go to Zero\r\nOK\r\n",
            b"Step: 0, Err: 0, Status: 0x340880\r\nOK\r\n",
        ]
        expected_write_calls = [
            call().write(b"z\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT),
            call().write(b"s?\r\n"),
            call().read_until(b'OK\r\n', timeout=WlPhotonics_WltfN.DEFAULT_RESPONSE_TIMEOUT),
        ]
        # Act
        self.instr.go_to_zero()
        # Assert
        self.assertEqual(0, self.instr._motor_position)
        self._transport_mock.assert_has_calls(expected_write_calls)
