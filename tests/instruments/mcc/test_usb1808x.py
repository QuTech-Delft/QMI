from unittest import TestCase
from unittest.mock import MagicMock, Mock
from unittest.mock import patch

from dataclasses import dataclass
import logging

import qmi.instruments
from qmi.instruments.mcc.usb1808x import MCC_USB1808X
from tests.patcher import PatcherQmiContext as QMI_Context


# Mock import "mcculw"
class mcculw:
    ul = None
    enums = None
    device_info = None


@dataclass
class TestUldaqDeviceDescriptor:
    """Test device descriptor data."""
    product_name: str
    unique_id: MagicMock()


@dataclass
class TestRanges:
    """Test device analog range."""
    name: str
    range_min: float = -10
    range_max: float = 10


class TestDeviceConfig:

    version = "1.2.3"
    get_version = Mock(return_value=version)


class TestPortInfo:
    number_of_bits = num_bits = 4  # Unix | Win
    # Unix
    ai_chans = 8
    ai_ranges = [
        TestRanges(name="small_range"),
        TestRanges(name="medium_range"),
        TestRanges(name="large_range"),
    ]
    # Win
    type = "some_port_type"

    def get_port_info(self, val):
        return self

    @staticmethod
    def get_num_chans():
        return TestPortInfo.ai_chans

    @staticmethod
    def get_ranges(chan_type=None):
        return TestPortInfo.ai_ranges


TestDioPortInfo = Mock()
TestDioPortInfo.get_port_info = Mock(return_value=TestPortInfo)
TestDioPortInfo.get_port_direction = Mock(return_value=[1, 0, 1])

TestDioInfo = Mock()
# Unix
TestDioInfo.d_config_bit = Mock()
TestDioInfo.d_bit_in = Mock(return_value=1)
TestDioInfo.d_bit_out = Mock()
TestDioInfo.get_info = Mock(return_value=TestDioPortInfo)
TestDioInfo.get_config = Mock(return_value=TestDioPortInfo)
# Win
TestDioInfo.num_ports = 1
TestDioInfo.port_info = [TestPortInfo()]

TestAiInfo = Mock()
# Unix
TestAiInfo.a_in = Mock(return_value=12345)
TestAiInfo.get_info = Mock(return_value=TestPortInfo)
# Win
TestAiInfo.num_chans = 8
TestAiInfo.supported_ranges = [
    TestRanges(name="small_range"),
    TestRanges(name="medium_range"),
    TestRanges(name="large_range"),
]


TestAoInfo = Mock()
# Unix
TestAoInfo.a_out = Mock()
TestAoInfo.get_info = Mock(return_value=TestPortInfo)
# Win
TestAoInfo.num_chans = 2
TestAoInfo.supported_ranges = [
    TestRanges(name="small_range"),
    TestRanges(name="medium_range"),
    TestRanges(name="large_range"),
]


class TestUSB1808XUnix(TestCase):
    """Testcase for the MCC_USB1808X class on Unix environment."""

    @patch("sys.platform", "linux")
    def setUp(self):
        logging.getLogger("qmi.instruments.mcc.usb1808x").setLevel(logging.CRITICAL)
        from qmi.instruments.mcc.usb1808x import MCC_USB1808X, _Mcc_Usb1808xUnix

        self.unix_inst_class = _Mcc_Usb1808xUnix
        # Substitute a mock object in place of the "uldaq" module.
        # This must be done BEFORE the FOS driver runs "import uldaq".
        with patch.dict("sys.modules", {"uldaq": Mock()}):
            # Trigger lazy import of the uldaq module.
            qmi.instruments.mcc.usb1808x._import_modules()

        self._mock_name = "D3ADMAU5"
        self._test_descriptor = TestUldaqDeviceDescriptor(
            product_name="mockerson", unique_id=self._mock_name
        )

        uldaq_mock = Mock()
        uldaq_mock.DigitalDirection = Mock()
        uldaq_mock.DigitalDirection.INPUT = 0
        uldaq_mock.DigitalDirection.OUTPUT = 1
        uldaq_mock.DigitalPortType = Mock()
        uldaq_mock.DigitalPortType.AUXPORT = 2
        uldaq_mock.AiInputMode = {"DIFFERENTIAL": 1}
        uldaq_mock.Range = {"medium_range": 10}
        uldaq_mock.AInFlag.DEFAULT = 1
        uldaq_mock.AOutFlag.DEFAULT = 0
        self._patcher_uldaq = patch("qmi.instruments.mcc.usb1808x.uldaq", uldaq_mock)
        self._patcher_uldaq.start()

        self.instr = MCC_USB1808X(QMI_Context(), "unix_1808x", self._mock_name)

        # Patch device
        self.device_mock = Mock()
        self.device_mock.get_dio_device = Mock(return_value=TestDioInfo)
        self.device_mock.get_ai_device = Mock(return_value=TestAiInfo)
        self.device_mock.get_ao_device = Mock(return_value=TestAoInfo)
        patcher = patch('qmi.instruments.mcc.usb1808x.uldaq.DaqDevice', return_value=self.device_mock)
        self.device_init = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._patcher_uldaq.stop()
        logging.getLogger("qmi.instruments.mcc.usb1808x").setLevel(logging.NOTSET)

    def test_init(self):
        """MCC_USB1808X.__init__(), happy flow."""
        self.assertIsInstance(self.instr.device, self.unix_inst_class)

    def test_list_instruments(self):
        """MCC_USB1808X.list_instruments(), happy flow."""
        # Arrange
        mock_unique_id_1 = MagicMock()
        mock_unique_id_2 = MagicMock()
        mock_unique_id_3 = MagicMock()
        mock_resp = [
            TestUldaqDeviceDescriptor("USB-1808X", mock_unique_id_1),
            TestUldaqDeviceDescriptor("NOT", mock_unique_id_2),
            TestUldaqDeviceDescriptor("USB-1808X", mock_unique_id_3),
        ]
        # Act
        with patch(
            "qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=mock_resp
        ) as daq_dev_inv_patch:
            rt_val = self.unix_inst_class.list_instruments()

        # self._meta.import_module.assert_has_calls([call(), call()])
        # Assert
        daq_dev_inv_patch.assert_called_once()
        self.assertEqual(rt_val[0], mock_unique_id_1)
        self.assertEqual(rt_val[1], mock_unique_id_3)

    def test_open(self):
        """MCC_USB1808X.open(), happy flow."""
        # Arrange
        test_descriptor = TestUldaqDeviceDescriptor(product_name="NOT", unique_id=self._mock_name)
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[test_descriptor]):
            self.instr.open()

        # Assert
        self.assertIsNotNone(self.instr._device)
        self.assertTrue(self.instr._is_open)

    def test_open_no_device(self):
        """MCC_USB1808X.open(), no device found exception."""
        # Arrange
        expected_exception = f"MCC USB-1808X with unique_id '{self._mock_name}' not found."
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name="NOT", unique_id="NOT"
        )
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[test_descriptor]):
            with self.assertRaises(ValueError) as exc:
                self.instr.open()

            # Assert
            self.assertEqual(expected_exception, str(exc.exception))

    def test_open_connect_error(self):
        """MCC_USB1808X.open(), device.connect() exception."""
        # Arrange
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name="mockerson", unique_id=self._mock_name
        )
        self.device_mock.connect = Mock(side_effect=[Exception])
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[test_descriptor]):
            with self.assertRaises(Exception):
                self.instr.open()

        # Assert
        self.device_mock.connect.assert_called_once_with()
        self.device_mock.release.assert_called_once_with()

    def test_open_device_get_dio_device_error(self):
        """MCC_USB1808X.open(), device.get_dio_device() exception."""
        # Arrange
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name="mockerson", unique_id=self._mock_name
        )
        self.device_mock.get_dio_device = Mock(side_effect=[Exception])
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[test_descriptor]):
            with self.assertRaises(Exception):
                self.instr.open()

        # Assert
        self.device_mock.connect.assert_called_once_with()
        self.device_mock.disconnect.assert_called_once_with()

    def test_close(self):
        """MCC_USB1808X.close(), happy flow."""
        # Arrange
        self.instr._check_is_open = Mock(return_value=True)
        self.instr._device = Mock(spec=self.unix_inst_class)
        self.instr._device._unique_id = "D3ADMAU5"
        # Act
        self.instr.close()
        # Assert
        self.assertIsNone(self.instr._device)
        self.assertFalse(self.instr._is_open)

    def test_get_idn(self):
        """MCC_USB1808X.get_idn(), happy flow."""
        # Arrange
        expected_vendor = "Measurement Computing"
        expected_model = "USB-1808X"
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name=expected_model, unique_id=self._mock_name
        )
        expected_version = TestDeviceConfig.version
        self.device_mock.get_descriptor = Mock(return_value=test_descriptor)
        self.device_mock.get_config = Mock(return_value=TestDeviceConfig())
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_idn()

        # Assert
        self.device_mock.get_descriptor.assert_called_once_with()
        self.device_mock.get_config.assert_called_once_with()
        TestDeviceConfig.get_version.assert_called_once()
        self.assertEqual(expected_vendor, rt_val.vendor)
        self.assertEqual(expected_model, rt_val.model)
        self.assertEqual(self._mock_name, rt_val.serial)
        self.assertEqual(expected_version, rt_val.version)

    def test_get_dio_num_channels(self):
        """MCC_USB1808X.get_dio_num_channels(), happy flow."""
        # Arrange
        expected_num_channels = TestPortInfo.number_of_bits
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_dio_num_channels()

        TestDioInfo.get_info.assert_called_once_with()
        TestDioPortInfo.get_port_info.assert_called_once()
        self.assertEqual(expected_num_channels, rt_val)
        TestDioInfo.reset_mock()

    def test_get_dio_direction(self):
        """MCC_USB1808X.get_dio_direction(), happy flow."""
        # Arrange
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_dio_direction()

        TestDioInfo.get_config.assert_called_once_with()
        TestDioPortInfo.get_port_direction.assert_called_once()
        # OUTPUT is represented as a True, INPUT as a False
        self.assertEqual(rt_val[0], True)
        self.assertEqual(rt_val[1], False)
        self.assertEqual(rt_val[2], True)
        TestDioInfo.reset_mock()

    def test_set_dio_direction(self):
        """MCC_USB1808X.set_dio_direction(), happy flow."""
        # Arrange
        channel_0 = 0
        channel_1 = 1
        # Act and Assert
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            self.instr.set_dio_direction(channel_0, True)
            TestDioInfo.d_config_bit.assert_called_with(
                self._patcher_uldaq.new.DigitalPortType.AUXPORT, channel_0, self._patcher_uldaq.new.DigitalDirection.OUTPUT
            )
            self.instr.set_dio_direction(channel_1, False)
            TestDioInfo.d_config_bit.assert_called_with(
                self._patcher_uldaq.new.DigitalPortType.AUXPORT, channel_1, self._patcher_uldaq.new.DigitalDirection.INPUT
            )

        TestDioInfo.reset_mock()

    def test_get_dio_input_bit(self):
        """MCC_USB1808X.get_dio_input_bit(), happy flow."""
        # Arrange
        channel = 0
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_dio_input_bit(channel)  # We return True with the mock, defined at start of file

        # Assert
        self.assertTrue(rt_val)
        TestDioInfo.d_bit_in.assert_called_with(self._patcher_uldaq.new.DigitalPortType.AUXPORT, channel)
        TestDioInfo.reset_mock()

    def test_set_dio_output_bit(self):
        """MCC_USB1808X.set_dio_output_bit(), happy flow."""
        # Arrange
        channel = 0
        bit = False
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            self.instr.set_dio_output_bit(channel, bit)

        # Assert
        TestDioInfo.d_bit_out.assert_called_with(
            self._patcher_uldaq.new.DigitalPortType.AUXPORT, channel, int(bit)
        )
        TestDioInfo.reset_mock()

    def test_get_ai_num_channels(self):
        """MCC_USB1808X.get_ai_num_channels(), happy flow."""
        # Arrange
        expected_no_of_channels = TestPortInfo.ai_chans
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ai_num_channels()

        # Assert
        self.assertEqual(expected_no_of_channels, rt_val)
        TestAiInfo.get_info.assert_called_once_with()
        TestAiInfo.reset_mock()

    def test_get_ai_ranges(self):
        """MCC_USB1808X.get_ai_ranges(), happy flow."""
        # Arrange
        expected_ranges = ["small_range", "medium_range", "large_range"]

        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ai_ranges()

        # Assert
        self.assertListEqual(expected_ranges, rt_val)
        TestAiInfo.get_info.assert_called_once_with()
        TestAiInfo.reset_mock()

    def test_get_ai_value(self):
        """MCC_USB1808X.get_ai_value(), happy flow."""
        # Arrange
        channel = 5
        input_mode = "DIFFERENTIAL"
        analog_range = "medium_range"
        expected_value = 12345

        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ai_value(channel, input_mode, analog_range)

        # Assert
        self.assertEqual(expected_value, rt_val)
        TestAiInfo.a_in.assert_called_once_with(channel, 1, 10, self._patcher_uldaq.new.AInFlag.DEFAULT)
        TestAiInfo.reset_mock()

    def test_get_ao_num_channels(self):
        """MCC_USB1808X.get_ao_num_channels(), happy flow."""
        # Arrange
        expected_no_of_channels = TestPortInfo.ai_chans
        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ao_num_channels()

        # Assert
        self.assertEqual(expected_no_of_channels, rt_val)
        TestAoInfo.get_info.assert_called_once_with()
        TestAoInfo.reset_mock()

    def test_get_ao_ranges(self):
        """MCC_USB1808X.get_ao_ranges(), happy flow."""
        # Arrange
        expected_ranges = ["small_range", "medium_range", "large_range"]

        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ao_ranges()

        # Assert/
        self.assertListEqual(expected_ranges, rt_val)
        TestAoInfo.get_info.assert_called_once_with()
        TestAoInfo.reset_mock()

    def test_set_ao_value(self):
        """MCC_USB1808X.set_ao_value(), happy flow."""
        # Arrange
        channel = 1
        analog_range = "medium_range"
        expected_value = 5.4321

        # Act
        with patch("qmi.instruments.mcc.usb1808x.uldaq.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            self.instr.set_ao_value(channel, analog_range, expected_value)

        # Assert
        TestAoInfo.a_out.assert_called_once_with(
            channel, 10, self._patcher_uldaq.new.AOutFlag.DEFAULT, expected_value
        )
        TestAoInfo.reset_mock()


class TestUSB1808XWin(TestCase):
    """Testcase for the MCC_USB1808X class on Windows environment."""

    @patch("sys.platform", "win32")
    def setUp(self):
        logging.getLogger("qmi.instruments.mcc.usb1808x").setLevel(logging.CRITICAL)
        from qmi.instruments.mcc.usb1808x import MCC_USB1808X, _Mcc_Usb1808xWindows

        self.win_inst_class = _Mcc_Usb1808xWindows
        # Substitute a mock object in place of the "mcculw" module.
        # This must be done BEFORE the FOS driver runs "import mcculw".
        self.mcculw_mock = MagicMock(autospec=mcculw)
        with patch.dict("sys.modules", {
            "mcculw": self.mcculw_mock,
        }):
            # Trigger lazy import of the mcculw module.
            qmi.instruments.mcc.usb1808x._import_modules()

        self._mock_name = "D3ADMAU5"
        self._test_descriptor = TestUldaqDeviceDescriptor(
            product_name="mockerson", unique_id=self._mock_name
        )

        self._board_id = 99
        enums_mock = Mock()
        enums_mock.DigitalIODirection = Mock()
        enums_mock.DigitalIODirection.IN = 0
        enums_mock.DigitalIODirection.OUT = 1
        enums_mock.DigitalPortType = Mock()
        enums_mock.DigitalPortType.AUXPORT = 0
        enums_mock.InterfaceType = Mock()
        enums_mock.InterfaceType.USB = 1
        enums_mock.ULRange = {"medium_range": TestRanges("medium_range")}
        self._patcher_enums = patch("qmi.instruments.mcc.usb1808x.enums", enums_mock)
        self._patcher_enums.start()

        ul_mock = Mock()
        ul_mock.DigitalPortType = Mock()
        ul_mock.a_in = Mock(return_value=12345)
        ul_mock.a_out = Mock()
        ul_mock.get_board_number = Mock(return_value=self._board_id)
        ul_mock.get_config = Mock(side_effect=[0b0101])
        self._patcher_ul = patch("qmi.instruments.mcc.usb1808x.ul", ul_mock)
        self._patcher_ul.start()

        self.instr = MCC_USB1808X(QMI_Context(), "unix_1808x", self._mock_name, board_id=self._board_id)

        # Patch device
        self.device_mock = Mock()
        self.device_mock.product_name = "USB-1808X"
        self.device_mock.unique_id = self._mock_name
        self.device_mock.get_dio_info = Mock(return_value=TestDioInfo)
        self.device_mock.get_ai_info = Mock(return_value=TestAiInfo)
        self.device_mock.get_ao_info = Mock(return_value=TestAoInfo)
        patcher = patch('qmi.instruments.mcc.usb1808x.device_info.DaqDeviceInfo', return_value=self.device_mock)
        self.device_init = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._patcher_enums.stop()
        self._patcher_ul.stop()
        logging.getLogger("qmi.instruments.mcc.usb1808x").setLevel(logging.NOTSET)

    def test_init(self):
        """MCC_USB1808X.__init__(), happy flow."""
        self.assertIsInstance(self.instr.device, self.win_inst_class)

    def test_list_instruments(self):
        """MCC_USB1808X.list_instruments(), happy flow."""
        # Arrange
        mock_unique_id_1 = MagicMock()
        mock_unique_id_2 = MagicMock()
        mock_unique_id_3 = MagicMock()
        mock_resp = [
            TestUldaqDeviceDescriptor("USB-1808X", mock_unique_id_1),
            TestUldaqDeviceDescriptor("NOT", mock_unique_id_2),
            TestUldaqDeviceDescriptor("USB-1808X", mock_unique_id_3),
        ]
        # Act
        with patch(
            "qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=mock_resp
        ) as daq_dev_inv_patch:
            rt_val = self.win_inst_class.list_instruments()

        # self._meta.import_module.assert_has_calls([call(), call()])
        # Assert
        daq_dev_inv_patch.assert_called_once()
        self.assertEqual(rt_val[0], mock_unique_id_1)
        self.assertEqual(rt_val[1], mock_unique_id_3)

    def test_open(self):
        """MCC_USB1808X.open(), happy flow."""
        # Arrange
        test_descriptor = TestUldaqDeviceDescriptor(product_name="NOT", unique_id=self._mock_name)
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[test_descriptor]):
            self.instr.open()

        # Assert
        self.assertIsNotNone(self.instr._device)
        self.assertTrue(self.instr._is_open)
        self._patcher_ul.new.ignore_instacal.assert_called_once_with()
        self._patcher_ul.new.create_daq_device.assert_called_once_with(self._board_id, test_descriptor)
        self._patcher_ul.new.get_board_number.assert_called_with(test_descriptor)
        self.device_init.assert_called_once_with(self._board_id)

    def test_open_no_device(self):
        """MCC_USB1808X.open(), no device found exception."""
        # Arrange
        expected_exception = f"MCC USB-1808X with unique_id '{self._mock_name}' not found."
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name="NOT", unique_id="NOT"
        )
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[test_descriptor]):
            with self.assertRaises(ValueError) as exc:
                self.instr.open()

            # Assert
            self.assertEqual(expected_exception, str(exc.exception))

    def test_open_board_id_error(self):
        """MCC_USB1808X.open(), device.connect() exception."""
        # Arrange
        expected_exception = f"MCC USB-1808X device port configuration failed."
        self._patcher_ul.new.get_board_number = Mock(return_value=0)
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name="mockerson", unique_id=self._mock_name
        )
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[test_descriptor]):
            with self.assertRaises(Exception) as exc:
                self.instr.open()

            # Assert
            self.assertEqual(expected_exception, str(exc.exception))

        self._patcher_ul.new.create_daq_device.assert_called_once_with(self._board_id, test_descriptor)
        self._patcher_ul.new.get_board_number.assert_called_with(test_descriptor)
        self._patcher_ul.new.release_daq_device.assert_called_once_with(self._board_id)

    def test_open_create_daq_device_error(self):
        """MCC_USB1808X.open(), device.create_daq_device() exception."""
        # Arrange
        expected_exception = f"MCC USB-1808X device port configuration failed."
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name="mockerson", unique_id=self._mock_name
        )
        self._patcher_ul.new.create_daq_device = Mock(side_effect=[Exception])
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[test_descriptor]):
            with self.assertRaises(Exception) as exc:
                self.instr.open()

            # Assert
            self.assertEqual(expected_exception, str(exc.exception))

        self._patcher_ul.new.create_daq_device.assert_called_once_with(self._board_id, test_descriptor)
        self._patcher_ul.new.release_daq_device.assert_called_once_with(self._board_id)

    def test_close(self):
        """MCC_USB1808X.close(), happy flow."""
        # Arrange
        self.instr._check_is_open = Mock(return_value=True)
        self.instr._device = Mock(spec=self.win_inst_class)
        self.instr._device._unique_id = "D3ADMAU5"
        # Act
        self.instr.close()
        # Assert
        self.assertIsNone(self.instr._device)
        self.assertFalse(self.instr._is_open)

    def test_get_idn(self):
        """MCC_USB1808X.get_idn(), happy flow."""
        # Arrange
        expected_vendor = "Measurement Computing"
        expected_model = "USB-1808X"
        test_descriptor = TestUldaqDeviceDescriptor(
            product_name=expected_model, unique_id=self._mock_name
        )
        expected_version = TestDeviceConfig.version
        self._patcher_ul.new.get_config_string = Mock(return_value="1.2.3")
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_idn()

        # Assert
        self._patcher_ul.new.get_config_string.assert_called_once()
        self.assertEqual(expected_vendor, rt_val.vendor)
        self.assertEqual(expected_model, rt_val.model)
        self.assertEqual(self._mock_name, rt_val.serial)
        self.assertEqual(expected_version, rt_val.version)

    def test_get_dio_num_channels(self):
        """MCC_USB1808X.get_dio_num_channels(), happy flow."""
        # Arrange
        expected_num_channels = TestPortInfo.number_of_bits
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_dio_num_channels()

        self.device_mock.get_dio_info.assert_called_once_with()
        self.assertEqual(expected_num_channels, rt_val)
        TestDioInfo.reset_mock()

    def test_get_dio_direction(self):
        """MCC_USB1808X.get_dio_direction(), happy flow."""
        # Arrange
        expected_directions = [True, False, True, False]
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_dio_direction()

        self.device_mock.get_dio_info.assert_called_once_with()
        self._patcher_ul.new.get_config.assert_called_once()
        # OUTPUT is represented as a True, INPUT as a False
        for a in range(4):
            self.assertEqual(rt_val[a], expected_directions[a])

        TestDioInfo.reset_mock()

    def test_set_dio_direction(self):
        """MCC_USB1808X.set_dio_direction(), happy flow."""
        # Arrange
        channel_0 = 0
        channel_1 = 1
        # Act and Assert
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            self.instr.set_dio_direction(channel_0, True)
            self._patcher_ul.new.d_config_bit.assert_called_with(
                self._board_id, TestPortInfo.type, channel_0, self._patcher_enums.new.DigitalIODirection.OUT
            )
            self.instr.set_dio_direction(channel_1, False)
            self._patcher_ul.new.d_config_bit.assert_called_with(
                self._board_id, TestPortInfo.type, channel_1, self._patcher_enums.new.DigitalIODirection.IN,
            )

        TestDioInfo.reset_mock()

    def test_get_dio_input_bit(self):
        """MCC_USB1808X.get_dio_input_bit(), happy flow."""
        # Arrange
        channel = 0
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_dio_input_bit(channel)  # We return True with the mock, defined at start of file

        # Assert
        self.assertTrue(rt_val)
        self._patcher_ul.new.d_bit_in.assert_called_with(self._board_id, TestPortInfo.type, channel)
        TestDioInfo.reset_mock()

    def test_set_dio_output_bit(self):
        """MCC_USB1808X.set_dio_output_bit(), happy flow."""
        # Arrange
        channel = 0
        bit = False
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            self.instr.set_dio_output_bit(channel, bit)

        # Assert
        self._patcher_ul.new.d_bit_out.assert_called_with(
            self._board_id, TestPortInfo.type, channel, int(bit)
        )
        TestDioInfo.reset_mock()

    def test_get_ai_num_channels(self):
        """MCC_USB1808X.get_ai_num_channels(), happy flow."""
        # Arrange
        expected_no_of_channels = TestAiInfo.num_chans
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ai_num_channels()

        # Assert
        self.assertEqual(expected_no_of_channels, rt_val)
        self.device_mock.get_ai_info.assert_called_once_with()
        TestAiInfo.reset_mock()

    def test_get_ai_ranges(self):
        """MCC_USB1808X.get_ai_ranges(), happy flow."""
        # Arrange
        expected_ranges = ["small_range", "medium_range", "large_range"]
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ai_ranges()

        # Assert
        self.assertListEqual(expected_ranges, rt_val)
        self.device_mock.get_ai_info.assert_called_once_with()
        TestAiInfo.reset_mock()

    def test_get_ai_value(self):
        """MCC_USB1808X.get_ai_value(), happy flow."""
        # Arrange
        channel = 5
        input_mode = "DIFFERENTIAL"  # Not used actually on Windows version
        analog_range = "medium_range"
        expected_value = 12345
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ai_value(channel, input_mode, analog_range)

        # Assert
        self.assertEqual(expected_value, rt_val)
        self._patcher_ul.new.a_in.assert_called_once_with(
            self._board_id, channel, self._patcher_enums.new.ULRange[analog_range]
        )
        TestAiInfo.reset_mock()

    def test_get_ao_num_channels(self):
        """MCC_USB1808X.get_ao_num_channels(), happy flow."""
        # Arrange
        expected_no_of_channels = TestAoInfo.num_chans
        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ao_num_channels()

        # Assert
        self.assertEqual(expected_no_of_channels, rt_val)
        self.device_mock.get_ao_info.assert_called_once_with()
        TestAoInfo.reset_mock()

    def test_get_ao_ranges(self):
        """MCC_USB1808X.get_ao_ranges(), happy flow."""
        # Arrange
        expected_ranges = ["small_range", "medium_range", "large_range"]

        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            rt_val = self.instr.get_ao_ranges()

        # Assert
        self.assertListEqual(expected_ranges, rt_val)
        self.device_mock.get_ao_info.assert_called_once_with()
        TestAoInfo.reset_mock()

    def test_set_ao_value(self):
        """MCC_USB1808X.set_ao_value(), happy flow."""
        # Arrange
        channel = 1
        analog_range = "medium_range"
        expected_value = 54321
        v_range = TestRanges.range_max - TestRanges.range_min
        resolution = 2**qmi.instruments.mcc.usb1808x.ADC_CONVERTER_RESOLUTION
        # + 1 to expected value as the documentation says:
        #  "Must be in the range 0-n, where n is the value 2**Resolution – 1 of the converter."
        input_value = v_range * (expected_value + 1 - resolution / 2) / resolution

        # Act
        with patch("qmi.instruments.mcc.usb1808x.ul.get_daq_device_inventory", return_value=[self._test_descriptor]):
            self.instr.open()
            self.instr.set_ao_value(channel, analog_range, input_value)

        # Assert
        self._patcher_ul.new.a_out.assert_called_once_with(
            self._board_id, channel, TestRanges(analog_range), expected_value
        )
        TestAoInfo.reset_mock()
