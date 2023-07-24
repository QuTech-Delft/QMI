"""Test for the USB1808x driver."""
import struct

from math import isnan

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast

from dataclasses import dataclass


from qmi.core.transport import QMI_Transport
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.instruments.mcc.usb1808x import MCC_USB1808X
from qmi.core.exceptions import QMI_InstrumentException


@dataclass
class TestMeta:
    """Test meta data."""

    name: MagicMock
    id: MagicMock
    uldaq: MagicMock
    super: MagicMock
    import_module: MagicMock
    instr: MCC_USB1808X


@dataclass
class TestDeviceMeta:
    """Test device data."""

    descriptor: MagicMock
    device: MagicMock
    dio_device: MagicMock
    ai_device: MagicMock
    ao_device: MagicMock


@dataclass
class TestUldaqDeviceDescriptor:
    """Test device descriptor data."""

    product_name: str
    unique_id: MagicMock()


class TestMCC_USB1808X(TestCase):
    """Testcase for the MCC_USB1808X class.

    Decided not to check assertions for self._device and self._*_device in
    every function. These assertions are unnesecary in the code of the
    USB1808x driver, self._check_is_open() already covers this check.
    """

    def setUp(self):
        mock_name = MagicMock()
        mock_id = MagicMock()
        mock_uldaq = MagicMock()
        mock_super = MagicMock()
        mock_import_module = MagicMock()

        self._patcher_import_module = patch(
            "qmi.instruments.mcc.usb1808x._import_modules",
            mock_import_module,
        )
        self._patcher_import_module.start()

        self._patcher_uldaq = patch("qmi.instruments.mcc.usb1808x.uldaq", mock_uldaq)
        self._patcher_uldaq.start()

        instr = MCC_USB1808X(MagicMock(), mock_name, mock_id)

        self._patcher_super = patch("qmi.instruments.mcc.usb1808x.super", mock_super)
        self._patcher_super.start()

        self._meta = TestMeta(
            instr=cast(MCC_USB1808X, instr),
            name=mock_name,
            id=mock_id,
            uldaq=mock_uldaq,
            super=mock_super,
            import_module=mock_import_module,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_import_module.stop()
        self._patcher_uldaq.stop()
        self._patcher_super.stop()

    def test_init(self):
        """MCC_USB1808X.__init__(), happy flow."""
        self._meta.import_module.assert_called_once_with()

    def test_list_instruments(self):
        """MCC_USB1808X.list_instruments(), happy flow."""
        mock_unique_id_1 = MagicMock()
        mock_unique_id_2 = MagicMock()
        mock_unique_id_3 = MagicMock()
        mock_resp = [
            TestUldaqDeviceDescriptor("USB-1808X", mock_unique_id_1),
            TestUldaqDeviceDescriptor("NOT", mock_unique_id_2),
            TestUldaqDeviceDescriptor("USB-1808X", mock_unique_id_3),
        ]

        self._meta.uldaq.get_daq_device_inventory = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.list_instruments()
        self._meta.import_module.assert_has_calls([call(), call()])
        self._meta.uldaq.get_daq_device_inventory.assert_called_once_with(
            self._meta.uldaq.InterfaceType.USB
        )
        self.assertEqual(rt_val[0], mock_unique_id_1)
        self.assertEqual(rt_val[1], mock_unique_id_3)

    def _mock_device(self):
        """Initializes self._meta.uldaq with a mocked device."""
        mock_descriptor = TestUldaqDeviceDescriptor("USB-1808X", self._meta.id)
        self._meta.uldaq.get_daq_device_inventory = MagicMock(
            return_value=[mock_descriptor]
        )

        mock_device = MagicMock()
        self._meta.uldaq.DaqDevice = MagicMock(return_value=mock_device)

        mock_dio_device = MagicMock()
        mock_ai_device = MagicMock()
        mock_ao_device = MagicMock()
        mock_device.get_dio_device = MagicMock(return_value=mock_dio_device)
        mock_device.get_ai_device = MagicMock(return_value=mock_ai_device)
        mock_device.get_ao_device = MagicMock(return_value=mock_ao_device)

        return TestDeviceMeta(
            descriptor=mock_descriptor,
            device=mock_device,
            dio_device=mock_dio_device,
            ai_device=mock_ai_device,
            ao_device=mock_ao_device,
        )

    def test_open(self):
        """MCC_USB1808X.open(), happy flow."""
        self._meta.instr._check_is_closed = MagicMock()

        device_meta = self._mock_device()

        self._meta.instr.open()

        self._meta.instr._check_is_closed.assert_called_once_with()
        device_meta.device.connect.assert_called_once_with()
        self._meta.uldaq.DaqDevice.assert_called_once_with(device_meta.descriptor)
        self.assertEqual(self._meta.instr._device, device_meta.device)
        self.assertEqual(self._meta.instr._dio_device, device_meta.dio_device)
        self.assertEqual(self._meta.instr._ai_device, device_meta.ai_device)
        self.assertEqual(self._meta.instr._ao_device, device_meta.ao_device)
        self._meta.super().open.assert_called_once_with()

    def test_open_no_device(self):
        """MCC_USB1808X.open(), no device found exception."""
        self._meta.instr._check_is_closed = MagicMock()

        device_meta = self._mock_device()
        device_meta.descriptor.product_name = "NOT"
        device_meta.descriptor.id = "NOT"

        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.open()

    def test_open_connect_error(self):
        """MCC_USB1808X.open(), device.connect() exception."""
        self._meta.instr._check_is_closed = MagicMock()

        device_meta = self._mock_device()
        device_meta.device.connect = MagicMock(side_effect=Exception)

        with self.assertRaises(Exception):
            self._meta.instr.open()

        device_meta.device.release.assert_called_once_with()

    def test_open_device_get_dio_device_error(self):
        """MCC_USB1808X.open(), device.get_dio_device() exception."""
        self._meta.instr._check_is_closed = MagicMock()

        device_meta = self._mock_device()
        device_meta.device.get_dio_device = MagicMock(side_effect=Exception)

        with self.assertRaises(Exception):
            self._meta.instr.open()

        device_meta.device.disconnect.assert_called_once_with()
        device_meta.device.release.assert_called_once_with()

    def test_close(self):
        """MCC_USB1808X.close(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr._device = (
            device_meta.device
        )  # want to make sure disconnect and release arent called through open() thus set the device directly.
        self._meta.instr.close()
        device_meta.device.disconnect.assert_called_once_with()
        device_meta.device.release.assert_called_once_with()
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_get_idn(self):
        """MCC_USB1808X.get_idn(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        rt_val = self._meta.instr.get_idn()
        self._meta.instr._check_is_open.assert_called_once_with()
        device_meta.device.get_config().get_version.assert_called_once_with(
            self._meta.uldaq.DevVersionType.FW_MAIN
        )
        self.assertEqual(rt_val.vendor, "Measurement Computing")
        self.assertEqual(rt_val.model, device_meta.device.get_descriptor().product_name)
        self.assertEqual(rt_val.serial, device_meta.device.get_descriptor().unique_id)
        self.assertEqual(rt_val.version, device_meta.device.get_config().get_version())

    def test_dio_num_channels(self):
        """MCC_USB1808X.get_dio_num_channels(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        rt_val = self._meta.instr.get_dio_num_channels()
        device_meta.dio_device.get_info.assert_called_once_with()
        device_meta.dio_device.get_info().get_port_info.assert_called_once_with(
            self._meta.uldaq.DigitalPortType.AUXPORT
        )
        self.assertEqual(
            rt_val, device_meta.dio_device.get_info().get_port_info().number_of_bits
        )
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_dio_direction(self):
        """MCC_USB1808X.get_dio_direction(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_directions = [
            self._meta.uldaq.DigitalDirection.OUTPUT,
            self._meta.uldaq.DigitalDirection.INPUT,
            self._meta.uldaq.DigitalDirection.OUTPUT,
        ]
        device_meta.dio_device.get_config().get_port_direction = MagicMock(
            return_value=mock_directions
        )
        device_meta.dio_device.get_config.reset_mock()
        rt_val = self._meta.instr.get_dio_direction()
        device_meta.dio_device.get_config.assert_called_once_with()
        device_meta.dio_device.get_config().get_port_direction.assert_called_once_with(
            self._meta.uldaq.DigitalPortType.AUXPORT
        )
        # OUTPUT is represented as a True, INPUT as a False
        self.assertEqual(rt_val[0], True)
        self.assertEqual(rt_val[1], False)
        self.assertEqual(rt_val[2], True)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_set_dio_direction(self):
        """MCC_USB1808X.set_dio_direction(), happy flow."""
        device_meta = self._mock_device()
        self._meta.instr.open()
        map = [
            {"output": True, "direction": self._meta.uldaq.DigitalDirection.OUTPUT},
            {"output": False, "direction": self._meta.uldaq.DigitalDirection.INPUT},
        ]
        for item in map:
            self._meta.instr._check_is_open = MagicMock()
            mock_channel = MagicMock()
            mock_output = item["output"]
            device_meta.dio_device.d_config_bit = MagicMock()
            self._meta.instr.set_dio_direction(mock_channel, mock_output)
            device_meta.dio_device.d_config_bit(
                self._meta.uldaq.DigitalPortType.AUXPORT,
                mock_channel,
                item["direction"],
            )
            self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_dio_input_bit(self):
        """MCC_USB1808X.get_dio_input_bit(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_channel = MagicMock()
        rt_val = self._meta.instr.get_dio_input_bit(mock_channel)
        self.assertEqual(
            rt_val,
            device_meta.dio_device.d_bit_in(
                self._meta.uldaq.DigitalPortType.AUXPORT, mock_channel
            ),
        )
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_set_dio_output_bit(self):
        """MCC_USB1808X.set_dio_output_bit(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_channel = MagicMock()
        mock_value = MagicMock()
        self._meta.instr.set_dio_output_bit(mock_channel, mock_value)
        device_meta.dio_device.d_bit_out.assert_called_once_with(
            self._meta.uldaq.DigitalPortType.AUXPORT, mock_channel, mock_value
        )
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_ai_num_channels(self):
        """MCC_USB1808X.get_ai_num_channels(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        rt_val = self._meta.instr.get_ai_num_channels()
        device_meta.ai_device.get_info.assert_called_once_with()
        device_meta.ai_device.get_info().get_num_chans.assert_called_once_with()
        self.assertEqual(rt_val, device_meta.ai_device.get_info().get_num_chans())
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_ai_ranges(self):
        """MCC_USB1808X.get_ai_ranges(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_resp = [MagicMock(), MagicMock(), MagicMock()]
        device_meta.ai_device.get_info().get_ranges = MagicMock(return_value=mock_resp)
        device_meta.ai_device.get_info.reset_mock()
        rt_val = self._meta.instr.get_ai_ranges()
        device_meta.ai_device.get_info.assert_called_once_with()
        device_meta.ai_device.get_info().get_ranges.assert_called_once_with(
            self._meta.uldaq.AiChanType.VOLTAGE
        )
        self.assertEqual(rt_val[0], mock_resp[0].name)
        self.assertEqual(rt_val[1], mock_resp[1].name)
        self.assertEqual(rt_val[2], mock_resp[2].name)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_ai_value(self):
        """MCC_USB1808X.get_ai_value(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_channel = MagicMock()
        mock_input_mode = MagicMock()
        mock_analog_range = MagicMock()
        rt_val = self._meta.instr.get_ai_value(
            mock_channel, mock_input_mode, mock_analog_range
        )
        self.assertEqual(
            rt_val,
            device_meta.ai_device.a_in(
                mock_channel,
                self._meta.uldaq.AiInputMode[mock_input_mode],
                self._meta.uldaq.Range[mock_analog_range],
                self._meta.uldaq.AInFlag.DEFAULT,
            ),
        )
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_ao_num_channels(self):
        """MCC_USB1808X.get_ao_num_channels(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        rt_val = self._meta.instr.get_ao_num_channels()
        device_meta.ao_device.get_info.assert_called_once_with()
        device_meta.ao_device.get_info().get_num_chans.assert_called_once_with()
        self.assertEqual(rt_val, device_meta.ao_device.get_info().get_num_chans())
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_ao_ranges(self):
        """MCC_USB1808X.get_ao_ranges(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_resp = [MagicMock(), MagicMock(), MagicMock()]
        device_meta.ao_device.get_info().get_ranges = MagicMock(return_value=mock_resp)
        device_meta.ao_device.get_info.reset_mock()
        rt_val = self._meta.instr.get_ao_ranges()
        device_meta.ao_device.get_info.assert_called_once_with()
        device_meta.ao_device.get_info().get_ranges.assert_called_once_with()
        self.assertEqual(rt_val[0], mock_resp[0].name)
        self.assertEqual(rt_val[1], mock_resp[1].name)
        self.assertEqual(rt_val[2], mock_resp[2].name)
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_set_ao_value(self):
        """MCC_USB1808X.set_ao_value(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        device_meta = self._mock_device()
        self._meta.instr.open()
        mock_channel = MagicMock()
        mock_analog_range = MagicMock()
        mock_value = MagicMock()
        self._meta.instr.set_ao_value(mock_channel, mock_analog_range, mock_value)
        device_meta.ao_device.a_out.assert_called_once_with(
            mock_channel,
            self._meta.uldaq.Range[mock_analog_range],
            self._meta.uldaq.AOutFlag.DEFAULT,
            mock_value,
        )
        self._meta.instr._check_is_open.assert_called_once_with()
