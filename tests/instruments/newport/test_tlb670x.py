"""Unit test for Newport/NewFocus TLB670-X."""
import logging
import unittest
from unittest.mock import patch, Mock

from qmi.core.exceptions import QMI_InstrumentException
from qmi.instruments.newport.tlb670x import NewFocus_TLB670X


class CtypesMock:
    """Mock ctypes library.

    User create_string_buffer() and byref() as follows:
    1. push a StringBuffer object to the string_buffer attribute
    2. create_string_buffer() pops from the same attribute
    3. byref() adds it argument on the ref_objs attribute: this should be the same object that you added in step 1; the
       id() of that object is returned by byref() so you can check for that in the call arguments of the dllmock calls.
    """
    class StringBuffer:
        def __init__(self, value: str):
            self.value = value.encode("ascii")

        def __repr__(self):
            return "StringBuffer(id={}, value={})".format(hex(id(self)), self.value.decode())

    class IntValue:
        def __init__(self, value):
            self.value = value

        def __repr__(self):
            return "IntValue(id={}, value={})".format(hex(id(self)), self.value)

    def __init__(self):
        self.dllmock = Mock()
        self.ref_objs = []
        self.string_buffer = []

    def WinDLL(self, _):
        return self.dllmock

    def byref(self, obj):
        self.ref_objs.append(obj)
        return id(obj)

    def create_string_buffer(self, _):
        return self.string_buffer.pop(0)

    def c_ulong(self, value):
        return self.IntValue(value)


class TestTLB670XPlatform(unittest.TestCase):
    def setUp(self):
        patcher = patch("qmi.instruments.newport.tlb670x.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.configure_mock(platform="linux")
        self.addCleanup(patcher.stop)

        self.ctypes_mock = CtypesMock()
        patcher = patch("qmi.instruments.newport.tlb670x.ctypes", self.ctypes_mock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_platform_support(self):
        """Test platform support (Windows only)."""
        with self.assertRaises(RuntimeError):
            NewFocus_TLB670X(Mock(), "tlb670x", "anything")


class TestTLB670XInit(unittest.TestCase):
    def setUp(self):
        patcher = patch("qmi.instruments.newport.tlb670x.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.platform = "win"
        self.addCleanup(patcher.stop)

        self.ctypes_mock = CtypesMock()
        patcher = patch("qmi.instruments.newport.tlb670x.ctypes", self.ctypes_mock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        logging.getLogger("qmi.instruments.newport.tlb670x").setLevel(logging.NOTSET)

    def test_init_nominal(self):
        """Test nominal initialization."""
        serial_number = "SN1234"
        device_id = 123
        device_info_response = CtypesMock.StringBuffer(f"1,SNxxxx;2,SNyyyy;{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        instr = NewFocus_TLB670X(Mock(), "tlb670x", serial_number)
        instr.open()

        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once_with(id(device_info_response))
        self.assertEqual(self.ctypes_mock.ref_objs.pop(), device_info_response)
        self.assertEqual(instr.get_device_id(), device_id)
        self.assertEqual(instr.get_ident().serial, serial_number)

    def test_init_with_numeric_serialno(self):
        """Test with numeric serial number."""
        logging.getLogger("qmi.instruments.newport.tlb670x").setLevel(logging.CRITICAL)

        serial_number = "SN1234"
        device_id = 123
        device_info_response = CtypesMock.StringBuffer(f"1,SNxxxx;2,SNyyyy;{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        instr = NewFocus_TLB670X(Mock(), "tlb670x", 1234)
        instr.open()

        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once_with(id(device_info_response))
        self.assertEqual(self.ctypes_mock.ref_objs.pop(), device_info_response)
        self.assertEqual(instr.get_device_id(), device_id)
        self.assertEqual(instr.get_ident().serial, serial_number)

    def test_init_with_serialno_no_prefix(self):
        """Test with serial number without SN prefix."""
        logging.getLogger("qmi.instruments.newport.tlb670x").setLevel(logging.CRITICAL)

        serial_number = "SN1234"
        device_id = 123
        device_info_response = CtypesMock.StringBuffer(f"1,SNxxxx;2,SNyyyy;{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        instr = NewFocus_TLB670X(Mock(), "tlb670x", "1234")
        instr.open()

        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once_with(id(device_info_response))
        self.assertEqual(self.ctypes_mock.ref_objs.pop(), device_info_response)
        self.assertEqual(instr.get_device_id(), device_id)
        self.assertEqual(instr.get_ident().serial, serial_number)

    def test_init_device_not_found(self):
        """Test no device present."""
        serial_number = "SN1234"
        device_info_response = CtypesMock.StringBuffer("1,SNxxxx;2,SNyyyy;")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        instr = NewFocus_TLB670X(Mock(), "tlb670x", serial_number)
        with self.assertRaises(QMI_InstrumentException):
            instr.open()

        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once_with(id(device_info_response))
        self.ctypes_mock.dllmock.newp_usb_uninit_system.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs.pop(), device_info_response)

    def test_init_no_devices(self):
        """Test no device present."""
        serial_number = "SN1234"
        device_info_response = CtypesMock.StringBuffer("")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        instr = NewFocus_TLB670X(Mock(), "tlb670x", serial_number)
        with self.assertRaises(QMI_InstrumentException):
            instr.open()

        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once_with(id(device_info_response))
        self.ctypes_mock.dllmock.newp_usb_uninit_system.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs.pop(), device_info_response)

    def test_init_deinit(self):
        """Test init/deinit."""
        serial_number = "SN1234"
        device_id = 123
        device_info_response = CtypesMock.StringBuffer(f"1,SNxxxx;2,SNyyyy;{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        instr = NewFocus_TLB670X(Mock(), "tlb670x", serial_number)
        instr.open()
        instr.close()

        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once_with(id(device_info_response))
        self.ctypes_mock.dllmock.newp_usb_uninit_system.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs.pop(), device_info_response)


class TestTLB670XTxRx(unittest.TestCase):
    def setUp(self):
        patcher = patch("qmi.instruments.newport.tlb670x.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.platform = "win"
        self.addCleanup(patcher.stop)

        self.ctypes_mock = CtypesMock()
        patcher = patch("qmi.instruments.newport.tlb670x.ctypes", self.ctypes_mock)
        patcher.start()
        self.addCleanup(patcher.stop)

        serial_number = "SN1234"
        device_id = 123
        device_info_response = CtypesMock.StringBuffer(f"{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        self.instr = NewFocus_TLB670X(Mock(), "tlb670x", serial_number)
        self.instr.open()

        self.ctypes_mock.ref_objs.pop(0)  # call to get_device_info
        self.ctypes_mock.dllmock.reset_mock()

    def tearDown(self):
        logging.getLogger("qmi.instruments.newport.tlb670x").setLevel(logging.NOTSET)

    def test_txrx_nominal(self):
        """Test nominal send/receive sequence."""
        command = CtypesMock.StringBuffer("")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        error_str = "my_error_string"
        error_str_response = CtypesMock.StringBuffer(error_str)
        self.ctypes_mock.string_buffer.append(error_str_response)
        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0  # success
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        self.instr.check_error_status()

        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs[0].value, "ERRSTR?".encode("ascii"))  # query
        self.assertEqual(self.ctypes_mock.ref_objs[1].value, error_str.encode("ascii"))  # response

    def test_tx_fail(self):
        """Test failure in send sequence."""
        logging.getLogger("qmi.instruments.newport.tlb670x").setLevel(logging.CRITICAL)

        expected_error = "Command ERRSTR? returned an error -2: COMMAND NOT VALID"
        # Setup for _send
        command = CtypesMock.StringBuffer("")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        error_code = -2  # COMMAND NOT VALID
        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = error_code

        # Setup for reinit (automatic after fail in send)
        device_info_response = CtypesMock.StringBuffer("123,SN1234")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.check_error_status()
            self.assertEqual(expected_error, str(exc.exception))

        # Check send/receive sequence
        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_not_called()
        self.assertEqual(self.ctypes_mock.ref_objs[0].value, "ERRSTR?".encode("ascii"))  # query

        # Check for reinit
        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_uninit_system.assert_called_once()

    def test_rx_fail(self):
        """Test failure in receive sequence."""
        logging.getLogger("qmi.instruments.newport.tlb670x").setLevel(logging.CRITICAL)

        # Setup for _send
        command = CtypesMock.StringBuffer("")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0

        # Setup for _receive
        error_code = -2  # COMMAND NOT VALID
        error_str = "my_error_string"
        error_str_response = CtypesMock.StringBuffer(error_str)
        self.ctypes_mock.string_buffer.append(error_str_response)  # need to add for call to get_ascii
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = error_code

        # Setup for reinit (automatic after fail in receive)
        device_info_response = CtypesMock.StringBuffer("123,SN1234")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        with self.assertRaises(QMI_InstrumentException):
            self.instr.check_error_status()

        # Check send/receive sequence
        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs[0].value, "ERRSTR?".encode("ascii"))  # query

        # Check for reinit
        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_uninit_system.assert_called_once()

    def test_reset(self):
        """Test 'reset' RPC call."""
        self.instr.RESET_SLEEP_TIME = 0.01
        error_str = "NO ERROR"
        command = CtypesMock.StringBuffer("ERRSTR?")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        error_str_response = CtypesMock.StringBuffer(error_str)
        self.ctypes_mock.string_buffer.append(error_str_response)
        command = CtypesMock.StringBuffer("*RST")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        ok_response = CtypesMock.StringBuffer("OK\r\n")
        self.ctypes_mock.string_buffer.append(ok_response)
        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0  # success
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        self.instr.reset()

        self.assertEqual(2, self.ctypes_mock.dllmock.newp_usb_send_ascii.call_count)
        self.assertEqual(2, self.ctypes_mock.dllmock.newp_usb_get_ascii.call_count)

    def test_reset_excepts(self):
        """Test 'reset' RPC call with raising QMI_InstrumentException."""
        self.instr.RESET_SLEEP_TIME = 0.01
        error_str = "NO ERROR"
        command = CtypesMock.StringBuffer("ERRSTR?")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        error_str_response = CtypesMock.StringBuffer(error_str)
        self.ctypes_mock.string_buffer.append(error_str_response)
        command = CtypesMock.StringBuffer("*RST")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        serial_number = "SN1234"
        device_id = 12
        device_info_response = CtypesMock.StringBuffer(f"{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_send_ascii.side_effect = [0, 116]
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        with self.assertRaises(QMI_InstrumentException):
            self.instr.reset()

        self.ctypes_mock.dllmock.newp_usb_uninit_system.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_init_product.assert_called_once_with(NewFocus_TLB670X.PRODUCT_ID)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_called_once()
        self.assertEqual(2, self.ctypes_mock.dllmock.newp_usb_send_ascii.call_count)


class TestTLB670XGetSet(unittest.TestCase):
    def setUp(self):
        patcher = patch("qmi.instruments.newport.tlb670x.sys")
        self.sys_mock = patcher.start()
        self.sys_mock.platform = "win"
        self.addCleanup(patcher.stop)

        self.ctypes_mock = CtypesMock()
        patcher = patch("qmi.instruments.newport.tlb670x.ctypes", self.ctypes_mock)
        patcher.start()
        self.addCleanup(patcher.stop)

        serial_number = "SN1234"
        self.device_id = 12
        device_info_response = CtypesMock.StringBuffer(f"{self.device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        self.instr = NewFocus_TLB670X(Mock(), "tlb670x", serial_number)
        self.instr.open()

        self.ctypes_mock.ref_objs.pop(0)  # call to get_device_info
        self.ctypes_mock.dllmock.reset_mock()

    def _generic_get_test(self, query, expected_value, getter):
        """Helper function for testing getters."""
        # Setup send/receive
        command = CtypesMock.StringBuffer("")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        value_str = str(expected_value) + "\r\n"
        response = CtypesMock.StringBuffer(value_str)
        self.ctypes_mock.string_buffer.append(response)
        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0  # success
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        return_value = getter()

        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs[0].value, query.encode("ascii"))  # query
        self.assertEqual(self.ctypes_mock.ref_objs[1].value, value_str.encode("ascii"))  # response
        self.assertEqual(return_value, expected_value)

    def _generic_get_test_with_extra_OKs(self, query, expected_value, getter, extra_oks=1, after_oks=0, second_read=""):
        """Helper function for testing getters, return extra "OK" before correct answer."""
        # Setup send/receive
        command = CtypesMock.StringBuffer("4\r\n;4\r\n")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        extra_oks_string = ""
        for _ in range(extra_oks):
            extra_oks_string += "OK\r\n"

        after_oks_string = ""
        for _ in range(after_oks):
            after_oks_string += "OK\r\n"

        value_str = extra_oks_string + str(expected_value) + "\r\n" + after_oks_string
        response = CtypesMock.StringBuffer(value_str)
        self.ctypes_mock.string_buffer.append(response)
        if second_read:
            self.ctypes_mock.string_buffer.append(CtypesMock.StringBuffer(second_read))

        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0  # success
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        return_value = getter()

        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        if second_read:
            self.assertEqual(2, self.ctypes_mock.dllmock.newp_usb_get_ascii.call_count)
        else:
            self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_called_once()

        self.assertEqual(self.ctypes_mock.ref_objs[0].value, query.encode("ascii"))  # query
        self.assertEqual(self.ctypes_mock.ref_objs[1].value, value_str.encode("ascii"))  # response
        self.assertEqual(return_value, expected_value)

    def _generic_get_test_with_extra_IDN(self, query, expected_value, getter):
        """Helper function for testing getters, return extra "IDN" after correct answer."""
        # Setup send/receive
        command = CtypesMock.StringBuffer("")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        extra_idn_string = "cus TLB-6700 v2.4 31/09/23 SN12345\r\n"

        value_str = str(expected_value) + "\r\n" + extra_idn_string
        response = CtypesMock.StringBuffer(value_str)
        self.ctypes_mock.string_buffer.append(response)

        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0  # success
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        return_value = getter()

        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs[0].value, query.encode("ascii"))  # query
        self.assertEqual(self.ctypes_mock.ref_objs[1].value, value_str.encode("ascii"))  # response
        self.assertEqual(return_value, expected_value)

    def _generic_set_test(self, cmd_str, setpoint_value, setter):
        """Helper function for testing getters."""
        # Setup send/receive
        command = CtypesMock.StringBuffer("")  # to be set by _send
        self.ctypes_mock.string_buffer.append(command)
        response = CtypesMock.StringBuffer("OK\r\n")
        self.ctypes_mock.string_buffer.append(response)
        self.ctypes_mock.dllmock.newp_usb_send_ascii.return_value = 0  # success
        self.ctypes_mock.dllmock.newp_usb_get_ascii.return_value = 0  # success

        setter(setpoint_value)

        self.ctypes_mock.dllmock.newp_usb_send_ascii.assert_called_once()
        self.ctypes_mock.dllmock.newp_usb_get_ascii.assert_called_once()
        self.assertEqual(self.ctypes_mock.ref_objs[0].value, cmd_str.format(setpoint_value).encode("ascii"))  # command

    def test_get_available_devices_info(self):
        """Test getting available device info."""
        serial_number = "SN1234"
        device_id = 12
        expected_info = [(device_id, serial_number)]
        device_info_response = CtypesMock.StringBuffer(f"{device_id},{serial_number};")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = 0  # success

        info = self.instr.get_available_devices_info()

        self.assertListEqual(expected_info, info)

    def test_get_available_devices_info_excepts(self):
        """Test the exception case for getting devices info excepts at re-init."""
        expected_exception = "Unable to load device info: Unknown error"
        device_info_response = CtypesMock.StringBuffer("None,None;")
        self.ctypes_mock.string_buffer.append(device_info_response)
        device_info_response_reinit = CtypesMock.StringBuffer(f"{self.device_id},SOMESN;")
        self.ctypes_mock.string_buffer.append(device_info_response_reinit)
        self.ctypes_mock.dllmock.newp_usb_get_device_info.return_value = -1  # Some failure

        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.get_available_devices_info()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_get_available_devices_info_excepts_reinit(self):
        """Test the exception case for getting devices info excepts at re-init."""
        expected_exception = "No TLB-670X instrument present"
        device_info_response = CtypesMock.StringBuffer("None,None;")
        self.ctypes_mock.string_buffer.append(device_info_response)
        self.ctypes_mock.string_buffer.append(CtypesMock.StringBuffer(""))
        self.ctypes_mock.dllmock.newp_usb_get_device_info.side_effect = [-1, 0]  # Some failure, then ok

        with self.assertRaises(QMI_InstrumentException) as exc:
            self.instr.get_available_devices_info()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_get_wavelength(self):
        """Test get wavelength."""
        self._generic_get_test("SOURce:WAVElength?", 123.456, self.instr.get_wavelength)

    def test_get_powermode(self):
        """Test get powermode."""
        self._generic_get_test("OUTPut:STATe?", 1, self.instr.get_powermode)

    def test_get_trackingmode(self):
        """Test get trackingmode."""
        self._generic_get_test("OUTPut:TRACk?", 0, self.instr.get_trackingmode)

    def test_get_diode_current(self):
        """Test get diode current."""
        self._generic_get_test("SENSe:CURRent:DIODe", 456.789, self.instr.get_diode_current)

    def test_get_piezo_voltage(self):
        """Test get piezo voltage."""
        self._generic_get_test("SOURce:VOLTage:PIEZo?", 99.99, self.instr.get_piezo_voltage)

    def test_get_piezo_voltage_ok(self):
        """Test get piezo voltage with one extra "OK" returned first."""
        self._generic_get_test_with_extra_OKs("SOURce:VOLTage:PIEZo?", 99.99, self.instr.get_piezo_voltage)

    def test_get_piezo_voltage_idn(self):
        """Test get piezo voltage with one extra *IDN response returned after query."""
        self._generic_get_test_with_extra_IDN("SOURce:VOLTage:PIEZo?", 99.99, self.instr.get_piezo_voltage)

    def test_get_piezo_voltage_ok_nok(self):
        """Test get piezo voltage with two extra "OK"s returned first. This result in """
        self._generic_get_test_with_extra_OKs("SOURce:VOLTage:PIEZo?", 99.99, self.instr.get_piezo_voltage, 2)

    def test_get_piezo_voltage_nok(self):
        """Test get piezo voltage fails if after the expected value there is one "OK" more AFTER the response.
        In this case, as there is one OK
        """
        self._generic_get_test_with_extra_OKs(
                "SOURce:VOLTage:PIEZo?", 99.99, self.instr.get_piezo_voltage, 0, 1
            )

    def test_get_piezo_voltage_2nd_read_ok(self):
        """Test get piezo voltage fails if after the expected value there is one "OK" more AFTER the response.
        This case fails because response[1] is also "OK", prompting a re-read which then succeeds."""
        self._generic_get_test_with_extra_OKs(
                "SOURce:VOLTage:PIEZo?", 99.99, self.instr.get_piezo_voltage, 1, 1, "99.99\r\n"
            )

    def test_set_wavelength(self):
        """Test set wavelength."""
        self._generic_set_test("SOURce:WAVElength {}", 1.234, self.instr.set_wavelength)

        with self.assertRaises(ValueError):
            self.instr.set_wavelength(-1.0)

    def test_set_powermode(self):
        """Test set powermode."""
        self._generic_set_test("OUTPut:STATe {}", 0, self.instr.set_powermode)

        with self.assertRaises(ValueError):
            self.instr.set_powermode(-1)

        with self.assertRaises(ValueError):
            self.instr.set_powermode(2)

    def test_set_trackingmode(self):
        """Test set trackingmode."""
        self._generic_set_test("OUTPut:TRACk {}", 0, self.instr.set_trackingmode)

        with self.assertRaises(ValueError):
            self.instr.set_trackingmode(-1)

        with self.assertRaises(ValueError):
            self.instr.set_trackingmode(2)

    def test_set_diode_current_float(self):
        """Test set diode current."""
        self._generic_set_test("SOURce:CURRent:DIODe {}", 123.45, self.instr.set_diode_current)

        with self.assertRaises(ValueError):
            self.instr.set_diode_current(-1.234)

    def test_set_diode_current_int(self):
        """Test set diode current."""
        self._generic_set_test("SOURce:CURRent:DIODe {}", 123, self.instr.set_diode_current)

        with self.assertRaises(ValueError):
            self.instr.set_diode_current(-123)

    def test_set_diode_current_str(self):
        """Test set diode current."""
        self._generic_set_test("SOURce:CURRent:DIODe {}", "MAX", self.instr.set_diode_current)

        with self.assertRaises(ValueError):
            self.instr.set_diode_current("MIN")

    def test_set_piezo_voltage(self):
        """Test set diode current."""
        self._generic_set_test("SOURce:VOLTage:PIEZo {}", 99.99, self.instr.set_piezo_voltage)

        with self.assertRaises(ValueError):
            self.instr.set_piezo_voltage(-1.00)

        with self.assertRaises(ValueError):
            self.instr.set_piezo_voltage(101.00)


if __name__ == '__main__':
    unittest.main()
