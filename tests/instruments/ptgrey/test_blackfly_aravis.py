import unittest
from unittest.mock import MagicMock, patch
import logging
from typing import cast

import numpy as np

import qmi
from qmi.core.context import QMI_Context
from qmi.core.exceptions import (
    QMI_InstrumentException,
    QMI_UsageException,
    QMI_TimeoutException,
)
from qmi.instruments.ptgrey import Flir_Blackfly_Aravis
import qmi.instruments.ptgrey.blackfly_aravis as ba
import tests.instruments.ptgrey.aravis_stub as Aravis


class Region:
    # The returned items from Aravis.Camera.get_region are pointers,
    # not using a specific type. These pointers refer to non-existing
    # in-memory camera, thus using a stubbed Region class.
    x = None
    y = None
    width = None
    height = None


class TestPtGreyBlackFly(unittest.TestCase):
    def _create_instr_obj(self):
        """Create a PtGeyBlackFlyAravis object using an serial_number."""
        instr: Flir_Blackfly_Aravis = Flir_Blackfly_Aravis(
            QMI_Context("context"),
            "name",
            "SerialNumber",
            None,
        )
        return instr

    def _create_instr_ser(self):
        """Create a PtGeyBlackFlyAravis instrument using a serial_number."""
        instr: Flir_Blackfly_Aravis = qmi.make_instrument(
            "name",
            Flir_Blackfly_Aravis,
            "SerialNumber",
            None,
        )
        instr = cast(Flir_Blackfly_Aravis, instr)
        return instr

    def _create_instr_ip(self):
        """Create a PtGeyBlackFlyAravis instrument using an ip_address."""
        instr: Flir_Blackfly_Aravis = qmi.make_instrument(
            "name",
            Flir_Blackfly_Aravis,
            None,
            "10.10.10.10",
        )
        instr = cast(Flir_Blackfly_Aravis, instr)
        return instr

    def _get_feature(self, feat):
        """Retrieves a MagicMock specced to the expected type that
        is mapped to a feature name."""
        return self.feature_map[feat]

    def setUp(self):
        logging.getLogger("qmi.instruments.ptgrey.blackfly_aravis").setLevel(logging.CRITICAL)
        qmi.start("TestContext")
        ba.Aravis = self.aravis = MagicMock(spec=Aravis)

        # Most of these are slight guess work, for now this is not an issue.
        # Might want to validate whether the spec's match the expected type.
        self.feature_map = {
            "DeviceReset": MagicMock(spec=Aravis.GcCommand),
            "DeviceSerialNumber": MagicMock(spec=Aravis.GcRegisterNode),
            "DeviceVersion": MagicMock(spec=Aravis.GcRegisterNode),
            "AcquisitionFrameRateAuto": MagicMock(spec=Aravis.GcEnumeration),
            "AcquisitionFrameRateEnabled": MagicMock(spec=Aravis.GcBoolean),
            "ExposureMode": MagicMock(spec=Aravis.GcEnumeration),
            "ChunkSelector": MagicMock(spec=Aravis.GcEnumeration),
            "ChunkEnable": MagicMock(spec=Aravis.GcBoolean),
            "DeviceTemperature": MagicMock(spec=Aravis.GcIntegerNode),
            "TransmitFailureCount": MagicMock(spec=Aravis.GcIntegerNode),
            "BlackLevel": MagicMock(spec=Aravis.GcIntegerNode),
            "DeviceIndicatorMode": MagicMock(spec=Aravis.GcEnumeration),
            "DeviceModelName": MagicMock(spec=Aravis.GcRegisterNode),
            "DeviceID": MagicMock(spec=Aravis.GcRegisterNode),
            "DeviceFirmwareVersion": MagicMock(spec=Aravis.GcRegisterNode),
            "DeviceVendorName": MagicMock(spec=Aravis.GcRegisterNode),
            "pgrPowerSupplyVoltage": MagicMock(spec=Aravis.GcFloatNode),
            "pgrPowerSupplyCurrent": MagicMock(spec=Aravis.GcFloatNode),
            "pgrSensorDescription": MagicMock(spec=Aravis.GcRegisterDescriptionNode),
        }

    def tearDown(self) -> None:
        qmi.stop()
        logging.getLogger("qmi.instruments.ptgrey.blackfly_aravis").setLevel(logging.NOTSET)

    def test_open_ser(self):
        """Test whether a camera is found using a serial number."""
        instr = self._create_instr_ser()
        self.aravis.get_n_devices = MagicMock(return_value=1)
        self.aravis.get_device_serial_nbr = MagicMock(return_value="SerialNumber")
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.13")
        instr.open()
        self.aravis.Camera.new.assert_called_once_with(self.aravis.get_device_id(1))
        instr.close()

    def test_open_ser_multiple(self):
        """Test whether the correct serial number camera is selected from a list of cameras."""
        instr = self._create_instr_ser()
        self.aravis.get_n_devices = MagicMock(return_value=3)
        self.aravis.get_device_serial_nbr = MagicMock(
            side_effect=[
                "BadSerial1",
                "BadSerial2",
                "SerialNumber",
            ],
        )
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.13")
        instr.open()
        self.aravis.Camera.new.assert_called_once_with(self.aravis.get_device_id(1))
        instr.close()

    def test_open_ip(self):
        """Test whether a camera is found using a ip address."""
        instr = self._create_instr_ip()
        self.aravis.get_n_devices = MagicMock(return_value=1)
        self.aravis.get_device_serial_nbr = MagicMock(return_value="BadSerial")
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.10")
        instr.open()
        self.aravis.Camera.new.assert_called_once_with(self.aravis.get_device_id(1))
        instr.close()

    def test_open_ip_multiple(self):
        """Test whether the correct ip address camera is selected from a list of cameras."""
        instr = self._create_instr_ip()
        self.aravis.get_n_devices = MagicMock(return_value=3)
        self.aravis.get_device_serial_nbr = MagicMock(return_value="BadSerial")
        self.aravis.get_device_address = MagicMock(
            side_effect=[
                "10.10.10.11",
                "10.10.10.12",
                "10.10.10.10",
            ],
        )
        instr.open()
        self.aravis.Camera.new.assert_called_once_with(self.aravis.get_device_id(1))
        instr.close()

    def test_open_no_cam(self):
        """Test whether an exception is raised when no cameras are found."""
        instr = self._create_instr_ser()
        self.aravis.get_n_devices = MagicMock(return_value=1)
        self.aravis.get_device_serial_nbr = MagicMock(return_value="BadSerial")
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.13")
        with self.assertRaises(QMI_InstrumentException):
            instr.open()

    def test_open_duplicate(self):
        """Test whether an exception is raised duplicate cameras are found."""
        instr = self._create_instr_ser()
        self.aravis.get_n_devices = MagicMock(return_value=3)
        self.aravis.get_device_serial_nbr = MagicMock(
            side_effect=[
                "SerialNumber",
                "SerialNumber",
                "SerialNumber",
            ],
        )
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.13")
        with self.assertRaises(QMI_InstrumentException):
            instr.open()

    def test_close(self):
        """Test the close function of a camera."""
        instr = self._create_instr_ser()
        c = self.aravis.Camera
        self.aravis.get_n_devices = MagicMock(return_value=1)
        self.aravis.get_device_serial_nbr = MagicMock(return_value="SerialNumber")
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.13")
        self.aravis.Camera.new = MagicMock(return_value=c)
        instr.open()
        instr.close()
        c.stop_acquisition.assert_called_with()

    def _instr_create_camera(self):
        """Create a camera and allow it to be found when PtGreyBlackFly.open
        is called. PtGreyBlackFly containing the correct serial number or ip address."""
        camera = MagicMock(spec=Aravis.Camera)
        self.aravis.get_device_serial_nbr = MagicMock(return_value="SerialNumber")
        self.aravis.get_device_address = MagicMock(return_value="10.10.10.13")
        self.aravis.get_device_serial_nbr = MagicMock(return_value="SerialNumber")
        self.aravis.Camera.new = MagicMock(return_value=camera)
        return camera

    def _instr_open_obj(self):
        """Create PtGreyBlackFly object and a camera with the same SerialNumber.
        Open the object."""
        instr = self._create_instr_obj()
        camera = self._instr_create_camera()
        instr.open()
        return instr, camera

    def _instr_open(self):
        """Create PtGreyBlackFly instrument and a camera with the same SerialNumber.
        Open the instrument."""
        instr = self._create_instr_ser()
        camera = self._instr_create_camera()
        instr.open()
        return instr, camera

    def _create_device(self):
        """Mock a Aravis.GvDevice and attach the self._get_feature function
        to its .get_feature side_effect. This results in the same functionality
        that is expected from the device library. Features can be collected
        with self._get_feature by string, and by string they'll be identical."""
        device = MagicMock(Aravis.GvDevice)
        device.get_feature = MagicMock(side_effect=self._get_feature)
        return device

    def test_reset(self):
        """Test PtGreyBlackFly.reset()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        with patch("qmi.instruments.ptgrey.blackfly_aravis.time.sleep", MagicMock()):
            instr.reset()
            self._get_feature("DeviceReset").execute.assert_called_once_with()
            instr.close()

    def test_get_idn(self):
        """Test PtGreyBlackFly.get_idn()."""
        instr, camera = self._instr_open()
        device = self._create_device()

        camera.get_device = MagicMock(return_value=device)
        i = instr.get_idn()
        self.assertEqual(i.vendor, camera.get_vendor_name())
        self.assertEqual(i.model, camera.get_model_name())
        self.assertEqual(
            i.serial, self._get_feature("DeviceSerialNumber").get_value_as_string()
        )
        self.assertEqual(
            i.version, self._get_feature("DeviceVersion").get_value_as_string()
        )
        instr.close()

    def test_get_ip_address(self):
        """Test PtGreyBlackFly.get_ip_address()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        address = MagicMock(spec=Aravis.Address)
        inetaddress = MagicMock(spec=Aravis.InetAddress)
        device.get_device_address = MagicMock(return_value=address)
        camera.get_device = MagicMock(return_value=device)
        address.get_address = MagicMock(return_value=inetaddress)
        i = instr.get_ip_address()
        self.assertEqual(i, address.get_address().to_string())
        instr.close()

    def test_get_device_info(self):
        """Test PtGreyBlackFly.get_device_info()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        i = instr.get_device_info()
        for key in i:
            self.assertEqual(
                i[key],
                self._get_feature(key).get_value_as_string(),
                msg=f"{key} values are not equal",
            )
        instr.close()

    def test_get_device_info_gdouble(self):
        """Test PtGreyBlackFly.get_device_info() where DeviceVendorName is a gdouble.
        This is a mocked, the real scenario likely does not have DeviceVendorName as a gdouble.
        """
        instr, camera = self._instr_open()
        device = self._create_device()
        feature = self._get_feature("DeviceVendorName")
        v = MagicMock()
        v.name = "gdouble"
        camera.get_device = MagicMock(return_value=device)
        feature.get_value_type = MagicMock(return_value=v)
        i = instr.get_device_info()
        self.assertEqual(i["DeviceVendorName"], feature.get_value())
        instr.close()

    def test_get_frame_rate(self):
        """Test PtGreyBlackFly.get_frame_rate()."""
        instr, camera = self._instr_open()
        f = instr.get_frame_rate()
        self.assertEqual(f, camera.get_frame_rate())
        instr.close()

    def test_get_frame_rate_auto(self):
        """Test PtGreyBlackFly.get_frame_rate_auto()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        f = instr.get_frame_rate_auto()
        self.assertEqual(
            f, self._get_feature("AcquisitionFrameRateAuto").get_string_value()
        )
        instr.close()

    def test_set_frame_rate(self):
        """Test PtGreyBlackFly.set_frame_rate()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        r = MagicMock()
        a = MagicMock()
        instr.set_frame_rate(r, a)
        self._get_feature(
            "AcquisitionFrameRateEnabled"
        ).set_value.assert_called_once_with(True)
        self._get_feature(
            "AcquisitionFrameRateAuto"
        ).set_string_value.assert_called_once_with(a)
        camera.set_frame_rate(r)
        instr.close()

    def test_get_gain(self):
        """Test PtGreyBlackFly.get_gain()."""
        instr, camera = self._instr_open()
        g = instr.get_gain()
        self.assertEqual(g, camera.get_gain())
        instr.close()

    def test_get_gain_auto(self):
        """Test PtGreyBlackFly.get_gain_auto()."""
        instr, camera = self._instr_open()
        g = instr.get_gain_auto()
        self.assertEqual(g, self.aravis.Auto.to_string(camera.get_gain_auto()))
        instr.close()

    def test_set_gain(self):
        """Test PtGreyBlackFly.set_gain()."""
        instr, camera = self._instr_open()
        g = MagicMock()
        a = MagicMock()
        instr.set_gain(g, a)
        camera.set_gain_auto.assert_called_once_with(self.aravis.Auto.from_string(a))
        camera.set_gain.assert_called_once_with(g)
        instr.close()

    def test_get_exposure_mode(self):
        """Test PtGreyBlackFly.get_exposure_mode()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        e = instr.get_exposure_mode()
        self.assertEqual(e, self._get_feature("ExposureMode").get_string_value())
        instr.close()

    def test_set_exposure_mode(self):
        """Test PtGreyBlackFly.set_exposure_mode()."""
        instr, camera = self._instr_open()
        device = self._create_device()

        camera.get_device = MagicMock(return_value=device)
        m = MagicMock()
        instr.set_exposure_mode(m)
        self._get_feature("ExposureMode").set_string_value.assert_called_once_with(m)
        instr.close()

    def test_get_exposure_time(self):
        """Test PtGreyBlackFly.get_exposure_time()."""
        instr, camera = self._instr_open()
        e = instr.get_exposure_time()
        self.assertEqual(e, camera.get_exposure_time())
        instr.close()

    def test_get_exposure_time_auto(self):
        """Test PtGreyBlackFly.get_exposure_time_auto()."""
        instr, camera = self._instr_open()
        e = instr.get_exposure_time_auto()
        self.assertEqual(e, self.aravis.Auto.to_string(camera.get_exposure_time_auto()))
        instr.close()

    def test_set_exposure_time(self):
        """Test PtGreyBlackFly.set_exposure_time()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        e = MagicMock()
        a = MagicMock()
        instr.set_exposure_time(e, a)
        camera.set_exposure_time_auto.assert_called_once_with(
            self.aravis.Auto.from_string(a)
        )
        camera.set_exposure_time(e)
        instr.close()

    def test_get_pixel_format(self):
        """Test PtGreyBlackFly.get_pixel_format()."""
        instr, camera = self._instr_open()
        with patch.object(
            camera,
            "get_pixel_format",
            side_effect=[
                self.aravis.PIXEL_FORMAT_MONO_8,
                self.aravis.PIXEL_FORMAT_MONO_16,
                self.aravis.PIXEL_FORMAT_MONO_12_PACKED,
            ],
        ):
            p1 = instr.get_pixel_format()
            p2 = instr.get_pixel_format()
            p3 = instr.get_pixel_format()
            self.assertEqual(p1, "Mono8")
            self.assertEqual(p2, "Mono16")
            self.assertEqual(p3, "Mono12Packed")
        instr.close()

    def test_get_pixel_format_invalid(self):
        """Test PtGreyBlackFly.get_pixel_format_invalid()."""
        instr, camera = self._instr_open()
        with patch.object(
            camera,
            "get_pixel_format",
            return_value=0xBEEFCAFE,
        ):
            with self.assertRaises(ValueError):
                instr.get_pixel_format()
        instr.close()

    def test_set_pixel_format(self):
        """Test PtGreyBlackFly.set_pixel_format()."""
        instr, camera = self._instr_open()
        instr.set_pixel_format("Mono8")
        camera.set_pixel_format.assert_called_once_with(self.aravis.PIXEL_FORMAT_MONO_8)
        camera.set_pixel_format.reset_mock()
        instr.set_pixel_format("Mono16")
        camera.set_pixel_format.assert_called_once_with(
            self.aravis.PIXEL_FORMAT_MONO_16
        )
        camera.set_pixel_format.reset_mock()
        instr.set_pixel_format("Mono12Packed")
        camera.set_pixel_format.assert_called_once_with(
            self.aravis.PIXEL_FORMAT_MONO_12_PACKED
        )
        camera.set_pixel_format.reset_mock()
        instr.close()

    def test_set_pixel_format_invalid(self):
        """Test PtGreyBlackFly.set_pixel_format_invalid()."""
        instr, _ = self._instr_open()
        with self.assertRaises(ValueError):
            instr.set_pixel_format("INVALID!!!!")
        instr.close()

    def test_get_image_size(self):
        """Test PtGreyBlackFly.get_image_size()."""
        instr, camera = self._instr_open()
        r = Region
        with patch.object(
            camera,
            "get_region",
            return_value=r,
        ):
            w, h = instr.get_image_size()
            self.assertEqual(w, r.width)
            self.assertEqual(h, r.height)
        instr.close()

    def test_set_image_size(self):
        """Test PtGreyBlackFly.set_image_size()."""
        instr, camera = self._instr_open()
        r = Region
        with patch.object(
            camera,
            "get_region",
            return_value=r,
        ):
            w = MagicMock()
            h = MagicMock()
            instr.set_image_size(w, h)
            camera.set_region.assert_called_once_with(r.x, r.y, w, h)
        instr.close()

    def test_get_image_offset(self):
        """Test PtGreyBlackFly.get_image_offset()."""
        instr, camera = self._instr_open()
        r = Region
        with patch.object(
            camera,
            "get_region",
            return_value=r,
        ):
            x, y = instr.get_image_offset()
            self.assertEqual(x, r.x)
            self.assertEqual(y, r.y)
        instr.close()

    def test_set_image_offset(self):
        """Test PtGreyBlackFly.set_image_offset()."""
        instr, camera = self._instr_open()
        r = Region
        with patch.object(
            camera,
            "get_region",
            return_value=r,
        ):
            x = MagicMock()
            y = MagicMock()
            instr.set_image_offset(x, y)
            camera.set_region.assert_called_once_with(x, y, r.width, r.height)
        instr.close()

    def test_get_chunk_mode(self):
        """Test PtGreyBlackFly.get_chunk_mode()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        feature = self._get_feature("ChunkSelector")
        s = MagicMock()
        camera.get_device = MagicMock(return_value=device)
        feature.get_available_string_values = MagicMock(return_value=[s])
        a, t = instr.get_chunk_mode()
        self.assertEqual(a, camera.get_chunk_mode())
        feature.set_string_value.assert_called_once_with(s)
        self.assertEqual(t[s], self._get_feature("ChunkEnable").get_value())
        instr.close()

    def test_set_chunk_mode(self):
        """Test PtGreyBlackFly.set_chunk_mode()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        s = MagicMock()
        feature = self._get_feature("ChunkSelector")
        camera.get_device = MagicMock(return_value=device)
        feature.get_available_string_values = MagicMock(return_value=[s])
        v = MagicMock()
        instr.set_chunk_mode(v)
        device.write_register.assert_called_once_with(0x0D24, 1)
        feature.set_string_value.assert_called_once_with(s)
        self._get_feature("ChunkEnable").set_value.assert_called_once_with(True)
        instr.close()

    def test_get_device_temperature(self):
        """Test PtGreyBlackFly.get_device_temperature()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        t = instr.get_device_temperature()
        self.assertEqual(t, self._get_feature("DeviceTemperature").get_value())
        instr.close()

    def test_get_transmit_failure_count(self):
        """Test PtGreyBlackFly.get_transmit_failure_count()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        count = instr.get_transmit_failure_count()
        self.assertEqual(count, self._get_feature("TransmitFailureCount").get_value())
        instr.close()

    def test_get_black_level(self):
        """Test PtGreyBlackFly.get_black_level()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        t = instr.get_black_level()
        self.assertEqual(t, self._get_feature("BlackLevel").get_value())
        instr.close()

    def test_set_black_level(self):
        """Test PtGreyBlackFly.set_black_level()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        l = MagicMock()
        instr.set_black_level(l)
        self._get_feature("BlackLevel").set_value.assert_called_once_with(l)
        instr.close()

    def test_set_indicator_mode_enable(self):
        """Test PtGreyBlackFly.set_indicator_mode_enable()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        instr.set_indicator_mode(True)
        self._get_feature(
            "DeviceIndicatorMode"
        ).set_string_value.assert_called_once_with("Active")
        instr.close()

    def test_set_indicator_mode_disable(self):
        """Test PtGreyBlackFly.set_indicator_mode_disable()."""
        instr, camera = self._instr_open()
        device = self._create_device()
        camera.get_device = MagicMock(return_value=device)
        instr.set_indicator_mode(False)
        self._get_feature(
            "DeviceIndicatorMode"
        ).set_string_value.assert_called_once_with("Inactive")
        instr.close()

    def test_is_streaming(self):
        """Test PtGreyBlackFly.is_streaming()."""
        instr, camera = self._instr_open()
        v = instr.is_streaming()
        self.assertEqual(v, False)
        camera.get_payload = MagicMock(return_value=1)
        instr.start_acquisition(1)
        v = instr.is_streaming()
        self.assertEqual(v, True)
        instr.close()

    def test_start_acquisition(self):
        """Test PtGreyBlackFly.start_acquisition()."""
        instr, camera = self._instr_open_obj()
        s = self.aravis.Stream
        c = self.aravis.ChunkParser
        b = self.aravis.Buffer
        camera.get_payload = MagicMock(return_value=1)
        camera.create_stream = MagicMock(return_value=s)
        camera.create_chunk_parser = MagicMock(return_value=c)
        self.aravis.Buffer.new = MagicMock(return_value=b)
        with patch("qmi.instruments.ptgrey.blackfly_aravis.min", return_value=1):
            instr.start_acquisition(None)
            camera.set_acquisition_mode.assert_called_once_with(
                self.aravis.AcquisitionMode.CONTINUOUS
            )
            s.connect.assert_called_once_with("new-buffer", instr._new_image_cb)
            s.set_emit_signals.assert_called_once_with(False)
            s.push_buffer.assert_called_once_with(b)
            camera.start_acquisition.assert_called_once_with()
        instr.close()

    def test_start_acquisition_cb_enable(self):
        """Test PtGreyBlackFly.start_acquisition() with callback enabled"""
        instr, camera = self._instr_open_obj()
        s = self.aravis.Stream
        camera.get_payload = MagicMock(return_value=1)
        camera.create_stream = MagicMock(return_value=s)
        instr.register_image_callback(MagicMock())
        instr.start_acquisition(None)
        s.set_emit_signals.assert_called_once_with(True)
        instr.close()

    def test_start_acquisition_continuous(self):
        """Test PtGreyBlackFly.start_acquisition_continues()"""
        instr, camera = self._instr_open()
        camera.get_payload = MagicMock(return_value=1)
        instr.start_acquisition(None)
        camera.set_acquisition_mode.assert_called_once_with(
            self.aravis.AcquisitionMode.CONTINUOUS
        )
        instr.close()

    def test_start_acquisition_single(self):
        """Test PtGreyBlackFly.start_acquisition_single()"""
        instr, camera = self._instr_open()
        camera.get_payload = MagicMock(return_value=1)
        instr.start_acquisition(1)
        camera.set_acquisition_mode.assert_called_once_with(
            self.aravis.AcquisitionMode.SINGLE_FRAME
        )
        instr.close()

    def test_start_acquisition_multi(self):
        """Test PtGreyBlackFly.start_acquisition_multi()"""
        instr, camera = self._instr_open()
        camera.get_payload = MagicMock(return_value=1)
        instr.start_acquisition(65535)
        camera.set_acquisition_mode.assert_called_once_with(
            self.aravis.AcquisitionMode.MULTI_FRAME
        )
        camera.set_frame_count(65535)
        instr.close()

    def test_start_acquisition_invalid(self):
        """Test PtGreyBlackFly.start_acquisition() with invalid input."""
        instr, camera = self._instr_open()
        with self.assertRaises(QMI_UsageException):
            instr.start_acquisition(65537)
        instr.close()

    def test_stop_acquisition(self):
        """Test PtGreyBlackFly.stop_acquisition()."""
        instr, camera = self._instr_open()
        s = self.aravis.Stream
        camera.get_payload = MagicMock(return_value=1)
        camera.create_stream = MagicMock(return_value=s)
        instr.start_acquisition(None)
        s.set_emit_signals.reset_mock()
        instr.stop_acquisition()
        s.set_emit_signals.assert_called_once_with(False)
        camera.stop_acquisition.assert_called_once_with()
        instr.close()

    def test_get_next_image(self):
        """Test PtGreyBlackFly.get_next_image()."""
        instr, _ = self._instr_open_obj()
        s = self.aravis.Stream
        b = self.aravis.Buffer
        instr._stream = s
        instr._convert_image = MagicMock()
        s.pop_buffer = MagicMock(return_value=b)
        b.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        instr.get_next_image(None)
        s.pop_buffer.assert_called_once_with()
        instr._convert_image.assert_called_once_with(b)
        s.push_buffer.assert_called_once_with(b)
        instr.close()

    def test_get_next_image_timeout(self):
        """Test PtGreyBlackFly.get_next_image_timeout()."""
        instr, _ = self._instr_open_obj()
        s = self.aravis.Stream
        b = self.aravis.Buffer
        instr._stream = s
        instr._convert_image = MagicMock()
        s.timeout_pop_buffer = MagicMock(return_value=b)
        b.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        instr.get_next_image(100)  # Timeout is in us
        s.timeout_pop_buffer.assert_called_once_with(int(1000000 * 100))
        s.push_buffer.assert_called_once_with(b)
        instr.close()

    def test_get_next_image_no_stream(self):
        """Test PtGreyBlackFly.get_next_image_no_stream()."""
        instr, _ = self._instr_open_obj()
        with self.assertRaises(QMI_InstrumentException):
            instr.get_next_image(None)
        instr.close()

    def test_get_next_image_no_buffer(self):
        """Test PtGreyBlackFly.get_next_image_no_buffer()."""
        instr, _ = self._instr_open_obj()
        s = self.aravis.Stream
        instr._stream = s
        instr._convert_image = MagicMock()
        s.pop_buffer = MagicMock(return_value=None)
        with self.assertRaises(QMI_TimeoutException):
            instr.get_next_image(None)
        instr.close()

    def test_get_next_image_bad_status(self):
        """Test PtGreyBlackFly.get_next_image_bad_status()."""
        instr, _ = self._instr_open_obj()
        s = self.aravis.Stream
        b = self.aravis.Buffer
        instr._stream = s
        instr._convert_image = MagicMock()
        s.pop_buffer = MagicMock(return_value=b)
        b.get_status = MagicMock(return_value=self.aravis.BufferStatus.FAILURE)
        with self.assertRaises(QMI_InstrumentException):
            instr.get_next_image(None)
        instr.close()

    def test_register_image_callback(self):
        """Test PtGreyBlackFly.register_image_callback()."""
        instr, _ = self._instr_open_obj()
        s = self.aravis.Stream
        instr._stream = s
        c = MagicMock()
        instr.register_image_callback(c)
        self.assertEqual(instr._image_callbacks, [c])
        s.set_emit_signals.assert_called_once_with(True)
        instr.close()

    def test_register_image_callback_no_stream(self):
        """Test PtGreyBlackFly.register_image_callback_no_stream()."""
        instr, _ = self._instr_open_obj()
        s = self.aravis.Stream
        c = MagicMock()
        instr.register_image_callback(c)
        self.assertEqual(instr._image_callbacks, [c])
        s.set_emit_signals.assert_not_called()
        instr.close()

    def test_unregister_image_callback(self):
        """Test PtGreyBlackFly.unregister_image_callback()."""
        instr, _ = self._instr_open_obj()
        c = MagicMock()
        instr.register_image_callback(c)
        self.assertEqual(instr._image_callbacks, [c])
        instr.unregister_image_callback(c)
        self.assertEqual(instr._image_callbacks, [])
        instr.close()

    def test_unregister_image_callback_invalid(self):
        """Test PtGreyBlackFly.unregister_image_callback() invalid input."""
        instr, _ = self._instr_open_obj()
        c = MagicMock()
        with self.assertRaises(ValueError):
            instr.unregister_image_callback(c)
        instr.close()

    def test_new_image_cb(self):
        """Test PtGreyBlackFly.new_image_cb()."""
        instr, _ = self._instr_open_obj()
        b = self.aravis.Buffer
        s = self.aravis.Stream
        c = MagicMock()
        m = MagicMock()
        s.try_pop_buffer = MagicMock(return_value=b)
        b.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        instr._image_callbacks = [c]
        instr._convert_image = m
        instr._new_image_cb(s)
        c.assert_called_once_with(instr._convert_image(b))
        instr.close()

    def test_new_image_cb_no_buffer(self):
        """Test PtGreyBlackFly.new_image_cb() without buffer."""
        instr, _ = self._instr_open_obj()
        b = self.aravis.Buffer
        s = self.aravis.Stream
        s.try_pop_buffer = MagicMock(return_value=None)
        instr._new_image_cb(s)
        b.get_status.assert_not_called()
        instr.close()

    def test_new_image_cb_buf_no_suc(self):
        """Test PtGreyBlackFly.new_image_cb() without buffer success."""
        instr, _ = self._instr_open_obj()
        b = self.aravis.Buffer
        s = self.aravis.Stream
        m = MagicMock()
        s.try_pop_buffer = MagicMock(return_value=b)
        b.get_status = MagicMock(return_value=self.aravis.BufferStatus.FAILURE)
        instr._convert_image = m
        instr._new_image_cb(s)
        instr._convert_image.assert_not_called()
        instr.close()

    def test_new_image_cb_exception(self):
        """Test PtGreyBlackFly.new_image_cb() with callbakc exception."""
        instr, _ = self._instr_open_obj()
        b = self.aravis.Buffer
        s = self.aravis.Stream
        c = MagicMock(side_effect=Exception)
        m = MagicMock()
        s.try_pop_buffer = MagicMock(return_value=b)
        b.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        instr._image_callbacks = [c]
        instr._convert_image = m
        with patch(
            "qmi.instruments.ptgrey.blackfly_aravis._logger", MagicMock()
        ):  # remove exception log during unittest run.
            instr._new_image_cb(s)
            c.assert_called_once_with(instr._convert_image(b))
        instr.close()

    def test_convert_image(self):
        """Test PtGreyBlackFly.convert_image()."""
        instr, _ = self._instr_open_obj()
        parser = self.aravis.ChunkParser
        gain = MagicMock()
        black_level = MagicMock()
        exposure_time = MagicMock()
        buffer = self.aravis.Buffer
        width = 2
        height = 1

        def side_effect_get_float_value(buf, str):
            """Return a mocked float value depending on the provided string."""
            if buf is buffer:
                if str == "ChunkGain":
                    return gain
                if str == "ChunkBlackLevel":
                    return black_level
                if str == "ChunkExposureTime":
                    return exposure_time

        instr._chunk_parser = parser
        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        buffer.get_image_pixel_format = MagicMock(
            return_value=self.aravis.PIXEL_FORMAT_MONO_8
        )
        buffer.get_data = MagicMock(return_value=b"/x1/x2/x3/x4/x5")
        buffer.get_image_width = MagicMock(return_value=width)
        buffer.get_image_height = MagicMock(return_value=height)
        buffer.get_payload_type = MagicMock(
            return_value=self.aravis.BufferPayloadType.EXTENDED_CHUNK_DATA
        )
        parser.get_float_value = MagicMock(side_effect=side_effect_get_float_value)
        info = instr._convert_image(buffer)
        # Manipulate the buffer data equal to _convert_image() MONO_8.
        data = np.frombuffer(buffer.get_data(), dtype=np.uint8, count=(height * width))
        data = data.reshape((height, width))
        # Image info should be equal to that of the buffer.
        self.assertEqual(info.width, buffer.get_image_width())
        self.assertEqual(info.height, buffer.get_image_height())
        self.assertEqual(info.offset_x, buffer.get_image_x())
        self.assertEqual(info.offset_y, buffer.get_image_y())
        self.assertEqual(info.pixel_format, buffer.get_image_pixel_format())
        self.assertEqual(info.frame_id, buffer.get_frame_id())
        self.assertEqual(info.image_id, buffer.get_frame_id())
        self.assertEqual(info.timestamp, 1.0e-9 * buffer.get_timestamp())
        self.assertEqual(info.gain, gain)
        self.assertEqual(info.black_level, black_level)
        self.assertEqual(info.exposure_time, exposure_time)
        np.testing.assert_array_equal(info.data, data)
        instr.close()

    def test_convert_image_mono_16(self):
        """Test PtGreyBlackFly.convert_image() with MONO_16 format."""
        instr, _ = self._instr_open_obj()
        buffer = self.aravis.Buffer
        width = 2
        height = 1

        instr._chunk_parser = MagicMock()
        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        buffer.get_image_pixel_format = MagicMock(
            return_value=self.aravis.PIXEL_FORMAT_MONO_16
        )
        buffer.get_data = MagicMock(return_value=b"/x1/x2/x3/x4/x5")
        buffer.get_image_width = MagicMock(return_value=width)
        buffer.get_image_height = MagicMock(return_value=height)
        i = instr._convert_image(buffer)
        # Manipulate the buffer data equal to _convert_image() MONO_16.
        data = np.frombuffer(buffer.get_data(), dtype="<H", count=height * width)
        data = data.reshape((height, width))
        np.testing.assert_array_equal(i.data, data)
        instr.close()

    def test_convert_image_mono_12_packed(self):
        """Test PtGreyBlackFly.convert_image() with MONO_12_packed format."""
        instr, _ = self._instr_open_obj()
        buffer = self.aravis.Buffer
        width = 2
        height = 1

        instr._chunk_parser = MagicMock()
        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        buffer.get_image_pixel_format = MagicMock(
            return_value=self.aravis.PIXEL_FORMAT_MONO_12_PACKED
        )
        buffer.get_data = MagicMock(return_value=b"/x1/x2/x3/x4/x5")
        buffer.get_image_width = MagicMock(return_value=width)
        buffer.get_image_height = MagicMock(return_value=height)
        i = instr._convert_image(buffer)
        # Manipulate the buffer data equal to _convert_image() MONO_12_PACKED.
        tmp = np.frombuffer(
            buffer.get_data(), dtype=np.uint8, count=(height * width * 3 + 1) // 2
        )
        tmp = tmp.astype(np.uint16)
        data = np.zeros(2 * 1, dtype=np.uint16)
        data[::2] = ((tmp[1::3] & 0x0F) << 8) | tmp[0::3]
        data[1::2] = (tmp[2::3] << 4) | ((tmp[1::3] & 0xF0) >> 4)
        data = data.reshape((height, width))
        np.testing.assert_array_equal(i.data, data)
        instr.close()

    def test_convert_image_mono_invalid_pf(self):
        """Test PtGreyBlackFly.convert_image() with invalid format"""
        instr, _ = self._instr_open_obj()
        buffer = self.aravis.Buffer

        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        buffer.get_image_pixel_format = MagicMock(return_value=0xBEEFCAFE)
        with self.assertRaises(QMI_InstrumentException):
            instr._convert_image(buffer)
        instr.close()

    def test_convert_image_no_chunk_parser(self):
        """Test PtGreyBlackFly.convert_image() without parser"""
        instr, _ = self._instr_open_obj()
        buffer = self.aravis.Buffer

        instr._chunk_parser = MagicMock()
        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        buffer.get_image_pixel_format = MagicMock(
            return_value=self.aravis.PIXEL_FORMAT_MONO_12_PACKED
        )
        buffer.get_data = MagicMock(return_value=b"/x1/x2/x3/x4/x5")
        buffer.get_image_width = MagicMock(return_value=1)
        buffer.get_image_height = MagicMock(return_value=2)
        i = instr._convert_image(buffer)
        self.assertEqual(i.gain, 0)
        self.assertEqual(i.black_level, 0)
        self.assertEqual(i.exposure_time, 0)
        instr.close()

    def test_convert_image_buf_stat_fail(self):
        """Test PtGreyBlackFly.convert_image() with buffer failure."""
        instr, _ = self._instr_open_obj()
        buffer = self.aravis.Buffer

        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.FAILURE)
        with self.assertRaises(QMI_InstrumentException):
            instr._convert_image(buffer)
        instr.close()

    def test_convert_image_payload_chunk_data(self):
        """Test PtGreyBlackFly.convert_image() with invalid buffer payload type."""
        instr, _ = self._instr_open_obj()
        buffer = self.aravis.Buffer

        buffer.get_status = MagicMock(return_value=self.aravis.BufferStatus.SUCCESS)
        buffer.get_payload_type = MagicMock(
            return_value=self.aravis.BufferPayloadType.CHUNK_DATA
        )
        with self.assertRaises(QMI_InstrumentException):
            instr._convert_image(buffer)
        instr.close()

    def test_list_instrument(self):
        """Test PtGreyBlackFly.list_instruments()."""
        self.aravis.get_n_devices = MagicMock(return_value=1)
        d = Flir_Blackfly_Aravis.list_instruments()
        self.assertEqual(d[0].vendor_name, self.aravis.get_device_vendor(1))
        self.assertEqual(d[0].model_name, self.aravis.get_device_model(1))
        self.assertEqual(d[0].serial_number, self.aravis.get_device_serial_nbr(1))
        self.assertEqual(d[0].version, "")
        self.assertEqual(d[0].ip_address, self.aravis.get_device_address(1))

    def test_init_usage_exception(self):
        """Create a PtGeyBlackFlyAravis object usage exception due to invalid input."""
        with self.assertRaises(QMI_UsageException):
            Flir_Blackfly_Aravis(
                QMI_Context("context"),
                "name",
                None,
                None,
            )
