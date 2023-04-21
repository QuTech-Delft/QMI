from enum import Enum


def update_device_list():
    ...


def get_n_devices():
    ...


def get_device_vendor(d):
    ...


def get_device_model(d):
    ...


def get_device_serial_nbr(d):
    ...


def get_device_address(d):
    ...


def get_device_id(d):
    ...


class BufferPayloadType(Enum):
    CHUNK_DATA = 1
    EXTENDED_CHUNK_DATA = 2


class BufferStatus(Enum):
    SUCCESS = 1
    FAILURE = 2


class AcquisitionMode(Enum):
    CONTINUOUS = 1
    SINGLE_FRAME = 2
    MULTI_FRAME = 3


class PixelFormat(Enum):
    MONO_8 = 0xFFF1
    MONO_16 = 0xFFF2
    MONO_12_PACKED = 0xFFF3
    INVALID = 0


PIXEL_FORMAT_MONO_8 = PixelFormat.MONO_8.value
PIXEL_FORMAT_MONO_16 = PixelFormat.MONO_16.value
PIXEL_FORMAT_MONO_12_PACKED = PixelFormat.MONO_12_PACKED.value
PIXEL_FORMAT_INVALID = PixelFormat.INVALID.value


class Auto:
    def to_string(self, a):
        ...

    def from_string(self, a):
        ...


class GvDevice:
    def get_feature(self, f):
        ...

    def get_device_address(self):
        ...

    def write_register(self, r, v):
        ...


class ValueType:
    name = None


class ChunkParser:
    def get_float_value(self, b, v):
        ...


class GcCommand:
    def execute(self):
        ...

    def get_value_type(self):
        ...


class GcRegisterNode:
    def get_value_as_string(self):
        ...

    def get_value_type(self):
        ...

    def get_value(self):
        ...


class GcEnumeration:
    def get_string_value(self):
        ...

    def set_string_value(self, a):
        ...

    def get_available_string_values(self):
        ...

    def get_value_type(self):
        ...

    def get_value_as_string(self):
        ...


class GcBoolean:
    def get_value(self):
        ...

    def set_value(self, b):
        ...

    def get_value_type(self):
        ...

    def get_value_as_string(self):
        ...


class GcIntegerNode:
    def get_value(self):
        ...

    def set_value(self, b):
        ...

    def get_value_type(self):
        ...

    def get_value_as_string(self):
        ...


class GcFloatNode:
    def get_value_as_string(self):
        ...

    def get_value_type(self):
        ...


class GcRegisterDescriptionNode:
    def get_value_as_string(self):
        ...

    def get_value_type(self):
        ...


class Buffer:
    def new(self, p):
        ...

    def get_image_width(self):
        ...

    def get_image_height(self):
        ...

    def get_image_x(self):
        ...

    def get_image_y(self):
        ...

    def get_image_pixel_format(self):
        ...

    def get_frame_id(self):
        ...

    def get_timestamp(self):
        ...

    def get_data(self):
        ...

    def get_payload_type(self):
        ...

    def get_status(self):
        ...


class Stream:
    def try_pop_buffer(self):
        ...

    def push_buffer(self, b):
        ...

    def connect(self, n, c):
        ...

    def set_emit_signals(self, b):
        ...

    def pop_buffer(self):
        ...

    def timeout_pop_buffer(self, t):
        ...


class Address:
    def get_address(self):
        ...


class InetAddress:
    def to_string(self):
        ...


class Region:
    x = None
    y = None
    width = None
    height = None


class Camera:
    def new(self, d):
        ...

    def start_acquisition(self):
        ...

    def stop_acquisition(self):
        ...

    def get_device(self):
        ...

    def get_vendor_name(self):
        ...

    def get_model_name(self):
        ...

    def get_device_address(self):
        ...

    def get_frame_rate(self):
        ...

    def get_gain(self):
        ...

    def get_gain_auto(self):
        ...

    def get_pixel_format(self):
        ...

    def get_exposure_time(self):
        ...

    def get_exposure_time_auto(self):
        ...

    def get_region(self):
        return Region()

    def get_chunk_mode(self):
        ...

    def get_payload(self):
        ...

    def set_gain(self, g):
        ...

    def set_exposure_time(self, e):
        ...

    def set_pixel_format(self, f):
        ...

    def set_region(self, rx, ry, w, h):
        ...

    def set_acquisition_mode(self, m):
        ...

    def set_frame_count(self, n):
        ...

    def set_frame_rate(self, r):
        ...

    def set_gain_auto(self, g):
        ...

    def set_exposure_time_auto(self, a):
        ...

    def set_chunk_mode(self, c):
        ...

    def create_chunk_parser(self):
        ...

    def create_stream(self, a, b):
        return Stream()
