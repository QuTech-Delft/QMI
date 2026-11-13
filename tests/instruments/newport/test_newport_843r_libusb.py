"""Unit-tests for the Newport 843-R low-level USB access module."""

import logging
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from qmi.instruments.newport.newport_843r_libusb import Newport_843R_libusb

MODULE = "qmi.instruments.newport.newport_843r_libusb"
SERIAL_NUMBER = "SN12345"


class TestNewport843RLibusb(unittest.TestCase):
    """Testcase for the Newport_843R_libusb class."""

    def setUp(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.getLogger(MODULE).setLevel(logging.NOTSET)

    @staticmethod
    def _make_mock_device(serial_number: str = SERIAL_NUMBER, kernel_driver_active: bool = False) -> MagicMock:
        dev = MagicMock()
        dev.serial_number = serial_number
        dev.is_kernel_driver_active.return_value = kernel_driver_active
        return dev

    def _make_instrument(self, dev: MagicMock, serial_number: str | None = SERIAL_NUMBER) -> Newport_843R_libusb:
        with patch(f"{MODULE}.usb.core.find", return_value=[dev]), \
             patch(f"{MODULE}.usb.util.claim_interface"):
            return Newport_843R_libusb(serial_number)

    def test_init_with_matching_serial_number(self):
        """Newport_843R_libusb.__init__(), happy flow with matching serial number"""
        dev = self._make_mock_device()
        with patch(f"{MODULE}.usb.core.find", return_value=[dev]), \
             patch(f"{MODULE}.usb.util.claim_interface") as mock_claim:
            instr = Newport_843R_libusb(SERIAL_NUMBER)

        self.assertIs(instr._dev, dev)
        dev.is_kernel_driver_active.assert_called_once_with(Newport_843R_libusb.INTERFACE)
        dev.detach_kernel_driver.assert_not_called()
        dev.set_configuration.assert_called_once_with()
        mock_claim.assert_called_once_with(dev, Newport_843R_libusb.INTERFACE)

    def test_init_detaches_active_kernel_driver(self):
        """Newport_843R_libusb.__init__(), detaches an active kernel driver"""
        dev = self._make_mock_device(kernel_driver_active=True)
        self._make_instrument(dev)
        dev.detach_kernel_driver.assert_called_once_with(Newport_843R_libusb.INTERFACE)

    def test_init_with_no_serial_number_selects_single_device(self):
        """Newport_843R_libusb.__init__(None), selects the single attached device"""
        dev = MagicMock()
        type(dev).serial_number = PropertyMock(side_effect=AssertionError("serial_number should not be read"))
        dev.is_kernel_driver_active.return_value = False

        instr = self._make_instrument(dev, serial_number=None)

        self.assertIs(instr._dev, dev)

    def test_init_no_matching_device_raises(self):
        """Newport_843R_libusb.__init__(), no matching device raises LookupError"""
        dev = self._make_mock_device(serial_number="OTHER")
        with patch(f"{MODULE}.usb.core.find", return_value=[dev]):
            with self.assertRaises(LookupError) as ctx:
                Newport_843R_libusb(SERIAL_NUMBER)

        self.assertIn(SERIAL_NUMBER, str(ctx.exception))

    def test_init_multiple_matching_devices_raises(self):
        """Newport_843R_libusb.__init__(), multiple matching devices raises LookupError"""
        dev1 = self._make_mock_device()
        dev2 = self._make_mock_device()
        with patch(f"{MODULE}.usb.core.find", return_value=[dev1, dev2]):
            with self.assertRaises(LookupError):
                Newport_843R_libusb(SERIAL_NUMBER)

    def test_init_serial_number_read_error_is_skipped(self):
        """Newport_843R_libusb.__init__(), devices with unreadable serial numbers are skipped"""
        dev_broken = MagicMock()
        type(dev_broken).serial_number = PropertyMock(side_effect=Exception("no permission"))
        dev_ok = self._make_mock_device()
        with patch(f"{MODULE}.usb.core.find", return_value=[dev_broken, dev_ok]), \
             patch(f"{MODULE}.usb.util.claim_interface"):
            instr = Newport_843R_libusb(SERIAL_NUMBER)

        self.assertIs(instr._dev, dev_ok)

    def test_list_instruments(self):
        """Newport_843R_libusb.list_instruments(), happy flow"""
        dev1 = self._make_mock_device(serial_number="SN1")
        dev2 = self._make_mock_device(serial_number="SN2")
        with patch(f"{MODULE}.usb.core.find", return_value=[dev1, dev2]) as mock_find:
            result = Newport_843R_libusb.list_instruments()

        mock_find.assert_called_once_with(
            find_all=True, idVendor=Newport_843R_libusb.VENDOR_ID, idProduct=Newport_843R_libusb.PRODUCT_ID
        )
        self.assertEqual(result, ["SN1", "SN2"])

    def test_list_instruments_skips_unreadable_serial(self):
        """Newport_843R_libusb.list_instruments(), devices with unreadable serial numbers are skipped"""
        dev_broken = MagicMock()
        type(dev_broken).serial_number = PropertyMock(side_effect=Exception("no permission"))
        dev_ok = self._make_mock_device(serial_number="SN1")
        with patch(f"{MODULE}.usb.core.find", return_value=[dev_broken, dev_ok]):
            result = Newport_843R_libusb.list_instruments()

        self.assertEqual(result, ["SN1"])

    def test_close(self):
        """Newport_843R_libusb.close(), happy flow"""
        dev = self._make_mock_device()
        instr = self._make_instrument(dev)

        with patch(f"{MODULE}.usb.util.dispose_resources") as mock_dispose:
            instr.close()

        mock_dispose.assert_called_once_with(dev)
        self.assertIsNone(instr._dev)

    def test_send_command(self):
        """Newport_843R_libusb.send_command(), happy flow"""
        dev = self._make_mock_device()
        instr = self._make_instrument(dev)

        instr.send_command(b"$RE\r\n", timeout=2.0)

        dev.ctrl_transfer.assert_called_once_with(0x40, 2, 0, 0, b"$RE\r\n", 2001)

    def test_read_response(self):
        """Newport_843R_libusb.read_response(), happy flow"""
        dev = self._make_mock_device()
        instr = self._make_instrument(dev)
        mock_data = MagicMock()
        mock_data.tobytes.return_value = b"*OK\n"
        dev.ctrl_transfer.return_value = mock_data

        result = instr.read_response(timeout=1.5)

        dev.ctrl_transfer.assert_called_once_with(0xc0, 4, 0, 0, 2000, 1501)
        self.assertEqual(result, b"*OK\n")
