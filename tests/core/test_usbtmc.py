import unittest
import sys
import unittest.mock

import usb.core

sys.modules["usb.core"] = usb_core_mock = unittest.mock.Mock()
sys.modules["usb.util"] = usb_util_mock = unittest.mock.Mock()
sys.modules["usb"] = usb_mock = unittest.mock.MagicMock()

import numpy

# Import everything from usbtmc.py because there are a lot of constants
from qmi.core.usbtmc import *
usb.core = usb_core_mock
usb.util = usb_util_mock


class ExcInfoMock(BaseException):
    errno = 110


# Mock specifically the USBError
usb.core.USBError = ExcInfoMock


class MockEndPoint(unittest.mock.Mock):
    bEndpointAddress = 0x0
    bmAttributes = ["bulk_in", "bulk_out", "intr_in", "intr_out"]

    def __init__(self, response="", ep=None):
        super().__init__(spec=MockEndPoint)
        self.response = response
        self.ep = ep

        self.write = unittest.mock.Mock()
        self.clear_halt = unittest.mock.Mock()

    def read(self, transfer_size, timeout=0):
        return self.response


class MockIFace:
    bInterfaceClass = USBTMC_bInterfaceClass
    bInterfaceSubClass = USBTMC_bInterfaceSubClass
    bInterfaceProtocol = None
    bInterfaceNumber = 1
    index = 2

    def __iter__(self):
        return iter([MockEndPoint(), MockEndPoint(), MockEndPoint(), MockEndPoint()])


class MockInvalidEpIFace:
    bInterfaceClass = USBTMC_bInterfaceClass
    bInterfaceSubClass = USBTMC_bInterfaceSubClass
    bInterfaceProtocol = None
    bInterfaceNumber = 1
    index = 2

    def __iter__(self):
        return iter([None] * 4)


class MockAdvantestIFace:
    bInterfaceClass = None
    bInterfaceSubClass = None
    bInterfaceProtocol = None
    bInterfaceNumber = 1
    index = 2

    def __iter__(self):
        return iter([MockEndPoint(), MockEndPoint(), MockEndPoint(), MockEndPoint()])


class MockCfg:
    bConfigurationValue = 0

    def __init__(self, idVendor, error=False):
        self.idVendor = idVendor
        self.error = error

    def __iter__(self):
        if self.error:
            return iter([MockInvalidEpIFace()])

        if self.idVendor == 0x0957:
            # Default Agilent case
            return iter([MockIFace()])

        elif self.idVendor == 0x1334:
            # Advantest instrument
            return iter([MockAdvantestIFace()])

        elif self.idVendor == 0x1ab1:
            # Rigol instrument
            return iter([MockIFace()])

        elif self.idVendor == 0x1313:
            # Thorlabs device
            return iter([MockIFace()])

        else:
            return iter([MockAdvantestIFace()])


class MockUsbtmcInstrument:
    """Mock class for an USBTMC instrument. Default values are for Agilent U2701A/U2702A device"""
    def __init__(self, vendor=0x0957, product=0x2818, **kwargs):
        self.error = False
        self.idVendor = vendor
        self.idProduct = product
        if "serial" in kwargs:
            self.serial_number = kwargs["serial"]

        if "error" in kwargs:
            self.error = True

    def __iter__(self):
        return iter([MockCfg(self.idVendor, self.error)])

    def set_configuration(self, cfg):
        return

    def is_kernel_driver_active(self, interface_number):
        return True

    def detach_kernel_driver(self, interface_number):
        return


class UsbtmcExceptionTestCase(unittest.TestCase):
    """Test the UsbtmcException class."""

    def test_error_is_none(self):
        """Test creation of exception classes with error as 'None'."""
        expected_note = "A note"

        exc1 = UsbtmcException()
        exc2 = UsbtmcException(note=expected_note)

        self.assertIsNone(exc1.err)
        self.assertIsNone(exc1.msg)
        # As "msg" is now set as 'None', trying to turn it into a string fails
        with self.assertRaises(TypeError):
            str(exc1)

        self.assertIsNone(exc2.err)
        self.assertEqual(expected_note, str(exc2))

    def test_error_is_int(self):
        """Test creation of exception classes with error being an int."""
        expected_string_1 = "0: No error"
        expected_string_2 = "1: Unknown error"
        # No error case
        exc1 = UsbtmcException(err=0)
        # Unknown error case
        exc2 = UsbtmcException(err=1)

        self.assertEqual(expected_string_1, str(exc1))
        self.assertEqual(expected_string_2, str(exc2))

    def test_error_other_cases(self):
        """Test creation of exception classes with error not being 'None' nor int, and with a note"""
        error = "I'm an error!"
        note = "NOTE: a fake one"
        expected_string_1 = error
        expected_string_2 = error + " [" + note + "]"
        # Note is 'None' case
        exc1 = UsbtmcException(err=error)
        # Note is given case
        exc2 = UsbtmcException(err=error, note=note)

        self.assertEqual(expected_string_1, str(exc1))
        self.assertEqual(expected_string_2, str(exc2))


class InstrumentTestCase(unittest.TestCase):
    """Test Instrument class. The class takes *args and **kwargs as inputs. The relevant parts for testing are:
    - *args[n], n = :
        - 0 : if the only arg, and str: resource, else self.device. If two or more args, self.idVendor
        - 1 : With two or more args: self.idProduct
        - 2 : With three or more args: self.iSerial
    - **kwargs:
        - "idVendor": self.idVendor
        - "idProduct": self.idProduct
        - "iSerial": self.iSerial
        - "device" or "dev": self.device
        - "term_char": self.term_char
        - "resource" = resource  # NOTE: not a class attribute! Should be a VISA resource string.
    - property:
        - timeout = 5.0
        - the setter sets also self._timeout_ms = int(val * 1000)
    """
    def test_create_agilent_object(self):
        """Create a mock Agilent device object"""
        mock_instr = MockUsbtmcInstrument(serial="90")
        usb_core_mock.find = lambda find_all, custom_match: [mock_instr]
        # Finding Mock default instrument - Agilent U2701A/U2702A
        default_vendor = mock_instr.idVendor
        default_product = mock_instr.idProduct
        default_sn = mock_instr.serial_number

        dev = Instrument(default_vendor, default_product, default_sn)
        self.assertIsNotNone(dev)
        self.assertEqual(dev.idVendor, int(default_vendor))
        self.assertEqual(dev.idProduct, int(default_product))
        self.assertEqual(dev.iSerial, default_sn)

    def test_create_advantest_object(self):
        """Create a mock Advantest device object"""
        mock_instr = MockUsbtmcInstrument(0x1334, 0)
        usb_core_mock.find = lambda find_all, custom_match: [mock_instr]
        vendor = mock_instr.idVendor

        dev = Instrument(vendor, 0)
        self.assertIsNotNone(dev)
        self.assertEqual(dev.idVendor, int(vendor))

    def test_create_device(self):
        """Create a device with single argument input"""
        expected_timeout = 5.0
        device = 0x1234
        dev = Instrument(device)

        self.assertIsNotNone(dev)
        self.assertEqual(device, dev.device)
        self.assertEqual(expected_timeout, dev.timeout)
        self.assertEqual(expected_timeout, dev.abort_timeout)
        self.assertEqual(int(expected_timeout * 1000), dev._timeout_ms)

    def test_create_device_using_keywords(self):
        """Create a device using keyword arguments."""
        dev = Instrument(device="device", term_char="\x00")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.device, "device")
        self.assertEqual(dev.term_char, "\x00")

        dev2 = Instrument(dev="dev", term_char="\xFF")
        self.assertEqual(dev2.device, "dev")
        self.assertEqual(dev2.term_char, "\xFF")

    def test_create_resource(self):
        """Create a VISA resource with single argument input"""
        vendor = 0x1234
        product = 0x5678
        resource = f"USB::{vendor}::{product}::INSTR"
        mock_instr = MockUsbtmcInstrument(vendor, product)
        usb_core_mock.find = lambda find_all, custom_match: [mock_instr]
        dev = Instrument(resource)

        self.assertIsNotNone(dev)
        self.assertEqual(dev.idVendor, int(vendor))
        self.assertEqual(dev.idProduct, int(product))
        self.assertIsNone(dev.iSerial)

    def test_create_resource_with_sn(self):
        """Create a VISA resource with SN with single argument input"""
        vendor = 0x1234
        product = 0x5678
        sn = "90"
        resource = f"USB::{vendor}::{product}::{sn}::INSTR"
        mock_instr = MockUsbtmcInstrument(vendor, product, serial=sn)
        usb_core_mock.find = lambda find_all, custom_match: [mock_instr]
        dev = Instrument(resource)

        self.assertIsNotNone(dev)
        self.assertEqual(dev.idVendor, int(vendor))
        self.assertEqual(dev.idProduct, int(product))
        self.assertEqual(dev.iSerial, sn)

    def test_create_resource_using_keyword(self):
        """Create a VISA resource with single argument input"""
        vendor = 0x1234
        product = 0x5678
        resource = f"USB::{vendor}::{product}::INSTR"
        mock_instr = MockUsbtmcInstrument(vendor, product)
        usb_core_mock.find = lambda find_all, custom_match: [mock_instr]
        dev = Instrument(resource=resource)

        self.assertIsNotNone(dev)
        self.assertEqual(dev.idVendor, int(vendor))
        self.assertEqual(dev.idProduct, int(product))
        self.assertIsNone(dev.iSerial)

    def test_create_default_object_using_keywords(self):
        """Create an instrument object using keyword arguments."""
        vendor, product, sn = 0x1234, 0x5678, "90"
        mock_instr = MockUsbtmcInstrument(vendor, product, serial=sn)
        usb_core_mock.find = lambda find_all, custom_match: [mock_instr]
        vendor = mock_instr.idVendor

        dev = Instrument(idVendor=vendor, idProduct=product, iSerial=sn)
        self.assertIsNotNone(dev)
        self.assertEqual(dev.idVendor, int(vendor))
        self.assertEqual(dev.idProduct, int(product))
        self.assertEqual(dev.iSerial, sn)

    def test_create_device_raises_exception(self):
        """Test that device object without vendor id or faulty find_device raises exception"""
        with self.assertRaises(UsbtmcException) as usbtmc_exc:
            Instrument(idVendor=None, idProduct=None)

        self.assertEqual("No device specified [init]", str(usbtmc_exc.exception))

        usb_core_mock.find = lambda find_all, custom_match: []
        with self.assertRaises(UsbtmcException) as usbtmc_exc:
            Instrument(0x1234, 0x5678)

        self.assertEqual("Device not found [init]", str(usbtmc_exc.exception))

    def test_create_resource_raises_exception(self):
        """Creating a VISA resource from invalid string(s) raises exception"""
        expected_error = "Invalid resource string [init]"
        with self.assertRaises(UsbtmcException) as usbtmc_exc:
            Instrument("resource")

        self.assertEqual(expected_error, str(usbtmc_exc.exception))
        # TODO: To raise from the second exception clause in L370, 'arg1' or 'arg2' should be None, but didn't manage
        # to create such a string that would give None only there and not except the whole matching.
        # vendor = None
        # product = None
        # resource = f"USB::{vendor}::{product}::INSTR"
        # with self.assertRaises(UsbtmcException) as usbtmc_exc:
        #     Instrument(resource)
        #
        # self.assertEqual(expected_error, str(usbtmc_exc.exception))
        #


class OpenCloseMethodsTestCase(unittest.TestCase):
    """Test 'open' and 'close' methods of the class."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(serial="90")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x0957))
        self.mock_instr.set_configuration = unittest.mock.MagicMock()
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        default_product = self.mock_instr.idProduct
        default_sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, default_product, default_sn)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_default_mock_device(self):
        """Test opening the default mock device."""
        # We can also check the self. values that are set by the "get_capabilities" call in "open"
        expected_bcdUSBTMC = (self.ctrl_transfer_return[3] << 8) + self.ctrl_transfer_return[2]
        expected_support_pulse = self.ctrl_transfer_return[4] & 4 != 0
        expected_support_talk_only = self.ctrl_transfer_return[4] & 2 != 0
        expected_support_listen_only = self.ctrl_transfer_return[4] & 1 != 0
        expected_support_term_char = self.ctrl_transfer_return[5] & 1 != 0

        # Check the initial conditions match the __init__ of the class
        self.assertEqual(0, self.dev.bcdUSBTMC)
        self.assertFalse(self.dev.support_pulse)
        self.assertFalse(self.dev.support_talk_only)
        self.assertFalse(self.dev.support_listen_only)
        self.assertFalse(self.dev.support_term_char)

        self.dev.open()
        self.mock_instr.ctrl_transfer.assert_called()
        ctrl_transfer_calls = self.mock_instr.ctrl_transfer.call_count
        self.mock_instr.get_active_configuration.assert_called_once()
        self.mock_instr.set_configuration.assert_called_once()
        usb_util_mock.dispose_resources.assert_called_once()
        # Opening second time should not increase call counts as it should exit immediately
        self.dev.open()
        self.assertEqual(ctrl_transfer_calls, self.mock_instr.ctrl_transfer.call_count)
        self.mock_instr.get_active_configuration.assert_called_once()
        self.mock_instr.set_configuration.assert_called_once()
        usb_util_mock.dispose_resources.assert_called_once()

        self.assertEqual(expected_bcdUSBTMC, self.dev.bcdUSBTMC)
        self.assertEqual(expected_support_pulse, self.dev.support_pulse)
        self.assertEqual(expected_support_talk_only, self.dev.support_talk_only)
        self.assertEqual(expected_support_listen_only, self.dev.support_listen_only)
        self.assertEqual(expected_support_term_char, self.dev.support_term_char)

    def test_closing_default_mock_device(self):
        """Test closing the default mock device."""
        self.dev.reattach.append("nep")
        self.mock_instr.attach_kernel_driver = unittest.mock.MagicMock()
        # Should close immediately
        self.dev.close()
        usb_util_mock.dispose_resources.assert_not_called()
        self.mock_instr.set_configuration.assert_not_called()
        self.mock_instr.attach_kernel_driver.assert_not_called()

        # By opening first should then run through the close() in another path
        self.dev.open()
        self.dev.close()
        # We have two calls to dispose-resources as it is also called in _init_agilent_u27xx
        self.assertEqual(2, usb_util_mock.dispose_resources.call_count)
        self.mock_instr.set_configuration.assert_called_once()
        if os.name == "posix":
            # The _release_kernel_driver method makes an extra call
            self.assertEqual(2, self.mock_instr.attach_kernel_driver.call_count)

        else:
            self.mock_instr.attach_kernel_driver.assert_called_once_with("nep")

    def test_read_stb_open(self):
        """As the call read_stb has also a call to open() if device is not connected, we can test that case here.

        Note that the 'ask' call is now patched, as we want to test the first if-clause only.
        """
        self.dev.ask = unittest.mock.Mock(return_value="1")
        self.dev.read_stb()

        self.mock_instr.ctrl_transfer.assert_called()
        self.mock_instr.get_active_configuration.assert_called_once()
        self.mock_instr.set_configuration.assert_called_once()
        usb_util_mock.dispose_resources.assert_called_once()


class OpenExceptsTestCase(unittest.TestCase):
    """Test 'open' method of the class excepts."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(vendor=0x1234, serial="killer")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        default_product = self.mock_instr.idProduct
        default_sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, default_product, default_sn)

    def test_open_default_mock_device_excepts(self):
        """Test opening the default mock device."""
        expected_error = "Not a USBTMC device [init]"
        with self.assertRaises(UsbtmcException) as exc:
            self.dev.open()

        self.assertEqual(expected_error, str(exc.exception))


class OpenOldConfigurationTestCase(unittest.TestCase):
    """Test 'open' method of an instrument that is already configured."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(vendor=0x0957, serial="killer")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x0957))
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        default_product = self.mock_instr.idProduct
        default_sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, default_product, default_sn)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_already_configured_device(self):
        """Test opening the default mock device."""
        self.dev.force_reconfigure = False
        self.dev.open()


class OpenAgilent0x4218TestCase(unittest.TestCase):
    """Test 'open' and 'close' methods of the class."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(product=0x4218, serial="90")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=None)
        self.mock_instr.set_configuration = unittest.mock.MagicMock()
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        product = self.mock_instr.idProduct
        sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, product, sn)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_0x4218_mock_device(self):
        """Test opening the default mock device."""
        # If get_active_configuration() returns None, we should not have calls for attach_kernel_driver(). Check.
        self.mock_instr.attach_kernel_driver = unittest.mock.MagicMock()
        # Act
        self.dev.open()
        # Assert
        usb_util_mock.dispose_resources.assert_called_once()
        self.mock_instr.set_configuration.assert_called_once()
        self.mock_instr.attach_kernel_driver.assert_not_called()


class OpenAgilent0x4418TestCase(unittest.TestCase):
    """Test 'open' and 'close' methods of the class."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(product=0x4418, serial="90")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x0957))
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        product = self.mock_instr.idProduct
        sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, product, sn)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_0x4418_mock_device(self):
        """Test opening the default mock device."""
        self.dev.open()


class OpenRigolTestCase(unittest.TestCase):
    """Test 'open' method of the class for Rigol instrument."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(vendor=0x1ab1, product=0x04ce)
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x0957))
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        vendor = self.mock_instr.idVendor
        product = self.mock_instr.idProduct

        self.dev = Instrument(vendor, product)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_mock_device(self):
        """Test opening the mock device sets Rigol-related attributes to True."""
        self.assertFalse(self.dev.rigol_quirk)
        self.assertFalse(self.dev.rigol_quirk_ieee_block)

        self.dev.open()

        self.assertTrue(self.dev.rigol_quirk)
        self.assertTrue(self.dev.rigol_quirk_ieee_block)

    def test_read_raw_with_rigol(self):
        """read_raw method has conditional behaviour according to 'if self.rigol_quirk' and
        'if self.rigol_quirk_ieee_block'"""
        self.dev.open()
        # Rigol read data str layout: 0: #, 1: data length, 2 - l+2: data
        success_readout = numpy.array([c for c in "#12000321000321"])
        pending_readout = numpy.array([c for c in "#00"])
        expected_data = b"".join([c for c in list(pending_readout)[1:]])
        expected_data += b"".join([c for c in list(success_readout)[5:] + [b"#"]])
        self.dev.bulk_in_ep.read = unittest.mock.Mock(side_effect=[success_readout, pending_readout])

        data = self.dev.read_raw()

        self.assertEqual(2, self.dev.bulk_in_ep.read.call_count)
        self.assertEqual(expected_data, data)


class OpenThorlabsTestCase(unittest.TestCase):
    """Test 'open' and 'close' methods of the class for Thorlabs device."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(vendor=0x1313)
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x0957))
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        product = self.mock_instr.idProduct

        self.dev = Instrument(default_vendor, product)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_close_mock_device(self):
        """Test opening and closing the mock device make specific calls to ctrl_transfer."""
        expected_close_parameters_1 = unittest.mock.call(
            bmRequestType=0xA1, bRequest=USB488_GOTO_LOCAL, wValue=0x0000, wIndex=0x0000, data_or_wLength=1
        )
        expected_close_parameters_2 = unittest.mock.call(
            bmRequestType=0xA1, bRequest=USB488_REN_CONTROL, wValue=0x0000, wIndex=0x0000, data_or_wLength=1
        )

        self.dev.open()

        self.mock_instr.ctrl_transfer.assert_any_call(
            bmRequestType=0xA1, bRequest=USB488_REN_CONTROL, wValue=0x0001, wIndex=0x0000, data_or_wLength=1
        )

        self.mock_instr.ctrl_transfer.reset_mock()
        self.dev.close()

        self.mock_instr.ctrl_transfer.assert_has_calls([expected_close_parameters_1, expected_close_parameters_2])


class OpenInstrumentWithNoEndpointTestCase(unittest.TestCase):
    """Test 'open' with instrument not giving an endpoint fails."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(serial="90")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=None)
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        product = self.mock_instr.idProduct
        sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, product, sn)

        # Now we return from type wrong dirs so no match will be done in/out endpoints
        dir_side_dish = [0x2, 0x2, 0x4, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

    def test_open_excepts_with_none_endpoint(self):
        """See that an exception is raised if endpoint is None"""
        expected_error = "Invalid endpoint configuration [init]"
        with self.assertRaises(UsbtmcException) as exc:
            self.dev.open()

        self.assertEqual(expected_error, str(exc.exception))


class MethodsTestCase(unittest.TestCase):
    """Test other methods of the class with default instrument."""
    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        self.mock_instr = MockUsbtmcInstrument(serial="90")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x0957))
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        default_product = self.mock_instr.idProduct
        default_sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, default_product, default_sn)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENDPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

        self.dev.open()

    def tearDown(self) -> None:
        self.dev.close()

    def test_get_capabilities(self):
        """Test also with condition 'if self.is_usb488()' being True"""
        ctrl_transfer_usb488 = self.ctrl_transfer_return + [0] * 6 + [1, 2]
        expected_bcdUSBTMC = (ctrl_transfer_usb488[3] << 8) + ctrl_transfer_usb488[2]
        expected_bcdUSB488 = (ctrl_transfer_usb488[13] << 8) + ctrl_transfer_usb488[12]
        expected_support_pulse = ctrl_transfer_usb488[4] & 4 != 0
        expected_support_talk_only = ctrl_transfer_usb488[4] & 2 != 0
        expected_support_listen_only = ctrl_transfer_usb488[4] & 1 != 0
        expected_support_term_char = ctrl_transfer_usb488[5] & 1 != 0

        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [ctrl_transfer_usb488]
        self.dev.iface.bInterfaceProtocol = USB488_bInterfaceProtocol

        self.dev.get_capabilities()

        self.assertEqual(expected_bcdUSBTMC, self.dev.bcdUSBTMC)
        self.assertEqual(expected_bcdUSB488, self.dev.bcdUSB488)
        self.assertEqual(expected_support_pulse, self.dev.support_pulse)
        self.assertEqual(expected_support_talk_only, self.dev.support_talk_only)
        self.assertEqual(expected_support_listen_only, self.dev.support_listen_only)
        self.assertEqual(expected_support_term_char, self.dev.support_term_char)

    def test_pulse(self):
        """Test the 'pulse' call for pulse indicator request"""
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [self.ctrl_transfer_return]
        self.dev.support_pulse = True

        self.dev.pulse()

        self.mock_instr.ctrl_transfer.assert_called_once()

    def test_ask(self):
        """Test 'ask' method with a list/tuple of messages with multiple outputs"""
        expected_responses = ["1", "2"]
        message_list = ["msg1", "msg2"]
        self.dev.bulk_in_ep.read = unittest.mock.Mock(side_effect=[
            numpy.array(["\xc1", "\x01", "\x01", expected_responses[0], "\x0c", "\x0b", "\x0a", "\x03", "\x00"]),
            numpy.array(["\xc1", "\x01", "\x01", expected_responses[1], "\x0c", "\x0b", "\x0a", "\x03", "\x00"])
        ])

        values = self.dev.ask(message_list)
        for v, value in enumerate(values):
            self.assertEqual(expected_responses[v], value)

    def test_ask_raw(self):
        """Test writing and reading binary data"""
        expected_byte = 0  # numbers 0-9 should all work
        fake_ask = b"SMTH?"
        self.dev.bulk_in_ep.read = unittest.mock.Mock(return_value=numpy.array(
            ["\xc1", "\x01", "\x01", f"{expected_byte}", "\x0c", "\x0b", "\x0a", "\x03", "\x00"]
        ))
        # Mock the write for testing
        write_header = b"\x01\x01\xfe\x00\x05\x00\x00\x00\x01\x00\x00\x00"
        
        status_byte = self.dev.ask_raw(fake_ask)
        self.assertEqual(f"{expected_byte}".encode(), status_byte)

        match_found = False
        for _call in self.dev.bulk_out_ep.write.call_args_list:
            if _call[0][0].startswith(write_header):
                self.assertIn(fake_ask, _call[0][0])
                self.assertDictEqual({"timeout": 5000}, _call[1])
                match_found = True

        self.assertTrue(match_found)

    def test_read_raw_excepts_no_timeout(self):
        """Test read_raw excepting with 'usb.core.USBError' but error not being timeout."""
        self.dev.bulk_in_ep.read = unittest.mock.Mock(side_effect=[RuntimeError])
        with self.assertRaises(RuntimeError):
            self.dev.read_raw()

        self.dev.bulk_in_ep.read.assert_called_once()

    def test_read_raw_excepts_with_timeout(self):
        """Test read_raw excepting with 'usb.core.USBError', error being timeout with errno 110."""
        success_readout = USBTMC_STATUS_SUCCESS, "\x01", "\x01", "\x00", "\x0c", "\x0b", "\x0a", "\x03", "\x00"
        pending_readout = USBTMC_STATUS_PENDING, "\x01", "\x01", "\x00", "\x0c", "\x0b", "\x0a", "\x03", "\x00"
        self.dev.bulk_in_ep.read = unittest.mock.Mock(side_effect=[
            usb.core.USBError, success_readout, pending_readout
        ])
        with self.assertRaises(usb.core.USBError) as exc:
            self.dev.read_raw()

        self.assertEqual(exc.exception.errno, ExcInfoMock.errno)
        self.dev.bulk_in_ep.read.assert_any_call(
            self.dev.max_transfer_size + 15, timeout=int(1000 * self.dev.abort_timeout)
        )

    def test_write_raw_excepts_no_timeout(self):
        """Test write_raw excepting with 'usb.core.USBError' but error not being timeout."""
        self.dev.bulk_out_ep.write = unittest.mock.Mock(side_effect=[RuntimeError])
        with self.assertRaises(RuntimeError):
            self.dev.write_raw(b"foo")

    def test_write_raw_excepts_with_timeout(self):
        """Test write_raw excepting with 'usb.core.USBError', error being timeout with errno 110."""
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [
            self.ctrl_transfer_return, [USBTMC_STATUS_PENDING], self.ctrl_transfer_return
        ]
        self.dev.bulk_out_ep.clear_halt.reset_mock()
        self.dev.bulk_out_ep.write = unittest.mock.MagicMock(side_effect=[usb.core.USBError])
        with self.assertRaises(usb.core.USBError) as exc:
            self.dev.write_raw(b"bar")

        self.assertEqual(exc.exception.errno, ExcInfoMock.errno)
        self.dev.bulk_out_ep.clear_halt.assert_called_once()

    def test_read_stb(self):
        """Test the read_stb call with the default method"""
        expected_byte = 9  # numbers 0-9 should all work
        self.dev.bulk_in_ep.read = unittest.mock.Mock(return_value=numpy.array(
            ["\xc1", "\x01", "\x01", f"{expected_byte}", "\x0c", "\x0b", "\x0a", "\x03", "\x00"]
        ))
        # Mock the write for testing
        write_header = b"\x01\x01\xfe\x00\x05\x00\x00\x00\x01\x00\x00\x00"

        status_byte = self.dev.read_stb()
        self.assertEqual(expected_byte, status_byte)

        match_found = False
        for _call in self.dev.bulk_out_ep.write.call_args_list:
            if _call[0][0].startswith(write_header):
                self.assertIn(b"*STB?", _call[0][0])
                self.assertDictEqual({"timeout": 5000}, _call[1])
                match_found = True

        self.assertTrue(match_found)

    def test_read_stb_usb488(self):
        """Test the read_stb call with the default method with self.is_usb488 as True"""
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [[USBTMC_STATUS_SUCCESS, 2, 1, 0, 0, 0]]
        expected_byte = 9
        self.dev.interrupt_in_ep.read = unittest.mock.Mock(return_value=
            [130, expected_byte, "\x02", "\x01", "\x0c", "\x0b", "\x0a", "\x03", "\x00"]
        )
        
        self.dev.iface.bInterfaceProtocol = USB488_bInterfaceProtocol

        status_byte = self.dev.read_stb()
        self.assertEqual(expected_byte, status_byte)

    def test_read_stb_usb488_none_interrupt_in_ep(self):
        """Test the read_stb call with the default method with self.is_usb488 as True, but
        self.interrupt_in_ep as None.
        """
        expected_byte = 9
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [[USBTMC_STATUS_SUCCESS, 2, expected_byte, 0, 0, 0]]
        self.dev.interrupt_in_ep = None
        
        self.dev.iface.bInterfaceProtocol = USB488_bInterfaceProtocol

        status_byte = self.dev.read_stb()
        self.assertEqual(expected_byte, status_byte)

    def test_read_stb_usb488_excepts_on_b0(self):
        """Test the read_stb call with the default method with self.is_usb488 as True with exception"""
        expected_exception = "Read status failed [read_stb]"
        self.mock_instr.ctrl_transfer.reset_mock()
        # Fail on first byte not being 'success'
        self.mock_instr.ctrl_transfer.side_effect = [[USBTMC_STATUS_FAILED, 2, 1, 0, 0, 0]]
        
        self.dev.iface.bInterfaceProtocol = USB488_bInterfaceProtocol

        with self.assertRaises(UsbtmcException) as exc:
            self.dev.read_stb()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_read_stb_usb488_excepts_on_b1(self):
        """Test the read_stb call with the default method with self.is_usb488 as True with exception"""
        expected_exception = "Read status byte btag mismatch [read_stb]"
        
        # Fail on second byte of ctrl_transfer response (1) not being same as the USB488_bInterfaceProtocol (2).
        self.dev.iface.bInterfaceProtocol = USB488_bInterfaceProtocol

        with self.assertRaises(UsbtmcException) as exc:
            self.dev.read_stb()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_read_stb_usb488_excepts_on_resp(self):
        """Test the read_stb call with the default method with self.is_usb488 as True"""
        expected_exception = "Read status byte btag mismatch [read_stb]"
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [[USBTMC_STATUS_SUCCESS, 2, 1, 0, 0, 0]]
        # Fail on read returning first byte not matching 128 + 2 = 130.
        self.dev.interrupt_in_ep.read = unittest.mock.Mock(return_value=
                                                           [128, 0, "\x02", "\x01", "\x0c", "\x0b", "\x0a",
                                                            "\x03", "\x00"]
                                                           )
        self.dev.iface.bInterfaceProtocol = USB488_bInterfaceProtocol

        with self.assertRaises(UsbtmcException) as exc:
            self.dev.read_stb()

        self.assertEqual(expected_exception, str(exc.exception))

    def test_trigger(self):
        """Test the trigger function"""
        # Mock the write for testing
        write_header = b"\x01\x01\xfe\x00\x04\x00\x00\x00\x01\x00\x00\x00"

        self.dev.trigger()

        match_found = False
        for _call in self.dev.bulk_out_ep.write.call_args_list:
            if _call[0][0].startswith(write_header):
                self.assertIn(b"*TRG", _call[0][0])
                self.assertDictEqual({"timeout": 5000}, _call[1])
                match_found = True

        self.assertTrue(match_found)

    def test_trigger_with_support(self):
        """Test the trigger function with self.support_trigger as True"""
        timeout = int(self.dev.timeout * 1000)
        # Mock the write for testing
        
        self.dev.support_trigger = True

        self.dev.trigger()

        self.dev.bulk_out_ep.write.assert_called_once_with(
            b"\x80\x01\xfe\x00\x00\x00\x00\x00\x00\x00\x00\x00", timeout=timeout
        )

    def test_clear(self):
        """Test the clear function"""
        expected_no_of_calls = 3
        self.mock_instr.ctrl_transfer.reset_mock()
        second_pass = [USBTMC_STATUS_PENDING]
        third_pass = [USBTMC_STATUS_SUCCESS]
        self.mock_instr.ctrl_transfer.side_effect = [self.ctrl_transfer_return, second_pass, third_pass]

        self.dev.clear()

        self.assertEqual(expected_no_of_calls, self.mock_instr.ctrl_transfer.call_count)

    def test_clear_excepts(self):
        """Test that the clear function excepts by non-successful status"""
        expected_error = "Clear failed [clear]"
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.return_value = [USBTMC_STATUS_FAILED]

        with self.assertRaises(UsbtmcException) as exc:
            self.dev.clear()

        self.assertEqual(expected_error, str(exc.exception))

    def test_remote(self):
        """This should simply raise 'NotImplementedError'."""
        with self.assertRaises(NotImplementedError):
            self.dev.remote()

    def test_local(self):
        """This should simply raise 'NotImplementedError'."""
        with self.assertRaises(NotImplementedError):
            self.dev.local()

    def test_lock_raises_error(self):
        """This should simply raise 'NotImplementedError'."""
        with self.assertRaises(NotImplementedError):
            self.dev.lock()

    def test_unlock_raises_error(self):
        """This should simply raise 'NotImplementedError'."""
        with self.assertRaises(NotImplementedError):
            self.dev.unlock()

    def test_advantest_read_myid_raises_error(self):
        """This should simply raise 'NotImplementedError'."""
        with self.assertRaises(NotImplementedError):
            self.dev.advantest_read_myid()


class AdvantestTestCase(unittest.TestCase):
    """Test Advantest/ADCMT instrument case."""

    def setUp(self) -> None:
        self.ctrl_transfer_return = [USBTMC_STATUS_SUCCESS, 1, 2, 3, 4, 0]
        # Vendor ID 0x1334 is for Advantech
        self.mock_instr = MockUsbtmcInstrument(vendor=0x1334, product=0x2818, serial="90")
        self.mock_instr.ctrl_transfer = unittest.mock.MagicMock(return_value=self.ctrl_transfer_return)
        self.mock_instr.get_active_configuration = unittest.mock.MagicMock(return_value=MockCfg(0x1334))
        usb_core_mock.find = lambda find_all, custom_match: [self.mock_instr]
        default_vendor = self.mock_instr.idVendor
        default_product = self.mock_instr.idProduct
        default_sn = self.mock_instr.serial_number

        self.dev = Instrument(default_vendor, default_product, default_sn)

        usb_util_mock.dispose_resources = unittest.mock.MagicMock()
        usb_util_mock.ENDPOINT_TYPE_BULK = 0x1
        usb_util_mock.ENDPOINT_IN = 0x2
        usb_util_mock.ENDPOINT_OUT = 0x4
        usb_util_mock.ENDPOINT_TYPE_INTR = 0x8

        dir_side_dish = [0x2, 0x4, 0x2, 0x4]
        usb_util_mock.endpoint_direction = unittest.mock.Mock(side_effect=dir_side_dish)
        type_side_dish = [0x1, 0x1, 0x8, 0x8]
        usb_util_mock.endpoint_type = unittest.mock.Mock(side_effect=type_side_dish)

        self.dev.open()

    def tearDown(self) -> None:
        self.dev.close()

    def test_lock_unlock(self):
        """Test the 'lock' and 'unlock' methods."""
        # First check the initial state
        self.assertTrue(self.dev.advantest_quirk)
        self.assertFalse(self.dev.advantest_locked)
        # Then call 'lock'
        self.dev.lock()
        # Assert changed state
        self.assertTrue(self.dev.advantest_locked)
        # Then call 'unlock'
        self.dev.unlock()
        # Assert changed state
        self.assertFalse(self.dev.advantest_locked)

    def test_advantest_read_myid(self):
        """Test the advantest_read_myid method."""
        excepted = 1  # Returns the first byte as integer from self.device.ctrl_transfer, which is 1
        myid = self.dev.advantest_read_myid()
        self.assertEqual(excepted, myid)

    def test_advantest_read_myid_return_none(self):
        """Test the advantest_read_myid method returns none by exception."""
        excepted = None  # Returns the first byte as integer from self.device.ctrl_transfer, which is 1
        self.mock_instr.ctrl_transfer.reset_mock()
        self.mock_instr.ctrl_transfer.side_effect = [Exception()]

        myid = self.dev.advantest_read_myid()
        self.assertEqual(excepted, myid)


class ListResourcesTestCase(unittest.TestCase):
    """Test the list_resources function."""
    def test_list_resources(self):
        # Create mock Agilent device objects
        agilent_vendor_id = 0x0957
        agilent_product_id = [0x2818, 0x4218, 0x4418]
        agilent_fw_update_mode_prod_id = [0x2918, 0x4118, 0x4318]
        agilent_serial_nrs = ["90", "91", "92"]
        # Agilent default U2701A
        mock_instr_a = MockUsbtmcInstrument(serial=agilent_serial_nrs[0])
        # Agilent U2722A
        mock_instr_b = MockUsbtmcInstrument(product=agilent_product_id[1], serial=agilent_serial_nrs[1])
        # Agilent U2723A
        mock_instr_c = MockUsbtmcInstrument(product=agilent_product_id[2], serial=agilent_serial_nrs[2])
        # Create a mock Advantest device object with no serial number
        advantest_vendor_id = 0x1334
        advantest_product_id = 0x0
        mock_instr = MockUsbtmcInstrument(advantest_vendor_id, advantest_product_id, serial=None)
        usb_core_mock.find = lambda find_all, custom_match: [
            mock_instr_a, mock_instr_b, mock_instr_c, mock_instr
        ]
        # Expected resources found
        visa_str_1 = f"USB::{agilent_vendor_id}::{agilent_fw_update_mode_prod_id[0]}::{agilent_serial_nrs[0]}::INSTR"
        visa_str_2 = f"USB::{agilent_vendor_id}::{agilent_fw_update_mode_prod_id[1]}::{agilent_serial_nrs[1]}::INSTR"
        visa_str_3 = f"USB::{agilent_vendor_id}::{agilent_fw_update_mode_prod_id[2]}::{agilent_serial_nrs[2]}::INSTR"
        visa_str_4 = f"USB::{advantest_vendor_id}::{advantest_product_id}::INSTR"
        expected_resources = [visa_str_1, visa_str_2, visa_str_3, visa_str_4]
        # Act
        resources = list_resources()
        # Assert
        self.assertListEqual(expected_resources, resources)


if __name__ == '__main__':
    unittest.main()
