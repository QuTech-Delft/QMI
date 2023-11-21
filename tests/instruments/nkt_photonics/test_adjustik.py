from collections import namedtuple
import logging
import unittest
from unittest.mock import Mock, call, patch

import qmi
from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException
from qmi.core.transport import QMI_Transport
from qmi.instruments.nkt_photonics import NktPhotonics_KoherasAdjustik
from qmi.instruments.nkt_photonics.nkt_photonics_interbus_protocol import NKTPhotonicsInterbusProtocol


class TestTransportOperations(unittest.TestCase):

    def setUp(self) -> None:
        # Add patches
        patcher = patch(
            'qmi.instruments.nkt_photonics.adjustik.create_transport', spec=QMI_Transport)
        self.transport = patcher.start().return_value
        self.addCleanup(patcher.stop)
        qmi.start("test_adjustik_open_close")
        self.laser = qmi.make_instrument("test_laser", NktPhotonics_KoherasAdjustik, "transport_stub")

    def tearDown(self) -> None:
        if self.laser.is_open():
            self.laser.close()
        qmi.stop()

    def test_open(self):
        # arrange
        expected_calls = [call.open(), call.discard_read()]
        # act
        self.laser.open()
        # assert
        self.assertEqual(self.transport.mock_calls, expected_calls)

    def test_close(self):
        # arrange
        expected_calls = [call.close]
        # act
        self.laser.open()
        self.transport.reset_mock()
        self.laser.close()
        # assert
        self.assertEqual(self.transport.mock_calls, expected_calls)


class TestMethods(unittest.TestCase):

    def setUp(self) -> None:
        qmi.start("test_adjustik_methods")

        patcher = patch(
            'qmi.instruments.nkt_photonics.adjustik.create_transport', spec=QMI_Transport)
        self.transport = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch(
            'qmi.instruments.nkt_photonics.adjustik.NKTPhotonicsInterbusProtocol',
            spec=NKTPhotonicsInterbusProtocol
        )
        self.interbus = patcher.start().return_value
        self.addCleanup(patcher.stop)

        self.laser = qmi.make_instrument("test_laser", NktPhotonics_KoherasAdjustik, "transport_stub")
        self.laser.open()

    def tearDown(self) -> None:
        if self.laser.is_open():
            self.laser.close()
        qmi.stop()

    def test_getters(self):
        TestDescr = namedtuple("TestDescriptor", ["method_name", "register", "value", "value_bytes"])
        test_list = [
            TestDescr("get_basik_module_type",                          0x61,       (0x33), b"\x33"),
            TestDescr("get_basik_emission",                             0x30,          (1), b"\x01"),
            TestDescr("get_basik_setup_bits",                           0x31,     (0xFFFF), b"\xff\xff"),
            TestDescr("get_basik_output_power_setpoint_mW",             0x22,        (3.0), b',\x01'),
            TestDescr("get_basik_output_power_setpoint_dBm",            0xa0,        (3.0), b',\x01'),
            TestDescr("get_basik_wavelength_offset_setpoint",           0x2a,     (1000.0), b"\x10'"),
            TestDescr("get_basik_user_area",                            0x8d, (bytes(240)), bytes(240)),
            TestDescr("get_basik_status_bits",                          0x66,     (0xFFFF), b"\xff\xff"),
            TestDescr("get_basik_output_power_mW",                      0x17,        (3.0), b',\x01'),
            TestDescr("get_basik_output_power_dBm",                     0x90,        (3.0), b',\x01'),
            TestDescr("get_basik_standard_wavelength",                  0x32,     (6150.5), b'\x41\xf0\x00\x00'),
            TestDescr("get_basik_wavelength_offset",                    0x72,     (6150.5), b'\x41\xf0\x00\x00'),
            TestDescr("get_basik_module_temperature",                   0x1c,       (1000), b"\x10'"),
            TestDescr("get_basik_module_supply_voltage",                0x1e,         (10), b"\x10'"),
            TestDescr("get_basik_module_wavelength_modulation_enabled", 0xb5,          (1), b"\x01"),
            TestDescr("get_basik_wavelength_modulation_frequency",      0xb8,    (2.0, 1.0), b'\x00\x00\x00\x40\x00\x00\x80\x3f'),
            TestDescr("get_basik_wavelength_modulation_level",          0x2b,       (1000), b"\x10'"),
            TestDescr("get_basik_wavelength_modulation_offset",         0x2f,       (1000), b"\x10'"),
            TestDescr("get_basik_amplitude_modulation_frequency",       0xba,    (2.0, 1.0), b'\x00\x00\x00\x40\x00\x00\x80\x3f'),
            TestDescr("get_basik_amplitude_modulation_depth",           0x2c,       (1000), b"\x10'"),
            TestDescr("get_basik_modulation_setup_bits",                0xb7,     (0xFFFF), b"\xff\xff"),
            TestDescr("get_adjustik_module_type",                       0x61,       (0x34), b"\x34"),
        ]
        for test in test_list:
            self.interbus.reset_mock()
            with self.subTest(i=test.method_name):
                # arrange per test
                self.interbus.get_register.return_value = test.value_bytes
                expected_dest = 0x01 if "basik" in test.method_name else 0x80 if "adjustik" in test.method_name else 0x00
                # act
                actual_rv = getattr(self.laser, test.method_name)()
                # assert
                self.assertEqual(actual_rv, test.value)
                self.interbus.get_register.assert_called_once_with(expected_dest, test.register)

    def test_setters(self):
        TestDescr = namedtuple("TestDescriptor", ["method_name", "register", "value", "value_bytes"])
        test_list = [
            TestDescr("set_basik_setup_bits",                      0x31,  (0xFFFF,), b"\xff\xff"),
            TestDescr("set_basik_output_power_setpoint_mW",        0x22,     (3.0,), b',\x01'),
            TestDescr("set_basik_output_power_setpoint_dBm",       0xa0,     (3.0,), b',\x01'),
            TestDescr("set_basik_wavelength_offset_setpoint",      0x2a,  (1000.0,), b"\x10'"),
            TestDescr("set_basik_wavelength_modulation_frequency", 0xb8,  (2.0, 1.0), b'\x00\x00\x00\x40\x00\x00\x80\x3f'),
            TestDescr("set_basik_wavelength_modulation_level",     0x2b,  (1000.0,), b"\x10'"),
            TestDescr("set_basik_wavelength_modulation_offset",    0x2f,  (1000.0,), b"\x10'"),
            TestDescr("set_basik_modulation_setup_bits",           0xb7,  (0xFFFF,), b"\xff\xff"),
        ]
        for test in test_list:
            self.interbus.reset_mock()
            with self.subTest(i=test.method_name):
                # arrange
                expected_dest = 0x01 if "basik" in test.method_name else 0x80 if "adjustik" in test.method_name else 0x00
                # act
                getattr(self.laser, test.method_name)(*test.value)
                # assert
                self.interbus.set_register.assert_called_once_with(expected_dest, test.register, test.value_bytes)

    def test_enable_basik_emission_enables_emission(self):
        self.interbus.reset_mock()
        # arrange
        expected_dest = 0x01
        # act
        getattr(self.laser, "enable_basik_emission")()
        # assert
        self.interbus.set_register.assert_called_once_with(expected_dest, 0x30, b"\x01")

    def test_disable_basik_emission_disables_emission(self):
        self.interbus.reset_mock()
        # arrange
        expected_dest = 0x01
        # act
        getattr(self.laser, "disable_basik_emission")()
        # assert
        self.interbus.set_register.assert_called_once_with(expected_dest, 0x30, b"\x00")


class TestInterbus(unittest.TestCase):

    ADJUSTIK_TIMEOUT = 1.0

    def setUp(self):

        # Suppress logging.
        logging.getLogger("qmi.instruments.nkt_photonics.nkt_photonics_interbus_protocol").setLevel(logging.CRITICAL)

        context = Mock()
        self._mock_transport = Mock()

        with patch("qmi.instruments.nkt_photonics.adjustik.create_transport", return_value=self._mock_transport):
            self._laser = NktPhotonics_KoherasAdjustik(context, "laser", "transport_stub")

        self._laser.open()

        self.assertEqual(self._mock_transport.mock_calls, [
            call.open(),
            call.discard_read()
        ])
        self._mock_transport.reset_mock()

    def tearDown(self):
        logging.getLogger("qmi.instruments.nkt_photonics.nkt_photonics_interbus_protocol").setLevel(logging.NOTSET)

    def test_get_request(self):

        # Request: dst=1, src=161, MessageType.READ, reg=0x32
        request_msg = bytes([0x0d, 0x01, 0xa1, 0x04, 0x32, 0x26, 0xcd, 0x0a])

        # Response: dst=161, src=1, MessageType.DATAGRAM, reg=0x32, data=uint32(10644000)
        response_msg = bytes([0x0d, 0xa1, 0x01, 0x08, 0x32, 0x20, 0x6a, 0xa2, 0x00, 0x2c, 0x8c, 0x0a])

        self._mock_transport.read_until.return_value = response_msg

        v = self._laser.get_basik_standard_wavelength()
        self.assertAlmostEqual(v, 1064400.0)

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT)
        ])

    def test_set_request(self):

        # Request: dst=1, src=161, MessageType.WRITE, reg=0x2a, data=int16(840)
        request_msg = bytes([0x0d, 0x01, 0xa1, 0x05, 0x2a, 0x48, 0x03, 0x8c, 0xd1, 0x0a])

        # Response: dst=161, src=1, MessageType.ACK, reg=0x2a
        response_msg = bytes([0x0d, 0xa1, 0x01, 0x03, 0x2a, 0x7b, 0x89, 0x0a])

        self._mock_transport.read_until.return_value = response_msg

        self._laser.set_basik_wavelength_offset_setpoint(84.0)

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT)
        ])

    def test_two_requests(self):

        # Request: dst=1, src=161, MessageType.READ, reg=0x32
        request_msg_1 = bytes([0x0d, 0x01, 0xa1, 0x04, 0x32, 0x26, 0xcd, 0x0a])

        # Response: dst=161, src=1, MessageType.DATAGRAM, reg=0x32, data=uint32(10644000)
        response_msg_1 = bytes([0x0d, 0xa1, 0x01, 0x08, 0x32, 0x20, 0x6a, 0xa2, 0x00, 0x2c, 0x8c, 0x0a])

        # Request: dst=1, src=162, MessageType.READ, reg=0x2a
        request_msg_2 = bytes([0x0d, 0x01, 0xa2, 0x04, 0x2a, 0xec, 0xa4, 0x0a])

        # Response: dst=162, src=1, MessageType.DATAGRAM, reg=0x2a, data=int16(740)
        response_msg_2 = bytes([0x0d, 0xa2, 0x01, 0x08, 0x2a, 0xe4, 0x02, 0xf8, 0xc9, 0x0a])

        self._mock_transport.read_until.side_effect = [response_msg_1, response_msg_2]

        v = self._laser.get_basik_standard_wavelength()
        self.assertAlmostEqual(v, 1064400.0)

        v = self._laser.get_basik_wavelength_offset_setpoint()
        self.assertAlmostEqual(v, 74.0)

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg_1),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
            call.write(request_msg_2),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT)
        ])

    def test_retry_after_timeout(self):

        # Request: dst=1, src=161, MessageType.READ, reg=0x32
        request_msg = bytes([0x0d, 0x01, 0xa1, 0x04, 0x32, 0x26, 0xcd, 0x0a])

        # Response: dst=161, src=1, MessageType.DATAGRAM, reg=0x32, data=uint32(10644000)
        response_msg = bytes([0x0d, 0xa1, 0x01, 0x08, 0x32, 0x20, 0x6a, 0xa2, 0x00, 0x2c, 0x8c, 0x0a])

        # First time raise QMI_TimeoutException. Second time return expected response.
        read_until_data = [QMI_TimeoutException(), response_msg]

        def fake_read_until(message_terminator, timeout):
            v = read_until_data.pop(0)
            if isinstance(v, Exception):
                raise v
            else:
                return v

        self._mock_transport.read_until.side_effect = fake_read_until

        v = self._laser.get_basik_standard_wavelength()
        self.assertAlmostEqual(v, 1064400.0)

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT)
        ])

    def test_retry_after_bad_message(self):

        # Request: dst=1, src=161, MessageType.READ, reg=0x32
        request_msg = bytes([0x0d, 0x01, 0xa1, 0x04, 0x32, 0x26, 0xcd, 0x0a])

        # Response: dst=161, src=1, MessageType.DATAGRAM, reg=0x32, data=uint32(10644000)
        response_msg = bytes([0x0d, 0xa1, 0x01, 0x08, 0x32, 0x20, 0x6a, 0xa2, 0x00, 0x2c, 0x8c, 0x0a])

        # First time return garbage. Second time return expected response.
        self._mock_transport.read_until.side_effect = [b"\raap noot\n", response_msg]

        v = self._laser.get_basik_standard_wavelength()
        self.assertAlmostEqual(v, 1064400.0)

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT)
        ])

    def test_nack_response(self):

        # Request: dst=1, src=161, MessageType.READ, reg=0x32
        request_msg = bytes([0x0d, 0x01, 0xa1, 0x04, 0x32, 0x26, 0xcd, 0x0a])

        # Response: dst=161, src=1, MessageType.NACK, reg=0x32
        response_msg = bytes([0x0d, 0xa1, 0x01, 0x00, 0x32, 0xbd, 0xe3, 0x0a])

        # First time return garbage. Second time return expected response.
        self._mock_transport.read_until.return_value = response_msg

        with self.assertRaises(QMI_InstrumentException):
            self._laser.get_basik_standard_wavelength()

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
        ])

    def test_unsync_after_timeout(self):

        # Request: dst=1, src=161, MessageType.READ, reg=0x32
        request_msg_1 = bytes([0x0d, 0x01, 0xa1, 0x04, 0x32, 0x26, 0xcd, 0x0a])

        # Response: dst=161, src=1, MessageType.DATAGRAM, reg=0x32, data=uint32(10644000)
        response_msg_1 = bytes([0x0d, 0xa1, 0x01, 0x08, 0x32, 0x20, 0x6a, 0xa2, 0x00, 0x2c, 0x8c, 0x0a])

        # Request: dst=1, src=162, MessageType.READ, reg=0x2a
        request_msg_2 = bytes([0x0d, 0x01, 0xa2, 0x04, 0x2a, 0xec, 0xa4, 0x0a])

        # Response: dst=162, src=1, MessageType.DATAGRAM, reg=0x2a, data=int16(740)
        response_msg_2 = bytes([0x0d, 0xa2, 0x01, 0x08, 0x2a, 0xe4, 0x02, 0xf8, 0xc9, 0x0a])

        self._mock_transport.read_until.side_effect = [response_msg_1, response_msg_2]

        # 1st call: Raise QMI_TimeoutException.
        # 2nd call: Return expected response.
        # 3rd call: Return duplicate of first response.
        # 4th call: Return expected response.
        read_until_data = [QMI_TimeoutException(), response_msg_1, response_msg_1, response_msg_2]

        def fake_read_until(message_terminator, timeout):
            v = read_until_data.pop(0)
            if isinstance(v, Exception):
                raise v
            else:
                return v

        self._mock_transport.read_until.side_effect = fake_read_until

        v = self._laser.get_basik_standard_wavelength()
        self.assertAlmostEqual(v, 1064400.0)

        v = self._laser.get_basik_wavelength_offset_setpoint()
        self.assertAlmostEqual(v, 74.0)

        self.assertEqual(self._mock_transport.mock_calls, [
            call.write(request_msg_1),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
            call.write(request_msg_1),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
            call.write(request_msg_2),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT),
            call.read_until(message_terminator=b"\n", timeout=self.ADJUSTIK_TIMEOUT)
        ])
