"""Unit-tests for Santec MPM-210H driver class."""
import logging
import re
import struct
import unittest
from unittest.mock import Mock, call, patch

from qmi.core.exceptions import (
    QMI_InstrumentException, QMI_InvalidOperationException, QMI_TimeoutException, QMI_UsageException
)
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.core.transport import QMI_Transport
from qmi.instruments.santec.mpm_210h import Santec_Mpm210H

from tests.patcher import PatcherQmiContext as QMI_Context

TCP_TRANSPORT = "tcp:192.0.2.1:5000"
SERIAL_TRANSPORT = "serial:COM3"
GPIB_TRANSPORT = "gpib:16"
NO_ERROR = "0,No error"


def setUpModule():
    # Tests below deliberately use closed instruments; silence the resulting error logging.
    logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)


def tearDownModule():
    logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)


class _Mpm210hTestBase(unittest.TestCase):
    """Common set-up: a mocked transport, and a patched ``sleep`` to keep the tests fast."""

    def setUp(self) -> None:
        logging.getLogger("qmi.instruments.santec.mpm_210h").setLevel(logging.CRITICAL)
        self.transport = Mock(spec=QMI_Transport)
        patcher = patch("qmi.instruments.santec.mpm_210h.create_transport", return_value=self.transport)
        self.create_transport = patcher.start()
        self.addCleanup(patcher.stop)
        # Patch sleep before any driver is made, as the protocol binds it for the TCP command wait.
        patcher = patch("qmi.instruments.santec.mpm_210h.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        logging.getLogger("qmi.instruments.santec.mpm_210h").setLevel(logging.NOTSET)

    def _make_driver(self, transport: str = TCP_TRANSPORT, slot: int = 2) -> Santec_Mpm210H:
        return Santec_Mpm210H(QMI_Context("Santec_mpm-210h-test"), "mpm", transport, slot)

    def _open_driver(
        self, transport: str = TCP_TRANSPORT, slot: int = 2, model: str = "MPM-211"
    ) -> Santec_Mpm210H:
        """Make and open a driver for the given module model, then reset the transport mock."""
        driver = self._make_driver(transport, slot)
        self._respond(f"Santec,{model},00000000M211,Ver1.11")
        driver.open()
        self.transport.reset_mock()
        self.transport.read_until.side_effect = None
        self.sleep.reset_mock()
        return driver

    def _respond(self, *responses: str) -> None:
        """Queue CR+LF terminated responses to be returned by ``read_until``."""
        self.transport.read_until.side_effect = [f"{response}\r\n".encode("ascii") for response in responses]

    def _assert_writes(self, *commands: str, terminator: str = "\n") -> None:
        """Assert the exact sequence of commands written to the transport."""
        self.assertEqual(
            self.transport.write.call_args_list,
            [call(f"{command}{terminator}".encode("ascii")) for command in commands],
        )


class TestSantecMpm210hOpenClose(_Mpm210hTestBase):
    """Test driver creation, open and close with the different transport types, and the protocol handling."""

    def test_init_creates_transport_with_default_attributes(self) -> None:
        """Each supported transport type is created with its documented default attributes."""
        cases = [
            (TCP_TRANSPORT, {"port": 5000}),
            (SERIAL_TRANSPORT, {"baudrate": 115200, "bytesize": 8, "parity": "N", "stopbits": 1.0, "rtscts": False}),
            (GPIB_TRANSPORT, {"primary_addr": 16}),
            ("TCP:192.0.2.1", {"port": 5000}),
        ]
        for transport, default_attributes in cases:
            with self.subTest(transport=transport):
                self.create_transport.reset_mock()

                driver = self._make_driver(transport)

                self.create_transport.assert_called_once_with(transport, default_attributes=default_attributes)
                self.assertFalse(driver.is_open())

    def test_init_rejects_unsupported_transport(self) -> None:
        """Transport types other than tcp, serial and gpib are rejected."""
        for transport in ("udp:192.0.2.1:5000", "usbtmc:vendorid=0x1313,productid=0x8078", "vxi11:192.0.2.1", ""):
            with self.subTest(transport=transport), self.assertRaises(ValueError):
                self._make_driver(transport)

        self.create_transport.assert_not_called()

    def test_init_rejects_invalid_slot(self) -> None:
        """Only integer slot numbers 0 through 4 are accepted."""
        for slot in (-1, 5, True, 1.0, "1"):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                self._make_driver(slot=slot)

        for slot in range(5):
            with self.subTest(slot=slot):
                self._make_driver(slot=slot)

    def test_init_default_slot(self) -> None:
        """The driver addresses slot 0 by default."""
        driver = Santec_Mpm210H(QMI_Context("Santec_mpm-210h-test"), "mpm", TCP_TRANSPORT)
        self._respond("Santec,MPM-211,00000000M211,Ver1.11")

        driver.open()

        self._assert_writes("MMVER? 0")

    def test_init_range_defaults(self) -> None:
        """Ranges are initialized with the defaults from the manual."""
        driver = self._make_driver()

        self.assertEqual(str(driver._wavelength_range), "_WavelengthRange(min=1250.0, max=1630.0)")
        self.assertEqual(str(driver._step_range), "_StepRange(min=0.001, max=10.0)")
        self.assertEqual(str(driver._sweep_speed_range), "_SweepSpeedRange(min=0.001, max=200.0)")
        self.assertEqual(str(driver._averaging_time_range), "_AveragingTimeRange(min=0.01, max=10000.0)")

    def test_open_close(self) -> None:
        """open() opens the transport and reads the module model; close() closes the transport."""
        cases = [(TCP_TRANSPORT, "\n", b"\n"), (SERIAL_TRANSPORT, "\n", b"\n"), (GPIB_TRANSPORT, "", b"")]
        for transport, terminator, read_terminator in cases:
            with self.subTest(transport=transport):
                self.transport.reset_mock()
                driver = self._make_driver(transport, slot=3)
                self._respond("Santec,mpm-213 ,00000000M213,Ver1.11")

                driver.open()

                self.assertTrue(driver.is_open())
                self.transport.open.assert_called_once_with()
                self._assert_writes("MMVER? 3", terminator=terminator)
                self.transport.read_until.assert_called_once_with(read_terminator, timeout=10.0)
                self.assertEqual(driver._module, "MPM-213")
                self.assertEqual(driver._channel_count, 4)

                driver.close()

                self.assertFalse(driver.is_open())
                self.transport.close.assert_called_once_with()

    def test_open_sets_channel_count_by_module(self) -> None:
        """The MPM-212 has two channels, other modules have four."""
        for model, channel_count in (("MPM-211", 4), ("MPM-212", 2), ("MPM-213", 4), ("MPM-215", 4)):
            with self.subTest(model=model):
                driver = self._open_driver(model=model)

                self.assertEqual(driver._channel_count, channel_count)
                driver.close()

    def test_open_fails_on_invalid_identification(self) -> None:
        """A malformed MMVER? response aborts open() and closes the transport again."""
        driver = self._make_driver()
        self._respond("Santec,MPM-211")

        with self.assertRaises(QMI_InstrumentException):
            driver.open()

        self.assertFalse(driver.is_open())
        self.transport.close.assert_called_once_with()

    def test_open_fails_on_timeout(self) -> None:
        """No MMVER? response over GPIB (empty read) aborts open() and closes the transport again."""
        driver = self._make_driver(GPIB_TRANSPORT)
        self.transport.read_until.return_value = b""

        with self.assertRaises(QMI_InstrumentException) as exc:
            driver.open()

        self.assertIsInstance(exc.exception.__cause__, QMI_TimeoutException)
        self.assertFalse(driver.is_open())
        self.transport.close.assert_called_once_with()

    def test_rpc_methods_require_open_instrument(self) -> None:
        """Commands and queries are refused before open()."""
        driver = self._make_driver()

        with self.assertRaises(QMI_InvalidOperationException):
            driver.get_wavelength()

        with self.assertRaises(QMI_InvalidOperationException):
            driver.set_wavelength(1550.0)

        with self.assertRaises(QMI_InvalidOperationException):
            driver.get_logged_data(1)

        # Before open, all four channels are accepted, as the module model is not known yet.
        with self.assertRaises(QMI_InvalidOperationException):
            driver.get_channel_wavelength(4)

        with self.assertRaises(QMI_InvalidOperationException):
            self._make_driver(SERIAL_TRANSPORT).set_serial_echo(True)

        self.transport.write.assert_not_called()

    def test_command_termination_per_transport(self) -> None:
        """Commands use LF over TCP and serial, and no terminator over GPIB."""
        for transport, terminator in ((TCP_TRANSPORT, "\n"), (SERIAL_TRANSPORT, "\n"), (GPIB_TRANSPORT, "")):
            with self.subTest(transport=transport):
                driver = self._open_driver(transport)
                self._respond(NO_ERROR)

                driver.start_measurement()

                self._assert_writes("MEAS", "ERR?", terminator=terminator)
                driver.close()

    def test_query_strips_line_endings(self) -> None:
        """Both CR+LF (TCP, serial) and a lone CR (GPIB) are stripped from responses."""
        driver = self._open_driver(GPIB_TRANSPORT)
        self.transport.read_until.side_effect = [b"1550\r"]

        self.assertEqual(driver.get_wavelength(), 1550.0)
        self.transport.read_until.assert_called_once_with(b"", timeout=10.0)

    def test_empty_response_raises_timeout(self) -> None:
        """An empty response, as returned by GPIB on timeout, raises a timeout exception."""
        driver = self._open_driver(GPIB_TRANSPORT)
        self.transport.read_until.return_value = b""

        with self.assertRaises(QMI_TimeoutException):
            driver.get_wavelength()

    def test_tcp_waits_after_each_command(self) -> None:
        """Only over TCP, the driver waits 10 ms after sending each command."""
        cases = [(TCP_TRANSPORT, [call(0.01), call(0.01)]), (SERIAL_TRANSPORT, []), (GPIB_TRANSPORT, [])]
        for transport, expected_calls in cases:
            with self.subTest(transport=transport):
                driver = self._open_driver(transport)
                self._respond(NO_ERROR)

                driver.set_wavelength(1550.0)

                self.assertEqual(self.sleep.call_args_list, expected_calls)
                driver.close()

    def test_write_drains_error_queue_and_raises(self) -> None:
        """Commands drain ERR? until "No error", decoding known and unknown error codes."""
        driver = self._open_driver()
        self._respond("-222,Data out of range", '999,"Strange error"', NO_ERROR)

        with self.assertRaisesRegex(QMI_InstrumentException, "Data out of range.*Unknown error 999: Strange error"):
            driver.set_wavelength(1550.0)

        self._assert_writes("WAV 1550.000", "ERR?", "ERR?", "ERR?")

    def test_error_codes_are_decoded(self) -> None:
        """All error codes documented in the manual are decoded to their description."""
        documented_errors = {
            -101: "Invalid character",
            -103: "Invalid separator",
            -104: "Data type error",
            -108: "Parameter not allowed",
            -109: "Missing parameter",
            -110: "Command header error",
            -113: "Undefined header",
            -221: "Setting conflict",
            -222: "Data out of range",
            -284: "Program currently running",
            -300: "Device-specific error",
            -301: "Not a measurement module",
            -350: "Queue overflow",
            -351: "Queue empty",
            101: "Module communication header error",
            103: "Module communication response number error",
            104: "Module communication module mismatch",
            110: "TCP/IP communication error",
            116: "GPIB transmission not completed",
            117: "GPIB transmission timer expired",
            120: "Measurement controller trigger error",
            210: "SEM does not exist",
        }
        driver = self._open_driver()
        for code, description in documented_errors.items():
            with self.subTest(code=code):
                self._respond(f'{code},"raw message"', NO_ERROR)

                with self.assertRaisesRegex(QMI_InstrumentException, re.escape(str([description]))):
                    driver.start_measurement()

    def test_malformed_error_response_raises(self) -> None:
        """ERR? responses without a separator or with a non-integer code are rejected."""
        driver = self._open_driver()
        for response in ("No error", "x,No error"):
            with self.subTest(response=response):
                self._respond(response)

                with self.assertRaises(QMI_InstrumentException):
                    driver.start_measurement()

    def test_serial_echo(self) -> None:
        """With serial echo enabled, the echo of every command is read back and checked before the response."""
        driver = self._open_driver(SERIAL_TRANSPORT)
        # Echo handling is active for the ERR? check that follows the ECHO command.
        self._respond("ERR?", NO_ERROR)

        driver.set_serial_echo(True)

        self._assert_writes("ECHO 1", "ERR?")
        self.sleep.assert_called_once_with(0.1)
        self.transport.discard_read.assert_called_once_with()

        self._respond("LOGN?", "10")
        self.assertEqual(driver.get_logging_points(), 10)

        self._respond("something else")
        with self.assertRaisesRegex(QMI_InstrumentException, "Unexpected echo"):
            driver.get_logging_points()

        # A garbled, non-ASCII echo is also reported as an unexpected echo.
        self.transport.read_until.side_effect = [b"LOGN\xff?\r\n"]
        with self.assertRaisesRegex(QMI_InstrumentException, "Unexpected echo"):
            driver.get_logging_points()

        # The echo of ECHO 0 itself is discarded, and the following ERR? is no longer echoed.
        self.transport.reset_mock()
        self._respond(NO_ERROR)

        driver.set_serial_echo(False)

        self._assert_writes("ECHO 0", "ERR?")
        self.transport.discard_read.assert_called_once_with()
        self._respond("10")
        self.assertEqual(driver.get_logging_points(), 10)

    def test_serial_echo_is_rejected_for_other_transports(self) -> None:
        """ECHO is only available on RS-232."""
        for transport in (TCP_TRANSPORT, GPIB_TRANSPORT):
            with self.subTest(transport=transport):
                driver = self._open_driver(transport)

                with self.assertRaises(QMI_InstrumentException):
                    driver.set_serial_echo(True)

                self.transport.write.assert_not_called()
                driver.close()

    def test_serial_echo_error_is_raised(self) -> None:
        """An error reported after the ECHO command is raised."""
        driver = self._open_driver(SERIAL_TRANSPORT)
        self._respond("-108,Parameter not allowed", NO_ERROR)

        with self.assertRaisesRegex(QMI_InstrumentException, "Parameter not allowed"):
            driver.set_serial_echo(False)


class TestSantecMpm210hRpcProperties(_Mpm210hTestBase):
    """Test the RPC properties through a proxy in a real QMI context."""

    def setUp(self) -> None:
        super().setUp()
        self._ctx = QMI_Context("Santec_mpm-210h-rpc-test")

    def test_zeroing_wait_time_property_is_used(self) -> None:
        """A changed ZEROING_WAIT_TIME is used by zero()."""
        instr = Santec_Mpm210H(self._ctx, "mpm", TCP_TRANSPORT, 2)
        self._respond("Santec,MPM-211,00000000M211,Ver1.11", NO_ERROR)
        instr.open()
        try:
            instr.ZEROING_WAIT_TIME = 5
            instr.zero()
        finally:
            instr.close()

        self.assertEqual(self.sleep.call_args_list[-1], call(5))

    def test_response_timeout_property_is_used(self) -> None:
        """Echo reads and query responses use the current DEFAULT_RESPONSE_TIMEOUT."""
        instr = Santec_Mpm210H(self._ctx, "mpm", SERIAL_TRANSPORT, 2)
        self._respond("Santec,MPM-211,00000000M211,Ver1.11", "ERR?", NO_ERROR, "WAV?", "1550")
        with instr:
            instr.DEFAULT_RESPONSE_TIMEOUT = 20.0
            instr.set_serial_echo(True)
            instr.get_wavelength()

        self.assertEqual(
            self.transport.read_until.call_args_list,
            [call(b"\n", timeout=10.0)] + [call(b"\n", timeout=20.0)] * 4,
        )

    def test_response_timeout_property_is_used_for_logged_data(self) -> None:
        """The binary LOGG? block reads use the current DEFAULT_RESPONSE_TIMEOUT."""
        instr = Santec_Mpm210H(self._ctx, "mpm", TCP_TRANSPORT, 2)
        self._respond("Santec,MPM-211,00000000M211,Ver1.11")
        self.transport.read.side_effect = [b"#1", b"4", struct.pack("<f", 1.5)]
        self.transport.read_until_timeout.return_value = b""
        with instr:
            instr.DEFAULT_RESPONSE_TIMEOUT = 20.0
            self.assertEqual(instr.get_logged_data(1), [1.5])

        self.assertEqual(
            self.transport.read.call_args_list,
            [call(2, timeout=20.0), call(1, timeout=20.0), call(4, timeout=20.0)],
        )
        self.transport.read_until_timeout.assert_called_once_with(2, timeout=0.1)


class TestSantecMpm210hMethods(_Mpm210hTestBase):
    """Test the RPC methods of an opened MPM-210H driver."""

    def setUp(self) -> None:
        super().setUp()
        self.instr = self._open_driver()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()

        super().tearDown()

    def _reopen(self, model: str, transport: str = TCP_TRANSPORT) -> None:
        """Replace the driver under test with one for another module model or transport."""
        self.instr.close()
        self.instr = self._open_driver(transport, model=model)

    def _assert_setter(self, method, args: tuple, command: str) -> None:
        """Assert that a setter sends ``command`` followed by an error check."""
        self.transport.reset_mock()
        self._respond(NO_ERROR)

        method(*args)

        self._assert_writes(command, "ERR?")

    def _assert_getter(self, method, args: tuple, command: str, response: str, expected) -> None:
        """Assert that a getter sends ``command`` and parses ``response`` into ``expected``."""
        self.transport.reset_mock()
        self._respond(response)

        self.assertEqual(method(*args), expected)

        self._assert_writes(command)

    def _assert_rejected(self, method, args: tuple, exception: type[Exception] = ValueError) -> None:
        """Assert that a call raises ``exception`` without sending anything."""
        self.transport.reset_mock()

        with self.assertRaises(exception):
            method(*args)

        self.transport.write.assert_not_called()

    def _assert_bad_response(self, method, args: tuple, response: str) -> None:
        """Assert that a getter rejects the given response."""
        self._respond(response)

        with self.assertRaises(QMI_InstrumentException):
            method(*args)

    def test_get_idn(self) -> None:
        """MMVER? returns the identification of the driver's module."""
        expected = QMI_InstrumentIdentification("Santec", "MPM-211", "00000000M211", "Ver1.11")
        self._assert_getter(self.instr.get_idn, (), "MMVER? 2", "Santec, MPM-211, 00000000M211, Ver1.11", expected)
        self._assert_bad_response(self.instr.get_idn, (), "Santec,MPM-211,00000000M211")

    def test_get_mainframe_idn(self) -> None:
        """*IDN? returns the identification of the mainframe."""
        expected = QMI_InstrumentIdentification("SANTEC", "MPM-210H", "00000000", "Ver.2.0")
        self._assert_getter(self.instr.get_mainframe_idn, (), "*IDN?", "SANTEC,MPM-210H,00000000,Ver.2.0", expected)
        self._assert_bad_response(self.instr.get_mainframe_idn, (), "SANTEC,MPM-210H,00000000,Ver.2.0,extra")

    def test_get_error(self) -> None:
        """ERR? returns the raw error code and message, with quotes removed."""
        self._assert_getter(self.instr.get_error, (), "ERR?", '-103,"Invalid separator"', (-103, "Invalid separator"))
        self._assert_getter(self.instr.get_error, (), "ERR?", NO_ERROR, (0, "No error"))

    def test_get_module_recognition(self) -> None:
        """IDIS? returns the recognition state of all five slots."""
        self._assert_getter(
            self.instr.get_module_recognition, (), "IDIS?", "1,0,1,0,0", [True, False, True, False, False]
        )
        for response in ("1,0,1,0", "1,0,1,0,2", "1,0,x,0,0"):
            with self.subTest(response=response):
                self._assert_bad_response(self.instr.get_module_recognition, (), response)

    def test_gpib_address(self) -> None:
        """ADDR sets and ADDR? returns the GPIB address from 1 through 31."""
        self._assert_setter(self.instr.set_gpib_address, (1,), "ADDR 1")
        self._assert_setter(self.instr.set_gpib_address, (31,), "ADDR 31")
        for address in (0, 32, True):
            with self.subTest(address=address):
                self._assert_rejected(self.instr.set_gpib_address, (address,))

        self._assert_getter(self.instr.get_gpib_address, (), "ADDR?", "16", 16)
        self._assert_bad_response(self.instr.get_gpib_address, (), "sixteen")

    def test_network_addresses(self) -> None:
        """GW, SUBNET and IP set, and their queries return, IPv4 addresses."""
        cases = [
            (self.instr.set_gateway_address, self.instr.get_gateway_address, "GW", "192.168.1.254"),
            (self.instr.set_subnet_mask, self.instr.get_subnet_mask, "SUBNET", "255.255.255.0"),
            (self.instr.set_ip_address, self.instr.get_ip_address, "IP", "192.168.1.161"),
        ]
        for setter, getter, command, address in cases:
            with self.subTest(command=command):
                self._assert_setter(setter, (address,), f"{command} {address}")
                self._assert_getter(getter, (), f"{command}?", address, address)
                for invalid in ("192.168.1", "192.168.1.256", "localhost"):
                    self._assert_rejected(setter, (invalid,))

    def test_trigger_mode(self) -> None:
        """TRIG sets and TRIG? returns internal (False) or external (True) triggering."""
        self._assert_setter(self.instr.set_trigger_mode, (True,), "TRIG 1")
        self._assert_setter(self.instr.set_trigger_mode, (False,), "TRIG 0")
        self._assert_getter(self.instr.get_trigger_mode, (), "TRIG?", "1", True)
        self._assert_getter(self.instr.get_trigger_mode, (), "TRIG?", "0", False)
        self._assert_bad_response(self.instr.get_trigger_mode, (), "2")

    def test_measurement_mode(self) -> None:
        """WMOD sets and WMOD? returns the measurement mode, in upper case."""
        for mode in Santec_Mpm210H.VALID_MEASUREMENT_MODES:
            with self.subTest(mode=mode):
                self._assert_setter(self.instr.set_measurement_mode, (mode.lower(),), f"WMOD {mode}")

        self._assert_rejected(self.instr.set_measurement_mode, ("SWEEP3",))
        self._assert_getter(self.instr.get_measurement_mode, (), "WMOD?", "sweep2", "SWEEP2")

    def test_measurement_mode_mpm_215(self) -> None:
        """The MPM-215 supports only the CONST2 and SWEEP2 modes."""
        self._reopen("MPM-215")

        self._assert_setter(self.instr.set_measurement_mode, ("CONST2",), "WMOD CONST2")
        self._assert_setter(self.instr.set_measurement_mode, ("SWEEP2",), "WMOD SWEEP2")
        for mode in ("CONST1", "SWEEP1", "FREERUN"):
            with self.subTest(mode=mode):
                self._assert_rejected(self.instr.set_measurement_mode, (mode,))

    def test_wavelength(self) -> None:
        """WAV sets and WAV? returns the constant-wavelength measurement wavelength."""
        self._assert_setter(self.instr.set_wavelength, (1250,), "WAV 1250.000")
        self._assert_setter(self.instr.set_wavelength, (1630.0,), "WAV 1630.000")
        for wavelength in (1249.999, 1630.001):
            with self.subTest(wavelength=wavelength):
                self._assert_rejected(self.instr.set_wavelength, (wavelength,))

        self._assert_getter(self.instr.get_wavelength, (), "WAV?", "1550.125", 1550.125)
        self._assert_bad_response(self.instr.get_wavelength, (), "a lot")

    def test_wavelength_uses_the_instance_range(self) -> None:
        """Wavelength validation uses the driver's range dataclass."""
        self.instr._wavelength_range.min = 1300.0

        self._assert_rejected(self.instr.set_wavelength, (1299.0,))

    def test_channel_wavelength(self) -> None:
        """DWAV sets and DWAV? returns the wavelength of one channel of the driver's module."""
        self._assert_setter(self.instr.set_channel_wavelength, (4, 1550.0), "DWAV 2,4,1550.000")
        self._assert_rejected(self.instr.set_channel_wavelength, (1, 1700.0))
        for channel in (0, 5, True):
            with self.subTest(channel=channel):
                self._assert_rejected(self.instr.set_channel_wavelength, (channel, 1550.0))
                self._assert_rejected(self.instr.get_channel_wavelength, (channel,))

        self._assert_getter(self.instr.get_channel_wavelength, (1,), "DWAV? 2,1", "1550", 1550.0)

    def test_channels_mpm_212(self) -> None:
        """The MPM-212 module accepts only channels 1 and 2."""
        self._reopen("MPM-212")

        self._assert_getter(self.instr.get_channel_wavelength, (2,), "DWAV? 2,2", "1550", 1550.0)
        self._assert_rejected(self.instr.get_channel_wavelength, (3,))

    def test_sweep_wavelengths(self) -> None:
        """WSET sets and WSET? returns the start, stop and step wavelengths of a sweep."""
        self._assert_setter(self.instr.set_sweep_wavelengths, (1520, 1570, 0.05), "WSET 1520.000,1570.000,0.050")
        self._assert_setter(self.instr.set_sweep_wavelengths, (1520.0, 1520.5, 0.5), "WSET 1520.000,1520.500,0.500")
        invalid_args = [
            (1200.0, 1570.0, 0.05),  # Start out of range.
            (1520.0, 1700.0, 0.05),  # Stop out of range.
            (1520.0, 1570.0, 0.0001),  # Step too small.
            (1500.0, 1510.0, 20.0),  # Step too large, and would also not fit.
            (1520.0, 1520.4, 0.5),  # Stop before start + step.
            (1570.0, 1520.0, 0.05),  # Stop before start.
        ]
        for args in invalid_args:
            with self.subTest(args=args):
                self._assert_rejected(self.instr.set_sweep_wavelengths, args)

        with self.assertRaisesRegex(ValueError, "step must be in the range"):
            self.instr.set_sweep_wavelengths(1500.0, 1510.0, 20.0)

        self._assert_getter(
            self.instr.get_sweep_wavelengths, (), "WSET?", "1520,1570,0.05", (1520.0, 1570.0, 0.05)
        )
        self._assert_bad_response(self.instr.get_sweep_wavelengths, (), "1520,1570")

    def test_sweep_speed(self) -> None:
        """SPE sets and SPE? returns the sweep speed."""
        self._assert_setter(self.instr.set_sweep_speed, (0.001,), "SPE 0.001")
        self._assert_setter(self.instr.set_sweep_speed, (200,), "SPE 200.000")
        for speed in (0.0, 200.1):
            with self.subTest(speed=speed):
                self._assert_rejected(self.instr.set_sweep_speed, (speed,))

        self._assert_getter(self.instr.get_sweep_speed, (), "SPE?", "1", 1.0)

    def test_gain(self) -> None:
        """LEV sets and LEV? returns the common TIA gain, DLEV and DLEV? per channel."""
        self._assert_setter(self.instr.set_gain, (5,), "LEV 5")
        self._assert_setter(self.instr.set_channel_gain, (2, 1), "DLEV 2,2,1")
        for gain in (0, 6, True):
            with self.subTest(gain=gain):
                self._assert_rejected(self.instr.set_gain, (gain,))
                self._assert_rejected(self.instr.set_channel_gain, (1, gain))

        self._assert_rejected(self.instr.set_channel_gain, (5, 1))
        self._assert_rejected(self.instr.get_channel_gain, (5,))
        self._assert_getter(self.instr.get_gain, (), "LEV?", "3", 3)
        self._assert_getter(self.instr.get_channel_gain, (4,), "DLEV? 2,4", "2", 2)

    def test_gain_mpm_213(self) -> None:
        """The MPM-213 current meter accepts gains 1 through 4."""
        self._reopen("MPM-213")

        self._assert_setter(self.instr.set_gain, (1,), "LEV 1")
        self._assert_setter(self.instr.set_gain, (4,), "LEV 4")
        self._assert_rejected(self.instr.set_gain, (0,))
        self._assert_rejected(self.instr.set_gain, (5,))
        self._assert_rejected(self.instr.set_channel_gain, (1, 5))

    def test_gain_mpm_215(self) -> None:
        """The MPM-215 has no TIA gain setting."""
        self._reopen("MPM-215")

        self._assert_rejected(self.instr.set_gain, (1,), QMI_InstrumentException)
        self._assert_rejected(self.instr.get_gain, (), QMI_InstrumentException)
        self._assert_rejected(self.instr.set_channel_gain, (1, 1), QMI_InstrumentException)
        self._assert_rejected(self.instr.get_channel_gain, (1,), QMI_InstrumentException)

    def test_averaging_time(self) -> None:
        """AVG and FGSAVG set, and AVG? and FGSAVG? return, the averaging time in milliseconds."""
        cases = [
            (self.instr.set_averaging_time, self.instr.get_averaging_time, "AVG"),
            (
                self.instr.set_fast_gain_switching_averaging_time,
                self.instr.get_fast_gain_switching_averaging_time,
                "FGSAVG",
            ),
        ]
        for setter, getter, command in cases:
            with self.subTest(command=command):
                self._assert_setter(setter, (0.01,), f"{command} 0.01")
                self._assert_setter(setter, (10000,), f"{command} 10000.00")
                for avg_time in (0.0, 10000.01):
                    self._assert_rejected(setter, (avg_time,))

                self._assert_getter(getter, (), f"{command}?", "0.1", 0.1)

    def test_measurement_unit(self) -> None:
        """UNIT sets and UNIT? returns the measurement unit as a string."""
        self._assert_setter(self.instr.set_measurement_unit_to_milliwatts, (), "UNIT 1")
        self._assert_setter(self.instr.set_measurement_unit_to_dbm, (), "UNIT 0")
        self._assert_getter(self.instr.get_measurement_unit, (), "UNIT?", "0", "dBm")
        self._assert_getter(self.instr.get_measurement_unit, (), "UNIT?", "1", "mW")
        self._assert_bad_response(self.instr.get_measurement_unit, (), "2")

    def test_measurement_unit_mpm_213(self) -> None:
        """The MPM-213 current meter reports current units."""
        self._reopen("MPM-213")

        self._assert_getter(self.instr.get_measurement_unit, (), "UNIT?", "0", "dBmA")
        self._assert_getter(self.instr.get_measurement_unit, (), "UNIT?", "1", "mA")

    def test_power_range(self) -> None:
        """AUTO sets and AUTO? returns the common range mode, DAUTO and DAUTO? that of the module."""
        self._assert_setter(self.instr.set_power_range_to_manual, (), "AUTO 0")
        self._assert_setter(self.instr.set_power_range_to_auto, (), "AUTO 1")
        self._assert_getter(self.instr.get_auto_power_range, (), "AUTO?", "1", True)
        self._assert_getter(self.instr.get_auto_power_range, (), "AUTO?", "0", False)
        self._assert_bad_response(self.instr.get_auto_power_range, (), "-1")

        self._assert_setter(self.instr.set_module_power_range_to_manual, (), "DAUTO 2,0")
        self._assert_setter(self.instr.set_module_power_range_to_auto, (), "DAUTO 2,1")
        self._assert_getter(self.instr.get_module_auto_power_range, (), "DAUTO? 2", "1", True)
        self._assert_getter(self.instr.get_module_auto_power_range, (), "DAUTO? 2", "0", False)
        self._assert_bad_response(self.instr.get_module_auto_power_range, (), "3")

    def test_read_power(self) -> None:
        """READ? returns the power of every channel of the driver's module."""
        self._assert_getter(
            self.instr.read_power, (), "READ? 2", "-20.123,-20.454,-20.764,-20.644",
            [-20.123, -20.454, -20.764, -20.644],
        )
        self._assert_bad_response(self.instr.read_power, (), "-20.123,,-20.764,-20.644")

    def test_calibration(self) -> None:
        """CWAV? and CWAVPO? return the calibration wavelengths and per-channel offsets."""
        self._assert_getter(self.instr.get_calibration_wavelength, (1,), "CWAV? 2,1", "1250", 1250.0)
        self._assert_getter(self.instr.get_calibration_wavelength, (20,), "CWAV? 2,20", "1630", 1630.0)
        self._assert_getter(
            self.instr.get_channel_calibration_offset, (3, 20), "CWAVPO? 2,3,20", "-0.012", -0.012
        )
        self._assert_getter(self.instr.get_channel_calibration_offset, (1, 1), "CWAVPO? 2,1,1", "0.05", 0.05)
        for index in (0, 21, True):
            with self.subTest(index=index):
                self._assert_rejected(self.instr.get_calibration_wavelength, (index,))
                self._assert_rejected(self.instr.get_channel_calibration_offset, (1, index))

        self._assert_rejected(self.instr.get_channel_calibration_offset, (0, 1))

    def test_start_stop_measurement(self) -> None:
        """MEAS starts and STOP stops a logging measurement."""
        self._assert_setter(self.instr.start_measurement, (), "MEAS")
        self._assert_setter(self.instr.stop_measurement, (), "STOP")

    def test_get_measurement_status(self) -> None:
        """STAT? returns the measurement status and the number of logged points."""
        for status in (-1, 0, 1):
            with self.subTest(status=status):
                self._assert_getter(self.instr.get_measurement_status, (), "STAT?", f"{status},100", (status, 100))

        for response in ("2,100", "0", "0,100,1", "0,1e2"):
            with self.subTest(response=response):
                self._assert_bad_response(self.instr.get_measurement_status, (), response)

    def test_logging_points(self) -> None:
        """LOGN sets and LOGN? returns the number of logging points."""
        self._assert_setter(self.instr.set_logging_points, (1,), "LOGN 1")
        self._assert_setter(self.instr.set_logging_points, (1_000_000,), "LOGN 1000000")
        for points in (0, 1_000_001, 10.0, True):
            with self.subTest(points=points):
                self._assert_rejected(self.instr.set_logging_points, (points,))

        self._assert_getter(self.instr.get_logging_points, (), "LOGN?", "400000", 400_000)

    def test_get_logged_data_tcp(self) -> None:
        """TCP LOGG? data is read by its binary block header, and a trailing CR+LF is consumed."""
        payload = struct.pack("<2f", -20.5, 1.25)
        for trailer in (b"\r\n", b"\n", b""):
            with self.subTest(trailer=trailer):
                self.transport.reset_mock()
                self.transport.read.side_effect = [b"#1", b"8", payload]
                self.transport.read_until_timeout.return_value = trailer

                self.assertEqual(self.instr.get_logged_data(1), [-20.5, 1.25])

                self._assert_writes("LOGG? 2,1")
                self.assertEqual(
                    self.transport.read.call_args_list,
                    [call(2, timeout=10.0), call(1, timeout=10.0), call(8, timeout=10.0)],
                )
                self.transport.read_until_timeout.assert_called_once_with(2, timeout=0.1)

    def test_get_logged_data_tcp_invalid(self) -> None:
        """Malformed TCP LOGG? responses are rejected."""
        cases = [
            ([b"$1"], b""),  # Bad header character.
            ([b"#x"], b""),  # Non-digit length count.
            ([b"#1", b"x"], b""),  # Non-digit length.
            ([b"#1", b"6", b"\x00" * 6], b""),  # Length not a multiple of 4.
            ([b"#1", b"8", b"\x00" * 4], b""),  # Short payload.
            ([b"#1", b"4", b"\x00" * 4], b"xy"),  # Unexpected data after the payload.
        ]
        for reads, trailer in cases:
            with self.subTest(reads=reads, trailer=trailer):
                self.transport.read.side_effect = reads
                self.transport.read_until_timeout.return_value = trailer

                with self.assertRaises(QMI_InstrumentException):
                    self.instr.get_logged_data(1)

    def test_get_logged_data_gpib(self) -> None:
        """GPIB LOGG? data is one EOI-delimited message, optionally followed by CR+LF."""
        self._reopen("MPM-211", GPIB_TRANSPORT)
        payload = struct.pack("<3f", 1.0, 2.0, 3.0) + b"\x0a\x00\x00\x00"
        for trailer in (b"", b"\r\n"):
            with self.subTest(trailer=trailer):
                self.transport.reset_mock()
                self.transport.read_until.side_effect = None
                self.transport.read_until.return_value = b"#216" + payload + trailer

                values = self.instr.get_logged_data(4)

                self.assertEqual(values, [1.0, 2.0, 3.0, struct.unpack("<f", b"\x0a\x00\x00\x00")[0]])
                self._assert_writes("LOGG? 2,4", terminator="")
                self.transport.read_until.assert_called_once_with(b"", timeout=10.0)

    def test_get_logged_data_gpib_invalid(self) -> None:
        """Malformed or missing GPIB LOGG? responses are rejected."""
        self._reopen("MPM-211", GPIB_TRANSPORT)
        self.transport.read_until.side_effect = None
        invalid_responses = (
            b"#", b"#18\x00\x00\x00\x00", b"#14\x00\x00\x00\x00xy", b"#14\x00\x00\x00\x00x", b"#2x4\x00\x00\x00\x00"
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                self.transport.read_until.return_value = response

                with self.assertRaises(QMI_InstrumentException):
                    self.instr.get_logged_data(1)

        self.transport.read_until.return_value = b""
        with self.assertRaises(QMI_TimeoutException):
            self.instr.get_logged_data(1)

    def test_get_logged_data_rejects_serial_and_invalid_channel(self) -> None:
        """LOGG? is not available on RS-232, and the channel is validated."""
        self._assert_rejected(self.instr.get_logged_data, (0,))
        self._reopen("MPM-211", SERIAL_TRANSPORT)
        self._assert_rejected(self.instr.get_logged_data, (1,), QMI_InstrumentException)

    def test_zero(self) -> None:
        """ZERO is sent and the driver waits for the zeroing to complete."""
        self._respond(NO_ERROR)

        self.instr.zero()

        self._assert_writes("ZERO", "ERR?")
        self.assertEqual(self.sleep.call_args_list[-1], call(3))


if __name__ == "__main__":
    unittest.main()
