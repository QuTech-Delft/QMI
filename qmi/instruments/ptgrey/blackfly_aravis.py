"""
Instrument driver for PtGrey BlackFly cameras via the Aravis library.

This driver depends on Aravis, a free library for video acquisition
from Genicam cameras. Aravis is a C library based on GLib/GObject.

There is no Python module for Aravis.
Instead, Aravis is accessed via the GObject Introspection framework.
Therefore this driver depends on the Python module 'gi'.

Aravis works under Linux and is NOT supported on Windows.

This driver requires that Aravis is installed on the system. When installed
in a non-standard location, the directory containing libaravis-0.6.so must
be added to LD_LIBRARY_PATH.

Aravis must be compiled with introspection enabled, and the Aravis typelib
must be installed on the system. When installed in a non-standard location,
the directory containing Aravis.typelib must be added to GI_TYPELIB_PATH.
"""

import logging
import socket
import struct
import threading
import time
import typing

from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import numpy as np

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_UsageException, QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method

# Lazy import of the Aravis module. See the function _import_modules() below.
if typing.TYPE_CHECKING:
    from gi.repository import Aravis
else:
    Aravis = None


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Global mutex protecting the Aravis library.
_aravis_mutex = threading.Lock()


# Camera device information.
CameraInfo = NamedTuple('CameraInfo', [
    ('vendor_name', str),
    ('model_name', str),
    ('serial_number', str),
    ('version', str),
    ('ip_address', str)
])
CameraInfo.__doc__ = """Camera device information."""

# Image acquired from the camera.
ImageInfo = NamedTuple('ImageInfo', [
    ('width', int),
    ('height', int),
    ('offset_x', int),
    ('offset_y', int),
    ('pixel_format', str),
    ('frame_id', int),
    ('image_id', int),
    ('timestamp', float),
    ('gain', float),
    ('black_level', float),
    ('exposure_time', float),
    ('data', np.ndarray)
])
ImageInfo.__doc__ = """Image acquired from the camera.
    :ivar width: Image width in pixels.
    :ivar height: Image height in pixels.
    :ivar offset_x: X offset within sensor area in pixels.
    :ivar offset_y: Y offset within sensor area in pixels.
    :ivar pixel_format: Pixel format description (GenICam PFNC name).
    :ivar frame_id: Frame sequence number.
    :ivar image_id: Unique image ID.
    :ivar timestamp: Timestamp in seconds, or 0.0 if not present.
    :ivar gain: Analog gain in dB, or 0.0 if not present.
    :ivar black_level: Black level in percent, or 0.0 if not present.
    :ivar exposure_time: Exposure time in microseconds, or 0.0 if not present.
    :ivar data: Pixel data as a 2D Numpy array.
"""


def _import_modules() -> None:
    """Import the Aravis library.

    This import is done in a function, instead of at the top-level,
    to avoid an unnecessary dependency for programs that do not access
    the instrument directly.
    """

    global Aravis

    with _aravis_mutex:
        if Aravis is None:
            # Import Aravis introspection module via GObject Introspection
            import gi
            gi.require_version('Aravis', '0.6')
            from gi.repository import Aravis  # pylint: disable=W0621
            _logger.debug("Aravis library version: %s", Aravis._version)  # type: ignore


class PtGrey_BlackFly_Aravis(QMI_Instrument):
    """Instrument driver for PtGrey BlackFly cameras via the Aravis library.

    Although Aravis is a generic library for Genicam cameras, this driver
    is developed specifically for the PtGrey BFLY-GPE-31S4M-C camera.
    It is likely that the driver will also work with other monochrome Ethernet
    Genicam cameras. However modifications will be needed to support USB
    cameras and/or color cameras.

    The driver currently only supports basic image control settings and
    simple image acquisition.
    """

    @staticmethod
    def list_instruments() -> List[CameraInfo]:
        """Return a list of connected camera devices."""

        devices = []

        # Import Aravis.
        _import_modules()

        with _aravis_mutex:

            # Update list of cameras.
            Aravis.update_device_list()

            # Get list of cameras.
            n_devices = Aravis.get_n_devices()
            for i in range(n_devices):
                vendor_name    = Aravis.get_device_vendor(i)
                model_name     = Aravis.get_device_model(i)
                serial_number  = Aravis.get_device_serial_nbr(i)
                ip_address_str = Aravis.get_device_address(i)
                info = CameraInfo(vendor_name=vendor_name,
                                  model_name=model_name,
                                  serial_number=serial_number,
                                  version="",
                                  ip_address=ip_address_str)
                devices.append(info)

        return devices

    def __init__(self, context: QMI_Context, name: str, serial_number: Optional[str] = None, ip_address: Optional[str] = None) -> None:
        """Initialize a driver instance for the specified camera device.

        Either serial_number or ip_address should be specified.

        :argument serial_number: Serial number of camera device.
        :argument ip_address: IP address of camera device.
        """

        super().__init__(context, name)

        if (serial_number is None) and (ip_address is None):
            raise QMI_UsageException("Need either serial_number or ip_address")

        # Import Aravis module.
        _import_modules()

        # Parse IP address.
        if ip_address is None:
            ip_address_int = None
        else:
            (ip_address_int,) = struct.unpack('>I', socket.inet_aton(ip_address))

        # Store camera selection attributes.
        self._serial_number = serial_number
        self._ip_address = ip_address
        self._ip_address_int = ip_address_int

        # Camera object not yet available.
        self._cam = None           # type: Optional[Aravis.Camera]
        self._stream = None        # type: Optional[Aravis.Stream]
        self._chunk_parser = None  # type: Optional[Aravis.ChunkParser]

        # Image callback functions.
        self._image_callbacks = []  # type: List[Callable[[ImageInfo], None]]

    def _convert_image(self, buf: 'Aravis.Buffer') -> ImageInfo:
        """Convert Aravis Buffer object to an ImageInfo instance."""

        if buf.get_status() != Aravis.BufferStatus.SUCCESS:
            raise QMI_InstrumentException("Received incomplete image data")

        # Payload in CHUNK_DATA format does not contain width/height/format
        # meta-data. We can not process such images.
        if buf.get_payload_type() == Aravis.BufferPayloadType.CHUNK_DATA:
            raise QMI_InstrumentException("Received unsupported CHUNK_DATA payload")

        width = buf.get_image_width()
        height = buf.get_image_height()
        offset_x = buf.get_image_x()
        offset_y = buf.get_image_y()
        pixel_format = buf.get_image_pixel_format()
        frame_id = buf.get_frame_id()
        timestamp = buf.get_timestamp()

        # Convert to Numpy array.
        data = buf.get_data()
        if pixel_format == Aravis.PIXEL_FORMAT_MONO_8:
            pixels = np.frombuffer(data, dtype=np.uint8, count=height * width)
        elif pixel_format == Aravis.PIXEL_FORMAT_MONO_16:
            pixels = np.frombuffer(data, dtype='<H', count=height * width)
        elif pixel_format == Aravis.PIXEL_FORMAT_MONO_12_PACKED:
            tmp = np.frombuffer(data, dtype=np.uint8, count=(height * width * 3 + 1) // 2)
            tmp = tmp.astype(np.uint16)
            pixels = np.zeros(height * width, dtype=np.uint16)
            pixels[::2] = ((tmp[1::3] & 0x0f) << 8) | tmp[0::3]
            pixels[1::2] = (tmp[2::3] << 4) | ((tmp[1::3] & 0xf0) >> 4)
        else:
            raise QMI_InstrumentException("Unknown pixel format in image")

        # Reshape to 2D array.
        pixels = pixels.reshape((height, width))

        # Parse chunk data.
        assert self._chunk_parser is not None
        if buf.get_payload_type() in (Aravis.BufferPayloadType.CHUNK_DATA,
                                      Aravis.BufferPayloadType.EXTENDED_CHUNK_DATA):
            gain = self._chunk_parser.get_float_value(buf, "ChunkGain")
            black_level = self._chunk_parser.get_float_value(buf, "ChunkBlackLevel")
            exposure_time = self._chunk_parser.get_float_value(buf, "ChunkExposureTime")
        else:
            gain = 0
            black_level = 0
            exposure_time = 0

        # Convert timestamp to seconds.
        timestamp = 1.0e-9 * timestamp

        return ImageInfo(width=width,
                         height=height,
                         offset_x=offset_x,
                         offset_y=offset_y,
                         pixel_format=pixel_format,
                         frame_id=frame_id,
                         image_id=frame_id,
                         timestamp=timestamp,
                         gain=gain,
                         black_level=black_level,
                         exposure_time=exposure_time,
                         data=pixels)

    def _new_image_cb(self, stream: 'Aravis.Stream') -> None:
        """This function gets called by the Aravis library in a background
        thread when a new image is captured.
        """

        buf = stream.try_pop_buffer()
        if buf is None:
            # Image disappeared before we could handle it.
            return

        if buf.get_status() != Aravis.BufferStatus.SUCCESS:
            _logger.warning("Received incomplete image from camera %s", self._name)
            return

        # Convert image.
        img = self._convert_image(buf)

        # Re-insert buffer into stream.
        stream.push_buffer(buf)

        # Invoke custom callbacks.
        with _aravis_mutex:
            callbacks = self._image_callbacks

        for cb in callbacks:
            try:
                cb(img)
            except:
                _logger.exception("Do not let exception go up to Aravis background thread")

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection to %s serial_number=%s ip_address=%s",
                     self._name, self._serial_number, self._ip_address)
        self._check_is_closed()

        with _aravis_mutex:

            # Update list of cameras.
            Aravis.update_device_list()

            # Scan list of cameras to find our device.
            cam_selected = []
            n_devices = Aravis.get_n_devices()
            for i in range(n_devices):
                device_id         = Aravis.get_device_id(i)
                serial_number     = Aravis.get_device_serial_nbr(i)
                ip_address_str    = Aravis.get_device_address(i)
                (ip_address_int,) = struct.unpack('>I', socket.inet_aton(ip_address_str))
                if (((self._serial_number is None) or (self._serial_number == serial_number))
                        and ((self._ip_address_int is None) or (self._ip_address_int == ip_address_int))):
                    cam_selected.append(device_id)

            if not cam_selected:
                raise QMI_InstrumentException("No camera found matching serial_number={} ip_address={}"
                                              .format(self._serial_number, self._ip_address))
            if len(cam_selected) != 1:
                raise QMI_InstrumentException("Multiple cameras found matching serial_number={} ip_address={}"
                                              .format(self._serial_number, self._ip_address))

            # Open camera device.
            self._cam = Aravis.Camera.new(cam_selected[0])

        # Mark instrument as open.
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to %s", self._name)
        self._check_is_open()
        assert self._cam is not None

        # Stop image acquisition (just in case).
        self._cam.stop_acquisition()

        # Disconnect from camera.
        with _aravis_mutex:
            self._stream = None
            self._chunk_parser = None
            self._cam = None

        # Mark instrument as closed.
        super().close()

    @rpc_method
    def reset(self) -> None:
        """Reset the camera.

        Resetting triggers a complete reboot of the camera and involves
        temporarily closing and re-opening the network connection.
        """
        _logger.info("Resetting %s", self._name)
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        dev.get_feature('DeviceReset').execute()
        self.close()
        time.sleep(10)
        self.open()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return a QMI_InstrumentIdentification instance."""
        self._check_is_open()
        assert self._cam is not None
        vendor_name   = self._cam.get_vendor_name()
        model_name    = self._cam.get_model_name()
        dev = self._cam.get_device()
        serial_number = dev.get_feature('DeviceSerialNumber').get_value_as_string()
        version       = dev.get_feature('DeviceVersion').get_value_as_string()
        return QMI_InstrumentIdentification(vendor=vendor_name,
                                            model=model_name,
                                            serial=serial_number,
                                            version=version)

    @rpc_method
    def get_ip_address(self) -> str:
        """Return IP address of the camera device."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        address = dev.get_device_address()
        ip_address_str = address.get_address().to_string()
        return ip_address_str

    @rpc_method
    def get_device_info(self) -> Dict[str, Any]:
        """Return device information."""
        self._check_is_open()
        assert self._cam is not None

        info = {}

        keys = [
            "DeviceVendorName",
            "DeviceModelName",
            "DeviceVersion",
            "DeviceSerialNumber",
            "DeviceID",
            "DeviceFirmwareVersion",
            "pgrSensorDescription",
            "DeviceTemperature",
            "pgrPowerSupplyVoltage",
            "pgrPowerSupplyCurrent",
        ]

        dev = self._cam.get_device()
        for key in keys:
            f = dev.get_feature(key)
            if f is not None:
                if f.get_value_type().name == "gdouble":
                    v = f.get_value()
                else:
                    v = f.get_value_as_string()
                info[key] = v

        return info

    @rpc_method
    def get_frame_rate(self) -> float:
        """Return the acquisition frame rate in frames per second."""
        self._check_is_open()
        assert self._cam is not None
        return self._cam.get_frame_rate()

    @rpc_method
    def get_frame_rate_auto(self) -> str:
        """Return the automatic frame rate mode ("Off", "Once", or "Continuous")."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        return dev.get_feature('AcquisitionFrameRateAuto').get_string_value()

    @rpc_method
    def set_frame_rate(self, frame_rate: Optional[float] = None, auto_mode: str = "Off") -> None:
        """Set the acquisition frame rate and enable or disable automatic frame rate.

        :argument frame_rate: Frame rate in frame per second.
        :argument auto_mode: Automatic frame rate mode ("Off" or "Continuous").
        """
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        dev.get_feature('AcquisitionFrameRateEnabled').set_value(True)
        dev.get_feature('AcquisitionFrameRateAuto').set_string_value(auto_mode)
        if frame_rate is not None:
            self._cam.set_frame_rate(frame_rate)

    @rpc_method
    def get_gain(self) -> float:
        """Return analog gain in dB."""
        self._check_is_open()
        assert self._cam is not None
        return self._cam.get_gain()

    @rpc_method
    def get_gain_auto(self) -> str:
        """Return the automatic gain mode ("Off", "Once", or "Continuous")."""
        self._check_is_open()
        assert self._cam is not None
        return Aravis.Auto.to_string(self._cam.get_gain_auto())

    @rpc_method
    def set_gain(self, gain: Optional[float] = None, auto_mode: str = "Off") -> None:
        """Set analog gain in dB and enable or disable automatic gain.

        :argument gain: Analog gain in dB.
        :argument auto_mode: Automatic gain mode ("Off", "Once", or "Continuous").
        """
        self._check_is_open()
        assert self._cam is not None
        self._cam.set_gain_auto(Aravis.Auto.from_string(auto_mode))
        if gain is not None:
            self._cam.set_gain(gain)

    @rpc_method
    def get_exposure_mode(self) -> str:
        """Return the exposure mode ("Timed" or "TriggerWidth")."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        return dev.get_feature('ExposureMode').get_string_value()

    @rpc_method
    def set_exposure_mode(self, mode: str) -> None:
        """Set the exposure mode.

        :argument mode: Exposure mode ("Timed" or "TriggerWidth").
        """
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        dev.get_feature('ExposureMode').set_string_value(mode)

    @rpc_method
    def get_exposure_time(self) -> float:
        """Return the exposure time in microseconds."""
        self._check_is_open()
        assert self._cam is not None
        return self._cam.get_exposure_time()

    @rpc_method
    def get_exposure_time_auto(self) -> str:
        """Return the automatic exposure mode ("Off", "Once" or "Continuous")."""
        self._check_is_open()
        assert self._cam is not None
        return Aravis.Auto.to_string(self._cam.get_exposure_time_auto())

    @rpc_method
    def set_exposure_time(self, exposure_time: Optional[float] = None, auto_mode: str = "Off") -> None:
        """Set the exposure time and enable or disable automatic exposure.

        :argument exposure_time: Exposure time in microseconds.
        :argument auto_mode: Automatic exposure mode ("Off", "Once" or "Continuous").
        """
        self._check_is_open()
        assert self._cam is not None
        self._cam.set_exposure_time_auto(Aravis.Auto.from_string(auto_mode))
        if exposure_time is not None:
            self._cam.set_exposure_time(exposure_time)

    @rpc_method
    def get_pixel_format(self) -> str:
        """Return pixel format ("Mono8", "Mono12Packed" or "Mono16")."""
        self._check_is_open()
        assert self._cam is not None
        tbl = {Aravis.PIXEL_FORMAT_MONO_8: "Mono8",
               Aravis.PIXEL_FORMAT_MONO_16: "Mono16",
               Aravis.PIXEL_FORMAT_MONO_12_PACKED: "Mono12Packed"}
        fmt = self._cam.get_pixel_format()
        if fmt not in tbl:
            raise ValueError("Unknown pixel format")
        return tbl[fmt]

    @rpc_method
    def set_pixel_format(self, pixel_format: str) -> None:
        """Set format of the pixel data.

        :argument pixel_format: Format ("Mono8", "Mono12Packed" or "Mono16").
        """
        self._check_is_open()
        assert self._cam is not None
        tbl = {"Mono8": Aravis.PIXEL_FORMAT_MONO_8,
               "Mono16": Aravis.PIXEL_FORMAT_MONO_16,
               "Mono12Packed": Aravis.PIXEL_FORMAT_MONO_12_PACKED}
        if pixel_format not in tbl:
            raise ValueError("Unknown pixel format")
        fmt = tbl[pixel_format]
        self._cam.set_pixel_format(fmt)

    @rpc_method
    def get_image_size(self) -> Tuple[int, int]:
        """Return the current image size.

        :return: Image size as tuple (width, height) in pixels.
        """
        self._check_is_open()
        assert self._cam is not None
        region = self._cam.get_region()
        return (region.width, region.height)

    @rpc_method
    def set_image_size(self, width: int, height: int) -> None:
        """Set the size of images provided by the camera.

        A subset of the sensor area may be selected by setting the image size
        and image offset.

        :argument width: Width of image in pixels (must be a multiple of 4).
        :argument height: Height of image in pixels (must be a multiple of 2).
        """
        self._check_is_open()
        assert self._cam is not None
        region = self._cam.get_region()
        self._cam.set_region(region.x, region.y, width, height)

    @rpc_method
    def get_image_offset(self) -> Tuple[int, int]:
        """Return the current image offset position.

        :return: Offset position as tuple (x, y) in pixels.
        """
        self._check_is_open()
        assert self._cam is not None
        region = self._cam.get_region()
        return (region.x, region.y)

    @rpc_method
    def set_image_offset(self, x: int, y: int) -> None:
        """Set the image offset position.

        :argument x: Horizotal offset from the origin to the area of interest in pixels (must be a multiple of 2).
        :argument y: Vertical offset from the origin to the area of interest in pixels (must be a multiple of 2).
        """
        self._check_is_open()
        assert self._cam is not None
        region = self._cam.get_region()
        self._cam.set_region(x, y, region.width, region.height)

    @rpc_method
    def get_chunk_mode(self) -> Tuple[bool, Dict[str, bool]]:
        """Return the current chunk data configuration.

        :return: A tuple (chunk_data_active, chunk_types_enabled)
            where chunk_data_active is a boolean indicating whether chunk data is active and
            chunk_types_enabled is a dictionary indicating which chunk types are enabled.
        """
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        active = self._cam.get_chunk_mode()
        chunk_types = {}
        for chunk_type in dev.get_feature('ChunkSelector').get_available_string_values():
            dev.get_feature('ChunkSelector').set_string_value(chunk_type)
            chunk_types[chunk_type] = dev.get_feature('ChunkEnable').get_value()
        return (active, chunk_types)

    @rpc_method
    def set_chunk_mode(self, enable: bool) -> None:
        """Enable or disable chunk data mode.

        When chunk data mode is active, the camera adds some meta-data to each
        acquired image.

        In principle, the camera supports separate enabling of specific
        meta-data types. However this function enables all meta-data types
        when chunk data mode is enabled.
        """
        self._check_is_open()
        assert self._cam is not None

        if enable:
            dev = self._cam.get_device()

            # Enable EXTENDED_CHUNK_DATA payload.
            # By default, when chunk mode is enabled, the camera will send
            # CHUNK_DATA payload. Received image buffers in this format do
            # not contain width/height/format meta-data, which are required
            # by our image processing code.
            # By setting the extended_chunk_data_enable bit in the
            # Stream Channel Configuration Register, we ask that the camera
            # send EXTENDED_CHUNK_DATA instead of CHUNK_DATA. This feature
            # is optional and deprecated, but BlackFly cameras support it.
            dev.write_register(0x0d24, 1)

            for chunk_type in dev.get_feature('ChunkSelector').get_available_string_values():
                dev.get_feature('ChunkSelector').set_string_value(chunk_type)
                dev.get_feature('ChunkEnable').set_value(True)

        self._cam.set_chunk_mode(enable)

    @rpc_method
    def get_device_temperature(self) -> float:
        """Return the temperature of the camera in degrees Celcius."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        return dev.get_feature('DeviceTemperature').get_value()

    @rpc_method
    def get_transmit_failure_count(self) -> int:
        """Return the number of failed transmissions since the last reset."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        return dev.get_feature('TransmitFailureCount').get_value()

    @rpc_method
    def get_black_level(self) -> float:
        """Return analog black level in percent."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        return dev.get_feature('BlackLevel').get_value()

    @rpc_method
    def set_black_level(self, level: float) -> None:
        """Set analog black level.

        :argument level: Black level in percent.
        """
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        dev.get_feature('BlackLevel').set_value(level)

    @rpc_method
    def set_indicator_mode(self, enable: bool) -> None:
        """Enable or disable the indicator LED on the camera."""
        self._check_is_open()
        assert self._cam is not None
        dev = self._cam.get_device()
        sval = "Active" if enable else "Inactive"
        dev.get_feature("DeviceIndicatorMode").set_string_value(sval)

    @rpc_method
    def is_streaming(self) -> bool:
        """Return True if the camera is in streaming mode."""
        return self._stream is not None

    @rpc_method
    def start_acquisition(self, num_frames: Optional[int] = None) -> None:
        """Start frame acquisition.

        Set acquisition mode and number of frames as specified, then start
        frame acquisition in the camera.

        Call get_next_image() to fetch each image as it becomes available.
        Call stop_acquisition() to end the acquisition process.

        :argument num_frames: Number of frames to acquire,
            or None to set the camera in Continuous mode.
        """
        self._check_is_open()
        assert self._cam is not None

        _logger.debug("Starting image acquisition on %s num_frames=%r",
                      self._name, num_frames)

        if num_frames is None:
            # Continuous mode.
            self._cam.set_acquisition_mode(Aravis.AcquisitionMode.CONTINUOUS)
        elif num_frames == 1:
            # Single frame.
            self._cam.set_acquisition_mode(Aravis.AcquisitionMode.SINGLE_FRAME)
        elif num_frames > 0 and num_frames < 65536:
            # Multi-frame.
            self._cam.set_acquisition_mode(Aravis.AcquisitionMode.MULTI_FRAME)
            self._cam.set_frame_count(num_frames)
        else:
            raise QMI_UsageException("Invalid value for num_frames")

        # Create stream object and connect to event handler.
        with _aravis_mutex:
            self._chunk_parser = self._cam.create_chunk_parser()
            self._stream = self._cam.create_stream(None, None)
            self._stream.connect("new-buffer", self._new_image_cb)
            if self._image_callbacks:
                self._stream.set_emit_signals(True)
            else:
                self._stream.set_emit_signals(False)

        # Pre-allocate image buffers and give them to the stream to manage.
        payload = self._cam.get_payload()
        num_bufs = min(128, 128*1024*1024 // payload)
        if num_frames is not None:
            num_bufs = min(num_bufs, num_frames)

        for i in range(num_bufs):
            buf = Aravis.Buffer.new(payload)
            self._stream.push_buffer(buf)

        # Start image acquisition.
        self._cam.start_acquisition()

    @rpc_method
    def stop_acquisition(self) -> None:
        """Stop frame acquisition in the camera."""
        self._check_is_open()
        assert self._cam is not None
        _logger.debug("Stopping image acquisition on %s", self._name)

        # Stop image acquisition.
        self._cam.stop_acquisition()

        # Clean up stream object.
        if self._stream is not None:
            self._stream.set_emit_signals(False)
        self._stream = None
        self._chunk_parser = None

    @rpc_method
    def get_next_image(self, timeout: Optional[float] = None) -> ImageInfo:
        """Return the next image from the current acquisition.

        This function blocks until the next image is available.
        It then returns a named tuple containing image attributes
        as well as pixel data (as a Numpy array). The image is
        then released from the PySpin buffer.

        This function must only be used when the camera is in
        acquisition mode (after start_acquisition()).

        This function must only be called if a next image is expected
        (based on the num_frames parameter to start_acquisition()).
        """
        self._check_is_open()
        assert self._cam is not None

        if self._stream is None:
            raise QMI_InstrumentException("Camera not in streaming mode")

        if timeout is None:
            buf = self._stream.pop_buffer()
        else:
            buf = self._stream.timeout_pop_buffer(int(1000000 * timeout))

        if buf is None:
            raise QMI_TimeoutException("Timeout while waiting for image")

        if buf.get_status() != Aravis.BufferStatus.SUCCESS:
            raise QMI_InstrumentException("Received incomplete image data")

        img = self._convert_image(buf)

        self._stream.push_buffer(buf)

        return img

    def register_image_callback(self, callback: Callable[[ImageInfo], None]) -> None:
        """Register callback function to be invoked when a new image becomes available.

        Note that the callback function may be invoked from a background thread.
        """
        with _aravis_mutex:
            self._image_callbacks.append(callback)
            if self._stream is not None:
                self._stream.set_emit_signals(True)

    def unregister_image_callback(self, callback: Callable) -> None:
        """Unregister the specified image callback function."""
        with _aravis_mutex:
            self._image_callbacks.remove(callback)
